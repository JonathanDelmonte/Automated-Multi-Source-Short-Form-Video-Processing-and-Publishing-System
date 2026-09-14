# Mapa dos estágios — onde cada coisa mora no fork

**Fase:** 0.2 · **Data:** 12 de setembro de 2026
**Objetivo (do `PLANO-DE-ACAO.md`):** ler o código enquanto ele roda e descobrir onde
mora cada um dos sete estágios do §4. Este é o entregável real da fase.

Números de linha valem para o commit em que este documento foi escrito; os nomes de
função sobrevivem ao drift.

---

## O desenho que explica todo o resto

O upstream **não é um serviço com um pipeline dentro. É um CLI com uma fila na
frente.**

```
POST /api/process ──► fila asyncio ──► subprocess.Popen ──► main.py (CLI)
  (app.py, 6220 l.)    semáforo         cmd + env vars       (2072 l.)
        ▲                                                        │
        └──────── status do job ◄── parse do stdout ◄────────────┘
```

- `app.py:2385` monta `cmd = [sys.executable, "-u", "main.py"]` e
  `app.py:1873` (`run_job`) o executa com `subprocess.Popen`.
- **Configuração por estágio vai como variável de ambiente**, definida antes do
  `Popen` (`app.py:2401`). É por isso que existe `layout_env`: ligar um layout para
  *um* job é setar a env dele naquele processo.
- **O progresso é o stdout.** Uma thread lê a saída linha a linha
  (`enqueue_output`, `app.py:1817`) e ela *é* o log do job que o painel mostra.

Três consequências que valem para as próximas fases:

1. **A costura da Fase 1 (`SourceAdapter`) é o `argparse` de `main.py`**
   (`main.py:1814`, bloco `__main__`), não um ponto no meio do pipeline. Hoje o
   parser aceita `-u/--url` ou `-i/--input` como grupo mutuamente exclusivo.
2. **A costura da Fase 3 (`Publisher`) é o `app.py`**, camada HTTP — não o
   `main.py`. Os dois estágios das pontas moram em arquivos diferentes do resto.
3. **Estado de job vive em disco, não em banco** (ADR-008): `.resume.json` com
   heartbeat, arquivo `.owner`, `output/.instance`. Isso responde a incerteza que
   a Fase 0.5 tinha em aberto — ver o fim deste documento.

---

## Os sete estágios

### 01 Ingest

| Onde | O quê |
|---|---|
| `main.py:download_youtube_video` (725) | download via `yt-dlp`, com cascata de tentativas |
| `main.py:plan_download_attempts` (688) | ordem das rotas de download |
| `main.py:is_youtube_url` (676) | roteamento por origem |
| `yt_clients.py` | lista explícita de clients do `yt-dlp` (`default,mweb`) + PO token |
| `file_hosts.py` | origens que não são YouTube |
| `app.py:process_endpoint` (2236) | upload direto e entrada do job |
| `quality_probe.py` | probe de qualidade, rodado como subprocesso próprio (`app.py:2026`) |
| **`sources/`** | **a camada de adapter, desde o bloco 1.1** |

**Atualizado no bloco 1.1 (13-set-2026).** Quando este documento foi escrito não havia
camada de adapter: a decisão de origem estava espalhada entre `is_youtube_url`
(roteamento por host), `plan_download_attempts` (rotas de rede) e o `__main__` (URL ou
arquivo), e nenhum dos três era o dono da pergunta *"que tipo de fonte é esta?"*.

Agora é o `sources/`: uma fonte, uma classe, com `matches` / `probe` / `fetch`, e o
pipeline recebe sempre a mesma coisa — um arquivo em disco e um título. A costura é o
`__main__`, como este documento previa; o que sobrou lá é só a escolha do diretório de
saída, que é ergonomia de CLI.

| Adapter | `id` | Casa com |
|---|---|---|
| `sources/youtube.py` | `youtube` | os hosts do YouTube |
| `sources/twitch.py` | `twitch-vod` | `/videos/<id>`, `/<canal>/v/<id>`, `/<canal>/clip/<slug>`, `clips.twitch.tv` |
| `sources/twitch.py` | `twitch-live` | `/<canal>` e `/<canal>/videos` — **recusa explícita** até o bloco 1.5 |
| `sources/direct.py` | `direct` | qualquer outra URL http(s) |
| `sources/local.py` | `upload` | o que não é URL (o upload do painel, o `-i`) |

