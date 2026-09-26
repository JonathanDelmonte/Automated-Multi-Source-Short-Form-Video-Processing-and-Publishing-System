// O "Conectar YouTube" do lado da tela (etapa 7.3). O consentimento é feito
// pelo motor (`conexoes.py`); aqui ficam as regras que a tela precisa, sem
// React, para o teste do painel rodar este arquivo no `node` de verdade.

// A origem pela qual ESTE navegador fala com o motor. É para lá que o Google
// devolve a pessoa depois do consentimento:
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

// O Google só devolve para esta máquina: `localhost`, `127.0.0.1` ou `[::1]`.
// O painel aberto de outro aparelho da rede não conecta, e a tela diz isso
// ANTES do clique, em vez de mandar a pessoa ao Google para voltar com erro.
export function voltaPossivel(origem) {
  try {
    const { protocol, hostname } = new URL(origem);
    return protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]', '::1'].includes(hostname);
  } catch {
    return false;
  }
}

// A volta do Google chegou a ESTA página? (Só acontece no painel do Docker:
// no site, quem recebe é o motor.)
export function ehVoltaDoGoogle(busca) {
  const q = new URLSearchParams(busca || '');
  return q.has('state') && (q.has('code') || q.has('error'));
}

export function dadosDaVolta(busca) {
  const q = new URLSearchParams(busca || '');
  return { state: q.get('state'), code: q.get('code'), error: q.get('error') };
}

// As frases de cada código que o motor devolve. É a tela que fala português
// com acento; o motor manda o código.
export const MENSAGENS = {
  sem_aplicativo: 'Falta o cadastro do aplicativo do Google. Cole o ID do cliente e a chave secreta em Configurações → aplicativos.',
  volta: 'O Google só devolve a conexão para este computador. Abra o painel aqui, em http://localhost, e conecte de novo.',
  plataforma: 'Por enquanto só dá para conectar contas do YouTube por aqui.',
  tipo: 'Pedido de conexão inválido.',
  expirou: 'Esse pedido de conexão venceu ou já foi usado. Clique em conectar de novo.',
  recusada: 'A conexão foi cancelada na tela do Google. Nada mudou.',
  troca: 'O Google não aceitou o código de volta. Clique em conectar de novo.',
  sem_refresh: 'O Google respondeu sem a autorização permanente. Tire o acesso do Virtu Clips em myaccount.google.com/permissions e conecte de novo.',
  gravar: 'O programa não conseguiu guardar a conexão neste computador.',
  cliente: 'O Google não reconheceu esse ID do cliente ou essa chave secreta. Confira se copiou os dois do mesmo cliente.',
  formato: 'Isso não parece um ID do cliente do Google (termina em .apps.googleusercontent.com).',
  vazio: 'Preencha os dois campos.',
};

export function mensagemDe(codigo, padrao = 'Não deu para conectar. Tente de novo.') {
  return MENSAGENS[codigo] || padrao;
}

// O cadastro do aplicativo do Google: os tipos de erro que o motor devolve no
// `POST /api/aplicativos`, em frases.
export const MENSAGENS_DO_CADASTRO = {
  ...MENSAGENS,
  tipo: 'Esse cliente é do tipo "Aplicativo da Web". Crie um do tipo "App para computador" — é o que aceita a volta para este computador.',
};
