# Plano da plataforma — canais, criação e automação

**Data:** 25 de setembro de 2026 · **Revisado:** 26 de setembro de 2026
**Status:** aprovado pelo autor em 26-set-2026, com as respostas da seção
"Decisões do autor"; a etapa 7.1 começou.
**Relação com os outros planos:** o `PLANO-DE-ACAO.md` cobre as Fases 0 a 6, o
motor que baixa, transcreve, corta, publica e mede. Este cobre a Fase 7 em
diante: a plataforma em volta dele, organizada por **canal**.

**Este documento é a memória do projeto para a Fase 7.** Tudo o que o autor
pediu e decidiu em conversa está aqui, com as palavras dele no "Registro das
conversas", para que nada precise ser conversado de novo. O `CLAUDE.md`, que
toda sessão nova lê primeiro, aponta para cá.

---

## O que estamos construindo

Um **sistema com um painel** — os dois:

- **O motor**, no computador de quem usa (Docker ou ajudante): baixa, transcreve,
  corta, cria, publica e, a partir desta fase, roda as automações sozinho
  enquanto o PC estiver ligado.
- **O painel**, o site no Cloudflare: onde se cria, acompanha e decide. Ele não
  processa nada; conversa com o motor da própria máquina.
- **As integrações**: YouTube, TikTok e Instagram; e, desde a 7.10, Douyin,
  Kuaishou, Bilibili e Xiaohongshu, pelo pacote do dia. É por elas que o
  conteúdo sai e as métricas voltam.

No mercado, o nome disso é *plataforma de automação de conteúdo*: estúdio de
criação e central de publicação no mesmo lugar. O pedido do autor é que ela
junte o que hoje está espalhado em ferramentas separadas: corte com IA, vídeo
gerado por IA e gestão de contas em rede social — "a ferramenta suprema".

## A ideia em uma página

- **O canal é o centro, não o vídeo.** Um canal tem nicho (infantil, finanças,
  curiosidades, acidentes...), identidade visual e **contas ligadas**. O mesmo
  canal no YouTube e no TikTok é o caso mais comum.
- **Cada canal cria de duas formas, separadas:**
  - **cortes de vídeo real**: o que o programa faz hoje, a partir de um link, de
    uma live ou de uma busca por tema;
  - **vídeo criado por IA**: roteiro, cenas, voz e montagem. **O estilo não sai
    do nicho sozinho**: é um *estilo de criação* que a pessoa configura (3D,
    motion, o que quiser), fica salvo na seção de vídeo de IA do canal, e a IA
    não foge dele.
- **Um conteúdo, um galho por plataforma.** Num canal ligado, o que é criado vai
  para o YouTube e para o TikTok, e depois cada galho é gerido sozinho (título,
  horário, métricas).
- **Análises em três telas** quando o canal é ligado: a geral do canal, a do
  YouTube e a do TikTok.
- **O PC ligado é quem trabalha.** Cada canal tem uma *receita* (de onde vêm os
  vídeos, como editar, quando postar, se espera aprovação), e o motor a cumpre
  sem ninguém olhar.
- **Primeiro a estrutura, depois as funções.** A Fase 7.1 monta as telas e os
  dados com lugar para tudo; o que ainda não funciona aparece marcado "em
  breve", dizendo o que vai fazer. Cada fase seguinte preenche um pedaço.

## O mapa do aplicativo

```
Início            o que roda agora, o que vai ao ar hoje, avisos, atalho para criar
Canais            todos os canais, com o avatar e os ícones das plataformas ligadas
  └ um canal
      Visão geral   números, projetos, próximos posts, avisos do canal
      Criar         cortes de vídeo · vídeo de IA · série em partes
      Automação     a receita do canal
      Agenda        o que vai ao ar e quando, por plataforma
      Publicados    cada galho, com status e link
      Análises      Geral · YouTube · TikTok · Instagram
      Ajustes       nicho, identidade, contas ligadas, aprovação
Criar             cortar um vídeo sem canal (o Clip Generator de hoje)
Projetos          todo vídeo processado, de todos os canais
Agenda            o calendário de todos os canais
Análises          todos os canais lado a lado
Ferramentas       YouTube Studio (títulos e miniaturas) e o que vier
Frota             aparelhos (phone farm): os celulares, as contas de cada um,
                  o ensino do app, o que cada um fez
Configurações     chaves de IA, contas conectadas, uso e limites, agente,
                  versões, desempenho do PC
Ajuda             primeiros passos e respostas curtas
```

### O que já existe e só muda de lugar

| Hoje | Na estrutura nova |
|---|---|
| Clip Generator | **Criar**, e dentro de cada canal com o canal já escolhido |
| Projetos | **Projetos**, com filtro por canal |
| Publicação → pacote do dia | **Agenda**: o pacote é "o que postar hoje à mão" |
| Publicação → contas | **Canais** (ligar) e **Configurações → Contas conectadas** |
| Publicação → publicar e fila | **Agenda** (a de todos os canais e a aba Agenda de cada canal); o que já saiu, na aba **Publicados** do canal |
| Publicação → onde vai o tempo | **Configurações → Desempenho**: nunca foi publicação |
| YouTube Studio | **Ferramentas** |
| AI Agent | **sai**: é a página do projeto original, em inglês. O "Conectar um agente" das Configurações já cobre |
| Configurações | fica, e ganha contas conectadas, uso e limites e desempenho |

No motor, quase tudo o que as telas novas pedem já existe: contas de YouTube,
TikTok e Instagram no banco, a fila e o rastro de cada publicação, o agendador
com jitter (ADR-007), o envio pelo YouTube, o coletor de métricas, a calibração,
o YouTube Studio, os templates de legenda e o renderizador Remotion. As peças
novas do motor são o **canal** e a **receita**.

## O modelo de dados

As regras de sempre (ADR-008): `tenant_id` em toda tabela, FK composta com
`tenant_id` em toda referência, migração pelo Alembic, e o
`tests/test_db_schema.py` cobrando.

**E uma regra nova, que decide o desenho:** o motor cria o banco no boot com
`create_all` (`db_seed.seed()`), e ninguém roda `alembic upgrade` na máquina de
quem usa. O `create_all` cria tabela que falta, mas **nunca acrescenta coluna a
tabela que já existe**. Uma coluna nova em `accounts` ou `jobs` não chegaria ao
banco do autor, e a primeira consulta que a lesse quebraria. Por isso, campo novo
em tabela que já existe entra como **tabela nova de ligação**, que o
`create_all` cria sozinho. A migração do Alembic vai junto, para quem usa o
caminho de produção.

| Tabela | Hoje | O que muda |
|---|---|---|
| `channels` | — | **nova** (7.1): nome, nicho, avatar, cor, idioma, se espera aprovação |
| `channel_accounts` | — | **nova** (7.1): liga uma conta a um canal. Uma conta, no máximo um canal; conta sem canal continua valendo |
| `channel_jobs` | — | **nova** (7.1): liga um projeto a um canal. Sem linha = projeto feito sem canal |
| `accounts` | conta de plataforma (YouTube, TikTok, Instagram) | nada |
| `jobs` | um vídeo processado | nada |
| `publications` | um corte numa conta | nada: **já é o galho**. A unicidade (corte, conta) é o que impede postar duas vezes |
| `metrics` | série de views e retenção por publicação | nada; as análises agregam por conta e por canal |
| `channel_settings` | — | **nova** (7.5): a agenda do canal (as janelas e quantos posts por dia) e o "feito para crianças" |
| `recipes` | — | **nova** (7.5): o tipo, de onde vêm os vídeos e como editar. Quando postar e se espera aprovação ficaram no **canal** (a agenda nos ajustes; a aprovação desde a 7.1) |
| `candidates` | — | **nova** (7.5): vídeos que a receita achou, com a licença, esperando a vez — a caixa de entrada de fontes |
| `source_licenses` | — | **nova** (7.5): a origem e a licença de cada fonte processada (autor, licença, link), de onde sai o crédito |
| `clip_approvals` | — | **nova** (7.5): os cortes da automação esperando a pessoa — a caixa de aprovação |
| `series`, `series_parts` | — | **novas** (7.6): a série de um projeto (nome, idioma, duração de cada parte, quantas) e a parte de cada corte — é por ela que o agendador sabe a ordem |
| `series_playlists`, `series_playlist_items` | — | **novas** (7.6): a playlist de cada série em cada conta do YouTube, e as partes que já entraram nela |
| `creation_styles`, `creations` | — | **novas** (7.7): o estilo de criação de cada canal (o documento de `estilos.py`; as imagens dos personagens ficam em `DATA_DIR/estilos/`), e cada vídeo de IA — o projeto, a ideia, o título e o roteiro, que é de onde sai o "não repetir o tema" |
| `fleet_settings`, `devices`, `device_accounts`, `device_scripts` | — | **novas** (7.9): se a frota está ligada, os aparelhos, a conta que mora em cada um (com o modo, o limite do dia e a hora do consentimento) e o caminho do post ensinado em cada app, com o resultado do ensaio |

O projeto também guarda o canal na própria pasta (`.canal`, ao lado do `.tenant`):
a lista de projetos vem do disco, e o banco falha aberto. Pelo mesmo motivo, a
origem e a licença da fonte (7.5) moram também na pasta (`.origem.json`): é dali
que o crédito sai na hora de publicar. E a série (7.6) também: o pedido
(`serie.json`) e as partes que já ficaram prontas (`serie_progresso.json`), que
é o que deixa o motor retomar uma série parada no meio sem refazer nada. E o
vídeo de IA (7.7): o pedido com a cópia do estilo (`criacao.json`), as imagens
dos personagens (`referencias/`), o roteiro, cada cena, a narração e a legenda —
é o que o deixa continuar de onde parou sem gastar a cota de novo.

## As fases

A numeração é o **nome** da etapa, não a ordem; a ordem está em "Ordem e
dependências", no fim.

### 7.1 — A estrutura

- **Limpar as sobras do projeto original.** A UI de cobrança (`TrialGate`,
  `TopUpModal`, `PlanChoiceModal`, `UsageMeter`, `InvoicesCard`,
  `WatermarkModal`, `TrialUpgradeModal`), a aba AI Agent, `examples/n8n/`,
  `ops/` e `design.md`; e as telas de conta em nuvem que só existem com
  `billingEnabled`. Cada item conferido com busca no código antes de sair: a
  lista do CLAUDE.md é o ponto de partida, não a verdade.
- **Navegação nova**, com a mesma técnica de hoje: uma definição alimenta o
  trilho do computador, a gaveta e a barra do celular (Parte D do
  `OPORTUNIDADES.md`).
- **Cada tela com endereço** (`#/canais/<id>/agenda`). Hoje a aba aberta não fica
  na URL; com canais, voltar, recarregar e mandar o link de uma tela precisa
  funcionar. Endereço com `#` porque o site é estático no Cloudflare. **Sem
  biblioteca nova**: toda dependência nova do painel muda o `package.json`, e o
  botão de atualizar do Docker recusa essa mudança (reconstruir a imagem, 40
  minutos).
