# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Convencoes deste fork (precedem a orientacao do upstream, abaixo)

Este repositorio e um fork de OpenShorts. A secao "Project Overview" e as
seguintes descrevem o upstream e seguem validas para navegar o codigo, mas as
regras abaixo sao deste projeto e tem precedencia.

### Atribuicao de commits -- obrigatorio

Autor de todo commit: **Jonathan Delmonte <jonathanpdelmon@gmail.com>**.

Esse e o e-mail, sem excecao. E o que o GitHub usa para ligar o commit ao
perfil do autor: com qualquer outro, o commit aparece como texto simples, sem
foto e sem link para a conta.

Nao adicionar trailers de co-autoria de assistente (`Co-Authored-By:` de
Claude, `Claude-Session:` ou equivalentes) em mensagens de commit, descricoes
de pull request ou qualquer artefato versionado. O trabalho e creditado ao
autor do projeto.

### Para onde se empurra -- e para onde NAO

`origin` e **o repositorio do autor**:
`JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System`.
Todo push vai para la, na branch `claude/loving-fermat-c84xtd`.

`upstream` e `mutonby/openshorts`, o projeto de terceiros que serviu de base.
**E somente leitura.** A URL de push dele foi desabilitada de proposito
(`git remote set-url --push upstream DISABLED_no_push_to_upstream`), para que
nem um comando errado consiga enviar nada para o repositorio deles. Nunca
reabilitar, nunca abrir pull request contra eles, nunca empurrar branch para
la. A relacao com o upstream e de uma via: `git fetch upstream` para receber
correcoes, e nada no sentido inverso.

Os 427 commits e os 9 contribuidores deste repositorio sao esperados: 420 vem
do historico do upstream, incorporado na Fase 0.1 para que as correcoes deles
cheguem por `git fetch` (ADR-001). O credito a eles esta no `NOTICE`.

### Idioma

Documentacao, mensagens de commit e comentarios novos em portugues. Codigo
herdado do upstream permanece como esta -- nao traduzir em massa.

### Onde esta o planejamento

| Arquivo | Papel |
|---|---|
| `docs/PLANO-DE-ACAO.md` | ponto de entrada: fases, ordem de execucao, critérios de pronto |
| `docs/PLANO-TECNICO.md` | documento de origem v2: arquitetura, o *que* e o *porque* |
| `docs/AUDITORIA-VERIFICACAO.md` | verificacao das premissas do plano, com fontes |
| `docs/DECISOES.md` | ADR-001 a 009 |
| `docs/OPORTUNIDADES.md` | o que a ferramenta faz alem do plano, o que o plano preve e ela nao faz, e o que preservar ao trocar o frontend |
| `docs/MAPA-DOS-ESTAGIOS.md` | onde mora cada estagio 01-07, e o desenho CLI+fila do upstream |
| `docs/COMO-EXECUTAR.md` | passo a passo para rodar na maquina do autor, com as armadilhas |
| `docs/upstream/README-openshorts.md` | README do upstream, preservado para consulta |

Antes de alterar arquitetura, ler `docs/DECISOES.md`. Varias escolhas que
parecem arbitrarias no codigo estao justificadas la.

### Divergencias deliberadas do upstream

- **`cloud/` foi removido** (ADR-001). Estava sob OpenShorts Commercial
  License, nao sob MIT. `BILLING_ENABLED=1` agora falha com erro explicito em
  `app.py` em vez de `ImportError` -- e intencional, nao um bug a consertar.
  Removidos junto: `requirements-billing.txt`, `docker-compose.cloud.yml`,
  `alembic/`, `alembic.ini`.
- **Schema proprio** (`db_models.py`, `db.py`, `db_seed.py`, `alembic/`, Fase
  0.5 concluida, ADR-008). Todo o ORM do upstream pertencia ao modulo comercial
  e saiu com ele, entao as nove tabelas da secao 7 nasceram escritas, com
  `tenant_id` em todas menos `tenants`. SQLAlchemy 2.x async; SQLite em
  `data/cortes.db` por padrao (FORA de `output/`, que e barrido pela limpeza) e
  Postgres por `DATABASE_URL`. Migracao: `alembic upgrade head`. Seed:
  `python db_seed.py`.
  - **Leia e escreva por `db.tenant()`**, nao por `db.session()`: ele filtra e
    preenche `tenant_id` sozinho e recusa objeto de outro tenant. Sessao crua e
    para quem precisa de SQL que o escopo nao cobre, e ai a responsabilidade e
    explicita.
  - **FK composta com `tenant_id`** em toda referencia entre tabelas, entao
    vazamento entre tenants e `IntegrityError`, nao bug improvavel. No SQLite
    isso depende de `PRAGMA foreign_keys=ON`, ligado por engine em `db.py` --
    nao desfazer: sem ele as FKs compostas sao decoracao (ja aconteceu).
  - `tests/test_db_schema.py` quebra se uma tabela nova nascer sem `tenant_id`.
  - **Auth e a Fase 4.** Ate la tudo pertence ao tenant fixo
    `00000000-0000-0000-0000-000000000001`, e nada do pipeline usa o banco
    ainda: `sources` e `jobs` passam a ser escritas na Fase 1.
