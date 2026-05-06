/**
 * ChatWidget.jsx
 * --------------
 * The main chat interface. Renders the conversation history and handles
 * user input. Each AI message can include a scrollable row of ProductCards.
 */

import { useState, useRef, useEffect } from 'react'
import { sendChat, fetchSuggestions } from '../api'
import ProductCard from './ProductCard'

// ── Styles ────────────────────────────────────────────────────────────────────
const s = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: '#ffffff',
    borderRadius: '16px',
    boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
    overflow: 'hidden',
  },

  // ── Chat header ──────────────────────────────────────────────────────────
  header: {
    background: '#008060',
    padding: '16px 20px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    flexShrink: 0,
  },
  headerAvatar: {
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    background: 'rgba(255,255,255,0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '18px',
  },
  headerText: {
    flex: 1,
  },
  headerTitle: {
    color: '#ffffff',
    fontWeight: '700',
    fontSize: '15px',
  },
  headerSubtitle: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: '12px',
    marginTop: '1px',
  },

  // ── Messages area ────────────────────────────────────────────────────────
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },

  // ── Individual message row ───────────────────────────────────────────────
  msgRow: (role) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: role === 'user' ? 'flex-end' : 'flex-start',
    gap: '8px',
  }),

  bubble: (role) => ({
    maxWidth: '75%',
    padding: '10px 14px',
    borderRadius: role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
    background: role === 'user' ? '#008060' : '#f3f4f6',
    color: role === 'user' ? '#ffffff' : '#111827',
    fontSize: '14px',
    lineHeight: '1.55',
    whiteSpace: 'pre-wrap',
  }),

  // ── Product card grid (2-column responsive) ─────────────────────────────
  productGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '10px',
    width: '100%',
  },

  // ── Typing indicator ─────────────────────────────────────────────────────
  typingBubble: {
    padding: '10px 16px',
    borderRadius: '18px 18px 18px 4px',
    background: '#f3f4f6',
    display: 'flex',
    gap: '4px',
    alignItems: 'center',
  },
  dot: {
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    background: '#9ca3af',
    animation: 'bounce 1.2s infinite',
  },

  // ── Input bar ────────────────────────────────────────────────────────────
  inputBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '14px 16px',
    borderTop: '1px solid #e5e7eb',
    background: '#ffffff',
    flexShrink: 0,
  },
  input: {
    flex: 1,
    border: '1px solid #e5e7eb',
    borderRadius: '24px',
    padding: '10px 16px',
    fontSize: '14px',
    outline: 'none',
    background: '#f9fafb',
    transition: 'border-color 0.15s',
  },
  // ── Autocomplete dropdown ────────────────────────────────────────────────
  dropdown: {
    position:     'absolute',
    bottom:       'calc(100% + 4px)',  // float above the input, 4px gap
    left:         0,
    right:        0,
    background:   '#ffffff',
    border:       '1px solid #e5e7eb',
    borderRadius: '10px',
    boxShadow:    '0 -4px 16px rgba(0,0,0,0.08)',
    overflow:     'hidden',
    zIndex:       20,
  },
  dropdownItem: {
    padding:    '9px 14px',
    fontSize:   '13px',
    color:      '#374151',
    cursor:     'pointer',
    transition: 'background 0.1s',
    userSelect: 'none',
  },

  sendBtn: {
    width: '40px',
    height: '40px',
    borderRadius: '50%',
    border: 'none',
    background: '#008060',
    color: '#fff',
    fontSize: '18px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s',
    flexShrink: 0,
  },
  sendBtnDisabled: {
    background: '#d1d5db',
  },

  // ── Empty state ──────────────────────────────────────────────────────────
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    color: '#9ca3af',
    padding: '40px',
  },
  emptyIcon: { fontSize: '48px' },
  emptyTitle: { fontSize: '16px', fontWeight: '600', color: '#374151' },
  emptySubtitle: { fontSize: '13px', textAlign: 'center', lineHeight: 1.5 },

  // ── Suggestion chips ─────────────────────────────────────────────────────
  chips: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
    justifyContent: 'center',
    marginTop: '4px',
  },
  chip: {
    padding: '6px 14px',
    borderRadius: '100px',
    border: '1px solid #e5e7eb',
    background: '#ffffff',
    fontSize: '12px',
    color: '#374151',
    cursor: 'pointer',
    transition: 'border-color 0.15s, background 0.15s',
  },
  // ── Branding footer ───────────────────────────────────────────────────────────
  brandingRow: {
    fontSize: '11px',
    color: '#9ca3af',
    padding: '6px 14px 10px',
    textAlign: 'right',
    borderTop: '1px solid #f3f4f6',
  },
}

