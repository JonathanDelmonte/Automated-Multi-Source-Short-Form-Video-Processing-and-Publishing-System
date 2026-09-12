# Plano de ação — início do desenvolvimento

**Repositório:** `Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System`
**Branch de desenvolvimento:** `claude/loving-fermat-c84xtd`
**Data:** 12 de setembro de 2026
**Base:** `docs/PLANO-TECNICO.md` v2, corrigido por `docs/AUDITORIA-VERIFICACAO.md`

Este documento converte o Plano Técnico em sequência executável. O Plano Técnico
decide *o que* e *por quê*; este decide *em que ordem*, *com qual critério de pronto*
e *onde o plano original precisava de ajuste*.

---

## Estado atual

| Item | Situação |
|---|---|
| Repositório | fork do `openshorts` incorporado — 420 commits do upstream + planejamento |
| Licença | MIT limpo. `cloud/` removido (ADR-001) |
| Fase | **Fase 0 e Fase 0.5 completas em código.** Próximo: Fase 1 — ingestão |

Ambiente local verificado: Python 3.11.15, Node 22, Docker 29.3, PostgreSQL 16,
Redis 7, `uv`, `poetry`. **`ffmpeg`, `ffprobe` e `yt-dlp` ausentes** — vêm na imagem
do `docker compose` do fork, então não bloqueiam a Fase 0, mas bloqueiam qualquer
execução fora de container. O `openshorts` pede 8GB+ de RAM.

---

## O que a verificação mudou no plano

Detalhe e fontes em `docs/AUDITORIA-VERIFICACAO.md`. Em uma linha cada:

1. **A base não é MIT puro.** O diretório `cloud/` do `openshorts` está sob licença
   comercial que proíbe oferta como serviço hospedado pago. → apagar no primeiro
   commit (ADR-001).
2. **`clippyme` é fork do `openshorts`.** A aquisição mais valiosa do plano — compor
   na hora do download — vem por `git diff`, não por reescrita. → Fase 2 cai de ~2
   semanas para ~1 (ADR-002).
3. **O YOLOv8 já está dentro.** A "decisão em aberto" sobre AGPL chegou depois do
   fato. → isolar atrás de interface, MediaPipe como padrão (ADR-003).
4. **O Groq tem teto de 100k tokens/dia**, ausente da tabela do §3. Uma live de 4h
   consome 60–75% do orçamento diário. → o pré-filtro heurístico deixa de ser
   opcional (ADR-004) e a cascata passa a ordenar por duração da fonte (ADR-005).
5. **Falta uma etapa no roadmap.** O §7 exige `tenant_id` desde o primeiro commit; o
   §9 põe multi-tenancy na Fase 4, depois de três fases criando tabelas. → Fase 0.5
   (ADR-008).

Das quatro decisões em aberto do §10, três foram fechadas com dado (ADR-003, 004,
006) e uma segue aberta por escolha, com a parte estrutural resolvida (ADR-007).

---

## Correção de sequenciamento

O roadmap do §9 tem uma inversão que custa caro se seguida à risca:

```
§9 original:   Fase 0 ──► Fase 1 ──► Fase 2 ──► Fase 3 ──► Fase 4
               fork       ingestão   template   publisher  multi-tenancy
                          +tabelas   +tabelas   +tabelas   ◄── tenant_id chega aqui

corrigido:     Fase 0 ──► Fase 0.5 ──► Fase 1 ──► Fase 2 ──► Fase 3 ──► Fase 4
               fork       tenant_id    ingestão   template   publisher  auth
                          no schema    +tabelas   +tabelas   +tabelas
                                       └── já nascem com tenant_id ──┘
```

O §7 do plano já diz o porquê: "adicionar auth sobre um schema que já tem tenant é um
sábado de trabalho; adicionar tenant sobre um schema que não tem é uma migração que
quebra tudo". A Fase 0.5 custa 2–3 dias e é paga pela semana que o ADR-002 economiza
na Fase 2. O cronograma total não muda.

---

## Fase 0 — fork rodando, zero código novo

**Duração:** ~1 semana · **Objetivo do §9:** ler o código enquanto ele roda e
descobrir onde cada estágio mora.

