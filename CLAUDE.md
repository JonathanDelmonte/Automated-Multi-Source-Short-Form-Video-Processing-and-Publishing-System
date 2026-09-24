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
Todo push vai para la, na branch **`main`**.

> Ate 13-set-2026 a branch se chamava `claude/loving-fermat-c84xtd`. Aquele
> nome nunca foi escolha de projeto: e o padrao que o Claude Code na web gera
> para a branch de uma sessao (`claude/<duas-palavras>-<hash>`), e como o
> repositorio nasceu daquela sessao, o GitHub o adotou como branch padrao.
> Renomeado a pedido do autor. Efeito colateral bem-vindo: o `ci.yml` dispara
> em `push: branches: [main]`, entao o CI, que nunca tinha rodado neste
> repositorio, passou a rodar.


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

### A maquina do autor (para dar comando pronto, nao com `<caminho>`)

Windows 10. O repositorio esta em:

```
C:\Users\User\Documents\GitHub\Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System
```

E o padrao do GitHub Desktop. Placa **NVIDIA RTX 3060**, entao os caminhos de
GPU valem. O `docs/COMO-EXECUTAR.md` usa `C:\cortes` como exemplo generico --
ao passar comando PARA O AUTOR, usar o caminho acima.

**E preferir os atalhos a comandos crus.** `atalhos/` existe justamente porque
`docker compose` a mao tem pegadinhas que ja morderam: todos os `.bat` chamam o
`_garantir-docker.bat`, que ABRE o Docker Desktop e espera o motor subir. Sem
ele, o erro e `failed to connect to the docker API at npipe:////...`, que nao
diz "abra o Docker Desktop" -- diz que nao achou um cano, entao parece problema
do projeto e e do Windows. Ja aconteceu por eu ter mandado o comando cru.

**Para atualizar, mandar `atalhos\atualizar.bat` -- nunca `git pull` + `subir`.**
Os dois nao sao equivalentes: o `subir` e `docker compose up -d`, que **nao
recria container cujo config nao mudou**, entao o codigo novo fica no disco sem
ninguem reler. O bind mount do Windows nao repassa evento de arquivo (ver
`docs/COMO-EXECUTAR.md`), entao nem o `--reload` do uvicorn nem o grafo de
modulos do Vite percebem sozinhos. Ja aconteceu por eu ter mandado `git pull` +
`subir-gpu.bat`: o painel abriu **em preto**, sem erro e sem log.

### Idioma

Documentacao, mensagens de commit e comentarios novos em portugues. Codigo
herdado do upstream permanece como esta -- nao traduzir em massa.

### Onde esta o planejamento

| Arquivo | Papel |
|---|---|
| `docs/PLANO-DE-ACAO.md` | ponto de entrada: fases, ordem de execucao, critérios de pronto |
| `docs/PLANO-TECNICO.md` | documento de origem v2: arquitetura, o *que* e o *porque* |
| `docs/AUDITORIA-VERIFICACAO.md` | verificacao das premissas do plano, com fontes |
| `docs/DECISOES.md` | ADR-001 a 012 |
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
  - **A auth chegou na Fase 4** (`auth.py`, bloco 4.1). Antes dela, e enquanto
    nenhum usuario tiver senha, tudo pertence ao tenant fixo
    `00000000-0000-0000-0000-000000000001`.
  - **O pipeline ESCREVE no banco desde o bloco 3.3**: `sources` e `jobs` no
    submit, `clips` no fim do job, `accounts` e `publications` pela fila de
    publicacao. Antes disso so `templates` era escrita. Tudo falha aberto -- o
    pipeline nunca dependeu do banco --, mas a Fase 3 depende: `publications`
    tem FK composta para `clips`.
- **MediaPipe e o tracking padrao** (ADR-003); YOLOv8 (AGPL-3.0) fica atras de
  flag desligada -- **feito no bloco 1.7** (`face_tracker.py`). Eram dois
  problemas no mesmo lugar: o de licenca (o detector era o fallback *automatico*
  de toda cena sem rosto, ou seja, ligado por padrao) e o de custo
  (`model = YOLO(...)` em nivel de modulo carregava e, na primeira vez, baixava
  os pesos **em todo job**, porque o `main.py` e subprocesso novo a cada video).
  - `FACE_TRACKER=yolo` liga; qualquer outro valor cai no padrao Apache 2.0.
  - O **import** do `ultralytics` mora dentro de `face_tracker.modelo_yolo()`.
    E ele que traz a AGPL para o processo; nao o por de volta no topo do
    `main.py`. Um teste le a arvore sintatica do `main.py` e falha se voltar.
  - `main.detect_person_yolo` e o **unico** portao: os quatro sitios de chamada
    (`main`, `reframe_v2`, `camera_inset`, `screencast_layout`) passam por la.
  - **O ADR-003 subestimou o custo, e a nota nele registra isso.** O detector
    nao serve so para enquadrar: `camera_inset` e `screencast_layout` o usam
    para DETECTAR. Sem ele, INSET pode nao disparar (o rosto num recuadro de
    webcam 1080p e pequeno demais para o BlazeFace) e SCREENCAST pode nao achar
    o apresentador (medido: zero deteccoes numa demonstracao de planilha). A
    decisao ficou de pe, mas a degradacao e **barulhenta**:
    `face_tracker.avisar_desligado()` imprime uma linha por job. Nao silenciar.
  - Os pesos so sao pre-baixados com `--build-arg YOLO=1`, mesmo padrao do
    `GPU=1`.
- **Cascata de LLM gratuita** (`llm_cascade.py`, Fase 0.4 concluida, ADR-004,
  ADR-005 e ADR-011). O detector de momentos atravessa Groq / Gemini e, quando
  os dois falham numa chamada, todo provedor gratuito que tiver chave (Qwen e
  gpt-oss-20b na mesma chave do Groq, outro Gemini na mesma chave do Google,
  NVIDIA/Nemotron, Mistral, Ollama Cloud, OpenRouter, Cloudflare, Z.ai), em
  ordem que depende da duracao falada da fonte, com orcamento diario em
  `output/.llm_budget.json` (em disco porque o `main.py` e subprocesso novo a
  cada job). Provedor entra so com sua chave presente; o Ollama e opt-in via
  `OLLAMA_BASE_URL`. Sem nenhuma chave, o comportamento e o antigo. Variaveis
  documentadas no `.env.example`. Ver a secao "A cascata ampliada" abaixo.
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

### Documento de template (`template.py`, Fase 2 bloco 2.1)

O JSON da secao 5 -- "nao e um editor de timeline, e um documento de
configuracao versionado" -- com defaults, validacao, seis presets de legenda e
a traducao `safeArea` -> `margin_v`. Stdlib pura, entao roda no CI.

- **O ADR-002 ganhou nota: as duas aquisicoes do `clippyme` ja estavam aqui.**
  A segunda passada existe (`/api/subtitle` requeima legenda sobre o clipe ja
  renderizado; `/api/hook` idem; `recut` recorta sem reenquadrar) e os presets
  sao combinacao de botoes que o `generate_ass` ja expoe. Faltava o documento,
  nao o motor. **Nao adicionar o remote do clippyme para importar o que ja esta
  escrito.**
- **`karaoke_fill` nao foi inventado**: e o `subtitles.AUTO_CAPTION_STYLE`,
  escolhido por medicao em 25-jul-2026. Um teste compara os dois.
- **Merge e por secao**: `{"safeArea": {"bottomPct": 25}}` mantem o `topPct`.
  Campo desconhecido passa intacto -- documento versionado, recusar o que ainda
  nao se le transformaria todo campo novo em migracao.
- **`safeArea` nao e enfeite** (12% topo, 18% base): e onde o app cobre o
  quadro com nome de perfil e botoes. O `SAFE_MARGIN_V` de hoje (43, ~15%) ja
  veio de uma falha observada; os 18% da secao 5 sao mais folga na mesma
  direcao, e um teste garante que o padrao nunca fique ABAIXO do atual.
- **Um preset so vale se o `generate_ass` souber receber**: um teste compara
  as chaves com a assinatura dele, porque argumento errado so quebraria na hora
  de queimar, depois do render inteiro.

**Aplicar (bloco 2.2)** e por `/api/subtitle`, que ja era a segunda passada.
`SubtitleRequest.template` e `preview_seconds` sao os dois campos novos.

- **O documento MANDA no estilo quando vem**, e nao o contrario. Os campos
  soltos do request sao a sobreposicao por clipe do modal, e o modal manda
  todos eles sempre, preenchidos com os defaults dele -- deixar o modal vencer
  campo a campo tornaria o template decorativo.
- **Template forca o caminho ASS.** E o unico que aceita realce por palavra,
  efeito, base apagada e a legenda na costura de um SPLIT; e o `burn_subtitles`
  reconhece `.ass` e **nao** aplica `force_style` em cima, que e o que faz os
  estilos do documento chegarem intactos.
- **O preview corta a ENTRADA, nao a legenda.** O ASS cobre o clipe inteiro e
  os eventos alem do corte nunca aparecem, entao nao ha timestamp a remapear.
  Entre 0,5 e 30 s.
- **Preview nao mexe no metadata nem arquiva.** Apontar o `video_url` do clipe
  para um trecho de 3s seria perder o clipe de vista. Sai com nome proprio
  (`preview_...`) e o corte intermediario e apagado.

**CRUD (bloco 2.3)**: `/api/templates` (GET lista + presets + padrao, POST
salva, DELETE apaga). Primeiro uso do banco por um caminho do pipeline.

- **Salvar cria VERSAO, nunca sobrescreve**; apagar leva **todas** as versoes
  daquele nome. Sobrescrever perderia o unico ganho da versao (voltar ao
  estilo de antes); apagar so uma deixaria o template vivo com o estilo velho.
- **O banco nasce no boot** (`db_seed.seed()` no lifespan, idempotente), e
  **falha aberto**: banco quebrado nao impede a API de subir, porque o
  pipeline funciona sem ele. Quem usar templates recebe 503 dizendo o que
  rodar.
- **O seed grava o `template.PADRAO`, nao o exemplo da secao 5.** O exemplo
  referencia `logo.png`, `endcard.mp4` e `lofi_01.mp3`, que nao existem, e liga
  `cuts.removeSilence`, que ninguem implementa -- como documentacao esta certo,
  como linha que o painel lista e um template que promete o que nao faz.
- **`maxWords` nao e `max_chars`.** A secao 5 conta PALAVRAS, o `generate_ass`
  conta CARACTERES; a traducao ingenua (que o bloco 2.1 fez) virava bloco de
  tres LETRAS a partir do proprio exemplo da secao 5. Hoje converte por
  `CHARS_POR_PALAVRA`, documentado como aproximacao, e `maxChars` da o numero
  exato.
- **Dois sistemas de preset convivem**: os 11 `CAPTION_PRESETS` do
  `SubtitleModal` sao escolhas rapidas por clipe, no navegador; o template e o
  documento salvo, e manda no estilo inteiro. O seletor fica acima deles na
  tela porque a ordem visual e a ordem de precedencia.

### Camada de ingestao (`sources/`, Fase 1 bloco 1.1)

Uma fonte, uma classe, com `matches` / `probe` / `fetch`; o pipeline recebe
sempre um arquivo em disco e um titulo. Antes disto a decisao de origem estava
em `main.is_youtube_url` + `main.plan_download_attempts` + o `__main__` do
`main.py`, e nenhum era o dono da pergunta.

- **Os adapters chamam o `main`; nao movem o codigo dele.** `download_youtube_video`
  sao ~240 linhas do upstream (cascata de proxy, clients do yt-dlp,
  contabilidade de bytes pagos). Traze-las para o adapter daria conflito em todo
  `git fetch upstream`.
- **O `main` e resolvido tarde e por `base.modulo_main()`, nunca por
  `import main`.** Tardio porque evita o ciclo e mantem o pacote importavel so
  com a stdlib (os testes de roteamento rodam no CI, que de proposito nao
  instala torch nem scenedetect). E pelo helper porque `python main.py` carrega
  o arquivo como `__main__`: um `import main` ali dentro **le o arquivo outra
  vez**, criando um segundo modulo com o topo reexecutado -- outro grafo do
  MediaPipe, outro `DETECT_LOCK`, outros globais, em todo job.
  `tests/test_sources_modulo_main.py` roda um subprocesso de verdade para
  pegar isso; sob o pytest o defeito nao aparece, porque ali `__main__` e o
  proprio pytest.
- **`probe()` aqui e o barato**, sem rede. O probe caro (duracao, tamanho) tem
  dono: `quality_probe.py` e `cloud/metering.probe_url_minutes`, com as regras
  de quando vale pagar por ele. `tests/test_sources.py` falha se um `probe`
  passar a importar o `main`.
- **A ordem do `REGISTRY` e o desempate**: `DirectUrlAdapter` aceita qualquer
  http(s), entao plataforma nova entra **antes** dele ou nunca e alcancada.
- **`id` novo exige migracao.** `sources.adapter` tem `CHECK`; um id fora da
  lista so falharia ao gravar a primeira linha, depois do download inteiro.
  `tests/test_db_schema.py::test_sources_aceita_todo_adapter_registrado` quebra
  antes. O `direct` (URL de arquivo solta, que a lista da secao 4 nao previa)
  entrou pela migracao `2f1b7c4ae903`.
- **O que e propriedade da fonte mora no adapter**, nao numa tabela no
  `main.py`: `cookie_env` / `cookie_file` (o VOD sub-only da Twitch precisa de
  `TWITCH_COOKIES`, em arquivo proprio para que dois jobs simultaneos nao se
  sobrescrevam; o do YouTube fica em `/app/cookies.txt` porque o
  `quality_probe.py` procura esse caminho pelo nome) e o rotulo para log. O
  `main.py` so reexporta: `source_label`, `cookie_jar_for`.
- **A live da Twitch e gravada em BLOCOS** (`sources/twitch_live.py`, bloco
  1.5). Ver a secao propria abaixo. A URL de um canal nunca pode cair no
  adapter generico: o yt-dlp *aceita* gravar live e baixaria ate a transmissao
  acabar. Nao mover `TwitchLiveAdapter` para depois do `DirectUrlAdapter` no
  `REGISTRY`.
- **`/<canal>/videos` continua recusada** por `assert_fetchable`, que roda
  **duas vezes**: no `app.py` ao submeter (antes do probe de qualidade, que
  numa listagem nao responde nada) e no `main.py` antes do yt-dlp. Nao e um
  video: o yt-dlp a trataria como playlist e baixaria o canal inteiro.

### O jar de cookies pode ser ARQUIVO, nao so variavel (22-set-2026)