- **MediaPipe e o tracking padrao** (ADR-003); YOLOv8 (AGPL-3.0) fica atras de
  flag desligada. **Ainda nao feito**: `main.py:88` instancia `YOLO(...)` em
  nivel de modulo, em todo job. Tornar isso lazy e trabalho da Fase 1.
- **Cascata de LLM gratuita** (`llm_cascade.py`, Fase 0.4 concluida, ADR-004 e
  ADR-005). O detector de momentos atravessa Groq / Gemini / Cerebras / Ollama
  em ordem que depende da duracao falada da fonte, com orcamento diario em
  `output/.llm_budget.json` (em disco porque o `main.py` e subprocesso novo a
  cada job). Provedor entra so com sua chave presente; o Ollama e opt-in via
  `OLLAMA_BASE_URL`. Sem nenhuma chave, o comportamento e o antigo. Variaveis
  documentadas no `.env.example`.
- **Custo por job instrumentado** (`job_metrics.py`, bloco 0.5 concluido). Um
  coletor por job mede tempo de parede e tokens por estagio, credita a chamada
  de LLM ao estagio aberto pela pilha (por isso o LLM e instrumentado num lugar
  so, `main._run_llm_stage`), e mede **duracao falada**, nao a do arquivo. O
  resumo vai para o stdout, que e o log que o `/api/status` devolve, e o dict
  para o sidecar `<base>.timings.json`, com a forma que a coluna
  `jobs.timings_json` da secao 7 vai ter.
- **Dependencias pagas removidas** (Fase 0.3 concluida). Sairam os modulos
  `saasshorts.py` (fal.ai), `translate.py` (ElevenLabs) e `s3_uploader.py`
  (AWS S3), 22 endpoints (`/api/translate`, `/api/social/*`,
  `/api/saasshorts/*`, `/api/thumbnail/publish*`, `/gallery`,
  `/video/{id}`), a ferramenta MCP `publish_clip` e, no painel, as abas
  AI Shorts e UGC Gallery, o modal de dublagem, o de publicacao e o de
  agendamento semanal. **As secoes do upstream abaixo descrevem features que
  nao existem mais neste fork** -- a lista de "Key Files", o pipeline de 11
  passos e a tabela de endpoints estao corrigidas, mas trate qualquer outra
  mencao a fal.ai, ElevenLabs, Upload-Post ou S3 como historica.
- **A superficie de marketing e SEO foi removida** (ADR-009, 13-set-2026).
  Sairam `Landing.jsx`, `PricingPage.jsx`, `PricingSection.jsx`, `Legal.jsx`,
  `dashboard/seo/`, o `vite-plugin-seo.js`, o `StarBanner` e a metade de
  marketing do `index.html`. **A porta 5175 agora abre a ferramenta**, sem
  landing e sem a marca `openshorts_skip_landing` no localStorage: o
  `main.jsx` responde `app` para todo hash que nao seja `#/account`,
  `#/oauth/authorize`, `#/deleted` ou `#/auth/`.
  - Saiu junto o que so servia a isso: o inicializador do OpenPanel no
    `index.html`, o `public/op1.js`, o `lib/consent.js` e o `CookieBanner`.
    **`lib/analytics.js` continua existindo como no-op explicito** -- ha 13
    chamadas a `track()` em quatro arquivos, e o cabecalho do modulo diz por
    que elas ficaram. Nao reintroduzir telemetria sem decisao consciente.
  - **Ficou de fora de proposito**: a UI de cobranca (`TrialGate`,
    `TopUpModal`, `PlanChoiceModal`, `UsageMeter`, `InvoicesCard`,
    `WatermarkModal`), inalcancavel via `billingEnabled` desde o ADR-001, e
    `examples/n8n/`, `ops/`, `design.md`. Candidatos ao proximo corte.
  - O que preservar ao trocar o frontend esta na Parte D de
    `docs/OPORTUNIDADES.md`: sao ~580 linhas (`src/tokens.css` com 53, o
    mapeamento em `tailwind.config.js`, as classes de `index.css` e os tres
    primitivos de `components/ui/`), nao as 4.800 de landing e pricing.