- **Quebrar o `App.jsx`** (1.963 linhas) em páginas. Ele fica com o esqueleto:
  navegação, sessão e avisos.
- **Canais**: criar, editar e apagar; avatar (enviado ou gerado); nicho; contas
  (as já cadastradas ou novas, pelo @ da conta); **se espera aprovação, escolhido
  ao criar o canal** — quem decide é quem usa.
- **A página do canal** com as sete abas. Onde há dado, o dado (projetos e
  publicados do canal); onde não há, o "em breve" dizendo o que vai fazer.
- **Criar**: o fluxo de hoje, com o canal escolhido no começo, ou nenhum.
- **Visual**: ícones de YouTube, TikTok e Instagram, e o avatar do canal em todo
  lugar que o nomeia, sobre os tokens e primitivos que a Parte D do
  `OPORTUNIDADES.md` manda preservar. O autor quer "um visual bem bonito".
- **Dados**: `channels`, `channel_accounts` e `channel_jobs`, com a API de
  canais no motor.

**Pronto quando:** dá para criar o "Canal infantil" ligado a uma conta do YouTube
e a uma do TikTok, entrar nele, criar cortes pelo fluxo de hoje com o canal já
escolhido, e ver os projetos dele no canal e em Projetos. Todo o resto do mapa tem
lugar visível, marcado "em breve". E nada do que funciona hoje para de funcionar:
cortar sem canal, publicar, agendar, YouTube Studio, chaves, atualizar pelo botão.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.1a | limpar as sobras do projeto original | feita (26-set) |
| 7.1b | motor: tabelas, `canais.py`, `/api/canais`, o canal no projeto (`.canal` + `channel_jobs`), `PUT /api/jobs/{id}/canal` | feita (26-set) |
| 7.1c | painel: navegação com endereço, as dez páginas, canais, ícones | feita (26-set) |
| 7.1d | conferir as telas no computador e no celular, docs, CI | feita (26-set) |

Conferido com o motor de verdade e um navegador (Playwright), no computador e no
celular: criar um canal pela tela com uma conta nova (o botão só acende depois de
escolher a aprovação), mover um projeto de canal pelo cartão, mandar um vídeo com
o canal marcado e cair na tela do projeto, recarregar sem perder a aba, apagar o
canal soltando o projeto e a conta, e o `#app` das versões antigas abrindo o
Início. Com um motor de antes dos canais, as telas de canal dizem para atualizar
e o Criar segue sem o seletor.

### 7.2 — Qualidade dos cortes

**Fica para o fim, a pedido do autor** (ver a ordem). Ele pode puxá-la antes,
quando mandar a lista.

- **A lista do autor**: as melhorias que ele já enxerga nos cortes (a enviar).
- **O que falta aqui e o Brevidy tem:**
  - remover silêncios: o `cuts.removeSilence` que o template prevê e ninguém
    implementa (B5 do `OPORTUNIDADES.md`);
  - emojis sugeridos na legenda;
  - escolher na criação o preset de legenda e o modelo de IA.
- **A tela de carregamento**, com as etapas e, agora, número de verdade:
  - porcentagem por corte, com os quadros prontos sobre o total, que o motor já
    conta;
  - tempo estimado pela média dos últimos vídeos desta máquina, que o
    `/api/tempo` já tem.

  A regra de antes continua: barra que mente é pior que barra nenhuma, e sem
  medida não há número.
- No fim, todos os cortes do vídeo numa grade, como hoje.

**Pronto quando:** a lista do autor está feita, e um vídeo mostra o carregamento
com porcentagem e tempo estimado que batem com o log.

### 7.3 — Contas de verdade: conectar e publicar

- **Cada pessoa usa o próprio cadastro de aplicativo** (decisão de 26-set-2026),
  como já faz com as chaves de IA: o projeto dela no Google Cloud e o app dela no
  TikTok, com as credenciais coladas em Configurações e um passo a passo para
  criá-las.
- **"Conectar YouTube" pelo site.** Hoje é `python youtube_oauth.py` no terminal.
  O motor faz o mesmo fluxo quando o botão pede: o retorno vem para a própria
  máquina, que é o que o Google aceita para programa instalado. São dois
  consentimentos, como hoje, um para publicar e outro para ler métricas. Duas
  credenciais pequenas em vez de uma grande (bloco 5.1).
- **A cota nova do YouTube.** Hoje são 100 envios por dia numa cota só de envio,
  e 100 buscas por dia noutra. O `quota.py` e o teto do agendador ainda seguram
  em 6 envios por dia, pela regra antiga de 1.600 unidades por envio. Corrigir os
  dois, e o teste que congela o número.
- **A trava do post atrasado — defeito conhecido do agendador de hoje.** O laço
  pega tudo o que venceu (`publish_queue.devidas`) e publica um atrás do outro:
  com o PC desligado por horas, cinco posts sairiam no mesmo minuto. O autor
  pediu o contrário: quando o PC volta, posta, mas **nunca vários de uma vez**.
  Por conta, sai o primeiro atrasado (se o espaçamento mínimo desde o último post
  permitir) e os outros são reespalhados nas janelas seguintes, com o mesmo
  jitter. Hoje nada publica sozinho — ninguém conectou o YouTube —, então o
  defeito ainda não morde; tem de estar consertado antes que morda.
- **TikTok.** O app de desenvolvedor da pessoa, com o Content Posting API. Até a
  auditoria, o post pela API sai **só privado**, e no máximo 5 contas por dia; o
  pacote do dia continua sendo o caminho para postar público.
- **Instagram** entra aqui, junto (decisão de 26-set-2026), numa versão mais
  simples: é a plataforma que a frota (7.9) vai usar mais.
- **"Já publiquei" pede o link.** Hoje o botão da fila manual não guarda o link
  do post, e sem ele o que se posta à mão nunca é medido.
- **O galho por plataforma.** Num canal ligado, o corte pronto vira uma
  publicação por conta. Cada uma tem título, descrição e hashtags da plataforma
  dela, e horário próprio.

**Pronto quando:** o primeiro corte sai do programa, de verdade, para um canal
ligado, com os galhos rastreados, pela API ou à mão com o link registrado. Em
modo privado primeiro, conferido no app de cada plataforma (a ressalva da Fase
3 continua valendo). E um teste prova a trava: cinco posts vencidos para a mesma
conta não saem juntos.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.3a | motor: cota nova do YouTube (100 envios/dia), agenda por conta, a trava do post atrasado, "já publiquei" com link, os galhos do canal no publicar e no agendar; e o acerto do banco que já existe (`db_acerto`) | feita (26-set) |
| 7.3b | cadastro de aplicativo por pessoa (Configurações → aplicativos, com o passo a passo) e "Conectar YouTube" pelo site, para publicar e para medir | feita (26-set) |
| 7.3c | TikTok pela Content Posting API (Direct Post), privado até a auditoria: o cadastro do app do TikTok nas Configurações, o "conectar" da conta pelo site e o driver `tiktok-api` na cascata | feita (26-set) |
| 7.3d | Instagram na versão simples: o galho do Instagram sai pelo pacote do dia (agora escolhido por plataforma no painel) e volta pelo "já publiquei" com o link; a legenda respeita o limite de 5 hashtags do app; a publicação pela API fica para depois (o porquê está logo abaixo) | feita (26-set) |
| 7.3e | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI; de quebra, a grade de cortes do projeto passou a se dividir pelo espaço que sobra (a 1280 px os botões dos cartões se sobrepunham desde o menu lateral da 7.1) | feita (26-set) |

A trava tem o teste que o "pronto quando" pede
(`tests/test_agendador.py::TestTravaNoLaco::test_cinco_posts_vencidos_da_mesma_conta_nao_saem_juntos`):
cinco posts vencidos para a mesma conta, uma volta do laço, e sai um; os outros
quatro ficam para as janelas seguintes, espaçados, e a volta seguinte não
publica nada. Conferido também no navegador: publicar um projeto no Canal
infantil abre um galho por conta (YouTube e TikTok), o "já publiquei" recusa o
link do TikTok no galho do YouTube e guarda o link certo, e agendar no canal dá
horário próprio a cada conta.

O "Conectar YouTube" foi conferido no navegador até onde dá sem uma conta de
verdade: o botão abre a tela do Google com a volta para este computador, só o
escopo de envio e PKCE; uma volta com código falso é recusada com a frase certa,
e o mesmo pedido não vale duas vezes; conectada, a conta mostra "publica
sozinho" e a fila passa a usar a API. **O que falta ver no PC do autor** é o
consentimento de verdade, com o projeto dele no Google Cloud (o roteiro está no
`COMO-EXECUTAR.md`, Passo 8).

Dois defeitos antigos apareceram no caminho e foram consertados junto: a linha
agendada que caía na fila manual era entregue de novo a cada minuto, para
sempre; e a agenda mostrava as horas com a diferença do fuso (3 h no Brasil),
porque o banco devolve a hora sem ele.

O TikTok foi conferido no navegador do mesmo jeito: a conta do TikTok manda
cadastrar o app **do TikTok** (e não o do Google); a client key torta é recusada
dizendo qual campo; o "conectar" abre a tela do TikTok com a client key, os dois
escopos (`user.info.basic,video.publish`), a volta para este computador e o
desafio do PKCE em hexadecimal; a volta com código falso diz "o TikTok não
aceitou", e não "o Google"; conectada, a conta diz "sobe sozinho pela API do
TikTok" e avisa que, até a auditoria, o post sai só para ela e a conta precisa
estar privada. **Até a auditoria, o driver pede sempre o privado**, mesmo que
se peça público e a conta ofereça: o TikTok recusaria o post. **O que falta ver
no PC do autor** é o post de verdade, com o app dele no TikTok for Developers
(em Sandbox) e a conta de teste privada (`COMO-EXECUTAR.md`, Passo 8).

**O Instagram na versão simples (7.3d)** é o galho completo sem a API: o
pacote do dia agora se escolhe por plataforma no painel (até aqui ele só
baixava o do YouTube, e a legenda do Instagram existia no programa sem chegar a
ninguém), a legenda sai com no máximo 5 hashtags — o limite do app desde
dez-2025, que antes era 30 —, e a conta do Instagram diz na tela o caminho dela:
pacote do dia, postar, e o link no "já publiquei", que é o que deixa acompanhar
o post.

**Por que a publicação pelo Instagram fica para depois**, pesquisado em
26-set-2026:

- **A API oficial precisa do vídeo num endereço público.** O Instagram busca o
  arquivo por `video_url`, num servidor HTTPS aberto na hora do post; o programa
  roda no computador de quem usa, e abri-lo para a internet vai contra o
  desenho inteiro. O envio direto do arquivo (`rupload.facebook.com`) existe,
  mas o exemplo oficial da Meta usa token do **Facebook**, não do Instagram, e
  há relato público de ele falhar na prática (`ProcessingFailedError ...
  FILE_NOT_FOUND`), com a recomendação de voltar ao `video_url`.
