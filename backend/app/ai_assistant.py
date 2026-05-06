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

from app.intent_parser     import extract_intent, merge_intents
from app.embedding_service import semantic_search, embeddings_ready
from app.search_engine     import (
    search_with_fallback, is_vague_query, recommend_products,
    is_compare_query, is_size_guide_query, is_related_query, is_budget_query,
)

load_dotenv()

# ── OpenAI setup ───────────────────────────────────────────────────────────────
client       = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# ── Step 4: AI reasoning response ─────────────────────────────────────────────

_RECOMMENDATION_SYSTEM = """\
You are ShopAssist AI, a helpful shopping assistant for a clothing and lifestyle store.

You will receive:
  1. The customer's original question
  2. What they were specifically looking for (extracted filters)
  3. A structured list of matching products with their real attributes

Respond in JSON with EXACTLY these two keys:

{
  "answer": string,
  "recommendations": [
    {
      "product_id": string,
      "reason":     string
    }
  ]
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES FOR "reason" (most important)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Write exactly 1 sentence per product — max 20 words.
• ONLY use facts from the product data. Never invent color, size, price, or brand.
• Reference what the customer asked for (color, budget, size, brand).
• Use this format:
    "This matches because it's [fact], [fact], and [fact]."
• Examples:
    "This matches because it's black, priced at $120 (within your $150 budget), and available in size 9."
    "Great pick — it's by Adidas as requested, priced at $75, and comes in white."
    "Fits your budget at $89 and is available in your size (M)."
• If a filter was relaxed (fallback), honestly say what DOES match:
    "We don't have this in size 9, but this black Nike shoe is available at $110."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES FOR "answer"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 1–2 sentences, friendly and conversational.
• Mention how many products were found.
• Do NOT repeat the per-product reasons — just give a brief summary.
• If the product list is empty, set recommendations to [] and suggest the
  customer try adjusting color, size, price, or brand.

NEVER:
  • Recommend a product not in the provided list
  • Mention attributes (color, size, price, brand) not shown in the product data
  • Use vague filler like "great option" or "perfect choice" without a real fact
  • Use markdown inside JSON string values

Return ONLY valid JSON. No code fences, no extra text outside the JSON.
"""


def _format_products_for_prompt(results_df: pd.DataFrame) -> str:
    """
    Serialize the top search results into clearly labeled blocks.

    Using a labeled format (name:, brand:, price:, etc.) helps the AI
    reference exact attribute values rather than paraphrasing.
    """
    if results_df.empty:
        return "No matching products found in the catalog."

    blocks = []
    for i, (_, row) in enumerate(results_df.head(5).iterrows(), start=1):
        price     = float(row.get("price", 0))
        inventory = int(row.get("inventory", 0) or 0)
        color     = row.get("color") or ""
        size      = row.get("size")  or ""

        lines = [f"Product {i}:"]
        lines.append(f"  product_id : {row['product_id']}")
        lines.append(f"  name       : {row.get('product_title', 'Unknown')}")
        lines.append(f"  brand      : {row.get('vendor', 'Unknown')}")
        lines.append(f"  category   : {row.get('category', '') or 'N/A'}")
        lines.append(f"  price      : ${price:.2f}")
        if color: lines.append(f"  color      : {color}")
        if size:  lines.append(f"  size       : {size}")
        lines.append(f"  stock      : {'In stock' if inventory > 0 else 'Out of stock'} ({inventory} units)")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _build_fallback_reason(row: pd.Series, intent: dict) -> str:
    """
    Generate a data-driven reason string from actual product attributes
    without calling OpenAI — used when the AI API call fails.

    Compares what the customer asked for (intent) with what the product has.
    """
    parts = []

    # Color match
    color     = row.get("color") or ""
    wanted_c  = (intent.get("color") or "").lower()
    if color:
        if wanted_c and wanted_c in color.lower():
            parts.append(f"it's {color} as you requested")
        else:
            parts.append(f"available in {color}")

    # Price match
    price     = float(row.get("price", 0))
    max_price = intent.get("max_price")
    if max_price and price <= max_price:
        parts.append(f"priced at ${price:.2f} (within your ${max_price:.0f} budget)")
    else:
        parts.append(f"priced at ${price:.2f}")

    # Size match
    size     = row.get("size") or ""
    wanted_s = (intent.get("size") or "").lower()
    if size and wanted_s and wanted_s in size.lower():
        parts.append(f"available in size {size}")
    elif size:
        parts.append(f"comes in size {size}")

    # Brand match
    vendor    = row.get("vendor") or ""
    wanted_v  = (intent.get("vendor") or "").lower()
    if vendor and wanted_v and wanted_v in vendor.lower():
        parts.append(f"by {vendor} as requested")

    if not parts:
        return "Matches your search criteria."

    if len(parts) == 1:
        return f"This matches because {parts[0]}."
    return "This matches because " + ", ".join(parts[:-1]) + f", and {parts[-1]}."


