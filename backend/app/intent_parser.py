"""
intent_parser.py
----------------
Converts a customer's natural-language shopping query into a structured
JSON object that the search engine can understand.

Uses OpenAI Chat completions with JSON mode to guarantee valid output.

Example:
    Input:  "Show me cheap black sneakers size 9"
    Output: {
        "keyword":   "sneakers",
        "vendor":    null,
        "category":  "shoes",
        "color":     "black",
        "size":      "9",
        "max_price": 100
    }
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI setup ───────────────────────────────────────────────────────────────
client       = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


# ── Synonym tables ─────────────────────────────────────────────────────────────

# Maps common product-type words to the canonical category name stored in CSV
CATEGORY_SYNONYMS = {
    "sneakers":  "shoes",
    "trainers":  "shoes",
    "kicks":     "shoes",
    "pumps":     "shoes",
    "heels":     "shoes",
    "loafers":   "shoes",
    "flats":     "shoes",
    "sandals":   "shoes",
    "sneaker":   "shoes",
    "trainer":   "shoes",
    "backpack":  "bags",
    "backpacks": "bags",
    "bag":       "bags",
    "handbag":   "bags",
    "purse":     "bags",
    "tote":      "bags",
    "satchel":   "bags",
    "hoodie":    "hoodies",
    "hoody":     "hoodies",
    "sweatshirt":"hoodies",
    "tee":       "t-shirts",
    "tshirt":    "t-shirts",
    "jeans":     "pants",
    "trousers":  "pants",
    "joggers":   "pants",
    "leggings":  "pants",
    "top":       "tops",
    "blouse":    "tops",
    "shirt":     "tops",
    "jacket":    "jackets",
    "coat":      "jackets",
    "blazer":    "jackets",
    "dress":     "dresses",
    "gown":      "dresses",
    "skirt":     "skirts",
    "shorts":    "shorts",
    "suit":      "suits",
    "hat":       "accessories",
    "cap":       "accessories",
    "belt":      "accessories",
    "wallet":    "accessories",
    "scarf":     "accessories",
    "gloves":    "accessories",
    "socks":     "socks",
    "swimsuit":  "swimwear",
    "bikini":    "swimwear",
}

# Budget/price words → approximate max_price ceiling in USD
BUDGET_KEYWORDS = {
    "cheap":       100,
    "affordable":  100,
    "budget":      100,
    "inexpensive": 100,
    "low-cost":    80,
    "bargain":     80,
    "economical":  80,
    "value":       100,
    "low cost":    80,
    "on a budget": 100,
}


# ── System prompt ──────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
You are a search-filter extractor for a clothing and lifestyle store.

Given a customer's shopping query, extract the relevant filters and return
a JSON object with EXACTLY these keys (use null for anything not mentioned):

{
  "keyword":   string | null,   // core product keyword(s), e.g. "sneakers"
  "vendor":    string | null,   // brand name, e.g. "Nike", "Adidas", "Converse"
  "category":  string | null,   // product type, e.g. "shoes", "t-shirt", "bags"
  "color":     string | null,   // color name, e.g. "black", "white", "red"
  "size":      string | null,   // size value, e.g. "M", "Large", "9", "XL"
  "max_price": number | null    // maximum budget in USD (number only, no $ sign)
}

Rules:
- Return ONLY valid JSON. No markdown fences, no explanation.
- If a field is not mentioned by the customer, return null for that field.
- Normalize synonyms: sneakers/trainers → shoes, backpack/bag → bags
- Budget words: cheap/affordable/budget → max_price: 100
- Extract brand names carefully (Nike, Adidas, Converse, Puma, Vans, etc.)
- Size can be a number for shoes (e.g. "9") or a letter for clothing (e.g. "M", "XL")
- Do NOT invent products or brands not mentioned in the query.
"""


# ── Main function ──────────────────────────────────────────────────────────────

def extract_intent(user_query: str) -> dict:
    """
    Parse a customer's natural-language query into structured search filters.

    Calls OpenAI with JSON mode to extract:
      keyword, vendor, category, color, size, max_price

    Falls back to safe defaults if anything goes wrong.

    Parameters
    ----------
    user_query : str
        The raw message the customer typed in the chat widget.

    Returns
    -------
    dict with keys: keyword, vendor, category, color, size, max_price
    All values are strings, numbers, or None.
    """

    # All fields default to None — we only set what the customer mentioned
    defaults = {
        "keyword":   None,
        "vendor":    None,
        "category":  None,
        "color":     None,
        "size":      None,
        "max_price": None,
    }

    try:
        # Call OpenAI — JSON mode guarantees we get parseable JSON back
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_query},
            ],
            max_tokens=200,
            temperature=0,  # temperature=0 gives consistent, deterministic output
        )

        raw    = response.choices[0].message.content or "{}"
        intent = json.loads(raw)

        # Merge AI output with defaults so all keys are always present
        intent = {**defaults, **intent}

        # ── Post-processing ────────────────────────────────────────────────────

        # Normalize the category: "sneakers" → "shoes", "backpack" → "bags", etc.
        if intent.get("category"):
            cat_lower = intent["category"].lower().strip()
            intent["category"] = CATEGORY_SYNONYMS.get(cat_lower, cat_lower)

        # Also normalize the keyword if it matches a category synonym
        if intent.get("keyword"):
            kw_lower = intent["keyword"].lower().strip()
            if kw_lower in CATEGORY_SYNONYMS and not intent.get("category"):
                intent["category"] = CATEGORY_SYNONYMS[kw_lower]

        # Detect budget words if AI missed max_price
        if intent.get("max_price") is None:
            query_lower = user_query.lower()
            for word, price in BUDGET_KEYWORDS.items():
                if word in query_lower:
                    intent["max_price"] = price
                    break

        return intent

    except Exception as e:
        # Log but don't crash — caller will fall back to keyword search
        print(f"[intent_parser] Failed to extract intent: {e}")
        return defaults
