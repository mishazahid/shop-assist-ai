# ShopAssist AI

AI-powered shopping assistant that connects to a Shopify store and lets
customers find products through a natural-language React chat interface.

```
┌──────────────────────────────────────────┐
│  React Frontend  (Vite, port 5173)       │
│  ChatWidget → ProductCard                │
└─────────────────┬────────────────────────┘
                  │ POST /chat
                  ▼
┌──────────────────────────────────────────┐
│  FastAPI Backend  (Uvicorn, port 8000)   │
│                                          │
│  1. Intent extraction  (OpenAI)          │
│  2. Pandas search  (local CSV)           │
│  3. Recommendation  (OpenAI)             │
└─────────────────┬────────────────────────┘
                  │ GET /admin/api/.../products.json
                  ▼
         Shopify Admin API
```

---

## Project structure

```
ShopAssist AI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             ← FastAPI app + all endpoints
│   │   ├── shopify_client.py   ← Shopify Admin API + pagination
│   │   ├── data_cleaner.py     ← raw JSON → clean CSVs
│   │   ├── search_engine.py    ← Pandas keyword + filter search
│   │   └── ai_assistant.py     ← OpenAI intent extraction + recommendations
│   ├── data/                   ← auto-created; stores products.csv & variants.csv
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx             ← page layout + sync button
│   │   ├── api.js              ← all backend API calls
│   │   ├── index.css
│   │   └── components/
│   │       ├── ChatWidget.jsx  ← chat UI + message history
│   │       └── ProductCard.jsx ← product image/title/price/badges
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── .env.example
│
└── README.md
```

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| npm | 9+ | bundled with Node.js |
| Shopify store | any | Admin API token required |
| OpenAI account | — | API key required |

---

## Setup — Backend

### 1. Create a virtual environment

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

Open `backend/.env` and fill in:

```env
SHOPIFY_STORE_DOMAIN=your-store.myshopify.com
SHOPIFY_ADMIN_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o
```

### 4. Start the backend

```bash
uvicorn app.main:app --reload
```

The API is now running at **http://localhost:8000**.

### 5. Sync Shopify products

Open your browser and visit:

```
http://localhost:8000/sync-products
```

This fetches all products from Shopify, cleans them, and saves
`data/products.csv` and `data/variants.csv`.  This takes a few seconds
and only needs to be done once (or whenever products change).

---

## Setup — Frontend

### 1. Install Node dependencies

```bash
cd frontend
npm install
```

### 2. Configure environment variables

```bash
copy .env.example .env      # Windows
# cp .env.example .env      # macOS/Linux
```

The default `.env` is:

```env
VITE_API_URL=http://localhost:8000
```

### 3. Start the dev server

```bash
npm run dev
```

The app is now running at **http://localhost:5173**.

---

## API Reference

### `GET /health`
Health check. Returns product and variant counts.

```json
{ "status": "ok", "products": 30, "variants": 147 }
```

### `GET /sync-products`
Fetches all products from Shopify, cleans the data, and saves CSVs.
Reloads the in-memory DataFrames automatically.

### `GET /products?limit=100&offset=0`
Returns all products from the local CSV.

### `GET /variants?limit=200&offset=0`
Returns all variants from the local CSV.

### `POST /search`
Search products with optional filters.

```json
{
  "query":         "running shoes",
  "vendor":        "Nike",
  "category":      "shoes",
  "max_price":     150.0,
  "size":          "10",
  "color":         "black",
  "in_stock_only": true,
  "top_n":         10
}
```

### `POST /chat`
AI assistant — natural-language chat.

**Request:**
```json
{ "message": "Show me black shoes under $150" }
```

**Response:**
```json
{
  "answer": "I found 3 great options for you!",
  "products": [
    {
      "product_id": "123",
      "product_title": "Air Max 90",
      "vendor": "Nike",
      "price": 120.00,
      "color": "Black",
      "size": "10",
      "inventory": 5,
      "image_url": "https://...",
      "reason": "Classic black colorway, exactly under your $150 budget."
    }
  ],
  "recommendations": [
    { "product_id": "123", "reason": "..." }
  ]
}
```

---

## How the AI pipeline works

```
User: "Show me black shoes under $150"
         │
         ▼
  OpenAI (intent extraction)
    → { keyword: "shoes", color: "black", max_price: 150 }
         │
         ▼
  Pandas search on variants.csv
    → top 5 matching in-stock variants
         │
         ▼
  OpenAI (recommendation writing)
    → { answer: "...", recommendations: [{product_id, reason}] }
         │
         ▼
  Enrich with full product data
         │
         ▼
  Return to React frontend
```

The AI **never invents products** — it can only recommend items returned
by the Pandas search engine.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `SHOPIFY_ADMIN_TOKEN` error | Confirm the token starts with `shpat_` and has the `read_products` scope |
| `503 Product data not loaded` | Visit `http://localhost:8000/sync-products` to create the CSVs |
| CORS error in the browser | Make sure the backend is running on port 8000 and the frontend on 5173 |
| `openai.AuthenticationError` | Check `OPENAI_API_KEY` in `backend/.env` |
| Products not updating | Call `GET /sync-products` again or run with `--reload` |
| Empty search results | Try a broader query; remove size/color filters |

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `SHOPIFY_STORE_DOMAIN` | — | Store subdomain (required) |
| `SHOPIFY_ADMIN_TOKEN` | — | Admin API token (required) |
| `SHOPIFY_API_VERSION` | `2024-04` | Shopify API version |
| `SHOPIFY_PAGE_LIMIT` | `250` | Products per page (max 250) |
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `DATA_DIR` | `data` | Folder for CSVs |

### Frontend (`frontend/.env`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend URL |
