# Decisões de arquitetura

Registro curto e datado. Cada entrada diz o que foi decidido, contra o que, e o que
faria a decisão ser revista. As ADRs 001 a 005 e a 008 fecham pontos que o
`PLANO-TECNICO.md` deixou abertos ou que a `AUDITORIA-VERIFICACAO.md` reabriu com
dado novo.

---

## ADR-001 — Forkar `mutonby/openshorts` e apagar `cloud/` no primeiro commit

**Data:** 2026-09-12 · **Status:** **implementada** (Fase 0.1)

O veredito do §2 do Plano Técnico se mantém: forkar o `openshorts` não pelo conjunto
de features, mas pela tração (~4.0k ★ · ~1.0k forks), que é o acervo de bugs de
`ffmpeg`, `yt-dlp` e tracking já encontrados e corrigidos por terceiros.

O que muda é a higiene de licença. O `openshorts` é MIT **com exceção** do diretório
`cloud/`, sob *OpenShorts Commercial License*, que proíbe oferecer o software a
terceiros como serviço pago ou hospedado. O plano projeta virada para SaaS em três
seções (§3, §7, §8), então o carve-out é incompatível com o destino declarado.

**Decisão:** `git rm -r cloud/` como primeira alteração do fork, antes de qualquer
outra, e registro no `NOTICE`. O restante do fork fica MIT puro.

**Revisão se:** o projeto abandonar definitivamente a hipótese SaaS — e mesmo aí a
remoção não custa nada, porque o `cloud/` não serve ao self-hosted.

### O que a execução encontrou

A licença confere com o auditado, textualmente. A cláusula que morde é a primeira
das proibições: *"Offer the Commercial Software, or any modified version or derivative
of it, to third parties as a hosted, managed, or paid service"*.

A remoção não foi um `git rm` isolado. O `cloud/` tinha 25 arquivos e outros quatro
artefatos existiam só para servi-lo:

| Removido | Por quê |
|---|---|
| `cloud/` | o carve-out comercial em si |
| `requirements-billing.txt` | instalava a stack exclusiva do modo pago |
| `docker-compose.cloud.yml` | composição do modo pago |
| `alembic/` e `alembic.ini` | migrações cujo alvo era `cloud.models`; `versions/` estava vazio |

O `Dockerfile` foi corrigido, porque copiava e instalava o `requirements-billing.txt`
em toda build — a remoção sem isso quebraria a imagem.

**O núcleo não quebrou, e isso não foi sorte.** O upstream já isolava o modo pago
atrás da flag `BILLING_ENABLED`, que é **falsa por padrão**: os 28 imports de `cloud`
em `app.py` e `mcp_server.py` são todos locais, dentro de blocos guardados — nenhum em
nível de módulo — e havia um `else: cloud = None` com dependência no-op para o modo
self-host. Self-host já era o caminho padrão do upstream.

Uma alteração própria foi feita: a guarda `if BILLING_ENABLED:` agora levanta
`RuntimeError` com mensagem explicando a remoção, em vez de deixar o `ImportError`
estourar três frames abaixo. É o que impede a decisão de ser desfeita por engano com
uma variável de ambiente.

### O que a remoção custou

Duas coisas, registradas para não serem descobertas por surpresa depois.

**130 testes saíram junto.** Doze arquivos em `tests/` tinham import de `cloud` no
topo e deixariam de coletar; todos testavam o módulo comercial (billing, metering,
proxy ledger, OAuth, política de e-mail, apagamento de conta). Um treze avo arquivo,
`test_mcp_endpoint.py`, era misto: a classe `TestCloudModeAuth` saiu e os 11 testes de
núcleo continuam. Restam 54 arquivos de teste, nenhum importando `cloud`.

**Perdeu-se a classificação de falha.** A função `cloud.alerts._classify_failure`
traduzia erro de pipeline em causa legível — distinguia falha de download de falha de
`ffmpeg`, reconhecia upload sem áudio, não culpava o `ffmpeg` por um erro do Gemini.
É comportamento de núcleo útil, mas morava no módulo comercial e portá-lo traria a
licença comercial de volta para a árvore MIT, o que anularia o propósito desta ADR.

Fica para reimplementar do zero, e o lugar natural já existe no plano: a tabela `jobs`
do §7 tem coluna `error`. Entra junto com ela, na Fase 0.5.

> Não mover código de `cloud/` para a árvore MIT, em nenhuma hipótese — nem "só uma
> função". É a regra que faz esta ADR valer algo. O código segue alcançável no
> histórico do git, sob a licença original, para consulta e referência.


---

## ADR-002 — `clippyme` entra como remote de git, não como porte manual

**Data:** 2026-09-12 · **Status:** aceita

O §2 trata o `clippyme` como repositório doador cujos módulos serão lidos e
reescritos. A auditoria mostrou que o `clippyme` é fork do próprio `openshorts`:
existe ancestral comum, logo existe `git diff` com três pontos.

Isso atinge exatamente a aquisição que o plano considera mais valiosa — a composição
na hora do download, sem reprocessar o vídeo, chamada de "a melhor ideia de
arquitetura dos quatro".

**Decisão:** adicionar `clippyme` como segundo remote e trazer o compositor e os seis
presets de legenda por cherry-pick assistido, filtrando os caminhos de transcrição
paga (Deepgram, ElevenLabs Scribe). O `opensource-clipping` e o `autoclip` **não** são
forks e seguem como doadores de leitura, conforme o plano original.

**Consequência:** a Fase 2 cai de ~2 semanas para ~1 semana.

### Nota de implementação (bloco 2.1, 14-set-2026) — as duas aquisições já estavam no fork

Ao começar a Fase 2, antes de adicionar o remote, li o código para saber o que
exatamente importar. As duas coisas que esta ADR queria já existiam:

- **O compositor de segunda passada.** `/api/subtitle` lê o clipe **já
  renderizado**, pega a transcrição do `_metadata.json` e requeima a legenda em
  cima dele; `/api/hook` faz o mesmo com a sobreposição; o `recut` recorta sem
  reenquadrar. Trocar de legenda nunca reprocessou o vídeo neste fork.
