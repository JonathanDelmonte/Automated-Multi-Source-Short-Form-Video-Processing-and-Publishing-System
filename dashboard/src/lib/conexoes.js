// O "conectar" de uma conta do lado da tela (etapa 7.3: YouTube na 7.3b,
// TikTok na 7.3c). O consentimento é feito pelo motor (`conexoes.py`); aqui
// ficam as regras que a tela precisa, sem React, para o teste do painel rodar
// este arquivo no `node` de verdade.

// A origem pela qual ESTE navegador fala com o motor. É para lá que o Google
// (ou o TikTok) devolve a pessoa depois do consentimento:
// - no site do Cloudflare, o motor é chamado direto (`http://localhost:8000`
//   ou `:8001`), e é o próprio motor que recebe a volta;
// - no painel do Docker, a API é relativa (o Vite repassa), e a volta chega ao
//   painel, que a manda ao motor (`concluirVolta`).
export function origemDoMotor(apiBase, origemDaPagina) {
  if (apiBase && /^https?:\/\//.test(apiBase)) {
    try {
      return new URL(apiBase).origin;
    } catch {
      return origemDaPagina;
    }
  }
  return origemDaPagina;
}

// A volta só vem para esta máquina: `localhost`, `127.0.0.1` ou `[::1]` no
// Google. O TikTok é mais estreito (Login Kit for Desktop): só `localhost` e
// `127.0.0.1`, e sempre com porta. O painel aberto de outro aparelho da rede
// não conecta, e a tela diz isso ANTES do clique, em vez de mandar a pessoa à
// tela de autorização para voltar com erro.
export function voltaPossivel(origem, plataforma = 'youtube') {
  try {
    const { protocol, hostname, port } = new URL(origem);
    if (protocol !== 'http:') return false;
    if (plataforma === 'tiktok') return ['localhost', '127.0.0.1'].includes(hostname) && port !== '';
    return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(hostname);
  } catch {
    return false;
  }
}

// Quem mostra a tela de autorização de cada plataforma.
const EMPRESA = { youtube: 'Google', google: 'Google', tiktok: 'TikTok' };

// O que cada plataforma conecta por aqui, e qual cadastro de aplicativo ela
// usa. Espelho de `conexoes.TIPOS_DE` / `APLICATIVO_DE` do motor (há teste
// comparando): o TikTok só publica por enquanto -- medir vem na 7.4.
export const TIPOS_DE = { youtube: ['publicar', 'medir'], tiktok: ['publicar'] };
export const APLICATIVO_DE = { youtube: 'google', tiktok: 'tiktok' };

// O que cada botão de conectar diz, por plataforma e tipo.
export const DESCRICAO_DOS_TIPOS = {
  youtube: {
    publicar: { ligado: 'publica sozinho', botao: 'conectar para publicar',
                dica: 'O programa sobe os cortes sozinho, na hora marcada. Não lê nem apaga nada.' },
    medir: { ligado: 'mede as visualizações', botao: 'conectar para medir',
             dica: 'O programa lê as visualizações e a retenção dos cortes. Não publica nada.' },
  },
  tiktok: {
    publicar: { ligado: 'publica sozinho', botao: 'conectar para publicar',
                dica: 'O programa sobe os cortes sozinho, na hora marcada, pelo Direct Post. Não lê nem apaga nada.' },
  },
};

// O cadastro que serve a esta conta, no programa deste computador:
// - 'pronto': colado (ou no .env), e o botão de conectar aparece;
// - 'falta': a pessoa ainda não colou, e a tela manda cadastrar;
// - 'motor-antigo': o programa não conhece esta plataforma -- o site é
//   publicado antes de o programa de quem usa ser atualizado, e mandar
//   cadastrar levaria a uma página sem o cartão dela;
// - null: ainda não se sabe (ou o programa é de antes da 7.3).
export function situacaoDoAplicativo(prontos, plataforma) {
  if (!prontos) return null;
  const chave = APLICATIVO_DE[plataforma];
  if (!chave || !(chave in prontos)) return 'motor-antigo';
  return prontos[chave] ? 'pronto' : 'falta';
}

