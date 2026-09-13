import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Alvo do backend para o proxy de desenvolvimento. O padrão é o nome do
// serviço no docker-compose; use VITE_PROXY_TARGET=http://localhost:8000 para
// rodar o dev server no host contra um backend em localhost (sem CORS, mesma
// origem).
const backend = process.env.VITE_PROXY_TARGET || 'http://backend:8000'
const renderer = process.env.VITE_RENDER_TARGET || 'http://renderer:3100'

// O plugin `seo()` saiu com a superfície de marketing (ADR-009): ele injetava
// a home visível a crawler dentro do #root e emitia as páginas estáticas, o
// sitemap.xml e o llms.txt do produto comercial do upstream. `allowedHosts`
// também saiu, porque listava os domínios do deploy deles.
// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/videos': { target: backend, changeOrigin: true },
      '/thumbnails': { target: backend, changeOrigin: true },
      '/render': { target: renderer, changeOrigin: true },
    }
  }
})