- **Não existe post privado para testar.** Conta profissional do Instagram (a
  única que a API aceita) não pode ser privada, e o que sobe aparece para os
  seguidores na hora — o contrário do "privado primeiro" deste passo.
- **E o autor já disse qual é o caminho do Instagram**: "é mais outro tipo de
  coisa (...) bom pra phone farm" (7.9).

O que mudaria isso: a Meta documentar o envio direto com o token do Instagram,
ou o programa ganhar um jeito seguro de servir o corte por HTTPS só durante o
post. Medir o Instagram (7.4) é outra conversa: ler métricas não envia vídeo, e
o token de leitura pode ser colado do painel da Meta.

**Onde a 7.3 está (26-set-2026).** O código está inteiro e conferido até onde
dá daqui: a trava tem o teste que o "pronto quando" pede; os galhos, o "já
publiquei" com link, o "conectar" do YouTube e do TikTok e o pacote por
plataforma rodaram no navegador; e todas as telas da 7.3 (Agenda, a visão geral,
a agenda e os publicados do canal, Configurações → aplicativos e → contas, e o
projeto) abrem sem erro e sem rolagem para o lado no computador e no celular.
**O que falta para fechar o "pronto quando" depende das contas do autor**, e o
roteiro está no `COMO-EXECUTAR.md`, Passo 8:

1. **YouTube pela API, privado**: cadastrar o projeto dele no Google Cloud em
   Configurações → aplicativos, conectar a conta, publicar um corte e conferir
   no YouTube Studio;
2. **TikTok pela API, privado**: o app dele no TikTok for Developers em
   Sandbox, a conta de teste PRIVADA no app, publicar e conferir no app;
3. **Instagram à mão**: o pacote do dia do Instagram, postar e colar o link no
   "já publiquei".

Os três no mesmo corte de um canal ligado são o "primeiro corte com os galhos
rastreados" do critério.

O autor decidiu testar tudo no final (ver "Decisões do autor"): a 7.4 começa sem
esperar esse teste.

### 7.4 — Análises por canal

- **YouTube**: visualizações e retenção, pela API de Analytics que o coletor já
  usa.
- **TikTok**: visualizações, curtidas, comentários e compartilhamentos dos vídeos
  da própria conta, pela API de exibição. Retenção, a documentação não mostra.
- **Instagram**: o que a API oficial de contas profissionais der.
- **Três telas no canal ligado**: Geral (a soma) e uma por plataforma. Em
  Análises, no menu, todos os canais lado a lado.
- **Início** com os números do dia.
- **A calibração começa a ter dado** (bloco 5.2), e o horário de postar deixa de
  ser palpite: o ADR-007 previa calibrar com retenção medida.

**Pronto quando:** um canal ligado mostra as telas com números coletados das
plataformas, e o relatório de calibração conta os cortes medidos.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.4a | motor: medir o TikTok (a Display API, com o "conectar para medir" separado do de postar) e o Instagram (o token colado, conferido e renovado sozinho); curtidas, comentários, compartilhamentos e tempo médio também no YouTube (`metric_details`); a coleta passa a ser por conta, e uma conta sem conexão não para as outras | feita (26-set) |
| 7.4b | motor: `analises.py` (a soma do canal e de cada plataforma, o ganho das últimas 24 h, a série por dia, os melhores cortes, o horário de postar) e as rotas `/api/analises`, `/api/analises/canais` e `/api/analises/hoje`; a calibração por plataforma e por canal | feita (26-set) |
| 7.4c | painel: as três telas no canal ligado (Geral e uma por plataforma ligada), Análises no menu com os canais lado a lado, os números do dia no Início, o "conectar para medir" do TikTok e o token do Instagram | feita (26-set) |
| 7.4d | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (26-set) |

**Como o Instagram mede, e por que é diferente.** Publicar pela API do Instagram
ficou fora (7.3d), mas medir não envia vídeo. O login da Meta só devolve a
pessoa para endereço HTTPS cadastrado, e o programa atende em `localhost` —
então, em vez do botão, a pessoa gera o token no painel do app dela na Meta e
cola na conta. O programa pergunta ao Instagram de quem é o token antes de
guardar (de outra conta, recusa e diz qual), renova uma vez por semana (o token
dura 60 dias), e marca a conexão como vencida se o Instagram recusar — a tela
pede outro.

**As três regras das telas**, que moram no motor (`analises.py`) para valerem
em todas:

- vale o último número **conhecido** de cada campo — uma leitura em que o
  YouTube não deu a retenção não apaga a de ontem;
- o ganho de um dia só conta com base: um corte antigo medido pela primeira vez
  não "ganha" num dia as visualizações da vida inteira;
- o horário de postar só aponta uma faixa com 5 posts medidos em duas faixas **e**
  a melhor passando a segunda por 25%. Na conferência, sem a margem, 2.036
  contra 2.020 virava "a tarde rende mais".

**Onde a 7.4 está (26-set-2026).** Conferido com o motor de verdade, um banco de
demonstração com quatro semanas de leituras e um navegador (Playwright), no
computador e no celular: as análises de um canal ligado (Geral, YouTube e
TikTok), as da página Análises (os canais lado a lado e a soma por plataforma), os
números do dia no Início, o "conectar para medir" do TikTok abrindo a tela dele
com `user.info.basic,video.list`, a volta para este computador e o PKCE em
hexadecimal, e o token do Instagram (tirar, colar um torto — recusado pelo
formato —, colar um no formato certo — o Instagram de verdade não é alcançável
daqui, e a tela diz que não conseguiu falar com ele). As cores dos gráficos
passaram no validador de paleta contra o fundo dos cartões. O relatório de
calibração conta os cortes medidos, por plataforma. **O que falta ver no PC do
autor** são os números de verdade, com as contas dele: o roteiro está no
`COMO-EXECUTAR.md`, Passo 12.

### 7.5 — Automação por canal

- **A receita** diz quatro coisas:
  - de onde vêm os vídeos: link fixo, busca por tema, live da Twitch ou pasta;
  - como editar: template, duração, layout e idioma;
  - quando postar: janelas por canal, com o jitter do ADR-007;
  - se espera aprovação: **configuração do canal, escolhida por quem usa**.
- **Busca de vídeos com licença.** O YouTube marca os vídeos Creative Commons, e
  a busca filtra só esses: pela API (100 buscas por dia) ou pelo yt-dlp,
  conferindo a licença de cada vídeo antes de baixar. O crédito do autor vai na
  descrição, como a licença exige, e a origem fica registrada em
  `source_licenses`.
- **Caixa de entrada de fontes** e **caixa de aprovação** de cortes, para os
  canais que pedem aprovação.
- **"Feito para crianças"** marcado sozinho em todo envio de canal infantil: é
  exigência do YouTube pela COPPA, a lei americana.
- **Não repetir**: a mesma fonte ou o mesmo corte não vai duas vezes, nem entre
  canais.
- **O motor ligado.** Para rodar sozinho, o motor tem de subir com o Windows: o
  ajudante já faz isso; no Docker, o Docker Desktop precisa iniciar com o
  Windows. O post cuja hora passou com o PC desligado segue a trava da 7.3.
- **O fuso da agenda (achado na 7.4, consertado aqui).** O agendador calculava
  as janelas no fuso do processo, e no Docker o container roda em UTC:
  11h/15h/19h viravam 8h/12h/16h em Brasília. Agora o painel manda o fuso do
  navegador ao motor a cada vez que abre, e as janelas de cada canal valem nele;
  o contorno `SCHEDULE_WINDOWS=14,18,22` deixou de ser preciso.

**Pronto quando:** o canal infantil, com o PC ligado e ninguém mexendo, acha um
vídeo com licença, corta, espera a aprovação (ou não, se o canal estiver assim) e
posta nos horários dele, com o crédito na descrição.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.5a | motor: as cinco tabelas; a agenda do canal (as janelas e quantos posts por dia, nos ajustes do canal) no fuso de quem usa — o conserto do achado da 7.4 —; e o "feito para crianças" (escolhido no canal, ou pelo nicho), que vai no envio do YouTube e no LEIA-ME do pacote do dia | feita (26-set) |
| 7.5b | motor: as quatro fontes da receita — a busca com licença Creative Commons conferida vídeo a vídeo (pela API, com a cota de 100 buscas por dia, ou pelo yt-dlp), os links (vídeo, playlist ou canal), a live da Twitch em blocos e a pasta do canal —; a origem gravada no projeto e em `source_licenses`; e o crédito no fim do texto de toda plataforma, sem nunca ser cortado | feita (26-set) |
| 7.5c | motor: o laço (a cada 5 minutos, um vídeo por vez, parando quando a agenda do canal tem dois dias de posts), o fim do job (a caixa de aprovação ou a agenda do canal), a caixa de aprovação e o "não repetir" — a fonte, entre canais, e o corte, na mesma plataforma | feita (26-set) |
| 7.5d | painel: a aba Automação do canal (a receita, a caixa de entrada de fontes e a de aprovação, com a prévia do corte), a agenda do canal nos Ajustes, o calendário da semana na Agenda e o resumo no Início | feita (26-set) |
| 7.5e | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (26-set) |

**Como a receita ficou, e por quê:**

- **Quando postar e se espera aprovação são do canal, não da receita.** As
  janelas valem para tudo o que o canal posta — pela receita, pela aprovação ou
  à mão —, e a trava do agendador trabalha por conta: duas receitas no mesmo
  canal (a de cortes e, na 7.7, a de IA) postariam pelas mesmas janelas de
  qualquer jeito. A agenda fica nos ajustes do canal; a aprovação, onde está
  desde a 7.1. A receita só as mostra.
- **O idioma é o do canal** (7.1): é nele que a busca procura e que o crédito é
  escrito. Os títulos e a legenda saem na língua falada do vídeo, como sempre.
- **A busca só traz licença conferida**, e por isso roda sem pedir nada a quem
  usa. Links, live e pasta pedem a confirmação de que a pessoa tem os direitos,
  e **trocar a fonte apaga a confirmação**: quem confirmou uma lista de links não
  confirmou a próxima.
- **O estoque manda, não o relógio.** Com dois dias de posts na agenda (ou
  cortes esperando a aprovação), a receita não corta mais nada — senão, um canal
  que posta 3 por dia e corta 5 por vídeo acumularia uma pilha que ninguém vai
  postar.
- **O crédito nunca é o que se corta.** Quando o texto passa do limite da
  plataforma, quem encolhe é a descrição que a IA escreveu; o crédito, que a
  licença exige, vai inteiro.
- **Aprovar e não caber em conta nenhuma não some**: o corte volta a esperar, e
  a tela diz por quê.