export function empresaDe(plataforma) {
  return EMPRESA[plataforma] || 'Google';
}

// A volta do consentimento chegou a ESTA página? (Só acontece no painel do
// Docker: no site, quem recebe é o motor.) O nome é da 7.3b; o TikTok volta
// do mesmo jeito, com `state` e `code` (ou `error`).
export function ehVoltaDoGoogle(busca) {
  const q = new URLSearchParams(busca || '');
  return q.has('state') && (q.has('code') || q.has('error'));
}

export function dadosDaVolta(busca) {
  const q = new URLSearchParams(busca || '');
  return { state: q.get('state'), code: q.get('code'), error: q.get('error') };
}

// As frases de cada código que o motor devolve. É a tela que fala português
// com acento; o motor manda o código. `{empresa}` é quem mostrou a tela de
// autorização: o Google (YouTube) ou o TikTok.
export const MENSAGENS = {
  sem_aplicativo: 'Falta o cadastro do aplicativo. Cole os dados dele em Configurações → aplicativos.',
  volta: 'O {empresa} só devolve a conexão para este computador. Abra o painel aqui, em http://localhost, e conecte de novo.',
  plataforma: 'Por enquanto só dá para conectar contas do YouTube e do TikTok por aqui.',
  tipo: 'Pedido de conexão inválido.',
  expirou: 'Esse pedido de conexão venceu ou já foi usado. Clique em conectar de novo.',
  recusada: 'A conexão foi cancelada na tela do {empresa}. Nada mudou.',
  troca: 'O {empresa} não aceitou o código de volta. Clique em conectar de novo.',
  sem_refresh: 'O Google respondeu sem a autorização permanente. Tire o acesso do Virtu Clips em myaccount.google.com/permissions e conecte de novo.',
  escopo: 'A permissão de postar vídeos não veio. Conecte de novo e deixe marcada a opção de publicar.',
  gravar: 'O programa não conseguiu guardar a conexão neste computador.',
  cliente: 'O Google não reconheceu esse ID do cliente ou essa chave secreta. Confira se copiou os dois do mesmo cliente.',
  formato: 'Isso não parece um ID do cliente do Google (termina em .apps.googleusercontent.com).',
  vazio: 'Preencha os dois campos.',
};

// O que muda no TikTok: a página de permissões do Google não serve para ele.
const DO_TIKTOK = {
  sem_refresh: 'O TikTok respondeu sem a autorização permanente. Clique em conectar de novo.',
};

export function mensagemDe(codigo, { plataforma = 'youtube', padrao = 'Não deu para conectar. Tente de novo.' } = {}) {
  const texto = (plataforma === 'tiktok' && DO_TIKTOK[codigo]) || MENSAGENS[codigo];
  return texto ? texto.replace('{empresa}', EMPRESA[plataforma] || 'Google') : padrao;
}

// O cadastro do aplicativo: os tipos de erro que o motor devolve no
// `POST /api/aplicativos`, em frases.
export const MENSAGENS_DO_CADASTRO = {
  ...MENSAGENS,
  tipo: 'Esse cliente é do tipo "Aplicativo da Web". Crie um do tipo "App para computador" — é o que aceita a volta para este computador.',
};

// O formato errado diz QUAL campo e de qual console, que é o que a pessoa
// precisa para achar o valor certo.
const FORMATO = {
  'google.client_id': MENSAGENS.formato,
  'google.client_secret': 'Isso não parece a chave secreta do cliente do Google (hoje elas começam com GOCSPX-).',
  'tiktok.client_key': 'Isso não parece a client key do TikTok (letras e números, como aw… ou sbaw… no sandbox).',
  'tiktok.client_secret': 'Isso não parece o client secret do TikTok (fica logo abaixo da client key, no app).',
};

export function mensagemDoCadastro(codigo, { plataforma = 'google', campo } = {}) {
  if (codigo === 'formato' && FORMATO[`${plataforma}.${campo}`]) return FORMATO[`${plataforma}.${campo}`];
  return MENSAGENS_DO_CADASTRO[codigo] || 'Não deu para salvar.';
}
