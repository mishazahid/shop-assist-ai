"""
embedding_service.py
--------------------
Provides semantic (meaning-based) search on top of the product catalog
using OpenAI text embeddings and cosine similarity.

How it works:
  1. When products are loaded, we call build_product_embeddings() once.
     This converts each product's text (title + vendor + category +
     description + tags) into a 1536-dimensional number vector via
     OpenAI's "text-embedding-3-small" model, then pre-normalizes
     the matrix so per-query cosine similarity is a single dot product.

  2. When the user types a query, we call semantic_search().
     This embeds the query (1 OpenAI call) and scores it against the
     pre-normalized product matrix in one vectorized operation.

  3. Products are returned sorted by similarity — the best matches come first.

Everything is stored in plain Python lists and NumPy arrays in memory.
No database, no FAISS — fast enough for a typical store catalog.

Performance:
  - Product embeddings: computed once at startup / after sync, never again.
  - Normalized product matrix: pre-computed once and cached; zero work per query.
  - Query embedding: 1 OpenAI API call per search — unavoidable, already minimal.
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
# Filled once by build_product_embeddings(); read on every semantic_search() call.
# Never recomputed unless /sync-products is called.

_product_ids:   list[str]          = []    # product IDs aligned with matrix rows
_embedding_matrix: np.ndarray | None = None  # shape (N, 1536) — raw vectors
_normed_matrix:    np.ndarray | None = None  # shape (N, 1536) — pre-normalized rows
                                              # cached so cosine similarity = one dot product


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

    After generating raw vectors, the matrix is immediately pre-normalized
    (unit L2 norm per row) so that semantic_search() can compute cosine
    similarity as a single dot product — no per-query normalization needed.

    Parameters
    ----------
    products_df : pd.DataFrame
        The product-level DataFrame from data_cleaner.clean_products().

    Returns
    -------
    bool : True if embeddings were built successfully, False on error.
    """
    global _product_ids, _embedding_matrix, _normed_matrix

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

        # Stack raw vectors into a matrix — shape: (N, 1536)
        raw_matrix = np.vstack(all_vectors)

        # Pre-normalize every product row to unit length once.
        # Cosine similarity = dot(unit_a, unit_b), so at query time we only
        # need one matrix-vector multiply — no per-query norm computation.
        row_norms = np.linalg.norm(raw_matrix, axis=1, keepdims=True) + 1e-9
        normed    = (raw_matrix / row_norms).astype(np.float32)

        # Commit atomically — assign all globals together so a concurrent
        # request never sees a partially updated state.
        _product_ids      = ids
        _embedding_matrix = raw_matrix   # kept for potential future use / inspection
        _normed_matrix    = normed       # used by semantic_search() on every query

        print(
            f"[embeddings] Done. {len(_product_ids)} products indexed. "
            f"Normalized matrix cached {_normed_matrix.shape} — "
            f"ready for fast cosine similarity."
        )
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
      cos_sim(A, B) = dot(unit_A, unit_B)

    Product vectors are pre-normalized at build time (_normed_matrix), so
    per-query work is: embed query → normalize query → one dot product.
    No per-query normalization of the product matrix.

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

    # Embed the query — 1 OpenAI API call, unavoidable (query varies per request)
    query_vec = get_query_embedding(query)
    if query_vec is None:
        return []

    # Normalize the query vector to unit length
    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-9)

    # Dot product against pre-normalized product matrix = cosine similarity.
    # _normed_matrix rows are already unit-length, so no division needed here.
    scores = _normed_matrix @ query_norm   # shape: (N,)

    # Sort indices by score descending; take top_k
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [_product_ids[i] for i in top_indices]


def embeddings_ready() -> bool:
    """Return True if the normalized embedding index is loaded and ready to query."""
    return _normed_matrix is not None and len(_product_ids) > 0