### Fluxo de git

Desenvolvimento em `claude/loving-fermat-c84xtd`. O upstream fica como remote
`upstream`; correcoes de terceiros chegam por `git fetch upstream` e merge --
por isso as alteracoes proprias ficam atras das interfaces (`SourceAdapter`,
`Publisher`, `FaceTracker`) em vez de espalhadas no codigo herdado.

---

## Project Overview

OpenShorts is an AI-powered vertical video generator that transforms long YouTube videos or local uploads into viral-ready short clips (9:16 format) for TikTok, Instagram Reels, and YouTube Shorts. Uses Google Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`, overridable with `GEMINI_MODEL`) for viral moment detection and title generation.

## Development Commands

### Local Development (Docker)
```bash
docker compose up --build   # Build and run full stack
```
- Backend: http://localhost:8000 (FastAPI/Uvicorn)
- Frontend: http://localhost:5175 (Vite proxies API calls to backend)

### Frontend Only (Dashboard)
```bash
cd dashboard
npm install
npm run dev       # Dev server with HMR (port 5173)
npm run build     # Production build
npm run lint      # ESLint (strict, --max-warnings 0)
```

### Backend Only
```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Architecture

### Core Processing Pipeline
1. **Ingest** - YouTube download (yt-dlp) or local upload
2. **Transcription** - faster-whisper with word-level timestamps
3. **Scene Detection** - PySceneDetect for segment boundaries
4. **AI Analysis** - Gemini identifies 3-15 viral moments (15-60 sec each)
5. **FFmpeg Extraction** - Precise clip cutting
6. **AI Cropping** - Vertical reframing with subject tracking
7. **Effects/Subtitles** - Optional AI-generated FFmpeg filters
8. **Hook Overlay** - Text overlays with styled fonts

(Os passos 9 a 11 do upstream -- dublagem ElevenLabs, backup em S3 e
distribuicao via Upload-Post -- foram removidos na Fase 0.3. A publicacao
propria entra na Fase 3.)

### Key Files
| File | Purpose |
|------|---------|
| `main.py` | Core video processing: transcription, scene detection, clip extraction, vertical reframing |
| `app.py` | FastAPI server with async job queue and REST endpoints |
| `editor.py` | Gemini AI integration for dynamic video effects (FFmpeg filter generation) |
| `hooks.py` | Hook text overlay generation with font rendering |
| `subtitles.py` | SRT generation, FFmpeg subtitle burning, and dubbed video transcription |
| `dashboard/src/App.jsx` | Main React component with state management |

### Sem superficie de SEO (ADR-009)

O upstream mantinha um gerador de SEO em tempo de build (`vite-plugin-seo.js`)
que injetava a home visivel a crawler dentro do `#root` e emitia as paginas
estaticas, o `sitemap.xml` e o `llms.txt`. **Removido inteiro.** Isto e uma
ferramenta self-hosted que atende em localhost: nao ha crawler para indexar, e
o que havia descrevia e apontava para o produto comercial do upstream.

Nao reintroduzir: nem `public/sitemap.xml`, nem meta de Open Graph com
`openshorts.app`, nem o fallback de landing no `#root`. Se um dia este projeto
tiver um site, ele nasce escrito para ele.

### Cómo se elige el layout

`POST /api/process` acepta `layouts`: una lista (JSON) o cadena separada por
comas con `auto`, `split`, `screencast`, `speaker_cut`, `punch_in` y `none`.
Cada nombre enciende su variable de entorno para **ese** trabajo
(`app.py:layout_env`); `none` apaga el picker aunque prod corra con
`AUTO_LAYOUT=1` (recorte simple y nada más). Sin `layouts` manda el env del
despliegue, que desde el 25-ago-2026 es `AUTO_LAYOUT=1`. El dashboard lo expone
en opciones avanzadas ("vertical layout": auto / split / screencast / none,
`MediaInput.jsx`, recordado en `localStorage.os_layout`).

