# Como executar na sua máquina

As três execuções que a Fase 0 não pôde fechar no ambiente remoto, na ordem do
mais barato para o mais caro — se algo falhar, falha rápido e antes de você
esperar meia hora por um build.

| # | O quê | Tempo | Por que não rodou antes |
|---|---|---|---|
| 1 | Uma chamada real ao Groq | 2 min | não havia chave de API no ambiente |
| 2 | `docker compose up --build` | 15–40 min na 1ª vez | o gateway do container nega o CDN do Docker Hub (403 de política) |
| 3 | Um vídeo de verdade no pipeline | 5–20 min | precisa da stack de ML (torch, ~2 GB) e do `ffmpeg` |

---

## O que você precisa

- **Docker** com Compose v2 (`docker compose`, sem hífen)
- **8 GB de RAM livres** — é o que o `openshorts` pede, e o estágio de
  transcrição é o que come
- **~15 GB de disco** — a imagem com torch e as libs de CUDA é gorda
- **GPU NVIDIA é opcional.** Sem ela tudo roda em CPU, só mais devagar: a
  transcrição de um vídeo de 10 min leva minutos em vez de segundos

Nada aqui custa dinheiro. Nenhuma chave paga foi configurada, e a Fase 0.3
removeu as integrações que pediriam uma.

---

## Passo 1 — A chave do Groq (2 minutos)

Comece por aqui porque é o teste mais barato: se a chave não funcionar, você
descobre em dois minutos em vez de depois do build.

1. Vá a **console.groq.com**, entre com Google ou GitHub
2. **API Keys → Create API Key**, copie o valor (começa com `gsk_`)

Não pede cartão. Teste a chave sem instalar nada:

```bash
curl -s https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer COLE_SUA_CHAVE_AQUI" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile",
       "messages":[{"role":"user","content":"responda apenas: ok"}]}'
```

**Funcionou** se vier um JSON com `"content":"ok"` e um bloco `usage` com
contagem de tokens. Guarde o `usage`: é o mesmo campo que a cascata usa para
debitar do orçamento diário.

**Não funcionou** se vier `invalid_api_key` (chave errada) ou
`model_decommissioned` (o Groq trocou o nome do modelo — nesse caso me diga, é
uma linha em `llm_cascade.py`, ou você resolve na hora com
`GROQ_MODEL=` no `.env`).

> O Gemini é opcional, mas **recomendado junto**. A cascata manda fonte longa
> para ele (contexto de 1M) e três estágios que olham *frames* — escolha de
> layout, detector de conteúdo em tela e vídeo sem fala — só falam Gemini e
> degradam sem chave. Pegue em **aistudio.google.com/apikey**, também grátis.
> Lembre do alerta do §3: o free tier do Google usa o conteúdo enviado para
> treino fora da UE/UK/EEA, e o Brasil está incluído. Para conteúdo próprio
> costuma ser aceitável; com conteúdo de cliente, não é.

---

## Passo 2 — O `.env`

**Este é o mecanismo, e ele não é óbvio:** o `docker-compose.yml` não declara
`environment:` nem `env_file:` para o backend. A configuração chega porque o
repositório inteiro é montado em `/app` e o `load_dotenv()` lê `/app/.env`.
Ou seja: **o arquivo `.env` na raiz do repositório é o painel de controle.**

```bash
cd Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System
git checkout claude/loving-fermat-c84xtd
cp .env.example .env
```

Abra o `.env` e descomente/preencha o mínimo:

```bash
GROQ_API_KEY=gsk_...            # do passo 1
GEMINI_API_KEY=...              # opcional, mas os estágios por frames precisam

# Para o primeiro teste, baixe o piso de duração: o default rejeita
# qualquer fonte com menos de 45 s ANTES de começar, e é a armadilha
# número um de quem testa com um vídeo curto.
MIN_SOURCE_SECONDS=20
```

O resto tem default razoável. As variáveis da cascata de LLM e do banco estão
documentadas no próprio `.env.example`, com os tetos de cada provedor.

---

## Passo 3 — Subir

```bash
docker compose up --build
```

A primeira vez leva de 15 a 40 minutos: a imagem instala torch, torchvision,
ultralytics, mediapipe e faster-whisper. As seguintes sobem em segundos.

Sobem três serviços:

| Serviço | Porta | O quê |
|---|---|---|
| backend | **8000** | FastAPI + fila de jobs |
| frontend | **5175** | o painel |
| renderer | 3100 | serviço de render em Node (Remotion) |

**Pronto quando:**

```bash
curl http://localhost:8000/health           # {"status":"ok"}
curl http://localhost:8000/api/config       # billingEnabled deve ser false
```

E o painel abre em **http://localhost:5175**.

