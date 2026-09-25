# Plano da plataforma — canais, criação e automação

**Data:** 25 de setembro de 2026
**Status:** proposta, para discutir com o autor antes de começar
**Relação com os outros planos:** o `PLANO-DE-ACAO.md` cobre as Fases 0 a 6, o
motor que baixa, transcreve, corta, publica e mede. Este cobre a Fase 7 em
diante: a plataforma em volta dele, organizada por **canal**.

---

## O que estamos construindo

Um **sistema com um painel** — os dois:

- **O motor**, no computador de quem usa (Docker ou ajudante): baixa, transcreve,
  corta, cria, publica e, a partir desta fase, roda as automações sozinho
  enquanto o PC estiver ligado.
- **O painel**, o site no Cloudflare: onde se cria, acompanha e decide. Ele não
  processa nada; conversa com o motor da própria máquina.
- **As integrações**: YouTube e TikTok primeiro; Instagram e outras plataformas
  depois. É por elas que o conteúdo sai e as métricas voltam.

No mercado, o nome disso é *plataforma de automação de conteúdo*: estúdio de
criação e central de publicação no mesmo lugar. O pedido do autor é que ela
junte o que hoje está espalhado em ferramentas separadas: corte com IA, vídeo
gerado por IA e gestão de contas em rede social.

## A ideia em uma página

- **O canal é o centro, não o vídeo.** Um canal tem nicho (infantil, finanças,
  curiosidades, acidentes...), identidade visual e **contas ligadas**. O mesmo
  canal no YouTube e no TikTok é o caso mais comum.
- **Cada canal cria de duas formas, separadas:**
  - **cortes de vídeo real**: o que o programa faz hoje, a partir de um link, de
    uma live ou de uma busca por tema;
  - **vídeo criado por IA**: roteiro, cenas, voz e montagem, no estilo do nicho
    (boneco 3D no infantil, motion em finanças). O estilo sai do nicho: a IA
    propõe e o autor muda se quiser.
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
      Visão geral   números, próximos posts, avisos do canal
      Criar         cortes de vídeo · vídeo de IA · série em partes
      Automação     a receita do canal
      Agenda        o que vai ao ar e quando, por plataforma
      Publicados    cada galho, com status e link
      Análises      Geral · YouTube · TikTok
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

| Tabela | Hoje | O que muda |
|---|---|---|
| `channels` | — | **nova** (7.1): nome, nicho, avatar, idioma, identidade (template de legenda, cores, voz), estilo de IA, modo de aprovação |
| `accounts` | conta de plataforma (YouTube, TikTok, Instagram) | ganha `channel_id`, anulável: conta solta continua valendo |
| `jobs` | um vídeo processado | ganha `channel_id` e, na 7.5, `recipe_id`. Nulos = feito à mão, sem canal |
| `sources` | de onde veio o vídeo | ganha **licença e crédito**: autor, licença e link |
| `publications` | um corte numa conta | nada: **já é o galho**. A unicidade (corte, conta) é o que impede postar duas vezes |
| `metrics` | série de views e retenção por publicação | nada; as análises agregam por conta e por canal |
| `recipes` | — | **nova** (7.5): tipo, fonte, edição, agenda, aprovação |
| `candidates` | — | **nova** (7.5): vídeos que a busca achou, com a licença, esperando decisão |
| `creations` | — | **nova** (7.7): roteiro, cenas e arquivos de um vídeo de IA |
| `devices` | — | **nova** (7.9): os aparelhos da frota |

Na migração, cada conta que já existe vira um canal com uma conta só. Nada do que
está cadastrado se perde.

## As fases

A ordem proposta é a da numeração. As portas externas (ver adiante) levam
semanas e dependem do autor, então vale abri-las durante a 7.1.

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
  funcionar. Endereço com `#` porque o site é estático no Cloudflare.
- **Quebrar o `App.jsx`** (1.963 linhas) em páginas. Ele fica com o esqueleto:
  navegação, sessão e avisos.
- **Canais**: criar, editar e apagar; avatar (enviado ou gerado); nicho; ligar as
  contas já cadastradas.
- **A página do canal** com as sete abas. Onde há dado, o dado (projetos e
  publicados do canal); onde não há, o "em breve" dizendo o que vai fazer.
- **Criar**: o fluxo de hoje, com o canal escolhido no começo, ou nenhum.
- **Visual**: ícones de YouTube, TikTok e Instagram, e o avatar do canal em todo
  lugar que o nomeia, sobre os tokens e primitivos que a Parte D do
  `OPORTUNIDADES.md` manda preservar.
- **Dados**: `channels`, e `channel_id` em `accounts` e `jobs`, com a migração
  das contas existentes.