`auto` activa `layout_picker.py`: **una** llamada a Gemini por vídeo de origen
(no por clip) que elige entre `none` / `screencast` / `split`. Medido sobre el
corpus de 48 contra etiquetas revisadas a mano: 94% / 92% / 96% en tres pasadas,
con 0-1 falsos positivos sobre los 28 clips que no deben tocarse, y solo 2 clips
que cambian de respuesta entre pasadas.

**Manda 12 fotogramas a 1024px, no el vídeo.** Gemini factura vídeo a ~300
tokens por segundo: una hora de fuente son ~1,08M de tokens (no cabe en una
ventana de 1M) y una subida de 1-2 GB para recibir una palabra. Doce fotogramas
cuestan ~3k tokens **dure lo que dure la fuente**, que es lo que hace viable
esto con los podcasts de una hora que entran de verdad. La resolución importa y
el número de fotogramas no: a 640px detecta 15 de 20 (una hoja de cálculo es
ilegible), a 1024px sube a 17, y pasar a 24 fotogramas lo empeora. A 1024px la
diferencia con mandar el vídeo entero cae dentro de la varianza que ya tiene el
propio modo vídeo, a 2,2 s por clip en vez de ~15 s.

Lo que hace que funcione, y que conviene no deshacer: se le pide una **decisión
entre opciones cerradas**, no una medida. Los cuatro intentos anteriores (Canny,
MSER, cobertura temporal, anchura) le pedían un número y ninguno separó una hoja
de cálculo de un marcador de esquina. La varianza que este repo atribuía a
Gemini era de las medidas continuas, no del modelo.

`layout_picker.apply()` sólo **añade**: una elección explícita del usuario nunca
se desactiva porque el modelo diga `none`.

### Hook grounding for on-screen clips (`hook_grounding.py`)

The hook and title come from the detail pass, which only reads the
transcript, so on a clip whose meaning is on the screen (a settings dialog,
a spreadsheet) they summarise the video's topic instead of naming what is
shown. After the render, if the `<clip>.layout.json` sidecar says at least
25% of the clip is `screencast` / `wide` / `inset` (plus `general` when the
layout picker called the video a screencast: a face-less scene there is a
slide or a dialog, not a group shot), three frames from those
stretches at 1024px plus the clip's own words go to Gemini
(`GroundedHook`) and `viral_hook_text` / `video_title_for_youtube_short`
are rewritten in place before `auto_hook_clip` burns them; the originals
stay under `hook_grounding.before`. Gemini-only (frames): with just a local
LLM it logs one line and keeps the transcript hook. `HOOK_GROUNDING=0`
disables it. The detail prompt itself now carries the rule "about this
moment, not the video", which is the cheap half of the same fix.

### Local LLM for the moment picker (`llm_backend.py`)

`LLM_BASE_URL` (+ `LLM_MODEL`, `LLM_API_KEY`) routes the two transcript
passes of `get_viral_clips` to any OpenAI-compatible `/chat/completions`
instead of Gemini; the response is validated with the same pydantic schemas
Gemini enforces server-side, so `main.py` sees one shape. `main.score_batch_size`
drops to 3 windows per call there (local contexts are 4-8k; a truncated
prompt scores garbage silently). Self-host `/api/process` then accepts a
request without `X-Gemini-Key` and `/api/config.localLlm` tells the dashboard
not to demand one. Frame-based stages (`layout_picker`, `screencast_layout`,
`get_visual_clips`) stay on Gemini and degrade as they always did without a
key. Never wired in cloud mode: `BILLING_ENABLED` ignores it.

### Thumbnail Studio (`thumbnail.py`, `/api/thumbnail/*`)

Titles come from the transcript plus 10 frames at 1024px, never the whole
video (same reasoning as the layout picker: an hour of video is ~1M tokens for
a text task). Two calls: a 25-title brainstorm across fixed styles, then a
critic that scores, dedupes by angle and returns 10, each paired with a 1-4
word `thumbnail_text` that complements the title rather than repeating it.
Rules baked in: payoff inside 50 characters (phones cut there), keyword in the
first 3 words, same language as the transcript. Text model is
`GEMINI_MODEL_THUMBNAIL` (default `gemini-3.7-flash`), deliberately not
`GEMINI_MODEL`: flash-lite is fine for a closed-choice layout pick and visibly
worse at creative titles. Image model is `GEMINI_IMAGE_MODEL` (default
`gemini-3.1-flash-image`).

