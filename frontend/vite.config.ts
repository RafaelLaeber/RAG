import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Em desenvolvimento, /api vai para o FastAPI: mesma origem, o cookie de sessão funciona sem CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000' },
    },
  },
})
