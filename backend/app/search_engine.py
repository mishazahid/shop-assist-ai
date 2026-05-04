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

    # Merge product-level fields into the variant table
    desc_map       = products_df.set_index("product_id")["description"].to_dict()
    df["description"] = df["product_id"].map(desc_map).fillna("")

    # Merge handle so the frontend can build Shopify product page URLs
    if "handle" in products_df.columns:
        handle_map  = products_df.set_index("product_id")["handle"].to_dict()
        df["handle"] = df["product_id"].map(handle_map).fillna("")

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
        "handle", "description", "tags", "score",
    ]
    cols = [c for c in display_cols if c in df.columns]
    return df[cols].head(top_n).reset_index(drop=True)


def search_with_fallback(
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
) -> tuple[pd.DataFrame, str]:
    """
    Search with automatic progressive filter relaxation.

    Tries up to 5 levels — each level drops one more filter until
    results are found.  Returns the first non-empty result set.

    Fallback order:
      Level 0 — all filters (exact match)
      Level 1 — drop size
      Level 2 — drop size + color
      Level 3 — drop size + color + price
      Level 4 — drop size + color + price + semantic limit (broadest)

    Vendor and category are intentional and never dropped — if the user
    said "Adidas" we don't silently switch to other brands.

    Returns
    -------
    (pd.DataFrame, str)
      DataFrame : best matching results (up to top_n rows)
      str       : human-readable description of what was relaxed,
                  e.g. "size", "size and color", "size, color, and price"
                  Empty string "" means an exact match was found.
    """

    # Record which variant filters were originally active
    had_size  = size  is not None
    had_color = color is not None
    had_price = max_price is not None

    def _run(s, c, p, sem_ids):
        """Thin wrapper so we don't repeat the long argument list."""
        return search_products(
            variants_df          = variants_df,
            products_df          = products_df,
            keyword              = keyword,
            vendor               = vendor,
            category             = category,
            max_price            = p,
            size                 = s,
            color                = c,
            in_stock_only        = in_stock_only,
            top_n                = top_n,
            semantic_product_ids = sem_ids,
        )

    def _label(drop_size, drop_color, drop_price):
        """Build a readable string of which filters were relaxed."""
        parts = []
        if drop_size  and had_size:  parts.append("size")
        if drop_color and had_color: parts.append("color")
        if drop_price and had_price: parts.append("price")
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]} and {parts[1]}"
        return f"{parts[0]}, {parts[1]}, and {parts[2]}"

    # ── Level 0: exact match (all filters active) ─────────────────────────────
    df = _run(size, color, max_price, semantic_product_ids)
    if not df.empty:
        return df, ""

    # ── Level 1: relax size ───────────────────────────────────────────────────
    if had_size:
        print("[search] No results — relaxing size filter.")
        df = _run(None, color, max_price, semantic_product_ids)
        if not df.empty:
            return df, _label(True, False, False)

    # ── Level 2: relax size + color ───────────────────────────────────────────
    if had_color:
        print("[search] No results — relaxing size + color filters.")
        df = _run(None, None, max_price, semantic_product_ids)
        if not df.empty:
            return df, _label(True, True, False)

    # ── Level 3: relax size + color + price ───────────────────────────────────
    if had_price:
        print("[search] No results — relaxing size + color + price filters.")
        df = _run(None, None, None, semantic_product_ids)
        if not df.empty:
            return df, _label(True, True, True)

    # ── Level 4: top semantic matches — ignore all variant filters ────────────
    # Also drop the semantic candidate limit so we search the full catalog.
    # Vendor and category are still kept (user specifically asked for them).
    print("[search] No results — returning top semantic/keyword matches.")
    df = _run(None, None, None, None)
    if not df.empty:
        return df, "exact match"

    # Nothing at all — return empty so AI can say "sorry, nothing found"
    return df, "exact match"


# ── Vague / recommendation query detection ────────────────────────────────────

_VAGUE_KEYWORDS = {
    "recommend", "recommendation", "recommendations",
    "suggest", "suggestion", "suggestions",
    "popular", "trending",
    "best seller", "bestsellers", "best sellers",
    "best", "top picks", "top rated",
    "anything", "something",
    "surprise me", "show me something",
}


def is_vague_query(text: str) -> bool:
    """
    Return True if the query is a general recommendation / discovery request
    rather than a specific product search.

    Called before intent extraction so the pipeline can skip hard filters
    for queries like "recommend something stylish" or "what's popular".

    Examples that return True:
      "recommend something stylish"
      "what's popular right now"
      "suggest something nice"
      "show me your best products"

    Examples that return False (specific filters present):
      "black Nike shoes under $100"
      "Adidas hoodie in size M"
    """
    lower = text.lower().strip()
    return any(kw in lower for kw in _VAGUE_KEYWORDS)


def recommend_products(
    variants_df:          pd.DataFrame,
    products_df:          pd.DataFrame,
    semantic_product_ids: list  | None = None,
    top_n:                int          = 5,
) -> pd.DataFrame:
    """
    Return top recommended products for vague / exploratory queries.

    Skips all hard filters (size, color, price, vendor, category).

    Ranking priority:
      1. Semantic similarity  — captures the stylistic intent of the query
         (only when embeddings are available; supplied by the caller)
      2. Inventory level      — high stock is a proxy for popular/featured items
      3. Price ascending      — tie-break toward more accessible price points

    Parameters
    ----------
    variants_df          : variant-level DataFrame from data_cleaner
    products_df          : product-level DataFrame from data_cleaner
    semantic_product_ids : product_ids ordered by semantic similarity, best first.
                           Pass None to fall back to inventory-only ranking.
    top_n                : maximum number of results to return

    Returns
    -------
    pd.DataFrame with one row per recommended product (best variant selected).
    """
    df = variants_df.copy()

    # Merge product-level fields (same as search_products)
    desc_map = products_df.set_index("product_id")["description"].to_dict()
    df["description"] = df["product_id"].map(desc_map).fillna("")

    if "handle" in products_df.columns:
        handle_map = products_df.set_index("product_id")["handle"].to_dict()
        df["handle"] = df["product_id"].map(handle_map).fillna("")

    # In-stock only — out-of-stock items shouldn't be recommended
    df = df[df["in_stock"] == True].copy()

    if df.empty:
        return df

    if semantic_product_ids:
        # Semantic rank drives order; inventory breaks ties within the same rank
        rank_map = {pid: rank for rank, pid in enumerate(semantic_product_ids)}
        df["sem_rank"] = df["product_id"].map(rank_map).fillna(9999).astype(int)
        df.sort_values(
            ["sem_rank", "inventory", "price"],
            ascending=[True, False, True],
            inplace=True,
        )
    else:
        # No embeddings — rank by inventory (popularity proxy) then price
        df.sort_values(["inventory", "price"], ascending=[False, True], inplace=True)

    # One best variant per product (already the top row after sorting)
    df.drop_duplicates(subset=["product_id"], keep="first", inplace=True)

    display_cols = [
        "product_id", "product_title", "vendor", "category",
        "size", "color", "price", "inventory", "image_url",
        "handle", "description", "tags",
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