**Onde a 7.5 está (26-set-2026).** O "pronto quando" roda inteiro nos testes do
motor (`tests/test_automacao.py`): o canal infantil acha um vídeo Creative
Commons (a busca é imitada; o resto é o motor de verdade, com o `/api/process`
inteiro), corta, e posta às 11h, 15h e 19h de Brasília com o crédito na
descrição — com e sem a aprovação. As telas foram conferidas com o motor de
verdade, um banco de demonstração com três canais (o infantil, com aprovação e
busca; um de finanças, com links e sem aprovação; um de fatos, com a pasta) e um
navegador (Playwright), no computador e no celular: a aba Automação, o modelo
do nicho no editor, a caixa de entrada (na fila, cortados e fora, com o motivo
de cada um), a caixa de aprovação com a prévia, a agenda do canal, o calendário,
o Início, e as Ferramentas apontando para as receitas. Na conferência saíram
cinco acertos de tela — o texto do "agendar" citava as janelas da instalação com
o destino num canal que tem as dele, a caixa de aprovação listava os cortes de
trás para a frente, e, no celular, as miniaturas esticavam, os layouts da
receita não cabiam e a fila cortava a hora do agendado — e três textos que ainda
anunciavam a automação como futura. Na revisão do código, o "feito para
crianças" passou a olhar também o canal da **conta** de destino, e não só o do
projeto: um projeto sem canal publicado na conta do canal infantil sairia
desmarcado. **O que falta ver no PC do autor** é a rede de verdade: a busca no
YouTube, o corte de um vídeo achado por ela e o post com o crédito. O roteiro
está no `COMO-EXECUTAR.md`, Passo 13.

### 7.6 — Séries em partes

Um vídeo longo (uma live, um filme sem direitos autorais) vira Parte 1, 2, 3...,
em blocos de cerca de um minuto, na ordem.

- "Parte N" no vídeo e no título, postadas em sequência.
- No YouTube, uma playlist por série.
- Reaproveita o corte por tempo e a live em blocos (bloco 1.5).

**Pronto quando:** uma live de 1 hora vira uma série agendada, na ordem, sem
buraco e sem repetição.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.6a | motor: dividir em partes (`series.py`) — contíguas, cortadas nas pausas da fala, perto da duração pedida —; o modo série no pipeline, sem IA escolhendo trecho (nenhuma chave é pedida), com o "Parte N" no vídeo e no título, a segunda tentativa sem reenquadrar para a parte que falhou e a retomada que não refaz o que já ficou pronto; o pedido no `/api/process`; e as quatro tabelas | feita (27-set) |
| 7.6b | motor: postar na ordem — cada conta só solta uma parte depois da anterior; a que falhou segura as seguintes até alguém tentar de novo ou pular; as que ficaram para trás ganham horários novos, na ordem —; a publicação presa "subindo" vira "falhou" em 30 minutos; e o "agendar no canal quando ficar pronta" | feita (27-set) |
| 7.6c | motor: uma playlist por série no YouTube, pela terceira conexão da conta ("conectar para playlists"), que é opcional | feita (27-set) |
| 7.6d | painel: "Série em partes" no Criar, a série na tela do projeto, a série num item só na fila (com a parte que pede atenção em cima) e o botão da playlist na conta | feita (27-set) |
| 7.6e | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (27-set) |

**Como a série ficou, e por quê:**

- **As partes cobrem o trecho inteiro, sem buraco e sem repetir**: o fim de uma
  é o começo da seguinte. Quantas partes: o tempo dividido pela duração pedida,
  arredondado (uma live de 1 hora dá 60 partes de 1 min; 2 min 30 s com partes de
  1 min dão três de 50 s). Cada fronteira cai na maior pausa da fala a até 20% do
  ponto exato, de preferência num fim de frase, e a parte começa um instante antes
  da primeira palavra — nunca no meio de uma. Sem fala (um filme mudo), corta no
  tempo.
- **Nenhuma IA escolhe trecho**, então a série não pede chave de IA e não gasta
  cota. A transcrição continua: é ela que diz onde estão as pausas, e a legenda
  sai dela.
- **"Parte N" no vídeo** nos 5 primeiros segundos (ou o tempo todo, ou não), com
  os estilos do gancho; **no título**, sempre ("Nome - Parte N"). A descrição do
  TikTok e do Instagram diz "Parte 3 de 60 — Nome".
- **Uma parte que falhou tenta de novo sem reenquadrar** (o quadro inteiro sobre o
  fundo desfocado): uma série com buraco é pior que uma parte com enquadramento
  simples. Se nem assim sair, a série segue sem ela, e a tela do projeto diz qual
  faltou.
- **Parou no meio (o PC desligou), recomeça de onde parou**: as partes prontas
  ficam anotadas na pasta do projeto, e são as mesmas partes da primeira vez.
- **Na agenda, cada conta solta uma parte por vez, na ordem.** A que falhou segura
  as seguintes daquela conta — publicar a 4 sem a 3 quebraria a série —, e a fila
  diz "parada". Tentar de novo ou pular a parte destrava: a primeira das que
  ficaram para trás sai na hora, se a trava de sempre deixar, e as outras ganham
  horários novos nas janelas do canal, na ordem. As outras contas não esperam.
- **A publicação que ficou "subindo" por 30 minutos vira "falhou"**, com o aviso
  de conferir na plataforma se ela subiu mesmo assim. Acontece quando o PC desliga
  no meio de um envio; sem isto, a série daquela conta ficaria parada para sempre.
- **"Agendar no canal quando ficar pronta"** vem marcado quando há canal: ao
  terminar, as partes vão para a agenda do canal, nas janelas dele — 3 por dia por
  padrão, então uma live de 1 hora é uma série de 20 dias. Não passa pela caixa de
  aprovação: pedir a série já é a aprovação. E **numa série não há "publicar
  agora"**: soltaria as 60 partes de uma vez.
- **A playlist é opcional, porque é a permissão mais ampla do programa.** O Google
  não tem uma permissão só para playlists: criar uma exige a de gerenciar a conta
  do YouTube. Por isso ela é uma terceira conexão, separada das de publicar e de
  medir, e a série funciona igual sem ela. Com ela, a playlist nasce quando a
  primeira parte vai ao ar, e cada parte entra na ordem. Cada chamada gasta 50
  unidades da cota diária (10.000), e o que não cabe hoje entra amanhã. Apagada no
  YouTube, o programa cria outra.
- **Na fila, a série é um item só**: uma linha por conta com a contagem ("2 de 60
  publicadas") e o que pede atenção ("a parte 3 falhou · 57 paradas atrás dela",
  com os botões de tentar de novo e pular ali mesmo), e as partes, em ordem, num
  clique. Aberta por inteiro, uma live de 1 hora eram 60 grupos, e a parte que
  falhou ficava no fim da página. A aba Agenda do canal passou a mostrar também o
  que falhou e o que está subindo: é justamente o que destrava as partes paradas.
- **O site novo com o programa antigo não cria série.** O site é publicado antes
  de o programa de quem usa ser atualizado, e um programa de antes da 7.6 ignora
  o pedido de série: faria cortes comuns, sem erro nenhum. O formulário pergunta
  ao programa se ele sabe fazer série e, se não souber, manda atualizar.

**O que a série consertou de antes**, porque numa série os defeitos apareciam
toda vez:

- **O número do corte.** Com um corte que não renderizou, o seguinte passava a ser
  tratado pelo número dele: publicar o corte 3 subia o arquivo do 4, e trocar a
  legenda do 3 mexia no 4. Numa série, era a Parte 4 indo ao ar com o título da 3.
  Consertado no motor inteiro e na tela.
- **As escolhas do projeto na retomada.** Um job retomado depois de um reinício
  perdia o que a pessoa escolheu na tela (enquadramento, legenda, template) e
  rodava com os padrões. Agora as escolhas vão junto no arquivo de retomada.
- **O projeto recuperado do disco** mostrava todo corte prometido, inclusive o que
  não renderizou, como um cartão sem vídeo.
- **A duração do corte que começa no segundo zero** não aparecia no cartão — a
  Parte 1 de toda série.

**Para o autor decidir:** a playlist pede a permissão de gerenciar a conta do
YouTube (o Google não oferece uma menor). Ficou opcional, com a explicação na tela
de conexão; se preferir não oferecê-la, é só dizer, e a série segue sem playlist.

**Onde a 7.6 está (27-set-2026).** O "pronto quando" roda nos testes do motor
(`tests/test_serie_no_motor.py`): uma live de 1 hora vira 60 partes agendadas em
duas contas do canal, e o agendador, avançado no tempo, solta as 60 de cada conta
na ordem, sem buraco e sem repetir; com a parte 3 falhando no YouTube, as
seguintes esperam, e tentar de novo ou pular as destrava na ordem, sem o TikTok
esperar. O pipeline em modo série roda o `__main__` do `main.py` como ele está,
com as bibliotecas pesadas imitadas (`tests/test_main_serie.py`). As telas foram
conferidas com o motor de verdade, um banco de demonstração (a live de 60 partes
com a parte 3 falhando no YouTube e a playlist; um filme de 8 partes com a 5
faltando) e um navegador, no computador e no celular. Na conferência saíram três
acertos: a fila, que com uma série de 60 partes ocupava a página e deixava a parte
que falhou no fim (virou um item só); a aba Agenda do canal, que escondia o que
falhou; e o projeto recuperado do disco, com a parte que faltou como cartão sem
vídeo. **O que falta ver no PC do autor**: uma live de verdade virando série, o
"Parte N" no vídeo e a playlist no YouTube. O roteiro está no `COMO-EXECUTAR.md`,
Passo 14.

### 7.7 — Vídeo curto criado por IA

- **O que se monta:** roteiro (a cascata grátis já escreve), cenas, imagens ou
  vídeo, voz, legenda e montagem.
- **O estilo de criação é configurado, não adivinhado** (decisão de
  26-set-2026). Nada de "infantil = 3D" automático: quem usa monta um estilo
  (personagens, visual, voz, ritmo, o que quiser), ele fica salvo na seção de
  vídeo de IA do canal, e todo vídeo daquela seção segue o estilo — é o que
  mantém os episódios parecidos entre si e bem feitos. Como exatamente a tela de
  estilo funciona se desenha quando a etapa começar.
- **Motion já tem motor aqui.** O Remotion, renderizador que o projeto já tem em
  container no Docker, desenha animação a partir de dados: a IA escreve a cena e
  ele anima, grátis e local. O ajudante não o leva hoje (`empacotar.FORA`), e
  isso entra na conta.
- **O resto começa com uma pesquisa**, como a do ADR-011: o que há de grátis no
  mês para imagem, vídeo e voz. Modelo de vídeo por API (Veo, Kling, Runway) é
  pago; o caminho grátis é montar, ou rodar um modelo aberto na placa, devagar.
- **Personagem consistente** entre cenas e episódios é o problema difícil das
  histórias, e é ele que decide a ferramenta.

