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
| 3 | `docker compose up -d --build` | 15–40 min **na primeira vez**, segundos depois |
| 4 | Mandar um vídeo pelo navegador | 5–20 min |

Nada aqui custa dinheiro. Nenhuma chave paga foi configurada, e a Fase 0.3
removeu as integrações que pediriam uma.

---

## O jeito sem Docker: o ajudante

Para usar o Virtu Clips em outro computador — ou no seu, sem Docker —, nada deste guia
é preciso: abra **https://virtu-clips.zirtuno.workers.dev**, clique em **Baixar o
Virtu Clips para Windows** e abra o arquivo. Ele instala o motor em
`%LOCALAPPDATA%\VirtuClips` sem pedir administrador, usa a placa de vídeo se houver,
fica como ícone perto do relógio, liga com o Windows e se atualiza sozinho. Os
projetos ficam em `%LOCALAPPDATA%\VirtuClips\dados`, e desinstalar não os apaga. As
decisões estão no ADR-012.

O resto deste guia é o caminho do Docker, que continua valendo no seu computador. Os
dois convivem: o Docker usa a porta 8000 e o ajudante a 8001, e quando o Docker está
de pé o ajudante para o motor dele e deixa o site falar com o Docker.

### Roteiro: testar o ajudante no seu PC (uma vez, antes de mandar para alguém)

O Windows do GitHub prova a instalação — inclusive como um usuário **sem**
administrador, que é o caso do erro 448 de 24-set-2026 —, um vídeo inteiro no
processador, a atualização sozinha e a desinstalação. Não prova a placa, o YouTube, o
ícone nem o aviso do Windows: isso só numa máquina de verdade.

1. **Feche o Docker Desktop** (ícone da baleia perto do relógio → *Quit Docker
   Desktop*). Não é obrigatório, mas assim o teste é do ajudante e não do Docker.
2. Abra o site. Em poucos segundos aparece a logo, "procurando o Virtu Clips neste
   computador" e o botão **Baixar o Virtu Clips para Windows**. Clique.
3. Abra o `Instalar-Virtu-Clips.exe` baixado. **Confira:** o Windows mostra "O Windows
   protegeu o computador"? *Mais informações* → *Executar assim mesmo* resolve? O
   instalador é escuro, com a logo.
4. A instalação abre uma janela azul do PowerShell baixando o motor. Com a RTX 3060
   ela baixa também as bibliotecas de CUDA do whisper (~1 GB a mais), então pode
   levar uns 10 minutos. A janela fecha sozinha. A pasta `%LOCALAPPDATA%\Cortes`
   da tentativa que deu o erro 448 é limpa sozinha nesse passo.
5. No fim, o site abre sozinho. **Confira:** o ícone "V" perto do relógio (talvez na
   setinha ^); passando o mouse, **"Virtu Clips: pronto (placa de vídeo)"**. Se
   disser "(processador)", me mande o arquivo abaixo.

   ```
   %LOCALAPPDATA%\VirtuClips\dados\logs\instalacao.log
   ```

6. **A chave de IA: o site pede, e você cola.** Na primeira vez aparece "Required API
   keys missing" → *go to settings* → cole a chave do Gemini (a mesma da linha
   `GEMINI_API_KEY=` do seu `.env`; quem não tem, cria de graça em
   aistudio.google.com). Ela fica guardada no navegador. Ninguém precisa copiar
   arquivo nenhum — e os campos para as outras chaves gratuitas (Groq e as demais
   da cascata) são o próximo passo.
7. Cole um link do YouTube e processe. **Confira:** o download funciona (sem cookies),
   e no log do job a linha do whisper diz `cuda`. O tempo total deve ficar perto do
   que o Docker faz com o mesmo vídeo.
8. **A convivência:** abra o Docker Desktop e rode `atalhos\atualizar.bat`.
   **Confira:** os containers sobem (agora com o nome `virtu-clips-*`), e em até um
   minuto o ícone do ajudante passa a dizer "outro motor do Virtu Clips (o Docker) já
   está atendendo". Recarregue o site (F5): ele passa a falar com o Docker.

Para tirar o ajudante: Configurações do Windows → Aplicativos → **Virtu Clips** →
Desinstalar. Os projetos continuam em `%LOCALAPPDATA%\VirtuClips\dados`.

**O que me mandar de volta:** o que aconteceu em cada "Confira", e, se algo falhar,
os arquivos da pasta `%LOCALAPPDATA%\VirtuClips\dados\logs`.

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

3. **Reinicie o computador** se ele pedir — mas confira antes se precisa
   mesmo (passo 6). O reboot só é necessário quando o instalador teve de
   **ligar recursos do Windows** que estavam desligados (Virtual Machine
   Platform e WSL): recurso recém-ativado só vale depois do boot. Se já
   estavam ligados, não há o que esperar.
4. Abra o Docker Desktop e espere o ícone da baleia parar de dizer "starting".
5. **Feche e reabra o Prompt de Comando** — sem isso ele não enxerga o
   `docker`, porque o `PATH` só é lido na abertura da janela.
6. Confira com **`docker ps`**, não com `docker --version`.

   `docker --version` só imprime a versão do cliente e **não fala com o
   motor** — ele responde certinho com o engine parado, então não detecta
   justamente a falha que o reboot conserta. Já o `docker ps` precisa
   conversar com o engine dentro do WSL 2.

   - Respondeu uma lista vazia (só o cabeçalho `CONTAINER ID  IMAGE …`):
     está tudo no ar, **sem precisar reiniciar**.
   - `cannot connect to the Docker daemon`, ou reclamação de WSL: abra o
     Docker Desktop e espere a baleia. Se persistir, **aí** reinicie.

O que a sua máquina precisa ter:

