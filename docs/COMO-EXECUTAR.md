# Como executar na sua máquina

> **Este guia é para Windows.** Os comandos são do **Prompt de Comando (CMD)**
> e do **PowerShell**, e cada linha é um comando inteiro.
>
> A versão anterior deste arquivo tinha comandos de Linux, com a barra `\` no
> fim da linha. Aquilo é "continuação de linha" do bash: o Linux junta as
> linhas, o CMD do Windows **não** — ele executa cada pedaço como se fosse um
> comando separado, e é por isso que aparecia
> `'-H' não é reconhecido como um comando interno`. Culpa do arquivo, não sua.
>
> Para macOS e Linux, veja o [Apêndice B](#apêndice-b--macos-e-linux).

São quatro coisas, e só a terceira demora:

| # | O quê | Tempo |
|---|---|---|
| 1 | Pegar as chaves de API (grátis) | 5 min |
| 2 | Criar o arquivo `.env` e colar as chaves | 2 min |
| 3 | `docker compose up --build` | 15–40 min **na primeira vez**, segundos depois |
| 4 | Mandar um vídeo pelo navegador | 5–20 min |

Nada aqui custa dinheiro. Nenhuma chave paga foi configurada, e a Fase 0.3
removeu as integrações que pediriam uma.

---

## Antes de começar

- **Docker Desktop** instalado **e aberto**. Ele precisa estar rodando (o ícone
  da baleia perto do relógio, sem "starting"). Se o Docker estiver fechado,
  todo comando `docker` responde
  `error during connect: the docker daemon is not running` — e isso não é
  problema do projeto.
- **8 GB de RAM livres.** É o que o estágio de transcrição pede.
- **~15 GB de disco.** A imagem com torch e as libs de CUDA é gorda.
- **GPU NVIDIA é opcional.** Sem ela tudo roda em CPU, só mais devagar: a
  transcrição de um vídeo de 10 min leva minutos em vez de segundos.

---

## Passo 1 — As chaves

### 1a. Groq — esta destrava o painel

> ### Groq com **Q** não é Grok com **K**
>
> São coisas diferentes, de empresas diferentes, e o nome parecido é azar
> nosso:
>
> | | O que é | Usamos? |
> |---|---|---|
> | **Groq** (com Q) | Empresa de **chips** que roda modelos abertos (Llama) muito rápido. Tem camada grátis de verdade, sem cartão. | **Sim.** É o primeiro provedor da cascata. |
> | **Grok** (com K) | O modelo de IA da xAI, do Elon Musk. É pago. | **Não.** Não aparece em lugar nenhum do projeto. |
>
> O projeto inteiro é de ferramentas gratuitas (é a restrição nº 1 do Plano
> Técnico). Nada do Elon Musk entra aqui.

1. Vá a **console.groq.com** e entre com Google ou GitHub.
2. **API Keys → Create API Key**.
3. Copie o valor. Ele **começa com `gsk_`**.

Não pede cartão.

**Por que esta é a que importa:** com ela no `.env`, o painel para de exigir a
chave do Gemini para aceitar um vídeo (`App.jsx:587`,
`geminiOk = !!apiKey || !!localLlm`). Só com a do Groq você já consegue rodar o
pipeline inteiro de ponta a ponta.

### 1b. Gemini (Google) — opcional, mas você vai querer

> ### A chave do Gemini começa com `AIza`
>
> Se o que você copiou começa com outra coisa — `AQ.`, `ya29.`, `1//` — **não é
> a chave da API.** São tokens de sessão/login do Google, que aparecem quando
> se copia da URL ou de uma tela de autorização em vez do botão certo. Eles não
> funcionam aqui e não dá para converter um no outro.
>
> O caminho certo é: **aistudio.google.com/apikey** → botão
> **"Criar chave de API"** → copiar o valor que aparece, que começa com `AIza` e
> tem ~39 caracteres, sem pontos no meio.

