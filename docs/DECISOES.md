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

**Data:** 2026-09-12 · **Status:** parcial
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