- **Os seis presets de legenda.** `subtitles.generate_ass` já expõe cor,
  contorno, realce, opacidade da base, caixa, efeito, caixa alta, alinhamento e
  janela de palavras. Um preset é uma combinação desses botões, e o primeiro
  deles é o `AUTO_CAPTION_STYLE` que o repositório já escolheu por medição.

O que faltava era o **documento**: os botões existiam espalhados por parâmetros
de endpoint, sem nome, sem versão, sem lugar onde escrever "o meu estilo" uma
vez. É o que o `template.py` passou a ser.

**A decisão não foi desfeita** — o `clippyme` continua sendo doador legítimo, e
adicioná-lo como remote continua sendo o jeito certo de trazer algo de lá. Mas a
Fase 2 não começa importando: começa com um módulo próprio, e o remote entra se
e quando um bloco precisar de algo concreto que aqui não exista.

---

## ADR-003 — MediaPipe é o padrão; YOLOv8 fica atrás de flag desligada

**Data:** 2026-09-12 · **Status:** aceita
**Fecha a decisão em aberto §10.4**

O §10 pergunta se o tracking de rosto deve usar MediaPipe puro desde o início para
evitar a AGPL-3.0 do YOLOv8. A auditoria mostrou que a pergunta chegou tarde: o
`openshorts` já embarca YOLOv8 (Ultralytics), então o passivo entra no repositório no
minuto do fork, sem decisão.

Remover em bloco não é obviamente certo — o MediaPipe resolve rosto bem, e o YOLOv8
resolve melhor detecção de pessoa quando o rosto está virado. O trade-off é real.

**Decisão:** aplicar ao tracker o mesmo padrão que o §1 do plano já aplica ao driver
de navegador — *existe na arquitetura, nasce desligado por padrão e fora do caminho
automático*. Concretamente: isolar atrás de uma interface `FaceTracker` (mesmo
desenho de `SourceAdapter` e `Publisher`), MediaPipe como implementação padrão, YOLOv8
como implementação opcional desligada e documentada como AGPL.

Assim o caminho padrão fica Apache 2.0, a qualidade extra continua disponível para uso
pessoal, e a virada para SaaS passa a ser mudança de configuração em vez de reescrita.

**Revisão se:** o MediaPipe puro se mostrar insuficiente em material real — nesse caso
o substituto é YOLOX ou RTMDet (Apache 2.0), não o YOLOv8.

### Nota de implementação (bloco 1.7, 14-set-2026) — o custo é maior do que esta ADR supôs

