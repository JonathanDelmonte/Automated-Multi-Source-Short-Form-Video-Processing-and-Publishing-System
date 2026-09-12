# Plano Técnico

**Repositório:** `Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System`
**Versão do documento:** 2 — 12 de setembro de 2026
**Status:** pré-código. Nenhuma linha escrita ainda.

Sistema self-hosted que recebe vídeo longo de qualquer origem, gera cortes verticais com template de marca fixo e publica por uma camada de drivers intercambiáveis.

---

## Restrições travadas

| Restrição | Decisão |
|---|---|
| **Custo** | 100% gratuito na fase inicial. Nenhuma API paga, nenhuma mensalidade. |
| **Escopo** | Uso pessoal agora, com multi-tenancy prevista no schema desde o primeiro commit. |
| **Publicação** | Camada de drivers intercambiáveis — quatro modos, configuráveis por plataforma e por conta. |
| **Automação** | Processo inteiro automatizado. Nenhuma etapa que exija abrir um app de terceiro. |
| **Base** | Fork de projeto MIT existente (ver auditoria). |

---

## 1. Entendendo os limites das plataformas

### YouTube: quota, não dinheiro

O YouTube não cobra nada pela API. O que ele dá é um orçamento diário de **unidades de quota** — moeda interna, fictícia, que zera toda meia-noite no horário do Pacífico. Cada projeto no Google Cloud nasce com **10.000 unidades por dia**, de graça.

| Operação | Custo | Cabem em 10.000 |
|---|---|---|
| Listar vídeos de um canal (`playlistItems.list`) | 1 un. | 10.000 |
| Buscar (`search.list`) | 100 un. | 100 |
| **Subir um vídeo** (`videos.insert`) | **1.600 un.** | **6 por dia** |

Quando acaba, não chega fatura — a API responde `quotaExceeded` até o dia virar. Dá pra pedir aumento por formulário no Google Cloud Console.

> **Na prática:** a 3 vídeos/dia você gasta 4.800 das 10.000 gratuitas. Sobra quase metade pra listar, checar status e reprocessar falha. **A quota do YouTube não é um gargalo neste projeto.**

### TikTok: permissão, não quota

No TikTok não existe orçamento diário. Existe uma **permissão** que você não tem até provar que merece. Enquanto o app não passa na auditoria de Content Posting, todo post publicado via API sai como `SELF_ONLY` (visível só pra você) ou cai como rascunho esperando você concluir no app.

Publicar público direto exige submeter o app à auditoria, demonstrar a interface dentro das regras e esperar semanas. É por isso que existem agregadores (Ayrshare, Blotato, Upload-Post, PostPeer): você aluga a auditoria já aprovada deles. **Todos são pagos — ficam fora da fase inicial.**

### Automação de navegador: o que ela é e o que não é

Funciona tecnicamente: Playwright com contexto persistente, sessão logada salva em disco. Sem quota, sem auditoria, sem mensalidade. Mas dois pontos precisam ficar registrados:

**Um robô nunca vê mais que a conta que ele usa.** Ele entra com o mesmo cookie de sessão e enxerga exatamente o que o humano logado enxerga. VOD sub-only da Twitch continua exigindo conta inscrita; vídeo privado continua privado. O que o robô ganha não é permissão — é paciência e repetição.

**A detecção não procura o Playwright.** Ela cruza fingerprint de navegador, fingerprint de TLS e padrão de comportamento: postagens em horários regulares demais, sem movimento de mouse, sem hesitação de digitação. A punição não é erro HTTP tratável no `catch` — é shadowban silencioso ou perda da conta. Num projeto de cortes, a conta é o ativo.

**Decisão:** o driver existe na arquitetura, mas nasce **desligado por padrão e fora da cascata de fallback automático**. No volume alvo, a API oficial resolve de graça.

---

## 2. Auditoria das bases open-source

Quatro candidatos, todos MIT, todos Python + FastAPI no backend com React no front. Trocar de base depois não é catastrófico, e portar módulo de um pro outro é viável.