**Pronto quando:** um canal com um estilo salvo gera sozinho um vídeo de um
minuto no estilo (roteiro, imagem, voz e legenda), sem nenhum serviço pago, e um
segundo vídeo sai reconhecivelmente no mesmo estilo.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.7a | pesquisa: o que há de grátis para imagem, voz e vídeo, e o personagem consistente — virou o ADR-013 | feita (27-set) |
| 7.7b | motor: a mídia grátis (`midia_ia.py`) — imagem pelo Cloudflare com as referências dos personagens, voz pelo Gemini numa chamada por vídeo, a cota do dia contada em disco | feita (27-set) |
| 7.7c | motor: o estilo de criação do canal (`estilos.py`, `criacoes.py`) — o documento, a tabela, o salvar, e a imagem de referência de cada personagem (gerada ou enviada) | feita (29-set) |
| 7.7d | motor: a criação como job (`criar_video.py`, `montagem.py`) — roteiro, imagens, voz, legenda e montagem, retomando de onde parou; o pedido no `/api/criacoes` | feita (29-set) |
| 7.7e | motor: a receita de IA — o canal cria sozinho, com a lista de ideias, o estoque da agenda e a caixa de aprovação | feita (29-set) |
| 7.7f | painel: o estilo na aba Criar do canal, "Vídeo criado por IA" no Criar, a receita de IA na Automação e o "continuar de onde parou" no projeto | feita (29-set) |
| 7.7g | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (29-set) |

**Como o vídeo de IA ficou, e por quê** (o levantamento e as escolhas estão no
ADR-013):

- **O estilo mora no canal e é escolhido campo a campo**: o formato (história,
  fatos curiosos, explicação ou livre), para quem é, o tom, as regras do canal, a
  duração (20 a 90 s), quantas cenas (3 a 14), o visual (oito atalhos, como
  "livro infantil" e "aquarela", mais a descrição e o que nunca aparece), até
  quatro personagens, a voz (30, com o jeito de cada uma, e o jeito de falar) e a
  legenda. Nada vem do nicho: um canal infantil e um de finanças nascem com o
  mesmo estilo padrão, e quem muda é a pessoa.
- **O personagem consistente é uma imagem de referência, aprovada pela pessoa.**
  Cada personagem ganha uma imagem, gerada (uma da cota do dia) ou enviada — um
  desenho dela mesma serve. Ela vai para o modelo em toda cena em que ele
  aparece, com a mesma descrição em texto; é isso que faz o segundo vídeo sair
  com a mesma Lulu. Personagem sem imagem impede criar: um vídeo com ele sairia
  diferente a cada cena.
- **Um vídeo é um projeto como os outros**: entra na fila, tem a barra (escrevendo
  o roteiro, desenhando as cenas, gravando a narração, sincronizando a legenda,
  montando o vídeo), o cancelar, a retomada depois de um reinício, a publicação e
  a agenda. A ideia é opcional: sem ela, o roteiro inventa uma, e nunca repete o
  tema de um vídeo que o canal já fez.
- **A legenda é o texto do roteiro, no tempo da voz.** O whisper só dá o tempo de
  cada palavra — ele erra justamente o nome do personagem ("Lulú"), e quem
  escreveu o texto nós sabemos. Cada cena troca de imagem quando a fala dela
  começa.
- **Saem dois arquivos**, como num corte: o vídeo limpo e o legendado. É o limpo
  que deixa trocar o estilo da legenda depois, pela tela do projeto, sem queimar
  uma legenda por cima da outra.
- **Nada é refeito**: o roteiro, cada imagem e a narração ficam na pasta do
  projeto. Um vídeo que parou (a cota do dia acabou, o PC desligou) continua de
  onde parou pelo botão "continuar de onde parou", sem gastar a cota de novo com o
  que já saiu. Mesmo depois de o programa reiniciar ele aparece na lista, com o
  botão.
- **A cota é conferida antes, nunca no meio**: o motor só começa um vídeo se as
  imagens dele cabem na cota grátis do dia (cerca de 8 mil neurons do Cloudflare,
  uns 8 vídeos de 8 cenas), e a tela diz quantos ainda cabem hoje. O roteiro que
  sai com cenas demais junta as vizinhas mais curtas: cada cena é uma imagem da
  cota, e nenhuma fala se perde.
- **A receita de IA** (aba Automação) cria sozinha: uma ideia por vídeo, na ordem
  da lista; acabada a lista, uma ideia nova sobre o tema. Um vídeo de cada vez;
  com posts para dois dias na agenda (ou vídeos esperando aprovação), ela espera.
  O vídeo pronto vai para a caixa de aprovação (canal que pede) ou direto para a
  agenda do canal, um galho por conta, como os cortes. O que parou continua de
  onde parou até três vezes; depois a ideia é pulada, e a tela diz qual — salvar
  a receita de novo a devolve à fila. A receita de cortes e a de IA dividem a
  agenda, o estoque e a caixa de aprovação do canal.
- **As chaves são as que já existem**: o token e o ID da conta do Cloudflare
  (imagens) e a chave do Gemini (voz), nas Configurações → Chaves de IA. A voz do
  Gemini no plano grátis treina com o conteúdo, como a cascata de texto já diz.
- **O site novo com o programa antigo não cria vídeo de IA**: a tela pergunta ao
  programa se ele sabe e, se não souber, manda atualizar antes do clique.

**Para o autor decidir:**
- O movimento das cenas é o lento, de câmera (aproximar, afastar, deslizar), sobre
  imagens paradas: vídeo gerado por IA de graça não existe hoje (ADR-013). Se ele
  quiser animação de verdade, os caminhos são o Remotion (só no Docker) ou um
  modelo aberto na placa, devagar — é uma escolha dele.
- A cota do Cloudflare é dividida entre as imagens e a cascata de texto; o motor
  reserva 2 mil neurons para o texto (`CLOUDFLARE_IMAGE_NEURONS_DAILY`, 8 mil). Se
  ele não usar o Cloudflare para texto, dá para subir até 10 mil.

**Onde a 7.7 está (29-set-2026).** O "pronto quando" roda nos testes: o job de
criação de ponta a ponta com o ffmpeg de verdade (`tests/test_criar_video.py`) —
roteiro, imagens com a referência só nas cenas do personagem, narração, legenda
com o nome certo e montagem vertical no tempo da voz —, o estilo e o pedido pela
API (`tests/test_criacao_no_motor.py`) e a receita criando sozinha, agendando e
seguindo para a próxima ideia (`tests/test_receita_ia.py`). As telas foram
conferidas com o motor de verdade, um banco de demonstração (o canal da Lulu com
dois personagens, um vídeo pronto, um parado e a receita ligada; um canal com um
personagem sem imagem) e um navegador, no computador e no celular. Na
conferência saíram dois acertos: o vídeo que parou sumia da lista depois de um
reinício (e a tela dizia "não existe mais", justo no que só precisava de
"continuar"), e o quadro do topo da Automação dizia "receita desligada" com a
receita de IA criando. Na revisão do código saiu um terceiro: o Início, com as
duas receitas ligadas no mesmo canal, mostrava só uma. **O que falta ver no PC do autor**: um vídeo de verdade —
as imagens do Cloudflare, a voz do Gemini e se o segundo vídeo sai com a mesma
cara. O roteiro está no `COMO-EXECUTAR.md`, Passo 15.

### 7.8 — Vídeo longo

A mesma máquina da 7.7, em episódios mais longos para o YouTube: uma novelinha de
vários minutos. Depende de a 7.7 estar de pé. O cartão do Criar já prometia os
dois caminhos — "um vídeo horizontal longo, montado a partir dos cortes ou de um
roteiro" —, e a etapa entrega os dois.

**Pronto quando:** um canal com um estilo salvo cria um episódio horizontal de
vários minutos que continua a história do episódio anterior, sem nenhum serviço
pago; e os cortes de um projeto viram um vídeo horizontal de "melhores momentos",
com capítulos, que sobe para o YouTube em partes, retomando se a conexão cair.

**Andamento** (atualizado a cada parte entregue):

| Parte | O quê | Situação |
|---|---|---|
| 7.8a | motor: o episódio longo por IA — horizontal, de 2 a 10 minutos, a narração em blocos, os capítulos e a história que continua | feita (29-set) |
| 7.8b | motor: a compilação horizontal dos cortes — da origem deitada quando ela está no disco, com capítulos e legenda | feita (29-set) |
| 7.8c | motor: o vídeo longo vai só para o YouTube — o envio em partes com retomada, os capítulos na descrição, o galho do canal | feita (30-set) |
| 7.8d | painel: Criar → Vídeo longo (o episódio e a compilação), o vídeo deitado no projeto e a publicação só no YouTube | feita (30-set) |
| 7.8e | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (30-set) |

**Como o vídeo longo ficou, e por quê:**

- **Dois caminhos na mesma tela** (Criar → Vídeo longo): o episódio criado por
  IA, no estilo salvo no canal, e a compilação dos cortes que já existem. Os dois
  são horizontais (1920x1080) e **vão só para o YouTube**: TikTok e Instagram são
  a tela em pé. Publicado no canal inteiro, ele abre só o galho do YouTube; a
  tela de publicar nem oferece as outras contas, e o pacote do dia do TikTok e do
  Instagram não o leva.
- **O episódio é o vídeo de IA da 7.7, deitado e mais longo.** A duração vai de 2
  a 10 minutos, com uma imagem a cada 15 segundos de fala (um episódio de 5
  minutos tem 20 cenas). A cota é conferida pela duração escolhida, antes do
  clique: um episódio de 10 minutos (40 imagens) cabe na cota grátis de um dia,
  e a tela diz quantas imagens ainda cabem hoje.
- **A narração sai em blocos de uns dois minutos e meio.** Uma fala de vários
  minutos numa chamada só é o que a voz grátis do Gemini faz pior (ela acelera,
  muda e corta); em blocos, cada um é uma chamada da cota de voz do dia, o bloco
  quebra entre duas cenas e os blocos prontos ficam na pasta — a cota que acabar
  no terceiro não custa os dois primeiros de novo.
- **A história continua.** O episódio pode ser avulso ou de uma história: com
  ela, o roteiro recebe o título e o resumo dos episódios anteriores e continua de
  onde o último parou, e o vídeo sai com "História - Episódio N: título". Um nome
  novo começa uma história no episódio 1. Enquanto o episódio anterior não
  terminou, o próximo espera — é do resumo dele que o novo continua.
- **Os capítulos seguem as regras do YouTube, ou não saem.** O primeiro em 0:00,
  pelo menos três, cada um com 10 segundos: uma lista fora disso é ignorada
  inteira pelo YouTube, sem aviso. No episódio, o roteiro diz onde cada capítulo
  começa; na compilação, cada corte abre um, com o título dele. Um capítulo curto
  demais some e o trecho fica com o anterior.