| Requisito | Detalhe |
|---|---|
| Windows 10 **22H2 (build 19045)** ou maior | **Home serve.** No WSL 2 o Home é suportado — em Home é, aliás, o único backend possível |
| **WSL na versão empacotada** (2.1.5+), não o componente embutido | é o requisito que mais trava, e o embutido não se anuncia como velho — veja o quadro logo abaixo |
| Virtualização ligada na BIOS/UEFI | Confira no Gerenciador de Tarefas → Desempenho → CPU: "Virtualização: Ativado". Se estiver desativada, é uma opção da BIOS (`Intel VT-x` ou `AMD-V`) |
| Processador 64-bit com SLAT | Qualquer CPU dos últimos ~12 anos tem |

Para descobrir a sua versão do Windows: tecla Windows → digite `winver` →
Enter.

#### "There was a problem with WSL" — o WSL embutido não serve

Se o Docker Desktop abrir um diálogo **There was a problem with WSL** citando
`wsl.exe --version: exit status 1` e, no lugar de uma versão, a **tela de
ajuda** do `wsl.exe` (`Uso: wsl.exe [Argument]`), o diagnóstico é exato: essa
é a assinatura do **WSL antigo, o que vem embutido no Windows**. O `--version`
só existe no WSL novo, empacotado à parte; o antigo, ao receber um argumento
que não conhece, imprime o manual e sai com erro — e é isso que o Docker lê
como falha.

Não é o reboot que está faltando: é o WSL moderno que não está instalado. Em
**PowerShell como Administrador**:

```powershell
wsl --install
```

Liga os recursos do Windows que faltam (Virtual Machine Platform e WSL), baixa
o WSL empacotado e instala um Ubuntu junto — que o Docker não usa e não
atrapalha.

**Reinicie depois deste comando.** Aqui o reboot é obrigatório, pela razão do
passo 3: ele ligou recursos do Windows, e recurso recém-ativado só vale depois
do boot.

Confirme com `wsl --version`: tem de imprimir números de versão. Se ainda vier
a tela de ajuda, instale **"Windows Subsystem for Linux"** pela Microsoft
Store, ou o MSI de `github.com/microsoft/WSL/releases`.

Numa build mais antiga que 22H2 — o 19044 (21H2), por exemplo — o WSL
empacotado não instala, e aí é preciso atualizar o Windows antes.

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

Não é preciso trocar de branch: `main` é a branch padrão do repositório, então
o `clone` já traz ela.

**Para atualizar depois**, quando eu subir mudanças novas:

```bat
cd /d C:\cortes
git pull
```

O `git pull` não mexe no seu `.env` — ele não está versionado, justamente para
as suas chaves nunca irem parar no GitHub.

#### Os atalhos (o equivalente ao `pnpm dev`)

