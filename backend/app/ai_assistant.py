"""
ai_assistant.py
---------------
Orchestrates the full AI pipeline for the /chat endpoint.

Pipeline (in order):
  1. Intent extraction  — intent_parser.py converts free-text → JSON filters
  2. Semantic search    — embedding_service.py ranks products by meaning
  3. Hard filters       — search_engine.py applies brand / size / price / color
  4. AI reasoning       — OpenAI writes a friendly natural-language response
  5. Enrichment         — attach full product data to each recommendation

Fallback strategy:
  - If semantic search fails (no embeddings or API error) → keyword search
  - If results are empty after semantic + filters → retry without semantic ranking
  - If AI response generation fails → return search results with a generic message
  - If intent extraction fails → treat the raw message as a keyword

The assistant NEVER invents products.  It only recommends items that
came back from the search engine, so hallucination is impossible.
"""

import os
import json
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from app.intent_parser     import extract_intent
from app.embedding_service import semantic_search, embeddings_ready
from app.search_engine     import search_products

load_dotenv()

# ── OpenAI setup ───────────────────────────────────────────────────────────────
client       = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# ── Step 4: AI reasoning response ─────────────────────────────────────────────

_RECOMMENDATION_SYSTEM = """\
You are ShopAssist AI, a friendly and knowledgeable shopping assistant for a
clothing and lifestyle store.

You will receive:
  - The customer's original shopping question
  - A list of products currently available in the store

Your job is to write a helpful, friendly response in JSON format with EXACTLY
these two keys:

{
  "answer": string,             // 1-3 sentences, friendly and specific
  "recommendations": [          // one entry per product (up to 4)
    {
      "product_id": string,
      "reason":     string      // one sentence explaining why this product fits
    }
  ]
}

Rules (important — follow these strictly):
  - ONLY recommend products from the provided list. Never invent products.
  - Be specific: mention price, color, size, or brand when relevant.
  - If the list is empty, set recommendations to [] and in the answer field
    politely explain that nothing matched, then suggest the customer try
    changing the color, size, price range, or brand.
  - Keep it conversational and upbeat — like a helpful store assistant.
  - Return ONLY valid JSON. No markdown code fences, no extra text.
"""


def _format_products_for_prompt(results_df: pd.DataFrame) -> str:
    """
    Serialize the top search results into a compact text block so the
    AI can read and reason about them.
    """
    if results_df.empty:
        return "No matching products found in the catalog."

    lines = []
    for _, row in results_df.head(5).iterrows():
        price    = f"${float(row.get('price', 0)):.2f}"
        attrs    = []
        if row.get("size"):  attrs.append(f"size {row['size']}")
        if row.get("color"): attrs.append(f"color {row['color']}")
        attr_str = ", ".join(attrs)

        lines.append(
            f"  product_id={row['product_id']} | "
            f"{row['product_title']} by {row['vendor']} | "
            f"{price} | stock: {row.get('inventory', 0)}"
            + (f" | {attr_str}" if attr_str else "")
        )

    return "\n".join(lines)


