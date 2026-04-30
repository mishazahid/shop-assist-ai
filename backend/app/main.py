"""
main.py
-------
FastAPI application — the backend for ShopAssist AI.

Endpoints:
  GET  /health          — health check (product / variant counts)
  GET  /sync-products   — fetch from Shopify, clean, save CSV, rebuild embeddings
  GET  /products        — return all products from CSV
  GET  /variants        — return all variants from CSV
  POST /search          — search products with structured filters
  POST /chat            — AI-powered natural-language shopping assistant

Run locally:
  cd backend
  uvicorn app.main:app --reload
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.shopify_client    import fetch_all_products
from app.data_cleaner      import (
    clean_products, clean_variants,
    save_to_csv, load_from_csv, csv_exists,
)
from app.search_engine     import search_products
from app.ai_assistant      import ask_assistant
from app.embedding_service import build_product_embeddings   # NEW: semantic search index

load_dotenv()

# ── In-memory data store ───────────────────────────────────────────────────────
# DataFrames are loaded once at startup and reused for every request.
# Call GET /sync-products to refresh them from Shopify.
_products_df: pd.DataFrame = pd.DataFrame()
_variants_df: pd.DataFrame = pd.DataFrame()


def _load_data() -> None:
    """Load products and variants from CSV into memory."""
    global _products_df, _variants_df
    if csv_exists():
        _products_df, _variants_df = load_from_csv()
        print(
            f"[startup] Loaded {len(_products_df):,} products, "
            f"{len(_variants_df):,} variants from CSV."
        )
    else:
        print("[startup] No CSV found. Call GET /sync-products first.")


# ── Application lifecycle ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once when the server starts.
    1. Load CSV data into memory
    2. Build semantic embeddings for all products (if data is available)
    """
    _load_data()

    # Build the semantic search index so queries like "casual summer shoes"
    # work out of the box — even without exact keyword matches.
    if not _products_df.empty:
        print("[startup] Building semantic embeddings…")
        build_product_embeddings(_products_df)
    else:
        print("[startup] No products loaded — skipping embedding build.")
        print("[startup] Call GET /sync-products to fetch products from Shopify.")

    yield   # Server is now running — yield until shutdown


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShopAssist AI API",
    description="Shopify AI Shopping Assistant backend",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow the React dev server to call this backend without CORS errors
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite default port
        "http://localhost:3000",   # Create React App / other
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Body for POST /search — all fields optional."""
    query:         Optional[str]   = None
    vendor:        Optional[str]   = None
    category:      Optional[str]   = None
    max_price:     Optional[float] = None
    size:          Optional[str]   = None
    color:         Optional[str]   = None
    in_stock_only: bool            = True
    top_n:         int             = 10


class ChatRequest(BaseModel):
    """Body for POST /chat."""
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """
    Simple health check.
    Returns how many products and variants are currently loaded in memory.
    """
    return {
        "status":   "ok",
        "products": len(_products_df),
        "variants": len(_variants_df),
    }


@app.get("/sync-products")
def sync_products():
    """
    Fetch all products from Shopify, clean the data, save to CSV,
    reload the in-memory DataFrames, and rebuild the semantic search index.

    This may take 10–30 seconds on a large catalog (most of the time is
    the Shopify API + OpenAI embedding calls).
    """
    global _products_df, _variants_df

    try:
        # Step 1: Fetch from Shopify
        print("[sync] Fetching products from Shopify…")
        raw = fetch_all_products()

        # Step 2: Clean into DataFrames
        print("[sync] Cleaning data…")
        _products_df = clean_products(raw)
        _variants_df = clean_variants(raw)

        # Step 3: Persist to CSV so future restarts don't need to re-sync
        save_to_csv(_products_df, _variants_df)

        # Step 4: Rebuild the semantic embedding index
        # This enables meaning-based search (e.g. "casual summer outfit")
        print("[sync] Rebuilding semantic embeddings…")
        build_product_embeddings(_products_df)

        return {
            "status":   "ok",
            "products": len(_products_df),
            "variants": len(_variants_df),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/products")
def get_products(limit: int = 100, offset: int = 0):
    """Return all products from the local CSV (paginated)."""
    if _products_df.empty:
        raise HTTPException(
            status_code=503,
            detail="Product data not loaded. Call GET /sync-products first.",
        )
    slice_df = _products_df.iloc[offset : offset + limit]
    return {
        "total":    len(_products_df),
        "products": slice_df.to_dict(orient="records"),
    }


@app.get("/variants")
def get_variants(limit: int = 200, offset: int = 0):
    """Return all variants from the local CSV (paginated)."""
    if _variants_df.empty:
        raise HTTPException(
            status_code=503,
            detail="Variant data not loaded. Call GET /sync-products first.",
        )
    slice_df = _variants_df.iloc[offset : offset + limit]
    return {
        "total":    len(_variants_df),
        "variants": slice_df.to_dict(orient="records"),
    }


@app.post("/search")
def search(req: SearchRequest):
    """
    Search products with optional keyword and structured filters.

    This endpoint uses keyword-only search (no AI).
    Use POST /chat for the full AI-powered experience.
    """
    if _products_df.empty or _variants_df.empty:
        raise HTTPException(
            status_code=503,
            detail="Product data not loaded. Call GET /sync-products first.",
        )

    results = search_products(
        variants_df   = _variants_df,
        products_df   = _products_df,
        keyword       = req.query,
        vendor        = req.vendor,
        category      = req.category,
        max_price     = req.max_price,
        size          = req.size,
        color         = req.color,
        in_stock_only = req.in_stock_only,
        top_n         = req.top_n,
    )

    return {
        "total":   len(results),
        "results": results.to_dict(orient="records"),
    }


@app.post("/chat")
def chat(req: ChatRequest):
    """
    AI-powered shopping assistant.

    Full pipeline:
      1. Extract search intent from the user's natural-language message
      2. Run semantic + keyword search on the product catalog
      3. Generate a friendly AI recommendation response
      4. Return structured JSON for the React frontend

    Response:
      message  / answer : AI-written response text
      products          : list of product objects (for product cards)
      recommendations   : [{product_id, reason}] from the AI
    """
    if _products_df.empty or _variants_df.empty:
        raise HTTPException(
            status_code=503,
            detail="Product data not loaded. Call GET /sync-products first.",
        )

    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        result = ask_assistant(
            user_message = req.message,
            variants_df  = _variants_df,
            products_df  = _products_df,
            top_n        = 5,
        )
        return result

    except Exception as exc:
        # Log the full error on the server but return a clean message to the user
        print(f"[chat] Unhandled error: {exc}")
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")