Estão na pasta **`atalhos\`**, não na raiz — eram dez arquivos misturados com o
código, e em ordem alfabética ficavam espalhados entre `app.py` e `subtitles.py`.
A pasta inteira é conveniência de quem roda no Windows e pode ser apagada sem
afetar o projeto (há um `LEIA-ME.txt` lá dentro dizendo isso).

Dê **duplo clique** no Explorer, ou digite o nome no Prompt de Comando. Todos
entram na pasta certa sozinhos, então não é preciso `cd` nenhum.

**E todos abrem o Docker Desktop se ele não estiver rodando.** Sem isso, o erro
que aparecia era este:

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

Ele não diz *"abra o Docker Desktop"* — diz que não achou um cano. Parece
problema do projeto, e é do Windows: o Docker Desktop não estava no ar. Agora
`_garantir-docker.bat` (chamado pelos outros) abre o programa e espera o motor
responder, até 3 minutos.

| Arquivo | Quando |
|---|---|
| **`subir.bat`** | **o do dia a dia.** Sobe em segundos, sem reconstruir. Usa a placa NVIDIA sozinho quando há uma |
| `parar.bat` | para tudo de verdade (`docker compose down`) |
| `atualizar.bat` | `git pull` + sobe. Avisa se as dependências mudaram |
| `reconstruir.bat` | só quando muda `requirements.txt`, `package.json` ou o `Dockerfile`. Com placa, já constrói com as libs de CUDA |
| `subir-gpu.bat`, `reconstruir-gpu.bat` | ficaram pelo costume: fazem o mesmo que os dois de cima |
| `abrir-painel.bat` | abre `localhost:5175` no navegador |
| `abrir-pasta-dos-cortes.bat` | abre no Explorer a pasta `output`, onde ficam os vídeos |
| `conferir-gpu.bat` | responde se a placa chegou ao container |
| `ver-log.bat` | mostra o log do backend ao vivo. **A única janela que fica rolando** |
| `_garantir-docker.bat` | não se roda direto: é o pedaço que os outros chamam para abrir o Docker |
| `_modo-gpu.bat`, `_subir.bat` | não se rodam direto: decidem se há placa e sobem (veja abaixo) |

**A placa NVIDIA é decidida num lugar só, e pela máquina** (desde 22-set-2026).
Antes havia um `subir` para CPU e outro para GPU, e o `atualizar.bat` subia pelo
de CPU: bastava atualizar uma vez para o `docker compose up -d` **recriar** o
backend sem a placa — sem erro, sem aviso. O whisper voltava ao `small` em CPU,
e um vídeo de 10 minutos passava a levar 5 só para transcrever.

Agora todo atalho que sobe pergunta ao `nvidia-smi` do Windows (que vem com o
driver da NVIDIA) e escolhe os arquivos do compose sozinho. A **primeira linha**
que ele escreve diz o que decidiu:

```
Placa NVIDIA encontrada: subindo com a GPU.
```

Se o Docker recusar a placa — o Docker Desktop fora do motor WSL 2, por
exemplo —, ele sobe em CPU para não ficar fora do ar e diz isso com todas as
letras. Devagar é melhor que parado; devagar **em silêncio** era o defeito.

**Todos sobem em modo destacado (`-d`) e devolvem o terminal**, desde
13-set-2026. Antes ficavam anexados ao log, e daí vinha uma confusão razoável:
a janela nunca fechava, cada atalho aberto virava mais uma janela rolando
`GET /health/ready ... 200 OK` para sempre, e ficava parecendo que havia quatro
sistemas rodando ao mesmo tempo. **Não havia: é uma pilha só.** `docker compose
up` não sobe nada novo se os containers já estão de pé — ele só se *anexa* ao
log deles. Quatro janelas eram quatro leituras do mesmo log.

Com `-d`, fechar a janela não para nada (e nunca parava — veja `atalhos\parar.bat`
abaixo). Quando o log for de fato necessário, ele tem um atalho próprio:
`atalhos\ver-log.bat`.

**O `--build` não é o normal, é a exceção.** Ele reconstrói a imagem inteira —
os 15 a 40 minutos. Só faz sentido quando muda a *lista de dependências*, e isso
acontece raramente. O resto do tempo é `atalhos\subir.bat`.

#### Depois do `git pull`, o que é preciso rodar

**Quase sempre nada, e o motivo não é óbvio.** O `docker-compose.yml` monta a
sua pasta *dentro* do container (`- .:/app` no backend, `- ./dashboard:/app` no
frontend). Não é cópia: é a mesma pasta vista de dois lugares. No instante em
que o `git pull` termina, os arquivos novos já estão lá dentro.

O que varia é se o processo que está rodando **percebe**:

| Processo | Percebe sozinho? | Por quê |
|---|---|---|
| **Vite** (frontend) | **sim**, com polling | vigia os arquivos — mas no Windows precisa de `VITE_USE_POLLING=1`, veja o quadro abaixo |
| **uvicorn** (backend) | **no Windows, não** | roda com `--reload`, e o `--reload` depende dos mesmos eventos que não chegam. Por isso o `atalhos\atualizar.bat` reinicia o backend por conta própria (~3 s) |
| **a imagem** (torch, node_modules) | só com `--build` | pacote instalado mora na imagem, não na pasta montada |

> **O bind mount do Windows não repassa evento de arquivo, e isso custou uma
> aba inteira.** A aba **Projetos** foi ao GitHub, o `git pull` a trouxe para o
> disco, o backend já respondia ao endpoint novo dela (`GET /api/jobs 200 OK`
> no log) — e ela não aparecia na barra lateral. O arquivo estava lá dentro; o
> que faltou foi alguém *avisar* o Vite. O Docker Desktop no Windows monta uma
> pasta do `C:\` dentro de um container Linux atravessando uma camada que não
> traduz as notificações do sistema de arquivos, então o inotify do container
> nunca dispara: o dev server segue servindo o grafo de módulos que leu quando
> subiu, indefinidamente. É por isso que recriar o container "resolvia" — na
> subida ele relê tudo do disco.
>
> Duas correções, uma para cada lado: o `docker-compose.yml` liga
> `VITE_USE_POLLING=1` no frontend (o `vite.config.js` troca os eventos por uma
> varredura a cada 300 ms; é barato porque só olha `dashboard/`), e o
> `atalhos\atualizar.bat` reinicia o backend explicitamente em vez de torcer para o
> `--reload` perceber — no backend a mesma varredura sairia cara, porque o
> repositório inteiro está montado em `/app` e `output/` cresce a cada job.

Daí a tabela:

> **Use o `atalhos\atualizar.bat` em vez de `git pull` na mão.** Ele faz o pull
> **e** reinicia os dois processos. Um `git pull` sozinho põe os arquivos no
> disco e não avisa ninguém — e é assim que se chega numa tela preta sem
> mensagem nenhuma (17-set-2026).

| O que mudou no `pull` | O que rodar |
|---|---|
| só `docs/*.md` | nada |
| `.jsx`, `.css` **editados** | nada — o polling do Vite pega (com `Ctrl+F5` se teimar) |
| arquivos de frontend **acrescentados ou apagados** | `atalhos\atualizar.bat` (reinicia o painel). O polling vigia o conteúdo dos arquivos que o Vite já carregou; o **grafo de módulos** ele monta na subida. Um arquivo novo não entra nesse grafo, e o painel abre **em preto** — sem erro e sem log |
| `.py` | `atalhos\atualizar.bat` já reinicia o backend; à mão, `docker compose restart backend` |
| `vite.config.js` | `docker compose restart frontend` (~3 s) |
| `docker-compose.yml` | `docker compose up -d` (recria o container, sem rebuild) |
| `requirements.txt`, `package.json`, `Dockerfile` | `docker compose up -d --build` |

**`--build` é o caro, e quase nunca é o certo.** Ele reconstrói a imagem — os
15 a 40 minutos da primeira vez. Só faz sentido quando muda a *lista de
dependências*, nunca quando muda só o código.

> **Sobre o `--reload` do backend**, porque a primeira versão disto estava
> errada: não basta acrescentar a flag. O `requirements.txt` fixa
> `uvicorn==0.46.0`, o pacote simples, e sem o `watchfiles` o uvicorn cai num
> reloader por polling (`StatReload`) que **registra em log que os
> `--reload-exclude` não têm efeito** e varre a árvore inteira atrás de `.py` a
> cada ciclo — `output/` incluído, que cresce a cada job. Por isso o
> `watchfiles` está fixado no `requirements.txt`, e por isso ligar isto custou
> **um** `docker compose up --build`.
>
> O que ele **não** resolve é o bind mount do Windows: o `watchfiles` também
> espera eventos do sistema de arquivos, e eles não atravessam. Ele tem um modo
> de polling (`WATCHFILES_FORCE_POLLING=1`), e deliberadamente não está ligado —
> o repositório inteiro está montado em `/app`, então a varredura passaria por
> `output/` a cada ciclo, que é exatamente o problema do `StatReload` de volta
> por outra porta. Em vez disso o `atalhos\atualizar.bat` reinicia o backend quando o
> `pull` traz código: são ~3 s, e não custam CPU o dia inteiro.

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

### 1b+. Mais IAs gratuitas, para quando uma delas falhar (opcional)

As duas chaves acima já bastam. As de baixo servem de **reserva**: quando o Groq e
o Gemini falham na mesma chamada (fila cheia, fora do ar, cota do dia — como o
`503 ... high demand` do Google), o programa passa na hora para a próxima que
tiver chave, em vez de esperar. Todas são **gratuitas e sem cartão** (conferido em
24-set-2026; o porquê de cada uma está no ADR-011 de `docs/DECISOES.md`).

**Você já ganhou três sem fazer nada:** a mesma chave do Groq agora também usa o
**Qwen** e o gpt-oss-20b (o Groq dá uma cota separada para cada modelo), e a mesma
do Google usa um segundo modelo Gemini.

Para cada uma que quiser, crie a chave no site e cole a linha no fim do `.env`,
como no passo 2:

| IA | Onde criar a chave | Linha para o `.env` |
|---|---|---|
| **Nemotron** (NVIDIA) | build.nvidia.com → entrar → "Get API Key" | `NVIDIA_API_KEY=...` |
| **Mistral** (pede telefone) | console.mistral.ai/api-keys | `MISTRAL_API_KEY=...` |
| **Ollama Cloud** | ollama.com/settings/keys | `OLLAMA_CLOUD_API_KEY=...` |
| **OpenRouter** (50 por dia) | openrouter.ai/keys | `OPENROUTER_API_KEY=...` |
| **Cloudflare** (duas linhas) | dash.cloudflare.com/profile/api-tokens (permissão "Workers AI") | `CLOUDFLARE_API_TOKEN=...` e `CLOUDFLARE_ACCOUNT_ID=...` |
| **GLM** (Z.ai, servidor na China) | z.ai/manage-apikey/apikey-list | `ZAI_API_KEY=...` |

Depois de colar, rode `atalhos\atualizar.bat` (ou `subir.bat`) para o servidor
ler o `.env` de novo. O log do próximo vídeo lista, na linha `Analyzing with a
cascata`, todas as IAs que entraram.

> ⚠️ **Várias delas usam o conteúdo para treino** — o log do job diz quais (Gemini,
> NVIDIA, Mistral, OpenRouter e Z.ai). Na Mistral dá para desligar em Settings →
> Privacy. Para vídeo seu, costuma ser aceitável; para vídeo de cliente, não.
>
> O **Cerebras** não entra nesta lista: deixou de ser gratuito em julho de 2026.

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
docker compose up -d --build
```

(`docker compose`, com espaço e sem hífen. O `docker-compose` com hífen é a v1,
antiga.)

A primeira vez leva de 15 a 40 minutos: a imagem instala torch, torchvision,
ultralytics, mediapipe e faster-whisper. **As seguintes sobem em segundos.**

O `-d` é o que faz o terminal voltar quando termina, em vez de ficar anexado ao
log para sempre. A construção continua aparecendo na tela — ela demora, convém
ver. Para parar tudo depois: `atalhos\parar.bat`, ou `docker compose down`.

Sobem três serviços:

| Serviço | Porta | O quê |
|---|---|---|
| backend | **8000** | FastAPI + fila de jobs |
| frontend | **5175** | o painel |
| renderer | 3100 | serviço de render em Node (Remotion) |

### Com GPU NVIDIA

Pelos atalhos, **não há passo nenhum**: `atalhos\reconstruir.bat` constrói a
imagem com as libs de CUDA e `atalhos\subir.bat` reserva a placa, os dois
sozinhos quando o `nvidia-smi` do Windows responde.

Por baixo, continuam sendo **dois** passos — e faltar o segundo era a armadilha:
instalar as libs de CUDA na imagem não faz o container enxergar a placa. À mão:

```bat
cd /d C:\Users\User\Documents\GitHub\Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build backend
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

O `docker-compose.gpu.yml` é uma **sobreposição**: ele passa `GPU=1` ao build,
reserva a GPU para o container e liga `WHISPER_MODEL=large-v3-turbo` +
`WHISPER_DEVICE=cuda`. **Todo comando `docker compose` à mão precisa dele**, ou o
`up` recria o backend sem a placa.
Ficou em arquivo separado de propósito — a reserva de dispositivo é exigência,
não preferência, e numa máquina sem placa o `up` falharia em vez de cair para
CPU.

No Windows basta o driver NVIDIA normal (ele traz suporte a WSL 2 desde 2021).
**Não se instala driver dentro do WSL.**

**Confirme que a placa chegou**, porque a falha aqui é silenciosa:

```bat
docker compose exec backend python diagnostico.py
```

A linha `placa p/ o whisper` responde. `sim` é GPU de verdade; `nao` significa
que ela não chegou ao container — e aí o `WHISPER_DEVICE=cuda` cai para CPU
sozinho, sem erro nenhum. Funciona, só que lento, que é o pior modo de falhar.

**A pergunta é feita ao `ctranslate2`, e não ao `torch`** — é o ctranslate2 que
o faster-whisper usa de fato. Não é preciosismo: os dois são bibliotecas
diferentes com exigências diferentes de CUDA/cuDNN, e o caso em que o torch
enxerga a placa e o ctranslate2 não é conhecido. `torch.cuda.is_available()`
respondendo `True` com a transcrição rodando em CPU é exatamente a falha
silenciosa disfarçada de conferência feita.

**Subiu quando o `-d` devolver o terminal e os três aparecerem de pé:**

```bat
docker compose ps
```

```
NAME               STATUS
virtu-clips-backend     Up 20 seconds (healthy)
virtu-clips-frontend    Up 19 seconds
virtu-clips-renderer    Up 19 seconds
```

O log do frontend anuncia `Local: http://localhost:5173/`. Esse `5173` é a
porta **dentro** do container; na sua máquina o painel atende em **5175** (o
`docker-compose.yml` mapeia `"5175:5173"`). Não é erro — só não adianta digitar
o que está escrito no log.

**No log, `GET /health/ready ... 200 OK` a cada poucos segundos, sem parar, é o
normal.** É o `HEALTHCHECK` do Dockerfile perguntando ao backend se ele
continua vivo, e `200` é a resposta certa. Linhas idênticas rolando para sempre
têm a cara exata de um loop travado; aqui são a aparência de um sistema
saudável. (`atalhos\ver-log.bat` é o atalho para ver isso quando você quiser.)

**Fechar a janela não para nada** — e nunca parou, mesmo antes do `-d`: os três
serviços têm `restart: unless-stopped` no compose, então o Docker os religa. O
único jeito de encerrar de verdade é `atalhos\parar.bat` (`docker compose down`).

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
"localLlm": { "provider": "cascade", "model": "openai/gpt-oss-120b", ... }
```

**Se vier `"localLlm": null`, a chave não chegou ao container.** Quase sempre é
uma destas três:

1. o arquivo virou `.env.txt` (veja o passo 2);
2. tem `#` no começo da linha — **espaço em volta do `=` não atrapalha**, isso
   foi medido com o `python-dotenv` que o projeto usa (a tabela está no passo 2);
3. o `docker compose` subiu de outra pasta.

Depois de corrigir o `.env`, é preciso **reiniciar** para ele ser lido de novo:
`atalhos\parar.bat` e depois `atalhos\subir.bat` (essa segunda vez é rápida, não reconstrói).

E o painel abre em **http://localhost:5175**.

---

## Passo 5 — O primeiro vídeo

**Use um arquivo do seu computador, não um link do YouTube.** Duas razões: o §8
do Plano Técnico registra que baixar do YouTube com `yt-dlp` fere os Termos de
Serviço deles, e um upload tira a rede da equação no primeiro teste — se falhar,
você sabe que o problema é o pipeline, não o download.

> **O que o campo de link aceita, desde 13-set-2026** (Fase 1, blocos 1.1 e 1.2):
>
> | Cola isto | Acontece |
> |---|---|
> | vídeo do YouTube | baixa (o log diz `🔌 Fonte: YouTube`) |
> | VOD da Twitch (`/videos/<número>`) | baixa, avisando que VOD expira em 7 a 60 dias |
> | clip da Twitch (`/clip/...` ou `clips.twitch.tv/...`) | baixa |
> | link do Google Drive (`/file/d/...`) | baixa; privado precisa de `GDRIVE_COOKIES` |
> | link direto de um `.mp4` | baixa do IP da sua máquina, sem proxy |
> | **canal da Twitch ao vivo** (`twitch.tv/<canal>`) | **grava 15 min e corta esse pedaço** |
> | lista de vídeos do canal (`twitch.tv/<canal>/videos`) | recusa na hora: é listagem, não vídeo |
>
> **A live é gravada em blocos, e isso é de propósito.** Não dá para baixar o
> que ainda não aconteceu: gravar uma live de 4h inteira seria um job de 4
> horas, que ocuparia a fila a tarde toda e não sobreviveria a um `git pull`
> com rebuild no meio. Então cada job grava um pedaço de 15 minutos
> (`TWITCH_LIVE_BLOCK_MINUTES` no `.env` muda isso, até 2h) e corta esse
> pedaço. Para cobrir mais, é enviar de novo — a automação disso é a Fase 4.
>
> Enquanto grava, a barra fica em "recebendo o vídeo" pelos 15 minutos. É
> esperado, e o log diz: `🔴 Gravando 15 min da transmissão ao vivo`.
>
> VOD de sub-only precisa de conta inscrita: `TWITCH_COOKIES` no `.env`, no
> mesmo formato do `YOUTUBE_COOKIES`. Clip e VOD público não precisam de nada.

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

### Onde os projetos ficam (e por que o Docker mostra tão pouco)

**No seu disco, na pasta do projeto — nunca dentro do Docker.** O
`docker-compose.yml` monta a pasta do repositório dentro do container, então o
programa roda no Docker mas escreve direto aqui:

```
C:\Users\User\Documents\GitHub\Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System\output\<job-id>\
```

Apagar o container, reconstruir a imagem ou desinstalar o Docker não leva os
cortes junto. O `416MB / 15.21GB` que o Docker Desktop mostra é **memória**
(RAM) do container naquele instante, não espaço em disco — e ela sobe enquanto
um vídeo processa (o modelo de transcrição e os quadros ficam na memória) e
desce depois. O `Disk: ... GB used` do rodapé do Docker Desktop também não são
vídeos: são as imagens do programa (Python, torch com CUDA, ffmpeg).

**Com placa NVIDIA, abrir o painel já sobe o modelo de transcrição** (desde
24-set-2026). Ele fica carregado na placa enquanto o painel estiver aberto — é
o que tira uns 15 a 25 s de cada vídeo — e sai sozinho 10 minutos depois que
você fecha a aba (`ASR_RESIDENTE_OCIOSO_MIN` no `.env` muda isso). Nesse tempo
a memória do container e a da placa ficam mais altas mesmo sem vídeo nenhum
processando: é o modelo esperando, não vazamento. Não ocupa disco.

`atalhos\abrir-pasta-dos-cortes.bat` abre essa pasta no Explorer.

Na pasta de cada projeto há mais de uma versão de cada corte: `..._clip_1.mp4`
é o reenquadrado limpo, `hooked_..._clip_1.mp4` tem o gancho e
`subtitled_...` tem a legenda por cima — o painel mostra e baixa a mais
completa. O vídeo original baixado também fica ali, porque o editor de cortes
recorta dele de novo.

**Nada é apagado sozinho desde 22-set-2026.** Até então uma limpeza automática
apagava o projeto 24 horas depois, e outra apagava os mais antigos quando a
pasta passava de 25 GB. Agora quem apaga é você, pelo ícone de lixeira na aba
**Projetos** — que leva a pasta inteira, o vídeo enviado daquele projeto e o
registro dele no banco (menos o de um corte já publicado, que é o histórico de
métricas). Se algum arquivo estiver aberto em outro programa (um player, a
pasta aberta no Explorer, o antivírus), o painel diz qual e pede para fechar e
apagar de novo, em vez de dizer "apagado" com o vídeo ainda no disco.

Quem quiser a limpeza automática de volta põe no `.env`:

```
JOB_RETENTION_SECONDS=86400   # apaga projeto com mais de 24 h
OUTPUT_MAX_GB=25              # apaga os mais antigos acima de 25 GB
```

---

## Passo 6 — Ler o relatório de custo

É o que fecha o critério de saída da Fase 0, e o que a Fase 1 precisa. No fim
do log do job, na janela do Prompt de Comando:

```
📊 Custo deste job:
   01_ingest                 0.8s
   02_probe                  6.2s
   03_transcribe          1310.0s
   04_detect                18.1s  1 chamada(s)  31200 tokens  [groq]
   05_06_render            960.0s (ocupado 2700s em 9x)
   └ 05_corte               50.0s
   └ 06_legenda             77.0s
   └ 06_reenquadra         173.0s
   TOTAL                  2295.1s  1 chamada(s)  31200 tokens
   12.4 min de fala → 2516 tokens/min falado
```

As linhas com `└` são os passes **dentro** do render, e não somam com ele: a
cadeia de um corte é corte → reenquadramento → [marca d'água] → [gancho] →
legenda, e cada seta é um encode inteiro do clipe.

O `(ocupado ... em 9x)` aparece quando um estágio rodou em paralelo: o primeiro
número é o tempo que **você esperou**, o segundo é o trabalho gasto somando os
`CLIP_WORKERS`. Até 16-set-2026 só existia o segundo, apresentado como se fosse
o primeiro — o render vinha multiplicado por 3 e o relatório acusava a
transcrição no lugar dele.

Também em `output\<job-id>\<nome>.timings.json`, e no `/api/status/<job-id>`,
campo `timings`.

**O número que importa é o último.** `tokens/min falado` é o que permite
calcular, por medição e não por estimativa, quanto custaria uma live de 4 h — e
é o insumo para calibrar o pré-filtro heurístico na Fase 1. O ADR-004 estimou
~75.000 tokens para uma live de 4 h; este número diz se a estimativa estava
certa.

### Se o YouTube recusar o download

**Colar o link e pronto é o caminho normal — cookies não são pré-requisito.**
O download sai anonimamente pelo cliente `tv` do yt-dlp, que é o único que o
YouTube ainda serve sem conta e sem token. No log isso aparece assim:

```
🔓 Sem cookies (YOUTUBE_COOKIES nao esta no .env e nao ha jar na pasta):
   usando os clientes anonimos do yt-dlp (tv, default).
```

Se mesmo assim o job morrer com:

```
ERROR: Sign in to confirm you're not a bot.
```

então uma de duas coisas aconteceu, e **elas têm consertos diferentes** — não
adivinhe qual, meça:

```
atalhos\testar-youtube.bat https://youtu.be/xxxxxxxx
```

Ele tenta um cliente por vez e imprime uma tabela. Leia assim:

- **Algum candidato passou** → é a lista de clientes que envelheceu. O próprio
  relatório imprime a linha a colar no `.env` (por exemplo `YT_CLIENTS_ANON=ios`).
  Cole, rode `atalhos\atualizar.bat` e mande o vídeo de novo. Não precisa
  reconstruir a imagem.
- **Nenhum passou, e todos no anti-bot** → é o IP desta casa, não a lista.
  Trocar de cliente não resolve. As saídas são esperar algumas horas, sair por
  outra rede, ou dar os cookies de uma conta — que é o que vem abaixo.

> Por que isso muda sozinho: quem decide qual cliente é servido é o YouTube, e
> a resposta troca sem aviso. Em 6-set-2026 a lista padrão devolvia 1080p sem
> cookies; em 22-set-2026 a mesma lista respondia "sign in to confirm you're
> not a bot", com o mesmo código, na mesma casa. Por isso a lista é variável de
> ambiente e existe um comando que a mede.

#### Dar cookies de uma conta (só se o passo acima disser que é o IP)

**São três passos, e o arquivo vai na pasta do projeto** — não
dentro do `.env`. A variável `YOUTUBE_COOKIES` continua valendo e vence quando
existe, mas ela guarda o *conteúdo inteiro* do arquivo, dezenas de linhas: é o
mecanismo de um deploy em nuvem, onde segredo se entrega por ambiente. Aqui o
repositório está montado dentro do container, então o arquivo basta.

1. No Chrome/Edge, instale uma extensão de exportar cookies no formato
   **Netscape** (procure por "cookies.txt").
2. Abra **youtube.com logado**, clique na extensão e exporte. O arquivo sai
   como `www.youtube.com_cookies.txt`.
3. Salve esse arquivo na **raiz do projeto**, ao lado do `docker-compose.yml`.
   Não precisa renomear: o adapter do YouTube aceita esse nome e também
   `cookies.txt`.

Não precisa reiniciar nada — o `main.py` é um processo novo a cada job e lê o
arquivo na hora. Mande o vídeo de novo e o log passa a dizer
`🍪 ... achei www.youtube.com_cookies.txt na pasta do projeto`.

> **O arquivo é credencial viva.** Quem o tiver entra na sua conta sem senha e
> sem 2FA. Ele está no `.gitignore` (desde 22-set-2026), então não sobe num
> `git push` — mas não o mande por e-mail, chat nem o cole num issue. Para
> revogar, basta sair da conta do YouTube naquele navegador: os cookies
> exportados morrem junto.

Se voltar a falhar depois de semanas, é a sessão que expirou: exporte de novo
por cima.

---

### Se estiver lento

```bat
docker compose exec backend python diagnostico.py
```

Ele junta a medição com o ambiente e conclui só quando tem as duas metades. "A
transcrição é 70% do tempo" não é defeito nenhum num vídeo muito falado; "o
whisper está em CPU" é apenas verdade numa máquina sem placa. Juntas, viram o
próximo passo.

Dois padrões vêm de fábrica e nenhum dos dois reclama:

| Variável | Nasce | Numa máquina com placa |
|---|---|---|
| `WHISPER_DEVICE` | `cpu` | `cuda` (+ `WHISPER_COMPUTE=float16`) |
| `FFMPEG_ENCODER` | `x264` | `auto` (usa h264_nvenc, cai para x264 sozinho) |

O segundo pesa mais do que parece: **não é um encode por corte**, são 3 a 5 do
mesmo clipe, e os dois primeiros a `-crf 18`.

Rode o diagnóstico **dentro do container** (`docker compose exec`). Fora dele as
sondagens não alcançam a placa nem o ffmpeg da imagem, e a resposta que ele dá é
"não deu para saber" — que ele nunca apresenta como "não".

---

## Passo 7 — O banco (não é mais opcional)

Desde a Fase 3 o pipeline **escreve** no banco: cada job deixa uma linha em
`sources`, uma em `jobs` e uma por corte em `clips` — e é a linha de `clips` que
permite publicar depois. Sem banco o pipeline continua funcionando (ele falha
aberto de propósito), mas a aba **Publicação** fica sem nada para mostrar.

Com o stack no ar, abra **outro** Prompt de Comando (o primeiro está ocupado
mostrando o log):

```bat
cd /d C:\cortes
docker compose exec backend alembic upgrade head
docker compose exec backend python db_seed.py --no-ddl
```

Cria `data\cortes.db` com as nove tabelas, o tenant fixo e o template padrão.

---

## Passo 8 — Publicar

Abra a aba **Publicação** no painel (porta 5175).

### O caminho que já funciona sem configurar nada

**Pacote do dia.** Um botão, um ZIP: os cortes do dia mais um `.txt` por corte
com título, descrição e hashtags — sem rótulo e sem cabeçalho, para selecionar
tudo e colar. É o driver `manual`, e ele é o padrão de propósito: automatiza o
trabalho todo menos abrir o app e apertar publicar.

Dentro do ZIP há um `LEIA-ME.txt` com a ordem sugerida, que é a ordem em que a
detecção já entregou — do melhor para o pior.

### Para o YouTube subir sozinho

Uma vez só, e não dá para pular: a API do YouTube exige um token que só nasce de
um consentimento no navegador.

1. Em <https://console.cloud.google.com>: criar um projeto, habilitar a
   **YouTube Data API v3**, e em *Credenciais* criar um **ID do cliente OAuth**
   do tipo **Aplicativo de computador**. Anote o Client ID e o Client Secret.
2. Na pasta do projeto, **fora** do Docker (o navegador precisa abrir na sua
   máquina):

```bat
cd /d C:\cortes
python youtube_oauth.py
```

Ele abre a tela do Google, você autoriza, e o segredo é guardado em
`data\vault\youtube\canal.json` com permissão restrita. O script imprime
também as três linhas de `.env` equivalentes, se você preferir ambiente a
arquivo — nesse caso, cole no `.env` e reinicie o backend.

3. No painel, em **contas**, adicione a conta com o mesmo nome que você passou
   em `--handle` (o padrão é `canal`). A linha passa a dizer *"sobe sozinho pela
   API oficial"* em vez de *"fila manual"*.

**São 6 uploads por dia**, e o número não é escolha nossa: a API cobra 1.600
unidades por vídeo contra 10.000/dia. O sétimo do dia **cai na fila manual
sozinho** — não vira erro. O contador zera à meia-noite no horário do Pacífico,
não no seu.

### Na primeira vez, publique privado

O padrão já é `private`. Publique um corte, confira no YouTube Studio que o
título, a descrição e o vídeo estão certos, e só então mude. **Este é o primeiro
caminho do projeto que sai da sua máquina**: um erro no resto custa um job
refeito, um erro aqui é um vídeo no seu canal.

Se você pedir `public` e o vídeo subir como `private`, o painel diz isso na
linha do resultado — costuma ser o app OAuth que ainda não passou pela
verificação do Google, e não um erro do projeto.

---

## Passo 9 — Definir o dono (e só então pensar em expor)

Abra o painel. Se ninguém tem senha ainda, a primeira tela pede **um e-mail e uma
senha** — é o dono da instalação.

**Isso não cria uma conta nova.** Dá senha e e-mail de verdade ao usuário que o banco
já tinha e que já é dono de tudo: os projetos, os templates, as contas de publicação.
Nada muda de lugar; você só passa a conseguir entrar.

A partir daí o painel pede login, e cada conta só enxerga o que é dela — projetos,
arquivos, clipes e fila.

### Antes de abrir para a internet

Até esta fase o aviso era simples: **não exponha**. Não havia autenticação nenhuma.
Agora tem condição, e ela é uma só: **defina o dono antes.** Enquanto ninguém tem
senha, qualquer um que alcance a porta 8000 processa, apaga e baixa os seus vídeos.

Três coisas continuam valendo mesmo com o dono definido, e nenhuma é pequena:

- **Não há HTTPS aqui.** A senha e o token viajam como a conexão os carregar. Expor
  significa pôr um proxy com TLS na frente (Caddy, nginx, Cloudflare Tunnel), não
  abrir a porta no roteador.
- **`/thumbnails/` ainda é público.** As sessões de thumbnail não têm carimbo de dono.
- **Não há recuperação de senha nem 2FA.** Perder a senha do dono significa mexer no
  banco à mão. É ferramenta pessoal; o preço é esse.

### Uma segunda conta

Pela API, logado como dono:

```bat
curl -X POST http://localhost:8000/api/usuarios ^
  -H "Authorization: Bearer SEU_TOKEN" ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"outra@exemplo.com\",\"senha\":\"uma-senha-boa\"}"
```

Ela nasce num espaço próprio e não vê nada do seu. Para alguém que deva ver os **seus**
projetos, mande `"tenant": "mesmo"`.

---

## Passo 10 — Deixar publicar sozinho

Na aba **Publicação**, o botão **agendar** espalha os cortes do projeto pelas próximas
janelas em vez de publicar na hora. O padrão: **3 por dia**, às 11h, 15h e 19h, com
pelo menos 3 h entre um e outro e **±25 minutos de variação**.

A variação não é enfeite nem configuração opcional: publicar 12:00:00 todo dia é um
dos sinais que a detecção de automação cruza. Pedir zero não desliga — cai num piso de
5 minutos (ADR-007).

Os números estão no `.env` (`SCHEDULE_PER_DAY`, `SCHEDULE_WINDOWS`,
`SCHEDULE_MIN_GAP_MINUTES`) porque **são chutes informados, não verdade**: descobrir o
horário certo exige retenção medida, e isso é a Fase 5.

O teto duro é outro e não é escolha nossa: **6 por dia**, da quota do YouTube. O
agendador nunca o ultrapassa.

---

## Passo 11 — Descobrir por que está devagar

Na aba **Publicação**, o cartão **onde vai o tempo**. Ele lê as medições que as suas
execuções já deixaram — não precisa rodar nada de novo.

O número grande é o **fator**: quantos minutos de processamento cada minuto de vídeo
custou. Um vídeo de 10 minutos que leva 40 dá `4,0×`. É o único número que dá para
comparar entre execuções, porque não depende de quão longo era o vídeo.

Abaixo dele, uma barra por estágio, **na ordem em que acontecem** — ler nessa ordem é
o que deixa ver onde ele engasga.

As observações apontam para coisas que dá para conferir, não para palpites. A mais
provável, se a transcrição dominar:

> **Sem GPU, a transcrição roda em CPU.** Desde 22-set-2026 o log do job diz qual
> whisper rodou (`🎙️ [ASR] whisper small em CPU ...`), porque antes isso não
> aparecia em lugar nenhum. Numa máquina com placa, `atalhos\subir.bat` a devolve —
> e `atalhos\diagnostico.bat` diz, se não devolver, onde a corrente arrebentou.

Se o tempo estiver **fora de estágio nenhum**, o relatório diz isso também — aí é fila,
subida do subprocesso, ou um pedaço que ninguém instrumentou, e não o pipeline.

---

## Passo 12 — Métricas (só depois de publicar)

A tabela `metrics` é o que permite, daqui a alguns meses, trocar "o LLM achou este
corte bom" por "este corte reteve 62%". Ela só enche se você emitir a credencial de
**leitura**, uma vez:

```bat
cd /d C:\cortes
python youtube_oauth.py --leitura
```

**O token de publicação não serve, e não serve de propósito.** Ele tem escopo só de
upload — se vazar, a diferença para o escopo completo é a diferença entre um vídeo
indesejado e um canal vazio. A credencial de leitura é outra, só com escopos
`readonly`, guardada em outro arquivo: a que publica não lê, a que lê não publica, e
nenhuma das duas apaga.

Depois disso o servidor mede sozinho a cada 6 horas. Para conferir na hora:

```bat
curl -X POST http://localhost:8000/api/metricas/coletar -H "Authorization: Bearer SEU_TOKEN"
```

E `GET /api/calibracao` mostra o cruzamento entre o que o modelo previu e o que deu.
**Ele vai dizer que a amostra é pequena, e isso é a resposta certa** — com menos de
dez cortes medidos, qualquer correlação é ruído com um número em cima.

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
| "There was a problem with WSL", `wsl.exe --version: exit status 1` com a tela de ajuda no lugar da versão | o WSL é o embutido no Windows, e o Docker precisa do empacotado (2.1.5+) | `wsl --install` em PowerShell **como Administrador**, e **reiniciar** — ver o quadro em "Antes de começar" |
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
| Um job continua rodando depois de fechar o terminal | os serviços têm `restart: unless-stopped` — fechar a janela **não** os para | `docker compose down` (com `down`, não fechando a janela) |
| Um job "cancelado" volta a processar sozinho | corrigido em 13-set-2026: o manifesto de resume o re-enfileirava | use o botão **cancelar** no painel, que apaga o manifesto |
| Poucos cortes num vídeo longo | o teto padrão é 12 | `CLIP_TARGET_MAX=25` no `.env` + `docker compose restart backend` |
| Build morre sem espaço | a imagem com torch é gorda | `docker system prune -a` e ~15 GB livres |
| `failed to solve: invalid file request .cache/huggingface/...` no build | o modelo do Whisper é baixado para `.cache/` dentro da pasta do projeto, e o cache do HuggingFace usa **links simbólicos** que o contexto de build do Docker não segue | corrigido em 13-set-2026: `.cache/`, `output/`, `uploads/` e `data/` entraram no `.dockerignore`. Se aparecer, `git pull` |
| O build leva minutos "transferindo contexto" | `output/` estava sendo copiado a cada build | mesmo conserto acima |
| Log rolando sem parar com `GET /health/ready 200 OK` | **não é erro**: é o HEALTHCHECK do Dockerfile confirmando que o backend está vivo | nada a fazer; `200 OK` é a resposta certa |
| A linha do frontend anuncia `localhost:5173` | é a porta dentro do container | no navegador é **5175** (`"5175:5173"` no compose) |

---

## Apêndice A — Testar a chave do Groq sem subir nada

Só se você quiser conferir a chave **antes** de esperar o build. O passo 4 testa
a mesma coisa pelo navegador, então isto é atalho, não obrigação.

Abra o **PowerShell** (tecla Windows → digite `powershell` → Enter) e rode as
duas linhas abaixo, uma de cada vez. **Cada linha é um comando inteiro** — não
tem `\` no fim:

```powershell
$k = "gsk_COLE_A_SUA_CHAVE_AQUI"
Invoke-RestMethod -Uri "https://api.groq.com/openai/v1/chat/completions" -Method Post -Headers @{ Authorization = "Bearer $k" } -ContentType "application/json" -Body '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"responda apenas: ok"}]}' | ConvertTo-Json -Depth 6
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
docker compose up -d --build
```

E a conferência do passo 4 pode ser por terminal:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/config
```

O teste do Apêndice A, em uma linha:

```bash
curl -s https://api.groq.com/openai/v1/chat/completions -H "Authorization: Bearer $GROQ_API_KEY" -H "Content-Type: application/json" -d '{"model":"openai/gpt-oss-120b","messages":[{"role":"user","content":"responda apenas: ok"}]}'
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
