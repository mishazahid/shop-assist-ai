"""
embedding_service.py
--------------------
Provides semantic (meaning-based) search on top of the product catalog
using OpenAI text embeddings and cosine similarity.

How it works:
  1. When products are loaded, we call build_product_embeddings() once.
     This converts each product's text (title + vendor + category +
     description + tags) into a 1536-dimensional number vector via
     OpenAI's "text-embedding-3-small" model.

  2. When the user types a query, we call semantic_search().
     This converts the query into the same kind of vector and measures
     how "close" (cosine similarity) it is to every product vector.

  3. Products are returned sorted by similarity — the best matches come first.

Everything is stored in plain Python lists and NumPy arrays in memory.
No database, no FAISS — fast enough for a typical store catalog.
"""

import os
import numpy as np
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI setup ───────────────────────────────────────────────────────────────
client          = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
EMBEDDING_MODEL = "text-embedding-3-small"   # cheap, fast, 1536 dimensions

# ── In-memory embedding store ──────────────────────────────────────────────────
# These three variables are filled by build_product_embeddings() and read by
# semantic_search().  They stay in memory for the life of the server process.

_product_ids: list[str]       = []      # product IDs in the same order as matrix rows
_embedding_matrix: np.ndarray | None = None  # shape (N, 1536), one row per product


# ── Helper ─────────────────────────────────────────────────────────────────────

def _build_product_text(row: pd.Series) -> str:
    """
    Combine a product row's fields into a single text string for embedding.

    We repeat title and category because they're the strongest signals —
    repeating a field is a simple way to increase its weight.
    """
    # products_df uses "title"; variants_df uses "product_title" — handle both
    title    = str(row.get("title") or row.get("product_title") or "")
    vendor   = str(row.get("vendor")   or "")
    category = str(row.get("category") or "")
    desc     = str(row.get("description") or "")
    tags     = str(row.get("tags") or "")

    # Title and category repeated twice to up-weight them
    combined = f"{title} {title} {vendor} {category} {category} {tags} {desc}"

    # Collapse whitespace and cap at 2000 chars to keep token usage low
    return " ".join(combined.split())[:2000]


# ── Public API ─────────────────────────────────────────────────────────────────

def build_product_embeddings(products_df: pd.DataFrame) -> bool:
    """
    Generate OpenAI embeddings for every product and store them in memory.

    Call this once after loading CSV data (startup) and again after each
    /sync-products so the semantic index stays in sync with the catalog.

    Parameters
    ----------
    products_df : pd.DataFrame
        The product-level DataFrame from data_cleaner.clean_products().

    Returns
    -------
    bool : True if embeddings were built successfully, False on error.
    """
    global _product_ids, _embedding_matrix

    if products_df.empty:
        print("[embeddings] No products to embed — skipping.")
        return False

    print(f"[embeddings] Building embeddings for {len(products_df)} products…")

    # Build one text string per product
    ids   = products_df["product_id"].astype(str).tolist()
    texts = [_build_product_text(row) for _, row in products_df.iterrows()]

    try:
        all_vectors = []
        batch_size  = 100  # OpenAI allows up to 2048; 100 is a safe batch size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # One API call per batch — returns one embedding vector per input
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
            )

            # Convert each embedding to a NumPy float32 array
            vectors = [np.array(e.embedding, dtype=np.float32) for e in response.data]
            all_vectors.extend(vectors)

            print(f"[embeddings] Embedded {min(i + batch_size, len(texts))}/{len(texts)}")

        # Store everything in module-level globals
        _product_ids      = ids
        _embedding_matrix = np.vstack(all_vectors)  # shape: (N, 1536)

        print(f"[embeddings] Done. {len(_product_ids)} products indexed for semantic search.")
        return True

    except Exception as e:
        print(f"[embeddings] ERROR building embeddings: {e}")
        print("[embeddings] Semantic search will be unavailable; keyword search still works.")
        return False


def get_query_embedding(query: str) -> np.ndarray | None:
    """
    Convert a search query into a 1536-dimensional embedding vector.

    Returns None if the API call fails (e.g. bad key, quota exceeded).
    """
    try:
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[query],
        )
        return np.array(response.data[0].embedding, dtype=np.float32)

    except Exception as e:
        print(f"[embeddings] Failed to embed query '{query[:50]}': {e}")
        return None


def semantic_search(query: str, top_k: int = 20) -> list[str]:
    """
    Find the top_k most semantically similar product IDs for a query.

    Uses cosine similarity:
      cos_sim(A, B) = dot(A, B) / (||A|| * ||B||)

    A score of 1.0 means identical meaning; 0.0 means unrelated.

    Parameters
    ----------
    query  : str  — the customer's message
    top_k  : int  — how many candidate product IDs to return (before filtering)

    Returns
    -------
    list[str] : product_ids sorted by similarity, best match first.
    Empty list if embeddings aren't built or the API call fails.
    """
    if not embeddings_ready():
        print("[embeddings] Not ready — falling back to keyword search.")
        return []

    # Embed the query
    query_vec = get_query_embedding(query)
    if query_vec is None:
        return []

    # Normalise the query vector to unit length
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)

    # Normalise all product vectors (row-wise)
    row_norms  = np.linalg.norm(_embedding_matrix, axis=1, keepdims=True) + 1e-9
    normed_mat = _embedding_matrix / row_norms   # shape: (N, 1536)

    # Dot product of each normalised product vector with the normalised query
    # = cosine similarity for each product
    scores = normed_mat @ query_norm             # shape: (N,)

    # Sort indices by score descending; take top_k
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [_product_ids[i] for i in top_indices]


def embeddings_ready() -> bool:
    """Return True if the embedding index is loaded and ready to query."""
    return _embedding_matrix is not None and len(_product_ids) > 0