Ao implementar, apareceu um fato que esta decisão não levou em conta. A ADR discute o
detector como **qualidade de enquadramento** ("o MediaPipe resolve rosto bem, e o
YOLOv8 resolve melhor detecção de pessoa quando o rosto está virado"). Mas ele não é
usado só para enquadrar: **dois layouts dependem dele para detectar**, e os dois
registram medição no próprio código.

| Quem | O que perde sem o YOLO |
|---|---|
| TRACK | cena sem rosto segura o último alvo em vez de procurar um corpo — o custo que a ADR previu |
| **INSET** (`camera_inset.py`) | pode **não disparar**: o rosto dentro de um recuadro de webcam numa fonte 1080p costuma ser pequeno demais para o BlazeFace, e o detector exige 3 amostras para concluir |
| **SCREENCAST** (`screencast_layout.py`) | pode **não achar o apresentador**: o comentário registra *"measured: zero detections across an Excel walkthrough where the person is plainly visible"* |

A decisão **não foi desfeita** — o passivo AGPL-3.0 é real e a escolha é do autor. Mas
a degradação deixou de ser silenciosa: `face_tracker.avisar_desligado()` imprime uma
linha por job na primeira vez que alguém pede o detector e ele está desligado, dizendo
o que se perde e como ligar. Perder um layout sem aviso seria pior que perdê-lo.

**Consequência para a revisão acima:** se o YOLOX/RTMDet entrar como substituto Apache
2.0, ele precisa cobrir estes dois casos de detecção, não só o enquadramento.

---

## ADR-004 — O pré-filtro heurístico é obrigatório, não oportunista

**Data:** 2026-09-12 · **Status:** aceita
**Fecha a decisão em aberto §10.3**

O §10 pergunta se o pré-filtro heurístico entra já na Fase 0 "ou só quando o rate
limit apertar". A auditoria respondeu com número: o free tier do Groq tem teto de
**100.000 tokens/dia**, ausente da tabela do §3. Uma live de 4h da Twitch — o caso
que a própria Fase 1 elege como pior caso a testar primeiro — estimada em ~75.000
tokens com as janelas de 20% de sobreposição do §3, consome de 60% a 75% do orçamento
diário inteiro. O limite de 1.000 requisições/dia nunca é alcançado; é irrelevante.

O rate limit não vai apertar no futuro. Ele já está apertado no caso de uso alvo.

**Decisão:** o pré-filtro é requisito de arquitetura, não otimização. Entra na Fase 1,
junto com o adapter de Twitch live que cria a necessidade — não antes (a Fase 0 não
tem fonte longa para exercitá-lo) e não depois (a Fase 1 não funciona sem ele).

A Fase 0 ganha em troca uma tarefa de meia hora que torna a calibração possível:
instrumentar tokens por chamada, chamadas por job e tempo por estágio em
`timings_json`, campo que o §7 já prevê no schema. Sem essa medição, ajustar o
pré-filtro é achismo.

---

## ADR-005 — A ordem da cascata de LLM depende da duração da fonte

**Data:** 2026-09-12 · **Status:** aceita

O §3 propõe cascata fixa: `[Groq(), GeminiFlash(), Cerebras(), Ollama()]`, com Groq
primário por velocidade e Gemini Flash acionado "quando precisar de contexto gigante".
Com o teto de 100k tokens/dia do Groq (ADR-004), uma ordem fixa gasta o recurso mais
escasso no trabalho mais pesado.

**Decisão:** o resolvedor escolhe pela duração falada da fonte, mantendo a interface
`LLMProvider` do §3 intacta:

- **Fonte curta** (até ~40 min de fala): Groq primeiro. É onde a velocidade de ~320
  tok/s encurta o job e onde o custo em tokens é baixo.
- **Fonte longa** (live, podcast, VOD de horas): Gemini Flash primeiro, pelo contexto
  de 1M e pelo orçamento diário maior. O Groq viraria gargalo.
- **Cerebras** terceiro em ambos os casos — o teto dele é de tokens (~1M/dia), o que o
  torna bom complemento justamente do Groq.
- **Ollama local** como piso. Nunca falha, nunca tem limite, custa GPU.

**Atenção de privacidade (do §3, mantida):** o free tier do Google AI Studio usa os
dados enviados para treinar modelos fora da UE/UK/EEA, Brasil incluído. Aceitável para
conteúdo próprio; inaceitável com conteúdo de cliente. Se o projeto virar SaaS, o
Gemini free tier sai da cascata — e, por esta ADR, é justamente o primário das fontes
longas. O substituto precisa estar mapeado antes da virada, não durante.

**Revisão se:** os limites mudarem. Reconfirmar antes da Fase 0.

> **Nota de 24-set-2026 — os limites mudaram, e a revisão está no ADR-011.** O
> Cerebras deixou de ser gratuito (crédito único de US$ 5, com cartão, desde
> 21-jul-2026) e o modelo dele aqui (`llama-3.3-70b`) foi aposentado; o Groq
> publicou 200k tokens/dia para o `gpt-oss-120b`. A regra desta ADR — a ordem
> depende da duração — continua de pé: os dois primeiros de cada ordem são os
> mesmos, e tudo o que o ADR-011 acrescenta vem depois deles.

### Implementada na Fase 0.4 — `llm_cascade.py`

**Status: implementada.** O módulo decide **ordem e orçamento**, e nada mais: não
importa o SDK do Google nem cliente HTTP. Quem sabe falar com cada provedor é o
`main.py`, que já tinha os dois caminhos, e recebe um `Provider` por tentativa.

Três decisões de implementação que valem registro:

**O orçamento vive em disco, não em memória.** É consequência direta do achado da
Fase 0.2: o `main.py` roda como subprocesso novo a cada job, então um contador em
memória zeraria entre vídeos e o teto diário nunca valeria nada. Fica em
`output/.llm_budget.json`, junto dos outros arquivos de estado que o caminho
self-host já mantém ali, com escrita atômica (`os.replace`) para dois jobs em
paralelo.

**O Gemini não é chamado por HTTP.** Ele entra na cascata como provedor, mas a
chamada continua pelo SDK que já existia, porque o caminho do SDK carrega duas
coisas que HTTP genérico não reproduz: `response_schema` server-side e o
`GeminiBlockedError` que o `_run_stage_split` usa para bissectar batch bloqueado
por PROHIBITED_CONTENT. Não verifiquei o endpoint OpenAI-compatível do Google, e
não preciso.

**O Ollama é opt-in, sem default para localhost.** A primeira versão adivinhava
`http://localhost:11434/v1`, e os testes pegaram o efeito: o Ollama entrava em
*toda* cascata mesmo sem nada escutando, e cada job gastaria uma tentativa de
conexão para descobrir. Pior, o plano o chama de "rede de segurança que nunca
falha", e isso só é verdade se ele estiver rodando — quem sabe é quem instalou.
Agora entra só com `OLLAMA_BASE_URL`.

### Achado da Fase 0.2 — a cascata não parte do zero

`llm_backend.py` (165 linhas) já existe no upstream e já desacopla o detector do
Gemini: `LLM_BASE_URL` + `LLM_MODEL` + `LLM_API_KEY` roteiam as duas passadas de
`get_viral_clips` para qualquer endpoint compatível com OpenAI
`/chat/completions`, validando a resposta com os mesmos schemas pydantic que o Gemini
usa server-side, de modo que `main.py` vê uma forma só. Groq, Cerebras e Ollama falam
esse dialeto.

Ou seja, o bloco 0.4 não precisa escrever a abstração — ela está feita para **um**
provedor configurável. O que falta é a lista ordenada, a checagem de rate limit antes
de chamar (`available()` do §3) e a escolha por duração da fonte desta ADR.

Uma restrição a registrar: os estágios que trabalham por frames — `layout_picker`,
`screencast_layout` e `get_visual_clips` — continuam presos ao Gemini e degradam sem
chave. A cascata cobre o detector sobre transcrição, não esses.

---

## ADR-006 — Quantidade de cortes por vídeo é configuração, não constante

**Data:** 2026-09-12 · **Status:** aceita, com padrão provisório
**Fecha a decisão em aberto §10.1**

O §10 pergunta quantos cortes o sistema deve propor por vídeo. A resposta honesta é
que ninguém sabe antes da Fase 5, que existe precisamente para calibrar isso com
retenção real em vez de achismo do LLM.

O erro a evitar é transformar um número não sabido em constante no código.

**Decisão:** o detector devolve candidatos **ranqueados com score**, e quantos sobem é
configuração com dois controles independentes: teto de candidatos por fonte (padrão
provisório: 10) e piso de score abaixo do qual o candidato não é proposto mesmo que
haja vaga no teto. O piso é o que importa — sem ele, um vídeo ruim gera dez cortes
ruins para preencher cota.

**Revisão:** na Fase 5, com dados de retenção. É o objetivo declarado daquela fase.

---

## ADR-007 — Cadência de publicação fica para a Fase 4, com jitter como requisito

**Data:** 2026-09-12 · **Status:** fechada em 16-set-2026 (Fase 4, bloco 4.4)
**Aborda a decisão em aberto §10.2**

O §10 pergunta quantos posts por dia e em quais horários. O próprio plano localiza
isso na Fase 4, a cerca de sete semanas de distância; travar agora seria decidir sem
informação e sem necessidade. Fica em aberto por escolha.

Uma parte, porém, é decidível agora, porque é estrutural e não de gosto: o §1 do plano
identifica "postagens em horários regulares demais" como um dos sinais que a detecção
de automação cruza. Um agendador que publica às 12:00:00 todo dia produz exatamente
essa assinatura.

**Decisão:** o agendador nasce com jitter na janela de publicação — requisito de
desenho, não configuração opcional. Vale para todos os drivers, inclusive `manual` e
`youtube-api`, onde não há risco de conta: custa nada e evita retrofit quando o driver
`browser` eventualmente for ligado à mão.

Os números — quantos por dia, quais janelas, espaçamento mínimo — permanecem abertos
para a Fase 4. Padrões de partida para discussão: 3/dia, espaçamento mínimo de 3h,
jitter de ±25 min.

**Fechado em 16-set-2026, na Fase 4 (bloco 4.4), e os números de partida ficaram.**
Não por inércia: o **3/dia** é o único que o plano corrobora duas vezes — a conta do
§1 ("3 vídeos/dia gastam 4.800 e sobra metade para listagem e reprocessamento") e a
proposta deste ADR chegaram nele por caminhos diferentes. O teto duro é outro e não é
escolha nossa: **6/dia**, do contador de quota do `youtube-api`, e o agendador nunca o
ultrapassa (`min(scheduler.por_dia(), quota.uploads_por_dia())`).

O que **não** está fechado, e está dito como tal: se 11h/15h/19h são os horários certos.
Isso não se decide com argumento — decide-se com retenção medida, que é a tabela
`metrics` e a Fase 5. Por isso os três números vivem em variável de ambiente
(`SCHEDULE_PER_DAY`, `SCHEDULE_WINDOWS`, `SCHEDULE_MIN_GAP_MINUTES`): calibrar não pode
exigir deploy.

O jitter virou código com uma trava que o ADR pedia implicitamente. `JITTER_MINIMO_MIN`
(5 min) é um **piso não configurável**: pedir zero não desliga o jitter, só o reduz ao
piso, com uma linha no log dizendo por quê. A alternativa — aceitar zero — é um
agendador que um dia roda com zero, e aí a assinatura que este ADR existe para evitar
volta sem ninguém decidir que volta.

---

## ADR-008 — `tenant_id` no schema antes das Fases 1 a 3, não na Fase 4

**Data:** 2026-09-12 · **Status:** aceita

O §7 do plano é categórico: `tenant_id` em toda tabela "desde o primeiro commit", e
justifica com a assimetria correta — "adicionar auth sobre um schema que já tem tenant
é um sábado de trabalho; adicionar tenant sobre um schema que não tem é uma migração
que quebra tudo".

Só que o roadmap do §9 põe multi-tenancy na Fase 4, e a Fase 0 manda explicitamente
"não escrever nenhuma linha própria". Entre um ponto e outro, as Fases 1, 2 e 3 criam
tabelas novas: `sources`, `templates`, `clips`, `publications`. Seguido à risca, o
roadmap produz exatamente a migração que o §7 quer evitar, três fases depois e com
mais tabelas dentro.

O schema herdado do fork não tem `tenant_id`, e o plano não aloca tempo para colocá-lo.

**Decisão:** inserir uma etapa curta entre a Fase 0 e a Fase 1 — chamada aqui de
**Fase 0.5** — que leva o schema ao desenho do §7, com `tenant_id` em toda tabela e um
tenant fixo no seed. Sem auth, que segue na Fase 4 conforme o plano.

É a correção de sequenciamento que mais economiza trabalho no plano inteiro, e ela não
aparece como tarefa em nenhuma fase do §9.

### Revisão após a Fase 0.1 — não há schema herdado

A premissa desta ADR era "levar o schema herdado ao desenho do §7". A Fase 0.1 mostrou
que **não existe schema herdado no caminho MIT**: `sqlalchemy`, `asyncpg` e `alembic`
estavam só no `requirements-billing.txt`; o Postgres, só no `docker-compose.cloud.yml`;
e todo o ORM morava em `cloud.models`. O `docker-compose.yml` do self-host não tem
serviço de banco, e o `alembic/env.py` se descrevia como ambiente "for cloud-mode
migrations".

Ou seja: a camada de persistência inteira era do módulo comercial e saiu com ele.

Isso **não invalida a ADR — reforça**. A assimetria que a justificava era "adicionar
tenant sobre um schema que não tem é uma migração que quebra tudo". Agora não há
migração a fazer: as nove tabelas do §7 nascem escritas, com `tenant_id` na primeira
delas. O risco que a ADR queria evitar desaparece por completo.

O que muda é a **natureza e o tamanho** da fase. Deixa de ser migração de duas ou três
tabelas e passa a ser autoria da camada de persistência: escolher a stack (o §3 admite
PostgreSQL ou SQLite local), inicializar alembic do zero, escrever as nove tabelas e
ligar ao estado de job que o pipeline mantém hoje por outro meio.

**Estimativa revisada:** 3–5 dias, contra os 2–3 originais.

### Implementada na Fase 0.5

**Status: implementada.** Nove tabelas, `tenant_id` em oito delas (`tenants` *é* o
tenant), seed com tenant fixo, alembic do zero. Quatro decisões que valem registro:

**Stack: SQLAlchemy 2.x async, SQLite por padrão, Postgres por `DATABASE_URL`.**
SQLite porque o escopo declarado é uso pessoal self-hosted — zero operação, um
arquivo. Async porque o `app.py` é async de ponta a ponta e uma consulta bloqueante
num handler `async def` trava o event loop, o que com o semáforo de jobs do upstream
para a fila inteira. O `sqlalchemy` e o `alembic` voltaram ao `requirements.txt` aqui
depois de saírem na Fase 0.3 — lá pertenciam ao `cloud/`, aqui são deste schema.

**Isolamento garantido pelo banco, com chave estrangeira composta.** `clips.job_id →
jobs.id` permitiria, por bug de consulta, um corte de um tenant referenciar o job de
outro. A FK composta `(tenant_id, job_id) → jobs(tenant_id, id)` torna isso
**impossível**, não desencorajado. Custa um índice único por tabela-pai.

**O critério "nenhuma consulta ignora a coluna" virou estrutura, não disciplina.**
Duas peças: `TenantScope` (`db.tenant()`), que filtra e preenche `tenant_id`
automaticamente e *recusa* objeto de outro tenant; e um teste que quebra se um modelo
novo nascer sem a coluna — o mesmo padrão que o upstream usava em
`test_account_erasure.py`, onde o teste falha se uma tabela nova referencia
`users.id` sem entrar na lista.

**Um vazamento real que só apareceu porque testei.** O SQLite ignora chave
estrangeira por padrão, e meu listener de `PRAGMA foreign_keys=ON` farejava
`type(conn).__module__.startswith(("sqlite3","aiosqlite"))`. Com aiosqlite o que chega
ao evento é `sqlalchemy.dialects.sqlite.aiosqlite.AsyncAdapt_aiosqlite_connection`: a
checagem dava `False`, o pragma nunca rodava, e **o banco aceitou um job do tenant B
apontando para a fonte do tenant A** — as FKs compostas eram decoração. Corrigido
ligando o listener ao engine e decidindo pelo nome do dialeto, que é determinístico.
`TestIsolamentoEntreTenants::test_o_pragma_de_fk_do_sqlite_esta_ligado` impede a volta.

**O banco mora em `data/`, não em `output/`.** O `output/` é barrido pela limpeza por
idade e pelo teto de tamanho. Hoje as duas só apagam diretórios, então um arquivo ali
sobreviveria — mas por um detalhe de código herdado que um `git fetch upstream` pode
mudar sem aviso. Tirar o banco do caminho da vassoura troca "sobrevive porque testei"
por "não está lá".

### A incerteza, resolvida na Fase 0.2

A pergunta em aberto era onde o caminho self-host guarda estado de job hoje. Resposta:
**em disco, em cinco arquivos com semântica clara**, e nenhum é banco —
`<job>.resume.json` (manifesto de retomada, com heartbeat a cada 10 s), o arquivo
`.owner`, `output/.instance` (id da instância, para handover entre containers),
`<clip>.layout.json` e `.transcript_checkpoint.json`. A leitura é centralizada em
`_recover_jobs_from_disk` (`app.py:621`).

Isso **reduz** o risco da fase. Não há estado em memória a resgatar nem schema a
migrar: as tabelas `jobs` e `sources` do §7 nascem espelhando o que esses arquivos já
dizem, e os arquivos podem seguir existindo durante a transição. A estimativa de 3–5
dias fica, mas agora a faixa é por volume de tabelas, não por incerteza. Detalhe em
`docs/MAPA-DOS-ESTAGIOS.md`.


---

## ADR-009 — A superfície de marketing e SEO sai inteira, não reescrita

**Data:** 2026-09-12 · **Status:** aceita e executada em 2026-09-13
**Aberta pela Fase 0.3**

A Fase 0.3 removeu as dependências pagas do código. Sobrou um resíduo que ela
deliberadamente não tocou: `Landing.jsx`, `PricingPage.jsx`, `PricingSection.jsx`,
`dashboard/seo/*` (incluindo `legal.js`, com 1619 linhas), `index.html`, mais
`examples/n8n/`, `ops/` e `design.md`. Tudo isso anuncia dublagem em 30+ idiomas,
UGC com atores sintéticos e publicação automática — features que não existem mais.

A tentação é corrigir o texto. É a saída errada, por três motivos.

**Não há produto a divulgar.** O plano define o escopo como uso pessoal, self-hosted.
Uma landing page com tabela de preços, página de planos, cluster de `/alternatives` e
comparativo de concorrentes serve a um SaaS — e o `CLAUDE.md` do upstream chega a
instruir que nada no site diga "OpenShorts é grátis" sem citar o preço do Cloud na
mesma frase. Manter essa superfície é manter a obrigação de mantê-la coerente.

**Ela é grande e cara de manter correta.** O `vite-plugin-seo.js` gera páginas
estáticas, `sitemap.xml` e `llms.txt` a partir de `seo/pages.js`, e o `seo/data.js` é
descrito como fonte única de verdade de preço e pipeline. Reescrever a copy significa
manter esse gerador alinhado com um produto que não existe, a cada mudança.

**Ela carrega marca de terceiro.** É o marketing do OpenShorts, não deste projeto.
Um fork pessoal que publica a landing page do upstream com preços do upstream não é
só inútil: é enganoso.

**Proposta:** remover a superfície inteira — landing, pricing, páginas de SEO,
`legal.js`, o plugin gerador e os textos de marketing do `index.html` — deixando o
painel entrar direto na ferramenta. O `NOTICE` continua creditando o upstream, que é
a obrigação real da licença MIT.

**Decidido em 13-set-2026, e antes da Fase 4.** A previsão de adiar para a Fase 4
caiu quando o autor subiu o projeto pela primeira vez: a porta 5175 abria na home
comercial do upstream, anunciando "ai shorts from $0.65 per video" e "direct publish
to YouTube", e o botão `github` levava ao repositório deles. Não era teoria sobre
manutenção futura, era a primeira tela do próprio produto mostrando o produto de
outra pessoa.

Removido: `Landing.jsx` (808), `PricingPage.jsx` (323), `PricingSection.jsx` (189),
`Legal.jsx` (114), `dashboard/seo/` (3.541, incluindo `legal.js`), o
`vite-plugin-seo.js` (155), o `StarBanner`, o cartão que divulgava
`mutonby/skill-autoshorts` dentro da aba de agente, e a metade de marketing do
`index.html` (SEO, Open Graph, Twitter, canonical, JSON-LD).

Saiu junto o que só existia para servir a isso: o inicializador do OpenPanel no
`index.html`, o `public/op1.js` que ele carregava, o `lib/consent.js` e o
`CookieBanner`. Não era correção de privacidade — o rastreador já era inerte aqui,
travado por variáveis não definidas **e** por um teste de host
(`/^(www\.)?openshorts\.app$/`) que localhost nunca passa. Era coerência: sem o
inicializador, o script virou arquivo inalcançável e o banner passou a pedir
consentimento para nada. `lib/analytics.js` ficou como no-op explícito, porque as 13
chamadas a `track()` vivem em quatro arquivos que o autor vai reescrever.

**O que ficou de fora, de propósito:** a UI de cobrança (`TrialGate`, `TopUpModal`,
`PlanChoiceModal`, `UsageMeter`, `InvoicesCard`, `WatermarkModal`), que o ADR-001 já
deixou inalcançável via `billingEnabled`, e `examples/n8n/`, `ops/` e `design.md`.
Nada disso está no caminho de quem abre a ferramenta, e misturar tudo num commit só
apagaria a fronteira entre "o que me recebia na porta" e "o que existe mas ninguém
alcança".

**Revisão se:** o projeto virar SaaS. Aí a superfície volta a ter função — mas escrita
para este produto, não herdada.

---

## ADR-010 — O que mantém o `browser` fora da cascata é o risco, não o nome

**Data:** 2026-09-15 · **Status:** aceita e executada no bloco 3.1
**Aberta pela Fase 3**

A §6 define a cascata de publicação com um comentário que é, na prática, um
requisito de segurança:

```
resolve(platform, account) =>
  youtubeApi.ifQuotaLeft() ?? aggregator.ifSubscribed() ?? manualQueue
// browser NUNCA entra aqui automaticamente
```

A leitura óbvia é escrever `if driver.id == "browser": continue` no resolvedor.
Funciona hoje, e é a forma errada de escrever isto.

**Uma lista de exceções por nome só protege contra o que já aconteceu.** O dia
em que existir um segundo driver arriscado — um agregador que faz login por
sessão do navegador, um cliente não oficial de alguma plataforma —, ele entra na
cascata por omissão. Ninguém revisa a lista de exceções ao adicionar coisa nova;
é justamente o tipo de regra que se esquece porque parece resolvida.

E o custo do esquecimento não é um bug comum. A §1 é explícita: **a punição por
detecção não é erro HTTP tratável — é shadowban ou perda da conta**, e num
projeto de cortes a conta é o ativo. Não há retry, não há fallback, não há
mensagem de erro para tratar. A falha é silenciosa e permanente.

**Decisão:** a regra é sobre a propriedade, não sobre o nome. A §6 já pedia
`riskScore` na assinatura de `cost()`, e ele passa a ter uma função: **a cascata
automática só aceita driver com risco zero** (`RISCO_MAXIMO_AUTOMATICO = 0.0`).
O `browser` declara `1.0` e sai; um driver arriscado futuro sai pelo mesmo
motivo, sem que ninguém precise ter lembrado dele.

O teto é zero, e não "baixo". Um teto tolerante é o começo da conversa que
termina com a conta banida por conveniência — e o que se ganharia é automação
que a fila manual já entrega.

São três camadas, e nenhuma depende das outras:

1. o `risk_score` acima do teto tira o driver da cascata;
2. o `manual` responde `disponivel()` sempre e **encerra** a busca — nada
   registrado depois dele é alcançável por `resolve()`, e o `browser` está
   depois dele;
3. o próprio `browser.disponivel()` exige `PUBLISHER_BROWSER=1`, então nem o
   caminho explícito (`driver_por_id`) responde numa instalação que não ligou.

`accounts.driver_pref` é **preferência dentro do que a cascata já aceita**,
nunca ampliação: preferir um driver arriscado não o torna elegível. É o que
impede um clique errado no painel de virar uma conta perdida.

**Duas consequências que não estavam previstas:**

**`driver_pref` nascia valendo `manual`, e isso era um pino disfarçado de
padrão.** A cascata respeita a preferência da conta; uma preferência gravada em
toda linha não é preferência. Com `manual` ali, o `youtube-api` nunca seria
escolhido por conta nenhuma, por mais quota que sobrasse — a camada inteira
entregaria sempre o mesmo resultado, e o sintoma seria "nunca publica sozinho",
que ninguém liga a um valor default numa coluna. Quem mostrou foi um teste do
bloco 3.1. O valor `auto` entrou pela migração `8c5d2e91b740` e passou a ser o
padrão; `manual` na coluna volta a significar uma escolha de verdade: *esta
conta eu publico à mão*.

**`publish()` recebe a `account`, que a §6 não passa.** O pseudocódigo da seção
entrega a conta para `resolve(platform, account)` e para `capability(account)` e
a esquece em `publish(clip, meta, opts)` — mas nenhum driver funciona sem ela: o
`manual` precisa da plataforma para escolher qual texto escrever, o
`youtube-api` precisa do `credentials_ref` para achar o token. Ela vem como
parâmetro próprio, e não dentro de `PublishOptions`, porque não é uma opção: é
para onde vai.

**`publish` e `capability` são síncronos**, apesar do `Promise<...>` da §6 — ali
o TypeScript descreve o formato do contrato, não o modelo de concorrência. O
upload do YouTube é subida em blocos com biblioteca síncrona e o pacote do
`manual` é trabalho de disco; os dois rodam num executor a partir do `app.py`,
que é o que o `download_all_clips` já faz com o ZIP dele. Prometer `async` só
adicionaria uma camada em volta de trabalho bloqueante.

**Revisão se:** aparecer plataforma sem API pública que o projeto precise de
verdade **e** o autor decidir aceitar o risco de conta. Aí o `browser` deixa de
ser stub — e continua fora da cascata automática, porque a decisão acima é sobre
automação, não sobre existir.

---

## ADR-011 — Todo provedor gratuito com chave entra na cascata, depois dos dois de sempre

**Data:** 2026-09-24 · **Status:** aceita

**Contexto.** No log de 165 s, a detecção levou 21,6 s em vez de ~12: o Groq
estourou os 8.000 tokens/minuto (as duas chamadas de pontuação gastam ~6 mil, e a
de detalhe pede ~4,5 mil), a vez passou ao Gemini, e o Gemini respondeu `503 ...
high demand`. O programa esperou 5 s e tentou de novo. Com só dois provedores, não
havia terceiro. O autor pediu "o máximo de IA gratuita possível", porque quer o
projeto 100% gratuito — e porque quanto mais provedores, mais tokens por dia.

**Levantamento (24-set-2026).** Fonte principal: a lista mantida em
`mnfst/awesome-free-llm-apis` (atualizada em setembro, com links para a
documentação de cada provedor), conferida por busca nos pontos que mudaram:

| Provedor | Custo | Limite | Treina com o conteúdo? |
|---|---|---|---|
| Groq (`gpt-oss-120b`, `gpt-oss-20b`, `qwen3.8-27b`) | grátis, sem cartão | **por modelo**: 30/min, 1.000/dia, 8k tokens/min, 200k/dia | não |
| Google Gemini (3.1 e 3.5 Flash-Lite) | grátis | ~1.500/dia por modelo, sem número estável | sim (fora da UE) |
| NVIDIA NIM (Nemotron, Qwen, gpt-oss...) | grátis (Developer Program) | 40/min, 10.000/dia por modelo | registra "para melhorar produtos NVIDIA" |
| Mistral | modo gratuito, sem cartão, pede telefone | ~1/s | sim, com opt-out |
| Ollama Cloud | grátis | por sessão (5 h) e semana, sem número | — |
| OpenRouter (`openrouter/free`) | grátis | 20/min, 50/dia (1.000/dia após US$ 10 uma vez) | provedores gratuitos podem registrar |
| Cloudflare Workers AI | grátis | 10.000 neurons/dia, divididos entre modelos | não |
| Z.ai (GLM-4.7-Flash) | grátis | 1 chamada por vez; servidor na China | sem política clara |

Ficaram de fora: **Cerebras** como gratuito (virou crédito único de US$ 5 com
cartão; continua aceito para quem pagar), **GitHub Models** (aposentado em
30-jul-2026), **Hugging Face** (US$ 0,10/mês), **ModelScope** e **SiliconFlow**
(exigem verificação de identidade chinesa), e os **gateways sem chave** (Kilo,
LLM7, OVHcloud anônimo): catálogo que muda sem aviso, e mandar a transcrição a um
terceiro que registra, sem a pessoa ter pedido, não é o tipo de coisa que entra
por padrão.

**Decisão.**

1. **Os dois primeiros de cada ordem não mudam** (ADR-005): Groq e Gemini numa
   fonte curta, Gemini e o segundo Gemini numa longa. Todo o resto vem DEPOIS e só
   atende quando os anteriores falharam naquela chamada — o caminho normal, e a
   qualidade que ele entrega, ficam como estavam.
2. **Um id por modelo, não por provedor.** O Groq conta a cota por modelo: a mesma
   `GROQ_API_KEY` vira três filas de 8k tokens/min (`groq`, `groq-qwen`,
   `groq-20b`), e a `GEMINI_API_KEY`, duas (`gemini`, `gemini-lite`). É o ganho
   sem cadastro nenhum: quem já tinha as duas chaves ganhou três provedores.
3. **Só entra quem tem chave.** Cadastrar um provedor no catálogo não custa nada a
   quem não o usa.
4. **Com outro provedor pronto, "ocupado" passa ao próximo na hora**
   (`llm_cascade.erro_de_capacidade`). É a extensão natural da regra do 429 da
   rodada 5: esperar 5 s por quem disse que está cheio, com outro respondendo em
   2 s, é tempo perdido. Resposta ERRADA (corpo vazio, JSON quebrado) continua com
   a regra de sempre, porque ali repetir o mesmo é o que recupera. O último da
   fila espera como sempre esperou.
5. **Chave recusada (401) desliga, no resto do job, todo mundo que a usa**, e o
   log diz qual variável conferir — o mesmo tratamento do modelo inexistente.
6. **Provedor na nuvem tem 3 min para responder** (`LLM_TIMEOUT_NUVEM`), e não os
   10 min do modelo local.
7. **O pré-filtro não aperta.** Ele usa o menor teto de tokens/dia publicado da
   cadeia; os provedores novos publicam teto de chamadas (ou nenhum), e os modelos
   extras do Groq têm o mesmo teto do principal. Há teste.

**Consequências.** A lista de quem treina com o conteúdo cresce (o log do job
lista cada um). Cada padrão de modelo é uma aposta que apodrece — o
`qwen3-32b` saiu do Groq em julho, o `llama-3.3-70b` do Cerebras também —, e o
tratamento do 404 de modelo existe para que isso vire uma linha no log dizendo
qual variável trocar, e não um job parado.

**Revisão se:** um provedor mudar os termos (o Cerebras mudou em julho); ou se a
medição da Fase 5 mostrar que um dos fallbacks escolhe cortes piores que o Gemini —
aí ele desce na ordem, não sai.


---

## ADR-012 — O ajudante: o motor no Windows sem Docker, por usuário, e que se atualiza sozinho

**Data:** 2026-09-24 · **Status:** aceita; provada no Windows do GitHub, falta o teste no PC do autor

**Contexto.** Desde a Fase 6.1 o site é só a tela, e quem processa é o motor no
computador de quem o abre — pelo motivo do YouTube, que recusa IP de datacenter
(ver a Fase 6 no `PLANO-DE-ACAO.md`). Até aqui "o motor" era o Docker do autor:
Docker Desktop, WSL 2, um `.env` à mão e 15 a 40 minutos de `docker compose
build`. Para outra pessoa, isso não é instalar um programa, é montar um ambiente.
O autor pediu um instalador de um clique, que use a placa de vídeo se houver e se
atualize sozinho, e que o Docker dele continue funcionando.

**Decisão.**

1. **Python de verdade, instalado pelo `uv`, e não um executável congelado.**
   PyInstaller com torch, mediapipe e ctranslate2 dá mais de 2 GB, *hooks* frágeis
   e, a cada atualização, tudo de novo. O instalador (Inno Setup, grátis) traz só
   o que não depende da máquina — o código (~1 MB zipado), o `uv`, o ffmpeg e o
   deno — e o `instalar.ps1` baixa o resto: um CPython 3.11 só do Cortes (`uv
   python install`, `--python-preference only-managed`, para nunca depender do
   Python que a pessoa tiver), as bibliotecas (~350 MB) e, **só onde há placa
   NVIDIA**, as de CUDA do whisper (~1 GB). A atualização passa a ser do código;
   as bibliotecas só mudam quando a lista delas muda.
   - **torch de CPU** (o do PyPI no Windows, ~200 MB contra ~2,5 GB). A placa fica
     com o que mais pesa: o whisper (ctranslate2) e o NVENC do ffmpeg. O
     TransNetV2 lê quadros de 48×27, que a CPU aguenta.
   - **O YOLO (AGPL) não vai** (ADR-003): nem `ultralytics`, nem `torchvision`.
2. **Por usuário, sem administrador** (`PrivilegesRequired=lowest`,
   `%LOCALAPPDATA%\Cortes`): fora das pastas que o OneDrive sincroniza.
   Desinstalar leva o programa e **deixa `dados\`** — são os cortes da pessoa.
3. **Sem assinatura digital** (é paga). O Windows avisa na primeira vez, e o site
   explica o "Mais informações → Executar assim mesmo". O SignPath Foundation
   assina projetos abertos de graça; fica para quando houver usuários além do
   círculo do autor.
4. **O ajudante usa a porta 8001; a 8000 é do Docker.** No login os dois sobem
   juntos e o ajudante quase sempre chega antes: na mesma porta, o container do
   Docker morreria com "port is already allocated", em silêncio. O site procura a
   8000 e depois a 8001, e quando o Docker atende o ajudante para o motor dele —
   depois de terminar o job que estiver rodando. Só escuta em 127.0.0.1.
5. **Cada versão numa pasta, e um arquivo diz qual vale** (`versoes\<versão>\` e
   `atual.txt`). Trocar de versão é reescrever o arquivo (atômico), não renomear a
   pasta do motor: no Windows um rename falha com qualquer arquivo aberto lá
   dentro — o antivírus examinando o que acabou de ser extraído, por exemplo. O
   atalho, o menu Iniciar e o início com o Windows chamam o `iniciar.py`, que a
   atualização nunca troca e que cai na versão completa mais nova se o
   `atual.txt` apontar para o nada.
6. **A atualização verifica antes de trocar, e volta atrás sozinha.** De 6 em 6
   horas o ajudante confere o GitHub Releases e prepara a versão nova sem parar
   nada; troca só com a fila vazia e ninguém no painel há 5 minutos (o `/health`
   diz as duas coisas). A troca é de outro processo, depois que o ajudante sai — o
   Windows não deixaria o `uv` substituir o Pillow e o pystray que ele tem
   carregados. A versão nova sobe numa porta de teste, com pastas temporárias, e
   o `main.py` tem de importar. Não passou: não vira a atual, as dependências da
   anterior voltam (os pinos são exatos) e ela não é tentada de novo.
7. **Versão = contagem de commits da `main`.** Só cresce, e o Docker calcula a
   mesma coisa pelo git (`versao_do_motor.py`): o site compara com a publicada e,
   **só no Docker** — que se atualiza pelo `atualizar.bat` —, avisa quando o motor
   ficou para trás.
8. **Publicação pelo CI do Windows, e só quando o motor muda.** Com o motor e o
   instalador verdes — instalar sem janela, processar um vídeo pelo motor
   instalado, trocar para uma versão boa e voltar de uma quebrada, desinstalar —,
   o instalador vai para o GitHub Releases. A impressão digital do conteúdo decide:
   um commit de documentação ou do painel não publica nada e não reinicia o motor
   de ninguém. Ficam as 5 versões mais novas.
9. **Sob o ajudante, pedido que altera algo só vem de página autorizada**
   (`CORTES_ORIGEM_ESTRITA`). O CORS decide quem lê a resposta, não quem manda o
   pedido: um formulário de qualquer site disparava um `POST` simples no motor, e
   o job rodava. Com a origem fora da lista, 403 antes do endpoint. Sem `Origin` é
   programa, não navegador, e passa. O Docker não liga ainda: o painel aberto de
   outro aparelho da rede passa pelo proxy do Vite com a origem daquele aparelho.

**O que o CI não prova**, e fica para o teste no PC do autor (`COMO-EXECUTAR.md`):
a placa de vídeo, o download do YouTube, a IA de verdade, o ícone na bandeja e o
aviso do SmartScreen.

**Consequências.** O repositório passa a ter um segundo caminho de execução que o
Linux do CI não roda — daí o `windows.yml`, que custa ~10 minutos por envio.
Instalar exige internet (o Python e as bibliotecas vêm na hora). E a pessoa ainda
precisa de uma chave de IA: hoje, a do Gemini colada em Configurações, ou um
`dados\.env` com as da cascata — pendente de uma forma mais simples.

> **Nota de 25-set-2026:** as duas pendências fecharam. O Python passou a vir
> DENTRO do instalador (24-set, depois do erro 448; só as bibliotecas vêm na
> hora), e as chaves de todas as IAs da cascata se colam em Configurações →
> Chaves de IA: o motor confere cada uma com a IA e a guarda (`chaves_ia.py`),
> sem arquivo para editar.

**Revisão se:** o `uv` deixar de publicar o CPython standalone para Windows; o
tamanho das bibliotecas tornar a instalação inviável em conexão lenta (aí um
instalador "completo", com tudo dentro, como segunda opção); ou o Mac e o Linux
entrarem (Fase 6.4), quando a pasta, o atalho e o início com o sistema mudam de
forma, e a estrutura de versões fica.

### Nota (24-set-2026, mesmo dia): o Python passou a vir no instalador

O primeiro teste no PC do autor morreu no item 1: `uv python install 3.11`
respondeu *"Failed to create Python minor version link directory"*, erro 448
(*"o caminho não pode ser atravessado porque contém um ponto de montagem não
confiável"*). O uv cria um atalho de pasta (junction) para cada versão menor do
Python; o Inno Setup 6.7 liga por padrão a **RedirectionGuard** do Windows, que
recusa atravessar atalho criado por usuário comum; e ela passa aos programas que o
instalador abre — ao contrário do que diz a ajuda do Inno, e medido no CI: com a
proteção forçada, o PowerShell do `instalar.ps1` a registra ligada. Foi assim que
chegou ao uv. O CI nunca viu porque o runner do GitHub é administrador — atalho de
administrador é "confiável".

O item 1 muda em uma coisa: **o CPython standalone vem dentro do `.exe`**
(`empacotar.py --python`), e o `uv` roda com `UV_PYTHON_DOWNLOADS=never` — usa esse
Python e nunca baixa outro, que é o que criaria o atalho de novo. O instalador
cresce umas dezenas de MB, e a instalação deixa de depender do servidor de onde o
uv baixava o Python. Junto: `RedirectionGuard=no` (a proteção é para instalador
administrador mexendo em pasta que qualquer um escreve; este roda como a própria
pessoa, na pasta dela) e, no `windows.yml`, uma instalação como **usuário comum**,
com a proteção forçada, para que o caso que falhou tenha teste.

**A marca virou Virtu Clips no mesmo dia** (a logo do autor): o instalador é o
`Instalar-Virtu-Clips.exe` e o item 2 passa a morar em `%LOCALAPPDATA%\VirtuClips`.
O AppId continua o mesmo — uma entrada só em "Aplicativos" — e o instalador traz os
projetos da pasta `Cortes` antiga e apaga o resto dela.
