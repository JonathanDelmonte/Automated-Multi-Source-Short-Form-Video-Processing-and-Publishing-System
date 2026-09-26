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
- **As integrações**: YouTube, TikTok e Instagram; outras plataformas depois. É
  por elas que o conteúdo sai e as métricas voltam.

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
Frota             aparelhos (phone farm) — em breve
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
| Publicação → publicar e fila | **Criar** e **Publicados** de cada canal, e a **Agenda** |
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
| `source_licenses` | — | **nova** (7.5): licença e crédito da fonte (autor, licença, link) |
| `recipes` | — | **nova** (7.5): tipo, fonte, edição, agenda, aprovação |
| `candidates` | — | **nova** (7.5): vídeos que a busca achou, com a licença, esperando decisão |
| `creation_styles`, `creations` | — | **novas** (7.7): o estilo de criação salvo, e o roteiro, as cenas e os arquivos de cada vídeo de IA |
| `devices` | — | **nova** (7.9): os aparelhos da frota |

O projeto também guarda o canal na própria pasta (`.canal`, ao lado do `.tenant`):
a lista de projetos vem do disco, e o banco falha aberto.

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

**Pronto quando:** o canal infantil, com o PC ligado e ninguém mexendo, acha um
vídeo com licença, corta, espera a aprovação (ou não, se o canal estiver assim) e
posta nos horários dele, com o crédito na descrição.

### 7.6 — Séries em partes

Um vídeo longo (uma live, um filme sem direitos autorais) vira Parte 1, 2, 3...,
em blocos de cerca de um minuto, na ordem.

- "Parte N" no vídeo e no título, postadas em sequência.
- No YouTube, uma playlist por série.
- Reaproveita o corte por tempo e a live em blocos (bloco 1.5).

**Pronto quando:** uma live de 1 hora vira uma série agendada, na ordem, sem
buraco e sem repetição.

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

### 7.8 — Vídeo longo

A mesma máquina da 7.7, em episódios mais longos para o YouTube: uma novelinha de
vários minutos. Depende de a 7.7 estar de pé.

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

### 7.10 — Mais plataformas

- **Plataformas chinesas** (Douyin, Kuaishou, Bilibili, Xiaohongshu): o autor as
  vê como "área inexplorada, com possibilidade de ganho". A porta fica aberta
  pela mesma interface. Cada uma tem as exigências dela; em geral, cadastro com
  número de telefone chinês.
- Toda plataforma nova é uma migração (`accounts.platform` tem CHECK) e um
  driver.

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
| Idiomas | o mesmo canal em outro idioma, com legenda traduzida ou voz | depois da 7.7 |
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

Quando a estrutura estiver de pé, o "canal como centro" vira o ADR-013.

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

## Fontes

As regras externas foram conferidas em 25-set-2026:

- YouTube, envio e cota: [Videos: insert](https://developers.google.com/youtube/v3/docs/videos/insert),
  [Revision History](https://developers.google.com/youtube/v3/revision_history),
  [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost),
  [Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
- TikTok, postagem e métricas: [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines),
  [Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
  [List Videos](https://developers.tiktok.com/docs/en/tiktok-api-v1-video-list).