> **Por que a live é reconhecida só para ser recusada.** Sem o
> `TwitchLiveAdapter`, a URL de um canal cairia no adapter genérico — e o
> `yt-dlp` *aceita* gravar live da Twitch: ficaria baixando até a transmissão
> acabar. Um job que não termina é pior que um job que falha, porque ninguém
> percebe que está errado. Até o bloco 1.5, é um erro imediato que diz o que
> fazer no lugar (esperar o VOD).
>
> A recusa acontece **duas vezes, de propósito**: no `app.py`, ao submeter
> (`assert_fetchable`, antes até do probe de qualidade — numa live ele não
> responde duração nenhuma), e de novo no `main.py`, que é a última porta antes
> do yt-dlp. A primeira é a que o usuário vê: mensagem no formulário, na hora,
> em vez de um job vermelho no histórico dez segundos depois. A segunda existe
> porque o `main.py` também roda pela linha de comando.

Três coisas que o bloco travou, e que valem para os adapters seguintes:

- **Os adapters chamam o código que já existe; não o movem.** `download_youtube_video`
  são ~240 linhas do upstream. Trazê-las para dentro do adapter daria conflito em todo
  `git fetch upstream` — que é justamente o que as interfaces do §4 existem para evitar.
- **O `probe` daqui é o barato**, o que dá para saber sem tocar a rede. O probe caro
  (duração, tamanho) já tem dono — `quality_probe.py` e as regras de quando vale pagar
  por ele em `cloud/metering.probe_url_minutes`. Um teste falha se um `probe` passar a
  importar o `main`.
- **O pacote não importa `main` no topo** (só dentro do `fetch`). Além de evitar o
  ciclo, isso o mantém importável só com a biblioteca padrão — então os testes de
  roteamento rodam no CI, que de propósito não instala torch nem scenedetect.
  Corolário do bloco 1.2: **o que é propriedade da fonte mora no adapter**, não numa
  tabela no `main.py`. O pote de cookies (`cookie_env` / `cookie_file`) e o rótulo
  para o log estão lá pelos dois motivos — é onde vive a resposta, e é onde o CI
  consegue testá-la. O `main.py` só reexporta (`source_label`, `cookie_jar_for`).

> **Herança de proxy pago sem consumidor.** O upstream roteava downloads por proxies
> estáticos e por DataImpulse (por GB), e a contabilidade morava em
> `cloud/proxy_ledger.py` — removido na Fase 0.1. O `main.py` ainda tem a lógica de
> rota e imprime `PROXY_ROUTE=`, mas nada mais persiste isso. Inofensivo (só atua com
> `PROXY_URL` setado, e não vamos setar), porém é peso morto para a Fase 1 avaliar.

### 02 Probe

| Onde | O quê |
|---|---|
| `main.py:get_video_resolution` (629) | resolução, via OpenCV |
| `ffmpeg_utils.py` (298 l.) | `METADATA_SCRUB`, `QUALITY_FAST`, `audio_encode_args` |
| `main.py:detect_scenes` (625) · `scene_detection.py` | PySceneDetect |

**Implementada no bloco 1.3** (`audio_probe.py`). O que este documento registrou na
Fase 0.2 — *"a linha já está escrita, só está no lugar errado da árvore"* — era
literal: a receita existia dentro do backend Parakeet
(`transcribe_backends._extract_wav`), como wav temporário só daquele caminho.
Promovê-la a estágio foi o trabalho.

```
"-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"
```

Agora o `main.py` roda um `ffprobe` e, quando há análise pela frente, extrai
`.audio16k.wav` no diretório do job. Transcrição e detecção leem esse arquivo; o
vídeo só é tocado no 05/06, e mesmo ali só nos trechos escolhidos.

| Decisão | Por quê |
|---|---|
| **Tudo falha aberto** | ffprobe que não roda ou extração que sai vazia devolvem "não consegui" e o pipeline segue entregando o vídeo ao modelo, como antes. Otimização que derruba job não é otimização. |
| **A duração vem do `ffprobe`**, com o OpenCV de reserva | `frame_count/fps` erra em vídeo de taxa variável e, quando o container não declara fps, **divide por zero** — derrubava o job no lugar mais bobo possível. |
| **Não extrai com `--skip-analysis`** | converter o vídeo inteiro não lê transcrição nenhuma; seriam minutos de ffmpeg para nada. |
| **Não extrai sem trilha de áudio** | o pipeline já tem o caminho de análise visual; forçar a extração só trocaria um erro claro por um arquivo vazio. |
| **O WAV é apagado no fim** | numa live de 4h são ~460 MB parados. Quem resume um job interrompido não perde nada: o que evita retranscrever é o `.transcript_checkpoint.json`. |
| **Dotfile** | o diretório do job é servido em `/videos/<job>/`, e isto é estado intermediário — mesma convenção do `.resume.json`. |

