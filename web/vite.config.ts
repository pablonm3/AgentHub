import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Python server serves web/dist at the root and answers /api, /reports and /runs.
// In development the Vite server forwards those paths to it. The server refuses requests
// whose Host or Origin is not its own, so the proxy presents the server's own origin.
const server = process.env.AGENTHUB_URL ?? 'http://127.0.0.1:8787'
const forward = { target: server, changeOrigin: true, headers: { origin: server } }

export default defineConfig({
  base: '/',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    proxy: {
      '/api': forward,
      '/reports': forward,
      '/runs': forward,
    },
  },
})
