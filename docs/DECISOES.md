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

**Estimativa revisada:** 3–5 dias, contra os 2–3 originais. A incerteza está em onde o
caminho self-host guarda estado de job hoje — e dimensionar isso é exatamente o
entregável da Fase 0.2, que manda ler o código enquanto ele roda.
