"""
data_cleaner.py
---------------
Transforms raw Shopify product JSON into two clean Pandas DataFrames:

  products_df  — one row per product
  variants_df  — one row per variant (a product has many variants for sizes/colors)

Both DataFrames are saved to CSV so the frontend and AI can load them
instantly without re-fetching from Shopify every time.

Note: IDs are stored as strings to prevent Excel from displaying them in
scientific notation (e.g., 7.12e+13 instead of 7123456789012).
"""

import os
import re
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
# DATA_DIR is relative to the backend/ folder
_HERE     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(_HERE, os.getenv("DATA_DIR", "data"))
PRODUCTS_CSV = os.path.join(DATA_DIR, "products.csv")
VARIANTS_CSV = os.path.join(DATA_DIR, "variants.csv")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove HTML tags from Shopify product descriptions."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _get_size_color(product: dict, variant: dict) -> tuple[str, str]:
    """
    Return (size, color) for a variant by matching the product's option names.

    Shopify stores up to 3 options per product (e.g., Size, Color, Material).
    Each variant has option1 / option2 / option3 matching those positions.
    """
    options = product.get("options", [])
    size = ""
    color = ""
    for i, opt in enumerate(options, start=1):
        opt_name  = opt.get("name", "").lower()
        opt_value = variant.get(f"option{i}", "") or ""
        if opt_value.lower() == "default title":
            opt_value = ""
        if "size" in opt_name:
            size = opt_value
        elif "color" in opt_name or "colour" in opt_name:
            color = opt_value
    return size, color


# ── Main functions ─────────────────────────────────────────────────────────────

def clean_products(raw_products: list[dict]) -> pd.DataFrame:
    """
    Build a product-level DataFrame. One row per product.

    Columns: product_id, title, vendor, category, description,
             tags, price (lowest variant), image_url, status
    """
    rows = []
    for p in raw_products:
        # Use the first product image if available
        images    = p.get("images", [])
        image_url = images[0].get("src", "") if images else ""

        # Use the lowest variant price as the product price
        variants  = p.get("variants", [])
        prices    = [float(v.get("price", 0) or 0) for v in variants]
        min_price = min(prices) if prices else 0.0

        rows.append({
            "product_id":   str(p.get("id", "")),   # string → no Excel scientific notation
            "title":        (p.get("title") or "").strip(),
            "vendor":       (p.get("vendor") or "").strip(),
            "category":     (p.get("product_type") or "").strip(),
            "description":  _strip_html(p.get("body_html", "")),
            "tags":         (p.get("tags") or ""),
            "price":        min_price,
            "image_url":    image_url,
            "handle":       p.get("handle", ""),
            "status":       p.get("status", ""),
        })

    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=["product_id"], inplace=True)

    # Keep only products the store has marked as active
    if "status" in df.columns:
        df = df[df["status"] == "active"].copy()

    df.reset_index(drop=True, inplace=True)
    return df


def clean_variants(raw_products: list[dict]) -> pd.DataFrame:
    """
    Build a variant-level DataFrame. One row per variant.

    Columns: variant_id, product_id, product_title, vendor, category,
             sku, size, color, price, compare_at_price, inventory,
             in_stock, image_url, tags
    """
    rows = []
    for p in raw_products:
        product_id    = str(p.get("id", ""))
        product_title = (p.get("title") or "").strip()
        vendor        = (p.get("vendor") or "").strip()
        category      = (p.get("product_type") or "").strip()
        tags          = (p.get("tags") or "")

        images        = p.get("images", [])
        product_image = images[0].get("src", "") if images else ""

        for v in p.get("variants", []):
            size, color = _get_size_color(p, v)

            # If the variant has its own image, use that; fall back to product image
            variant_image = product_image
            variant_image_id = v.get("image_id")
            if variant_image_id:
                for img in images:
                    if img.get("id") == variant_image_id:
                        variant_image = img.get("src", product_image)
                        break

            inventory = int(v.get("inventory_quantity") or 0)

            rows.append({
                "variant_id":       str(v.get("id", "")),   # string → no Excel scientific notation
                "product_id":       product_id,
                "product_title":    product_title,
                "vendor":           vendor,
                "category":         category,
                "tags":             tags,
                "sku":              (v.get("sku") or ""),
                "size":             size,
                "color":            color,
                "price":            float(v.get("price") or 0),
                "compare_at_price": float(v.get("compare_at_price") or 0),
                "inventory":        inventory,
                "in_stock":         inventory > 0,
                "image_url":        variant_image,
            })

    df = pd.DataFrame(rows)
    df.drop_duplicates(subset=["variant_id"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def save_to_csv(products_df: pd.DataFrame, variants_df: pd.DataFrame) -> None:
    """Save both DataFrames to CSV files inside DATA_DIR."""
    os.makedirs(DATA_DIR, exist_ok=True)
    products_df.to_csv(PRODUCTS_CSV, index=False)
    variants_df.to_csv(VARIANTS_CSV, index=False)
    print(f"Saved {len(products_df):,} products  → {PRODUCTS_CSV}")
    print(f"Saved {len(variants_df):,} variants  → {VARIANTS_CSV}")


def load_from_csv() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load previously saved DataFrames from CSV, preserving ID types."""
    products_df = pd.read_csv(PRODUCTS_CSV, dtype={"product_id": str})
    variants_df = pd.read_csv(
        VARIANTS_CSV,
        dtype={"variant_id": str, "product_id": str},
    )
    variants_df["in_stock"] = variants_df["in_stock"].astype(bool)
    return products_df, variants_df


def csv_exists() -> bool:
    """Return True if both CSV files already exist on disk."""
    return os.path.isfile(PRODUCTS_CSV) and os.path.isfile(VARIANTS_CSV)
