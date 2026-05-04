/**
 * widget.jsx
 * ----------
 * Entry point for the embeddable Shopify widget bundle.
 *
 * When this script is loaded on a Shopify storefront it:
 *   1. Finds or creates a <div id="shopassist-widget-root"> in the page body
 *   2. Mounts the FloatingWidget (bubble + chat panel) into that div
 *   3. Never touches any other part of the page
 *
 * All styles are inline — no CSS file is injected, no global styles change.
 *
 * Usage in Shopify theme.liquid (before </body>):
 *   <script src="https://your-vercel-app.vercel.app/widget.js" defer></script>
 */

import { createRoot } from 'react-dom/client'
import FloatingWidget from './components/FloatingWidget'

function mount() {
  // Re-use an existing root div if the merchant added one manually,
  // otherwise append one to the body.
  let container = document.getElementById('shopassist-widget-root')
  if (!container) {
    container = document.createElement('div')
    container.id = 'shopassist-widget-root'
    document.body.appendChild(container)
  }

  createRoot(container).render(<FloatingWidget />)
}

// Wait for DOM if the script loaded in <head>; mount immediately if in <body>
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount)
} else {
  mount()
}