### Antes de começar

Reconfirmar os limites de free tier dos provedores de LLM — o próprio §3 manda
("confirme antes de codar, isso muda toda hora"), e a auditoria já encontrou uma
tabela incompleta. Verificar Groq, Google AI Studio e Cerebras: RPM, requisições/dia
e **tokens/dia**, que é a coluna que faltava.

### 0.1 — Fork e higiene de licença · meio dia · ✅ CONCLUÍDA

O repositório de destino já existe e está vazio, então o fork entra como histórico
de upstream em vez de repositório separado. Isso é o que preserva o ativo que
justifica o fork: as correções futuras de terceiros chegam por `git fetch`.

```bash
git remote add upstream https://github.com/mutonby/openshorts.git
git fetch upstream
git merge --allow-unrelated-histories upstream/main

git rm -r cloud/          # ADR-001 — licença comercial, incompatível com SaaS
```

Criar o `NOTICE` creditando `openshorts`, seu upstream original
`kamilstanuch/Autocrop-vertical`, e os doadores previstos no §2. Registrar ali a
remoção do `cloud/` e o motivo.

**Pronto quando:** `cloud/` não existe, `NOTICE` existe, `git log` mostra o histórico
do upstream, e `git fetch upstream` traz atualizações.

**Resultado.** Os quatro critérios atendidos. A remoção foi maior que o previsto:
além do `cloud/` (25 arquivos), saíram `requirements-billing.txt`,
`docker-compose.cloud.yml`, `alembic/` e `alembic.ini` — todos exclusivos do modo pago
— e o `Dockerfile` foi corrigido, porque instalava o requirements de billing em toda
build.

O núcleo não quebrou: o upstream já isolava o modo pago atrás da flag
`BILLING_ENABLED`, falsa por padrão, com os 28 imports de `cloud` todos locais e
guardados. A guarda agora levanta erro explicativo em vez de `ImportError`, para que a
decisão não seja desfeita por uma variável de ambiente.

Um achado com efeito na Fase 0.5: **não há banco de dados no caminho self-host** — todo
o ORM pertencia ao módulo comercial. Ver ADR-008.

### 0.2 — Subir · 1 dia · ✅ CONCLUÍDA (com ressalva de ambiente)

`docker compose up` e nada mais. Sem alterar código. Percorrer a UI e mapear onde
mora cada um dos sete estágios do §4 — este é o entregável real da fase, mesmo que
não seja um arquivo.

**Pronto quando:** UI carrega, healthcheck verde, e existe uma nota própria dizendo
em que arquivo mora cada estágio de 01 a 07.

**Resultado.** O mapa dos estágios está em `docs/MAPA-DOS-ESTAGIOS.md` — o entregável
real da fase. UI e healthcheck verificados, mas **não por `docker compose`**.

> **Ressalva de ambiente.** O `docker compose up` não roda no container remoto desta
> sessão: o gateway de rede responde `403` de política ao CDN de blobs do Docker Hub
> (`production.cloudfront.docker.com`), então nem a imagem base `python:3.11-slim`
> baixa. O README do proxy lista esse caso como "report, do not work around". **Isso
> não é defeito do fork** — resta executar `docker compose up --build` na sua máquina,
> e é o único critério da fase que não pôde ser fechado aqui.

Como `pypi.org` e `registry.npmjs.org` têm acesso direto, a verificação foi feita
nativamente, e o próprio `ci.yml` do upstream mostra que esse é um caminho legítimo:
ele instala deliberadamente um conjunto leve, **sem** torch, ultralytics, mediapipe ou
faster-whisper, porque os módulos de pipeline os importam de forma lazy atrás dos
feature gates.

| Verificação | Resultado |
|---|---|
| `app.py` importa | OK — 60 rotas, `BILLING_ENABLED: False` |
| `GET /health` | `200 {"status":"ok"}` |
| `GET /health/ready` | `200 {"status":"ready"}` |
| `GET /api/config` | `200` · `billingEnabled: false` |
| UI (vite dev) | `200`, título servido |
| UI → API pelo proxy do vite | `200` |
| `npm run build` | OK — build em 7,8 s |
| `pytest tests/` | **596 passaram, 17 skipped, 0 falhas** |