O download de YouTube morria com "sign in to confirm you're not a bot" numa
maquina onde o `quality_probe.py` achava os cookies. As duas metades
procuravam em lugares diferentes, e o comentario do probe afirmava o
contrario: *"Mirrors main.py's cookie discovery"*. O `main.py` nao tinha
descoberta nenhuma -- lia `YOUTUBE_COOKIES` e, sem ela, desistia.

- **`sources.jar_em_disco()` e a unica definicao**, e os dois chamam. Um teste
  le o AST dos dois arquivos e falha se qualquer um voltar a ter lista propria
  de caminhos -- foi exatamente assim que divergiram.
- **A variavel continua vencendo quando esta posta.** Ela guarda o CONTEUDO do
  `cookies.txt` e e o mecanismo certo em nuvem, onde segredo se entrega por
  ambiente. Num `docker compose` com o repositorio montado em `/app`, o arquivo
  na pasta e o natural -- e um jar velho esquecido ali nao pode calar quem
  definiu a variavel de proposito.
- **O nome alternativo mora no ADAPTER** (`cookie_file_alt`), como o
  `cookie_env` e o `cookie_file`: `www.youtube.com_cookies.txt` e o nome com
  que as extensoes salvam, e obrigar a renomear e um passo a mais para errar.
  So o YouTube o declara, entao ele nao vira jar da Twitch por acidente.
- **Arquivo vazio conta como ausente**: um `cookies.txt` de zero byte e o que
  sobra de uma exportacao que falhou, e passa-lo ao yt-dlp devolve o MESMO erro
  de bot sem dizer que o jar e que estava vazio.
- **`.gitignore` passou a cobrir os jars**, e nao cobria. Cookie de sessao e
  credencial viva: quem tem o arquivo entra na conta sem senha e sem 2FA. O
  conserto acima fez o arquivo passar a existir no diretorio de trabalho, entao
  a falta virou risco de verdade. Ha teste chamando `git check-ignore`.

### Sem cookies e o caminho NORMAL: a lista de clientes e outra (22-set-2026)

Colar um link e ver o job morrer em "sign in to confirm you're not a bot" nao
era falta de cookies -- era a lista de `player_client` medida PARA A CONTA
sendo imposta a quem nao tem conta. `yt_clients.HD_CLIENTS = default,mweb` veio
de uma medicao de 6-set-2026 com cookies, em IP de datacenter, e valia; a linha
da mesma medicao que dizia "sem cookies o padrao devolve 1080p" venceu, e no
dia em que venceu nao sobrou naquele trio um cliente que o YouTube sirva
anonimamente: `visionos`, `web` e `mweb` respondem todos LOGIN_REQUIRED.

- **Duas listas, escolhidas POR TENTATIVA** (`yt_clients.args_da_tentativa`):
  `default,mweb` quando aquela tentativa leva cookies, `tv,default` quando nao
  leva. Quem decide e o que de FATO acontece (`envia_cookies and tem_jar`), nao
  a intencao do plano -- a tentativa `fallback` sai anonima de proposito depois
  de uma HD, e mandava a lista da conta junto.
- **`tv` porque e o unico sem exigencia nenhuma.** Na tabela do proprio yt-dlp
  (`INNERTUBE_CLIENTS`) ele e o unico cliente sem `REQUIRE_AUTH` e sem PO token
  -- nem GVS nem player. Pede o player JS, que o Deno da imagem resolve. Um
  teste le aquela tabela e falha se um nome com `REQUIRE_AUTH` entrar na lista
  anonima.
- **A decisao mora no `yt_clients` e nao no `main.py`** porque e regra, e
  `main.py` so e importavel com torch: no `yt_clients` (stdlib puro) o CI
  exercita as quatro combinacoes. No `main.py` sobrou um AST guard contra o
  formato antigo, que montava os args UMA vez para todas as tentativas.
- **`YT_CLIENTS_ANON` / `YT_CLIENTS_AUTH` sobrescrevem, e isso e a parte
  importante.** Esta e a unica peca do pipeline cuja resposta certa muda sem
  ninguem tocar no codigo -- quem decide e o YouTube. Com o repositorio montado
  em `/app`, trocar a lista e editar o `.env` e reiniciar o backend (segundos);
  sem a variavel seria reconstruir a imagem (40 min) a cada palpite. Variavel
  em branco ou so com virgulas cai no padrao: `player_client: []` nao extrai
  nada.
- **`python diagnostico_youtube.py <url>`** (atalho: `testar-youtube.bat`) mede
  qual lista passa HOJE, desta maquina, e imprime a linha de `.env` a por --
  ou diz que nao ha nada a mudar. Ele **nao aplica** a troca: mexer na lista
  que todo download usa e decisao de quem esta olhando, nao efeito colateral de
  um diagnostico. `conclusoes()` e pura, entao o CI le a regra sem rede.
- **Quando TODOS os candidatos caem no anti-bot, o relatorio nao manda trocar
  de lista**: ai a causa e o IP, e a saida e esperar, sair por outra rede ou
  dar cookies. Afirmar "e o cliente" quando todos falharam igual seria o
  chute que este repositorio recusa em toda decisao.
- **O PO token NAO era a causa, e isso custou quase um rebuild.** No mesmo log
  o `bgutil:script-node` aparece indisponivel (o `nodejs` do Debian trixie e
  20.19.2 e o bgutil 2.0.0 pede `>= 22` -- e o `git clone --depth 1` sem tag no
  Dockerfile foi buscar o 2.0.0 no rebuild da GPU). Mas o `bgutil:script-deno`
  aparece DISPONIVEL e tem preferencia MAIOR, e mesmo assim nenhum token foi
  pedido: o LOGIN_REQUIRED acontece antes de existir formato para assinar.
  Subir o Node arrumaria uma linha de aviso, nao o download. Fica registrado
  como candidato ao proximo `reconstruir.bat`, nao como conserto.
- **O probe usa a MESMA lista** (`quality_probe.py`), e o comentario que mandava
  nunca sobrescrever o padrao do yt-dlp saiu: um probe que mede por uma lista e
  um download que baixa por outra medem coisas diferentes, e e exatamente o que
  o `yt_clients` existe para impedir.

### Google Drive por cookies, nao OAuth (`sources/gdrive.py`, bloco 1.6)

Divergencia deliberada do §4, que previa "Drive API v3 + OAuth com refresh
token". OAuth e o desenho certo para SaaS multiusuario e desproporcional para
ferramenta pessoal: projeto no Google Cloud, tela de consentimento,
credenciais de cliente e fluxo de refresh, tudo para o autor ler arquivos da
propria conta. O yt-dlp ja tem extrator de Drive e cobre os dois casos --
compartilhado por link baixa sem nada, privado baixa com `GDRIVE_COOKIES`
(jar proprio, `/app/cookies-gdrive.txt`).

Quando a Fase 4 trouxer multiusuario, o OAuth entra como **outra
implementacao atras desta mesma interface** -- e o motivo de a camada existir.

**Pasta do Drive e recusada** por `assert_fetchable`: o yt-dlp nao suporta
pasta, e sem a recusa a URL cai no adapter generico e falha com uma mensagem
sobre extrator.

### Live da Twitch em blocos (`sources/twitch_live.py`, Fase 1 bloco 1.5)

**Um job = um bloco, e essa e a decisao inteira.** O §4 chama a live de "worker
de longa duracao"; o fatiamento em blocos que ele manda fazer e o que evita
precisar de um. Um job de 4h quebraria quatro coisas de uma vez: a vaga no
semaforo da fila, o batimento do manifesto de resume (60s), o drain de um
deploy (`DRAIN_TIMEOUT_SECONDS`, 840s) e a barra do painel.

- `TWITCH_LIVE_BLOCK_MINUTES` (15 por padrao), com **teto de 2h** -- acima
  disso o job deixa de caber no drain, que e justamente o que o fatiamento
  resolve.
- **ffmpeg grava, yt-dlp so resolve.** O yt-dlp grava live ate ela acabar; nao
  ha "grave 15 minutos". Ele entra so para dizer se o canal esta no ar e achar
  a URL do stream; quem grava e `ffmpeg -i <url> -t <segundos> -c copy`, que
  fecha o arquivo no tempo pedido. `-t` **depois** do `-i`: antes dele seria um
  seek, e numa live isso nunca fecha o arquivo.
- **Aqui NAO se falha aberto**, ao contrario do estagio 02: sem o arquivo nao
  ha o que processar. Canal fora do ar levanta `LiveOffline` com a saida
  (use a URL do VOD).
- Efeito colateral bom: o pre-filtro do bloco 1.4 le o orcamento **restante**
  do dia, entao os blocos seguintes de uma live longa vao sendo apertados
  sozinhos conforme a cota e consumida.

### Estagio 02: o audio dirige (`audio_probe.py`, Fase 1 bloco 1.3)

A decisao mais importante do §4, e agora implementada: um `ffprobe` e um WAV
16k mono (`.audio16k.wav` no diretorio do job) antes de tudo. Transcricao e
deteccao leem **so o audio**; o video so e tocado no 05/06, e ali so nos
trechos escolhidos. O custo passa a crescer com a duracao FALADA, nao com o
tamanho do arquivo -- e o que sustenta o alvo de 10GB do §4.

- **Tudo falha aberto.** `probe()` devolve o dict vazio e `extract_wav()`
  devolve None; o `main.py` entao entrega o video ao modelo como antes.
  Otimizacao de custo que derruba job nao e otimizacao. Nao trocar por
  `raise`.
- **A duracao vem do `ffprobe`**, com o OpenCV de reserva. `frame_count/fps`
  erra em video de taxa variavel e **divide por zero** quando o container nao
  declara fps.
- **Nao extrai** com `--skip-analysis` (ninguem vai ler transcricao) nem sem
  trilha de audio (o caminho de analise visual ja existe).
- **O WAV e apagado no fim** (a menos de `--keep-original`): numa live de 4h
  sao ~460 MB. Quem resume um job nao perde nada -- o que evita retranscrever
  e o `.transcript_checkpoint.json`.
- **O Parakeet reconhece o WAV do pipeline** e nao o reextrai.
  `transcribe_backends._extract_wav` devolve `(caminho, e_nosso_para_apagar)`:
  o `finally` dele apagava o arquivo que o resto do job ainda usa. **Nao voltar
  a devolver so o caminho.**
- **`PIPELINE_STAGES` no `app.py` ganhou `02_probe`.** Os testes de progresso
  derivam indice e total da lista; nao voltar a fixar numeros neles.

### Pre-filtro heuristico (`prefilter.py`, Fase 1 bloco 1.4, ADR-004)

Corta janelas de pontuacao antes do LLM. **Corta por ORCAMENTO, nunca por
qualidade**: nunca decide que uma janela e ruim, decide que so cabem N hoje e
manda as N melhores. Num video curto ele **nao faz nada** -- e o que o torna
seguro de deixar ligado antes de existir calibracao. Nao trocar por limiar de
nota: o erro de um limiar mal calibrado e silencioso.

- **O orcamento e o menor teto publicado da CADEIA**, nao o do primeiro
  provedor. Pelo ADR-005 fonte longa comeca no Gemini, que nao publica teto --
  olhar so o primeiro deixaria passar exatamente a live de 4h que o ADR-004
  quer viabilizar. E a cascata escorrega: um 429 do Gemini poe o job no Groq no
  meio do caminho.
- **Nenhum provedor com teto publicado = nao atua.** Sem numero divulgado,
  cortar seria o achismo que o ADR-004 manda evitar.
- Piso de `MINIMO_DE_JANELAS`; `PREFILTER_MAX_WINDOWS` manda em tudo.
- Os quatro sinais do ADR-004, normalizados **relativos ao video** (fala densa
  num podcast calmo e outra coisa que numa live de gameplay). A energia vem do
  WAV do estagio 02 e e opcional: sem numpy ou sem WAV, decide com os outros
  tres.
- **Os numeros das janelas descartadas vao para o log de proposito**: calibrar
  isto e trabalho da Fase 5 e precisa de casos reais.

### Camada de publicacao (`publishers/`, Fase 3 bloco 3.1, ADR-010)

Um driver, uma classe, com `disponivel` / `capability` / `cost` / `publish`. O
pipeline entrega um `RenderedClip` e nao sabe para onde vai -- mesmo padrao do
`sources/`, e pelo mesmo motivo: stdlib puro, entao a regra de negocio (qual
driver atende) roda no CI sem banco e sem cliente de plataforma nenhuma.

- **O `browser` fica fora da cascata automatica por RISCO, nao por nome**
  (ADR-010). `resolve()` so aceita driver com `cost().risk_score <=
  RISCO_MAXIMO_AUTOMATICO`, que e **zero**. Nao trocar por
  `if driver.id == "browser"`: uma lista de excecoes por nome nao protege do
  proximo driver arriscado, e o preco do esquecimento e a conta, nao um bug.
- **O `manual` e o piso e ENCERRA a cascata.** `resolve()` sempre devolve
  alguma coisa -- "nenhum driver atende" nao e um estado possivel, e e isso que
  torna a cascata segura de deixar automatica. Nada registrado depois do
  `manual` e alcancavel; o `browser` esta depois dele de proposito.
- **O `manual` nao e a versao capada.** Ele escreve, ao lado do corte, a
  legenda pronta para colar: titulo, descricao da plataforma daquela conta e as
  hashtags que ainda faltam. **Um arquivo por corte e por plataforma** -- "pronto
  pra colar" so e verdade se der para selecionar tudo e colar. E termina em
  `scheduled`, nunca em `published`: quem aperta publicar e a pessoa.
- **`driver_pref` e preferencia dentro do que a cascata ja aceita**, nunca
  ampliacao. O padrao e `auto` (migracao `8c5d2e91b740`): com o antigo `manual`,
  toda conta nascia presa na fila manual e o `youtube-api` nunca seria escolhido.
- **`publish()` recebe a `account`**, que a §6 esquece de passar. Sem ela o
  `manual` nao sabe que texto escrever e o `youtube-api` nao acha o token.
- `aggregator` e `browser` sao stubs que levantam `DriverDesligado`.

**O driver `youtube-api`** (`publishers/youtube_api.py`, `quota.py`, `vault.py`,
`youtube_oauth.py`, bloco 3.4) publica no canal proprio pela API oficial.

- **6 uploads por dia**: 1600 unidades por `videos.insert` contra 10.000/dia, o
  numero exato que o plano manda respeitar. O contador existe para que o 7o
  **caia na fila manual**, nao para virar `quotaExceeded` e um job vermelho.
- **O dia do contador e o do Pacifico**, que e quando a quota do YouTube zera.
  Contar em UTC daria 7-8 horas por dia de discordancia com a API. Sem `tzdata`
  no sistema, cai para UTC-8 fixo -- o horario mais tarde, entao erra para o
  lado de segurar o upload.
