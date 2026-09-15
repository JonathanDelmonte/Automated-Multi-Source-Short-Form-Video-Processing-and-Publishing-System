# Oportunidades: o que a ferramenta tem além do plano

Levantado em 13-set-2026, antes de remover a superfície de marketing herdada
do upstream, a pedido do autor: *"antes de apagar tudo, faça uma análise de
funcionalidades que essa ferramenta tem e que o nosso plano inicial não tem."*

## Por que este documento existe

O `PLANO-TECNICO.md` foi escrito olhando o problema, não o código. Depois da
Fase 0 o código está lido, e ele contém **capacidades inteiras que o plano não
previu** — algumas porque o plano não pensou nelas, outras porque o plano as
descreveu numa linha e o upstream gastou milhares nelas.

Isso importa por um motivo prático: várias fases do roadmap estão parcialmente
construídas e o plano não sabe. A Fase 2 (motor de template) tem um renderizador
React funcionando; a Fase 5 (calibrar detecção) tem instrumentação de custo
pronta. Planejar sem esse inventário é reescrever o que já existe.

**Este documento não é um roadmap.** É o insumo para revisar o roadmap. Nada
aqui está decidido; a Parte C propõe uma ordem e o autor decide.

## Como foi levantado, e o que isso não cobre

Lido: os 46 módulos Python da raiz (17.523 linhas), os 30 endpoints de
`app.py`, as 7 ferramentas de `mcp_server.py`, os 33 componentes React do
painel, as composições Remotion e o `tailwind.config.js`/`tokens.css`.
Cruzado contra as seções 4 a 9 do `PLANO-TECNICO.md`.

**Limite honesto:** isto é leitura de código e docstring, não medição. Onde
digo "funciona", quero dizer "está implementado e tem caminho de chamada"; só
a cascata de LLM foi verificada rodando (`/api/config`, os dois provedores
`ready: true`). Um recurso pode estar implementado e ser ruim — a Parte C marca
quais merecem teste antes de contar com eles.

## O placar

| | |
|---|---|
| Capacidades que a ferramenta tem e o plano não previu | **11** |
| Dessas, que adiantam uma fase do roadmap | 4 (Fases 1, 2, 3 e 5) |
| Capacidades que o plano prevê e a ferramenta não tem | **8** |
| Dessas, que são pré-requisito de outra coisa | 3 |

---

# Parte A — O que a ferramenta tem e o plano não previu

## A1. Reenquadramento: o plano pede uma linha, existem oito modos

O plano, seção 4, estágio 05: *"falante ativo → caminho de câmera suavizado."*
Uma linha. O que está implementado:

| Modo | Arquivo | Para quê |
|---|---|---|
| TRACK | `main.py`, `reframe_v2.py` | um sujeito; MediaPipe + estabilização "tripé pesado" |
| GENERAL | `reframe_v2.py` | grupo ou paisagem; fundo desfocado preservando a largura |
| SPLIT | `split_layout.py` (279) | conversa a dois, empilhada em meias-telas |
| SCREENCAST / WIDE | `screencast_layout.py` (335) | conteúdo cujo sentido está fora do centro |
| INSET | `camera_inset.py` (291) | tela cheia em cima, webcam de canto ampliada embaixo |
| PANEL | `panel_layout.py` (274) | 3 ou 4 pessoas de um plano aberto, ladrilhadas |
| ALTERNATE | `active_speaker.py` (290) | corte seco para quem fala |
| PUNCH-IN | `punch_in.py` | ~12% de aproximação nas batidas |

Mais um **seletor por IA** (`layout_picker.py`): 12 fotogramas a 1024px para o
Gemini, uma chamada por vídeo de origem, escolhendo entre opções fechadas.
Medido pelo upstream em 48 clipes: 92–96% de acerto.

**O que isso quer dizer para o plano:** o estágio 05 não precisa ser escrito.
Precisa ser **avaliado** com material seu. A pergunta deixa de ser "como
reenquadrar" e passa a ser "quais desses oito modos o meu conteúdo usa, e o
seletor acerta nele?".

## A2. Edição por clipe (EDL) — o plano não tem edição manual nenhuma