Os dois pontos que pareciam problema e não são:

- **O proxy do vite dava `500`** porque tem como alvo padrão `http://backend:8000`, o
  nome do serviço no compose. Com `VITE_PROXY_TARGET=http://localhost:8000`, que o
  próprio `vite.config.js` documenta, responde `200`.
- **`npm run lint` acusa 10 erros**, todos herdados e em arquivos que nunca toquei
  (`public/op1.js` — um blob minificado de analytics — mais `Legal.jsx`,
  `PricingPage.jsx` e `lib/consent.js`). **A CI não roda lint:** o `ci.yml` roda
  `pytest tests/ -v`, `npm ci` e `npm run build`, e os dois jobs ficariam verdes neste
  commit. Note que quatro dos cinco arquivos pertencem à superfície comercial e de
  marketing que este fork está descartando, então tendem a sair sozinhos adiante.

A suíte verde é a validação prática da Fase 0.1: a remoção do `cloud/` não quebrou o
que ficou.

### 0.3 — Extirpar as dependências pagas · 1 dia · ✅ CONCLUÍDA

Conforme a tabela do §2. Remover, não desativar:

| Remover | Por quê | Substituto |
|---|---|---|
| Módulo fal.ai inteiro (Flux, Hailuo, VEED, Kling) | pago; é o módulo de AI UGC com atores sintéticos, fora do escopo | nenhum — escopo removido |
| ElevenLabs | pago | `edge-tts` quando/se TTS for usado |
| Upload-Post | 10 uploads grátis/mês contra ~90/mês necessários | camada `Publisher` própria, Fase 3 |
| AWS S3 | pago acima do free tier | disco local |

Ao remover o Upload-Post, deixar o ponto de chamada explícito com um erro claro em
vez de apagar em silêncio — é ali que a interface `Publisher` do §6 vai encaixar na
Fase 3.

**Pronto quando:** busca por `fal`, `elevenlabs`, `upload-post` e `boto3` não retorna
nada em caminho de código ativo, e a aplicação sobe com **zero** chaves de API paga
configuradas.

**Alvos localizados na Fase 0.2:**

| Alvo | Onde | Cuidado |
|---|---|---|
| fal.ai + ElevenLabs | `saasshorts.py` — o módulo de UGC com atores sintéticos | fora do escopo do §2; remover inteiro |
| Upload-Post | `app.py:4655`, com `resolve_upload_post` em `app.py:166` | é o ponto onde o `Publisher` da Fase 3 encaixa |
| AWS S3 | `s3_uploader.py`, importado **no topo** do `app.py` (linha 31) | import de módulo, não lazy: editar a linha 31 e os seis nomes que ela traz |
| Mídia de demo | `churchil_queen_vertical.gif` (63 MB) e outros ~85 MB | o GitHub já avisa no push; todo clone carrega |

**Resultado.** Os dois critérios atendidos: a busca não retorna nada em caminho de
código ativo e a aplicação sobe com zero chaves pagas. Saiu mais do que a tabela
acima previa, porque nenhuma das quatro dependências estava isolada.

| Onde | Antes | Depois |
|---|---|---|
| `app.py` | 6221 l. · 60 rotas | 4947 l. · **38 rotas** |
| `dashboard/src/App.jsx` | 2184 l. | 1750 l. |
| `ResultCard.jsx` | 1169 l. | 838 l. |
| `ThumbnailStudio.jsx` | 1243 l. | 1036 l. |
| Módulos Python | — | 3 removidos (2226 l.) |
| Componentes React | — | 6 removidos (~2150 l.) |
| Endpoints | — | 22 removidos |
| Ferramentas MCP | 7 | 6 (`publish_clip` saiu) |

Três coisas que valem registro:

**A remoção por regex foi descartada a meio caminho.** Os endpoints que devolvem
`HTMLResponse` têm `@media` em coluna zero dentro da f-string, e qualquer varredura
por linha lê isso como decorador e corta o bloco no meio — `/video/{video_id}`
apareceu como 53 linhas quando tem 80. Refeita sobre a AST, que dá os limites exatos
de cada nó de topo. A lição vale para as próximas fases: este código tem HTML embutido
em Python e JSX de mil linhas, então edição estrutural pede parser, não `sed`.

