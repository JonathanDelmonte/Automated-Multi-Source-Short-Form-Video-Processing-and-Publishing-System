# Automated Multi-Source Short-Form Video Processing and Publishing System

Sistema self-hosted que recebe vídeo longo de qualquer origem, gera cortes verticais
com template de marca fixo e publica por uma camada de drivers intercambiáveis.

**Status:** pré-código. O planejamento está fechado; a Fase 0 é forkar a base e
colocá-la para rodar.

## Restrições travadas

| Restrição | Decisão |
|---|---|
| Custo | 100% gratuito na fase inicial. Nenhuma API paga, nenhuma mensalidade. |
| Escopo | Uso pessoal agora, com multi-tenancy prevista no schema desde o primeiro commit. |
| Publicação | Camada de drivers intercambiáveis — quatro modos, por plataforma e por conta. |
| Automação | Processo inteiro automatizado. Nenhuma etapa que exija abrir um app de terceiro. |
| Base | Fork de `mutonby/openshorts` (MIT, sem o diretório `cloud/` — ver ADR-001). |

## Pipeline

```
01 Ingest     SourceAdapter resolve a origem e entrega um arquivo canônico
02 Probe      ffprobe + extração de áudio 16k mono
03 Transcribe faster-whisper com timestamp por palavra + diarização
04 Detect     cascata de LLM sobre a transcrição, retorna índices de palavra
05 Reframe    falante ativo → caminho de câmera suavizado
06 Compose    template aplicado: legenda, logo, hook, outro, BGM
07 Publish    driver resolvido por plataforma, conta e modo
```

## Documentação

Comece pelo plano de ação.

| Documento | Papel |
|---|---|
| [`docs/PLANO-DE-ACAO.md`](docs/PLANO-DE-ACAO.md) | **ponto de entrada** — ordem de execução, fases e critérios de pronto |
| [`docs/PLANO-TECNICO.md`](docs/PLANO-TECNICO.md) | documento de origem v2 — arquitetura, o *que* e o *porquê* |
| [`docs/AUDITORIA-VERIFICACAO.md`](docs/AUDITORIA-VERIFICACAO.md) | verificação das premissas do plano, com fontes |
| [`docs/DECISOES.md`](docs/DECISOES.md) | ADR-001 a 008 — decisões travadas |

## Stack

Toda gratuita: `faster-whisper` (transcrição), `pyannote` (diarização), cascata de LLM
free tier com Ollama local como piso, MediaPipe (tracking), `ffmpeg` (composição),
`yt-dlp`/`streamlink` (ingestão), PostgreSQL, Redis, disco local, YouTube Data API.
