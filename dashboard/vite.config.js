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

// Dentro do container no Windows o Vite precisa de polling para enxergar um
// `git pull`. O bind mount do Docker Desktop (`- ./dashboard:/app`) não repassa
// os eventos de arquivo do sistema de arquivos do Windows para o inotify do
// Linux — o arquivo novo está lá, mas nada avisa o Vite, então ele segue
// servindo o grafo de módulos antigo e o navegador mostra a versão anterior do
// painel até alguém recriar o container. O sintoma é bem específico: `git pull`
// traz uma aba nova, o backend responde ao endpoint novo e a aba não aparece.
//
// Fica atrás da variável porque polling custa CPU e só é preciso no container:
// rodando `npm run dev` direto na máquina os eventos funcionam normalmente.
// O `docker-compose.yml` liga a variável no serviço `frontend`.
const polling = ['1', 'true', 'yes'].includes(String(process.env.VITE_USE_POLLING).toLowerCase())

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: polling ? { usePolling: true, interval: 300 } : undefined,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/videos': { target: backend, changeOrigin: true },
      '/thumbnails': { target: backend, changeOrigin: true },
      '/render': { target: renderer, changeOrigin: true },
    }
  }
})