`recut.py` (342) + `ClipEditor.jsx` (1.613) + `/api/clip/{}/edl` +
`/api/clip/rerender`.

Cada clipe carrega uma **receita**: a lista de segmentos da fonte que o
compõem. A interface permite aparar, estender, dividir e reordenar esses
segmentos **presos à palavra** da transcrição, e re-renderizar a partir da
receita — sem reprocessar a fonte.

O plano é explícito em não ter isso: *"Não é um editor de timeline."* A
intenção era manter a Fase 2 simples, e é uma boa intenção. Mas o corte
automático erra o começo da frase com frequência, e a alternativa a um ajuste
de dois cliques é descartar o clipe. **Isto existe, funciona e não custa nada
manter.**

## A3. Thumbnail Studio — uma categoria inteira ausente do plano

`thumbnail.py` (788) + `ThumbnailStudio.jsx` (1.039) + 6 endpoints.

- Títulos a partir da transcrição **mais 10 fotogramas**, nunca do vídeo
  inteiro (mesma economia do seletor de layout)
- Duas chamadas: brainstorm de 25 títulos, depois um crítico que pontua,
  remove ângulos repetidos e devolve 10, cada um com um `thumbnail_text` de
  1–4 palavras que **complementa** o título em vez de repeti-lo
- Regras embutidas: desfecho dentro de 50 caracteres (é onde o celular corta),
  palavra-chave nos 3 primeiros termos, mesmo idioma da transcrição
- Imagens são N **conceitos diferentes**, não um prompt repetido; por padrão o
  modelo deixa um lado como espaço negativo e o PIL escreve o texto em Anton
  com contorno — assim acento e ortografia nunca saem errados
- `/api/thumbnail/frames/{session}` pontua fotogramas por área de rosto e
  nitidez (MediaPipe + Laplaciano) e oferece o **criador** como referência,
  em vez de um rosto genérico

**O plano não menciona thumbnail em lugar nenhum.** É um ponto cego: um corte
publicado no YouTube Shorts compete pela miniatura tanto quanto pelo gancho.

## A4. Acesso por agente (MCP) — o plano não previu agentes

`mcp_server.py` (603) + `mcp_stdio.py` + `mcp_ui.py` (195).

O pipeline inteiro exposto como ferramentas para agente, em JSON-RPC:
`process_video`, `create_upload`, `get_job_status`, `list_clips`, `get_quota`,
`add_subtitles`, `recut_clip`. Cada ferramenta chama de volta o próprio app
em processo (`httpx.ASGITransport`), então **não consegue divergir** do
comportamento REST.

O `mcp_ui.py` é o detalhe fino: um seletor de clipes embutido para clientes MCP
com interface. Escolher entre 3 e 15 clipes olhando para eles é melhor do que
ler títulos em JSON.

**Onde isso encosta no plano:** a seção 6 quer publicação automatizada. Um
agente que já sabe cortar e consultar status é metade do caminho para "o
sistema roda sozinho" — e é uma metade que o plano ia construir do zero.

## A5. Renderizador Remotion — a Fase 2 já tem metade pronta

`render-service/` (Node) + `remotion/src/` + `/api/render`.

Uma composição `ShortVideo` em React, com `HookOverlay`, `Subtitles` e
`VideoEffects` (zoom, brilho, contraste, saturação por faixa de tempo), com
schema de props validado e duração/fps/dimensões calculados por metadados.

A seção 5 do plano quer *"um documento de configuração versionado que o
renderizador lê"*. **O renderizador existe.** Falta o documento — e a Fase 0.5
já criou a tabela `templates` com `spec_json` e o seed já gravou o
"Padrão Cortes v3" inteiro nela.

Ou seja, a Fase 2 é hoje: ligar `templates.spec_json` às props do
`ShortVideo`. Isso é muito menos que "construir um motor de template".

## A6. Transcrição com backend alternativo

`transcribe_backends.py` (380): NVIDIA Parakeet (onnx-asr) com faster-whisper
como reserva, ambos atrás de um `transcribe_media()` que devolve o mesmo
contrato. O plano diz só "faster-whisper".

Importa porque a transcrição é o estágio mais caro em tempo de parede — no
relatório de custo é ele que domina. Um backend mais rápido muda o custo do
projeto inteiro, e a escolha já está atrás de uma interface.