**Duas quebras que nem o build nem o lint pegam.** Um botão "Next: Publish" continuava
navegando para o passo 4 do Thumbnail Studio, que deixou de existir — levaria a uma
tela vazia. E `skills/openshorts/`, que descreve a API para agentes, documentava
`publish_clip` e `/api/social/*`: não é marketing, é contrato, e um agente seguindo
aquilo chamaria 404. Ambos corrigidos. O sinal automatizado cobre referência quebrada,
não navegação para lugar nenhum.

**Uma funcionalidade foi preservada em vez de cair por tabela.** O botão "create clips
from this video" vivia dentro do passo de publicação, atrás do sucesso do upload.
Removido o passo, ele seria perdido junto — sem ter relação alguma com dependência
paga. Foi re-alojado no passo de descrição, que agora é o último.

> **Pendente, e fora do escopo desta fase:** a superfície de marketing e SEO
> (`Landing.jsx`, `PricingPage.jsx`, `PricingSection.jsx`, `dashboard/seo/*`,
> `index.html`) mais `examples/n8n/`, `ops/` e `design.md` ainda anunciam dublagem,
> UGC e publicação automática. É *copy*, não caminho de código — e a decisão de fundo
> é maior que reescrever texto. Ver `DECISOES.md`, ADR-009.

### 0.4 — Cascata de LLM gratuita · 1–2 dias · ✅ CONCLUÍDA

O `openshorts` chama o Gemini direto no código. Extrair para o `Protocol
LLMProvider` do §3 e implementar a ordenação por duração de fonte do ADR-005.

Esta é a única parte da Fase 0 que escreve código próprio, e é inevitável: o §9 manda
"configurar a cascata de LLM grátis", e não há cascata configurável no fork — há uma
chamada chumbada. Manter mínimo: a interface, dois provedores (Groq e Gemini Flash) e
o Ollama como piso. Cerebras pode esperar.

**Pronto quando:** um vídeo atravessa o pipeline inteiro com zero chave paga, e
desligar o provedor primário faz o secundário assumir sem intervenção.

**Resultado.** `llm_cascade.py` (~350 l.) + 31 testes. A cascata decide **ordem e
orçamento**, e nada mais — não importa o SDK do Google nem cliente HTTP. Quem sabe
falar com cada provedor continua sendo o `main.py`, que já tinha os dois caminhos, e
`_run_gemini_stage` segue sendo *uma tentativa contra um provedor*, com o backoff que
já tinha. Confirmado o que a Fase 0.2 previu: `llm_backend.py` já abstraía o
endpoint, então o trabalho foi a lista ordenada, o `available()` e a escolha por
duração.

Roteamento verificado pelo `main.py`, com a chamada ao provedor injetada:

| Cenário | Tentou | Lote |
|---|---|---|
| Fonte curta, Groq + Gemini | `groq` | 6 janelas |
| Fonte longa, 4h | `gemini` | 8 janelas |
| **Primário derrubado** | `groq` → **`gemini` assumiu** | 6 |
| Só Groq, sem chave do Google | `groq` | 6 |
| Nenhum provedor | caminho antigo | 8 |

Duas integrações que faltavam e teriam quebrado na prática, encontradas ao ligar:

- **`get_viral_clips` abortava exigindo `GEMINI_API_KEY`.** Com uma cascata de Groq
  só, `llm_backend.active()` é falso, então o código caía no `else` que exige a chave
  do Google e devolvia `None`. O cliente do Gemini agora é construído só se houver
  chave.
- **`/api/process` rejeitava a requisição**, e o painel escondia a opção, pelo mesmo
  motivo. Ambos passam a aceitar a cascata: com `GROQ_API_KEY`, `/api/config` devolve
  `localLlm: cascade / llama-3.3-70b-versatile` e o painel para de pedir chave do
  Google.

**Um bug de desenho que os testes pegaram:** o Ollama tinha default para
`http://localhost:11434/v1`, então entrava em *toda* cascata mesmo sem nada
escutando, e cada job gastaria uma tentativa de conexão para descobrir. Virou
opt-in — detalhe em ADR-005.

