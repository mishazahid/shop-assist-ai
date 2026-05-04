/**
 * ProductCard.jsx
 * ---------------
 * Displays a single product in a clean, Shopify-style card.
 * Designed to sit inside the 2-column product grid in ChatWidget.
 *
 * Props:
 *   product  {object}  — product/variant data from the /chat or /search API
 */

import { useState } from 'react'
import { addToCart } from '../api'

// Shopify store URL for "View Product" links.
// Set VITE_SHOPIFY_STORE_URL in frontend/.env — empty string works inside a theme.
const STORE_URL = (import.meta.env.VITE_SHOPIFY_STORE_URL || '').replace(/\/$/, '')

export default function ProductCard({ product }) {
  const [cartState, setCartState] = useState('idle') // idle | loading | success | error
  const [errorMsg,  setErrorMsg]  = useState('')

  if (!product) return null

  const inStock    = (product.inventory ?? 0) > 0
  const hasImage   = product.image_url && product.image_url.trim() !== ''
  const productUrl = product.handle ? `${STORE_URL}/products/${product.handle}` : null

  const stockColor = inStock ? '#dcfce7' : '#fee2e2'
  const stockText  = inStock ? '#166534' : '#991b1b'
  const stockLabel = inStock ? `✓ ${product.inventory} in stock` : 'Out of stock'

  // ── Add to Cart ───────────────────────────────────────────────────────────
  const handleAddToCart = async () => {
    if (!inStock || !product.variant_id || cartState === 'loading') return
    setCartState('loading')
    setErrorMsg('')
    try {
      await addToCart(product.variant_id, 1)
      setCartState('success')
      setTimeout(() => setCartState('idle'), 2500)
    } catch (err) {
      setCartState('error')
      setErrorMsg(err.message || 'Could not add to cart.')
      setTimeout(() => { setCartState('idle'); setErrorMsg('') }, 3000)
    }
  }

  const btnLabel = {
    idle:    inStock ? 'Add to Cart' : 'Out of Stock',
    loading: 'Adding…',
    success: '✓ Added!',
    error:   'Try Again',
  }[cartState]

  const isDisabled    = !inStock || cartState === 'loading'
  const btnBackground = !inStock   ? '#e5e7eb'
    : cartState === 'error'        ? '#dc2626'
    : cartState === 'success'      ? '#16a34a'
    :                                '#008060'

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      style={st.card}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.12)'
        e.currentTarget.style.transform = 'translateY(-2px)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.07)'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      {/* Image */}
      <div style={st.imageWrapper}>
        {hasImage ? (
          <img
            src={product.image_url}
            alt={product.product_title || 'Product'}
            style={st.image}
            onError={(e) => {
              e.target.style.display = 'none'
              e.target.parentNode.innerHTML = '<span style="font-size:36px;opacity:0.4">🛍️</span>'
            }}
          />
        ) : (
          <span style={st.imagePlaceholder}>🛍️</span>
        )}
      </div>

      {/* Body */}
      <div style={st.body}>

        {/* Brand */}
        {product.vendor && <div style={st.vendor}>{product.vendor}</div>}

        {/* Title */}
        <div style={st.title}>
          {product.product_title || product.title || 'Unnamed Product'}
        </div>

        {/* Price — visually highlighted */}
        <div style={st.priceRow}>
          <span style={st.price}>${Number(product.price || 0).toFixed(2)}</span>
        </div>

        {/* Badges: size / color / stock */}
        <div style={st.badgeRow}>
          {product.size  && <span style={st.badge}>Size {product.size}</span>}
          {product.color && <span style={st.badge}>{product.color}</span>}
          <span style={{ ...st.stockBadge, background: stockColor, color: stockText }}>
            {stockLabel}
          </span>
        </div>

        {/* AI reason */}
        {product.reason && <div style={st.reason}>{product.reason}</div>}

        {/* Actions */}
        <div style={st.actions}>
          {/* Add to Cart — primary action */}
          <button
            style={{
              ...st.cartBtn,
              background: btnBackground,
              opacity:    cartState === 'loading' ? 0.75 : 1,
              cursor:     isDisabled ? 'not-allowed' : 'pointer',
              color:      !inStock ? '#9ca3af' : '#ffffff',
            }}
            onClick={handleAddToCart}
            disabled={isDisabled}
            title={!inStock ? 'Out of stock' : 'Add to cart'}
          >
            {btnLabel}
          </button>

          {/* View Product — secondary action, only shown when URL is available */}
          {productUrl && (
            <a
              href={productUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={st.viewBtn}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#f0fdf9'
                e.currentTarget.style.color      = '#005c47'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
                e.currentTarget.style.color      = '#008060'
              }}
            >
              View Product →
            </a>
          )}
        </div>

        {/* Cart error message */}
        {cartState === 'error' && errorMsg && (
          <div style={st.errorMsg}>⚠ {errorMsg}</div>
        )}
      </div>
    </div>
  )
}