- **A compilação sai do vídeo de origem, deitado**, quando ele ainda está no
  disco: o corte vertical jogou fora os lados do quadro. Sem a origem (um upload
  que a limpeza levou, ou um vídeo de IA), entra o próprio corte em pé, no meio,
  sobre uma cópia desfocada dele — e a tela avisa antes. Entre um corte e outro,
  meio segundo de escuro. A legenda é a transcrição dos projetos, no tempo da
  compilação, e o crédito das fontes Creative Commons entra na descrição sozinho,
  uma linha por fonte. Nada ali gasta cota: é o ffmpeg do computador.
- **O envio ao YouTube é em partes, com retomada.** Um episódio tem centenas de
  megabytes, e um envio só, numa conexão de casa, perde tudo na primeira queda.
  Acima de 64 MB ele sobe em pedaços de 8 MB; se a conexão cai, o programa
  pergunta ao YouTube até onde chegou e continua dali. O Short continua como
  sempre foi.
- **Tudo é projeto como os outros**: fila, barra, cancelar, a lista de projetos
  ("episódio 2", "compilação de 4 cortes"), a agenda e a publicação. O episódio
  que parou continua de onde parou, como o vídeo de IA; a compilação que parou é
  montada de novo inteira, pelo botão "montar de novo". Os cortes de um projeto
  viram um vídeo longo pelo atalho "vídeo longo com estes cortes", na tela dele.
- **O site novo com o programa antigo não cria vídeo longo**: um programa de
  antes da 7.8 faria um vídeo curto no lugar do episódio, sem erro nenhum. A tela
  pergunta antes e manda atualizar.

**Onde a 7.8 está (30-set-2026).** O "pronto quando" roda nos testes: o episódio
de ponta a ponta com o ffmpeg de verdade — deitado, com capítulos e a narração em
blocos, e o bloco pronto guardado quando a voz acaba no meio
(`tests/test_criar_video.py`) —, a história que continua e o pedido pela API
(`tests/test_criacao_no_motor.py`), a compilação de ponta a ponta da origem e do
corte em pé (`tests/test_compilacao.py`, `tests/test_compilacao_no_motor.py`) e o
envio em partes com as quedas imitadas (`tests/test_youtube_api.py`). As telas
foram conferidas com o motor de verdade e um banco de demonstração (o canal da
Lulu com duas histórias, uma parada no episódio 1; um canal de podcast com um
projeto com a origem no disco e outro sem), no computador e no celular — e a
compilação do passeio foi montada de verdade pelo motor: 4 cortes de 2 projetos,
50 segundos em 1920x1080, com os quatro capítulos. Na conferência saíram quatro
acertos: o pacote do dia do TikTok e do Instagram levava os vídeos longos (e o
botão contava com eles); o canal inteiro aparecia como destino do vídeo longo
com "TikTok, Instagram, YouTube" no nome; a linha do estilo na tela do episódio
dizia a duração do vídeo curto ("60 s · 8 cenas") ao lado da escolhida; e "1
cortes". Na revisão do código saiu um quinto: um corte re-editado no editor
(com um pedaço do meio tirado) entrava na compilação inteiro, com o que a pessoa
tinha tirado — agora ele entra pelos trechos da edição. **O que falta ver no PC do autor**: um episódio de verdade (as imagens
deitadas, a voz em blocos sem emenda aparente, a história continuando no
episódio 2) e uma compilação subindo para o YouTube com os capítulos na barra do
vídeo. O roteiro está no `COMO-EXECUTAR.md`, Passo 16.

### 7.9 — Frota de aparelhos (phone farm)

A tela do vídeo que o autor mandou (ver "As ferramentas de referência"):
aparelhos ao vivo, o estado de cada um, os apps e as contas, a automação e a
agenda. **O Instagram é a plataforma que ela mais vai usar.** Entra por último e
separada, porque é a parte de maior risco (ver Limites).

- Os aparelhos, físicos ou em nuvem, e o estado de cada um.
- As contas de cada aparelho e o que ele posta, com limite por conta.
- Um driver de publicação por aparelho, atrás da mesma interface (`publishers/`)
  e com a mesma trava do ADR-010: risco acima de zero, então nunca entra na
  cascata automática sem a conta ter pedido.

**Pronto quando:** um celular, pelo cabo ou pela rede, entra na frota pela tela;
a conta do Instagram de um canal passa a morar nele; o corte do canal abre no
app do celular com a legenda pronta, e a pessoa só toca em publicar — ou, numa
conta que consentiu, depois de a pessoa ensinar o caminho e um ensaio passar, o
próprio motor toca, dentro do limite do dia; e o painel mostra o que cada
aparelho fez, com a tela de cada passo.

**Andamento:**

| Parte | O quê | Situação |
|---|---|---|
| 7.9a | pesquisa: falar com os aparelhos e o que as plataformas permitem (ADR-016) | feita (1-out) |
| 7.9b | motor: o cliente do adb e o estado de cada aparelho | feita (1-out) |
| 7.9c | motor: as tabelas da frota, ligar a frota, os aparelhos e as contas com limite | feita (1-out) |
| 7.9d | motor: o driver do aparelho — entregar, e o automático com consentimento, ensino e ensaio | feita (1-out) |
| 7.9e | painel: a página Frota | feita (1-out) |
| 7.9f | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (1-out) |

**Como a frota ficou, e por quê (o ADR-016 tem o levantamento):**

- **Nasce desligada, e ligar pede que a pessoa leia os limites.** Eles ficam na
  página depois de ligada, embaixo dos aparelhos.
- **O programa fala com o celular pelo adb**, a ferramenta oficial do Google para
  desenvolvedor de Android, que a pessoa instala uma vez no Windows
  (`winget install --id Google.PlatformTools`). Pelo cabo, pela rede de casa
  (com o pareamento por código do Android 11 em diante) ou um celular em nuvem,
  que é só um endereço. No Docker, quem liga o adb é o `atalhos\celulares.bat`;
  no ajudante, ele liga sozinho.
- **O padrão é entregar.** O corte vai para a galeria do celular e o app abre com
  ele, na tela de postar — o que o "compartilhar" da galeria faria. A legenda
  fica na fila do painel e num arquivo no celular. Quem toca em publicar é a
  pessoa, que depois marca "já publiquei" com o link, como no pacote do dia.
- **O automático é conta por conta, com três travas.** A pessoa consente na hora
  de ligar (a frase diz que a plataforma pode punir a conta); ensina o caminho
  uma vez, clicando na tela do celular que aparece no painel — no campo da
  legenda o motor digita, e no botão de publicar ela marca sem tocar —; e um
  ensaio refaz tudo com um vídeo de teste e para antes de publicar. Sem o ensaio
  passando, o vídeo só é entregue. O app atualizou? Volta a entregar até ser
  ensinado e ensaiado de novo.
- **O que não é o esperado para, e o motor nunca toca às cegas.** Um botão que
  não aparece, uma janela que ninguém ensinou, o celular bloqueado: ele guarda a
  tela, devolve o teclado de antes e deixa o corte esperando a pessoa. Se depois
  do toque de publicar aparece uma janela, a tela diz "confira no app se saiu".
- **Limite por conta**: 3 posts por dia de padrão e no máximo 15 — o teto da via
  oficial do TikTok, a mais apertada das três. Vale também para a entrega.
- **Um celular, uma conta por app.** Trocar de conta dentro do app seria mais um
  toque às cegas, e postar na conta errada é pior que não postar.
- **A legenda com acento e emoji pede o teclado ADBKeyBoard** no celular da frota:
  o comando de digitar do Android não escreve nenhum dos dois. O motor o liga só
  durante o post e devolve o teclado de antes.
- **O que cada aparelho fez fica guardado com a tela de cada passo** (as últimas
  50 vezes de cada um): é a resposta para "por que não saiu?".
- **O que a frota não faz, de propósito**: criar ou entrar em contas; curtir,
  seguir, comentar ou "aquecer" conta; mudar a identidade do celular, proxy ou VPN
  por aparelho, GPS falso; imitar gente (toque sorteado, digitar devagar);
  resolver captcha. É o "Limites" deste plano.

**Onde a 7.9 está (1-out-2026).** O "pronto quando" roda nos testes contra um
servidor de adb de mentira, que fala o protocolo de verdade, e um celular
simulado com as telas do Instagram: o cliente do adb (`tests/test_adb_cliente.py`),
o estado e a tela do aparelho (`tests/test_frota_aparelho.py`), o ensino e o
roteiro — com a janela que ninguém ensinou e o botão noutro idioma
(`tests/test_frota_roteiro.py`) —, o caminho inteiro pela API do motor (ligar,
pôr o celular, ligar a conta, ensinar, ensaiar, consentir, publicar, o limite, o
celular bloqueado, o vizinho que não vê nada: `tests/test_frota.py`), a porta do
consentimento na cascata (`tests/test_publishers.py`) e as regras da tela no
`node` contra as do motor (`tests/test_painel_da_frota.py`). As telas foram
conferidas com o motor de verdade falando com esse adb de mentira, no computador
e no celular: ligar a frota, pôr dois celulares (um pelo cabo, um pela rede),
ligar a conta do Instagram, ensinar os três passos clicando na imagem, ensaiar,
consentir o automático e publicar — e o histórico mostrou as quatro telas do
post. Na conferência saíram dois acertos: as mensagens do motor chegavam à tela
sem acento ("botao", "nao"), e o resultado do ensaio repetia "passou" ao lado da
etiqueta que já dizia isso. **O que falta ver no PC do autor**: tudo o que
depende de um celular de verdade — o adb do Windows alcançado pelo Docker (o
`host.docker.internal`, que veio de relato de terceiros e é a primeira coisa a
confirmar; se não alcançar, o ajudante fala com o adb direto), a tela do
Instagram lida pelo `uiautomator`, o ADBKeyBoard digitando a legenda e um post de
verdade. O roteiro está no `COMO-EXECUTAR.md`, Passo 18.

### 7.10 — Mais plataformas

- **Plataformas chinesas** (Douyin, Kuaishou, Bilibili, Xiaohongshu): o autor as
  vê como "área inexplorada, com possibilidade de ganho". A porta fica aberta
  pela mesma interface. Cada uma tem as exigências dela; em geral, cadastro com
  número de telefone chinês.
- Toda plataforma nova é uma migração (`accounts.platform` tem CHECK) e um
  driver.

**Pronto quando:** um canal ganha conta no Douyin, no Kuaishou, no Bilibili ou no
Xiaohongshu como ganha no TikTok; o corte vai para a fila dela como um galho do
canal; o pacote do dia dela traz o corte com o texto pronto para colar, em
chinês e nas regras do app; e o "já publiquei" aceita o link como o app o copia.

**Andamento:**

| Parte | O quê | Situação |
|---|---|---|
| 7.10a | pesquisa: o que cada uma exige de quem é de fora e o que oferece para publicar e medir (ADR-015) | feita (30-set) |
| 7.10b | motor: as quatro no banco, nos links, na legenda de cada app, no pacote do dia e na tradução do texto | feita (30-set) |
| 7.10c | painel: contas, ícones, o cartão de cada uma, o pacote e o "já publiquei" | feita (30-set) |
| 7.10d | conferir as telas no computador (1280 px) e no celular (390 px), docs, CI | feita (30-set) |