| Projeto | Tração | Fontes | Template de edição | Publicação |
|---|---|---|---|---|
| **openshorts** | 2.4k ★ · 669 forks | YouTube, upload, URL de site | parcial — legendas ASS, thumbnails | Upload-Post (TikTok, IG, YT) |
| **clippyme** | 0 ★ · 473 commits | YouTube, upload | **o mais forte** — 6 presets karaokê, logo, hook, color grading, smart cut | Zernio + SmartScheduler |
| **opensource-clipping** | 43 ★ · 207 commits | **YouTube, TikTok, IG, Google Drive** | **o mais rico** — hook 3s, B-roll Pexels, BGM com ducking, split-screen de podcast | nativo, só YouTube + Facebook |
| **autoclip** | 8 ★ · 19 commits | upload, YouTube (trava sem auth) | 4 estilos, só legenda | nenhuma — só exporta arquivo |

### O que nenhum dos quatro tem

- **Twitch como fonte.** Adapter escrito do zero — é fácil, `yt-dlp` já fala Twitch.
- **Autenticação e multi-tenancy.** O clippyme avisa explicitamente que só deve rodar em LAN confiável.
- **Camada de publicação plugável.** Cada um casou com um fornecedor único e chumbou a chamada no código.
- **Arquivo grande de verdade.** O openshorts limita upload a 2GB.

### Veredito

**Forkar o `openshorts`.** Não porque é o mais completo — não é. Porque 2.4k estrelas e 669 forks significam que os bugs chatos de `ffmpeg`, de `yt-dlp` quebrando e de tracking de rosto travando já foram encontrados e corrigidos por outra gente. Esse é o ativo que não dá pra escrever sozinho.

`clippyme` e `opensource-clipping` viram **repositórios doadores**: ler o código, portar os módulos bons, creditar no `NOTICE`. Especificamente:

- **Do clippyme:** o motor de template, e principalmente o truque de aplicar legenda e logo *na hora do download*, sem reprocessar o vídeo. É a melhor ideia de arquitetura dos quatro.
- **Do opensource-clipping:** o adapter de Google Drive, o sistema de hook e B-roll, e o uso de `edge-tts` (gratuito) no lugar do ElevenLabs.
- **Do autoclip:** a decisão de fazer a detecção de momento retornar **índice de palavra em vez de timestamp**. LLM erra aritmética de tempo; não erra contagem de item em lista.

O `autoclip` é imaturo demais pra ser base — 19 commits.

### Dependências pagas a remover do fork

O openshorts vem com integrações que violam a restrição de custo zero:

| Dependência | Por quê | Ação |
|---|---|---|
| fal.ai (Flux, Hailuo, VEED, Kling) | Pago, e pertence ao módulo de AI UGC com atores sintéticos | Remover o módulo inteiro |
| ElevenLabs (dublagem) | Pago | Remover, ou trocar por `edge-tts` |
| Upload-Post | 10 uploads grátis/mês — insuficiente para ~90/mês | Substituir pela camada Publisher própria |
| AWS S3 | Pago acima do free tier | Disco local na fase 1 |

---

## 3. Stack 100% gratuita

| Camada | Escolha | Custo | Limite real |
|---|---|---|---|
| Transcrição | `faster-whisper` local (small/medium) | zero | só CPU/GPU |
| Diarização | `pyannote` | zero | exige token HuggingFace (grátis) |
| Detecção de momento | cascata de LLMs grátis (abaixo) | zero | rate limit por provedor |
| Detecção de rosto | MediaPipe | zero | ver nota de licença |
| Composição | `ffmpeg` | zero | nenhum |
| TTS (se usar) | `edge-tts` | zero | nenhum |
| B-roll (se usar) | API do Pexels | zero | 200 req/hora |
| Storage | disco local | zero | seu HD |
| Banco | PostgreSQL ou SQLite local | zero | nenhum |
| Fila | Redis local | zero | nenhum |
| Publicação | YouTube Data API + driver manual | zero | 6 uploads/dia |

### Cascata de LLM — mesmo padrão do Publisher

