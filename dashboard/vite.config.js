import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
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

// O motor se atualiza pelo botão do site (25-set-2026, `atualizar_motor.py`):
// avança o checkout e grava esta marca quando algum arquivo do painel mudou.
// O polling acima vê a EDIÇÃO de um arquivo que já existia, mas não a mudança
// do grafo de módulos -- um arquivo novo ou apagado deixava o painel em preto
// até o `docker compose restart frontend` do `atalhos\atualizar.bat`. Aqui o
// dev server faz o mesmo sozinho, e a aba aberta recarrega quando ele volta.
//
// **No Docker ele SAI, e o `restart: unless-stopped` do compose o sobe de
// novo** -- é o `restart frontend` do atalho, o caminho que já funcionava. O
// `server.restart()` do Vite 4 fecha o servidor ANTES de criar o novo, e foi
// medido: se a troca cai no meio da pré-otimização das dependências, o novo
// nunca sobe, e o processo fica vivo sem ouvir a porta -- o painel fora do ar
// sem uma linha de erro. Fora do Docker não há quem suba o processo de novo;
// ali fica o `server.restart()`, com quem roda o `npm run dev` olhando.
//
// `fs.watchFile` e não o vigia do Vite: é o `stat` de um arquivo só, a cada
// 2 s, e enxerga a escrita de OUTRO container no mesmo bind mount -- que é
// exatamente o evento que não atravessa.
const MARCA_DE_REINICIO = fileURLToPath(new URL('./.reiniciar-painel', import.meta.url))
const noDocker = fs.existsSync('/.dockerenv')

function reiniciarQuandoOMotorSeAtualizar() {
  return {
    name: 'reiniciar-quando-o-motor-se-atualizar',
    apply: 'serve',
    configureServer(server) {
      const { logger } = server.config
      const aoMudar = (atual, anterior) => {
        if (!atual.mtimeMs || atual.mtimeMs === anterior.mtimeMs) return
        if (noDocker) {
          logger.info('o motor se atualizou pelo site: o painel sai e o Docker o sobe de novo', { timestamp: true })
          setTimeout(() => process.exit(0), 100)
          return
        }
        logger.info('o motor se atualizou pelo site: reiniciando o painel', { timestamp: true })
        server.restart().catch((e) => logger.error(`o painel não reiniciou: ${e}`))
      }
      fs.watchFile(MARCA_DE_REINICIO, { interval: 2000 }, aoMudar)
      // O `restart` cria outro servidor, que registra o próprio vigia.
      server.httpServer?.once('close', () => fs.unwatchFile(MARCA_DE_REINICIO, aoMudar))
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), reiniciarQuandoOMotorSeAtualizar()],
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