**Como as chinesas ficaram, e por quê (o ADR-015 tem o levantamento):**

- **Publicam pelo pacote do dia, como o Instagram da 7.3d.** Nenhuma das quatro
  deixa uma pessoa de fora da China publicar pela API: no Douyin isso é para site
  de governo e de imprensa, no Kuaishou para empresa, no Bilibili pede
  identidade de desenvolvedor e revisão lá, e o Xiaohongshu não tem. E robô no
  navegador é o que custa a conta (ADR-010). Então o programa entrega o corte e
  o texto prontos, e quem aperta publicar é a pessoa.
- **O texto do post vai em chinês.** É em chinês que esses apps buscam e
  recomendam: um título em português no Douyin não é achado por ninguém. O
  título, a descrição e as tags de cada corte são traduzidos pelas IAs grátis do
  programa, uma vez só (a tradução fica guardada na pasta do projeto). Se nenhuma
  IA responder, vai o texto original, e o LEIA-ME do pacote diz qual corte ficou
  assim.
- **Cada app com as regras dele.** No Douyin, no Bilibili e no Xiaohongshu o
  título tem campo próprio: a primeira linha do arquivo é o título, já no tamanho
  do campo (30, 80 e 20 caracteres), e o resto é o texto. As tags do Bilibili têm
  campo próprio também, e saem na última linha, sem `#`. O Kuaishou tem um campo
  só, como o TikTok. O LEIA-ME diz em que campo vai cada parte.
- **O vídeo em si continua como foi feito**: a fala e a legenda no idioma
  original. Legenda em chinês é a função "Idiomas" desta lista, e o autor a
  deixou para depois (1-out-2026). Ela não pede reconstruir a imagem: uma fonte
  com os caracteres chineses na pasta `fonts/` do projeto basta, chamada pelo
  nome no estilo da legenda (ver o ADR-015).
- **O "já publiquei" aceita o que o app copia.** O botão "compartilhar" dos apps
  chineses copia um texto com o link no meio ("复制打开抖音... https://v.douyin.com/...");
  o programa tira o link de dentro, segue o link curto até o endereço do vídeo e
  guarda. O Kwai (o Kuaishou de fora da China, grande no Brasil) e o bilibili.tv
  são outras plataformas: o link deles é recusado, para não guardar o post
  errado.
- **O vídeo longo vai também ao Bilibili**, que é o do vídeo longo e deitado na
  China. Nas outras três ele não vai, como no TikTok.
- **Nenhuma é medida.** Os números do post ficam dentro do app: as análises e o
  "a IA acertou?" contam só as plataformas medidas, e a conta chinesa não aparece
  no aviso de "conecte para medir".
- **O site novo com o programa antigo não oferece as chinesas.** O motor diz as
  plataformas que conhece (`/api/contas`), e um programa de antes da 7.10
  recusaria a conta do Douyin ao salvar.

**Onde a 7.10 está (30-set-2026).** O "pronto quando" roda nos testes: a conta
de cada uma aceita pelo banco (inclusive o banco antigo, pelo acerto do boot), os
links de cada app como eles chegam (o endereço, o link curto, o texto do
"compartilhar"), a legenda nas regras de cada campo, a tradução em lotes e
guardada, o subprocesso de verdade sem nenhuma IA, e o pacote e a publicação
pela API do motor (`tests/test_plataformas_chinesas.py`); e as regras do painel
no `node` contra as do motor (`tests/test_painel_das_plataformas.py`). As telas
foram conferidas com o motor de verdade e um banco de demonstração (o canal
"Gatos da Neve" com YouTube, TikTok, Douyin, Bilibili e Xiaohongshu, e uma conta
solta do Kuaishou), no computador e no celular; os cortes foram publicados no
canal inteiro pela porta do painel, e o pacote do Bilibili saiu com dois cortes em
chinês e o terceiro marcado no LEIA-ME, porque a IA de mentira da demonstração
não respondeu. Na conferência saíram três acertos: a lista de contas vinha na
ordem do banco (com sete plataformas, embaralhada); o "a IA acertou?" contava o
post do Bilibili como um corte que ainda não tinha números; e o LEIA-ME do
Bilibili chamava as tags de hashtags. Na revisão do código, um quarto: o painel
de análises pediria para "conectar para medir" as contas chinesas, e não há o
que conectar. **O que falta ver no PC do autor**: a tradução com
as chaves de IA dele, e — se ele tiver conta em alguma delas — um post de verdade
com o texto colado do pacote. O roteiro está no `COMO-EXECUTAR.md`, Passo 17.

## Funções essenciais que ainda não estavam na lista

| Função | Por quê | Onde entra |
|---|---|---|
| Caixa de aprovação | "ver antes de postar", ligada ou não por canal | 7.5 (a escolha já existe na 7.1) |
| Identidade do canal | avatar, cores, fonte, template de legenda, gancho, voz, idioma | lugar na 7.1; uso na 7.2 e na 7.7 |
| Origem e licença de cada vídeo | responde reclamação e strike, e gera o crédito | 7.5 |
| Saúde das contas | conexão expirando, cota, reclamação, strike, queda de alcance | 7.3 e 7.4 |
| Avisos no celular | "postou", "falhou", "strike", "motor desligado" | 7.3 |
| Uso e limites | quanto das IAs grátis, da cota do YouTube e do disco já foi hoje | tela na 7.1; números na 7.3 |
| Não repetir | mesma fonte ou corte, nem entre canais | 7.5 |
| Primeiros passos | quem instala pela primeira vez: chaves, conta, primeiro canal | 7.1 |
| Calendário | todos os canais num calendário | lugar na 7.1; completo na 7.5 |
| Idiomas | o mesmo canal em outro idioma, com legenda traduzida ou voz | depois da 7.7; o texto do post já sai em chinês para as plataformas chinesas (7.10), e a legenda em chinês o autor deixou para depois (1-out-2026) |
| Ideias por nicho | tendências e temas, para a busca e para a IA | 7.5 e 7.7 |
| Música e efeitos sem direitos | biblioteca para os vídeos | 7.2 e 7.7 |
| Modelos de canal | receitas prontas por nicho, para começar um canal rápido | 7.5 |
| Editor com linha do tempo | ajuste fino antes de postar, no estilo do CapCut | depois da 7.2 |
| Backup | projetos e banco moram no PC; uma cópia automática | depois da 7.5 |
| Teste de título e miniatura | comparar duas versões | depois da 7.4 |

## Portas que dependem de fora

Levam semanas e dependem de cada pessoa, que usa o próprio cadastro. O autor não
tem pressa: "a gente vai fazendo aos poucos".

- **YouTube**
  - O projeto no Google Cloud com a tela de consentimento **em produção**. Em
    "teste", a conexão expira a cada 7 dias. Em produção sem verificação aparece
    o aviso de "app não verificado", aceitável para uso próprio.
  - A **auditoria** da API do YouTube. Sem ela, todo vídeo enviado pela API fica
    privado, e é também por ela que se pede mais cota.
- **TikTok**: o app de desenvolvedor, que pede site, termos de uso e política de
  privacidade (o site no Cloudflare pode hospedar as duas páginas), e a auditoria
  do Content Posting API.
- **O preço do cadastro por pessoa:** cada um faz a própria auditoria para postar
  em público pela API. Até lá, posta à mão com o pacote do dia. Se um dia o autor
  quiser um cadastro só para todos (o dele, com a cota dividida), é um valor
  padrão nas Configurações, não um redesenho.

## Limites — o que o plano não faz

- **Direitos autorais.** Cada canal usa vídeo com licença (Creative Commons ou
  domínio público), próprio, com autorização ou criado por IA.
  - Corte de filme e série sem direitos leva reclamação do Content ID (a receita
    vai para o dono) ou strike; três strikes apagam o canal.
  - Os jeitos "específicos" de postar que circulam (espelhar, dar zoom, mudar o
    tom) são truques para escapar da detecção, e não entram no programa.
- **Monetização.** Canal feito só de cortes de vídeos de outros, mesmo com
  licença, costuma ser recusado pelo YouTube como "conteúdo reutilizado", a não
  ser que a edição acrescente algo: comentário, narração, montagem própria. As
  receitas precisam poder acrescentar.
- **Crianças.** Conteúdo infantil no YouTube é marcado "feito para crianças" por
  lei (COPPA), o que desliga comentários e anúncio personalizado. Não é opcional.
- **A frota.** As plataformas proíbem conta falsa e publicação automatizada em
  massa, e a punição é a conta: "a conta é o ativo" (ADR-010). A frota entra
  opt-in, isolada e com limite por conta. Não entra ferramenta para enganar a
  detecção: criar contas em massa, disfarçar aparelho ou rede.

## Decisões do autor (26-set-2026)

| Pergunta | Decisão |
|---|---|
| Um cadastro de app (Google, TikTok) para todos ou um por pessoa? | **Um por pessoa**, como as chaves de IA |
| Post atrasado (PC desligado na hora)? | **Posta quando o PC voltar, com trava**: nunca vários de uma vez |
| Canal novo espera aprovação? | **Configuração do canal**; quem escolhe é quem usa |
| Instagram? | **Entra junto** com YouTube e TikTok, mais simples; é o que a frota mais vai usar |
| Qualidade dos cortes (7.2)? | **Fica para o fim**, depois da estrutura; a lista vem do autor |
| Estilo do vídeo de IA? | **Configurado por quem usa e salvo no canal**; nada automático pelo nicho |
| Prazo das auditorias? | Sem pressa; "quando eu quiser dividir o trabalho, a gente divide" |
| Quando testar no PC dele? | **No final**, tudo junto: as etapas seguem sem esperar o teste de cada uma (26-set-2026, ao fechar a 7.3) |
| Legenda em chinês no vídeo? | **Por enquanto, não**; o texto do post já vai em chinês (1-out-2026, ao fechar a 7.10) |
| Mais plataformas (o Kwai e outras)? | **Por enquanto, só essas**; o autor vai fazer uma pesquisa de mercado antes de escolher outras (1-out-2026) |

O "canal como centro" virou o ADR-014 em 30-set-2026, com a estrutura de pé (7.1 a
7.8); o 013 foi para a pesquisa de mídia grátis da 7.7, e o 015 para as
plataformas chinesas da 7.10.

## Ordem e dependências

Ordem combinada: **a 7.1 primeiro**. Depois dela, a próxima se confirma com o
autor ao fim de cada etapa. A qualidade dos cortes (7.2) fica para o fim, e ele
pode puxá-la antes quando mandar a lista.

```
7.1 estrutura ──┬── 7.3 contas e publicar ──┬── 7.4 análises
                │                           ├── 7.5 automação ── 7.6 séries
                │                           └── 7.10 mais plataformas
                ├── 7.7 vídeo de IA curto ── 7.8 vídeo longo
                └── 7.2 qualidade (no fim, ou antes se o autor pedir)
7.9 frota: depois da 7.3, e por último entre as grandes
```