Nenhum provedor gratuito é confiável sozinho. O Google parou de publicar o RPD do free tier na documentação, e medições independentes chegaram a encontrar **20 requisições por dia** em alguns modelos. Depender só dele é frágil.

Limites divulgados em setembro de 2026 — **confirme antes de codar, isso muda toda hora**:

| Provedor | RPM | Por dia | Contexto | Cartão? | Pegadinha |
|---|---|---|---|---|---|
| **Groq** | 30 | 1.000 | 128k | não | ~320 tok/s, o mais rápido |
| **Cerebras** | 30 | ~1M tokens | 128k | não | teto é de tokens, não de chamadas |
| **Google AI Studio** | 5–15 | 20–1.500 | **1M** | não | **usa seus dados para treino fora da UE/UK/EEA** |
| **GitHub Models** | 15 | 150–1.000 | varia | não | inclui GPT-4o e Claude 3.5 Sonnet |
| **Mistral** | varia | ~1B tokens/mês | 128k | não | tier Experiment usa dados p/ treino |
| **OpenRouter** | 20 | 50 | varia | não | 50/dia é pouco demais |
| **Ollama local** | ∞ | ∞ | do modelo | não | custa sua GPU, qualidade menor |

**Ordem recomendada:**

1. **Groq (Llama 3.3 70B)** — primário. 1.000/dia cobre com folga, e a velocidade encurta o job inteiro.
2. **Gemini Flash** — quando precisar de contexto gigante (transcript inteiro de live de 4h).
3. **Cerebras** — terceiro.
4. **Ollama local** — rede de segurança. Nunca falha, nunca tem limite.

```python
class LLMProvider(Protocol):
    id: str
    max_context: int
    def available(self) -> bool: ...          # checa rate limit local antes de chamar
    def complete(self, prompt: str, schema: dict) -> dict: ...

CASCADE = [Groq(), GeminiFlash(), Cerebras(), Ollama()]
```

> **Alerta de privacidade:** o free tier do Google AI Studio usa os dados enviados para treinar modelos fora da UE/UK/EEA — o Brasil está incluído. Para conteúdo próprio isso costuma ser aceitável. Se o projeto virar SaaS com conteúdo de cliente, **deixa de ser aceitável** e o Gemini free tier precisa sair da cascata.

### Reduzir consumo até os limites gratuitos sobrarem

Isso é engenharia, não economia. Cada técnica abaixo derruba o número de chamadas ou de tokens:

1. **Pré-filtro heurístico antes do LLM.** Energia de áudio, silêncio prolongado, mudança de falante, densidade de palavras por segundo. Só janelas candidatas chegam ao modelo. Corta de 60% a 80% das chamadas, e é a otimização de maior impacto.
2. **Índice de palavra, não timestamp.** O prompt manda `["hoje","eu","vou",...]` numerado e o modelo devolve `{start: 412, end: 598}`. Economiza tokens e elimina erro aritmético.
3. **Janelas com 20% de sobreposição**, nunca o transcript inteiro numa chamada.
4. **Cache por hash de conteúdo.** Reprocessar o mesmo vídeo custa zero.
5. **Remover muletas do prompt** ("né", "tipo", "hum", "então assim").
6. **Saída em JSON compacto**, nunca prosa.

### Nota de licença — importante para o futuro SaaS

**YOLOv8 da Ultralytics é AGPL-3.0.** A AGPL exige que você publique o código-fonte de qualquer coisa que ofereça o software por rede. Se este projeto virar SaaS de código fechado, usar YOLOv8 obriga a abrir tudo ou comprar licença comercial da Ultralytics.

Saídas: usar **MediaPipe sozinho** (Apache 2.0, suficiente para tracking de rosto), ou **YOLOX / RTMDet** (Apache 2.0). Enquanto for self-hosted pessoal a AGPL não dispara, mas essa escolha fica mais cara de desfazer depois de estar no código inteiro.

O `ffmpeg` compilado com `libx264` é GPL. Para self-hosted não muda nada; se um dia distribuir binário, muda.