No `/api/config`, confira o campo `localLlm`: com `GROQ_API_KEY` no `.env` ele
deve vir como `cascade / llama-3.3-70b-versatile`. Se vier `null`, a chave não
chegou ao container — quase sempre é `.env` no lugar errado ou o compose
subindo de outro diretório.

**Com GPU NVIDIA**, a imagem precisa das libs de CUDA, que não entram por
padrão:

```bash
docker compose build --build-arg GPU=1 backend && docker compose up
```

E no `.env`: `WHISPER_MODEL=large-v3-turbo`, `WHISPER_DEVICE=cuda`,
`WHISPER_COMPUTE=float16`.

---

## Passo 4 — O primeiro vídeo

**Use um arquivo local, não um link do YouTube.** Duas razões: o §8 do Plano
Técnico registra que baixar do YouTube com `yt-dlp` fere os Termos de Serviço
deles, e um upload elimina a variável de rede do primeiro teste — se falhar,
você sabe que o problema é o pipeline e não o download.

Pegue algo com **2 a 5 minutos de alguém falando** — podcast, aula, uma live
sua. Fala é o que o detector lê; vídeo sem fala cai no caminho por frames, que
exige Gemini.

No painel em `localhost:5175`: escolha o arquivo, confirme que tem direitos
sobre ele, e envie. Acompanhe o log na tela.

O que deve acontecer, na ordem:

```
01 ingest      →  o arquivo é recebido
02 probe       →  resolução e cenas
03 transcribe  →  baixa o modelo whisper na 1ª vez (alguns minutos), transcreve
04 detect      →  a cascata de LLM pontua janelas e detalha as melhores
05/06 render   →  corta, reenquadra em 9:16, queima legenda
```

Os cortes saem em `output/<job-id>/`. Cada um vem com `_metadata.json`, e
título e descrição gerados.

### Se quiser pelo terminal em vez do painel

```bash
docker compose exec backend python main.py -i /app/uploads/seu_video.mp4 -o /app/output/teste
```

---

## Passo 5 — Ler o relatório de custo

É o que fecha o critério de saída da Fase 0, e o que a Fase 1 precisa. No fim
do log do job:

```
📊 Custo deste job:
   01_ingest               0.8s
   03_transcribe         142.3s
   04_detect              18.1s    6 chamada(s)    31200 tokens  [groq]
   05_06_render          201.4s
   TOTAL                 362.6s    6 chamada(s)    31200 tokens
   12.4 min de fala → 2516 tokens/min falado
```

Também em `output/<job-id>/<nome>.timings.json`, e no `/api/status/<job-id>`,
campo `timings`.

**O número que importa é o último.** `tokens/min falado` é o que permite
calcular, por medição e não por estimativa, quanto custaria uma live de 4 h —
e é o insumo para calibrar o pré-filtro heurístico na Fase 1. O ADR-004
estimou ~75.000 tokens para uma live de 4 h; este número diz se a estimativa
estava certa.

---

## Opcional — O banco

Nada do pipeline usa o banco ainda (`sources` e `jobs` passam a ser escritas
na Fase 1), mas vale confirmar que funciona na sua máquina:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python db_seed.py --no-ddl
```

Cria `data/cortes.db` com as nove tabelas, o tenant fixo e o template padrão.

---

## Armadilhas, todas vindas do código

| Sintoma | Causa | Solução |
|---|---|---|
| "fonte muito curta" antes de começar | `MIN_SOURCE_SECONDS=45` | baixe no `.env` (passo 2) |
| Aviso de qualidade baixa | `QUALITY_GATE_MIN_HEIGHT=720` | é só aviso; ou baixe o valor |
| Upload acima de 2 GB recusado | `MAX_FILE_SIZE_MB=2048` | limite do upstream. A Fase 1 sobe para 10 GB |
| `localLlm: null` no `/api/config` | o `.env` não chegou ao container | confirme que está na raiz do repo e que o `compose` subiu dali |
| Transcrição travada minutos na 1ª vez | está baixando o modelo whisper | normal, só na primeira |
| "no usable clips" | fala esparsa, ou nenhum trecho passou do piso de score | vídeo com mais fala contínua |
| `BILLING_ENABLED` dá erro na subida | **é intencional** (ADR-001): o módulo comercial foi removido | não ligue essa flag |
| Build morre sem espaço | a imagem com torch é gorda | `docker system prune -a` e ~15 GB livres |

---

## O que me mandar de volta

Três coisas, e com elas eu ajusto a Fase 1 sobre comportamento real em vez de
suposição:

1. **O bloco `📊 Custo deste job`** inteiro — é o que valida ou corrige a
   estimativa de tokens do ADR-004
2. **O `/api/config`**, para eu confirmar que a cascata foi reconhecida
3. **Qualquer erro**, com as ~30 linhas de log em volta

Se a chamada ao Groq do passo 1 falhar por nome de modelo, me diga o erro: é
uma linha em `llm_cascade.py`.