def generate_recommendation(
    user_query:        str,
    results_df:        pd.DataFrame,
    fallback_note:     str        = "",
    intent:            dict | None = None,
    is_recommendation: bool        = False,
    is_compare:        bool        = False,
    is_size_guide:     bool        = False,
    is_related:        bool        = False,
    is_budget:         bool        = False,
) -> dict:
    """
    Call OpenAI to write a structured, reasoning-based recommendation.

    Parameters
    ----------
    user_query        : the customer's original message
    results_df        : DataFrame of products found by the search engine
    fallback_note     : describes which filters were relaxed (empty = exact match)
    intent            : structured filters extracted from the query — passed so the
                        AI knows exactly what the customer was looking for and can
                        write targeted, factual reasons for each product
    is_recommendation : True when the query was vague (e.g. "recommend something").
                        Tells the AI to frame results as popular/curated picks
                        rather than filter-matched results.

    Returns
    -------
    dict with keys:
      answer          : str  — friendly response text
      recommendations : list — [{product_id, reason}, ...]
    """
    products_text = _format_products_for_prompt(results_df)

    # Tell the AI what the customer was specifically looking for.
    # This lets it write reasons like "matches your black color preference"
    # or "falls within your $150 budget" using the customer's own words.
    intent_lines = []
    if intent:
        if intent.get("keyword"):   intent_lines.append(f"  keyword  : {intent['keyword']}")
        if intent.get("vendor"):    intent_lines.append(f"  brand    : {intent['vendor']}")
        if intent.get("category"):  intent_lines.append(f"  category : {intent['category']}")
        if intent.get("color"):     intent_lines.append(f"  color    : {intent['color']}")
        if intent.get("size"):      intent_lines.append(f"  size     : {intent['size']}")
        if intent.get("max_price"): intent_lines.append(f"  budget   : under ${intent['max_price']:.0f}")

    intent_block = (
        "Customer was looking for:\n" + "\n".join(intent_lines)
        if intent_lines else ""
    )

    # Build the full user message for the AI
    user_content = f"Customer question: {user_query}\n\n"
    if intent_block:
        user_content += f"{intent_block}\n\n"
    user_content += f"Matching products:\n{products_text}"

    # ── Mode-specific framing ─────────────────────────────────────────────────
    if is_compare:
        user_content += (
            "\n\nNote: The customer wants to COMPARE products. "
            "Structure your answer as a clear comparison — highlight key differences "
            "in price, color/style, brand, and stock. "
            "End with a concise recommendation: 'If you want X, go with [Product A]. "
            "If you prefer Y, choose [Product B].'"
        )
    elif is_size_guide:
        sizes = sorted(results_df["size"].dropna().unique().tolist()) if not results_df.empty else []
        sizes_str = ", ".join(str(s) for s in sizes) if sizes else "check the product page"
        user_content += (
            f"\n\nNote: The customer needs SIZE GUIDANCE. "
            f"Available sizes: {sizes_str}. "
            "Provide practical advice: mention the available sizes, suggest going up a size "
            "if between sizes, and note that fit can vary by brand. "
            "Be specific and helpful — don't just say 'check the size chart'."
        )
    elif is_related:
        user_content += (
            "\n\nNote: The customer wants SIMILAR or ALTERNATIVE products. "
            "Present these as great alternatives. For each, briefly say what makes it "
            "similar to what they described. "
            "Start with: 'Here are some similar options you might love!'"
        )
    elif is_budget:
        budget = intent.get("max_price", 0) if intent else 0
        fitting = results_df[results_df["price"] <= budget] if not results_df.empty and budget else results_df
        user_content += (
            f"\n\nNote: The customer has a BUDGET of ${budget:.0f}. "
            f"{len(fitting)} of the products shown fit within their budget. "
            "For each product, clearly state the price and confirm it's within budget. "
            "End your answer with how many options fit their budget."
        )
    elif is_recommendation:
        user_content += (
            "\n\nNote: The customer asked for general recommendations, not a "
            "specific filtered search. Present these as popular or curated picks. "
            "Start your answer with a friendly intro such as: "
            "'Here are some popular products you might love!' or "
            "'Here are my top picks for you today!'"
        )

    # ── Fallback note (can stack with mode framing) ───────────────────────────
    if fallback_note == "exact match":
        user_content += (
            "\n\nNote: No exact match was found. These are the closest alternatives. "
            "Start your answer with: 'We couldn't find an exact match, "
            "but here are some similar options you might like.'"
        )
    elif fallback_note:
        user_content += (
            f"\n\nNote: No exact match was found for the {fallback_note} filter. "
            f"It was relaxed to find these alternatives. "
            f"Start your answer by briefly acknowledging this."
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
    user_message:    str,
    variants_df:     pd.DataFrame,
    products_df:     pd.DataFrame,
    top_n:           int          = 5,
    previous_intent: dict | None  = None,
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
        print(f"[assistant] Intent extraction failed ({e}), using raw query as keyword.")
        intent = {
            "keyword":   user_message,
            "vendor":    None,
            "category":  None,
            "color":     None,
            "size":      None,
            "max_price": None,
        }

    # ── Step 1b: Merge with previous turn's intent ────────────────────────────
    # Only fields mentioned in the new query override the previous values.
    # Fields not mentioned (None in new intent) are carried over from memory.
    # Example: previous={color:"black", category:"shoes"}, new={max_price:100}
    #          merged  ={color:"black", category:"shoes",  max_price:100}
    if previous_intent:
        intent = merge_intents(previous_intent, intent)
        print(f"[assistant] Merged intent (previous + new): {intent}")
    else:
        print(f"[assistant] Intent: {intent}")

    # ── Step 1c: Detect recommendation / discovery mode ──────────────────────
    # Triggered when the query is vague (e.g. "recommend something stylish")
    # AND no specific product attributes were extracted from it.
    # When active, strict filters are skipped entirely — results are ranked by
    # semantic similarity and inventory instead of filter matching.
    use_recommendation_mode = is_vague_query(user_message) and not any([
        intent.get("vendor"),
        intent.get("category"),
        intent.get("color"),
        intent.get("size"),
        intent.get("max_price"),
    ])
    if use_recommendation_mode:
        print("[assistant] Recommendation mode — skipping strict filters, ranking by popularity/semantics.")

    # ── Step 1d: Detect special query modes ──────────────────────────────────
    use_compare_mode    = is_compare_query(user_message)
    use_size_guide_mode = is_size_guide_query(user_message)
    use_related_mode    = is_related_query(user_message)
    use_budget_mode     = is_budget_query(user_message) and bool(intent.get("max_price"))
    if use_compare_mode:    print("[assistant] Compare mode — customer wants product comparison.")
    if use_size_guide_mode: print("[assistant] Size guide mode — customer needs sizing help.")
    if use_related_mode:    print("[assistant] Related mode — customer wants similar products.")
    if use_budget_mode:     print("[assistant] Budget mode — customer stated explicit budget.")

    # ── Step 2: Semantic search — get candidate product IDs ─────────────────
    semantic_ids = []
    if embeddings_ready():
        try:
            # Get the top-30 most semantically similar product IDs for this query
            semantic_ids = semantic_search(user_message, top_k=30)
            print(f"[assistant] Semantic search returned {len(semantic_ids)} candidates.")
        except Exception as e:
            print(f"[assistant] Semantic search failed ({e}), falling back to keyword.")

    # ── Step 3: Search ────────────────────────────────────────────────────────
    fallback_note = ""
    if use_recommendation_mode:
        # Skip all hard filters — rank by semantic similarity + inventory
        results_df = recommend_products(
            variants_df          = variants_df,
            products_df          = products_df,
            semantic_product_ids = semantic_ids if semantic_ids else None,
            top_n                = top_n,
        )
        print(f"[assistant] Recommendation search returned {len(results_df)} products.")
    else:
        # Standard search with progressive filter relaxation
        # Tries: all filters → no size → no color → no price → pure semantic/keyword
        results_df, fallback_note = search_with_fallback(
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
        if fallback_note:
            print(f"[assistant] Fallback used — relaxed: {fallback_note}")

    print(f"[assistant] Search returned {len(results_df)} products.")

    # ── Step 4: Generate AI reasoning response ──────────────────────────────
    # When there are truly no results, clear the fallback note so the AI uses
    # the system prompt's "empty list" rule instead of "here are similar options".
    if results_df.empty:
        fallback_note = ""

    try:
        # Pass intent so the AI can write targeted, factual reasons for each product
        ai_response = generate_recommendation(
            user_query         = user_message,
            results_df         = results_df,
            fallback_note      = fallback_note,
            intent             = intent,
            is_recommendation  = use_recommendation_mode,
            is_compare         = use_compare_mode,
            is_size_guide      = use_size_guide_mode,
            is_related         = use_related_mode,
            is_budget          = use_budget_mode,
        )
    except Exception as e:
        # If the OpenAI call fails, generate data-driven reasons without AI
        print(f"[assistant] Recommendation generation failed ({e}), using fallback response.")
        ai_response = {
            "answer": (
                "Here are some products that match your search."
                if not results_df.empty
                else "I couldn't find anything matching that description. "
                     "Try adjusting the color, size, price, or brand."
            ),
            "recommendations": [
                {
                    "product_id": str(row["product_id"]),
                    # Use actual product attributes to build the reason — no AI needed
                    "reason": _build_fallback_reason(row, intent),
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
        "fallback_used":   fallback_note != "", # True if filters were relaxed
        "_intent":         intent,              # final merged intent — saved to session by main.py
    }
