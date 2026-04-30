/**
 * App.jsx
 * -------
 * Root component. Renders the page layout with a header and the
 * ChatWidget centred in the page.
 */

import { useState, useEffect } from 'react'
import ChatWidget from './components/ChatWidget'
import { checkHealth, syncProducts } from './api'

export default function App() {
  const [status, setStatus]     = useState(null)   // {products, variants} counts
  const [syncing, setSyncing]   = useState(false)
  const [syncMsg, setSyncMsg]   = useState('')

  // On load, check if the backend has product data
  useEffect(() => {
    checkHealth()
      .then((data) => setStatus(data))
      .catch(() => setStatus(null))
  }, [])

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg('Fetching products from Shopify…')
    try {
      const result = await syncProducts()
      setSyncMsg(
        `✅ Synced ${result.products} products and ${result.variants} variants.`
      )
      setStatus(result)
    } catch (err) {
      setSyncMsg(`❌ Sync failed: ${err.message}`)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div style={styles.page}>
      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <header style={styles.topBar}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>🛍️</span>
          <span style={styles.logoText}>ShopAssist AI</span>
        </div>

        <div style={styles.statusArea}>
          {status && (
            <span style={styles.statsLabel}>
              {status.products} products · {status.variants} variants
            </span>
          )}
          <button
            style={{ ...styles.syncBtn, opacity: syncing ? 0.6 : 1 }}
            onClick={handleSync}
            disabled={syncing}
          >
            {syncing ? '⟳ Syncing…' : '⟳ Sync Products'}
          </button>
        </div>
      </header>

      {/* Sync status message */}
      {syncMsg && (
        <div style={styles.syncBanner}>{syncMsg}</div>
      )}

      {/* ── Main layout ─────────────────────────────────────────────────── */}
      <main style={styles.main}>
        {/* Left panel — branding / info */}
        <div style={styles.leftPanel}>
          <h1 style={styles.headline}>
            Your AI<br />Shopping<br />Assistant
          </h1>
          <p style={styles.subtext}>
            Ask anything about our product catalog in plain English.
            The assistant searches live inventory and explains why each
            recommendation is a great fit.
          </p>

          <div style={styles.featureList}>
            {[
              ['🔍', 'Smart search', 'Understands natural language'],
              ['🎨', 'Filter by color or size', 'Find exactly what you need'],
              ['💰', 'Budget-aware', 'Set a max price and we handle the rest'],
              ['✅', 'Live inventory', 'Only recommends in-stock items'],
            ].map(([icon, title, desc]) => (
              <div key={title} style={styles.feature}>
                <span style={styles.featureIcon}>{icon}</span>
                <div>
                  <div style={styles.featureTitle}>{title}</div>
                  <div style={styles.featureDesc}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel — chat widget */}
        <div style={styles.chatPanel}>
          <ChatWidget />
        </div>
      </main>
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
  page: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(135deg, #f0fdf9 0%, #f6f6f7 60%, #fff 100%)',
  },

  // Top navigation bar
  topBar: {
    height: '60px',
    background: '#ffffff',
    borderBottom: '1px solid #e5e7eb',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 28px',
    flexShrink: 0,
    position: 'sticky',
    top: 0,
    zIndex: 10,
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  logoIcon: { fontSize: '22px' },
  logoText: {
    fontWeight: '700',
    fontSize: '17px',
    color: '#111827',
    letterSpacing: '-0.01em',
  },
  statusArea: {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
  },
  statsLabel: {
    fontSize: '12px',
    color: '#6b7280',
  },
  syncBtn: {
    padding: '7px 16px',
    background: '#f3f4f6',
    border: '1px solid #e5e7eb',
    borderRadius: '8px',
    fontSize: '13px',
    fontWeight: '500',
    color: '#374151',
    cursor: 'pointer',
    transition: 'background 0.15s',
  },

  // Sync banner
  syncBanner: {
    background: '#f0fdf9',
    borderBottom: '1px solid #bbf7d0',
    padding: '8px 28px',
    fontSize: '13px',
    color: '#166534',
    flexShrink: 0,
  },

  // Two-column layout
  main: {
    flex: 1,
    display: 'grid',
    gridTemplateColumns: '1fr 480px',
    gap: '40px',
    padding: '40px 28px',
    maxWidth: '1100px',
    margin: '0 auto',
    width: '100%',
    alignItems: 'start',

    // Stack on small screens
    '@media (max-width: 768px)': {
      gridTemplateColumns: '1fr',
    },
  },

  // Left info panel
  leftPanel: {
    padding: '20px 0',
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  },
  headline: {
    fontSize: '44px',
    fontWeight: '800',
    lineHeight: 1.15,
    color: '#111827',
    letterSpacing: '-0.02em',
  },
  subtext: {
    fontSize: '15px',
    color: '#4b5563',
    lineHeight: 1.65,
    maxWidth: '380px',
  },
  featureList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    marginTop: '8px',
  },
  feature: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
  },
  featureIcon: {
    fontSize: '20px',
    flexShrink: 0,
    marginTop: '1px',
  },
  featureTitle: {
    fontSize: '14px',
    fontWeight: '600',
    color: '#111827',
  },
  featureDesc: {
    fontSize: '13px',
    color: '#6b7280',
    marginTop: '1px',
  },

  // Right chat panel — fixed height so it fills the viewport nicely
  chatPanel: {
    height: 'calc(100vh - 140px)',
    minHeight: '500px',
    position: 'sticky',
    top: '80px',
  },
}
