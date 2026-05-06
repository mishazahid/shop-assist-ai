/**
 * AdminDashboard.jsx
 * ------------------
 * Merchant admin panel. Three tabs:
 *   1. Queries    — live query log with answered/unanswered status
 *   2. Analytics  — summary stats, top categories/brands, unanswered list
 *   3. Widget     — customise colors, position, copy, live preview
 *
 * Auth: admin key stored in localStorage, checked against ADMIN_API_KEY on the backend.
 * Access at: /admin
 */

import { useState, useEffect, useCallback } from 'react'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── API helpers ───────────────────────────────────────────────────────────────

async function adminFetch(path, key, options = {}) {
  const sep = path.includes('?') ? '&' : '?'
  const res = await fetch(`${BASE_URL}${path}${sep}admin_key=${encodeURIComponent(key)}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color = '#008060' }) {
  return (
    <div style={st.statCard}>
      <div style={{ ...st.statValue, color }}>{value}</div>
      <div style={st.statLabel}>{label}</div>
      {sub && <div style={st.statSub}>{sub}</div>}
    </div>
  )
}

function BarChart({ title, rows }) {
  if (!rows || rows.length === 0) return (
    <div style={st.chartBox}>
      <div style={st.chartTitle}>{title}</div>
      <div style={st.empty}>No data yet</div>
    </div>
  )
  const max = Math.max(...rows.map(r => r.count))
  return (
    <div style={st.chartBox}>
      <div style={st.chartTitle}>{title}</div>
      {rows.map(r => (
        <div key={r.label} style={st.barRow}>
          <div style={st.barLabel}>{r.label}</div>
          <div style={st.barTrack}>
            <div style={{ ...st.barFill, width: `${(r.count / max) * 100}%` }} />
          </div>
          <div style={st.barCount}>{r.count}</div>
        </div>
      ))}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AdminDashboard() {
  const [adminKey,   setAdminKey]   = useState(() => localStorage.getItem('shopassist-admin-key') || '')
  const [authed,     setAuthed]     = useState(false)
  const [authErr,    setAuthErr]    = useState('')
  const [tab,        setTab]        = useState('queries')

  // Queries tab
  const [queries,    setQueries]    = useState([])
  const [qTotal,     setQTotal]     = useState(0)
  const [qOffset,    setQOffset]    = useState(0)
  const [qLoading,   setQLoading]   = useState(false)

  // Analytics tab
  const [summary,    setSummary]    = useState(null)
  const [aLoading,   setALoading]   = useState(false)

  // Widget config tab
  const [config,     setConfig]     = useState(null)
  const [cfgSaving,  setCfgSaving]  = useState(false)
  const [cfgMsg,     setCfgMsg]     = useState('')

  const handleLogin = async () => {
    setAuthErr('')
    try {
      await adminFetch('/admin/analytics', adminKey)
      localStorage.setItem('shopassist-admin-key', adminKey)
      setAuthed(true)
    } catch (e) {
      setAuthErr(e.message)
    }
  }

  const loadQueries = useCallback(async (offset = 0) => {
    setQLoading(true)
    try {
      const data = await adminFetch(`/admin/queries?limit=50&offset=${offset}`, adminKey)
      setQueries(data.queries || [])
      setQTotal(data.total || 0)
      setQOffset(offset)
    } catch (e) {
      console.error(e)
    } finally {
      setQLoading(false)
    }
  }, [adminKey])

  const loadAnalytics = useCallback(async () => {
    setALoading(true)
    try {
      const data = await adminFetch('/admin/analytics', adminKey)
      setSummary(data)
    } catch (e) {
      console.error(e)
    } finally {
      setALoading(false)
    }
  }, [adminKey])

  const loadConfig = useCallback(async () => {
    try {
      const data = await adminFetch('/admin/widget-config', adminKey)
      setConfig(data)
    } catch (e) {
      console.error(e)
    }
  }, [adminKey])

  useEffect(() => {
    if (!authed) return
    if (tab === 'queries')   loadQueries(0)
    if (tab === 'analytics') loadAnalytics()
    if (tab === 'widget')    loadConfig()
  }, [authed, tab, loadQueries, loadAnalytics, loadConfig])

  const saveConfig = async () => {
    setCfgSaving(true)
    setCfgMsg('')
    try {
      const saved = await adminFetch('/admin/widget-config', adminKey, {
        method: 'POST',
        body: JSON.stringify(config),
      })
      setConfig(saved)
      setCfgMsg('✅ Saved!')
    } catch (e) {
      setCfgMsg(`❌ ${e.message}`)
    } finally {
      setCfgSaving(false)
      setTimeout(() => setCfgMsg(''), 3000)
    }
  }

  // ── Login screen ─────────────────────────────────────────────────────────
  if (!authed) {
    return (
      <div style={st.loginPage}>
        <div style={st.loginCard}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>🛍️</div>
          <h2 style={st.loginTitle}>ShopAssist Admin</h2>
          <p style={st.loginSub}>Enter your admin key to continue</p>
          <input
            style={st.loginInput}
            type="password"
            placeholder="Admin key"
            value={adminKey}
            onChange={e => setAdminKey(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            autoFocus
          />
          {authErr && <div style={st.loginErr}>⚠️ {authErr}</div>}
          <button style={st.loginBtn} onClick={handleLogin}>
            Sign In →
          </button>
          <div style={st.loginHint}>
            Set <code>ADMIN_API_KEY</code> in your Railway environment variables.
          </div>
        </div>
      </div>
    )
  }

  // ── Dashboard ─────────────────────────────────────────────────────────────
  return (
    <div style={st.page}>
      {/* Header */}
      <header style={st.header}>
        <div style={st.headerLogo}>
          <span>🛍️</span>
          <span style={st.headerTitle}>ShopAssist Admin</span>
        </div>
        <div style={st.headerRight}>
          <a href="/" style={st.backLink}>← Back to widget</a>
          <button style={st.logoutBtn} onClick={() => { setAuthed(false); localStorage.removeItem('shopassist-admin-key') }}>
            Sign out
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div style={st.tabs}>
        {[['queries','📋 Queries'], ['analytics','📊 Analytics'], ['widget','🎨 Widget']].map(([id, label]) => (
          <button
            key={id}
            style={{ ...st.tab, ...(tab === id ? st.tabActive : {}) }}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={st.content}>

        {/* ── Queries tab ───────────────────────────────────────────────── */}
        {tab === 'queries' && (
          <div>
            <div style={st.sectionHeader}>
              <h2 style={st.sectionTitle}>Customer Queries <span style={st.badge}>{qTotal}</span></h2>
              <button style={st.refreshBtn} onClick={() => loadQueries(qOffset)}>⟳ Refresh</button>
            </div>

            {qLoading ? <div style={st.loading}>Loading…</div> : (
              <>
                <div style={st.tableWrap}>
                  <table style={st.table}>
                    <thead>
                      <tr>
                        {['Time', 'Message', 'Category', 'Brand', 'Products', 'Status', 'Response'].map(h => (
                          <th key={h} style={st.th}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {queries.length === 0 ? (
                        <tr><td colSpan={7} style={st.emptyCell}>No queries yet — chat with the widget to see data here.</td></tr>
                      ) : queries.map(q => (
                        <tr key={q.id} style={q.was_answered ? {} : st.unansweredRow}>
                          <td style={st.td}>{q.ts?.slice(0, 16).replace('T', ' ')}</td>
                          <td style={{ ...st.td, maxWidth: 260, wordBreak: 'break-word' }}>{q.message}</td>
                          <td style={st.td}>{q.category || '—'}</td>
                          <td style={st.td}>{q.vendor || '—'}</td>
                          <td style={{ ...st.td, textAlign: 'center' }}>{q.products_found}</td>
                          <td style={st.td}>
                            <span style={q.was_answered ? st.answered : st.unanswered}>
                              {q.was_answered ? '✓ Answered' : '✗ No results'}
                            </span>
                          </td>
                          <td style={{ ...st.td, textAlign: 'right' }}>{q.response_ms}ms</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div style={st.pagination}>
                  <button style={st.pageBtn} disabled={qOffset === 0} onClick={() => loadQueries(Math.max(0, qOffset - 50))}>
                    ← Prev
                  </button>
                  <span style={st.pageInfo}>
                    {qOffset + 1}–{Math.min(qOffset + 50, qTotal)} of {qTotal}
                  </span>
                  <button style={st.pageBtn} disabled={qOffset + 50 >= qTotal} onClick={() => loadQueries(qOffset + 50)}>
                    Next →
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {/* ── Analytics tab ─────────────────────────────────────────────── */}
        {tab === 'analytics' && (
          <div>
            <div style={st.sectionHeader}>
              <h2 style={st.sectionTitle}>Analytics</h2>
              <button style={st.refreshBtn} onClick={loadAnalytics}>⟳ Refresh</button>
            </div>

            {aLoading || !summary ? <div style={st.loading}>Loading…</div> : (
              <>
                {/* Summary cards */}
                <div style={st.statGrid}>
                  <StatCard label="Total Queries"     value={summary.total_queries}                        />
                  <StatCard label="Answer Rate"       value={`${summary.answer_rate_pct}%`}  color="#16a34a" />
                  <StatCard label="Unanswered"        value={summary.unanswered_count}        color="#dc2626" />
                  <StatCard label="Avg Response Time" value={`${summary.avg_response_ms}ms`} color="#6b7280" />
                </div>

                {/* Charts */}
                <div style={st.chartGrid}>
                  <BarChart title="Top Searched Categories" rows={summary.top_categories} />
                  <BarChart title="Top Searched Brands"     rows={summary.top_vendors}    />
                </div>

                {/* Unanswered queries list */}
                {summary.unanswered_queries?.length > 0 && (
                  <div style={st.unansweredBox}>
                    <div style={st.chartTitle}>Recent Unanswered Queries</div>
                    <div style={st.unansweredHint}>
                      These are queries where no products were returned — consider adding these items to your catalog.
                    </div>
                    {summary.unanswered_queries.map((q, i) => (
                      <div key={i} style={st.unansweredItem}>
                        <span style={st.unansweredMsg}>"{q.message}"</span>
                        <span style={st.unansweredTs}>{q.ts?.slice(0,10)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Widget config tab ──────────────────────────────────────────── */}
        {tab === 'widget' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 32 }}>
            {/* Form */}
            <div>
              <div style={st.sectionHeader}>
                <h2 style={st.sectionTitle}>Widget Settings</h2>
                {cfgMsg && <span style={{ fontSize: 13, color: cfgMsg.startsWith('✅') ? '#16a34a' : '#dc2626' }}>{cfgMsg}</span>}
              </div>

              {!config ? <div style={st.loading}>Loading…</div> : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

                  <Field label="Primary Color">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <input type="color" value={config.primaryColor}
                        onChange={e => setConfig(c => ({ ...c, primaryColor: e.target.value }))}
                        style={{ width: 48, height: 36, border: 'none', cursor: 'pointer', borderRadius: 6 }}
                      />
                      <input style={st.textInput} value={config.primaryColor}
                        onChange={e => setConfig(c => ({ ...c, primaryColor: e.target.value }))}
                      />
                    </div>
                  </Field>

                  <Field label="Position">
                    <div style={{ display: 'flex', gap: 10 }}>
                      {['bottom-right', 'bottom-left'].map(pos => (
                        <button key={pos}
                          style={{ ...st.posBtn, ...(config.position === pos ? st.posBtnActive : {}) }}
                          onClick={() => setConfig(c => ({ ...c, position: pos }))}
                        >
                          {pos === 'bottom-right' ? '↘ Bottom Right' : '↙ Bottom Left'}
                        </button>
                      ))}
                    </div>
                  </Field>

                  <Field label="Widget Title">
                    <input style={st.textInput} value={config.title}
                      onChange={e => setConfig(c => ({ ...c, title: e.target.value }))}
                    />
                  </Field>

                  <Field label="Subtitle">
                    <input style={st.textInput} value={config.subtitle}
                      onChange={e => setConfig(c => ({ ...c, subtitle: e.target.value }))}
                    />
                  </Field>

                  <Field label="Welcome Message">
                    <input style={st.textInput} value={config.welcomeMsg}
                      onChange={e => setConfig(c => ({ ...c, welcomeMsg: e.target.value }))}
                    />
                  </Field>

                  <Field label="Show Branding">
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                      <input type="checkbox" checked={config.showBranding}
                        onChange={e => setConfig(c => ({ ...c, showBranding: e.target.checked }))}
                        style={{ width: 16, height: 16 }}
                      />
                      <span style={{ fontSize: 13, color: '#374151' }}>Show "Powered by ShopAssist AI"</span>
                    </label>
                  </Field>

                  <button
                    style={{ ...st.saveBtn, opacity: cfgSaving ? 0.7 : 1 }}
                    onClick={saveConfig}
                    disabled={cfgSaving}
                  >
                    {cfgSaving ? 'Saving…' : 'Save Changes'}
                  </button>
                </div>
              )}
            </div>

            {/* Live preview */}
            {config && (
              <div>
                <div style={st.previewLabel}>Live Preview</div>
                <div style={{ ...st.previewWidget, '--primary': config.primaryColor }}>
                  <div style={{ ...st.previewHeader, background: config.primaryColor }}>
                    <div style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>{config.title}</div>
                    <div style={{ color: 'rgba(255,255,255,0.75)', fontSize: 11, marginTop: 2 }}>{config.subtitle}</div>
                  </div>
                  <div style={st.previewBody}>
                    <div style={st.previewBubble}>{config.welcomeMsg}</div>
                  </div>
                  {config.showBranding && (
                    <div style={st.previewBranding}>Powered by ShopAssist AI</div>
                  )}
                </div>
                <div style={{ marginTop: 8, fontSize: 11, color: '#9ca3af', textAlign: 'center' }}>
                  Position: {config.position}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Field wrapper ─────────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div>
      <label style={st.fieldLabel}>{label}</label>
      {children}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────
const st = {
  // Login
  loginPage:  { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f9fafb' },
  loginCard:  { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 16, padding: '40px 36px', width: 360, textAlign: 'center', boxShadow: '0 4px 24px rgba(0,0,0,0.08)' },
  loginTitle: { fontSize: 22, fontWeight: 700, color: '#111827', margin: '0 0 6px' },
  loginSub:   { fontSize: 13, color: '#6b7280', margin: '0 0 24px' },
  loginInput: { width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14, boxSizing: 'border-box', marginBottom: 10 },
  loginErr:   { color: '#dc2626', fontSize: 13, margin: '0 0 10px' },
  loginBtn:   { width: '100%', padding: '11px 0', background: '#008060', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },
  loginHint:  { marginTop: 16, fontSize: 11, color: '#9ca3af', lineHeight: 1.5 },

  // Layout
  page:    { minHeight: '100vh', background: '#f9fafb', fontFamily: 'Inter, system-ui, sans-serif' },
  header:  { background: '#fff', borderBottom: '1px solid #e5e7eb', padding: '0 28px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  headerLogo:  { display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: 16, color: '#111827' },
  headerTitle: { fontSize: 16 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 14 },
  backLink:    { fontSize: 13, color: '#008060', textDecoration: 'none' },
  logoutBtn:   { padding: '6px 14px', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, cursor: 'pointer', color: '#374151' },

  tabs:    { background: '#fff', borderBottom: '1px solid #e5e7eb', padding: '0 28px', display: 'flex', gap: 4 },
  tab:     { padding: '12px 18px', border: 'none', background: 'transparent', fontSize: 13, fontWeight: 500, color: '#6b7280', cursor: 'pointer', borderBottom: '2px solid transparent', marginBottom: -1 },
  tabActive: { color: '#008060', borderBottomColor: '#008060' },

  content: { padding: '28px', maxWidth: 1100, margin: '0 auto' },

  sectionHeader: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 },
  sectionTitle:  { fontSize: 18, fontWeight: 700, color: '#111827', margin: 0 },
  badge:         { background: '#f3f4f6', borderRadius: 100, padding: '2px 8px', fontSize: 12, fontWeight: 600, color: '#6b7280' },
  refreshBtn:    { marginLeft: 'auto', padding: '6px 14px', background: '#f3f4f6', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, cursor: 'pointer', color: '#374151' },

  loading:   { color: '#9ca3af', fontSize: 14, padding: '40px 0', textAlign: 'center' },
  empty:     { color: '#9ca3af', fontSize: 13, padding: '20px 0', textAlign: 'center' },
  emptyCell: { padding: '32px', textAlign: 'center', color: '#9ca3af', fontSize: 13 },

  // Table
  tableWrap:    { overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 10 },
  table:        { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th:           { padding: '10px 14px', textAlign: 'left', background: '#f9fafb', color: '#6b7280', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '1px solid #e5e7eb' },
  td:           { padding: '10px 14px', borderBottom: '1px solid #f3f4f6', color: '#374151', verticalAlign: 'top' },
  unansweredRow: { background: '#fff7f7' },
  answered:     { color: '#16a34a', fontWeight: 600 },
  unanswered:   { color: '#dc2626', fontWeight: 600 },

  // Pagination
  pagination: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, marginTop: 16 },
  pageBtn:    { padding: '6px 16px', border: '1px solid #e5e7eb', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 13 },
  pageInfo:   { fontSize: 13, color: '#6b7280' },

  // Stat cards
  statGrid:  { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 },
  statCard:  { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '20px 24px' },
  statValue: { fontSize: 32, fontWeight: 800, color: '#008060', letterSpacing: '-0.02em' },
  statLabel: { fontSize: 13, color: '#6b7280', marginTop: 4 },
  statSub:   { fontSize: 11, color: '#9ca3af', marginTop: 2 },

  // Bar charts
  chartGrid:  { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 },
  chartBox:   { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '20px 24px' },
  chartTitle: { fontSize: 13, fontWeight: 700, color: '#374151', marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.04em' },
  barRow:     { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 },
  barLabel:   { width: 110, fontSize: 12, color: '#374151', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  barTrack:   { flex: 1, height: 10, background: '#f3f4f6', borderRadius: 100, overflow: 'hidden' },
  barFill:    { height: '100%', background: '#008060', borderRadius: 100, transition: 'width 0.3s' },
  barCount:   { width: 32, textAlign: 'right', fontSize: 12, color: '#6b7280', flexShrink: 0 },

  // Unanswered list
  unansweredBox:  { background: '#fff', border: '1px solid #fecaca', borderRadius: 12, padding: '20px 24px' },
  unansweredHint: { fontSize: 12, color: '#9ca3af', marginBottom: 14 },
  unansweredItem: { display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #fef2f2', fontSize: 13 },
  unansweredMsg:  { color: '#374151', fontStyle: 'italic', flex: 1, marginRight: 16 },
  unansweredTs:   { color: '#9ca3af', flexShrink: 0 },

  // Widget config form
  fieldLabel: { display: 'block', fontSize: 12, fontWeight: 600, color: '#374151', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 },
  textInput:  { width: '100%', padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 13, boxSizing: 'border-box', outline: 'none' },
  posBtn:     { padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8, background: '#fff', fontSize: 12, cursor: 'pointer', color: '#374151', fontWeight: 500 },
  posBtnActive: { borderColor: '#008060', background: '#f0fdf9', color: '#008060' },
  saveBtn:    { padding: '11px 24px', background: '#008060', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer' },

  // Preview
  previewLabel:   { fontSize: 11, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 },
  previewWidget:  { border: '1px solid #e5e7eb', borderRadius: 14, overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' },
  previewHeader:  { padding: '14px 16px' },
  previewBody:    { padding: 14, background: '#f9fafb', minHeight: 80, display: 'flex', alignItems: 'flex-end' },
  previewBubble:  { background: '#f3f4f6', borderRadius: '16px 16px 16px 4px', padding: '8px 12px', fontSize: 12, color: '#374151', maxWidth: '90%' },
  previewBranding:{ padding: '6px 12px', fontSize: 10, color: '#9ca3af', textAlign: 'right', borderTop: '1px solid #f3f4f6', background: '#fff' },
}