- **Debita ANTES da chamada.** O YouTube cobra quando aceita a requisicao: um
  upload que morre no meio ja gastou as 1600, e contar so no sucesso deixaria o
  contador abaixo da verdade justamente no dia ruim.
- **HTTP direto com `httpx`**, sem `google-api-python-client`: sao tres
  requisicoes, e o cliente oficial traria `google-auth` e amigos para uma imagem
  que ja carrega torch e mediapipe. A rede esta isolada em tres funcoes
  (`_token_de_acesso`, `_abrir_sessao`, `_enviar_arquivo`) e o que decide esta
  em funcoes puras -- o CI nao alcanca as primeiras e cobre todas as segundas.
- **`privacidade()` cai para `private`** com qualquer valor fora da lista: um
  erro de digitacao num campo de visibilidade nao pode ser o que publica um
  corte para o mundo. E o driver **avisa quando o YouTube rebaixa**, que e a
  diferenca entre "publiquei" e "subiu, mas ninguem ve".
- **O cofre** (`vault.py`) resolve `accounts.credentials_ref`, que a §7 exigia e
  ninguem lia. Backends `env` e `local` (arquivo 0600); mensagem de erro diz o
  NOME do campo que falta, nunca o valor -- o log do job aparece no painel.
  **Cada pedaco do endereco e sanitizado** antes de virar caminho: o ref vem do
  corpo de `POST /api/contas`, e `vault://local/../canal` daria um arquivo fora
  do cofre escolhido por quem mandou a requisicao. O ref tambem e validado na
  criacao da conta, e nao na hora de publicar.
- **`python youtube_oauth.py`** e a unica forma de emitir o refresh token
  (consentimento no navegador, loopback -- o Google desativou o `oob`). Escopo
  `youtube.upload` e so ele: se o token vazar, a diferenca para o escopo
  `youtube` completo e a diferenca entre um video indesejado e um canal vazio.

**O pacote do dia** (`publishers/pacote.py`, bloco 3.2) e a entrega que a §6
pede por escrito: `GET /api/publicacoes/pacote` devolve um ZIP com os cortes do
dia, a legenda de cada um e um `LEIA-ME.txt` com a ordem sugerida;
`GET /api/publicacoes/dias` lista os dias que tem corte.

- **O montador nao sabe onde o pipeline guarda nada.** Recebe
  `(RenderedClip, PostMeta)` que o `app.py` montou -- achar o arquivo ATUAL de
  um corte e conhecimento do `app.py`, que ja resolve `subtitled_` / `recut_` /
  `hooked_` em `_canonical_clip_file`. Copiar aquilo para ca criaria uma segunda
  verdade que empacotaria a versao sem legenda.
- **Um corte sem arquivo em disco nao derruba o pacote**: sai da lista e e
  nomeado no LEIA-ME.
- **O dia e a data do ARQUIVO do corte**, nao a do job -- um job de ontem que
  ganhou legenda hoje entra no pacote de hoje. E, sem `dia`, vale o dia mais
  recente que TEM corte, nao "hoje".
- **Nao ha `video_description_for_youtube` no prompt de deteccao** (so TikTok e
  Instagram), entao a descricao de um Short sai da queda de
  `PostMeta.description_for`.
- `_cortes_por_dia` e **o unico caminho da API que atravessa todos os jobs**.
  O filtro de dono ja esta la, no-op hoje, para que a Fase 4 nao tenha de
  lembrar dele depois.

### Fila de publicacao (`publish_queue.py`, `/api/contas`, `/api/publicar`, bloco 3.5)

Junta o resolvedor da §6, as linhas de `clips` do bloco 3.3 e as contas de
plataforma. A partir daqui existe, fora da cabeca de quem publicou, a linha
"este corte foi para este canal por este driver".

- **O corpo de `/api/publicar` aceita `account_id`, nunca `driver`.** Deixar o
  painel mandar o driver reabriria por fora a porta que o ADR-010 fechou --
  bastaria um `driver: "browser"` numa requisicao. A conta e um endereco; o
  driver e consequencia, e quem decide e `publishers.resolve`.
- **A linha de `publications` nasce antes do upload** (`publishing`) e e fechada
  depois. Gravar so no sucesso deixaria um upload morto no meio sem rastro, e a
  unicidade `(clip, conta)` e o que impede o retry de postar duas vezes.
- **Aqui, ao contrario do `job_registry`, o erro SOBE.** Sem banco nao ha como
  impedir post duplicado, e um corte publicado duas vezes no mesmo canal e pior
  que um corte nao publicado.
- **So `driver.publish()` vai para o executor.** O resto fala com o banco, e o
  engine async esta preso ao loop que o criou -- um `asyncio.run` dentro da
  thread criaria um segundo loop e a conexao pertenceria ao errado. Um teste le
  o AST para garantir.
- **`marcar_publicado` e o unico caminho para `published`** na fila manual, e e
  humano de proposito: o driver entregou o pacote e nao tem como saber que a
  pessoa apertou publicar.
- No painel, a aba **Publicação** (`PublicacoesTab.jsx`): pacote do dia, contas
  (com o driver que atenderia cada uma agora), publicar um projeto e a fila.
  Pequena de proposito, como o bloco 2.3b -- o frontend vai ser trocado.

> `publishers/__init__.py` **exporta os submodulos** (`from . import pacote,
> quota`) porque o `app.py` so faz `import publishers`. Sem isso e
> `AttributeError` em producao e verde no teste, porque o arquivo de teste do
> pacote importa o submodulo e deixa o atributo posto para a sessao inteira.
> Ja aconteceu; ha um teste em subprocesso guardando.

### O pipeline escreve no banco (`job_registry.py`, Fase 3 bloco 3.3)

Fecha a pendencia da Fase 1 -- `sources` e `jobs` nunca eram escritas -- e e
**pre-requisito da Fase 3**, porque `publications` tem FK composta para `clips`.
Grava em tres momentos: fonte + job no submit, `running` ao comecar, e desfecho
+ cortes no `finally` do `run_job_wrapper` (`app._fechar_job_no_banco`).

- **Tudo falha aberto**, como o `db_seed.seed()` no lifespan. O banco e o
  registro do pipeline, nao um participante: perder o registro de um job e
  ruim, perder o job e pior. Nenhuma funcao do modulo levanta.
- **`jobs.id` E o `job_id` do pipeline.** O `db_models.new_id` ja previa isso;
  um id proprio obrigaria a manter um mapa entre painel, pasta e banco.
- **O indice de palavra e DERIVADO da transcricao**, com fim exclusivo (fatia
  de lista) -- o CHECK exige `end > start` e com fim inclusivo um corte de uma
  palavra so seria recusado. A §2 desenhou o contrario (o LLM devolvendo o
  indice), mas o pipeline herdado pede segundos; os segundos exatos ficam no
  `rubric_json`, que e onde a saida do modelo pertence.
- **A transcricao vem do metadata em DISCO**, nunca do `result` em memoria --
  aquele dict e `{'clips', 'cost_analysis'}` e nunca teve transcricao. Ler dali
  devolveria faixa nula para todo corte, e como a coluna aceita nulo (video
  mudo) a tabela encheria de nulo sem um erro sequer.
- **`registrar_clipes` e idempotente por job**: um job retomado depois de um
  redeploy roda o fim do pipeline de novo, e `publications` tem unicidade por
  corte.
- **O estagio so vai ao banco no fim.** O marcador e consumido na *thread* que
  le o stdout do subprocesso; escrever num engine async dali complicaria um
  caminho quente para registrar o que a barra ja mostra ao vivo.

**Tres migracoes**, e todas porque o schema encontrou a realidade pela primeira
vez ao ganhar um escritor:
`8c5d2e91b740` (`accounts.driver_pref` aceita `auto` e nasce assim),
`4a7e1c30d8b2` (a faixa de palavras de `clips` vira anulavel -- video mudo nao
tem palavra a indexar, e sem isso o corte nao podia ser publicado) e
`6d9f4b12e0c7` (`jobs.status` aceita `cancelled`, que a §7 esqueceu e
`publications` ja tinha).

> Ao escrever CHECK com coluna anulavel, lembrar que **CHECK so recusa quando o
> resultado e FALSE**: `end > start` com `end` nulo vale NULL e passa. Os
> `is not null` no `ck_clips_faixa_de_palavras` nao sao redundantes.

### Auth propria (`auth.py`, Fase 4 bloco 4.1)

O "sabado de trabalho" que a §7 previu: o schema ja tinha `tenant_id` em toda
tabela desde a Fase 0.5, faltava quem autenticasse.

- **A auth nao tem flag: ela liga quando algum usuario ganha senha.** O seed ja
  cria `self-host@localhost`, dono do tenant fixo e de tudo o que existe em
  disco. O bootstrap (`POST /api/auth/bootstrap`) **nao cria conta** -- ele da
  senha e e-mail de verdade a esse usuario. Criar um usuario novo ali deixaria
  os jobs e templates de ontem numa conta em que ninguem entra.
- **Zero dependencia nova**, e e decisao: o magic-link (servico de e-mail) e o
  Google OAuth do upstream sairam com o `cloud/`. Trazer qualquer um de volta
  seria um servico pago ou um projeto no Google Cloud para o autor entrar na
  propria ferramenta -- a mesma desproporcao que o `sources/gdrive.py` recusou.
  E-mail e senha, `hashlib.scrypt` da stdlib.
- **O token e assinado, nao e JWT.** Um JWT traria biblioteca para negociar
  algoritmo, e e ai que moram os furos conhecidos (`alg: none`, HS256 x RS256).
  Aqui ha um algoritmo, no verificador, sem campo que o chamador mude.
- **`users.token_version` e a revogacao sem tabela de sessao.** Token assinado e
  stateless: quem o tem entra ate expirar. Bumpar a versao invalida todos os
  daquele usuario -- e o que a troca de senha e o "sair de todos os aparelhos"
  fazem. Trocar a senha e deixar as sessoes antigas vivas resolveria a metade
  que nao importa.
- **A tranca e um middleware, nao decoracao por endpoint.** Uma rota nova nasce
  protegida; quem quiser o contrario escreve o caminho em `ROTAS_PUBLICAS` (hoje
  `/api/config`, `/api/auth/` e `/health`, e ha um teste que congela a lista).
  Um teste varre TODAS as rotas `/api/*` e falha se alguma responder sem sessao.
- **`_auth_ativa()` tem um marcador em disco** (`DATA_DIR/.auth_ativa`) alem do
  banco. Sem ele havia um buraco: com o banco fora do ar, um container novo teria
  de escolher entre destrancar a API ou trancar toda instalacao que nunca quis
  auth (inclusive os testes, que nao montam banco). O banco e a autoridade; o
  arquivo e o piso -- uma vez trancado, nao destranca por falha de leitura.
- **Login nao diz se o e-mail existe**, e gasta um scrypt mesmo quando nao
  existe, para que a resposta nao seja visivelmente mais rapida.
- **`/mcp` fica FORA de `/api/` e e protegido de forma TRANSITIVA**: cada
  ferramenta chama de volta a mesma app por `ASGITransport`, e essa chamada
  passa pelo middleware. Medido, nao assumido -- ha teste.

### O tenant vem da sessao (`db._tenant_atual`, Fase 4 bloco 4.2)

`db.tenant()` sem argumento deixou de significar "o tenant fixo" e passou a
significar **o tenant da requisicao em curso**. Os 22 sitios de chamada em
`app.py`, `publish_queue.py` e `job_registry.py` nao mudaram uma linha -- que e
o que o docstring de `db.tenant()` previa desde a Fase 0.5.

- **E `ContextVar` e nao parametro, e a escolha foi contada.** Enfiar um
  `tenant_id` em 22 chamadas seria 22 lugares para acertar e, pior, 22 onde
  esquecer **nao da erro**: a chamada esquecida continua respondendo e passa a
  ler o tenant errado em silencio. Com o contexto, o sitio esquecido fica certo
  por omissao.
- **A isolacao inteira depende de um detalhe do Starlette**: um `ContextVar`
  posto no middleware tem de valer dentro do endpoint. Se uma versao futura
  rodar `call_next` numa tarefa que nao herda o contexto, o default vira o
  tenant errado -- sem erro e sem log.
  `test_o_contexto_atravessa_o_middleware` e o alarme. Nao apagar.
- **O worker da fila NAO herda o contexto**: ele roda depois da resposta. O
  tenant viaja dentro do proprio job (`jobs[id]['tenant_id']`), e o
  `run_job_wrapper` o repoe antes de qualquer coisa. Sem isso, todo job
  gravaria `sources`/`jobs`/`clips` no self-host.
- **Tres lugares guardam o tenant de um job**, e cada um cobre um buraco do
  outro: o dict em memoria (some no restart), o manifesto de resume (some
  quando o job termina) e o arquivo `.tenant` na pasta (fica). E o mesmo papel
  do `.owner` que o upstream ja escrevia.
- Um job ou manifesto anterior a este bloco cai no self-host: era o unico
  tenant que existia quando foi escrito, e chutar outro seria inventar dono.

### Fila e arquivos isolados por tenant (Fase 4 bloco 4.3)

O criterio de pronto da fase: "uma segunda conta usa o sistema sem ver nada da
primeira". O 4.2 cuidou dos dados; aqui e o que mais aparece na tela.

- **A guarda mora em `_assert_job_owner`**, que `/api/status`, cancelar, apagar,
  baixar tudo e os endpoints de edicao **ja chamavam**. Somar a checagem de
  tenant la protege os nove de uma vez, e o endpoint novo nasce protegido.
  `test_todo_endpoint_de_job_recusa_o_vizinho` cobra isso de todos.
- **404, nunca 403.** 403 confirma que o id existe, e quem sonda ids alheios ja
  ganhou metade da resposta com isso.
- **Os bytes de `/videos/` tem porta propria**, porque um `<video src>` nao
  manda cabecalho `Authorization`: vale a sessao **ou** `?mt=<token>`, um
  portador curto que o painel pendura na URL (o `RestoringStaticFiles` ja
  descrevia essa pendencia no docstring dele). O token carrega o **tenant** e
  nao o usuario -- o dono do arquivo e o tenant. E nao e a sessao de 30 dias na
  query, que vazaria para log de acesso, `Referer` e historico.
- **O frontend monta a URL num lugar so** (`config.js:getApiUrl`). Se cada
  componente montasse a sua, o que esquecesse o token nao tocaria o video -- e o
  bug pareceria "o clipe sumiu", nao "faltou autorizacao".