Thumbnails are `count` **different concepts**, not one prompt repeated: a text
call designs each (hook text, side for the text, palette, scene prompt), then
one image call per concept in parallel. By default (`burn_text=true`) the
image model is told to leave that side as negative space and PIL sets the text
in Anton with a black stroke, so accents and spelling are never wrong; the
`AI painted` toggle lets the model render the text itself. Every output is
cover-cropped to 1280x720 and saved under YouTube's 2 MB limit.
`GET /api/thumbnail/frames/{session}` scores sampled frames by face area and
sharpness (MediaPipe + Laplacian), keeps them spread across the runtime, and
the dashboard offers them as the person reference so the thumbnail shows the
creator instead of a stranger; an uploaded face photo still wins.

### Video Reframing Modes

**A source already shot vertical is passed through untouched.**
`reframe_v2.source_already_fits()` gates it: every layout below reorganises the
frame to buy back width the crop threw away, and on a 9:16 upload there is none
to buy. GENERAL was the visible failure — its 0.42 height ratio, which buys
presence on a landscape source by overflowing the sides, scaled a 1080x1920
source down to a 453px sliver floating over a blurred copy of itself, and the
scene classifier routes every face-less shot (a slide, a screen recording) there.
So the picker is skipped (one Gemini call saved per upload), the classifier is
skipped, and every scene renders TRACK, whose crop is the whole frame.
`general_filtergraph` additionally floors the foreground at the height where the
source fills the output width, so the editor's explicit GENERAL override on a
portrait clip cannot reproduce the shrink either.

- **TRACK Mode** (single subject): MediaPipe face detection + YOLOv8 fallback with "Heavy Tripod" stabilization
- **GENERAL Mode** (groups/landscapes): Blurred background layout preserving full width
- **SPLIT Mode** (two-shot conversation, `split_layout.py`): both speakers stacked
  in half-frames. Off by default (`SPLIT_LAYOUT=1`); v2 engine only, so a
  fallback to the v1 loop silently renders GENERAL instead. It upgrades scenes
  the classifier already sent to GENERAL, never TRACK ones, and needs both faces
  visible **in the same frame** for at least half the sampled frames — that is
  what separates a real two-shot from a plano/contraplano, where stacking would
  show the same person twice. `SPLIT_TIGHTNESS` (default 0.8) trades a little
  upscale for keeping the other speaker out of each half. Captions on a SPLIT
  stretch sit on the seam between the halves (`{\an5}` per word event in
  `subtitles.generate_ass`), the one place they cover nobody; the render
  records which stretches are stacked in a `<clip>.layout.json` sidecar
  (`layout_ranges.py`) and every metadata writer copies it into the clip's
  `layout_ranges`, so `/api/subtitle` finds it after a restyle too. The fast
  rerender (cut without reframe) carries the canonical clip's ranges through
  the new cut (`layout_ranges.remap`, in `recut.perform_recut`). Only the
  ASS path can do this; SRT burns keep one alignment for the whole file.
- **SCREENCAST / WIDE Modes** (`screencast_layout.py`, `SCREENCAST_LAYOUT=1`):
  for scenes whose meaning lives outside the centre. Gemini reports each range's
  **width_fraction**, and that is the gate — coverage was tried before and did
  not separate a spreadsheet from a corner ticker, while width does (a bug spans
  ~15% and survives any crop, a spreadsheet spans ~100% and cannot). Content
  narrower than 0.5 moves nothing. Between 0.5 and 0.85 there is room beside the
  content, so SCREENCAST stacks it over the presenter. Above 0.85 the presenter
  is composited **on top of** the content and stacking would show it twice, so
  those scenes get WIDE: the GENERAL layout with side-cropping disabled.
- **INSET Mode** (`camera_inset.py`): pantalla a ancho completo arriba, el
  recuadro de la webcam ampliado abajo. Para el caso de una sola fuente con la
  cámara compuesta en una esquina (OBS, VOD de stream). Se encadena detrás de
  la decisión `screencast`, **no** se le pregunta a Gemini: ofrecido como cuarta
  opción respondió `screencast` en los 5 clips que tienen recuadro, en dos
  pasadas, y la exactitud global cayó de 92% a 83-85%. El detector geométrico
  encuentra esos 5 sin falsos positivos. Los tres filtros que hacen falta, cada
  uno pagado con una iteración: sujeto **pequeño**, **descentrado en
  horizontal** (una cara de talking head está centrada aunque esté alta), y
  **quieto entre muestras** (3-11px frente a 316px de una persona real).
