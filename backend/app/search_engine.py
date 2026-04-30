"""
search_engine.py
----------------
Hybrid product search engine combining semantic ranking with hard filters.

search_products() supports two modes:

  SEMANTIC MODE (default when embeddings are ready):
    - Products are pre-ranked by cosine similarity to the query
    - Hard filters (size, color, price, etc.) are applied on top
    - Result order follows semantic relevance, then price

  KEYWORD MODE (fallback when embeddings are not available):
    - Products are scored by how many query terms appear in their text
    - Exact title match gets a relevance boost
    - Same hard filters are applied

In both modes:
  - Only in-stock variants are returned (by default)
  - One best variant is kept per product (no duplicates)
  - Up to top_n results are returned
"""

import re
import pandas as pd


def search_products(
    variants_df:           pd.DataFrame,
    products_df:           pd.DataFrame,
    keyword:               str   | None = None,
    vendor:                str   | None = None,
    category:              str   | None = None,
    max_price:             float | None = None,
    size:                  str   | None = None,
    color:                 str   | None = None,
    in_stock_only:         bool         = True,
    top_n:                 int          = 5,
    semantic_product_ids:  list  | None = None,
) -> pd.DataFrame:
    """
    Search variants and return up to top_n best matches.

    Parameters
    ----------
    variants_df          : variant-level DataFrame from data_cleaner
    products_df          : product-level DataFrame from data_cleaner
    keyword              : core search word(s), e.g. "running shoes"
    vendor               : brand filter, e.g. "Nike"
    category             : product-type filter, e.g. "shoes"
    max_price            : upper price bound (inclusive)
    size                 : size filter, e.g. "9" or "M"
    color                : color filter, e.g. "black"
    in_stock_only        : if True, skip out-of-stock variants
    top_n                : maximum number of results to return
    semantic_product_ids : ordered list of product_ids from semantic search
                           (best match first). If provided, the semantic
                           order drives ranking and keyword scoring is a
                           tiebreaker only.

    Returns
    -------
    pd.DataFrame with one row per matched product (best variant selected).
    Empty DataFrame if nothing matches.
    """

    # Work on a copy so we never mutate the caller's DataFrames
    df = variants_df.copy()

    # Merge product-level descriptions into the variant table for text search
    desc_map       = products_df.set_index("product_id")["description"].to_dict()
    df["description"] = df["product_id"].map(desc_map).fillna("")

    # ── Hard filter: in-stock ────────────────────────────────────────────────
    if in_stock_only:
        df = df[df["in_stock"] == True].copy()

    if df.empty:
        return df

    # ── Hard filter: vendor/brand ────────────────────────────────────────────
    if vendor:
        df = df[df["vendor"].str.contains(vendor, case=False, na=False)].copy()

    # ── Hard filter: product category/type ───────────────────────────────────
    if category:
        df = df[df["category"].str.contains(category, case=False, na=False)].copy()

    # ── Hard filter: maximum price ───────────────────────────────────────────
    if max_price is not None:
        df = df[df["price"] <= max_price].copy()

    # ── Hard filter: size ────────────────────────────────────────────────────
    if size:
        df = df[df["size"].str.contains(size, case=False, na=False)].copy()

    # ── Hard filter: color ───────────────────────────────────────────────────
    if color:
        df = df[df["color"].str.contains(color, case=False, na=False)].copy()

    if df.empty:
        return df

    # ── Ranking ──────────────────────────────────────────────────────────────

    if semantic_product_ids:
        # SEMANTIC MODE
        # Assign each row a rank based on its position in the semantic results.
        # Products not in the list (shouldn't happen, but just in case) get rank 9999.
        rank_map     = {pid: rank for rank, pid in enumerate(semantic_product_ids)}
        df["sem_rank"] = df["product_id"].map(rank_map).fillna(9999).astype(int)
        df["score"]    = 0  # keyword score used as tiebreaker only

        # Optional keyword tiebreaker: count how many query terms appear in text
        if keyword:
            text = _build_text_column(df)
            for term in keyword.lower().split():
                df["score"] += text.str.count(re.escape(term))

        # Sort: semantic rank first (lower = better), then keyword score (higher = better),
        # then price (lower = better)
        df.sort_values(["sem_rank", "score", "price"],
                       ascending=[True, False, True], inplace=True)

    else:
        # KEYWORD-ONLY MODE (fallback)
        df["score"] = 0

        if keyword:
            kw   = keyword.lower()
            text = _build_text_column(df)

            # Count how many times each query term appears in the combined text
            for term in kw.split():
                df["score"] += text.str.count(re.escape(term))

            # Exact title match gets a big relevance bonus
            title_lower = df["product_title"].fillna("").str.lower()
            df.loc[title_lower.str.contains(kw, na=False), "score"] += 10

            # Drop rows with zero score — they have nothing in common with the query
            df = df[df["score"] > 0].copy()

        # Sort: best score first, then cheapest price
        df.sort_values(["score", "price"], ascending=[False, True], inplace=True)

    if df.empty:
        return df

    # ── Deduplicate: one best variant per product ─────────────────────────────
    # After sorting, "first" is already the best variant per product
    df.drop_duplicates(subset=["product_id"], keep="first", inplace=True)

    # ── Select columns for the response ──────────────────────────────────────
    display_cols = [
        "product_id", "product_title", "vendor", "category",
        "size", "color", "price", "inventory", "image_url",
        "description", "tags", "score",
    ]
    cols = [c for c in display_cols if c in df.columns]
    return df[cols].head(top_n).reset_index(drop=True)


def _build_text_column(df: pd.DataFrame) -> pd.Series:
    """
    Concatenate all searchable text fields into one string per row.
    Used for keyword scoring.
    """
    return (
        df["product_title"].fillna("").str.lower() + " " +
        df["vendor"].fillna("").str.lower()        + " " +
        df["category"].fillna("").str.lower()      + " " +
        df["tags"].fillna("").str.lower()           + " " +
        df["description"].fillna("").str.lower()   + " " +
        df["color"].fillna("").str.lower()         + " " +
        df["size"].fillna("").str.lower()
    )


# ── Utility helpers ───────────────────────────────────────────────────────────
# These are used by the /search endpoint to populate filter dropdowns.

def get_all_vendors(variants_df: pd.DataFrame) -> list[str]:
    return sorted(variants_df["vendor"].dropna().unique().tolist())


def get_all_categories(variants_df: pd.DataFrame) -> list[str]:
    cats = variants_df["category"].dropna().unique().tolist()
    return sorted([c for c in cats if c])


def get_all_sizes(variants_df: pd.DataFrame) -> list[str]:
    sizes = variants_df["size"].dropna().unique().tolist()
    return sorted([s for s in sizes if s])


def get_all_colors(variants_df: pd.DataFrame) -> list[str]:
    colors = variants_df["color"].dropna().unique().tolist()
    return sorted([c for c in colors if c])