- **`auth.segredo_texto()`, nunca `segredo_de_sessao().decode("utf-8",
  "ignore")`.** Os 32 bytes sao aleatorios e o `ignore` DESCARTA os que nao
  formam UTF-8: medido, sobram 13 a 21 caracteres. A chave encolhe e envieza
  sem quebrar nada -- so protege menos do que parece.
- **O arquivo do segredo e base64, e o `.strip()` da leitura depende disso.**
  A primeira versao gravava `secrets.token_bytes(32)` cru e lia com
  `.read().strip()` -- mas `bytes.strip()` come espaco em branco ASCII, e 6 dos
  256 valores sao exatamente esses: **4,7% dos segredos** (medido em 200 mil
  sorteios) comecam ou terminam com um deles, e ai quem sorteou assina com 32
  bytes e quem reinicia le 31. E o "segredo novo a cada restart" que a funcao
  existe para impedir, so que uma instalacao em 21 e sem uma linha de log; num
  deploy rolante, as duas instancias dividem o volume e discordam da chave.
  O CI pegou uma vez (run 43). Arquivo antigo de bytes crus continua valendo
  **inteiro**, sem `strip`; texto escrito a mao continua perdendo o `\n` final.
- **`/thumbnails/` continua aberto**, e e limitacao conhecida: as sessoes de
  thumbnail nao tem carimbo de tenant, e o upstream as serve publicamente de
  proposito. Fecha-las exige carimba-las primeiro.

### Agendador com jitter (`scheduler.py`, Fase 4 bloco 4.4, ADR-007)

Fecha a decisao em aberto §10.2. `POST /api/agendar` espalha os cortes de um
projeto pelas proximas janelas; um laco no lifespan publica o que venceu.

- **Os numeros:** 3/dia, janelas 11h/15h/19h, espacamento minimo de 3 h, jitter
  de ±25 min. O 3/dia e o unico que o plano corrobora duas vezes (a conta do §1
  e a proposta do ADR-007). O teto duro e 6/dia, da quota, e o agendador nunca o
  ultrapassa. Os tres primeiros sao **defaults configuraveis** -- calibrar
  horario exige retencao medida, que e a Fase 5.
- **`JITTER_MINIMO_MIN` (5) e piso NAO configuravel.** Pedir zero nao desliga o
  jitter, so o reduz ao piso, com uma linha no log. A alternativa e um
  agendador que um dia roda com zero -- e a assinatura que o §1 manda evitar
  volta sem ninguem decidir que volta.
- **Jitter primeiro, espacamento depois.** Ao contrario, duas janelas a uma
  hora com jitter de -25 e +25 terminariam a 10 min uma da outra: o jitter
  destruindo a regra que o espacamento existe para manter.
- **Nada no passado**: uma janela que ja passou vai para amanha. Agendar para
  tras publicaria tudo de uma vez no primeiro tique, que e o oposto de espacar.
- **`scheduled_at` nulo x preenchido distingue as duas esperas** sem status
  novo: nulo e a fila manual (esperando uma pessoa), com data e a agendada
  (esperando a hora).
- **`publish_queue.reservar()` e um UPDATE condicional**, nao um leia-e-escreva:
  durante um deploy ha duas instancias com o mesmo banco e o mesmo laco, e a
  unicidade `(corte, conta)` nao pega esse caso porque a linha e a mesma.
- **O laco repoe o tenant antes de ler qualquer coisa.** Ele e do servidor e
  atravessa tenants; sem repor, `db.tenant()` nao reclama -- devolve None, e a
  publicacao morre dizendo "corte nao encontrado".
- O painel mostra a agenda **antes** de agendar: descobrir a que horas o sistema
  publicou depois do post e tarde para discordar.

### Calibracao: rubrica x resultado (`calibracao.py`, Fase 5 bloco 5.2)

`GET /api/calibracao` cruza `clips.score` (o que o modelo previu, desde o bloco
3.3) com `metrics` (o que deu, desde o 5.1). E o proposito declarado da fase.

- **Abaixo de `MINIMO_PARA_CORRELACAO` (10) o relatorio NAO publica
  coeficiente.** Com poucos cortes, um rho alto acontece por acaso com
  frequencia -- e uma vez escrito, vira a razao de alguem mexer nos pesos. E o
  mesmo movimento que o ADR-006, o pre-filtro e o `layout_picker` recusaram. Os
  dados crus saem de qualquer jeito: olhar e honesto, afirmar nao.
- **Spearman, e nao Pearson.** A pergunta e sobre ORDEM ("o corte que o modelo
  achou melhor rendeu mais?"). Um modelo que acerta o ranking inteiro mas
  comprime os scores entre 70 e 85 teria Pearson baixo e e exatamente o que
  queremos.
- **Empate recebe posto medio.** Sem isso, tres cortes com score 80 receberiam
  postos 1, 2 e 3 numa ordem arbitraria, e o coeficiente passaria a medir a
  ordem de insercao no banco.
- **Sem variacao devolve None, nunca zero.** Zero seria a afirmacao "medimos e
  nao ha relacao"; None e "nao da para afirmar".
- **Vale a leitura MAIS RECENTE de cada publicacao**, porque `metrics` e serie
  temporal: somar todas contaria o mesmo video uma vez por coleta e daria peso
  maior ao que foi publicado ha mais tempo.
- O contraste entre faixas de score e o que o **ADR-006** espera para fechar o
  piso -- e o relatorio diz que ele so vale quando a amostra por faixa deixar
  de ser um punhado.

### Onde vai o tempo (`timings_report.py`, Fase 5 bloco 5.3)

`GET /api/tempo` agrega os `timings_json` dos jobs. O `job_metrics` media por
estagio desde a Fase 0.5, mas ninguem lia isso ENTRE jobs -- cada execucao
imprimia o proprio resumo no log e o numero morria ali.

- **Mede, nao conserta.** Diante de "esta lento" a tentacao e abrir o `main.py`
  e procurar o culpado. As observacoes apontam para coisas VERIFICAVEIS ja
  escritas neste repositorio (o `WHISPER_DEVICE` que cai para CPU em silencio,
  o teto de cortes do ADR-006, a rota de proxy), nunca para uma conclusao que
  ninguem mediu. Sem estagio dominante, ele **nao inventa culpado**.
- **`fator_tempo_real` = parede ÷ duracao da fonte.** E a unica grandeza que
  responde "esta lento" sem depender de quao longo era o video. Sem a duracao
  da fonte e `None`, nunca 1,0.
- **Os estagios saem na ordem do PIPELINE, nao do tamanho** -- ler na ordem em
  que acontece e o que deixa ver onde ele engasga.
- **`fora_de_estagio_seconds`**: o tempo de parede que nao esta em estagio
  nenhum (espera na fila, subida do subprocesso, pedaco sem instrumentacao).
  Sem essa linha ele e invisivel: cada estagio parece pequeno e nada explica
  por que.
- **Le banco E sidecar, casando por `job_id`.** O sidecar
  `<base>.timings.json` existe desde a Fase 0.5; a coluna so desde o bloco 3.3 --
  so os dois juntos cobrem as primeiras execucoes, que sao justamente as que
  ninguem mediu. Casar por id e nao por contagem: o mesmo job somado duas vezes
  dobra a parede e corta o fator pela metade.

### O instrumento media errado, e errava para o lado pior (16-set-2026)

Primeiro passo de "atacar a lentidao", antes de tocar no pipeline. Dois
defeitos no `job_metrics`, e o pior deles e que **se cancelavam**, entao o
`/api/tempo` respondia plausivel e errado.

- **O laco de cortes e paralelo e o coletor somava.** `CLIP_WORKERS` (3 por
  padrao) workers mediam o MESMO estagio, e cada um somava a propria duracao:
  um render de 200 s de parede gravava 600 s. A soma dos estagios passava da
  parede do job, as fatias somavam mais de 100% e o `fora_de_estagio` ficava
  negativo -- **silenciado por um `max(0, ...)`**. E como o relatorio acusa o
  primeiro estagio acima de 50% **na ordem do pipeline**, quem levava a culpa
  era a transcricao, com um paragrafo sobre conferir a GPU, enquanto o render
  era o bloco maior. Um instrumento que aponta o culpado errado e pior que
  nenhum.
- **Metade do render nao era medida.** O `with stage("05_06_render")` fechava
  logo depois do `render_clip`; marca d'agua, hook grounding (uma chamada de
  LLM por corte), gancho e legenda -- cada um um encode inteiro do clipe --
  rodavam fora de estagio nenhum e caiam no `fora_de_estagio` que o item
  acima ja zerava.

O conserto:

- **`seconds` e OCUPADO, `wall_seconds` e PAREDE.** Os dois sao uteis: o
  primeiro e trabalho gasto (CPU-segundos), o segundo e o que a pessoa
  esperou. A parede e a **uniao dos intervalos**, contada na entrada -- `n`
  conta quantos estao abertos com aquele nome e o trecho so entra quando o
  ultimo fecha. Nos quatro estagios sequenciais as duas coincidem.
- **A pilha de atribuicao de tokens e thread-local.** Era global, e num pool
  isso creditava a chamada de LLM de um worker ao estagio que outro tivesse
  deixado no topo -- qual deles dependia do escalonador.
- **`substage()` mede sem anunciar.** O marcador do stdout e a BARRA do
  painel, e `_stage_view` devolve `stage_index` 0 para qualquer nome fora de
  `PIPELINE_STAGES`, ou seja, a barra volta ao comeco. Medicao fina nao pode
  custar isso. O laco de cortes ganhou seis: corte, reenquadra, marca d'agua,
  hook grounding, gancho, legenda.
- **O relatorio DENUNCIA o dado antigo** em vez de esconder: quando a soma
  nao cabe na parede, ele diz que aquele job foi medido antes do conserto e
  que a ordem de culpa nao vale. Cai para `seconds` quando falta
  `wall_seconds` -- o sidecar que ja esta em disco nao tem o campo.
- `tests/test_render_instrumentado.py` le a arvore sintatica e falha se um
  passe do corte voltar a rodar fora da medicao; com o `main.py` de antes ele
  nomeia os quatro. O teste da uniao de intervalos usa **relogio falso**, nao
  `sleep`: trocando `job_metrics.time`, nunca `job_metrics.time.time`, que e o
  modulo global.

### `python diagnostico.py`: medicao e ambiente na mesma frase

O relatorio do 5.3 sabe dizer QUAL estagio dominou e termina mandando conferir
a GPU **a mao**. Aqui a conferencia e feita, e a conclusao so existe com as
**duas metades**: "a transcricao e 70% do tempo" nao e defeito num video muito
falado, e "o whisper esta em CPU" e apenas verdade numa maquina sem placa --
juntas, viram um proximo passo.

- **Dois padroes que ninguem escolheu, e nenhum grita.** `WHISPER_DEVICE` nasce
  `cpu` e `FFMPEG_ENCODER` nasce `x264`. O segundo pesa mais do que parece: a
  cadeia de um corte e corte -> reenquadra -> [marca] -> [gancho] -> legenda,
  ou seja **3 a 5 encodes do mesmo clipe**, os dois primeiros a `-crf 18`.
- **"Nao deu para saber" nunca sai como "sim".** As sondagens devolvem `None`
  fora do container (o `ctranslate2` nao importa, o ffmpeg pode nao existir), e
  um `else` que juntasse `None` com `True` afirmaria que a placa esta em uso
  justamente quando ninguem olhou. Ha teste parametrizado para isso.
- **A placa e perguntada ao `ctranslate2`**, que e quem o faster-whisper usa;
  `torch.cuda.is_available()` responde por outra biblioteca. E o nvenc e
  perguntado a sonda do proprio `ffmpeg_utils`, nao a `ffmpeg -encoders`, que
  lista o encoder compilado mesmo sem driver para ele.
- **Le sidecar, nao banco**: o sidecar existe em todo job desde a Fase 0.5 e
  nao exige levantar o engine async num CLI. O `/api/tempo` junta os dois e
  continua sendo o caminho do painel, para o historico inteiro.
- `conclusoes()` e funcao pura sobre dois dicts, entao o CI exercita a conta
  sem GPU, sem ffmpeg e sem job.
- **`caminho_da_gpu()` diz ONDE a corrente arrebentou, nao apenas que
  arrebentou** (17-set-2026). Era o unico buraco que restava: o diagnostico
  respondia `placa p/ o whisper: nao` e as duas causas possiveis tem o mesmo
  sintoma e correcoes de custo muito diferente -- imagem sem as libs de CUDA
  pede `reconstruir.bat` (15 a 40 min), placa nao reservada pede
  `subir.bat` (segundos) -- os dois descobrem a placa sozinhos desde
  22-set-2026. Escolher entre as duas era cara ou coroa, e a coroa custava 40
  minutos.
  - **A imagem e sondada pelo `LD_LIBRARY_PATH`**, cujo comentario no
    Dockerfile diz, com estas palavras, que os caminhos "simplesmente nao
    existem em imagens CPU". A lista vem dele, entao a sonda continua certa se
    o Dockerfile mudar os caminhos. Pasta vazia conta como ausente: o `pip
    install` cria a pasta COM arquivos.
  - **O driver e sondado pelo `nvidia-smi` e pelos nos de dispositivo**,
    incluindo `/dev/dxg` -- no Docker Desktop com WSL 2 o no e esse, e olhar so
    `/dev/nvidia0` daria `nao` numa maquina Windows funcionando.
  - **E a unica conclusao que sai sem medicao**, e por isso e CONDICIONAL: o
    container nao sabe se a maquina tem placa. A regra das duas metades existe
    para nao prescrever mudanca no que talvez esteja certo -- "a corrente
    arrebentou aqui" e fato observado, nao palpite. Antes disto, um container
    sem placa nenhuma respondia so "rode um video e volte", mandando esperar
    uma medicao para descobrir o que ja estava na tela.
- **O `motivo_do_nvenc` le o erro que a sonda do pipeline joga fora**
  (17-set-2026). `ffmpeg_utils._probe_nvenc` manda o stderr para `DEVNULL` de
  proposito -- ela responde um booleano e roda antes de cada encode, nao pode
  poluir o log de todo job. Mas `nvenc: nao` sozinho manda adivinhar, e
  "libnvidia-encode ausente" (comum no Docker Desktop com WSL 2: o CUDA passa e
  o NVENC nao) e "sem sessao livre na placa" nao tem o mesmo conserto. O
  diagnostico reexecuta a MESMA sonda capturando o stderr.
  - **`ffmpeg_utils.comando_da_sonda_nvenc()` e a definicao unica.** Duas
    copias do comando divergem no dia em que uma delas mudar, e ai o motivo
    passa a explicar outra coisa. Ha teste lendo a fonte.
  - **Erro fora da lista conhecida sai CRU**, na ultima linha do ffmpeg.
    Inventar explicacao para erro que ninguem viu e o oposto do que este modulo
    faz.
  - **Cobra so quem PEDIU**: com `FFMPEG_ENCODER=x264` o libx264 e escolha, nao
    queda. Com `auto`/`nvenc` e expectativa nao cumprida em silencio, e o preco
    e todo encode da cadeia de um corte na CPU.

