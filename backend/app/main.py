"""
main.py
-------
FastAPI application — the backend for ShopAssist AI.

Endpoints:
  GET  /health              — health check (product / variant counts)
  GET  /sync-products       — fetch from Shopify, clean, save CSV, rebuild embeddings
  GET  /products            — return all products from CSV
  GET  /variants            — return all variants from CSV
  POST /search              — search products with structured filters
  POST /chat                — AI-powered natural-language shopping assistant
  POST /cart/add            — add a variant to the Shopify cart (proxy)
  POST /webhooks/shopify    — Shopify product webhook receiver (auto-sync)
  POST /webhooks/register   — register product webhooks with Shopify
  GET  /webhooks/list       — list registered Shopify webhooks

Run locally:
  cd backend
  uvicorn app.main:app --reload
"""

import os
import hmac
import hashlib
import base64
import threading
from contextlib import asynccontextmanager
from typing import Optional

import time
import requests as http_requests   # renamed to avoid collision with FastAPI
import pandas as pd
from fastapi import FastAPI, HTTPException, Header, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.shopify_client    import fetch_all_products, register_webhooks, list_webhooks
from app.data_cleaner      import (
    clean_products, clean_variants,
    save_to_csv, load_from_csv, csv_exists,
)
from app.search_engine     import (
    search_products,
    get_all_vendors, get_all_categories, get_all_colors,
)
from app.ai_assistant      import ask_assistant
from app.embedding_service import build_product_embeddings
from app.analytics         import init_db, log_query, get_recent_queries, get_total_count, get_summary
from app.widget_config     import load as load_widget_config, save as save_widget_config

load_dotenv()

# ── Admin & webhook secrets ────────────────────────────────────────────────────
ADMIN_API_KEY        = os.getenv("ADMIN_API_KEY", "")
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")

# ── In-memory data store ───────────────────────────────────────────────────────
# DataFrames are loaded once at startup and reused for every request.
# Call GET /sync-products to refresh them from Shopify.
_products_df: pd.DataFrame = pd.DataFrame()
_variants_df: pd.DataFrame = pd.DataFrame()

# ── Conversation memory (per session) ──────────────────────────────────────────
# Maps session_id → {intent: dict, last_active: float}
# Intent is the last merged set of search filters for that session.
# This lets follow-up messages like "under $100" remember the previous context.
_sessions: dict[str, dict] = {}
SESSION_TTL  = 3600   # seconds — sessions expire after 1 hour of inactivity
MAX_SESSIONS = 500    # cap to prevent unbounded memory growth

# ── Background sync state ──────────────────────────────────────────────────────
# Shopify webhooks must receive a 200 response within 5 s or they retry.
# We respond immediately and run the actual sync in a thread.
# _sync_lock prevents concurrent syncs; _sync_pending coalesces rapid events
# so a burst of webhooks (e.g. bulk update) produces at most two syncs.
_sync_lock    = threading.Lock()
_sync_pending = False


def _run_sync(topic: str) -> None:
    """
    Full catalog re-sync meant to run in a background thread.

    Coalescing: if another webhook fires while this sync is running, it sets
    _sync_pending = True instead of stacking another call.  After the current
    sync finishes it checks _sync_pending and re-runs once if needed.
    """
    global _products_df, _variants_df, _sync_pending

    if not _sync_lock.acquire(blocking=False):
        # A sync is already running — mark pending so it re-runs after
        _sync_pending = True
        print(f"[webhook] Sync already in progress ({topic}) — will re-run after.")
        return

    try:
        while True:
            _sync_pending = False
            print(f"[webhook] Background sync starting ({topic})…")
            try:
                raw          = fetch_all_products()
                _products_df = clean_products(raw)
                _variants_df = clean_variants(raw)
                save_to_csv(_products_df, _variants_df)
                build_product_embeddings(_products_df)
                print(
                    f"[webhook] Sync complete: "
                    f"{len(_products_df)} products, {len(_variants_df)} variants."
                )
            except Exception as exc:
                print(f"[webhook] Sync failed: {exc}")

            if not _sync_pending:
                break   # no further events queued — we're done
            print("[webhook] Re-running sync for queued webhook event…")
    finally:
        _sync_lock.release()


def _get_session_intent(session_id: str) -> dict | None:
    """Return the stored intent for a session, or None if expired / not found."""
    session = _sessions.get(session_id)
    if not session:
        return None
    if time.time() - session["last_active"] > SESSION_TTL:
        del _sessions[session_id]
        return None
    return session["intent"]


