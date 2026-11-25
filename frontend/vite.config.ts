import { readFileSync } from 'node:fs'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Versão do projeto, lida do package.json (que `npm version` atualiza no release).
// Vira a constante global __APP_VERSION__ no código, sem precisar repetir o número.
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8')) as {
  version: string
}

// Em desenvolvimento, /api vai para o FastAPI: mesma origem, os cookies de login funcionam sem CORS.
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(version),
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000' },
    },
  },
})