---

## 4. Arquitetura

```
01 Ingest     SourceAdapter resolve a origem e entrega um arquivo canônico
02 Probe      ffprobe + extração de áudio 16k mono
03 Transcribe faster-whisper com timestamp por palavra + diarização
04 Detect     cascata de LLM sobre a transcrição, retorna índices de palavra
05 Reframe    falante ativo → caminho de câmera suavizado
06 Compose    template aplicado: legenda, logo, hook, outro, BGM
07 Publish    driver resolvido por plataforma, conta e modo
```

### A regra que sustenta os 10GB: o áudio dirige, o vídeo obedece

Decisão mais importante do projeto, e precisa estar no estágio 02 desde o primeiro commit.

Um vídeo de 10GB vira **cerca de 100MB de WAV 16k mono**. Transcrição, diarização e detecção rodam só nisso. O arquivo grande só é tocado no estágio 05/06, e mesmo aí só nos trechos escolhidos — com `-ss` **antes** do `-i` para o ffmpeg fazer seek rápido em vez de decodificar do começo.

Consequência: o custo de processar cresce com a **duração falada**, não com o tamanho do arquivo. Um MOV 4K de 10GB e um MP4 720p de 800MB com a mesma live dentro custam quase o mesmo.

Na fase 1, com storage local, o upload grande é gravado direto em disco por streaming — nunca carregado em memória. Quando migrar para storage remoto, vira presigned multipart do browser direto pro bucket, em pedaços de 8 a 64MB, retomável.

### Camada de ingestão

| Fonte | Como | Onde trava |
|---|---|---|
| Vídeo do YouTube | `yt-dlp` | Fere o ToS do YouTube mesmo com o canal liberando cortes. Ver seção 8. |
| Canal do YouTube | `playlistItems.list` (1 unidade) + polling da uploads playlist | Nada. É o uso mais barato e legítimo da API. |
| VOD / clip da Twitch | `yt-dlp`, suporte nativo | Sub-only exige cookie de conta inscrita. VOD expira em 7–60 dias. |
| Live da Twitch ao vivo | `streamlink` ou `yt-dlp` gravando em tempo real, fatiado em blocos | Não dá pra baixar o que ainda não aconteceu. Vira worker de longa duração. |
| Google Drive | Drive API v3, `files.get?alt=media`, chunks | OAuth com refresh token. Arquivo grande exige `Range` requests. |
| Upload direto | Streaming pra disco local | Nada, se o arquivo não passar pela memória. |

Todos implementam a mesma interface e devolvem a mesma coisa. O resto do pipeline não sabe de onde veio.

```typescript
interface SourceAdapter {
  id: 'youtube' | 'youtube-channel' | 'twitch-vod' | 'twitch-live' | 'gdrive' | 'upload'
  matches(input: string): boolean
  probe(input: string): Promise<SourceInfo>        // duração, tamanho, permissão
  fetch(input: string, ctx: JobCtx): Promise<{
    storageKey: string
    durationMs: number
    meta: SourceMeta
  }>
}
```

---

## 5. Template de edição

Não é um editor de timeline. É **um documento de configuração versionado** que o renderizador lê. Muito mais simples de construir e de ajustar depois sem abrir código.

```json
{
  "name": "Padrão Cortes v3",
  "aspect": "9:16",
  "hook":     { "mode": "text_punch", "durationMs": 1200, "font": "Anton", "from": "clip.title" },
  "captions": { "preset": "karaoke_fill", "font": "Anton", "sizePt": 84,
                "yAnchor": 0.72, "highlight": "#FFD400", "strokePx": 6, "maxWords": 3 },
  "overlays": [
    { "asset": "logo.png",    "anchor": "top-right", "marginPx": 48, "opacity": 0.9 },
    { "asset": "endcard.mp4", "anchor": "full",      "atEnd": true,  "durationMs": 2000 }
  ],
  "audio":    { "bgm": "lofi_01.mp3", "gainDb": -22, "ducking": "sidechain" },
  "cuts":     { "removeSilence": true, "thresholdDb": -35, "maxGapMs": 400 },
  "safeArea": { "topPct": 12, "bottomPct": 18 }
}
```