- **ALTERNATE Mode** (`active_speaker.py`, `SPEAKER_SIGNAL=1` + `SPEAKER_CUT=1`):
  hard cuts to whoever is talking, rendered through the TRACK path as a
  trajectory with jumps. `SPEAKER_SIGNAL=1` alone just gates SPLIT on both people
  actually speaking. Mouth activity **must** be normalised per speaker before
  comparing (`normalise_activity`): raw frame-difference magnitude scales with
  local contrast and lighting, and on a real two-shot it handed one speaker
  90-100% of the scene.
- **Punch-in** (`punch_in.py`, `PUNCH_IN=1`): not a layout. A ~12% push on the
  clip's beats, riding the TRACK path by widening its per-frame crop command
  from x-only to w/h/x/y. Beats currently come from the audio envelope;
  `emphasis_times` is a plain list of seconds so the transcript's hook words can
  replace it without touching the module.

### Key Classes
- `SmoothedCameraman` - Stabilized camera movement with safe zone logic (prevents jitter)
- `SpeakerTracker` - Prevents rapid speaker switching, handles temporary occlusions

### API Endpoints
| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/process` | Submit video for processing |
| GET | `/api/status/{job_id}` | Poll job status and logs |
| POST | `/api/edit` | Apply AI video effects |
| POST | `/api/subtitle` | Generate and apply subtitles (auto-transcribes dubbed videos) |
| POST | `/api/hook` | Add text hook overlays |
| POST | `/mcp` | MCP server (JSON-RPC): the pipeline as agent tools (6 ferramentas) |
| POST/GET/DELETE | `/api/keys` | User API keys (cloud mode, session JWT only) |
| DELETE | `/api/account` | Erase the account and everything in it (GDPR art. 17) |

### Agent access (MCP, API keys, webhooks)

- **API keys** (`cloud/api_keys.py`): `osk_...` tokens, sha256-stored, created in
  the dashboard account page. `cloud/auth.get_current_user_optional` accepts
  them (`Bearer osk_...` or `X-API-Key`) and resolves the owner, so metering,
  entitlement, plan priority and job ownership apply to agents with zero
  endpoint changes. Key management itself refuses API-key auth: a leaked key
  cannot mint replacements.
- **MCP server** (`mcp_server.py`, mounted always): stateless Streamable-HTTP
  JSON-RPC at `/mcp` — no SDK dependency, ~3 methods + 8 tools. Each tool calls
  back into this same app in-process (`httpx.ASGITransport`) forwarding the
  caller's auth headers, so it can never drift from the REST behavior. Cloud
  mode 401s without a resolvable user; self-host stays BYOK-open.
- **stdio transport** (`mcp_stdio.py`): the same `handle_message` / `call_tool`
  as a subprocess, for hosts that only launch MCP servers as a command (Glama's
  Dockerfile deployments wrap one; a local client can skip the web server).
  Two invariants: `sys.stdout` is swapped for stderr **before `app` is
  imported**, because the pipeline prints everywhere and one stray line
  corrupts the JSON-RPC stream; and the app's lifespan is entered
  (`router.lifespan_context`), which `ASGITransport` does not do on its own.
- **OAuth for MCP clients** (`cloud/mcp_oauth.py`, cloud mode only): claude.ai
  and ChatGPT connect by URL, so the server publishes RFC 9728/8414 metadata
  under `/.well-known/`, accepts dynamic client registration (`POST
  /oauth/register`, public clients, PKCE S256 mandatory) and bounces
  `GET /oauth/authorize` to the dashboard consent screen (`#/oauth/authorize`),
  because the session JWT lives in localStorage on the frontend host and a
  bare API GET cannot see it. `POST /api/oauth/authorize` (session auth) mints
  the code; `POST /oauth/token` redeems it by **minting an ordinary `osk_`
  key** named after the client and returning it as the access token. No new
  auth path, no refresh tokens: the key shows up in Account → API keys and
  revoking it disconnects the app. The `/mcp` 401 carries
  `WWW-Authenticate: Bearer resource_metadata=...` so clients find the flow.
  `oauth_codes` is in `USER_OWNED_TABLES`; `oauth_clients` deliberately not.
- **Webhooks**: `POST /api/process` takes `webhook_url` + optional
  `webhook_secret` (HMAC-SHA256, `X-OpenShorts-Signature`). Validated with
  `security_utils.assert_public_url` at submit AND at delivery (DNS rebinding).
  Fired once per job from `run_job_wrapper` after the R2 archive so the payload
  can carry durable download links; survives redeploys via the resume manifest.
  `PUBLIC_API_URL` env sets the absolute-URL base when behind a proxy.

### Account erasure (GDPR art. 17)

