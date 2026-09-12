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
| 0 | Baixar o projeto para o seu computador | 3 min |
| 1 | Pegar as chaves de API (grátis) | 5 min |
| 2 | Criar o arquivo `.env` e colar as chaves | 2 min |
| 3 | `docker compose up --build` | 15–40 min **na primeira vez**, segundos depois |
| 4 | Mandar um vídeo pelo navegador | 5–20 min |

Nada aqui custa dinheiro. Nenhuma chave paga foi configurada, e a Fase 0.3
removeu as integrações que pediriam uma.

---

## Antes de começar

- **Docker Desktop** instalado **e aberto** — veja o quadro abaixo se ainda não
  tem. Ele precisa estar rodando (o ícone da baleia perto do relógio, sem
  "starting"). Com o Docker fechado, todo comando `docker` responde
  `error during connect: the docker daemon is not running`; com ele **não
  instalado**, a resposta é outra: `'docker' não é reconhecido como um comando
  interno`. Nenhuma das duas é problema do projeto.
- **8 GB de RAM livres.** É o que o estágio de transcrição pede.
- **~15 GB de disco.** A imagem com torch e as libs de CUDA é gorda.
- **GPU NVIDIA é opcional.** Sem ela tudo roda em CPU, só mais devagar: a
  transcrição de um vídeo de 10 min leva minutos em vez de segundos.

### Instalando o Docker Desktop

**O Docker não é "só para o backend": é o que roda tudo.** Os três serviços
(backend Python, painel React, renderer em Node) sobem por ele. A alternativa
seria instalar na mão Python 3.11, Node, `ffmpeg` e a stack de ML inteira —
torch, torchvision, ultralytics, mediapipe, faster-whisper, uns 2 GB de
bibliotecas — e acertar as versões de todas. O Docker é o atalho, não um
requisito a mais.

1. Baixe em **docker.com/products/docker-desktop** (Windows, AMD64).
2. Rode o instalador. Ele abre uma tela **Configuration** com três escolhas:

   | Opção | O que marcar | Por quê |
   |---|---|---|
   | Per-user / All-users | **Per-user (Recommended)** | não pede senha de administrador, e já usa o WSL 2 sozinho. All-users também funciona — serve para quem precisa de Windows Containers ou do backend Hyper-V, e este projeto não precisa de nenhum dos dois |
   | Use WSL 2 instead of Hyper-V | **marcado** | é o backend que roda os containers Linux do projeto |
   | Allow Windows Containers | **desmarcado** | o projeto roda containers **Linux**. O próprio instalador avisa do risco, e ligar isso não traz nada aqui |

   **Ao marcar Per-user, as duas caixas ficam cinzas — e isso está certo.**
   Cinza ali não é "desligado", é "não há o que decidir": o Per-user só sabe
   usar o WSL 2 (a caixa fica cinza **e marcada**) e não suporta Windows
   Containers (cinza e desmarcada). A escolha entre WSL 2 e Hyper-V só existe
   no All-users, que é por isso que as caixas aparecem embaixo dele. O texto
   do próprio instalador diz: *"Per-user installation… Uses the WSL 2
   backend. Windows Containers and the Hyper-V backend require an all-users
   installation."*

3. **Reinicie o computador** quando ele pedir. Não pule: o WSL 2 não fica
   ativo antes disso.
4. Abra o Docker Desktop e espere o ícone da baleia parar de dizer "starting".
5. **Feche e reabra o Prompt de Comando** — sem isso ele não enxerga o
   `docker`, porque o `PATH` só é lido na abertura da janela.
6. Confira: `docker --version` deve responder algo como `Docker version 2x.x`.

O que a sua máquina precisa ter:

| Requisito | Detalhe |
|---|---|
| Windows 10 **22H2 (build 19045)** ou maior | **Home serve.** No WSL 2 o Home é suportado — em Home é, aliás, o único backend possível |
| Virtualização ligada na BIOS/UEFI | Confira no Gerenciador de Tarefas → Desempenho → CPU: "Virtualização: Ativado". Se estiver desativada, é uma opção da BIOS (`Intel VT-x` ou `AMD-V`) |
| Processador 64-bit com SLAT | Qualquer CPU dos últimos ~12 anos tem |