## A7. Detecção de cena neural

`scene_detection.py`: TransNetV2, detector neural de corte de plano, com o
threshold clássico como reserva. O plano diz "PySceneDetect". Aguenta câmera
rápida e transição suave, onde o método por limiar inventa cortes.

## A8. Hook grounding — o gancho olha a tela

`hook_grounding.py`: quando o clipe é de tela (planilha, diálogo de
configuração), o gancho tirado só da transcrição descreve o *tema do vídeo* em
vez de nomear **o que está na tela**. Depois do render, se o sidecar de layout
disser que ≥25% do clipe é screencast/wide/inset, três fotogramas vão ao Gemini
e gancho e título são reescritos no lugar — com os originais preservados em
`hook_grounding.before`.

É o tipo de correção que ninguém planeja porque ninguém prevê o problema antes
de ver o resultado errado.

## A9. Sonda de qualidade pré-voo

`quality_probe.py`: antes de começar o job, descobre em subprocesso curto qual
a resolução máxima que a fonte oferece, para o usuário decidir antes de gastar
tempo. O plano não tem nada entre "escolher a fonte" e "processar".

## A10. Operação: resume, heartbeat, drain, handover

`.resume.json` com heartbeat de 10s, varredura a cada 30s re-enfileirando só o
que ninguém bateu há 60s, marcador de instância, drain em SIGTERM,
`/health/ready` para tirar a instância da rotação, checkpoint de transcrição
para não repetir o estágio caro num job re-executado.

O plano trata "job" como se rodar fosse garantido. **Isto é o que separa um
script de um serviço**, e veio de graça.

## A11. Legenda como operação reversível

`/api/subtitle` e `/api/subtitle/remove`: aplicar, trocar estilo e remover
legenda **depois** do render, sem reprocessar. Casa exatamente com a regra que
o plano defende na seção 5 ("aplicar o template no download, não no render") —
o upstream já a implementou para legenda.

---

# Parte B — O que o plano prevê e a ferramenta não tem

Os buracos reais, que continuam sendo trabalho a fazer.

| # | O plano quer | Situação | Peso |
|---|---|---|---|
| B1 | **`SourceAdapter`**: Twitch VOD/live, Google Drive, canal do YouTube por `playlistItems.list` | só upload e URL do yt-dlp | **Fase 1, o maior** |
| B2 | **`Publisher`** e seus drivers, com o `manual` como default | ~~nada~~ **feito na Fase 3** (15-set-2026): `publishers/`, `manual` com pacote do dia, `youtube-api` com quota, `aggregator`/`browser` como stub | ✅ |
| B3 | **Diarização** no estágio 03 | não existe. O que há é `active_speaker.py`, que lê **movimento de boca em vídeo** — resolve "quem está falando agora na tela", não "quantas pessoas há e qual disse o quê" | pré-requisito de rubrica por falante |
| B4 | **`safeArea`** do template (12% topo / 18% base) lido no render | **parcial**, e melhor do que parecia — ver abaixo | fiação da Fase 2 |
| B5 | **`cuts.removeSilence`** | no spec, sem implementação | densidade do corte |
| B6 | **BGM com ducking sidechain** | no spec, sem implementação | — |
| B7 | **Preview de 3 segundos** antes de queimar o render inteiro | não existe | economiza GPU e paciência |
| B8 | **`metrics`** com retenção real realimentando a rubrica | tabela criada na Fase 0.5, vazia; nada coleta | **Fase 5, o fosso** |

Sobre o B3, porque é sutil: o plano pede diarização para a **detecção** saber
quem falou. O `active_speaker` responde para o **reenquadramento** onde apontar
a câmera. São perguntas diferentes com respostas diferentes, e ter um não dá o
outro.

Sobre o B4, porque a primeira leitura estava errada e vale registrar: procurar
`safeArea` no código só acha o seed, os modelos e o teste — nada *lê* o campo,
e daí a conclusão fácil de que toda legenda cai atrás dos botões do TikTok.
**Não cai.** O `subtitles.py` resolve o caso pela própria conta:

```python
# Vertical margin for burned captions, in PlayResY=288 units (~15% of frame
# height). The old hardcoded 25 (8.7%) put captions underneath TikTok's and
# Reels' own bottom UI ... partly covered on the platform even though the
# exported file looked fine.
SAFE_MARGIN_V = 43
```

Ou seja: a faixa de baixo já é respeitada, a ~15% contra os 18% que o plano
pede, e por uma constante que alguém ajustou depois de ver o problema
acontecer. O que de fato falta é menor e diferente do que parecia:

- **a faixa de cima (12%) não é reservada por ninguém** — vale para hook,
  logo e qualquer overlay, não para legenda;
- **o valor é constante do módulo, não vem do `spec_json`** — trocar de
  template não muda a margem, o que contraria a ideia de template versionado
  da seção 5.

Isso deixa de ser "conserto urgente" e vira **fiação**, dentro do item 4 da
Parte C. A lição de método fica: ausência de referência ao campo não é ausência
do comportamento.

---

# Parte C — Melhorias, na ordem que eu faria

Ordenado por (valor ÷ esforço), não por empolgação.

### Primeiro: o que não custa código

1. **Avaliar os oito modos de layout (A1) com material seu.** Nenhuma linha
   escrita: rodar 10 clipes seus e anotar onde o seletor acerta e onde erra.
   É o que decide se a Fase 2 precisa mexer em reenquadramento — e pode muito
   bem decidir que não precisa. Feito antes de qualquer outra coisa, evita
   trabalho em cima de suposição.
2. **Preview de 3 segundos (B7).** O renderizador Remotion já aceita duração
   por props; é recortar a janela. Paga-se sozinho na primeira vez que um
   template errado seria descoberto depois do render inteiro.

### Depois: o que destrava uma fase inteira

3. **Ligar `templates.spec_json` às props do `ShortVideo` (A5 + B4, Fase 2).**
   A tabela existe, o seed tem o template, o renderizador existe. É o encontro
   dos três, não construção nova. Leva junto o `safeArea`: a margem de baixo
   deixa de ser constante do `subtitles.py` e passa a vir do template, e a de
   cima passa a existir para hook e overlay.
4. **`SourceAdapter` (B1, Fase 1).** Continua sendo o maior item do roadmap e
   nada do que foi achado aqui o adianta. Começar pelo canal do YouTube via
   `playlistItems.list`, que a seção 4 marca como o único caminho sem risco de
   ToS.
5. ~~**`Publisher` com o driver `manual` (B2, Fase 3).**~~ **Feito**
   (15-set-2026). O plano tinha razão em chamá-lo de "90% do trabalho": o
   pacote diário sai em `GET /api/publicacoes/pacote`, com um `.txt` por corte
   e por plataforma — título, descrição e hashtags, sem rótulo a apagar depois
   de colar. O que sobrou para a Fase 4 é o **gatilho**: hoje é um botão, e o
   agendador com jitter é o ADR-007.

### Ganhos que o plano não sabia que podia ter

6. **Medir Parakeet contra faster-whisper (A6).** A transcrição domina o tempo
   de parede; a interface já está pronta para trocar. Uma medição decide.
7. **Thumbnail Studio no fluxo (A3).** Já funciona. A pergunta é se entra no
   pipeline automático ou fica como passo manual — e isso depende de você
   publicar no YouTube ou só em Shorts/Reels/TikTok.
8. **MCP como caminho de automação (A4).** Se o objetivo declarado é "100%
   automatizado", um agente que já sabe operar o pipeline é uma alternativa
   séria a escrever o agendador da Fase 4 do zero. **Ficou mais forte com a
   Fase 3**: `/api/publicar` é mais uma ferramenta que o agente já saberia
   chamar, e o resolvedor garante que nem um agente confuso alcança o driver de
   risco (ADR-010) — a porta não é a educação de quem chama, é o `risk_score`.

### Vindo do primeiro uso real (13-set-2026)

Levantado pelo autor ao mandar o primeiro vídeo pelo painel. Ambos são sobre a
mesma coisa: **o que a interface conta enquanto um job de 10 minutos roda.**