`DELETE /api/account` (`cloud/account.py`, dashboard: Account → Delete account)
is immediate and irreversible: there is no recovery window because after the
delete there is nothing left to authenticate a recovery request against. It
refuses API-key auth (a leaked `osk_` must not destroy its own account) and
requires the caller to retype the account email.

The order of the steps is the design, and each one is a failure mode:
**Stripe cancel first**, aborting the whole thing if it fails, so we never erase
a user we are still billing; **R2 before the database**, because those rows are
the only index of which objects are theirs and dropping them first turns a
failed purge into permanent orphans; the DB delete is **one transaction** over
an explicit table list (`USER_OWNED_TABLES`) rather than the declared ON DELETE
CASCADEs, since `create_all` never ALTERs an existing table and a constraint
added after a table shipped exists in the models but not in production.
`tests/test_account_erasure.py` fails if a new table references `users.id`
without joining that list.

`app.py` registers a callback for the local working files, which record
ownership three different ways: the `.owner` file clip jobs write (so jobs
recovered from disk after a restart count too), `saas_jobs`, and
`thumbnail_sessions`. That last one is the only thing that ever deletes
generated thumbnails: the hourly sweep skips their directory and they are
served publicly at `/thumbnails/`.

What deliberately survives: the Stripe customer and its invoices (6-year
retention, Spanish commercial law) and one `account_deletions` row holding a
sha256 of the email as proof the erasure happened, itself purged after 5 years.
The "why are you leaving" answer is a closed list (`DELETION_REASONS`), never
free text — anything the user could type would land in a row designed to
outlive them. Deleting users also made one webhook path reachable that never
was before: `_apply_topup` reads the user id from Stripe metadata, so it now
confirms the row still exists before inserting, or the FK violation makes
Stripe retry the same doomed event for three days.

### Concurrency Model
Async job queue with semaphore-based concurrency control. Configure via `MAX_CONCURRENT_JOBS` env var (default: 5). Jobs auto-cleanup after 1 hour.

### Paid proxy accounting (`cloud/proxy_ledger.py`)

Downloads go direct → static ISP proxies (flat rate) → DataImpulse (per GB),
and the duration probe (`cloud/metering.probe_url_minutes`) follows the same
order, with one extra free step before any per-GB attempt: the fallback
clients through a static (`fallback-static`). **The client list is explicit
and shared** (`yt_clients.py`: `default,mweb` + the bgutil PO token
provider): with account cookies yt-dlp's own defaults are `tv_downgraded` +
`web`, and on a share of videos both come back UNPLAYABLE / SABR-only, which
yt-dlp reports as "Video unavailable". That was mistaken for an IP ban for a
week (it happened on every static IP too) and fed ~26 downloads a week to
the per-GB proxy, which then fetched 360p through the same dead list.
Measured in the prod container on 6-sep-2026, same static, same video:
cookies + defaults → unavailable; cookies + `default,mweb` → 1080p; no
cookies → 1080p. `mweb` needs the PO token, and the token needs the
webpage: never put `player_skip: webpage` back. A fallback attempt runs
anonymously when an HD attempt already failed with the cookies on that
route, and every attempt asks for the 1080p format spec (the old
`best[ext=mp4]` fallback spec was itself the 360p progressive file).
Two rules keep the per-GB proxy at zero on a normal day: the probe
reaches it **only** when a static route failed for a reason another IP can
fix (`static_failure_warrants_paid`: bot-check, 403/429, proxy/network
errors), never for a private/removed/members-only video, an uploader's
country block (the residential pool failed identically in 5 of 6 paid
probes, 3-5 sep) or a live stream
with no duration (those failed the same on every IP and used to cost ~1.7 MB
× 2 extractors each), and **never for a non-YouTube URL** (the download
plan already excluded those; Twitch, Kick, Rumble and product pages were
reaching it through the probe). The probe also carries `YOUTUBE_COOKIES`,
like the download does: an anonymous probe from the static IPs gets "Sign in
to confirm you're not a bot" in bursts (4-sep-2026: ~10 probes in one hour,
1.8 MB each on the per-GB proxy) because a datacenter IP's anonymous rate
limit is low and we make ~400 YouTube hits a day from three of them, while
the authenticated download sails through the same IPs. But the **first**
attempt on a route carries them and the second drops them, on the probe as
on the download: with the cookies attached YouTube answers UNPLAYABLE for
every client (`web_embedded`, `tv_downgraded`, `web` **and** `mweb`) on a
share of videos, which yt-dlp reports as "Video unavailable" (9-sep-2026,
same video on all three statics; anonymous on the same IP → 1080p 137+140).
Without that anonymous second attempt the probe read a cookie problem as an
IP problem and escalated to the per-GB proxy, which carries the same cookies
and fails identically, while the download recovered for free on the same
static. `main.py` prints `PROXY_ROUTE=<json>` after
every download (winner, paid bytes across all attempts including failed
paid ones, each free attempt's error); `app.py` persists it as a
`proxy_usage` row at job end and pages Telegram when the paid proxy carried
bytes, folding a burst into one message per 5 min. The in-memory monthly
counter and the container log (rotates within the hour) cannot answer "what
cost $14 on the 28th"; the table can. `PAID_PROXY_DAILY_MB` (default
500) is the hard ceiling: past it the paid proxy is dropped from the probe
and from every new job's env until UTC midnight. The watcher probes the
static pool against a real YouTube watch page (playable markers), not
google.com — the 28th happened because YouTube refused the static IPs while
google kept answering 204. On the dev Mac, do not keep
`PROXY_URL` in `.env`: every local `main.py` run then bills DataImpulse.