Três estágios do pipeline **só falam Gemini** e degradam sem a chave: a escolha
de layout, o detector de conteúdo em tela e o caminho para vídeo sem fala. A
cascata também manda fonte longa para ele, porque o contexto de 1M token é o
único que aguenta uma live inteira.

> ⚠️ **O alerta do §3 do Plano Técnico continua valendo:** a camada grátis do
> Google usa o conteúdo enviado para treinar os modelos deles fora da
> UE/UK/EEA, e o Brasil está incluído. Para conteúdo seu, costuma ser
> aceitável. Para conteúdo de cliente, não é.

### 1c. Uma regra sobre as chaves

**Chave de API é senha.** Não cole em chat, em issue, em print ou em commit —
inclusive porque robôs varrem esses lugares. Se uma chave já saiu do seu
computador, **revogue e crie outra**: no Groq é `console.groq.com` → API Keys →
o lixo ao lado da chave → Create API Key. No Google é
`aistudio.google.com/apikey` → excluir → criar. Leva 30 segundos e não quebra
nada, porque a chave nova entra no mesmo lugar do `.env`.

---

## Passo 2 — O arquivo `.env`

**Este é o mecanismo, e ele não é óbvio:** o `docker-compose.yml` não declara
`environment:` nem `env_file:` para o backend. A configuração chega porque a
pasta inteira do projeto é montada dentro do container em `/app` (a linha
`- .:/app`) e o `load_dotenv()` lê `/app/.env`.

**Ou seja: o arquivo `.env` na raiz do projeto é o painel de controle.** É lá
que as chaves moram, e é o único lugar.

Abra o **Prompt de Comando** (tecla Windows → digite `cmd` → Enter) e rode uma
linha de cada vez:

```bat
cd C:\caminho\para\Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System
git checkout claude/loving-fermat-c84xtd
copy .env.example .env
notepad .env
```

> **Não crie o `.env` pelo Explorer** (botão direito → Novo → Documento de
> Texto). O Windows esconde a extensão e você fica com `.env.txt`, que o
> programa não lê e você não vê. O `copy` acima cria com o nome certo.
>
> Não sabe o caminho? Abra a pasta do projeto no Explorer, clique na barra de
> endereço, copie, e cole depois do `cd `.

O Notepad abre um arquivo com muito comentário. **Não precisa mexer em nada do
que já está lá.** Vá até o **fim do arquivo**, dê Enter, e cole estas três
linhas:

```
GROQ_API_KEY=gsk_cole_a_sua_aqui
GEMINI_API_KEY=AIza_cole_a_sua_aqui
MIN_SOURCE_SECONDS=20
```

Salve (Ctrl+S) e feche.

Três detalhes que quebram isso na prática:

- **Sem espaço em volta do `=`.** `GROQ_API_KEY=gsk_...`, não
  `GROQ_API_KEY = gsk_...`.
- **Sem aspas** em volta da chave.
- **Sem `#` no começo da linha.** O `#` é comentário: a linha vira decoração.
  É por isso que colar no fim do arquivo é mais seguro do que caçar a linha
  comentada lá no meio.

**Por que `MIN_SOURCE_SECONDS=20`:** o padrão é 45, e o código rejeita qualquer
fonte mais curta que isso **antes de começar** (`app.py:61`). É a armadilha
número um de quem testa com um vídeo curto. Depois do primeiro teste você pode
apagar essa linha.

Se você só tem a chave do Groq, ponha só ela. A linha do Gemini pode ficar de
fora até você pegar a chave certa.

---

## Passo 3 — Subir

No mesmo Prompt de Comando, na mesma pasta:

```bat
docker compose up --build
```

(`docker compose`, com espaço e sem hífen. O `docker-compose` com hífen é a v1,
antiga.)

A primeira vez leva de 15 a 40 minutos: a imagem instala torch, torchvision,
ultralytics, mediapipe e faster-whisper. **As seguintes sobem em segundos.**
Deixe a janela aberta — é ela que mostra o log. Para parar tudo depois:
Ctrl+C na janela.

Sobem três serviços:

