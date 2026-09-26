// As regras da fila de publicações que a tela usa (etapa 7.3). Sem React, de
// propósito: o teste do painel roda este arquivo no `node` de verdade (e por
// isso o import leva a extensão, que o `node` exige e o Vite aceita).
import { ORDEM_DAS_PLATAFORMAS } from './plataformas.js';

const HORA = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' };

export function quando(iso) {
  if (!iso) return '';
  const data = new Date(iso);
  return Number.isNaN(data.getTime()) ? '' : data.toLocaleString(undefined, HORA);
}

// O estado de um galho, em palavras. `scheduled` cobre duas esperas: com data
// é a agendada (esperando a hora); sem data é a fila manual (esperando você).
export function estadoDoGalho(p) {
  switch (p.status) {
    case 'scheduled':
      return p.scheduled_at
        ? { texto: `agendado · ${quando(p.scheduled_at)}`, cor: 'text-ink2' }
        : { texto: 'esperando você postar', cor: 'text-brass' };
    case 'publishing':
      return { texto: 'subindo', cor: 'text-brass' };
    case 'published':
      return { texto: p.posted_at ? `publicado · ${quando(p.posted_at)}` : 'publicado', cor: 'text-ok' };
    case 'failed':
      return { texto: 'falhou', cor: 'text-danger' };
    case 'cancelled':
      return { texto: 'cancelado', cor: 'text-muted' };
    default:
      return { texto: p.status, cor: 'text-muted' };
  }
}

// Os galhos agrupados pelo corte, na ordem em que a fila chegou (a mais
// recente primeiro); dentro do corte, na ordem das plataformas -- a mesma em
// toda tela, para o olho achar o YouTube sempre no mesmo lugar.
export function agruparPorCorte(publicacoes) {
  const grupos = [];
  const porCorte = {};
  for (const p of publicacoes) {
    const chave = p.clip?.id || p.id;
    if (!porCorte[chave]) {
      porCorte[chave] = { chave, clip: p.clip || {}, galhos: [] };
      grupos.push(porCorte[chave]);
    }
    porCorte[chave].galhos.push(p);
  }
  const posicao = (p) => {
    const i = ORDEM_DAS_PLATAFORMAS.indexOf(p.account?.platform);
    return i < 0 ? ORDEM_DAS_PLATAFORMAS.length : i;
  };
  for (const grupo of grupos) grupo.galhos.sort((a, b) => posicao(a) - posicao(b));
  return grupos;
}

// O destino de uma publicação: um canal inteiro (um galho por conta ligada a
// ele) ou uma conta só. Vai no corpo como `channel_id` ou `account_id`, e o
// motor recusa os dois juntos.
export function corpoDoDestino(jobId, destino) {
  const [tipo, id] = (destino || '').split(':');
  if (!jobId || !id || (tipo !== 'canal' && tipo !== 'conta')) return null;
  return tipo === 'canal' ? { job_id: jobId, channel_id: id } : { job_id: jobId, account_id: id };
}