def generate_recommendation(user_query: str, results_df: pd.DataFrame) -> dict:
    """
    Call OpenAI to write a structured, reasoning-based recommendation.

    Parameters
    ----------
    user_query  : the customer's original message
    results_df  : DataFrame of products found by the search engine

    Returns
    -------
    dict with keys:
      answer          : str  — friendly response text
      recommendations : list — [{product_id, reason}, ...]
    """
    products_text = _format_products_for_prompt(results_df)

    # Build the user message: query + what the catalog returned
    user_content = (
        f"Customer question: {user_query}\n\n"
        f"Available matching products:\n{products_text}"
    )

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},   # guarantees valid JSON
        messages=[
            {"role": "system", "content": _RECOMMENDATION_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=600,
        temperature=0.4,   # slight creativity for natural-sounding responses
    )

    raw = response.choices[0].message.content or "{}"
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # If JSON parsing fails, wrap the raw text as a plain answer
        result = {"answer": raw, "recommendations": []}

    # Make sure both keys always exist
    result.setdefault("answer", "")
    result.setdefault("recommendations", [])
    return result


# ── High-level pipeline ────────────────────────────────────────────────────────

def ask_assistant(
    user_message: str,
    variants_df:  pd.DataFrame,
    products_df:  pd.DataFrame,
    top_n:        int = 5,
) -> dict:
    """
    Full AI pipeline: understand → search → reason → respond.

    Parameters
    ----------
    user_message : the customer's raw chat message
    variants_df  : variant-level DataFrame (size / color / inventory)
    products_df  : product-level DataFrame (title / description / tags)
    top_n        : max products to include in the final response

    Returns
    -------
    dict with keys:
      answer          : str   — AI-generated response text (used by React frontend)
      message         : str   — same as answer (alias for new API spec)
      products        : list  — full product objects for the frontend cards
      recommendations : list  — [{product_id, reason}] from the AI
    """

    # ── Step 1: Extract structured search intent ────────────────────────────
    try:
        intent = extract_intent(user_message)
    except Exception as e:
        # If intent extraction fails completely, treat the whole message as keyword
        print(f"[assistant] Intent extraction failed ({e}), using raw query as keyword.")
        intent = {
            "keyword":   user_message,
            "vendor":    None,
            "category":  None,
            "color":     None,
            "size":      None,
            "max_price": None,
        }

    print(f"[assistant] Intent: {intent}")

    # ── Step 2: Semantic search — get candidate product IDs ─────────────────
    semantic_ids = []
    if embeddings_ready():
        try:
            # Get the top-30 most semantically similar product IDs for this query
            semantic_ids = semantic_search(user_message, top_k=30)
            print(f"[assistant] Semantic search returned {len(semantic_ids)} candidates.")
        except Exception as e:
            print(f"[assistant] Semantic search failed ({e}), falling back to keyword.")

    # ── Step 3: Apply hard filters on the semantic candidates ────────────────
    results_df = search_products(
        variants_df          = variants_df,
        products_df          = products_df,
        keyword              = intent.get("keyword"),
        vendor               = intent.get("vendor"),
        category             = intent.get("category"),
        max_price            = intent.get("max_price"),
        size                 = intent.get("size"),
        color                = intent.get("color"),
        in_stock_only        = True,
        top_n                = top_n,
        semantic_product_ids = semantic_ids if semantic_ids else None,
    )

    # ── Step 3b: Fallback — if semantic + filters returned nothing ───────────
    # Try again without limiting to semantic candidates.
    # This handles cases where the semantic match was too strict.
    if results_df.empty and semantic_ids:
        print("[assistant] No results with semantic ranking — retrying with keyword search.")
        results_df = search_products(
            variants_df          = variants_df,
            products_df          = products_df,
            keyword              = intent.get("keyword"),
            vendor               = intent.get("vendor"),
            category             = intent.get("category"),
            max_price            = intent.get("max_price"),
            size                 = intent.get("size"),
            color                = intent.get("color"),
            in_stock_only        = True,
            top_n                = top_n,
            semantic_product_ids = None,   # keyword-only fallback
        )

    print(f"[assistant] Search returned {len(results_df)} products.")

    # ── Step 4: Generate AI reasoning response ──────────────────────────────
    try:
        ai_response = generate_recommendation(user_message, results_df)
    except Exception as e:
        # If OpenAI call fails, return the raw search results with a generic message
        print(f"[assistant] Recommendation generation failed ({e}), using fallback response.")
        ai_response = {
            "answer": (
                "Here are some products that match your search."
                if not results_df.empty
                else "I couldn't find anything matching that description. "
                     "Try changing the color, size, or price range."
            ),
            "recommendations": [
                {
                    "product_id": str(row["product_id"]),
                    "reason":     "Matches your search criteria.",
                }
                for _, row in results_df.head(top_n).iterrows()
            ] if not results_df.empty else [],
        }

    # ── Step 5: Enrich recommendations with full product data ────────────────
    # Build a lookup map so we can attach image, price, size, etc. to each
    # recommendation the AI chose — the frontend needs this for product cards.
    product_map: dict[str, dict] = {}
    if not results_df.empty:
        for _, row in results_df.iterrows():
            product_map[str(row["product_id"])] = row.to_dict()

    enriched_products = []
    for rec in ai_response.get("recommendations", []):
        pid = str(rec.get("product_id", ""))
        if pid in product_map:
            # Merge the AI's reason into the product data object
            product_data           = product_map[pid].copy()
            product_data["reason"] = rec.get("reason", "")
            enriched_products.append(product_data)

    answer = ai_response.get("answer", "")

    return {
        "answer":          answer,              # key used by the existing React frontend
        "message":         answer,              # alias to satisfy new API spec
        "products":        enriched_products,   # full product objects for product cards
        "recommendations": ai_response.get("recommendations", []),
    }
