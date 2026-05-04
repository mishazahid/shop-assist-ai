/**
 * FloatingWidget.jsx
 * ------------------
 * Floating chat bubble that sits bottom-right on any Shopify storefront.
 * Clicking the bubble opens/closes the ChatWidget panel.
 *
 * All styles are inline — no global CSS, no conflicts with Shopify themes.
 * z-index is set to the maximum safe value so it always floats on top.
 */

import { useState, useEffect } from 'react'
import ChatWidget from './ChatWidget'

export default function FloatingWidget() {
  const [open,     setOpen]     = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  // Detect mobile so the panel goes near-fullscreen on small screens
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 500)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Close panel when Escape is pressed
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const panelStyle = {
    position:      'absolute',
    bottom:        '70px',
    right:         isMobile ? '-16px' : '0',
    width:         isMobile ? '100vw'  : '400px',
    height:        isMobile ? 'calc(100vh - 88px)' : '600px',
    borderRadius:  isMobile ? '16px 16px 0 0' : '16px',
    overflow:      'hidden',
    boxShadow:     '0 20px 60px rgba(0,0,0,0.18)',
    display:       'flex',
    flexDirection: 'column',
    background:    '#ffffff',
    // Animate open
    animation:     'shopassist-slide-up 0.22s ease',
  }

  return (
    <>
      {/* Keyframe for panel slide-up — injected once */}
      <style>{`
        @keyframes shopassist-slide-up {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{
        position:   'fixed',
        bottom:     '24px',
        right:      '24px',
        zIndex:     2147483647,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}>
        {/* ── Chat panel ────────────────────────────────────────────────── */}
        {open && (
          <div style={panelStyle}>
            <ChatWidget />
          </div>
        )}

        {/* ── Floating bubble ───────────────────────────────────────────── */}
        <button
          onClick={() => setOpen(o => !o)}
          title={open ? 'Close ShopAssist AI' : 'Open ShopAssist AI'}
          style={{
            width:        '56px',
            height:       '56px',
            borderRadius: '50%',
            background:   '#008060',
            border:       'none',
            cursor:       'pointer',
            display:      'flex',
            alignItems:   'center',
            justifyContent: 'center',
            fontSize:     open ? '18px' : '26px',
            color:        '#ffffff',
            boxShadow:    '0 4px 20px rgba(0,128,96,0.45)',
            transition:   'transform 0.2s ease, box-shadow 0.2s ease',
            outline:      'none',
            flexShrink:   0,
          }}
          onMouseEnter={e => {
            e.currentTarget.style.transform  = 'scale(1.08)'
            e.currentTarget.style.boxShadow  = '0 6px 28px rgba(0,128,96,0.55)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.transform  = 'scale(1)'
            e.currentTarget.style.boxShadow  = '0 4px 20px rgba(0,128,96,0.45)'
          }}
        >
          {open ? '✕' : '🛍️'}
        </button>
      </div>
    </>
  )
}