Três detalhes que valem travar agora:

- **`safeArea` não é enfeite.** O TikTok cobre os 12% de cima com o nome do perfil e os 18% de baixo com legenda e botões. Legenda fora dessa faixa fica ilegível no app, e é o erro nº 1 de quem automatiza corte.
- **Aplicar o template no download, não no render.** Renderize uma vez o corte reenquadrado e limpo; legenda, logo e outro entram numa segunda passada rápida. Trocar de template depois não reprocessa o vídeo.
- **Preview de 3 segundos.** Antes de queimar minutos de GPU, renderize só o primeiro trecho com o template aplicado.

### Sobre o CapCut

**Fora do projeto.** O CapCut não tem API pública, então integrar exigiria automação de UI — trocar um problema simples (compor com `ffmpeg`, que você controla inteiro) por um difícil (dirigir app de terceiro que muda sem aviso e quebra a automação). Além disso, ele é feito para operação manual, o que conflita com a restrição de processo 100% automatizado.

Tudo que foi citado como funcionalidade desejada dele — logo automática, legenda estilizada, abertura padrão — cabe no JSON acima e sai do `ffmpeg` sem dependência externa.

---

## 6. Camada de publicação

O pipeline termina entregando um `RenderedClip` a uma interface. Quem resolve qual implementação atende é um resolvedor. Nenhum fornecedor encosta no resto do sistema.

```typescript
interface Publisher {
  id: 'youtube-api' | 'aggregator' | 'browser' | 'manual'
  platforms: Platform[]
  capability(account: Account): Promise<'public' | 'private_only' | 'draft' | 'none'>
  publish(clip: RenderedClip, meta: PostMeta, opts: PublishOptions): Promise<PublishResult>
  cost(n: number): { quotaUnits?: number; usd?: number; riskScore: number }
}

// cascata de fallback — browser NUNCA entra aqui automaticamente
resolve(platform, account) =>
  youtubeApi.ifQuotaLeft() ?? aggregator.ifSubscribed() ?? manualQueue
```

| Driver | Custo | Limite | Risco | Quando usar |
|---|---|---|---|---|
| `manual` | zero | nenhum | zero | **Default da fase 1.** Entrega os cortes prontos numa pasta e no painel. |
| `youtube-api` | zero | 6/dia | zero | Seu canal do YouTube. Cobre 3/dia com folga. |
| `aggregator` | mensalidade | do plano | zero | Só depois que o projeto deixar de ser gratuito. |
| `browser` | zero | nenhum | **conta** | Último recurso, ligado à mão, ciente do risco. |

O driver `manual` merece mais atenção do que o nome sugere. Ele não é a versão capada — ele automatiza 90% do trabalho, e o que sobra é abrir o app e apertar publicar, com título, descrição e hashtags já gerados e copiáveis. Faça ele entregar um **pacote por dia**: os cortes do dia mais um arquivo de legenda pronta pra colar.

---

## 7. Modelo de dados

Multi-tenant desde o schema, auth só na fase 4. `tenant_id` em toda tabela desde o primeiro commit, com um tenant fixo no seed. Adicionar auth sobre um schema que já tem tenant é um sábado de trabalho; adicionar tenant sobre um schema que não tem é uma migração que quebra tudo.

```
tenants        id, plan, created_at
users          id, tenant_id, email, role
accounts       id, tenant_id, platform, handle, credentials_ref, driver_pref
templates      id, tenant_id, name, spec_json, version
sources        id, tenant_id, adapter, input, storage_key, duration_ms
jobs           id, tenant_id, source_id, stage, status, error, timings_json
clips          id, tenant_id, job_id, start_word_idx, end_word_idx, score, rubric_json, render_key
publications   id, tenant_id, clip_id, account_id, driver, scheduled_at, status, remote_id
metrics        id, tenant_id, publication_id, views, retention_pct, collected_at
```

