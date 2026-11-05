import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En développement (npm run dev), tout ce qui commence par /api est renvoyé au backend FastAPI (port 8000).
// En production (npm run build), le backend sert lui-même le dossier dist/ : pas besoin de proxy.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
})