### Coletor de metricas (`metrics_collector.py`, Fase 5 bloco 5.1)

A tabela que a §7 chama de "mais valiosa do projeto" deixou de ser vazia.

- **Coletar exige escopo que o upload deliberadamente nao pediu**, e a saida
  NAO foi ampliar o token de publicacao: e um segundo consentimento, so de
  leitura, noutro endereco de cofre (`youtube-metrics/<handle>`, emitido por
  `python youtube_oauth.py --leitura`). Duas credenciais pequenas em vez de uma
  grande. Ha teste garantindo que `youtube_oauth.ESCOPO` continua sendo so
  `youtube.upload` -- "a Fase 5 precisou" e o tipo de motivo que desfaz uma
  decisao boa sem ninguem notar.
- **`metrics` e serie temporal, nao cache**: cada coleta ACRESCENTA linha. A §7
  poe `collected_at` e nao poe unicidade por publicacao exatamente por isso.
- **None nao e zero**, nos tres lugares: parse de views, parse de retencao e a
  regra de nao gravar linha sem numero nenhum.
- **A retencao e lida pelo NOME da coluna**, nunca pela posicao: a ordem muda
  com a lista de metricas pedida, e ler pela posicao gravaria views no campo de
  retencao sem dar erro.
- O `videos.list` custa 1 unidade e e debitado do mesmo teto de 10.000/dia, com
  `upload=False` para nao mentir no contador de uploads.

### Fluxo de git

Desenvolvimento em `main`. O upstream fica como remote
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
| POST | `/api/auth/bootstrap` | Da senha ao dono que ja existe (uma vez so) |
| POST | `/api/auth/login` | Entra e devolve o token |
| GET | `/api/me` | Quem sou eu |
| GET/POST | `/api/usuarios` | Contas da instalacao (criar: so o dono) |
| GET/POST/DELETE | `/api/contas` | Contas de plataforma (Fase 3) |
| POST | `/api/publicar` | Publica cortes de um projeto numa conta |
| GET | `/api/publicacoes` | A fila: o que subiu e o que espera a mão |
| GET | `/api/publicacoes/pacote` | O ZIP do dia: cortes + legendas prontas |
| GET/POST | `/api/agenda`, `/api/agendar` | A agenda em vigor, e agendar um projeto |
| GET/POST | `/api/metricas`, `/api/metricas/coletar` | Views e retenção coletadas |
| GET | `/api/tempo` | Onde vai o tempo de processamento |
| GET | `/api/calibracao` | O que a rubrica do modelo acertou |
| POST | `/api/asr/aquecer` | Sobe o modelo de transcricao na placa (o painel chama enquanto aberto) |
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

### Controle de job: cancelar, listar, apagar, progresso (13-set-2026)

Nada disto existia, e a ausencia do cancelamento era um bug de verdade: o
handle do `Popen` so vivia como variavel local de `run_job`, entao **nenhum
endpoint alcancava o processo**. Recarregar a pagina nao parava nada; matar o
container tambem nao, porque o manifesto de resume ressuscitava o job no boot
seguinte.

- `_job_processes[job_id]` publica o handle; `_cancelled_jobs` marca a
  intencao. O segundo e consultado em **tres** lugares e os tres importam: o
  `run_job` (cancelado nao e `failed` -- um processo morto por sinal volta com
  codigo != 0), a fila (nao comecar um job cancelado que esperava vaga) e o
  scan de resume (nao ressuscitar).
- `POST /api/jobs/{id}/cancel` faz os tres passos **nesta ordem**: marca,
  **apaga o manifesto**, mata o processo. O passo do meio e o unico cuja falta
  nao aparece na hora -- sem ele o job volta 30s depois.
- `GET /api/jobs` lista projetos (memoria + disco, sem o log). `DELETE
  /api/jobs/{id}` cancela **antes** de apagar a pasta: remover o diretorio
  debaixo de um `main.py` vivo deixa um processo orfao escrevendo no vazio.
- **Progresso e por estagio, nunca porcentagem.** `job_metrics.stage()` imprime
  `__STAGE__BEGIN <nome>` no stdout -- o canal que ja existe entre o subprocesso
  e o `app.py` -- e o `enqueue_output` consome e **descarta** a linha, como ja
  fazia com `CLIP_READY`. O `_stage_view` devolve `stage_index`/`stage_total`
  sobre `PIPELINE_STAGES`. Nao ha porcentagem porque nao ha medicao: a
  transcricao nao reporta progresso e o render varia com o numero de cortes.
  Uma barra que mente e pior que barra nenhuma.
- No painel: a aba **Projetos** (`ProjectsGrid.jsx`, ord 02) com uma grade de
  cartoes, um por video -- abrir, apagar (com confirmacao, porque leva os
  cortes junto) e criar novo. A **capa e o proprio clipe**
  (`<video preload="metadata">`): o navegador baixa so o cabecalho e desenha o
  primeiro quadro, entao nao ha campo de thumbnail a criar no pipeline. O
  `_resumo_do_job` manda `first_clip_url` para isso.
- Dentro de um projeto o cabecalho tem **dois** botoes: `← projetos` (voltar) e
  `+ novo`. Antes havia so "New Project", que **cria** em vez de voltar -- de um
  projeto aberto nao existia caminho nenhum para escolher outro.
- `ProjectsList.jsx` continua como a lista compacta sob o formulario da tela
  inicial; as duas fazem polling de 5s **so** enquanto ha job vivo.
- `tests/test_job_control.py` cobre os tres endpoints e o marcador.

### A marca e Virtu Clips (24-set-2026)

OpenShorts (do upstream) virou **Cortes** em 13-set-2026 e **Virtu Clips** em
24-set-2026, com a logo do autor: `marca/virtu-clips.png` -- VIRTU em letra
liquida, a barra com o alfinete, CLIPS em caixa alta pesada e condensada --,
branca sobre transparente. Feita para fundo escuro: todo lugar que a usa poe
preto por baixo.

- **Um lugar desenha, todos chamam: `ajudante/marca.py`.** O icone do
  instalador e do atalho, as imagens do assistente do instalador, o icone da
  bandeja e os arquivos do site. O site nao roda Python no build, entao
  `dashboard/public/virtu-clips.png`, `favicon.png` e `apple-touch-icon.png`
  sao versionados: trocou a logo, rode `python ajudante/marca.py` e versione o
  resultado. `tests/test_marca.py` falha se eles ficarem para tras.
- **Abaixo de 48 px a logo e borrao** (VIRTU e CLIPS empilhados num icone de
  16 px teriam ~4 px de altura cada). Ali entra o monograma: um V na Anton, a
  letra do CLIPS. O `.ico` leva os dois desenhos e o Windows escolhe pelo
  tamanho -- ate 40 px o V, de 48 para cima a logo. O favicon do site e o V.
- **O site e preto e branco.** O acento deixou de ser o latao laranja do
  sistema herdado ("Lumen") e virou o branco: botao principal branco com letra
  preta, como a logo. Os NOMES ficaram (`brass`, `brassink`...: ~170 usos);
  mudou o valor, no `tokens.css` e no `tailwind.config.js`. Os titulos sao
  Anton em caixa alta (`font-display uppercase tracking-wide`; era Instrument
  Serif em minusculas), servida de `public/fonts/` como as outras, cortada do
  `fonts/Anton-Regular.ttf` que o motor ja usa nos ganchos.
- **Containers `virtu-clips-*`.** O nome do projeto do compose nao mudou,
  entao o `up -d` do `atualizar.bat` recria os tres no lugar, sem sobrar os
  antigos segurando as portas.
- **Ficou o nome antigo no que ninguem ve, de proposito**, pelo mesmo motivo
  do `SESSION_KEY` (que continua `openshorts_session`): renomear so teria
  custo.
  - as chaves de localStorage `cortes_*` e as variaveis `CORTES_*`;
  - no ajudante, o mutex `Local\CortesAjudante` e o valor `Cortes` do
    "iniciar com o Windows" (`ajudante.VALOR_NO_INICIO`): o instalador novo
    SOBRESCREVE o valor de uma instalacao antiga, e dois valores seriam dois
    ajudantes no login -- o segundo so abriria o site;
  - `cortes-app` no `dashboard/package.json`: o `atalhos\atualizar.bat` manda
    reconstruir a imagem (40 min) quando um `package.json` muda;
  - o template semeado "Padrao Cortes": o seed procura pelo NOME, e renomear
    criaria uma segunda linha em todo banco que ja existe. E "cortes" ali e o
    substantivo comum.

### GPU: sao dois passos, e os atalhos dao os dois

`--build-arg GPU=1` instala as libs de CUDA na imagem e **nao** faz o container
enxergar a placa. A reserva do dispositivo esta em `docker-compose.gpu.yml`,
uma sobreposicao (`-f docker-compose.yml -f docker-compose.gpu.yml`), separada
de proposito: `reservations.devices` e exigencia, e numa maquina sem GPU o `up`
falharia em vez de cair para CPU. Sem a placa no container,
`WHISPER_DEVICE=cuda` cai para CPU **em silencio** -- funciona, so que lento.

Desde 22-set-2026 o overlay tambem passa `GPU=1` ao build, e os atalhos poem o
overlay sozinhos quando o `nvidia-smi` do Windows responde. Ver a secao abaixo.

### Os atalhos tiravam a placa (22-set-2026)

"Esta mais rapido, mas ainda demora": o log mostrava 5 min de transcricao para
10 min de audio numa RTX 3060. Nao era o pipeline -- era o `atualizar.bat`, que
eu mandei rodar. Ele fazia `docker compose up -d` so com o arquivo base, e isso
**recria** o backend sem a placa: sem o overlay a configuracao do servico muda
(medido com `docker compose config --hash=backend`, os dois hashes diferem), e
o compose recria o container quando ela muda. Sem o overlay o `WHISPER_DEVICE`
nem chega a ser `cuda`: roda o padrao, `small` em CPU int8, sem erro -- e sem a
linha `⚠️ [ASR] whisper GPU failed`, que so existe para a queda de cuda.

- **A decisao "tem placa?" mora num lugar so: `atalhos/_modo-gpu.bat`**, que
  pergunta ao `nvidia-smi` do Windows e poe `COMPOSE_FILE` no ambiente. O
  proprio `docker compose` le essa variavel, entao todo comando seguinte na
  mesma janela (up, build, restart, ps) usa os mesmos arquivos sem repetir
  `-f`. Separador `;` explicito (`COMPOSE_PATH_SEPARATOR`). Conferido com o
  binario do compose: `COMPOSE_FILE` com `;` da o mesmo hash que os dois `-f`.
- **Todo `up` passa pelo `_subir.bat`**, que cai para CPU e AVISA se o Docker
  recusar a placa (Docker Desktop fora do motor WSL 2). Devagar e melhor que
  parado; devagar em silencio era o defeito.
- **`subir-gpu.bat` e `reconstruir-gpu.bat` viraram apelidos.** Ter dois de
  cada era o proprio defeito: quem clicava no errado perdia a placa.
- **O overlay passa `GPU=1` ao build**, entao o `reconstruir.bat` -- que o
  `atualizar.bat` manda rodar quando uma dependencia muda -- nao constroi mais
  uma imagem sem CUDA. O `build` fica fora do hash de recriacao do compose:
  acrescenta-lo nao recria nada sozinho.
- **O `atualizar.bat` se reescreve enquanto roda**, e o cmd.exe continua da
  mesma posicao EM BYTES no arquivo novo. Tudo ate a linha do `git pull` tem de
  ficar identico; `tests/test_atalhos_gpu.py` congela esse trecho. Mudar ali
  exige duas etapas (o docstring do teste diz como).
- **O log do job diz qual whisper rodou** (`transcribe_backends.
  linha_do_whisper`). Em CPU a frase e condicional -- o container nao sabe se a
  maquina tem placa.
- **De brinde, um bug que estava la desde a criacao dos atalhos**: no
  `_garantir-docker.bat`, um `)` dentro de um `echo` no bloco `if` fechava o
  bloco no meio, e o `exit /b 1` passava a rodar sempre -- a espera de 3 min
  pelo motor desistia na primeira volta. O teste novo que pegou isso confere
  todos os atalhos: nada de parentese em `echo` dentro de bloco, nem `%` em
  `REM` (o cmd expande `%` antes de reconhecer o comentario).
- **Nao mandar comando `docker compose` cru ao autor sem o overlay.** A mao,
  sem os dois `-f`, e exatamente o `up` que recria o backend sem a placa.
- **Um caso de transicao, conhecido e barulhento:** numa maquina com placa e
  uma imagem construida SEM CUDA (so pelos atalhos antigos), o `subir.bat` passa
  a pedir a placa e o whisper grande cai para CPU. O log mostra o `⚠️ [ASR]
  whisper GPU failed` e a linha nova, e o diagnostico manda o `reconstruir.bat`.
  A maquina do autor nao esta nesse caso: a imagem dele ja tem as libs.
  Distinguir isso no proprio `_modo-gpu.bat` exigiria um LABEL no Dockerfile --
  e mudar o Dockerfile faz o `atualizar.bat` mandar reconstruir, 40 minutos.

### Velocidade, rodada 2: o que o resumo do job mostrou (22-set-2026)

Com a placa de volta, o mesmo video de 10,5 min caiu de ~20 min para 608 s. O
resumo do proprio job (`job_metrics`) dividiu assim:

| estagio | parede | o que era |
|---|---|---|
| 01_ingest | 41 s | download (com um 403 no meio, resolvido pelo retry) |
| 03_transcribe | 113 s | 43 s de transcricao; o resto, muito provavelmente, a PRIMEIRA descida do `large-v3-turbo` (~1,6 GB) -- conferir no proximo job |
| 04_detect | 86 s | tres chamadas ao Gemini, cada uma depois de um 404 do Groq |
| 05_06_render | 366 s | 338 s de reenquadramento (790 s ocupados nos 3 workers) |