> **Não verificado aqui:** uma chamada HTTP real ao Groq (não há chave neste
> ambiente) e um vídeo de verdade atravessando o pipeline, que precisa da stack de ML
> e do `ffmpeg`. Está provado o roteamento, o orçamento e a degradação; a chamada real
> é o primeiro teste a fazer na sua máquina, junto do `docker compose` que a Fase 0.2
> deixou pendente.

**Achado para a Fase 1, sobre o ADR-003:** `main.py:88` não só importa o YOLOv8 —
ele **instancia o modelo em nível de módulo** (`model = YOLO(...)`), em todo job,
antes de qualquer decisão. Então o passivo AGPL não está atrás de flag nenhuma hoje,
e o ADR-003 exige tornar esse import lazy, não só adicionar um toggle. Apareceu ao
stubar dependências para verificar a ligação.

### 0.5 — Instrumentar antes de otimizar · meio dia · ✅ CONCLUÍDA

Registrar por job, no campo `timings_json` que o §7 já prevê no schema: tokens por
chamada, chamadas por estágio, tempo de parede por estágio, e duração falada da fonte.

Meia hora de trabalho que converte a Fase 5 e o ADR-004 de opinião em medição. Sem
isso, calibrar o pré-filtro na Fase 1 é achismo, e a pergunta "quanto custou aquele
vídeo de 40 min?" não tem resposta.

**Pronto quando:** um job processado responde, por número, quantos tokens e quantos
segundos cada estágio custou.

**Resultado.** `job_metrics.py` + 22 testes. O que o upstream tinha era fragmentado e
não sobrevivia ao job: `stage_seconds` só de `detect`/`write` dentro do laço de
reframe, e prints soltos de download. Agora há um coletor por job, com o resumo no
stdout — que *é* o log que o `/api/status` devolve — e o dict no sidecar
`<base>.timings.json`, **com a mesma forma que a coluna `jobs.timings_json` do §7 vai
ter**. Quando a tabela nascer, é um INSERT lendo este dict.

```
📊 Custo deste job:
   01_ingest               0.1s
   03_transcribe           0.1s
   04_detect               0.0s    4 chamada(s)    73600 tokens  [gemini]
   05_06_render            0.1s
   TOTAL                   0.3s    4 chamada(s)    73600 tokens
   90.0 min de fala → 818 tokens/min falado
```

Duas decisões:

**A atribuição de tokens a estágio é automática.** O coletor mantém a pilha de
estágios abertos, então `add_llm` credita a chamada a quem está por cima. É o que
permitiu instrumentar o LLM num lugar só — `_run_llm_stage` — em vez de em cada sítio
de chamada.

