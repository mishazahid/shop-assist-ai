"""
shopify_client.py
-----------------
Fetches all products from the Shopify Admin REST API.

Key features:
  - Cursor-based pagination via the Link header (no page numbers)
  - Automatic retry on Shopify 429 rate-limit responses
  - All config read from environment variables — no hardcoded secrets
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN", "")
ADMIN_TOKEN  = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
API_VERSION  = os.getenv("SHOPIFY_API_VERSION", "2024-04")
PAGE_LIMIT   = int(os.getenv("SHOPIFY_PAGE_LIMIT", "250"))

BASE_URL = f"https://{STORE_DOMAIN}/admin/api/{API_VERSION}"

# Every request includes this header for authentication
HEADERS = {
    "X-Shopify-Access-Token": ADMIN_TOKEN,
    "Content-Type": "application/json",
}


def _get(endpoint: str, params: dict = None) -> requests.Response:
    """
    Send a single authenticated GET request to the Shopify Admin API.
    Retries once automatically if a 429 rate-limit response is received.
    """
    url = f"{BASE_URL}{endpoint}"
    for attempt in range(2):
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 429:
            # Shopify tells us how long to wait in the Retry-After header
            wait = float(response.headers.get("Retry-After", 2))
            print(f"  Rate limited. Waiting {wait}s …")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    response.raise_for_status()


def fetch_all_products() -> list[dict]:
    """
    Fetch every product from the Shopify store.

    Shopify uses cursor-based pagination.  When there are more pages,
    the response includes a Link header like:
        <https://store.myshopify.com/.../products.json?page_info=abc>; rel="next"

    We follow that URL until there is no "next" link.

    Returns
    -------
    list[dict]
        All raw product objects as returned by the Shopify API.
    """
    if not STORE_DOMAIN or not ADMIN_TOKEN:
        raise EnvironmentError(
            "SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_TOKEN must be set in your .env file."
        )

    all_products: list[dict] = []
    params   = {"limit": PAGE_LIMIT}
    endpoint = "/products.json"
    page     = 1

    while True:
        print(f"  Fetching page {page} …")
        resp     = _get(endpoint, params=params)
        products = resp.json().get("products", [])
        all_products.extend(products)
        print(f"    Got {len(products)} products (running total: {len(all_products)})")

        # Check if Shopify has a next page
        next_url = _parse_next_link(resp.headers.get("Link", ""))
        if not next_url:
            break  # no more pages

        # For subsequent pages we only pass page_info (other params are ignored by Shopify)
        page_info = _extract_page_info(next_url)
        params    = {"limit": PAGE_LIMIT, "page_info": page_info}
        page     += 1

    print(f"\nFinished. Total products fetched: {len(all_products)}")
    return all_products


def _parse_next_link(link_header: str) -> str | None:
    """
    Parse Shopify's Link header and return the URL for rel="next", or None.

    Example header:
        <https://store.myshopify.com/.../products.json?page_info=abc123&limit=250>; rel="next"
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            url_part = part.split(";")[0].strip()
            return url_part.strip("<>")
    return None


def _extract_page_info(url: str) -> str:
    """Extract the page_info query-string value from a full URL."""
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(url).query)
    return qs.get("page_info", [""])[0]