- **Classificar as cenas lia o clipe por seek** (`amostragem_cenas.py`). Cada
  `cap.set(CAP_PROP_POS_FRAMES)` num H.264 decodifica desde o keyframe
  anterior (GOP de 250), e isso -- nao o BlazeFace -- custava 1-4 s POR CENA,
  27-77 s por corte. Uma passada com `grab`/`retrieve`, medida num clipe 1080p
  de 50 s com 23 cenas: 25,8 s -> 5,8 s, **quadros identicos 115/115**. Um
  teste compara com o algoritmo antigo em 300 clipes sorteados: as decisoes
  TRACK/GENERAL sao as mesmas. Mora fora do `main.py` para o CI alcancar.
- **O reenquadramento ganhou filhos no resumo**: `06_reenquadra/1_cenas`
  (TransNetV2), `/2_estrategia`, `/3_trajetoria` e `/4_ffmpeg` (todo `_run`
  do `reframe_v2`). A barra no nome faz o resumo imprimir o filho recuado sob o
  pai, e o tempo dele esta CONTIDO no do pai -- nao somar. O proximo alvo sai
  daqui, e nao de palpite.
- **O Groq estava fora do ar para este projeto desde 16-ago-2026**: o
  `llama-3.3-70b-versatile` foi aposentado (registro de modelos do LiteLLM,
  `deprecation_date`), e todo job tentava, levava 404 e caia no Gemini gratis,
  que e mais lento e treina com o conteudo. Padrao trocado para
  `openai/gpt-oss-120b`, e a cascata passou a lembrar, POR JOB, do provedor
  cujo modelo nao existe (`llm_cascade._MODELO_INEXISTENTE`): avisa uma vez,
  com o `GROQ_MODEL=` a pôr no `.env`, e nao gasta cota fantasma. Erro
  passageiro (429, 503) continua sendo tentado de novo -- so o 404 de modelo
  desliga.
- **A linha `💰 Total cost (...)` passou a dizer quem RESPONDEU**; dizia o
  primeiro da cascata, entao anunciava llama enquanto o Gemini trabalhava.
- **Processar no navegador de quem usa foi considerado e recusado.** O
  programa JA roda na maquina e na placa de quem o instala (Docker + atalhos).
  No navegador ele ficaria mais lento, nao mais rapido: o ffmpeg em WebAssembly
  e uma ordem de grandeza mais lento que o nativo, o whisper grande seriam
  ~1,5 GB baixados por pessoa, notebook sem placa fica pior que o servidor, e o
  download do YouTube nem pode acontecer ali (e Python, e o navegador bloqueia
  por CORS). Seria reescrever o pipeline inteiro para perder velocidade. Para
  poucas pessoas, os caminhos sao: cada uma instala como o autor, ou o autor
  serve pela maquina dele -- a auth multiusuario da Fase 4 ja existe para isso.

### Os projetos ficam no disco de quem usa (22-set-2026)

O autor viu `416MB` no Docker Desktop e perguntou se o projeto estava "dentro
do Docker". Nao estava: o numero e a MEMORIA do container, e `output/` e a pasta
do repositorio montada no container (`./output:/app/output`). Mas havia duas
limpezas que apagavam o trabalho sozinhas, e as duas foram desligadas:

- **`JOB_RETENTION_SECONDS` nasce 0 (nunca) no self-host**, e nao 86400. As 24h
  do upstream eram o mesmo defeito da issue #46 deles, so que um dia depois.
- **`OUTPUT_MAX_GB` nasce 0.** O upstream justificava apagar os mais antigos com
  "ja estao no R2, so custa um re-download" -- e o R2 saiu com o `cloud/`.
- **O 0 precisa de guarda, e ela esta em `app._limpar_uma_vez`.** Sem ela,
  `now - mtime > 0` vale para todo arquivo: o valor que quer dizer "nunca"
  apagaria tudo na primeira volta, inclusive o upload do job que esta rodando.
  O `_sweep_retained_sources` ganhou a mesma leitura (0 = nunca nos dois
  relogios). `tests/test_retencao.py` pega a guarda removida.
- **Apagar o projeto leva `uploads/<job_id>_*` junto.** Antes a varredura de
  24h tirava o video enviado; sem ela, o botao de apagar e o unico caminho.
- `UPLOADS_MAX_GB` (15) continua: ali ficam copias de arquivos que a pessoa ja
  tem, e o teto so custa o re-editar de um projeto antigo enviado por upload.

**Apagar apaga tudo, e diz quando nao conseguiu** (22-set-2026, segunda volta:
"excluo o projeto, volto no Clip Generator e ele ainda esta la"):

- **`_apagar_pasta_do_job` devolve o que SOBROU**, com tres tentativas (0 /
  0,5 / 1,5 s), e o endpoint responde 409 com o nome do arquivo. Era
  `rmtree(ignore_errors=True)`: no Docker Desktop a pasta e do Windows, que nao
  apaga arquivo aberto, e o painel dizia "apagado" com o video no disco. Se
  sobrava o metadata, o projeto voltava na listagem; se sobrava so o video,
  ninguem mais o via. Roda numa thread: e rmtree de centenas de MB com espera.
- **O job nasce em grupo de processos proprio** (`start_new_session=True`), e
  cancelar mata o GRUPO (`_sinalizar_grupo`). Matar so o `main.py` deixava os
  ffmpeg filhos vivos, gravando na pasta recem-apagada. **A guarda nao e
  enfeite**: so ha `killpg` quando o grupo e do proprio job (pgid == pid e
  diferente do grupo do servidor) -- um processo sem grupo proprio esta no
  grupo do uvicorn, e o `killpg` ali derrubaria o servidor.
- **O registro no banco sai junto** (`job_registry.apagar_job`: job, cortes
  pelo cascade, fonte se ficou orfa), **menos o que ja foi publicado**: o
  cascade levaria `publications` e `metrics`, o historico que a calibracao le.
- **O painel solta o projeto apagado**: `onApagado` nas duas listas chama o
  `handleReset` quando o apagado e o aberto. Sem isso o Clip Generator seguia
  mostrando os cortes de um projeto que nao existia mais.
- **Nada do processamento fica dentro do Docker.** Os dois temporarios que
  caiam no /tmp do container (os comandos do render e o WAV do Parakeet) vao
  para a pasta do projeto; `tests/test_nada_dentro_do_docker.py` falha num
  `tempfile` sem `dir=`. E o log do container ganhou teto (3 x 10 MB,
  `x-log-com-teto` no compose): o backend repete ali cada linha de todo job, e
  esse log mora no .vhdx do Docker, que no Windows cresce e nao encolhe.