| Serviço | Porta | O quê |
|---|---|---|
| backend | **8000** | FastAPI + fila de jobs |
| frontend | **5175** | o painel |
| renderer | 3100 | serviço de render em Node (Remotion) |

**Com GPU NVIDIA**, as libs de CUDA não entram por padrão:

```bat
docker compose build --build-arg GPU=1 backend
docker compose up
```

E no `.env`: `WHISPER_MODEL=large-v3-turbo`, `WHISPER_DEVICE=cuda`,
`WHISPER_COMPUTE=float16`.

---

## Passo 4 — Conferir que as chaves chegaram (pelo navegador)

**Sem comando nenhum.** Abra estes dois endereços no Chrome ou no Edge:

| Endereço | O que deve aparecer |
|---|---|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:8000/api/config | um JSON com `"billingEnabled":false` |

No `/api/config`, procure o campo **`localLlm`**. Com a chave do Groq no `.env`,
ele vem parecido com isto:

```json
"localLlm": { "provider": "cascade", "model": "llama-3.3-70b-versatile", ... }
```

**Se vier `"localLlm": null`, a chave não chegou ao container.** Quase sempre é
uma destas três:

1. o arquivo virou `.env.txt` (veja o passo 2);
2. tem `#` no começo da linha, ou espaço em volta do `=`;
3. o `docker compose` subiu de outra pasta.

Depois de corrigir o `.env`, é preciso **reiniciar** para ele ser lido de novo:
Ctrl+C na janela e `docker compose up` outra vez (essa segunda vez é rápida,
não reconstrói).

E o painel abre em **http://localhost:5175**.

---

## Passo 5 — O primeiro vídeo

**Use um arquivo do seu computador, não um link do YouTube.** Duas razões: o §8
do Plano Técnico registra que baixar do YouTube com `yt-dlp` fere os Termos de
Serviço deles, e um upload tira a rede da equação no primeiro teste — se falhar,
você sabe que o problema é o pipeline, não o download.

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

Os cortes saem na pasta `output\<job-id>\` do projeto. Cada um vem com
`_metadata.json`, título e descrição gerados.

---

## Passo 6 — Ler o relatório de custo

É o que fecha o critério de saída da Fase 0, e o que a Fase 1 precisa. No fim
do log do job, na janela do Prompt de Comando:

```
📊 Custo deste job:
   01_ingest               0.8s
   03_transcribe         142.3s
   04_detect              18.1s    6 chamada(s)    31200 tokens  [groq]
   05_06_render          201.4s
   TOTAL                 362.6s    6 chamada(s)    31200 tokens
   12.4 min de fala → 2516 tokens/min falado
