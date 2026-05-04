import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],

  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },

  build: {
    lib: {
      entry:    resolve(__dirname, 'src/widget.jsx'),
      name:     'ShopAssistWidget',
      formats:  ['iife'],
      fileName: () => 'widget',
    },

    outDir:      'dist',
    emptyOutDir: false,   // main app already built to dist/ — don't wipe it

    rollupOptions: {
      // Bundle EVERYTHING — React, ReactDOM, all components.
      // The script tag on Shopify has no access to any npm packages.
      external: [],
      output: {
        inlineDynamicImports: true,
        assetFileNames: 'widget[extname]',
      },
    },

    minify: true,
  },
})