- **O que o Docker Desktop mostra nao e video**: "Container memory" e RAM (sobe
  enquanto processa, com o whisper e os quadros na memoria), e o "Disk" do
  rodape sao as imagens (Python, torch com CUDA, ffmpeg) e o cache de build.
  `atalhos\abrir-pasta-dos-cortes.bat` abre o `output\`, que e a resposta
  visivel para "onde estao os videos".

### O painel perguntava a config uma vez so (22-set-2026)

"Esta pedindo chave de API, antes funcionava; apertei F5 e sumiu." O
`AuthContext` pedia `/api/config` UMA vez, e a falha virava a config padrao --
sem `localLlm`, entao o painel concluia que nao havia chave de LLM. E o que
acontece logo depois do `atualizar.bat`: o frontend volta antes do backend.

- **A config e pedida ate responder** (1, 2, 4, 5, 5... s). Enquanto isso o
  painel mostra "conectando ao servidor" (`EsperandoServidor`), e depois de
  15 s diz o que conferir. Tela vazia ali seria o painel em preto de novo.
- **`keysMissing` exige `configCarregada`**: antes da config, `localLlm` nulo
  quer dizer "ainda nao sei", e nao "nao tem". O servidor continua sendo a
  autoridade -- o `/api/process` recusa sem LLM de qualquer jeito.

### O log diz a hora em que cada linha nasceu (22-set-2026)

"A contagem de minutos nao passa": o painel escrevia `new Date()` ao DESENHAR
cada linha, entao todas saiam com a hora de quem olhava. A hora certa so existe
no servidor, quando a linha chega do subprocesso.

- **`app.LinhasDoLog` e uma `list` que guarda a hora no `append`.** Continua
  sendo lista de texto porque `_job_error_text`, o MCP e os testes a leem assim;
  a hora fica em `.tempos`. Todo job nasce com ela -- um teste le a arvore do
  `app.py` e falha se um `'logs': [...]` cru voltar. O `__reduce__` existe
  porque sem ele um `copy` dobraria a lista de horas da ORIGINAL.
- **`/api/status` manda `log_times` (epoch)**, e o painel formata no fuso do
  navegador -- o container roda em UTC. Lista comum no lugar manda `null`, e a
  tela mostra a linha sem hora: melhor que a hora errada.
- **O "copiar log" leva a hora na frente** (`[15:29:03] ...`): quem cola o log
  para investigar lentidao ve quanto cada passo levou.

### Velocidade, rodada 3: o reenquadramento numa passada so (22-set-2026)

O log do job de 608 s mostrou o `06_reenquadra` custando 2,5 s por segundo de
clipe fora da classificacao de cenas. Parte disso era o render: **um ffmpeg por
cena**, mais um concat -- 24 processos para um corte de 50 s com 23 cenas, cada
um subindo o encoder de novo (no NVENC, um contexto CUDA) e voltando ao keyframe
anterior a cena (GOP 250 = ate 8 s decodificados para jogar fora).

- **Agora e um ffmpeg por clipe** (`reframe_v2._render_numa_passada`): cada
  cena vira um ramo `split -> trim -> grafo -> concat`. Os grafos de trecho sao
  os MESMOS de antes; `grafo_numa_passada` so troca o encanamento. Medido em
  x264 (sem NVENC, que nao ha aqui): 15,7 s -> 11,1 s num clipe de 50 s.
- **E consertou um defeito que ninguem tinha visto: o render por trecho
  atrasava a imagem.** O corte por TEMPO (`-ss`/`-t`) saia com 0 a 2 quadros a
  mais por trecho -- 1515 para 1500 --, e o audio vem inteiro do clipe, entao a
  cada troca de cena a imagem ficava mais para tras do som: meio segundo no fim
  daquele clipe. `trim` corta por QUADRO, e a saida bate quadro a quadro com a
  referencia (framemd5, a 30 e a 29,97 fps). O teste com ffmpeg de verdade da
  94 quadros para 90 se o render voltar a ser por trecho.
- **O `setpts=PTS-STARTPTS` apaga a taxa de quadros do fio**, e sem ela o
  encoder cai em 25 fps e JOGA QUADRO FORA (1251 de 1500). Por isso o `-r
  <taxa>` na saida. **Nao trocar por `fps=` depois do concat**: parece
  equivalente e come o ultimo quadro. `taxa_racional` devolve `30000/1001`, e
  nao `29.97`, que desalinharia do relogio do video.
- **`crop@c{idx}` e nao `crop@c`**: o `sendcmd` manda o comando a TODO filtro
  com aquele nome, e num grafo so os trechos se moveriam uns aos outros.
- **O render por trecho ficou como reserva** (`_render_por_trecho`), e cair nele
  imprime uma linha `⚠️ Render numa passada falhou`. Em silencio, a regressao de
  velocidade (e de sincronia) passaria despercebida.
- **O CI instala `imageio-ffmpeg`** (um ffmpeg estatico pelo pip) para rodar a
  comparacao quadro a quadro; sem ele esses testes pulam.

O que falta medir, e o proximo log com os subestagios (`06_reenquadra/1_cenas`
... `/4_ffmpeg`) vai dizer: cada clipe ainda e decodificado inteiro seis
vezes (TransNetV2, estrategia, trajetoria, render, gancho, legenda), e gancho e
legenda sao dois encodes a mais. Juntar essas passadas e o proximo alvo --
depois de ver o numero, nao antes.

### Velocidade, rodada 4: o log de 343 s (23-set-2026)

O mesmo video de 10,5 min caiu de 608 s para 343 s com a rodada 3. O resumo do
job dividiu assim: `01_ingest` 40 s, `03_transcribe` 61 s (17 s so para
carregar o modelo), `04_detect` 27 s (15 s esperando o Groq a toa) e
`05_06_render` 212 s, com ~42 s de ffmpeg de reenquadramento por corte de ~30 s.

- **O fundo desfocado e borrado em 1/4 da resolucao**
  (`ffmpeg_utils.fundo_desfocado`, usado pelo GENERAL, pelo WIDE e pelo
  INSET). A cadeia antiga ampliava o quadro inteiro para 3413x1920, jogava dois
  tercos fora e borrava 1080x1920 -- para produzir um borrao. Medido numa CPU
  de 4 nucleos: o grafo GENERAL foi de 105 para 206 quadros/s; SSIM do fundo
  0,9993 num video comum e 0,989 num zone plate. O renderizador v1 do upstream
  ja borrava assim, em OpenCV; o v2 e que tinha voltado a resolucao cheia.
  - **Nao reduzir com `fast_bilinear`.** Foi a primeira tentativa e serrilha:
    SSIM 0,955 no zone plate, e o fundo tremendo 44% mais numa textura em
    movimento. `tests/test_fundo_desfocado.py` mede com ffmpeg de verdade contra
    a cadeia antiga, que fica no teste como referencia.
- **O 429 com dica** (`llm_cascade.espera_antes_de_repetir`). O Groq diz
  quanto esperar ("try again in 20.4s"), e a regra antiga esperava 5 s e 10 s
  para levar o mesmo 429 tres vezes. A paciencia com um provedor continua a
  mesma (15 s); a dica so decide como gasta-la: se cabe, espera exatamente
  aquilo e volta ao mesmo provedor; se nao cabe, passa ao proximo na hora.
  Nunca espera mais que antes, e nunca desiste de quem a regra antiga ainda
  alcancaria. Deve acontecer em todo video desse tamanho: as duas chamadas de
  score gastam ~6,6 mil dos 8 mil tokens por minuto do Groq gratis.
  - O corpo do erro chega cortado em 300 caracteres (`llm_backend`), e a dica
    do Groq fica perto do caractere 215. O teste usa o corpo JA cortado.
- **O whisper carregando durante o download foi TENTADO E REVERTIDO no mesmo
  dia.** Uma thread de fundo subia o modelo enquanto o yt-dlp baixava, para
  esconder os ~17 s de carga (import, CUDA e ~1,6 GB de pesos lidos do
  `.cache/` da pasta do projeto, que no Docker Desktop e disco do Windows). O
  modelo subiu inteiro, e a primeira transcricao travou para sempre na
  placa, sem erro e sem log, na maquina do autor. A causa nao foi isolada --
  aqui nao ha placa --, e duas diferencas em relacao ao caminho que sempre
  funcionou sao suspeitas: a thread que criou o modelo (e os recursos de CUDA
  por thread do ctranslate2) ja tinha acabado quando ele foi usado, e o CUDA
  subiu enquanto o processo fazia fork para o yt-dlp, o deno e o ffmpeg.
  `test_o_whisper_nao_carrega_em_thread_de_fundo` trava a volta. **Nao
  reintroduzir sem reproduzir na maquina do autor antes.**
  - O caminho seguro para os 17 s continua sendo o outro: levar o `.cache/`
    para um volume do Docker, que carrega do disco Linux. Poe ~1,6 GB no disco
    do Docker, que o autor pediu para nao crescer -- decisao dele.
- **Duas linhas novas por corte no log**: `🎞️ corte N: 13 cena(s), 900
  quadros: GENERAL 62% (5), TRACK 38% (8)` e `⏱️ corte N: ffmpeg do
  reenquadramento, 900 quadros em 42.0s (21 q/s)`. O log dizia "13 cenas" e
  nada sobre quantos QUADROS eram plano aberto, o layout caro -- sem isso,
  "o render esta lento" nao se separa em "o conteudo e caro" e "a maquina esta
  sem folga". Quadros e nao cenas porque e o quadro que custa.

Ficou de fora, de proposito:

- **Gancho e legenda num encode so.** Economizaria um encode por corte, mas o
  `hooked_` intermediario e o que o `/api/subtitle` usa para trocar a legenda
  sem empilhar uma sobre a outra: `_strip_burned_captions` so volta um nivel
  se o arquivo de baixo existe. Sem ele, a legenda nova sairia por cima da
  velha -- o defeito que o `_reapply_captions` documenta.
- **A extracao dupla do yt-dlp** (~5 s: o titulo numa instancia, o download
  noutra, e cada uma inicializa o provedor de PO token por ~3 s). Mexer no
  download sem poder testar contra o YouTube de verdade e o risco errado para
  5 s.
- **Mais `CLIP_WORKERS`.** Sem saber se a maquina tem folga, mais workers pode
  ser so mais disputa. As duas linhas novas por corte respondem isso -- e
  responderam: a rodada 5 tentou 6 e a soma caiu (ver abaixo).

### Velocidade, rodada 5: o log de 213 s (23-set-2026)

Com a rodada 4 o mesmo video de 10,5 min caiu de 343 s para 213 s: o ffmpeg do
reenquadramento foi de ~20 para ~50 quadros/s por corte, e as linhas novas
mostraram que 61% a 100% dos quadros deste video sao GENERAL. O resumo apontou
o resto: `03_transcribe` 57 s (16 s de carga, 37 s decodificando),
`04_detect` 26 s (15 s esperando o Groq) e `05_06_render` 87 s, em duas
rodadas de tres cortes.

- **O whisper em lotes na placa foi TENTADO E DESLIGADO** (`WHISPER_BATCH_SIZE`,
  hoje 0 por padrao; > 1 liga). O `BatchedInferencePipeline` do faster-whisper
  (1.1+, aqui 1.2.1) corta o audio pelo VAD em trechos de ate 30 s e
  decodifica varios de uma vez. O log seguinte mediu o preco, e ele nao pagava:
  a decodificacao caiu so de ~38 s para 33 s, e a transcricao **perdeu fala**
  -- terminou em 536 s, quando a sequencial ia ate 602 s, com 7% menos
  palavras e uma frase repetida. O modo em lotes nao refaz com temperatura
  maior o trecho que saiu ruim, e o que sumiu era o trecho mais dificil do
  video (falas curtas, varios "Nao!" seguidos); o sequencial refaz.
  `test_o_padrao_e_o_sequencial` trava a volta.
  - O codigo ficou, atras da variavel, porque a rede dele esta testada:
    qualquer falha -- inclusive no meio da iteracao, porque o gerador e lazy
    -- refaz no sequencial, com uma linha no log. `without_timestamps=False`
    de proposito: o padrao do modo em lotes junta cada trecho num segmento so,
    e as janelas da deteccao (`clip_selection.build_transcript_windows`) se
    alinham a segmentos.
  - **Nao religar sem comparar as duas transcricoes do mesmo video**: o
    tempo sai no resumo do job, a fala perdida nao sai em lugar nenhum.
- **O modelo sai do disco sem perguntar ao Hugging Face**
  (`local_files_only=True` primeiro). O `snapshot_download` ia a rede em todo
  job so para confirmar a revisao do modelo ja baixado. So o "nao esta no
  disco" tenta de novo pela rede; erro de placa sobe como antes, para a queda
  para CPU. E o log ganhou `⏱️ [ASR] modelo carregado em X s` -- o numero
  que decide se vale levar o `.cache/` para um volume do Docker.
- **Com outro provedor pronto, o 429 nao espera mais que 3 s**
  (`llm_cascade.ESPERA_MAXIMA_COM_ALTERNATIVA_S`). A rodada 4 esperava a dica
  do Groq quando ela cabia na paciencia de 15 s -- e coube: 14,4 s parado com
  o Gemini pronto para responder em ~6 s. `run()` avisa cada chamada, por um
  `ContextVar`, se ha quem atenda depois dela; o ULTIMO da fila continua com a
  paciencia de sempre, porque desistir dele derruba a deteccao do job.
- **Seis cortes em paralelo com placa foi TENTADO E DESFEITO.** A conta era
  "sobra CPU e o NVENC abre 8 sessoes"; a medicao disse o contrario. Com 6, o
  ffmpeg do reenquadramento andou a 14-18 quadros/s por corte, **98 somados**,
  contra 46-61 por corte e **~155 somados** com 3: mais cortes juntos
  disputaram a mesma maquina e fizeram menos no total. O overlay de GPU nao
  poe mais `CLIP_WORKERS` (vale o 3 do `main.py`), e
  `test_a_placa_nao_sobe_os_cortes_em_paralelo_sem_medicao` so deixa subir
  junto com uma medicao nova. **A soma e o que conta**, nao o ritmo de um
  corte: as linhas `⏱️ corte N` do log dao as duas.

**O log de 290 s (o mesmo video, com a rodada 5 inteira) explica os 77 s a
mais**, e nem tudo e defeito:

| estagio | 213 s | 290 s | por que |
|---|---|---|---|
| 01_ingest + 02_probe | 43 s | 47 s | rede e disco; ruido de uma medida so |
| 03_transcribe | 57 s | 64 s | carga do modelo 23,5 s (~7 s acima da anterior), lotes -5 s |
| 04_detect | 26 s | 11 s | o Groq pediu 23 s de espera e a vez passou ao Gemini |
| 05_06_render | 87 s | 168 s | ~45 s dos seis cortes juntos; ~35 s de corte mais LONGO |

- **Os cortes sairam 41% mais longos** (5034 quadros contra 3562, ~28 s cada
  contra ~20 s), e isso nao e o render: quem marca inicio e fim e a segunda
  passada do LLM, e desta vez ela foi do Gemini (pelo pulo do Groq), lendo a
  transcricao em lotes, de segmentos maiores. Qual das duas pesou, um job so
  nao separa. Duracao de corte e decisao de conteudo (o prompt pede 15-60 s),
  entao nao se "conserta" por velocidade -- mas comparar dois jobs sem olhar
  o total de quadros atribui ao codigo o que foi do modelo.
- Ficam da rodada 5 o pulo do Groq (-15 s), a carga sem rede e a linha do
  tempo de carga. Esta ultima ja respondeu uma pergunta: 23,5 s no primeiro
  job depois do `atualizar.bat`, o que torna o `.cache/` num volume do Docker
  o maior ganho barato que sobra -- e continua sendo decisao do autor, porque
  sao ~1,6 GB no disco do Docker.

### Velocidade, rodada 6: o modelo fica na placa e o audio chega primeiro (24-set-2026)

Com as duas coisas da rodada 5 desfeitas, o mesmo video levou **192 s**:
`01_ingest` 26 s, `03_transcribe` 55 s (13,8 s so carregando o modelo),
`04_detect` 12 s, `05_06_render` 98 s. O autor recusou os 1,6 GB do modelo num
volume do Docker e nao quis mexer nas quatro codificacoes de cada corte ("mexer
nisso vai mexer na qualidade") -- as duas mudancas daqui so mexem em TEMPO. A
estimativa para esse video e ~24 s a menos (a carga e ~15 s de video e juncao),
a confirmar no proximo log.

**O modelo residente** (`asr_residente.py`):

- Um processo proprio segura o whisper na placa; o job pergunta a ele por um
  socket de arquivo e so carrega o seu se ele nao servir.
- **Quem sobe e o servidor, quando alguem abre o painel ou um video comeca**
  (`POST /api/asr/aquecer`, `app.run_job`), e ele sai sozinho depois de
  `ASR_RESIDENTE_OCIOSO_MIN` (10) minutos sem uso. O painel avisa ao abrir, ao
  voltar para a aba e a cada 2 min (`dashboard/src/lib/aquecerTranscricao.js`).
  **Nem para sempre, nem por aba**: o modelo e do SERVIDOR, e serve todas as
  abas e todas as pessoas da instalacao -- a pergunta do autor era como isso
  vale para quem receber o programa, e a resposta e que vale sozinho.
- **O modelo nasce e trabalha na mesma thread, e o processo nunca faz fork.**
  E o oposto exato das duas suspeitas da pre-carga que travou em 23-set. Nao
  "otimizar" transcrevendo na thread da conexao.
- **Qualquer duvida volta ao caminho de hoje**: residente ausente, de outra
  configuracao (a chave modelo/dispositivo/precisao e comparada), lento demais
  para carregar (150 s), com erro, ou morto no meio -> `None`, e o job carrega
  o dele. O job fica mais lento, nunca para.
- **Travou, morre.** O laco principal mede o sinal de vida da thread de
  trabalho (o progresso de cada segmento) e sai por `os._exit` depois de 300 s
  sem ele; o job ve a conexao cair e segue sozinho.
- **Socket em /tmp, nao em /app**: `/app` e a pasta do Windows montada, onde
  socket nao abre. O arquivo tem zero byte, entao nao fere o "nada do
  processamento dentro do Docker". JSON e nao pickle: pickle recebido e codigo.
- `auto` so liga com o whisper na placa; `ASR_RESIDENTE=0` desliga.
- `tests/test_asr_residente.py` sobe o PROCESSO de verdade, com um
  `faster_whisper` falso no caminho: erro de import no ponto de entrada so
  aparece ali.

**O audio primeiro** (`audio_primeiro.py`):

- O seletor do YouTube pede o MESMO par de formatos na ordem inversa
  (`bestaudio...+bestvideo...`). O yt-dlp baixa na ordem escrita: o audio
  (~10 MB) chega em ~1 s e a transcricao comeca enquanto o video (~180 MB) e a
  juncao terminam numa thread. O mp4 final e o mesmo -- um teste roda o yt-dlp
  DE VERDADE contra um servidor local e confere a ordem e as duas trilhas.
- O `01_ingest` termina quando o audio chega. Quem precisa do video chama
  `_esperar_video()`: metadata, analise visual e escolha de layout (que passou
  para depois da deteccao, ainda antes do render). A espera volta ao
  `01_ingest` por `job_metrics.retomar`, que mede sem mexer na barra.
- **O audio e copiado dentro do gancho do yt-dlp**, antes de ele seguir: ele
  apaga os pedacos depois de juntar, e uma tentativa que cai no video recomeca
  do zero. O primeiro audio vale.
- **Download que cai depois do audio derruba o job antes da deteccao**
  (`levantar_se_falhou` logo depois da transcricao): nao gastar cota de LLM
  num job que ja esta perdido.
- **Com whisper LOCAL na placa, o CUDA so sobe depois do download**
  (`transcribe_backends.antes_de_carregar_na_placa`). No caminho normal quem
  transcreve e o residente e o job nem toca a placa; na queda, a carga local
  volta a ser exatamente o caminho que sempre funcionou.
- So o YouTube (`SourceAdapter.audio_primeiro`): nas outras fontes o arquivo
  vem inteiro. `AUDIO_PRIMEIRO=0` volta ao de antes.
- `tests/test_main_audio_primeiro.py` executa o bloco `__main__` do `main.py`
  como ele esta, com torch/mediapipe/scenedetect trocados por imitacoes: e o
  caminho de todo video do YouTube, e um nome errado ali so apareceria na
  maquina do autor.

**Medido no log seguinte: 165 s** (era 192). `01_ingest` 12,5 s (o audio
chegou; o video baixou 28 s depois, durante a transcricao), `02_probe` 2 s,
`03_transcribe` 43,8 s **sem carga nenhuma** ("modelo ja na placa"),
`04_detect` 21,6 s -- 10 s perdidos num `503 ... high demand` do Gemini, que
virou o ADR-011 --, `05_06_render` 84,8 s. O primeiro corte apareceu 2 min 16 s
depois de colar o link.

**As linhas do log nao grudam mais** (`linhas_inteiras.py`):

- Um `print` sao duas escritas; com varias threads, o marcador caia no meio da
  linha dos outros e passava pelo `startswith` do `app.py`. No log de 192 s:
  `...ninguem acreditou__STAGE__BEGIN 05_06_render`. O download em paralelo
  faria disso a regra: o yt-dlp escreve o progresso com `\r` e sem `\n`
  durante o download inteiro.
- O `main.py` troca stdout e stderr, antes de tudo, por um escritor que so
  emite linha inteira, por thread, sob uma trava comum (o `app.py` junta os
  dois no mesmo cano). **Sem atributo `buffer`**: o `write_string` do yt-dlp
  escreveria direto nele, por fora da trava.

### Velocidade, rodada 7: o que o log de 165 s ainda mostrava (24-set-2026)

Tres coisas, todas de TEMPO: nenhuma toca modelo, parametro de encode ou arquivo
entregue. Estimativa, a confirmar no proximo log: ~10 s a menos no total e no
primeiro corte.

**O render se aquece durante a deteccao** (`aquecimento.py`):

- A primeira rodada de cortes levou 49 s e a segunda 36 s. A diferenca era custo
  de uma vez por processo pago no primeiro corte: a sonda do NVENC (~2 s) e a
  subida da placa para o TransNetV2 (~5 s: contexto de CUDA, pesos, kernels da
  primeira inferencia). Durante o `04_detect` o processo so espera o LLM; a
  thread de aquecimento faz tudo isso ali, com uma janela de quadros pretos do
  mesmo tamanho da real.
- **A placa so sobe depois do download terminar**: a pre-carga do whisper que
  travou em 23-set subia o CUDA com o yt-dlp fazendo fork. Dali em diante a
  thread faz o que o primeiro corte ja fazia, numa thread nao-principal, com
  outras abrindo ffmpeg -- so que mais cedo.
- **E havia um defeito**: `scene_detection._get_tn2_model` nao tinha trava, e os
  tres cortes da rodada carregavam cada um o seu modelo, ao mesmo tempo.
  `_TN2_CARGA` resolve; quem chega no meio do aquecimento espera por ele.
- Nunca levanta e nunca prende o job; `AQUECER_RENDER=0` desliga.
  `ffmpeg_utils.modo_do_encoder()` e a definicao unica de "vai sondar o NVENC?".

**O download baixa pela extracao que ja fez** (`main._baixar_pela_extracao`):

- Cada tentativa abria duas instancias do yt-dlp, e a segunda
  (`ydl.download([url])`) extraia tudo de novo -- pagina, player, provedores de
  PO token: ~3,5 s entre o titulo e o primeiro byte do audio, que com o audio
  primeiro e o que a transcricao espera.
- Agora e `process_ie_result(sanitize_info(info, remove_private_keys=True))`, o
  caminho do `--load-info-json` do proprio yt-dlp
  (`YoutubeDL.download_with_info_file`). O `sanitize_info` tira o
  `requested_formats` da primeira escolha, que faria baixar a escolha ERRADA se
  a nova caisse num formato unico -- e a extracao ja escolhe com o mesmo seletor.
- **Qualquer falha extrai de novo** (o caminho de antes, que e tambem o que o
  `download_with_info_file` faz), somando na conta de bytes o que a tentativa
  que caiu ja tinha puxado pelo proxy.
- Na rodada 4 isso ficou de fora "pelo risco de mexer no download sem testar
  contra o YouTube". Mudou o peso (esses segundos agora atrasam o inicio da
  transcricao) e mudou o teste: `tests/test_download_extracao_unica.py` roda o
  `download_youtube_video` de verdade, com o yt-dlp de verdade, contra um
  servidor local que conta os pedidos -- 3 com o codigo antigo, 2 com o novo.
  Contra o YouTube em si continua sem teste daqui.

**"Audio pronto" em linha propria**: o aviso saia da thread do download, onde a
barra de progresso do yt-dlp ainda estava pela metade (`\r` sem `\n`), e grudava
nela. Agora sai do `aguardar_audio`, na thread de quem espera. O teste reproduz a
linha grudada do log com o codigo antigo.

### A cascata ampliada: todo provedor gratuito com chave (ADR-011, 24-set-2026)

O autor pediu, depois do 503 do Gemini: "o maximo de IA gratuita possivel",
porque o projeto tem de ser 100% gratuito. O levantamento e as escolhas estao no
ADR-011; o que importa ao mexer no codigo:

- **Os dois primeiros de cada ordem sao os de sempre** (`ORDEM_CURTA`,
  `ORDEM_LONGA`). Tudo o que veio depois so atende quando eles falham naquela
  chamada: a qualidade do caminho normal nao mudou.
- **Um id por MODELO**: `groq`, `groq-qwen` e `groq-20b` usam a mesma
  `GROQ_API_KEY` e tem cotas separadas (o Groq conta por modelo); `gemini` e
  `gemini-lite` idem com a `GEMINI_API_KEY`. Nos nomes de variavel o hifen vira
  `_` (`LLM_GROQ_QWEN_TPD`, `GROQ_QWEN_MODEL`).
- **Com outro pronto, "ocupado" passa ao proximo na hora**
  (`erro_de_capacidade`): 503, 429 sem dica, 5xx, timeout. Resposta errada
  (corpo vazio, JSON quebrado) continua repetindo o mesmo -- ali e o que
  recupera. Os codigos so contam como palavra inteira: um "1500" num erro de
  validacao nao e um 500.
- **Chave recusada (401) desliga todo mundo que usa aquela variavel**, no resto
  do job, sem gastar cota (`_CHAVE_RECUSADA`, como o `_MODELO_INEXISTENTE`).
- **Provedor na nuvem tem 3 min** (`timeout_para`, `LLM_TIMEOUT_NUVEM`); os 600 s
  do `LLM_TIMEOUT` sao do modelo local em CPU.
- **O `llm_backend` passou a tentar o formato mais simples em QUALQUER 400/422**
  de um pedido com `response_format` (cada provedor recusa com palavras
  proprias), e tira o `<think>...</think>` que Qwen, GLM e Nemotron podem
  escrever antes do JSON.
- **O pre-filtro nao aperta**: os novos publicam teto de chamadas, nao de tokens;
  ha teste.
- **Cerebras nao e mais gratis** (credito unico de US$ 5 com cartao desde
  21-jul-2026) e o `llama-3.3-70b` dele foi aposentado: o padrao virou
  `gpt-oss-120b`, o rotulo diz "pago" e ele foi para o fim da fila.
- **Os padroes de modelo apodrecem** -- o `qwen3-32b` do Groq saiu em julho. O
  aviso de modelo inexistente nomeia a variavel certa de cada provedor
  (`model_env`); `tests/test_llm_cascade_gratis.py` falha se um provedor novo
  nascer sem ela.

### O site no Cloudflare e so a tela (Fase 6, 24-set-2026)

O autor quer abrir o programa de qualquer computador e ver a versao nova sem
`atualizar.bat`. O painel agora e publicado no Cloudflare (Workers com arquivos
estaticos, projeto `virtu-clips`) a cada envio para a `main`. **So o painel**:
download, transcricao e render continuam no computador de quem abre o site.

- **O site fala com `http://localhost`, fixo** (`dashboard/.env.site`,
  `npm run build:site`): procura a 8000 (o Docker) e depois a 8001 (o
  ajudante), e fica com a primeira que responder (`config.usarServidor`, pelo
  AuthContext). Cada navegador fala com a propria maquina, entao o mesmo site
  serve a todo computador que tiver o programa rodando. O `build` comum nao
  muda: caminho relativo e o proxy do Vite.