**Pronto quando:** dá para criar o "Canal infantil" ligado a uma conta do YouTube
e a uma do TikTok, entrar nele, criar cortes pelo fluxo de hoje com o canal já
escolhido, e ver os projetos dele no canal e em Projetos. Todo o resto do mapa tem
lugar visível, marcado "em breve". E nada do que funciona hoje para de funcionar:
cortar sem canal, publicar, agendar, YouTube Studio, chaves, atualizar pelo botão.

### 7.2 — Qualidade dos cortes

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

- **"Conectar YouTube" pelo site.** Hoje é `python youtube_oauth.py` no terminal.
  O motor faz o mesmo fluxo quando o botão pede: o retorno vem para a própria
  máquina, que é o que o Google aceita para programa instalado. São dois
  consentimentos, como hoje, um para publicar e outro para ler métricas. Duas
  credenciais pequenas em vez de uma grande (bloco 5.1).
- **A cota nova do YouTube.** Hoje são 100 envios por dia numa cota só de envio,
  e 100 buscas por dia noutra. O `quota.py` e o teto do agendador ainda seguram
  em 6 envios por dia, pela regra antiga de 1.600 unidades por envio. Corrigir os
  dois, e o teste que congela o número.
- **TikTok.** Um app de desenvolvedor do TikTok com o Content Posting API. Até a
  auditoria dele, o post pela API sai **só privado**, e no máximo 5 contas por
  dia; o pacote do dia continua sendo o caminho para postar público.
- **"Já publiquei" pede o link.** Hoje o botão da fila manual não guarda o link
  do post, e sem ele o que se posta à mão nunca é medido.
- **O galho por plataforma.** Num canal ligado, o corte pronto vira uma
  publicação por conta. Cada uma tem título, descrição e hashtags da plataforma
  dela, e horário próprio.
- **Instagram**: entra aqui ou na 7.10, decisão em aberto.

**Pronto quando:** o primeiro corte sai do programa, de verdade, para um canal
ligado, com os dois galhos rastreados. O do YouTube vai pela API; o do TikTok vai
pela API ou à mão, com o link registrado. Em modo privado primeiro, conferido no
app de cada plataforma; a ressalva da Fase 3 continua valendo.

### 7.4 — Análises por canal

- **YouTube**: visualizações e retenção, pela API de Analytics que o coletor já
  usa.
- **TikTok**: visualizações, curtidas, comentários e compartilhamentos dos vídeos
  da própria conta, pela API de exibição. Retenção, a documentação não mostra.
- **Três telas no canal ligado**: Geral (a soma), YouTube e TikTok. Em Análises,
  no menu, todos os canais lado a lado.
- **Início** com os números do dia.
- **A calibração começa a ter dado** (bloco 5.2), e o horário de postar deixa de
  ser palpite: o ADR-007 previa calibrar com retenção medida.

**Pronto quando:** um canal ligado mostra as três telas com números coletados das
duas plataformas, e o relatório de calibração conta os cortes medidos.

### 7.5 — Automação por canal

- **A receita** diz quatro coisas:
  - de onde vêm os vídeos: link fixo, busca por tema, live da Twitch ou pasta;
  - como editar: template, duração, layout e idioma;
  - quando postar: janelas por canal, com o jitter do ADR-007;
  - se espera aprovação.
- **Busca de vídeos com licença.** O YouTube marca os vídeos Creative Commons, e
  a busca filtra só esses: pela API (100 buscas por dia) ou pelo yt-dlp,
  conferindo a licença de cada vídeo antes de baixar. O crédito do autor vai na
  descrição, como a licença exige, e a origem fica registrada em `sources`.
- **Caixa de entrada de fontes** e **caixa de aprovação** de cortes. Automação que
  posta sem ninguém ver precisa de um lugar para ver quando se quer.
- **"Feito para crianças"** marcado sozinho em todo envio de canal infantil: é
  exigência do YouTube pela COPPA, a lei americana.
- **Não repetir**: a mesma fonte ou o mesmo corte não vai duas vezes, nem entre
  canais.
- **O motor ligado.** Para rodar sozinho, o motor tem de subir com o Windows: o
  ajudante já faz isso; no Docker, o Docker Desktop precisa iniciar com o
  Windows. Falta decidir o que fazer com o post cuja hora passou com o PC
  desligado.

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
- **O estilo sai do nicho**: boneco 3D para histórias infantis, motion para
  finanças, narração com imagens para curiosidades. A IA propõe, o autor muda.
- **Motion já tem motor aqui.** O Remotion, renderizador que o projeto já tem em
  container no Docker, desenha animação a partir de dados: a IA escreve a cena e
  ele anima, grátis e local. O ajudante não o leva hoje (`empacotar.FORA`), e
  isso entra na conta.