def _save_session_intent(session_id: str, intent: dict) -> None:
    """Persist the latest merged intent for a session."""
    # Evict the oldest session if we're at capacity
    if len(_sessions) >= MAX_SESSIONS and session_id not in _sessions:
        oldest = min(_sessions, key=lambda k: _sessions[k]["last_active"])
        del _sessions[oldest]
        print(f"[session] Evicted oldest session to stay under {MAX_SESSIONS} limit.")

    _sessions[session_id] = {"intent": intent, "last_active": time.time()}


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
    1. Load CSV data into memory (if it exists)
    2. Auto-sync from Shopify if no CSV is found (e.g. after a Railway restart)
    3. Build semantic embeddings for all products
    """
    global _products_df, _variants_df

    init_db()   # create analytics SQLite tables if they don't exist
    _load_data()

    # Railway has ephemeral storage — the CSV is gone on every restart.
    # Auto-sync from Shopify so the widget works without manual intervention.
    if _products_df.empty:
        shopify_domain = os.getenv("SHOPIFY_STORE_DOMAIN", "")
        # NOTE: the Shopify Admin API token env var used by shopify_client.py
        # is named SHOPIFY_ADMIN_TOKEN (not SHOPIFY_ACCESS_TOKEN).
        shopify_token  = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
        if shopify_domain and shopify_token:
            print("[startup] No CSV found — auto-syncing from Shopify…")
            try:
                raw          = fetch_all_products()
                _products_df = clean_products(raw)
                _variants_df = clean_variants(raw)
                save_to_csv(_products_df, _variants_df)
                print(
                    f"[startup] Auto-sync complete: "
                    f"{len(_products_df)} products, {len(_variants_df)} variants."
                )
            except Exception as exc:
                print(f"[startup] Auto-sync failed: {exc}")
        else:
            print("[startup] Shopify credentials not configured — skipping auto-sync.")

    if not _products_df.empty:
        print("[startup] Building semantic embeddings…")
        build_product_embeddings(_products_df)
    else:
        print("[startup] No products available. Call GET /sync-products to load data.")

    # Auto-register Shopify webhooks if PUBLIC_URL is configured.
    # Shopify deduplicates by (topic, address), so this is idempotent.
    public_url = os.getenv("PUBLIC_URL", "").rstrip("/")
    if public_url and os.getenv("SHOPIFY_ADMIN_TOKEN"):
        callback = f"{public_url}/webhooks/shopify"
        print(f"[startup] Registering Shopify webhooks → {callback}")
        try:
            register_webhooks(callback)
        except Exception as exc:
            print(f"[startup] Webhook registration failed: {exc}")

    yield   # Server is now running — yield until shutdown


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShopAssist AI API",
    description="Shopify AI Shopping Assistant backend",
    version="2.0.0",
    lifespan=lifespan,
)

# Allow requests from any origin (covers Vercel, local dev, and custom domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    message:    str
    session_id: str | None = None   # optional — enables multi-turn conversation memory


class CartAddRequest(BaseModel):
    """Body for POST /cart/add."""
    variant_id: int    # Shopify numeric variant ID
    quantity:   int = 1


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


@app.get("/autocomplete")
def autocomplete():
    """
    Return a flat list of suggestion terms for the chat input autocomplete.

    Combines product categories, brand names, colors, and common phrase
    combinations (e.g. "black shoes", "Nike hoodies").

    Called once when the frontend loads — no per-keystroke network requests.
    """
    if _variants_df.empty:
        return {"terms": []}

    vendors    = get_all_vendors(_variants_df)[:20]
    categories = get_all_categories(_variants_df)[:20]
    colors     = get_all_colors(_variants_df)[:12]

    terms: set[str] = set()

    # Standalone categories and brands
    for cat in categories:
        terms.add(cat.lower())
    for vendor in vendors:
        terms.add(vendor)

    # color + category combinations: "black shoes", "red dress"
    for color in colors[:8]:
        for cat in categories[:8]:
            terms.add(f"{color.lower()} {cat.lower()}")

    # vendor + category combinations: "Nike shoes", "Adidas hoodie"
    for vendor in vendors[:8]:
        for cat in categories[:8]:
            terms.add(f"{vendor} {cat.lower()}")

    return {"terms": sorted(terms)}


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

    # Look up the previous intent for this session (if any)
    previous_intent = None
    if req.session_id:
        previous_intent = _get_session_intent(req.session_id)
        if previous_intent:
            print(f"[session] Loaded previous intent for {req.session_id[:8]}…: {previous_intent}")
        else:
            print(f"[session] New session: {req.session_id[:8]}…")

    t_start = time.time()
    try:
        result = ask_assistant(
            user_message    = req.message,
            variants_df     = _variants_df,
            products_df     = _products_df,
            top_n           = 5,
            previous_intent = previous_intent,
        )

        # Save the merged intent back to session memory for the next turn
        if req.session_id and result.get("_intent"):
            _save_session_intent(req.session_id, result["_intent"])

        # Log to analytics
        log_query(
            session_id     = req.session_id,
            message        = req.message,
            intent         = result.get("_intent"),
            products_found = len(result.get("products", [])),
            was_answered   = len(result.get("products", [])) > 0,
            fallback_used  = result.get("fallback_used", False),
            response_ms    = int((time.time() - t_start) * 1000),
        )

        # Strip the internal _intent field before sending to the frontend
        result.pop("_intent", None)
        return result

    except Exception as exc:
        print(f"[chat] Unhandled error: {exc}")
        raise HTTPException(status_code=500, detail="Something went wrong. Please try again.")


@app.post("/cart/add")
def cart_add(req: CartAddRequest):
    """
    Proxy — adds a product variant to the Shopify cart.

    Forwards the request to Shopify's AJAX Cart API on the storefront.
    Using a backend proxy avoids CORS issues during development.

    Note: Shopify's AJAX cart is session-based (browser cookie).
    For full session continuity, embed this app inside a Shopify theme
    and call POST /cart/add.js directly from the frontend instead.
    The backend proxy is the correct approach for standalone / headless use.
    """
    store_domain = os.getenv("SHOPIFY_STORE_DOMAIN", "")
    if not store_domain:
        raise HTTPException(
            status_code=500,
            detail="SHOPIFY_STORE_DOMAIN is not configured in the backend .env file.",
        )

    shopify_url = f"https://{store_domain}/cart/add.js"

    try:
        resp = http_requests.post(
            shopify_url,
            json={"id": req.variant_id, "quantity": req.quantity},
            headers={
                "Content-Type": "application/json",
                "Accept":       "application/json",
            },
            timeout=10,
        )
    except http_requests.RequestException as exc:
        print(f"[cart] Network error reaching Shopify: {exc}")
        raise HTTPException(status_code=502, detail="Could not reach the Shopify store.")

    # Shopify returns 200 on success, 422 on invalid variant / out of stock
    if not resp.ok:
        error_body = resp.json() if resp.content else {}
        message    = error_body.get("description") or error_body.get("message") or "Failed to add to cart."
        print(f"[cart] Shopify rejected add-to-cart: {resp.status_code} — {message}")
        raise HTTPException(status_code=resp.status_code, detail=message)

    print(f"[cart] Added variant {req.variant_id} × {req.quantity} to cart.")
    return resp.json()


# ── Widget config (public) ────────────────────────────────────────────────────

@app.get("/widget-config")
def widget_config():
    """Return current widget appearance settings. Called by the frontend on load."""
    return load_widget_config()


# ── Admin: analytics ──────────────────────────────────────────────────────────

@app.get("/admin/analytics")
def admin_analytics():
    """Return aggregated analytics: totals, top categories/brands, unanswered queries."""
    return get_summary()


@app.get("/admin/queries")
def admin_queries(limit: int = 100, offset: int = 0):
    """Return paginated raw query log (most recent first)."""
    return {
        "total":   get_total_count(),
        "queries": get_recent_queries(limit=limit, offset=offset),
    }


# ── Admin: widget config ──────────────────────────────────────────────────────

@app.get("/admin/widget-config")
def admin_get_widget_config():
    return load_widget_config()


class WidgetConfigUpdate(BaseModel):
    primaryColor: Optional[str]  = None
    position:     Optional[str]  = None
    title:        Optional[str]  = None
    subtitle:     Optional[str]  = None
    welcomeMsg:   Optional[str]  = None
    showBranding: Optional[bool] = None


@app.post("/admin/widget-config")
def admin_save_widget_config(body: WidgetConfigUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return save_widget_config(updates)


# ── Shopify webhooks ──────────────────────────────────────────────────────────

class WebhookRequest(BaseModel):
    pass   # body is raw bytes; we validate via HMAC


def _verify_shopify_hmac(body: bytes, hmac_header: str) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET:
        return True   # skip verification if secret not configured (dev mode)
    digest = base64.b64encode(
        hmac.new(SHOPIFY_WEBHOOK_SECRET.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(digest, hmac_header)


from fastapi import Request as FastAPIRequest

@app.post("/webhooks/shopify")
async def shopify_webhook(
    request:               FastAPIRequest,
    background_tasks:      BackgroundTasks,
    x_shopify_hmac_sha256: Optional[str] = Header(None),
    x_shopify_topic:       Optional[str] = Header(None),
):
    """
    Receive Shopify product webhooks and trigger a background sync.

    Responds immediately (Shopify requires < 5 s) and runs the full catalog
    sync in a background thread.  Concurrent events are coalesced — a burst
    of webhooks (e.g. bulk product update) produces at most two syncs.

    The easiest way to register these webhooks is to set PUBLIC_URL in your
    Railway env vars — they are registered automatically on startup.
    You can also call POST /webhooks/register manually.
    """
    body = await request.body()

    if x_shopify_hmac_sha256 and not _verify_shopify_hmac(body, x_shopify_hmac_sha256):
        raise HTTPException(status_code=401, detail="Invalid HMAC — webhook rejected.")

    topic = x_shopify_topic or "unknown"
    print(f"[webhook] Received {topic} — queuing background sync…")
    background_tasks.add_task(_run_sync, topic)

    return {"status": "ok", "topic": topic}


@app.post("/webhooks/register")
def webhooks_register(callback_url: str):
    """
    Register the three product webhook topics with Shopify.

    Pass the full public URL of this server as `callback_url`, e.g.:
      https://your-app.railway.app/webhooks/shopify

    Alternatively, set PUBLIC_URL in your env vars — webhooks are then
    registered automatically on every server startup.
    """
    try:
        registered = register_webhooks(callback_url)
        existing   = list_webhooks()
        return {
            "newly_registered": registered,
            "all_webhooks":     existing,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/webhooks/list")
def webhooks_list():
    """Return all webhooks currently registered on the Shopify store."""
    try:
        return {"webhooks": list_webhooks()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