- **Processar na nuvem nao e o padrao, e o motivo e o YouTube**: ele recusa IP
  de datacenter, e a saida seria cookie de conta -- risco de banimento que o
  autor recusou ("so estou copiando um link"). Baixando pela internet de quem
  usa, nao ha cookie nenhum. A nuvem fica como opcao para PC fraco, com limite
  mensal (plano: Fase 6.3).
- **O Chrome pede permissao uma vez** para o site acessar o que roda neste
  computador (Local Network Access). `http://localhost` nao conta como conteudo
  misto numa pagina https -- e origem "potencialmente confiavel" --, entao a
  permissao e a unica barreira. Um "Bloquear" por engano deixa o painel girando
  sem erro nenhum, e o servidor nunca fica sabendo: por isso a
  `EsperandoServidor` explica a permissao quando a URL da API e absoluta.
- **Toda URL do servidor passa pelo `getApiUrl`, sem excecao.** No site, um
  caminho solto (`/videos/...`) vai ao Cloudflare e nao acha nada -- a capa do
  projeto, a previa do template e o pacote do dia faziam isso. E o `?t=` que
  fura o cache vai DENTRO do `getApiUrl`: depois dele, com a auth ligada,
  colaria no valor do `mt`.
- **O `name` do `wrangler.jsonc` e o nome do projeto no Cloudflare**; o build de
  la recusa o deploy se os dois divergirem. No painel deles: caminho
  `/dashboard`, build `npm ci && npm run build:site`, deploy
  `npx wrangler deploy`.
- **O `robots.txt` recusa todo rastreador.** O herdado convidava todos e
  apontava para o sitemap do produto do upstream -- inofensivo em localhost,
  errado com endereco publico (ADR-009).
- **O endereco e `https://virtu-clips.zirtuno.workers.dev`** (no ar desde
  24-set-2026; `zirtuno` e o subdominio da conta do autor). O `workers_dev:
  true` explicito existe porque o painel do Cloudflare mostrou o workers.dev
  "Disabled" logo depois do primeiro deploy.
- **O servidor so entrega resposta ao site e a propria maquina**
  (`origens.py`): o site oficial, as URLs de versao dele e qualquer pagina de
  `localhost`. Ate aqui o CORS refletia QUALQUER origem com credenciais --
  qualquer site aberto no mesmo navegador lia os projetos, os logs e os videos.
  O painel do Docker nao depende disto: o proxy do Vite o faz mesma origem,
  inclusive aberto de outro aparelho da rede. `ORIGENS_DO_PAINEL` troca a
  lista; em branco vale o site oficial, porque lista vazia trancaria o painel
  sem erro nenhum.
  - **`allow_private_network` so e passado se o Starlette o conhece**: a imagem
    de quem ja instalou pode ter um anterior, e ali o argumento derrubaria a
    API no boot.
  - **Renomear o projeto no Cloudflare exige trocar `SITE_OFICIAL`**; ha teste
    comparando com o `name` do `wrangler.jsonc`.
- **CORS decide quem LE a resposta, nao quem MANDA o pedido.** Um formulario
  de outro site dispara um POST simples, sem preflight -- o `/api/process`
  recebe `Form` --, e o job rodava sem que ninguem lesse a resposta. Sob o
  ajudante isso fechou (`CORTES_ORIGEM_ESTRITA`, ver a secao seguinte). **No
  Docker continua aberto**, e a permissao do Chrome e a unica barreira: o
  painel aberto de outro aparelho da rede chega pelo proxy do Vite com a
  origem daquele aparelho, que nenhuma lista preve (e o compose publica a
  porta em todas as interfaces).

### O ajudante: o motor no Windows sem Docker (Fase 6.2, ADR-012)

`ajudante/`: o instalador (`instalador.iss`, Inno Setup), o que ele roda no fim
(`instalar.ps1`), o icone perto do relogio (`ajudante.py`), a atualizacao
sozinha (`atualizacao.py`), o ponto de entrada fixo (`iniciar.py`) e o
empacotador do CI (`empacotar.py`). O `windows.yml` instala o `.exe` de verdade
num Windows do GitHub e publica no GitHub Releases, de onde o site o oferece.

- **Porta 8001; a 8000 e do Docker, e o ajudante nunca a ocupa.** No login os
  dois sobem juntos e o ajudante chega antes: na mesma porta, o container
  morreria com "port is already allocated", em silencio. Com o Docker
  atendendo, o ajudante para o motor dele (terminando antes o job em curso).
- **Cada versao numa pasta (`versoes\<versao>\`), e o `atual.txt` diz qual
  vale.** Trocar e `os.replace` num arquivo, nunca rename de pasta: no Windows
  o rename falha com qualquer arquivo aberto la dentro. O atalho, o menu
  Iniciar, o inicio com o Windows e o desinstalador chamam o `iniciar.py`, que
  a atualizacao nunca troca -- por isso ele e pequeno, stdlib pura, e repete
  duas definicoes do `atualizacao.py` (ha teste comparando).
- **`Caminhos.motor` e a versao que roda o arquivo**, nao uma pasta fixa: e
  assim que a verificacao sobe o motor da versao NOVA.
- **A troca verifica antes, e e de outro processo.** A versao nova sobe na
  porta 8128 com pastas temporarias (`--verificar --temporario`) e o `main.py`
  tem de importar; nao passou, as dependencias da anterior voltam (pinos
  exatos) e ela entra em `dados\atualizacao.json` para nao ser tentada de
  novo. O processo e outro porque a bandeja tem o Pillow e o pystray
  carregados, e o Windows nao deixa o `uv` trocar uma DLL em uso.
- **So troca com o motor livre**: nenhum job e ninguem no painel ha 5 min. O
  `/health` diz as duas coisas (`jobs_ativos`, `ocioso_s`); `/health`,
  `/api/config` e `/api/asr/aquecer` nao contam como atividade (o aquecer e o
  painel ABERTO, nao alguem trabalhando).
- **A versao e a contagem de commits da `main`.** O `empacotar.py` grava
  `VERSAO`; o Docker calcula pelo git ao subir (`versao_do_motor.py`, com
  `safe.directory` e recusando clone raso). O `/api/config` manda `motor`, e o
  `AvisoDoMotor` do painel avisa -- so no Docker -- quando a publicada e mais
  nova.
- **O CI so publica quando o motor muda** (`conteudo` do `versao.json`, a
  impressao digital sem a versao). Commit de documentacao nao reinicia o motor
  de ninguem -- e por isso o pacote nao leva `.md`, Dockerfile, compose,
  `.env.example`, `cli/` nem `skills/` (`empacotar.FORA*`). A primeira
  versao, `ajudante-523`, levava o `CLAUDE.md`: cada commit de texto seria uma
  versao nova. `LICENSE` e `NOTICE` ficam, porque a licenca manda.
- **`CORTES_ORIGEM_ESTRITA=1` sob o ajudante**: POST/PUT/PATCH/DELETE com
  `Origin` fora de `origens.py` e 403 antes do endpoint. Sem `Origin` passa --
  e programa, nao navegador.
- **O `.env` da pessoa mora em `dados\.env`** e vence tudo menos `PROTEGIDAS`
  (as pastas e o que o ajudante precisa): quem usa Docker copia o `.env` do
  repositorio, e la o `OUTPUT_DIR` pode ser `/app/...`.
- **Armadilhas que ja morderam:**
  - no `.iss`, **nenhuma linha pode comecar com `#`** fora das diretivas: o
    pre-processador leu `#13#10` (a quebra de linha do Pascal) como diretiva e
    a compilacao abortou. Ha teste;
  - no `instalar.ps1` (Windows PowerShell 5.1), a saida de `.exe` passa por
    `Write-Host` com `$ErrorActionPreference = "Continue"` so dentro do
    `Rodar`: com `Stop`, a primeira linha de progresso que o `uv` escreve no
    stderr derruba o script;
  - numa funcao do PowerShell, **a saida de um `.exe` vira parte do valor de
    retorno** -- dai o `| Out-Host` no `Atualizar` do `windows.yml`;
  - a libass abre a legenda com o `fopen` de 260 caracteres: o checkout do
    GitHub passa disso, e o video de ponta a ponta trabalha numa pasta curta;
  - o motor sob o ajudante nao espera o dreno de 20 s (`PROXY_DRAIN_SECONDS=0`):
    aquilo e para o proxy de deploy em nuvem;
  - **so a ponta da `main` publica.** A release cria a tag no commit da volta,
    e o GitHub trata uma tag num commit cujo `.github/workflows` difere do da
    `main` como "criar workflow": exige `workflows: write`, que o
    `GITHUB_TOKEN` nunca tem, e responde 403 "Resource not accessible by
    integration" -- com `Contents: write` no token. Medido em 24-set-2026 pelo
    cabecalho `X-Accepted-GitHub-Permissions` (`contents=write` OU
    `contents=write,workflows=write`). Com um commit mais novo na `main`, a
    volta dele publica, e as versoes saem em ordem.
- **O que o CI nao prova**: placa, YouTube, IA de verdade, o icone e o
  SmartScreen. O roteiro para o PC do autor esta no `COMO-EXECUTAR.md`.

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