Para descobrir a sua versão do Windows: tecla Windows → digite `winver` →
Enter.

---

## Passo 0 — Baixar o projeto

**O guia presumia que o projeto já estava na sua máquina, e não dizia como
colocá-lo lá.** Sem a pasta do projeto, o `.env` do passo 2 não tem onde morar.

### Se você já tem o projeto

Pelo **GitHub Desktop** ou por um clone anterior, então **não clone de novo** —
um segundo clone vira uma segunda cópia, e você acaba editando o `.env` de uma
enquanto o Docker sobe a outra.

O que você precisa é só do caminho dela. No GitHub Desktop:
**Repository → Show in Explorer**, e o caminho está na barra de endereço. O
padrão do GitHub Desktop é
`C:\Users\<seu usuário>\Documents\GitHub\<nome do repositório>`.

Guarde esse caminho: é ele que vai depois de todo `cd /d` deste guia, no lugar
de `C:\cortes`. Confirme que está atualizado (**Fetch origin**, e depois
**Pull origin** se aparecer — o Fetch sozinho baixa mas não aplica) e siga
para o passo 1.

### Se você ainda não tem

Primeiro confira se você tem o **git**. Abra o **Prompt de Comando** (tecla
Windows → digite `cmd` → Enter — **não precisa ser como Administrador**) e rode:

```bat
git --version
```

Se responder algo como `git version 2.x`, siga. Se responder
`'git' não é reconhecido`, instale de **git-scm.com/download/win** (next, next,
finish serve), feche o Prompt de Comando, abra de novo e repita.

Agora baixe o projeto. **Estas quatro linhas são pra copiar e colar como estão**
— aqui não tem nada para substituir:

```bat
cd /d C:\
git clone https://github.com/JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System.git cortes
cd /d C:\cortes
dir .env.example
```

O `cortes` no fim do `git clone` é de propósito: sem ele a pasta ficaria com o
nome inteiro do repositório, e você teria de digitá-lo em todo comando daqui
para frente. Assim o projeto mora em **`C:\cortes`**, e é esse o caminho de
todos os passos seguintes.

O `dir .env.example` é a conferência: se listar o arquivo, você está na pasta
certa. Se disser `Arquivo não encontrado`, o clone não terminou ou você está em
outra pasta — rode `cd /d C:\cortes` de novo.

Não é preciso trocar de branch: `claude/loving-fermat-c84xtd` é a branch padrão
do repositório, então o `clone` já traz ela.

**Para atualizar depois**, quando eu subir mudanças novas:

```bat
cd /d C:\cortes
git pull
```

O `git pull` não mexe no seu `.env` — ele não está versionado, justamente para
as suas chaves nunca irem parar no GitHub.

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

> ### A chave começa com `AQ.` ou com `AIza` — as duas são válidas
>
> O Google está trocando o formato das chaves do Gemini: as antigas começam com
> `AIza`, e as novas, emitidas pelo AI Studio desde meados de 2026, começam com
> **`AQ.`**. Não há botão para escolher: a conta emite uma ou outra, e a que o
> AI Studio te der é a certa.
>
> O caminho é **aistudio.google.com/apikey** → **"Criar chave de API"** →
> **"Copiar chave"**. O valor que aparece no campo "Chave de API" é a chave,
> comece ele como começar.
>
> **Uma ressalva que importa para este projeto, e ela é boa notícia:** as chaves
> `AQ.` funcionam no endpoint nativo do Gemini
> (`generativelanguage.googleapis.com`) e dão 401 nas rotas
> "compatíveis com OpenAI". Este projeto fala com o Gemini pelo SDK oficial
> (`from google import genai`, `main.py:21`), que é o caminho nativo — a
> ramificação está em `main.py:1499`, onde só provedor **com** `base_url` vai
> ao caminho compatível com OpenAI, e o Gemini é justamente o que tem
> `base_url=None` (`llm_cascade.py:101`). Groq e Cerebras é que usam a rota
> compatível, e as chaves deles não têm esse problema.
>
> Onde isso morde: se alguém apontar `LLM_BASE_URL` para o endpoint
> compatível-com-OpenAI do Google usando uma chave `AQ.`, o 401 é esperado e
> não é bug deste repositório. Use o caminho nativo.

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