- **O resto começa com uma pesquisa**, como a do ADR-011: o que há de grátis no
  mês para imagem, vídeo e voz. Modelo de vídeo por API (Veo, Kling, Runway) é
  pago; o caminho grátis é montar, ou rodar um modelo aberto na placa, devagar.
- **Personagem consistente** entre cenas e episódios é o problema difícil do
  infantil, e é ele que decide a ferramenta.

**Pronto quando:** o canal de finanças gera sozinho um vídeo de um minuto sobre
"o que é renda fixa" (roteiro, animação, voz e legenda) sem nenhum serviço pago.

### 7.8 — Vídeo longo

A mesma máquina da 7.7, em episódios mais longos para o YouTube: uma novelinha de
vários minutos. Depende de a 7.7 estar de pé.

### 7.9 — Frota de aparelhos (phone farm)

A tela do vídeo que o autor mandou: aparelhos ao vivo, o estado de cada um, os
apps e as contas, a automação e a agenda. Entra por último e separada, porque é a
parte de maior risco (ver Limites).

- Os aparelhos, físicos ou em nuvem, e o estado de cada um.
- As contas de cada aparelho e o que ele posta, com limite por conta.
- Um driver de publicação por aparelho, atrás da mesma interface (`publishers/`)
  e com a mesma trava do ADR-010: risco acima de zero, então nunca entra na
  cascata automática sem a conta ter pedido.

### 7.10 — Mais plataformas

- **Instagram (Reels)**: API oficial para contas profissionais; serve também à
  frota.
- **Plataformas chinesas** (Douyin, Kuaishou, Bilibili, Xiaohongshu): a porta fica
  aberta pela mesma interface. Cada uma tem as exigências dela; em geral, cadastro
  com número de telefone chinês.
- Toda plataforma nova é uma migração (`accounts.platform` tem CHECK) e um
  driver.

## Funções essenciais que ainda não estavam na lista

| Função | Por quê | Onde entra |
|---|---|---|
| Caixa de aprovação | automação que posta sem ninguém ver precisa de um "ver antes" opcional por canal | 7.5 |
| Identidade do canal | avatar, cores, fonte, template de legenda, gancho, voz, idioma | lugar na 7.1; uso na 7.2 e na 7.7 |
| Origem e licença de cada vídeo | responde reclamação e strike, e gera o crédito | 7.5 (a 7.1 já guarda o link) |
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

Levam semanas e dependem do autor, então vale abrir cedo.

- **YouTube**
  - O projeto no Google Cloud com a tela de consentimento **em produção**. Em
    "teste", a conexão expira a cada 7 dias. Em produção sem verificação aparece
    o aviso de "app não verificado", aceitável para uso próprio.
  - A **auditoria** da API do YouTube. Sem ela, todo vídeo enviado pela API fica
    privado, e é também por ela que se pede mais cota.
- **TikTok**: o app de desenvolvedor, que pede site, termos de uso e política de
  privacidade (o site no Cloudflare pode hospedar as duas páginas), e a auditoria
  do Content Posting API.
- **Decisão:** um projeto do Google e um app do TikTok para todos que usam o
  programa (os do autor, com a cota dividida entre todos), ou um por pessoa.

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

## Decisões em aberto

1. Um projeto do Google e um app do TikTok para todos, ou um por pessoa?
2. Post atrasado (PC desligado na hora): postar quando o motor voltar, ou passar
   para a próxima janela?
3. Canal novo nasce esperando aprovação? A proposta é que sim, até o autor
   confiar na receita.
4. Instagram na 7.3 ou só na 7.10?
5. A lista de qualidade da 7.2, que o autor vai mandar.

Quando a estrutura for aprovada, o "canal como centro" vira o ADR-013.

## Ordem e dependências

```
7.1 estrutura ──┬── 7.2 qualidade
                ├── 7.3 contas e publicar ──┬── 7.4 análises
                │                           ├── 7.5 automação ── 7.6 séries
                │                           └── 7.10 mais plataformas
                └── 7.7 vídeo de IA curto ── 7.8 vídeo longo
7.9 frota: por último
```

Em paralelo, sem depender de nada disto: o teste do ajudante no PC do amigo do
autor (Fase 6.2).

## Fontes

As regras externas foram conferidas em 25-set-2026:

- YouTube, envio e cota: [Videos: insert](https://developers.google.com/youtube/v3/docs/videos/insert),
  [Revision History](https://developers.google.com/youtube/v3/revision_history),
  [Quota Calculator](https://developers.google.com/youtube/v3/determine_quota_cost),
  [Quota and Compliance Audits](https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits).
- TikTok, postagem e métricas: [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines),
  [Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post),
  [List Videos](https://developers.tiktok.com/docs/en/tiktok-api-v1-video-list).
