/**
 * vite.widget.config.js
 * ---------------------
 * Builds the embeddable Shopify widget as a single self-contained IIFE file.
 *
 * Output: dist/widget.js
 *
 * IIFE format means the file has no import/export statements — it runs
 * immediately when loaded via a plain <script> tag in any Shopify theme.
 * React and all dependencies are bundled in so no CDN or npm is needed.
 */

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],

  define: {
    // Required for React to run in production mode inside the bundle
    'process.env.NODE_ENV': JSON.stringify('production'),
  },

  build: {
    lib: {
      entry:   resolve(__dirname, 'src/widget.jsx'),
      name:    'ShopAssistWidget',
      formats: ['iife'],
      // Always output as widget.js — no hash suffix
      fileName: () => 'widget',
    },

    outDir:      'dist',
    emptyOutDir: false,   // Main app already built to dist/ — don't wipe it

    rollupOptions: {
      output: {
        // Keep everything in one file — no code splitting
        inlineDynamicImports: true,
        // widget.css → widget.css (predictable filename for the <link> tag)
        assetFileNames: 'widget[extname]',
      },
    },

    // Minify for a smaller script tag payload
    minify: true,
  },
})