// ── Styles ─────────────────────────────────────────────────────────────────────
const st = {
  card: {
    background:    '#ffffff',
    border:        '1px solid #e5e7eb',
    borderRadius:  '14px',
    overflow:      'hidden',
    width:         '100%',          // fills the grid cell — no fixed pixel width
    display:       'flex',
    flexDirection: 'column',
    boxShadow:     '0 1px 4px rgba(0,0,0,0.07)',
    transition:    'box-shadow 0.2s ease, transform 0.2s ease',
  },
  imageWrapper: {
    width:          '100%',
    height:         '160px',
    background:     'linear-gradient(135deg, #f9fafb, #f3f4f6)',
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'center',
    overflow:       'hidden',
    flexShrink:     0,
  },
  image: {
    width:     '100%',
    height:    '100%',
    objectFit: 'cover',
  },
  imagePlaceholder: {
    fontSize:  '36px',
    opacity:   0.4,
    userSelect:'none',
  },
  body: {
    padding:       '12px',
    display:       'flex',
    flexDirection: 'column',
    gap:           '5px',
    flex:          1,
  },
  vendor: {
    fontSize:      '10px',
    fontWeight:    '600',
    color:         '#9ca3af',
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  },
  title: {
    fontSize:         '13px',
    fontWeight:       '600',
    color:            '#111827',
    lineHeight:       1.35,
    display:          '-webkit-box',
    WebkitLineClamp:  2,
    WebkitBoxOrient:  'vertical',
    overflow:         'hidden',
  },

  // Price gets its own row with a slight visual lift
  priceRow: {
    display:    'flex',
    alignItems: 'baseline',
    gap:        '4px',
    marginTop:  '2px',
  },
  price: {
    fontSize:      '16px',
    fontWeight:    '800',
    color:         '#008060',
    letterSpacing: '-0.02em',
  },

  badgeRow: {
    display:  'flex',
    flexWrap: 'wrap',
    gap:      '4px',
  },
  badge: {
    fontSize:     '10px',
    padding:      '2px 6px',
    borderRadius: '100px',
    background:   '#f3f4f6',
    color:        '#374151',
    fontWeight:   '500',
  },
  stockBadge: {
    fontSize:     '10px',
    padding:      '2px 6px',
    borderRadius: '100px',
    fontWeight:   '600',
  },

  reason: {
    fontSize:    '11px',
    color:       '#6b7280',
    fontStyle:   'italic',
    lineHeight:  1.45,
    borderTop:   '1px solid #f3f4f6',
    paddingTop:  '6px',
    marginTop:   '2px',
  },

  // Action buttons container
  actions: {
    display:       'flex',
    flexDirection: 'column',
    gap:           '6px',
    marginTop:     '8px',
  },

  // Add to Cart — solid, full-width
  cartBtn: {
    width:        '100%',
    padding:      '8px 0',
    borderRadius: '8px',
    border:       'none',
    fontSize:     '12px',
    fontWeight:   '600',
    letterSpacing:'0.01em',
    transition:   'background 0.15s, opacity 0.15s',
  },

  // View Product — ghost/outlined, full-width
  viewBtn: {
    display:       'block',
    textAlign:     'center',
    padding:       '7px 0',
    borderRadius:  '8px',
    border:        '1.5px solid #008060',
    color:         '#008060',
    background:    'transparent',
    fontSize:      '12px',
    fontWeight:    '600',
    textDecoration:'none',
    transition:    'background 0.15s, color 0.15s',
  },

  errorMsg: {
    fontSize:  '10px',
    color:     '#dc2626',
    textAlign: 'center',
    lineHeight: 1.4,
  },
}