```

Também em `output\<job-id>\<nome>.timings.json`, e no `/api/status/<job-id>`,
campo `timings`.

**O número que importa é o último.** `tokens/min falado` é o que permite
calcular, por medição e não por estimativa, quanto custaria uma live de 4 h — e
é o insumo para calibrar o pré-filtro heurístico na Fase 1. O ADR-004 estimou
~75.000 tokens para uma live de 4 h; este número diz se a estimativa estava
certa.

---

## Opcional — O banco

Nada do pipeline usa o banco ainda (`sources` e `jobs` passam a ser escritas na
Fase 1), mas vale confirmar que funciona na sua máquina. Com o stack no ar,
abra **outro** Prompt de Comando na mesma pasta:

```bat
docker compose exec backend alembic upgrade head
docker compose exec backend python db_seed.py --no-ddl
```

Cria `data\cortes.db` com as nove tabelas, o tenant fixo e o template padrão.

---

## Armadilhas, todas vindas do código (ou do Windows)

| Sintoma | Causa | Solução |
|---|---|---|
| `'-H' não é reconhecido como um comando interno` | comando de Linux quebrado em várias linhas com `\` | não existe mais neste guia; cada linha aqui é um comando inteiro |
| `the docker daemon is not running` | Docker Desktop fechado | abra o Docker Desktop e espere o ícone parar de dizer "starting" |
| `.env` não tem efeito, `localLlm: null` | o arquivo virou `.env.txt`, ou tem `#`/espaços na linha | passo 2; depois reinicie o `docker compose` |
| Notepad não acha o `.env` | o Explorer esconde arquivos que começam com ponto | abra pelo comando `notepad .env` dentro da pasta |
| `curl` se comporta estranho no PowerShell | lá `curl` é apelido do `Invoke-WebRequest`, que não aceita as opções do curl de verdade | use `curl.exe`, ou o `Invoke-RestMethod` do Apêndice A |
| "fonte muito curta" antes de começar | `MIN_SOURCE_SECONDS=45` | `MIN_SOURCE_SECONDS=20` no `.env` (passo 2) |
| Aviso de qualidade baixa | `QUALITY_GATE_MIN_HEIGHT=720` | é só aviso; ou baixe o valor |
| Upload acima de 2 GB recusado | `MAX_FILE_SIZE_MB=2048` | limite do upstream. A Fase 1 sobe para 10 GB |
| Transcrição travada minutos na 1ª vez | está baixando o modelo whisper | normal, só na primeira |
| "no usable clips" | fala esparsa, ou nenhum trecho passou do piso de score | vídeo com mais fala contínua |
| `invalid_api_key` no log | chave errada ou revogada | crie outra no console do provedor |
| `model_decommissioned` no log | o Groq trocou o nome do modelo | `GROQ_MODEL=<nome novo>` no `.env` resolve na hora; me avise que eu corrijo no `llm_cascade.py` |
| `BILLING_ENABLED` dá erro na subida | **é intencional** (ADR-001): o módulo comercial foi removido | não ligue essa flag |
| Build morre sem espaço | a imagem com torch é gorda | `docker system prune -a` e ~15 GB livres |

---

## Apêndice A — Testar a chave do Groq sem subir nada

Só se você quiser conferir a chave **antes** de esperar o build. O passo 4 testa
a mesma coisa pelo navegador, então isto é atalho, não obrigação.

Abra o **PowerShell** (tecla Windows → digite `powershell` → Enter) e rode as
duas linhas abaixo, uma de cada vez. **Cada linha é um comando inteiro** — não
tem `\` no fim:

```powershell
$k = "gsk_COLE_A_SUA_CHAVE_AQUI"
Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/chat/completions" -Method Post -Headers @{ Authorization = "Bearer $k" } -ContentType "application/json" -Body '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"responda apenas: ok"}]}' | ConvertTo-Json -Depth 6
```

**Funcionou** se vier um JSON com `"content": "ok"` e um bloco `usage` com
contagem de tokens. Esse `usage` é o mesmo campo que a cascata usa para debitar
do orçamento diário (`output/.llm_budget.json`).

**Não funcionou** se vier `invalid_api_key` (chave errada) ou
`model_decommissioned` (o Groq trocou o nome do modelo — veja a tabela de
armadilhas).

---

## Apêndice B — macOS e Linux

Os mesmos passos; muda só a forma dos comandos.

```bash
cd ~/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System
git checkout claude/loving-fermat-c84xtd
cp .env.example .env
nano .env          # ou o editor que preferir
docker compose up --build
```

E a conferência do passo 4 pode ser por terminal:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/config
```

O teste do Apêndice A, em uma linha:

```bash
curl -s https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $GROQ_API_KEY" -H "Content-Type: application/json" -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"responda apenas: ok"}]}'
```

E rodar um vídeo pelo terminal em vez do painel:

```bash
docker compose exec backend python main.py -i /app/uploads/seu_video.mp4 -o /app/output/teste
```

---

## O que me mandar de volta

Três coisas, e com elas eu ajusto a Fase 1 sobre comportamento real em vez de
suposição:

1. **O bloco `📊 Custo deste job`** inteiro — é o que valida ou corrige a
   estimativa de tokens do ADR-004.
2. **O que aparece em `/api/config`**, para eu confirmar que a cascata foi
   reconhecida. **Menos o valor das chaves** — elas não aparecem nesse JSON, e
   não devem aparecer no que você colar.
3. **Qualquer erro**, com as ~30 linhas de log em volta.
