// A versão do SITE, gravada no build e mostrada em Configurações → Versões
// (25-set-2026). O programa de cada computador diz a dele pelo `/api/config`;
// esta é a da tela, que o Cloudflare publica a cada envio para a `main`.
//
// A versão é a contagem de commits, a mesma regra do motor
// (`versao_do_motor.py`), então os dois números se comparam. E vale só com o
// histórico inteiro: num clone raso, `git rev-list --count` devolve a
// PROFUNDIDADE do clone -- "1" no lugar de "546", sem erro nenhum. O build do
// Cloudflare pode clonar raso, e ali (`WORKERS_CI`) se tenta trazer o
// histórico, só os commits e sem os arquivos (`--filter=blob:none`: medido,
// 2 s contra o GitHub). Não deu, fica sem número: melhor nenhum que um errado.
// O commit e a data saem sempre.
import { execSync } from 'node:child_process'
import { pathToFileURL } from 'node:url'

function git(args, cwd, timeout = 15000) {
  try {
    // `safe.directory`: no build e no container a pasta pode ser de outro
    // dono, e sem isto o git se recusa a ler o repositório. Entre aspas para o
    // shell não tentar expandir o `*` como nome de arquivo.
    const saida = execSync(`git -c "safe.directory=*" ${args}`, {
      cwd, timeout, stdio: ['ignore', 'pipe', 'ignore'],
    })
    return saida.toString().trim() || null
  } catch {
    return null
  }
}

export function versaoDoSite(cwd = process.cwd(), env = process.env) {
  let raso = git('rev-parse --is-shallow-repository', cwd)
  if (raso === 'true' && env.WORKERS_CI) {
    git('fetch --unshallow --filter=blob:none --quiet', cwd, 60000)
    raso = git('rev-parse --is-shallow-repository', cwd)
  }
  let versao = null
  if (raso === 'false') {
    const contagem = git('rev-list --count HEAD', cwd)
    if (contagem && /^\d+$/.test(contagem)) versao = contagem
  }
  const commit = git('rev-parse --short=7 HEAD', cwd)
    || (env.WORKERS_CI_COMMIT_SHA || '').slice(0, 7) || null
  return { versao, commit, publicadoEm: new Date().toISOString() }
}

// `node versao-do-site.js [pasta]` imprime o que o build gravaria (é o que o
// teste roda, em clone raso e inteiro).
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(JSON.stringify(versaoDoSite(process.argv[2] || process.cwd())))
}