**Mede duração falada, não duração do arquivo.** O §4 é explícito: "o custo de
processar cresce com a duração falada, não com o tamanho do arquivo". `tokens por
minuto falado` é o número que a Fase 1 vai usar para calibrar o pré-filtro, e uma live
de 4h com metade de silêncio custa metade.

**Uma quebra que eu causei e os testes pegaram:** inseri o helper `_job_timings` entre
o decorador `@app.get("/api/status/{job_id}")` e a função `get_status`, então o
decorador passou a registrar o *helper* como handler da rota — `/api/status` de um job
inexistente devolvia 200 com corpo nulo em vez de 404. Seis testes de MCP falharam e o
meu próprio `curl` confirmou. Helper movido para antes do decorador.

> **Nota sobre os números acima:** são de uma simulação, com custo por chamada
> inventado. O que está provado é que a forma existe e reporta; o custo real de um
> vídeo é o que falta medir, e é justamente o que este bloco passa a permitir.

### Critério de saída da Fase 0

O do §9, mais uma condição:

> Um corte vertical legendado sai na sua máquina, sem nenhuma chave de API paga
> configurada — **e existe medição de tokens e tempo por estágio de um vídeo real.**

**Estado: completa em código, pendente de uma execução real.** Os cinco blocos estão
feitos e verificados no que este ambiente permite: 637 testes passando, backend e
painel subindo, build limpo, nenhuma dependência paga em caminho ativo, cascata
roteando e degradando, e a medição reportando. O que falta é fora do meu alcance aqui:

| Pendente | Por quê |
|---|---|
| `docker compose up --build` | gateway deste container nega o CDN do Docker Hub (403 de política) |
| Uma chamada HTTP real ao Groq | não há chave neste ambiente |
| Um vídeo de verdade atravessando o pipeline | precisa da stack de ML (torch, ~2GB) e do `ffmpeg` |

São os três primeiros testes a fazer na sua máquina, e juntos fecham o critério.

> **Cuidado com o nome:** o **bloco 0.5** (instrumentar, acima) é parte da Fase 0. A
> **Fase 0.5** (o schema com `tenant_id`, abaixo) é outra coisa, inserida por ADR-008.
> A colisão de numeração é minha; mantive por já estar referenciada nos commits.

---

## Fase 0.5 — `tenant_id` no schema · 3–5 dias · ✅ CONCLUÍDA

Introduzida por ADR-008; não existe no §9.

**Revisada após a Fase 0.1.** A premissa era migrar um schema herdado. Não há schema
herdado: `sqlalchemy`, `asyncpg` e `alembic` estavam só no `requirements-billing.txt`,
o Postgres só no compose de cloud, e todo o ORM em `cloud.models`. A camada de
persistência inteira era do módulo comercial e saiu com ele.

O efeito líquido é favorável — não existe migração que quebre, e o `tenant_id` entra na
primeira tabela escrita, que é exatamente o que o §7 pede. Mas a fase deixa de ser
adaptação e passa a ser autoria: escolher a stack (o §3 admite PostgreSQL ou SQLite
local), inicializar alembic do zero, escrever as nove tabelas do §7 e ligar ao estado
de job que o pipeline mantém hoje por outro meio.

`credentials_ref` aponta para cofre, nunca guarda o token na linha. **Sem auth** — isso
segue na Fase 4, conforme o plano.

A incerteza restante é onde o caminho self-host guarda estado de job hoje.
Dimensionar isso é entregável da Fase 0.2, que manda ler o código enquanto ele roda —
outra razão para 0.2 vir antes.

**Pronto quando:** toda tabela tem `tenant_id`, o seed cria um tenant fixo, e nenhuma
consulta do código ignora a coluna.

**Resultado.** As nove tabelas do §7 em `db_models.py`, conexão e escopo em `db.py`,
seed em `db_seed.py`, alembic do zero, e 32 testes. Os três critérios atendidos.

| Peça | Escolha |
|---|---|
| ORM | SQLAlchemy 2.x, async — o `app.py` é async e consulta bloqueante trava o event loop |
| Banco | SQLite em `data/cortes.db`; `DATABASE_URL` aponta para Postgres |
| Migração | alembic do zero, com `render_as_batch` (o SQLite não tem `ALTER TABLE` completo) |
| Tenant | fixo, `00000000-…-0001`, criado pelo seed. Auth segue na Fase 4 |

**O terceiro critério virou estrutura, não disciplina.** "Nenhuma consulta ignora a
coluna" não se consegue prometendo; se consegue com duas peças: `db.tenant()`, que
filtra e preenche `tenant_id` sozinho e *recusa* objeto de outro tenant; e um teste que
quebra se um modelo novo nascer sem a coluna — o mesmo padrão que o upstream usava em
`test_account_erasure.py`.

**Isolamento garantido pelo banco.** Usei chave estrangeira **composta** com
`tenant_id`: `(tenant_id, job_id) → jobs(tenant_id, id)`. Um corte referenciar o job de
outro tenant deixa de ser "bug improvável" e passa a ser `IntegrityError`.

**E foi aí que achei um vazamento de verdade.** O SQLite ignora FK por padrão, e meu
listener de `PRAGMA foreign_keys=ON` testava o tipo da conexão. Com aiosqlite o que
chega ao evento é um `AsyncAdapt_aiosqlite_connection` da própria SQLAlchemy — a
checagem dava `False`, o pragma nunca rodava, e o teste mostrou **o banco aceitando um
job do tenant B apontando para a fonte do tenant A**. As FKs compostas eram decoração.
Corrigido ligando o listener ao engine e decidindo pelo dialeto. Se eu tivesse só
escrito o schema e seguido, isso teria ficado lá — parecendo correto.

**Uma precaução que não estava no plano:** o banco mora em `data/`, não em `output/`.
O `output/` é barrido pela limpeza por idade e pelo teto de tamanho; hoje as duas só
apagam diretórios, então um arquivo sobreviveria — mas por um detalhe de código
herdado que um `git fetch upstream` pode mudar. Melhor não estar no caminho.

Comandos: `alembic upgrade head` (produção, sabe evoluir banco com dados) ou
`python db_seed.py` (cria o schema e semeia). Verificado que a migração produz
**exatamente** o mesmo schema que o metadata — há um teste comparando os dois, porque
sem ele `create_all` (usado em teste) e `alembic upgrade` (usado em produção) divergem
em silêncio e o bug aparece no deploy.

> **Nada do pipeline usa o banco ainda**, e é de propósito: as tabelas `sources` e
> `jobs` passam a ser escritas na Fase 1, quando o `SourceAdapter` nascer. O que esta
> fase entrega é o lugar, com o `tenant_id` já dentro — que era exatamente o ponto de
> fazê-la antes das fases que criam tabelas.

---

## Fases 1 a 5 — ajustes sobre o §9

### Fase 1 — camada de ingestão · 1–2 semanas · ◀ PRÓXIMA

Conforme o §9, com duas adições:

- **O pré-filtro heurístico entra aqui** (ADR-004), junto com o adapter de Twitch live
  que cria a necessidade. Energia de áudio, silêncio prolongado, mudança de falante,
  densidade de palavras/segundo. É a otimização de maior impacto do §3 e, com o teto
  de 100k tokens/dia do Groq, é o que torna a live de 4h processável.
- **O tracker vai para trás de interface** (ADR-003), aproveitando que a fase já
  estabelece o padrão com `SourceAdapter`.

Manter a ordem do §9 — começar pela Twitch, porque live longa é o pior caso e testar
o pior caso cedo evita retrabalho. É também o caso que valida o pré-filtro.

A regra do §4 — *o áudio dirige, o vídeo obedece* — é o núcleo desta fase: extração
de áudio 16k mono antes de tudo, `-ss` antes do `-i` no `ffmpeg`, upload grande
gravado em disco por streaming e nunca em memória. O limite de 2GB do fork (§2) sai
aqui; o alvo é 10GB.

**Pronto quando:** os quatro tipos de link entram pelo mesmo endpoint, **e** uma live
de 4h é processada sem estourar o orçamento diário de tokens.

### Fase 2 — motor de template · ~1 semana

Reduzida de ~2 semanas por ADR-002. Em vez de escrever o motor, trazer do `clippyme`
por `git diff` com ancestral comum: o compositor de segunda passada e os seis presets
de legenda, filtrando Deepgram e ElevenLabs Scribe.

O que continua sendo trabalho próprio: o schema JSON do §5, o CRUD no painel, e o
preview de 3 segundos. Travar as três decisões do §5 — `safeArea` respeitada (12% topo,
18% base), template aplicado no download e não no render, preview antes de queimar GPU.

**Pronto quando:** trocar de template não reprocessa o vídeo.

### Fase 3 — camada Publisher · ~2 semanas

Sem alteração em relação ao §9. Interface, resolvedor, driver `manual` e driver
`youtube-api` com contador de quota. `aggregator` e `browser` como stub lançando
`NotImplemented`.

Dois pontos do plano que merecem não ser esquecidos por parecerem secundários:

- O driver `manual` é o **default da fase 1** e não é a versão capada — ele automatiza
  90% do trabalho. Entregar **pacote por dia**: os cortes mais um arquivo de legenda
  pronto para colar.
- O `browser` nasce desligado e **fora da cascata de fallback automático** (§1). A
  punição por detecção não é erro HTTP tratável — é shadowban ou perda da conta, e num
  projeto de cortes a conta é o ativo.

O contador de quota tem número exato para respeitar: 1.600 unidades por
`videos.insert` contra 10.000/dia, ou seja 6 uploads/dia, e a conta do §1 confere —
3 vídeos/dia gastam 4.800 e sobra metade para listagem e reprocessamento.

**Pronto quando:** os cortes do dia vão para o YouTube sozinhos e o resto cai na fila
manual.

### Fase 4 — auth e multi-tenancy real · ~1,5 semana

Reduzida de ~2 semanas porque o schema já está pronto desde a Fase 0.5 — é exatamente
o "sábado de trabalho" que o §7 prevê quando o tenant já existe. Sobra auth, tenant
vindo da sessão, fila isolada por tenant e o agendador.

O agendador nasce com jitter (ADR-007). Os números — quantos por dia, quais janelas,
espaçamento mínimo — são a decisão em aberto §10.2, a ser tomada aqui com informação.

Aqui também sai o aviso de LAN confiável que o `clippyme` documenta e que vale para o
fork: antes desta fase, não expor à internet pública.

**Pronto quando:** uma segunda conta usa o sistema sem ver nada da primeira.

### Fase 5 — calibrar a detecção com dados reais · contínuo

Sem alteração. A tabela `metrics` do §7 — "parece supérflua agora e é a tabela mais
valiosa do projeto". É ela que permite trocar a rubrica do LLM por retenção medida, e
fechar o ADR-006 com dado. A instrumentação da Fase 0.5 é o que alimenta isso.

---

## Cronograma

| Fase | Original §9 | Ajustado | Delta |
|---|---|---|---|
| 0 — fork rodando | ~1 sem | ~1 sem | — |
| 0.5 — `tenant_id` no schema | *(ausente)* | 3–5 dias | **+5 dias** |
| 1 — ingestão + pré-filtro | 1–2 sem | 1–2 sem | — |
| 2 — motor de template | ~2 sem | ~1 sem | **−1 sem** |
| 3 — Publisher | ~2 sem | ~2 sem | — |
| 4 — auth e multi-tenancy | ~2 sem | ~1,5 sem | **−0,5 sem** |
| 5 — calibração | contínuo | contínuo | — |
| **Total até Fase 4** | **~8 sem** | **~7,5 sem** | a correção se paga |

A Fase 0.5, que é a que remove o maior risco do plano, ainda sai de graça: cresceu de
3 para 5 dias com o achado da Fase 0.1, e continua coberta pela semana que a descoberta
sobre o `clippyme` economiza na Fase 2.

---

## Riscos a monitorar

| Risco | Sinal de alerta | Resposta preparada |
|---|---|---|
| Limites de free tier mudam sem aviso | `quotaExceeded` ou 429 antes do esperado | cascata do ADR-005 já prevê degradação; Ollama local é o piso que nunca falha |
| Gemini free tier sai da cascata (privacidade, se virar SaaS) | decisão de virar SaaS com conteúdo de cliente | é o primário das fontes longas (ADR-005) — mapear substituto **antes** da virada |
| ToS do YouTube quanto ao `yt-dlp` (§8) | — | risco aceito e registrado na fase pessoal; na virada SaaS, OAuth do canal próprio ou só upload direto |
| VOD da Twitch expira em 7–60 dias (§4) | fonte desaparece antes do processamento | ingerir cedo; não tratar VOD como armazenamento |
| Passivo AGPL do YOLOv8 volta pelo `clippyme` | cherry-pick da Fase 2 trazendo Ultralytics | ADR-003 mantém MediaPipe como padrão; revisar o diff antes de aplicar |
| Fork upstream divergir muito | conflitos crescentes em `git fetch upstream` | manter as alterações próprias atrás das interfaces do §4/§6, que é o que o plano já faz |

---

## Documentos

| Arquivo | Papel |
|---|---|
| `docs/PLANO-TECNICO.md` | documento de origem, v2 — o *que* e o *porquê*. Preservado íntegro. |
| `docs/AUDITORIA-VERIFICACAO.md` | o que a verificação confirmou e o que divergiu, com fontes |
| `docs/DECISOES.md` | ADR-001 a 008 — decisões travadas e o que faria revê-las |
| `docs/PLANO-DE-ACAO.md` | este — ordem de execução e critérios de pronto |