### Deploys and running jobs (handover + drain)

Every push to `main` redeploys the API container. Coolify starts the NEW
container before stopping the old one (rolling update) and both share
`output/`, so `app.py` coordinates them instead of relying on a fast swap:

- Each instance writes its id to `output/.instance` at startup. An instance
  that sees another id there is the old one and **drains**: it finishes the
  jobs it is running, starts none, and leaves queued manifests on disk.
- A running job heartbeats its `.resume.json` every 10 s. The resume scan
  (startup + every 30 s) re-enqueues only manifests nobody heartbeated for
  60 s, so no job runs twice and none is lost. Max 2 resume attempts.
- SIGTERM (`docker stop`) drains too, up to `DRAIN_TIMEOUT_SECONDS` (840),
  then hands the signal to uvicorn. The app's Coolify stop grace period is
  900 s (`application_settings.stop_grace_period`); keep the timeout below it.
  After the drain hands the signal to uvicorn, `--timeout-graceful-shutdown 15`
  (Dockerfile) caps the wait for in-flight connections: uvicorn's default is
  unbounded, and one open range download kept a drained container alive for
  the full grace period while Traefik still routed half the traffic to its
  closed port.
- `/health/ready` + the Dockerfile `HEALTHCHECK` are what keep Traefik off a
  dying container: its docker provider only routes to `healthy` containers,
  so an instance answers 503 from the moment it gets SIGTERM (out of rotation
  within ~10 s, socket still open) and a booting one gets no traffic until it
  answers. Only SIGTERM flips it, not the marker drain: at that point the new
  container is still booting and nobody else would be routable. The Coolify
  app has its health check enabled on that path so it waits for the new
  container to be `healthy` before stopping the old one. With that option on,
  Coolify replaces the Dockerfile HEALTHCHECK with its own curl/wget command
  AND its own interval/retries (5 s × 3), so the image must ship `curl` or
  every deploy rolls back as unhealthy, and a stopping container takes 15 s
  to turn `unhealthy`. That is why the drain keeps serving for
  `PROXY_DRAIN_SECONDS` (20) after the jobs are done before it hands the
  signal to uvicorn: closing the socket earlier is 502s until Traefik
  notices (measured ~60 s per deploy with retries=12 and no grace). And
  `HARD_EXIT_SECONDS` (30) after that the process is ended outright: uvicorn
  finishing does not end the interpreter while an executor thread hangs in
  a network probe, and that kept a drained container alive for the full 900 s.
  `/health` stays a plain liveness probe for the external watcher.
- `/api/status` answers from disk for a job this instance never held, so a
  poll landing on either container during the handover is fine.
- `main.py` leaves `.transcript_checkpoint.json` in the job dir so a job that
  does get re-run skips the paid transcription (download and Gemini repeat).

Before pushing, still batch small commits (tests, docs) with the next real
change: every deploy is a ~5 min build plus a handover.

## CI: a green pipeline closes the task, not the push
- After every `git push`, wait for the commit's workflow and confirm it is green: `ci-wait` (Victor's Mac) or `gh run watch $(gh run list -c $(git rev-parse HEAD) -L1 --json databaseId -q ".[0].databaseId") --exit-status`.
- If it is red: fix, push, check again. Never report the task as done with a red CI.
- Before pushing, run locally what the CI runs (lint + tests of this repo).
