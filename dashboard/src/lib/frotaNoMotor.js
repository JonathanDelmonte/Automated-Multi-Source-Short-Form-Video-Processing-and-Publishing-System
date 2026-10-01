import { apiFetch } from './api';

// A frota falando com o motor (etapa 7.9, ADR-016): ligar, os aparelhos, as
// contas de cada um, a tela ao vivo, o ensino e o ensaio. As frases de recusa
// vêm do motor (`frota.py`), já em português.
//
// Um motor de antes da 7.9 não tem as rotas: responde o 404 genérico do
// FastAPI ("Not Found") ou 405, e a tela diz para atualizar. O 409 de "o app
// tem mais de uma tela" chega com as opções (`detail.opcoes`).

async function pedir(caminho, metodo = 'GET', corpo) {
  let res;
  try {
    res = await apiFetch(caminho, {
      method: metodo,
      headers: corpo === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    return { ok: false, status: 0, erro: 'Não consegui falar com o programa neste computador.' };
  }
  const data = await res.json().catch(() => ({}));
  if ((res.status === 404 && data.detail === 'Not Found') || res.status === 405) {
    return { ok: false, status: res.status, motorAntigo: true,
             erro: 'Atualize o programa para usar a frota.' };
  }
  if (!res.ok) {
    const detalhe = data.detail;
    if (detalhe && typeof detalhe === 'object') {
      return { ok: false, status: res.status, erro: detalhe.mensagem || 'Não deu certo.',
               opcoes: detalhe.opcoes || [] };
    }
    return { ok: false, status: res.status,
             erro: typeof detalhe === 'string' && detalhe ? detalhe : 'Não deu certo. Tente de novo.' };
  }
  return { ok: true, data };
}

const doAparelho = (id, resto = '') => `/api/aparelhos/${id}${resto}`;

export const lerFrota = () => pedir('/api/frota');
export const ligarFrota = (ligada, entendi = false) => pedir('/api/frota', 'PUT', { ligada, entendi });

export const adicionarAparelho = (corpo) => pedir('/api/aparelhos', 'POST', corpo);
export const conectarNaRede = (endereco) => pedir('/api/aparelhos/conectar', 'POST', { endereco });
export const parear = (endereco, codigo) => pedir('/api/aparelhos/parear', 'POST', { endereco, codigo });

export const lerAparelho = (id, vivo = true) => pedir(doAparelho(id, vivo ? '' : '?vivo=0'));
export const editarAparelho = (id, campos) => pedir(doAparelho(id), 'PATCH', campos);
export const apagarAparelho = (id) => pedir(doAparelho(id), 'DELETE');

export const lerTela = (id) => pedir(doAparelho(id, '/tela'));
export const tocarNaTela = (id, x, y) => pedir(doAparelho(id, '/toque'), 'POST', { x, y });
export const apertarTecla = (id, tecla) => pedir(doAparelho(id, '/tecla'), 'POST', { tecla });

export const ligarConta = (id, corpo) => pedir(doAparelho(id, '/contas'), 'PUT', corpo);
export const soltarConta = (id, accountId) => pedir(doAparelho(id, `/contas/${accountId}`), 'DELETE');

export const lerFotos = (id, execucao) => pedir(doAparelho(id, `/execucoes/${execucao}`));

export const comecarEnsino = (id, plataforma, componente) =>
  pedir(doAparelho(id, '/ensino'), 'POST', { plataforma, componente: componente || null });
export const lerEnsino = (id) => pedir(doAparelho(id, '/ensino'));
export const acaoNoEnsino = (id, acao, corpo = {}) => pedir(doAparelho(id, `/ensino/${acao}`), 'POST', corpo);
export const cancelarEnsino = (id) => pedir(doAparelho(id, '/ensino'), 'DELETE');

export const ensaiar = (id, plataforma) => pedir(doAparelho(id, '/ensaio'), 'POST', { plataforma });
export const apagarRoteiro = (id, plataforma) => pedir(doAparelho(id, `/roteiros/${plataforma}`), 'DELETE');