O backend Parakeet **reconhece o próprio WAV do pipeline** e não o reextrai;
`_extract_wav` passou a devolver `(caminho, é_nosso_para_apagar)`, porque o
`finally` dele apagaria o arquivo que o resto do job ainda usa.

### 03 Transcribe

| Onde | O quê |
|---|---|
| `main.py:transcribe_video` (1467) | entrada do estágio |
| `transcribe_backends.py` (380 l.) | NVIDIA Parakeet (onnx-asr) → faster-whisper |
| `main.py:save/load_transcript_checkpoint` (1421/1432) | checkpoint, para job reexecutado não pagar transcrição de novo |

**Já é 100% gratuito, e melhor do que o plano assumia.** O §3 escolhe
`faster-whisper`; o upstream tem isso *mais* o Parakeet, com fallback automático para
whisper em erro de modelo e de GPU para CPU em erro de CUDA. Nada de Deepgram ou
ElevenLabs Scribe aqui — aquilo era do `clippyme`, e é o que o ADR-002 manda filtrar
ao portar.

**Não há diarização.** O §4 pede "faster-whisper com timestamp por palavra +
diarização" e o `pyannote` do §3 não está no `requirements.txt`. O que existe é
detecção de falante ativo por vídeo (`active_speaker.py`), que é outra coisa: serve ao
reenquadramento, não à atribuição de fala no transcript. Trabalho novo da Fase 1.

### 04 Detect

| Onde | O quê |
|---|---|
| `main.py:get_viral_clips` (1577) | as duas passadas sobre o transcript |
| `main.py:_run_gemini_stage` (1481) · `_run_stage_split` (1537) | chamada e divisão em janelas |
| `main.py:score_batch_size` (1565) | janelas por chamada — cai para 3 no LLM local |
| `clip_selection.py` (261 l.) | seleção e ranqueamento |
| `llm_backend.py` (165 l.) | **já existe uma saída para LLM não-Gemini** |
| `main.py:get_visual_clips` (1724) | caminho por frames, quando a fala é esparsa |
| `main.py:speech_is_sparse` (1716) | decide entre transcript e frames |
| **`prefilter.py`** | **pré-filtro do ADR-004, desde o bloco 1.4** |

**Atualizado no bloco 1.4.** Entre `build_transcript_windows` e o passe de
pontuação entrou o pré-filtro. Ele **corta por orçamento, nunca por qualidade**:
num vídeo curto devolve a lista inteira e não faz nada; numa live de 4h — 240
janelas, ~82k tokens só na pontuação, contra os 100.000/dia do Groq — escolhe as
que cabem. O orçamento é o menor teto publicado da cadeia inteira, não o do
primeiro provedor, porque pelo ADR-005 a fonte longa começa no Gemini, que não
publica teto. Detalhes e medição em `PLANO-DE-ACAO.md`, seção da Fase 1.

`llm_backend.py` é a melhor notícia para o bloco 0.4: `LLM_BASE_URL` + `LLM_MODEL` +
`LLM_API_KEY` já roteiam as duas passadas de `get_viral_clips` para qualquer endpoint
compatível com OpenAI `/chat/completions`, validando a resposta com os mesmos schemas
pydantic. Groq, Cerebras e Ollama falam esse dialeto. **A cascata do ADR-005 não parte
do zero** — parte de um provedor único configurável, e o que falta é a lista ordenada,
o controle de rate limit e a escolha por duração da fonte.

Os estágios baseados em frames (`layout_picker`, `screencast_layout`,
`get_visual_clips`) continuam presos ao Gemini e degradam sem chave.

### 05 Reframe

| Onde | O quê |
|---|---|
| `reframe_v2.py` (612 l.) | motor v2; `source_already_fits` passa vertical direto |
| `main.py:process_video_to_vertical` (1189) | orquestra o reenquadramento |
| `main.py:SmoothedCameraman` (106) | caminho de câmera suavizado, "heavy tripod" |
| `main.py:SpeakerTracker` (261) | evita troca rápida de falante e oclusão |
| `main.py:detect_face_candidates` (429) | **MediaPipe** |
| `main.py:detect_person_yolo` (460) | **YOLOv8 — o passivo AGPL do ADR-003** |
| `main.py:analyze_scenes_strategy` (557) | classifica a cena e escolhe o modo |
| `layout_picker.py` | uma chamada Gemini por vídeo: `none`/`screencast`/`split` |
| `split_layout.py` · `screencast_layout.py` · `camera_inset.py` · `punch_in.py` | os modos |
| `active_speaker.py` | fala ativa; `normalise_activity` é obrigatório |
| `layout_ranges.py` | sidecar `.layout.json` com os trechos por modo |

