/**
 * api.js
 * -------
 * All calls to the FastAPI backend in one place.
 *
 * The base URL is read from the VITE_API_URL environment variable
 * (set in .env).  If not set, it defaults to http://localhost:8000.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Generic fetch wrapper — throws a meaningful error on non-2xx responses.
 */
async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }

  return res.json()
}

/** Check if the backend is running and has data loaded. */
export function checkHealth() {
  return apiFetch('/health')
}

/**
 * Trigger a Shopify product sync.
 * Fetches all products from Shopify, cleans them, and saves CSVs.
 */
export function syncProducts() {
  return apiFetch('/sync-products')
}

/** Return all products (paginated). */
export function getProducts(limit = 50, offset = 0) {
  return apiFetch(`/products?limit=${limit}&offset=${offset}`)
}

/** Return all variants (paginated). */
export function getVariants(limit = 100, offset = 0) {
  return apiFetch(`/variants?limit=${limit}&offset=${offset}`)
}

/**
 * Search products with optional keyword and filters.
 *
 * @param {object} params
 * @param {string}  [params.query]
 * @param {string}  [params.vendor]
 * @param {string}  [params.category]
 * @param {number}  [params.max_price]
 * @param {string}  [params.size]
 * @param {string}  [params.color]
 * @param {boolean} [params.in_stock_only]
 */
export function searchProducts(params) {
  return apiFetch('/search', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

/**
 * Send a chat message to the AI assistant.
 *
 * @param {string} message  — customer's natural-language question
 * @returns {Promise<{answer: string, products: object[], recommendations: object[]}>}
 */
export function sendChat(message) {
  return apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  })
}