// Toggle for "Powered by ShopAssist AI" footer.
// Merchants can set VITE_SHOW_BRANDING=false in frontend/.env to hide it.
const SHOW_BRANDING =
  typeof import.meta !== 'undefined' &&
  import.meta.env &&
  import.meta.env.VITE_SHOW_BRANDING !== 'false'

// ── Bounce animation injected once ────────────────────────────────────────────
const ANIM_CSS = `
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); }
  30%            { transform: translateY(-6px); }
}
`
if (!document.getElementById('shopassist-anim')) {
  const tag = document.createElement('style')
  tag.id = 'shopassist-anim'
  tag.textContent = ANIM_CSS
  document.head.appendChild(tag)
}

// ── Suggestion prompts shown when chat is empty ───────────────────────────────
const SUGGESTIONS = [
  'Show me black shoes under $150',
  'Do you have Adidas products?',
  'I need a red dress in size M',
  'What hoodies are available?',
]


// ── Component ─────────────────────────────────────────────────────────────────
export default function ChatWidget() {
  const [messages, setMessages] = useState([])   // {role, text, products?}
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)
  const bottomRef               = useRef(null)
  const inputRef                = useRef(null)

  // Autocomplete
  const [acTerms,       setAcTerms]       = useState([])   // full list, loaded once
  const [dropdownItems, setDropdownItems] = useState([])   // filtered for current input
  const [showDropdown,  setShowDropdown]  = useState(false)

  // Stable session ID — persisted in localStorage so multi-turn context
  // survives page refreshes. Sent with every /chat request so the backend
  // can merge follow-up intents.
  const sessionId = useRef(
    (() => {
      // SSR guard
      if (typeof window === 'undefined') {
        return (
          (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
            ? crypto.randomUUID()
            : Math.random().toString(36).slice(2) + Date.now().toString(36))
        )
      }
      try {
        const existing = localStorage.getItem('shopassist-session-id')
        if (existing && typeof existing === 'string') return existing
      } catch {
        // ignore and fall through to generating a fresh ID
      }

      const fresh =
        typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
          ? crypto.randomUUID()
          : Math.random().toString(36).slice(2) + Date.now().toString(36)

      try {
        localStorage.setItem('shopassist-session-id', fresh)
      } catch {
        // ignore write errors (private / blocked storage)
      }
      return fresh
    })()
  )

  // Load conversation history from localStorage on first mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('shopassist-chat-history')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) setMessages(parsed.slice(-50))
      }
    } catch {}
  }, [])

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length === 0) return
    try {
      localStorage.setItem('shopassist-chat-history', JSON.stringify(messages.slice(-50)))
    } catch {}
  }, [messages])

  // Auto-scroll to the latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Load autocomplete terms once on mount — silent fail, it's an enhancement only
  useEffect(() => {
    fetchSuggestions()
      .then(data => setAcTerms(data.terms || []))
      .catch(() => {})
  }, [])

  const handleInputChange = (e) => {
    const val = e.target.value
    setInput(val)

    const trimmed = val.trim()
    if (trimmed.length < 2) {
      setShowDropdown(false)
      return
    }

    const lower = trimmed.toLowerCase()
    const matches = acTerms
      .filter(t => t.toLowerCase().includes(lower))
      .slice(0, 6)

    setDropdownItems(matches)
    setShowDropdown(matches.length > 0)
  }

  const handleSuggestionClick = (term) => {
    setInput(term)
    setShowDropdown(false)
    inputRef.current?.focus()
  }

  const handleClearChat = () => {
    setMessages([])
    setError(null)
    try { localStorage.removeItem('shopassist-chat-history') } catch {}
  }

  const handleSend = async (text) => {
    const msg = (text || input).trim()
    if (!msg || loading) return

    setInput('')
    setShowDropdown(false)
    setError(null)

    // Add user message to chat
    setMessages((prev) => [...prev, { role: 'user', text: msg }])
    setLoading(true)

    try {
      const data = await sendChat(msg, sessionId.current)
      // Add assistant response (with optional product cards)
      setMessages((prev) => [
        ...prev,
        {
          role:     'assistant',
          text:     data.answer || 'Here are some options I found.',
          products: data.products || [],
        },
      ])
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
      // Refocus the input after response
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      setShowDropdown(false)
      return
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div style={s.container}>
      {/* Header */}
      <div style={s.header}>
        <div style={s.headerAvatar}>🛍️</div>
        <div style={s.headerText}>
          <div style={s.headerTitle}>ShopAssist AI</div>
          <div style={s.headerSubtitle}>Ask me anything about our products</div>
        </div>
        <div
          style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: '#4ade80', flexShrink: 0,
          }}
          title="Online"
        />
      </div>

      {/* Messages */}
      <div style={s.messages}>
        {messages.length === 0 && !loading ? (
          // Empty state with suggestion chips
          <div style={s.emptyState}>
            <div style={s.emptyIcon}>🛍️</div>
            <div style={s.emptyTitle}>How can I help you shop today?</div>
            <div style={s.emptySubtitle}>
              Ask me to find products by style, color, size, or budget.
            </div>
            <div style={s.chips}>
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  style={s.chip}
                  onClick={() => handleSend(suggestion)}
                  onMouseEnter={(e) => {
                    e.target.style.borderColor = '#008060'
                    e.target.style.background  = '#f0fdf9'
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.borderColor = '#e5e7eb'
                    e.target.style.background  = '#ffffff'
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={s.msgRow(msg.role)}>
              {/* Text bubble */}
              <div style={s.bubble(msg.role)}>{msg.text}</div>

              {/* Product cards (AI messages only) */}
              {msg.role === 'assistant' && msg.products?.length > 0 && (
                <div style={s.productGrid}>
                  {msg.products.map((product, j) => (
                    <ProductCard key={product.variant_id || product.product_id || j} product={product} />
                  ))}
                </div>
              )}
            </div>
          ))
        )}

        {/* Typing indicator while waiting */}
        {loading && (
          <div style={s.msgRow('assistant')}>
            <div style={s.typingBubble}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{
                    ...s.dot,
                    animationDelay: `${i * 0.2}s`,
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div
            style={{
              background: '#fef2f2', border: '1px solid #fecaca',
              borderRadius: '8px', padding: '10px 14px',
              color: '#991b1b', fontSize: '13px',
            }}
          >
            ⚠️ {error}
          </div>
        )}

        {/* Invisible element to scroll to */}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={s.inputBar}>
        {/* Wrapper gives the dropdown an anchor point */}
        <div style={{ position: 'relative', flex: 1 }}>
          {/* Autocomplete dropdown — floats above the input */}
          {showDropdown && dropdownItems.length > 0 && (
            <div style={s.dropdown}>
              {dropdownItems.map((term, i) => (
                <div
                  key={i}
                  style={s.dropdownItem}
                  onMouseDown={(e) => {
                    // preventDefault keeps focus on the input so blur doesn't
                    // fire before the click is registered
                    e.preventDefault()
                    handleSuggestionClick(term)
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = '#f0fdf9' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  {term}
                </div>
              ))}
            </div>
          )}
          <input
            ref={inputRef}
            style={s.input}
            type="text"
            placeholder="Ask about products, sizes, colors, budget…"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onBlur={() => setShowDropdown(false)}
            disabled={loading}
            autoFocus
          />
        </div>
        <button
          style={{
            ...s.sendBtn,
            ...(loading || !input.trim() ? s.sendBtnDisabled : {}),
          }}
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          title="Send"
        >
          ↑
        </button>
      </div>
      {SHOW_BRANDING && (
        <div style={s.brandingRow}>
          Powered by{' '}
          <a
            href="https://shopassist.ai"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#6b7280', textDecoration: 'none', fontWeight: 500 }}
          >
            ShopAssist AI
          </a>
        </div>
      )}
    </div>
  )
}