No **Prompt de Comando**, rode uma linha de cada vez (com o projeto em
`C:\cortes`, como no passo 0):

```bat
cd /d C:\cortes
copy .env.example .env
notepad .env
```

> ### Duas formas de criar o `.env` no lugar errado
>
> **Pelo Explorer** (botão direito → Novo → Documento de Texto): o Windows
> esconde a extensão e você fica com `.env.txt`, que o programa não lê e você
> não vê no nome.
>
> **Rodando `notepad .env` fora da pasta do projeto.** Esta é a pior das duas,
> porque nada dá erro: o Notepad simplesmente abre um arquivo novo e vazio, e
> ao salvar cria o `.env` na pasta em que o Prompt de Comando estava — muitas
> vezes `C:\Windows\system32`, que é a pasta de sistema do Windows. O arquivo
> fica perfeito e no lugar errado, e o container nunca vai lê-lo.
>
> As duas se evitam com a mesma disciplina: **`cd /d C:\cortes` primeiro**, e
> `copy .env.example .env` antes do `notepad` — assim o Notepad abre um arquivo
> que já existe, com o conteúdo do exemplo dentro. Se ele abrir **vazio**, você
> está na pasta errada: feche sem salvar e volte ao `cd`.

O Notepad abre um arquivo com muito comentário. **Não precisa mexer em nada do
que já está lá.** Vá até o **fim do arquivo**, dê Enter, e cole estas três
linhas:

```
GROQ_API_KEY=cole_a_sua_do_groq_aqui
GEMINI_API_KEY=cole_a_sua_do_gemini_aqui
MIN_SOURCE_SECONDS=20
```

Salve (Ctrl+S) e feche.

**Só uma coisa quebra de verdade: o `#` no começo da linha.** O `#` é
comentário, e a linha vira decoração — é por isso que colar no fim do arquivo
é mais seguro do que caçar a linha comentada lá no meio.

O resto o parser tolera. Medido com o `python-dotenv==1.2.2` que o
`requirements.txt` fixa, que é o mesmo que o `load_dotenv()` do `app.py` usa:

| O que você escreveu | Vale? |
|---|---|
| `GROQ_API_KEY=gsk_123` | sim |
| `GROQ_API_KEY= gsk_123` (espaço depois do `=`) | **sim** |
| `GROQ_API_KEY = gsk_123` (espaço dos dois lados) | **sim** |
| `GROQ_API_KEY=gsk_123   ` (espaço no fim) | sim, é aparado |
| `GROQ_API_KEY="gsk_123"` (com aspas) | sim, as aspas saem |
| `#GROQ_API_KEY=gsk_123` | **não** — é a única que falha |

Colar sem espaço continua sendo o hábito melhor, porque nem todo programa que
lê `.env` é tão tolerante quanto este. Mas se você já colou com espaço, **não
precisa voltar para arrumar**: aqui funciona.

**Por que `MIN_SOURCE_SECONDS=20`:** o padrão é 45, e o código rejeita qualquer
fonte mais curta que isso **antes de começar** (`app.py:61`). É a armadilha
número um de quem testa com um vídeo curto. Depois do primeiro teste você pode
apagar essa linha.

Se você só tem a chave do Groq, ponha só ela. A linha do Gemini pode ficar de
fora até você pegar a chave certa.

---

## Passo 3 — Subir

No mesmo Prompt de Comando. O `cd` está repetido de propósito: `docker compose`
procura o `docker-compose.yml` na pasta em que você está, e de outra pasta ele
não acha nada.

