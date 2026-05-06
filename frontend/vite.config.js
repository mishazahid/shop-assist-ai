import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  // Serve index.html for all routes so /admin works as a client-side route
  appType: 'spa',
})