`credentials_ref` aponta pra um cofre, nunca guarda o token na linha.

`metrics` parece supérfluo agora e é a tabela mais valiosa do projeto — é ela que, daqui a alguns meses, permite calibrar a rubrica de detecção com retenção real em vez de achismo do LLM. É o único fosso competitivo que existe nesse mercado.

---

## 8. Risco de ToS

**Baixar vídeo do YouTube com `yt-dlp` fere os Termos de Serviço do YouTube**, e o canal ter liberado cortes não muda isso. São duas camadas separadas: o criador dá licença sobre o *conteúdo dele* (resolve direito autoral), o YouTube proíbe o *método de download* (continua de pé). O ecossistema de cortes inteiro opera nessa zona.

Quando virar SaaS, o risco muda de natureza: deixa de ser você usando e passa a ser você **oferecendo o download como serviço**, exposição bem maior. Nessa hora a saída é fazer o usuário conectar o próprio canal por OAuth e baixar só o que é dele, ou aceitar apenas upload direto.

Twitch e Google Drive são mais tranquilos: o Drive tem API oficial para download, e a Twitch é notoriamente permissiva com clipes — o modelo de negócio dela depende disso.

---

## 9. Roadmap

### Fase 0 — Fork rodando, zero código novo · ~1 semana

Forkar o openshorts, `docker compose up`, configurar a cascata de LLM grátis, e passar um vídeo até sair um corte com legenda. Não escrever nenhuma linha própria. O objetivo é ler o código enquanto ele roda e descobrir onde cada estágio mora.

Remover já nesta fase os módulos pagos: fal.ai, ElevenLabs, Upload-Post.

**Pronto quando:** um corte vertical legendado sai na sua máquina, sem nenhuma chave de API paga configurada.

### Fase 1 — Camada de ingestão · 1–2 semanas

Extrair o download chumbado para a interface `SourceAdapter`. Implementar Twitch VOD, Twitch live, Google Drive e upload em streaming. Mover a extração de áudio para antes de tudo.

Começar pela Twitch: live longa é o pior caso, e testar o pior caso cedo evita retrabalho.

**Pronto quando:** os quatro tipos de link entram pelo mesmo endpoint.

### Fase 2 — Motor de template · ~2 semanas

Schema JSON, CRUD no painel, aplicação na segunda passada de render, preview de 3 segundos. Portar os presets de legenda do clippyme em vez de escrever do zero.

**Pronto quando:** trocar de template não reprocessa o vídeo.

### Fase 3 — Camada Publisher · ~2 semanas

Interface, resolvedor, driver `manual` e driver `youtube-api` com contador de quota. `aggregator` e `browser` ficam como stub lançando `NotImplemented` — a arquitetura já os prevê.

**Pronto quando:** os cortes do dia vão pro YouTube sozinhos e o resto cai na fila manual.

### Fase 4 — Agendamento e multi-tenancy real · ~2 semanas

Auth, tenant vindo da sessão, fila isolada por tenant, e o agendador com as regras a definir: quantos por dia, quais horários, espaçamento mínimo.

**Pronto quando:** uma segunda conta usa o sistema sem ver nada da primeira.

### Fase 5 — Calibrar a detecção com dados reais · contínuo

Coletar retenção e views de cada publicação, cruzar com a rubrica que o LLM deu, ajustar os pesos. Aqui é onde o projeto deixa de ser um clone e vira algo que só você tem.

---

## 10. Decisões em aberto

- Quantos cortes por vídeo o sistema deve propor.
- Quantos posts por dia e em quais horários (fase 4).
- Se o pré-filtro heurístico entra já na fase 0 ou só quando o rate limit apertar.
- Se o tracking de rosto usa MediaPipe puro desde o início, evitando a AGPL do YOLOv8.

---

## Referências da auditoria

- Repositórios `openshorts`, `clippyme`, `autoclip` e `opensource-clipping` no GitHub
- Documentação de quota da YouTube Data API v3
- Documentação de auditoria da TikTok Content Posting API
- Comparativos de free tier de LLM, setembro de 2026