Para o ADR-003, as duas funções a isolar atrás da interface `FaceTracker` são
`detect_face_candidates` (MediaPipe, Apache 2.0) e `detect_person_yolo` (Ultralytics,
AGPL-3.0). Estão lado a lado no mesmo arquivo, o que torna o isolamento barato.

### 06 Compose

| Onde | O quê |
|---|---|
| `main.py:render_clip` (1108) | render do corte |
| `main.py:auto_caption_clip` (985) · `subtitles.py` (584 l.) | legenda; ASS permite `{\an5}` por palavra, SRT não |
| `main.py:auto_hook_clip` (1070) · `hooks.py` (456 l.) | hook, com fonte Anton |
| `hook_grounding.py` | reescreve hook e título quando o sentido está na tela |
| `main.py:apply_watermark` (1138) | marca d'água |
| `main.py:finalize_clip_passthrough` (966) | caminho sem reprocessar |
| `editor.py` · `edit_builder.py` | efeitos via filtro `ffmpeg` gerado por Gemini |
| `recut.py` | rerender rápido: corte novo sem reenquadrar |
| `remotion/` · `render-service/` | serviço de render em Node, porta 3100 |

`finalize_clip_passthrough` e `recut.py` são o parente mais próximo, no upstream, do
"aplicar o template no download, não no render" do §5 — e o ADR-002 traz do `clippyme`
a versão amadurecida disso, com passes de `ffmpeg` fundidos.

Não existe template como documento versionado. O §5 é trabalho novo da Fase 2; o que
existe é configuração espalhada em env vars e argumentos.

### 07 Publish

| Onde | O quê |
|---|---|
| `app.py:4655` | `POST https://api.upload-post.com/api/upload` — **chumbado** |
| `app.py:resolve_upload_post` (166) | resolve chave e perfil |
| `s3_uploader.py` (AWS S3) | backup, importado **no topo** do `app.py` (linha 31) |
| `thumbnail.py` | Thumbnail Studio, via Gemini |

Confirma o diagnóstico do §2: "cada um casou com um fornecedor único e chumbou a
chamada no código". É o ponto exato onde a interface `Publisher` do §6 entra, na
Fase 3.

**Detalhe para a Fase 0.3:** `s3_uploader` é importado no **nível de módulo** do
`app.py`, não lazy como os imports de `cloud` eram. Remover o S3 exige editar a linha
31 do `app.py` e os seis nomes que ela traz — não dá para só apagar o arquivo.

---

## O que a Fase 0.5 precisava saber

O ADR-008 deixou uma incerteza explícita: *onde o caminho self-host guarda estado de
job hoje*. Resposta: **em disco, em três lugares**, e nenhum é banco.

| Mecanismo | Onde | Para quê |
|---|---|---|
| `<job>.resume.json` | `output/` | manifesto de retomada, com heartbeat a cada 10 s |
| arquivo `.owner` | dir do job | dono do job, sobrevive a restart |
| `output/.instance` | `output/` | id da instância, coordena handover entre containers |
| `<clip>.layout.json` | dir do job | trechos por modo de layout (`layout_ranges.py`) |
| `.transcript_checkpoint.json` | dir do job | evita retranscrever em reexecução |

Isso **reduz o risco** da Fase 0.5 em relação ao estimado. Não há schema a migrar nem
estado em memória a resgatar: há arquivos com semântica clara e um ponto de leitura
central (`_recover_jobs_from_disk`, `app.py:621`). As tabelas `jobs` e `sources` do §7
nascem espelhando o que esses arquivos já dizem, e os arquivos podem continuar
existindo durante a transição.

Mantenho a estimativa de 3–5 dias, mas a faixa agora é por volume de tabelas, não por
incerteza.

---

## Estado verificado neste ambiente

Ver `PLANO-DE-ACAO.md`, Fase 0.2, para o que foi possível executar e o que não foi.
Resumo: backend, frontend, build e suíte de testes verificados nativamente; o
`docker compose up` está bloqueado por política de rede deste container, não por
defeito do fork.
