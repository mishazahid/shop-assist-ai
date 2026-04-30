/**
 * ProductCard.jsx
 * ---------------
 * Displays a single product recommendation in a clean Shopify-like card.
 *
 * Props:
 *   product  {object}  — product/variant data from the /chat or /search API
 */

const styles = {
  card: {
    background: '#ffffff',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    overflow: 'hidden',
    width: '200px',
    minWidth: '200px',
    flexShrink: 0,
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    display: 'flex',
    flexDirection: 'column',
    transition: 'box-shadow 0.2s',
  },
  imageWrapper: {
    width: '100%',
    height: '160px',
    background: '#f9fafb',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
    objectFit: 'cover',
  },
  imagePlaceholder: {
    fontSize: '40px',
    userSelect: 'none',
  },
  body: {
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    flex: 1,
  },
  title: {
    fontSize: '13px',
    fontWeight: '600',
    color: '#111827',
    lineHeight: 1.4,
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  vendor: {
    fontSize: '11px',
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  price: {
    fontSize: '15px',
    fontWeight: '700',
    color: '#008060',   // Shopify green
    marginTop: '2px',
  },
  badgeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '4px',
    marginTop: '4px',
  },
  badge: {
    fontSize: '10px',
    padding: '2px 7px',
    borderRadius: '100px',
    background: '#f3f4f6',
    color: '#374151',
    fontWeight: '500',
  },
  stockBadge: {
    fontSize: '10px',
    padding: '2px 7px',
    borderRadius: '100px',
    fontWeight: '500',
  },
  reason: {
    fontSize: '11px',
    color: '#6b7280',
    fontStyle: 'italic',
    marginTop: '6px',
    lineHeight: 1.4,
    borderTop: '1px solid #f3f4f6',
    paddingTop: '6px',
  },
}

export default function ProductCard({ product }) {
  if (!product) return null

  const inStock     = (product.inventory ?? 0) > 0
  const hasImage    = product.image_url && product.image_url.trim() !== ''
  const stockColor  = inStock ? '#dcfce7' : '#fee2e2'
  const stockText   = inStock ? '#166534' : '#991b1b'
  const stockLabel  = inStock ? `✓ ${product.inventory} in stock` : 'Out of stock'

  return (
    <div style={styles.card}>
      {/* Product image */}
      <div style={styles.imageWrapper}>
        {hasImage ? (
          <img
            src={product.image_url}
            alt={product.product_title || product.title || 'Product'}
            style={styles.image}
            onError={(e) => {
              // Hide broken images gracefully
              e.target.style.display = 'none'
              e.target.parentNode.innerHTML = '<span style="font-size:40px">🛍️</span>'
            }}
          />
        ) : (
          <span style={styles.imagePlaceholder}>🛍️</span>
        )}
      </div>

      {/* Product info */}
      <div style={styles.body}>
        {product.vendor && (
          <div style={styles.vendor}>{product.vendor}</div>
        )}

        <div style={styles.title}>
          {product.product_title || product.title || 'Unnamed Product'}
        </div>

        <div style={styles.price}>
          ${Number(product.price || 0).toFixed(2)}
        </div>

        {/* Size / color / stock badges */}
        <div style={styles.badgeRow}>
          {product.size && (
            <span style={styles.badge}>Size {product.size}</span>
          )}
          {product.color && (
            <span style={styles.badge}>{product.color}</span>
          )}
          <span
            style={{
              ...styles.stockBadge,
              background: stockColor,
              color: stockText,
            }}
          >
            {stockLabel}
          </span>
        </div>

        {/* AI reason */}
        {product.reason && (
          <div style={styles.reason}>{product.reason}</div>
        )}
      </div>
    </div>
  )
}