```bat
cd /d C:\cortes
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
abra **outro** Prompt de Comando (o primeiro está ocupado mostrando o log):

```bat
cd /d C:\cortes
docker compose exec backend alembic upgrade head
docker compose exec backend python db_seed.py --no-ddl
```

Cria `data\cortes.db` com as nove tabelas, o tenant fixo e o template padrão.

---

## Armadilhas, todas vindas do código (ou do Windows)

| Sintoma | Causa | Solução |
|---|---|---|
| `'-H' não é reconhecido como um comando interno` | comando de Linux quebrado em várias linhas com `\` | não existe mais neste guia; cada linha aqui é um comando inteiro |
| `O sistema não pode encontrar o caminho especificado` num `cd` | o caminho era um exemplo, ou o projeto não foi baixado | passo 0: o projeto vai para `C:\cortes` e é esse o caminho literal |
| `notepad .env` abre um arquivo **vazio** | você não está na pasta do projeto; o Notepad vai criar um `.env` onde o CMD estiver (`C:\Windows\system32`, por exemplo) | feche **sem salvar**, `cd /d C:\cortes`, `copy .env.example .env`, e só então `notepad .env` |
| `'git' não é reconhecido` | git não instalado | git-scm.com/download/win, depois feche e reabra o Prompt de Comando |
| `'docker' não é reconhecido` | Docker Desktop não instalado (≠ fechado) | instale (quadro em "Antes de começar") e **reabra o Prompt** — o `PATH` só é lido na abertura |
| Docker Desktop não inicia, fala em virtualização | virtualização desligada na BIOS | Gerenciador de Tarefas → Desempenho → CPU mostra o estado; ligar é opção da BIOS |
| `the docker daemon is not running` | Docker Desktop fechado | abra o Docker Desktop e espere o ícone parar de dizer "starting" |
| `.env` não tem efeito, `localLlm: null` | o arquivo virou `.env.txt`, ou tem `#`/espaços na linha | passo 2; depois reinicie o `docker compose` |
| Notepad não acha o `.env` | o Explorer esconde arquivos que começam com ponto | abra pelo comando `notepad .env` dentro da pasta |
| `curl` se comporta estranho no PowerShell | lá `curl` é apelido do `Invoke-WebRequest`, que não aceita as opções do curl de verdade | use `curl.exe`, ou o `Invoke-RestMethod` do Apêndice A |
| "fonte muito curta" antes de começar | `MIN_SOURCE_SECONDS=45` | `MIN_SOURCE_SECONDS=20` no `.env` (passo 2) |
| Aviso de qualidade baixa | `QUALITY_GATE_MIN_HEIGHT=720` | é só aviso; ou baixe o valor |
| Upload acima de 2 GB recusado | `MAX_FILE_SIZE_MB=2048` | limite do upstream. A Fase 1 sobe para 10 GB |
| Transcrição travada minutos na 1ª vez | está baixando o modelo whisper | normal, só na primeira |
| "no usable clips" | fala esparsa, ou nenhum trecho passou do piso de score | vídeo com mais fala contínua |
| `invalid_api_key` no log | chave do Groq errada ou revogada | crie outra em console.groq.com |
| `401` ou `API_KEY_INVALID` no Gemini | chave errada, **ou** uma chave `AQ.` mandada para uma rota compatível-com-OpenAI | o projeto usa o SDK nativo e não tem esse problema; se você apontou `LLM_BASE_URL` para o Google, tire |
| Um segundo clone do projeto | clonei de novo tendo o GitHub Desktop | use uma pasta só: o `.env` fica na que o `docker compose` sobe |
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

### E a do Gemini

Esta é um GET simples, sem corpo — ela só pergunta ao Google quais modelos a
chave enxerga, que é o teste mais barato de "a chave é válida":

```powershell
$g = "COLE_A_SUA_CHAVE_AQUI"
Invoke-RestMethod -Uri "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent" -Method Post -Headers @{ "x-goog-api-key" = $g } -ContentType "application/json" -Body '{"contents":[{"parts":[{"text":"responda apenas: ok"}]}]}' | ConvertTo-Json -Depth 8
```

**Funcionou** se vier um JSON com `"text": "ok"`.

Este teste chama `generateContent` de propósito, e não a listagem de modelos.
Listar modelos é mais curto, mas passa em casos em que gerar falha — e gerar é
o que o pipeline faz. Testar o que se vai usar custa a mesma linha.

O `x-goog-api-key` no cabeçalho é o mesmo mecanismo que o SDK oficial usa por
dentro, então este teste percorre o caminho real do projeto.

---

## Apêndice B — macOS e Linux

Os mesmos passos; muda só a forma dos comandos.

```bash
git clone https://github.com/JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System.git cortes
cd cortes
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