Em paralelo, sem depender de nada disto: o teste do ajudante no PC do amigo do
autor (Fase 6.2).

## As ferramentas de referência

O autor mandou duas, em vídeos do Instagram. O que elas mostram, para não
depender das imagens:

**Brevidy (brevidy.pro), um plugin do Premiere para cortar lives.** "Gostei do
fluxo e da ideia; a interface parece um editor de vídeo do CapCut."
- Painel *Autocut*: créditos e uso no topo; formato (9x16), layout (*AutoCrop*),
  modelo de IA (quem usa escolhe), preset de legenda (*Beast*), qualidade da
  transcrição (*Best*) e ações marcáveis: remover silêncios, sugerir emojis,
  sugerir cortes e sugerir destaques.
- Carregamento: "Loading..." com a etapa embaixo ("Rendering audio...",
  "Rendering video...", "Applying AutoCrop to timeline...") e, por cima, uma
  janelinha por corte com o título dele, a porcentagem e o tempo restante.
- No fim, os cortes prontos na linha do tempo (umas 18 de uma live).
- Onde entra: 7.2 (qualidade e a tela de carregamento) e o editor com linha do
  tempo.

**Um painel de frota de celulares ("Fleet Control Center").** "POV: you post
10.000 reels a day."
- Menu lateral: Control Center, Analytics, Automation, Schedule, Store, App
  management, Account management, Router, Billing, Settings, Help & docs.
- "Live devices 858 / 1000 online" e uma grade de celulares, cada um com os
  ícones de Instagram, TikTok, Facebook e YouTube.
- Onde entra: 7.9, com os limites da seção "Limites". Do menu dele vieram também
  ideias para o nosso: análises, automação e agenda como seções próprias, e
  "Help & docs" como a nossa Ajuda.

## Registro das conversas

As palavras do autor, levemente limpas da transcrição de voz, na ordem em que
vieram.

**25-set-2026, primeira mensagem sobre a Fase 7:**
- "Eu quero estruturar o aplicativo primeiro."
- "Eu quero que você possa conectar várias contas: uma sessão de YouTube, onde
  você vai conectar várias contas do YouTube, e uma sessão de TikTok (...) essa
  sessão vai servir para você publicar as coisas e criar também conteúdos."
- "Por mais que a gente não consiga automatizar agora, já deixar pronto essa
  automatização."
- O canal infantil como exemplo: "só de eu deixar o PC ligado (...) ele buscar
  vídeos no YouTube (...) de 50 minutos, e faz corte (...) edita, e ele posta
  (...) em horários específicos, uma, três horas da tarde."
- "Cliquei em criar vídeo de IA, ele vai criar um roteiro (...) e vai literalmente
  criar o vídeo (...) uma historinha, uma novelinha de inteligência artificial,
  (...) um minuto de vídeo, e vai postar. E isso só nesse canal; nos outros
  canais vai ser outras coisas."
- "Clipes longos divididos em partes (...) pego uma live, colo, e ele divide em
  vários clipes de um minuto (...) parte 1, parte 2. (...) Tudo isso que eu falo é
  sem direito autoral."
- "Eu quero que essa ferramenta seja a ferramenta suprema. Ela tenha a junção de
  todas as outras ferramentas da internet."

**25-set-2026, segunda mensagem:**
- Nichos: infantil, acidentes, fatos desconhecidos, finanças. "São duas coisas
  separadas: os cortes, que utilizam vídeos reais, e os que criam vídeos (...) e
  isso tudo vai ter em cada conta."
- "Tem que ter o ícone do YouTube, do TikTok, o ícone do canal; eu quero sempre
  que tenha um visual bem bonito."
- Canal ligado: "adicionando uma opção de linkar, então todo vídeo que a gente
  criar para esse canal vai lançar o mesmo conteúdo, tanto pro YouTube quanto pro
  TikTok (...) vai virar uma ramificação, dois galhos (...) e depois você gerencia
  cada um individualmente."
- Análises: "o analytic para esse canal no YouTube, o analytic para esse canal no
  TikTok e o analytic geral desse canal (...) três telas diferentes."
- "Tem que ter opção de criação de vídeo longo (...) mas isso fica mais pra
  frente."
- A frota: "quero que inclua uma sessão para isso (...) é algo mais pra frente";
  e o Instagram "é mais outro tipo de coisa (...) bom pra phone farm".
- "Estrutura o plano; a gente precisa estruturar primeiro, não precisa fazer
  funcionar (...) agora a gente precisa estruturar para depois ir fazendo."

**26-set-2026, as decisões** (a tabela acima), e:
- "Não coloca estilo 3D no infantil automaticamente (...) alguma funcionalidade
  que configura um estilo de criação, para que ele não fuja desse estilo (...) vai
  ficar salvo naquele projeto, daquela sessão de criação de vídeo de IA."
- "Espero que você tenha anotado tudo isso num documento, para que, mesmo que a
  gente perca esse chat, esteja salvo tudo o que a gente conversou." É este
  documento.

**26-set-2026, ao fechar a 7.3:** "vou testar só no final pode seguir para a
7.4". O roteiro de teste de cada etapa continua sendo escrito no
`COMO-EXECUTAR.md` à medida que ela fica pronta, para que o teste do final seja
seguir a lista, e não lembrar o que mudou.

**26-set-2026, ao fechar a 7.4:** "prossiga", para a 7.5. No meio da 7.5d a
sessão bateu no limite de uso, e a mensagem seguinte foi "prossiga para fase 4":
lido como seguir com a quarta parte da 7.5 (a 7.5d, o painel), que estava em
andamento; a Fase 4 do plano original (auth e multiusuário) já estava pronta.
Se era outra coisa, é só dizer.

**27-set-2026, ao fechar a 7.5:** "ainda não vou testar, siga para o próximo
passo" — a 7.6, as séries em partes. O pedido dela é o da primeira mensagem
("pego uma live, colo, e ele divide em vários clipes de um minuto (...) parte 1,
parte 2"), e o teste continua sendo o do final, pelo roteiro do
`COMO-EXECUTAR.md`.

**27-set-2026, ao fechar a 7.6:** "siga para o proximo passo" — a 7.7, o vídeo
curto criado por IA, pelo pedido da primeira mensagem ("vai criar um roteiro
(...) e vai literalmente criar o vídeo (...) uma historinha, uma novelinha de
inteligência artificial, (...) um minuto de vídeo, e vai postar") e pela decisão
de 26-set sobre o estilo salvo no canal. Depois vieram só pedidos de "continue":
a etapa seguiu sem mudança de rumo, e o teste continua sendo o do final.

**29-set-2026, ao fechar a 7.7:** "siga para o proximo passo" — a 7.8, o vídeo
longo, pelo pedido de 26-set ("tem que ter opção de criação de vídeo longo") e
pelo que o cartão do Criar já prometia: "montado a partir dos cortes ou de um
roteiro". Os dois caminhos entraram. Depois, de novo só "continue": nenhuma
decisão nova do autor nesta etapa, e o teste continua sendo o do final, pelo
Passo 16 do `COMO-EXECUTAR.md`.

**30-set-2026, ao fechar a 7.8:** "siga o proximo passo" — a 7.10, as
plataformas chinesas, pela ordem do plano: a 7.9 (a frota) é a última entre as
grandes, e a 7.2 espera a lista do autor. Nenhuma decisão nova do autor nesta
etapa; duas perguntas ficam para ele, e nenhuma trava o que foi feito:

- **Legenda em chinês no vídeo** (a função "Idiomas"): pede uma fonte com os
  caracteres chineses. Sem ela, o texto do post vai em chinês e o vídeo, como foi
  feito. (Aqui dizia "reconstruir a imagem, uns 40 minutos", e estava errado: a
  fonte entra pela pasta `fonts/` do projeto. Ver 1-out-2026.)
- **O Kwai**, o Kuaishou de fora da China, é grande no Brasil e não pede
  telefone chinês. Ele não entrou (não estava no pedido), mas entraria como as
  plataformas de fora, se o autor quiser.

**1-out-2026, ao fechar a 7.10:** a resposta às duas perguntas.
- "Por enquanto, não precisa de colocar a legenda chinesa."
- Sobre os 40 minutos: "o que eu quero saber é 40 minutos o tempo todo para o
  usuário ou 40 minutos uma vez só para a gente". Nem um nem outro: reconstruir a
  imagem nunca é por vídeo — quando é preciso, é uma vez por computador, pelo
  `reconstruir.bat` (e quem usa o ajudante nem tem imagem). E, conferindo o
  código para responder, a legenda em chinês nem pediria isso: as fontes da
  legenda vêm da pasta `fonts/` do projeto. A frase dos 40 minutos estava errada
  no ADR-015, aqui e no `CLAUDE.md`, e foi corrigida.
- "Depois eu vou fazer uma pesquisa de mercado sobre quais outras plataformas a
  gente pode implementar. Por enquanto, deixa essas." O Kwai fica de fora até lá.
- "Pode seguir para o próximo" — a 7.9, a frota de aparelhos, a última entre as
  grandes.

**1-out-2026, ao fechar a 7.9:** a frota seguiu o plano e os limites dele sem
pergunta nova ao autor — no meio, só o limite de uso, e "continue". Nenhuma
decisão nova nesta etapa. Das grandes, falta a 7.2 (a qualidade dos cortes), que
espera a lista dele; e o teste no PC dele continua sendo o do final, tudo junto,
com o Passo 18 do `COMO-EXECUTAR.md` para a frota.

## Fontes

As regras externas foram conferidas em 25-set-2026:

- YouTube, envio e cota: [Videos: insert](https://developers.google.com/youtube/v3/docs/videos/insert),
  [Revision History](https://developers.google.com/youtube/v3/revision_history),
  [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost),
  [Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
- TikTok, postagem e métricas: [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines),
  [Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
  [List Videos](https://developers.tiktok.com/docs/en/tiktok-api-v1-video-list).
- YouTube, busca e licença (7.5): [Search: list](https://developers.google.com/youtube/v3/docs/search/list)
  (o parâmetro `videoLicense=creativeCommon`) e o recurso [Videos](https://developers.google.com/youtube/v3/docs/videos)
  (o campo `status.license`); o texto das licenças que o crédito cita,
  [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) e
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), com a troca de uma
  para a outra no YouTube pesquisada em 26-set-2026 (anotada em `licencas.py`).
- A frota (7.9, conferidas em 1-out-2026): o [adb](https://developer.android.com/tools/adb)
  e o [pacote do Google](https://developer.android.com/tools/releases/platform-tools)
  que a pessoa instala; o teclado [ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard);
  e o teto de publicação do Instagram pela API,
  [100 posts em 24 horas](https://developers.facebook.com/docs/instagram-platform/content-publishing/).
  O do TikTok, "por volta de 15 posts por dia por criador, somando todos os
  apps", está nas [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines),
  acima.