10. **Não existe progresso — nem na interface, nem na API.** A reclamação foi
    "não tem nenhuma barra de progresso, não consigo entender o que está
    acontecendo", e o `GET /api/status/{job_id}` explica por quê: ele devolve
    `{status, logs, result, timings}` e nada mais. O painel não mostra
    porcentagem porque **o backend nunca calculou uma**. Não é trabalho de
    frontend: é o pipeline passar a reportar onde está.

    O caminho barato já existe e não pede medição nova: o `job_metrics` abre e
    fecha cada estágio por nome (`01_ingest`, `03_transcribe`, `04_detect`,
    `05_06_render`), então dá para expor "estágio 3 de 5, transcrevendo" a
    partir do que já é instrumentado. Porcentagem dentro do estágio é outra
    conversa -- o download tem (o yt-dlp reporta), a transcrição não.

    Importa mais do que parece em CPU: o estágio de transcrição domina o tempo
    de parede e fica minutos em silêncio na primeira execução, baixando o
    modelo do Whisper. Silêncio longo sem sinal é o que faz alguém recarregar a
    página ou matar o container no meio.

11. **Botão de copiar o log.** Pequeno, e resolve um caso concreto: hoje, para
    mandar um erro a quem pode ajudar, é preciso selecionar texto num painel que
    rola sozinho. A alternativa que existe -- abrir
    `localhost:8000/api/status/<job-id>` e dar Ctrl+A -- funciona, mas depende
    de saber o id e de conhecer o endpoint.

### O que coletar desde já, mesmo sem usar

9. **Começar a gravar `metrics` (B8).** Enquanto não houver publicação
    própria, dá para anotar à mão a retenção dos clipes publicados. A tabela
   existe. Seis meses de dados ruins valem mais que zero — e é o único item
   da lista cujo custo cresce com a espera.

---

# Parte D — O frontend: o que preservar quando trocar

O autor vai reescrever o painel inteiro. O que vale copiar, e o que não vale:

### Vale — e é pequeno

| O quê | Onde | Tamanho |
|---|---|---|
| **Os tokens de design** | `dashboard/src/tokens.css` | **53 linhas** |
| O mapeamento deles para o Tailwind | `dashboard/tailwind.config.js` | ~60 linhas |
| As classes de componente (`btn-ghost`, `card`…) | `dashboard/src/index.css` | 266 linhas |
| Três primitivos de UI | `components/ui/` (Modal, SegmentedControl, StepIndicator) | ~200 linhas |

O sistema chama-se **"Lumen · Night Foundry"**. Paleta inteira em OKLCH, em
camadas nomeadas por função e não por cor: `paper` / `paper2` / `paper3` para
os planos de fundo, `ink` / `ink2` / `muted` para os três níveis de texto,
`rule` / `rule2` para as divisórias, `brass` para o acento. Tipografia em três
famílias com papel definido (Instrument Serif no display, Geist no corpo,
JetBrains Mono nos rótulos micro), e `--text-display` em `clamp()`, que é o que
faz o título responder ao viewport sem media query.

**São ~580 linhas que carregam todo o "espaçamento e organização" que você
elogiou.** As outras 4.800 linhas de landing e pricing não carregam nada disso
— elas apenas *usam*. Copiar os tokens e escrever telas novas em cima dá o
mesmo resultado visual sem herdar uma linha de marketing.

### Vale ler antes de redesenhar, não copiar

- `MediaInput.jsx` (373) — a hierarquia do formulário de entrada: arquivo vs
  URL como abas, formato de saída como cartões, e o resto atrás de
  "advanced options". É a decisão de o que esconder, e ela está bem tomada.
- `ProcessingAnimation.jsx` + `ResultCard.jsx` — o que mostrar enquanto um job
  de 10 minutos roda. Espera longa sem feedback é o que faz o usuário recarregar
  a página.
- `App.jsx:786-795` — uma definição de navegação alimenta três superfícies
  (trilho no desktop, gaveta no celular, barra inferior). Padrão bom, e a
  numeração com buracos (01, 03, 05, 07) é um resquício de itens removidos.

### Não vale nada

`Landing.jsx` (808), `PricingPage.jsx` (323), `PricingSection.jsx` (189) e
`dashboard/seo/` (3.541). São copy de um produto comercial de terceiro,
anunciando features que este fork removeu. É o que sai agora.
