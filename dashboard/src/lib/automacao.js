import { apiFetch } from './api';
import { fusoDoNavegador } from './receita.js';

// A automação por canal no painel (etapa 7.5): a receita, a caixa de entrada
// de fontes e a caixa de aprovação. As regras moram no motor (`automacao.py`);
// aqui só se fala com ele.
//
// Um motor de antes da 7.5 não tem as rotas: responde o 404 genérico do
// FastAPI ("Not Found") ou 405, e a tela diz para atualizar, como nos canais.
// O 404 do motor novo ("Canal nao encontrado") tem outra frase.

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
  if (res.status === 404 && data.detail === 'Not Found') {
    return { ok: false, status: 404, motorAntigo: true, erro: 'Atualize o programa para usar a automação.' };
  }
  if (res.status === 405) {
    return { ok: false, status: 405, motorAntigo: true, erro: 'Atualize o programa para usar a automação.' };
  }
  if (!res.ok) {
    const detalhe = typeof data.detail === 'string' ? data.detail : null;
    return { ok: false, status: res.status, erro: detalhe || 'Não deu certo. Tente de novo.' };
  }
  return { ok: true, data };
}

export const lerReceita = (canalId) => pedir(`/api/canais/${canalId}/receita`);

export const salvarReceita = (canalId, { spec, ativa, confirmarDireitos = false }) =>
  pedir(`/api/canais/${canalId}/receita`, 'PUT', {
    spec, ativa, confirmar_direitos: confirmarDireitos,
  });

export const buscarAgora = (canalId) => pedir(`/api/canais/${canalId}/receita/buscar`, 'POST');

export const rodarAgora = (canalId) => pedir(`/api/canais/${canalId}/receita/rodar`, 'POST');

export const listarCandidatos = (canalId) => pedir(`/api/canais/${canalId}/candidatos`);

export const decidirCandidato = (id, acao) => pedir(`/api/candidatos/${id}`, 'POST', { acao });

export const listarAprovacoes = (canalId) =>
  pedir(canalId ? `/api/aprovacoes?canal=${canalId}` : '/api/aprovacoes');

export const decidirAprovacoes = (ids, decisao) =>
  pedir('/api/aprovacoes/decidir', 'POST', { ids, decisao });

export const lerAutomacao = () => pedir('/api/automacao');

export const lerTemplates = () => pedir('/api/templates');

// O fuso deste navegador vai para o motor a cada vez que o painel abre: o
// agendador e a automação trabalham sem ninguém olhando, e no Docker o motor
// roda em UTC. Motor antigo responde 404/405, e isso não é erro para ninguém.
export async function mandarFuso() {
  const { nome, offset_min: offsetMin } = fusoDoNavegador();
  try {
    await apiFetch('/api/fuso', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome, offset_min: offsetMin }),
    });
  } catch {
    // Sem motor agora: o próximo carregamento manda.
  }
}
