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
//
// Numa série (7.6), a parte parada atrás de uma anterior que falhou (ou que
// ficou presa subindo) diz isso em vez da hora: a hora marcada já passou, e
// ela só sai quando a pessoa tentar de novo ou pular a de antes.
export function estadoDoGalho(p) {
  if (p.status === 'scheduled' && p.parada) {
    const motivo = p.parada.motivo === 'subindo' ? 'ficou presa subindo' : 'falhou';
    return { texto: `parada: a parte ${p.parada.parte} ${motivo}`, cor: 'text-danger' };
  }
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

function posicaoDaPlataforma(p) {
  const i = ORDEM_DAS_PLATAFORMAS.indexOf(p?.account?.platform);
  return i < 0 ? ORDEM_DAS_PLATAFORMAS.length : i;
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
      porCorte[chave] = { chave, clip: p.clip || {}, serie: p.serie || null, galhos: [] };
      grupos.push(porCorte[chave]);
    }
    porCorte[chave].galhos.push(p);
  }
  for (const grupo of grupos) grupo.galhos.sort((a, b) => posicaoDaPlataforma(a) - posicaoDaPlataforma(b));
  return grupos;
}

// A fila com cada série num item só (7.6). Uma série de 60 partes eram 60
// grupos, e a parte que falhou -- a única que pede alguém -- ficava no fim da
// página, depois de 57 linhas "parada: a parte 3 falhou". A série entra onde
// apareceu a primeira parte dela, com as partes em ordem e um resumo por conta
// (`resumoDaSerie`); os cortes soltos seguem como antes.
export function agruparNaFila(publicacoes, { filtrada = false } = {}) {
  const itens = [];
  const series = {};
  for (const grupo of agruparPorCorte(publicacoes)) {
    const id = grupo.serie?.id;
    if (!id) {
      itens.push({ tipo: 'corte', chave: grupo.chave, grupo });
      continue;
    }
    if (!series[id]) {
      series[id] = { tipo: 'serie', chave: `serie:${id}`, serie: grupo.serie, grupos: [] };
      itens.push(series[id]);
    }
    series[id].grupos.push(grupo);
  }
  for (const item of Object.values(series)) {
    item.grupos.sort((a, b) => (a.serie?.parte || 0) - (b.serie?.parte || 0));
    item.contas = resumoDaSerie(item.grupos, { filtrada });
  }
  return itens;
}

const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;

// O que cada conta de uma série está fazendo, na ordem das plataformas, com a
// parte que pede atenção (`foco`): a que falhou (tentar de novo ou pular), a
// que ficou subindo, a que espera a pessoa postar à mão. Sem nenhuma dessas, a
// próxima que sai, ou "todas publicadas".
//
// `filtrada`: a fila veio filtrada por estado (as abas Agenda e Publicados de
// um canal), e ali "todas publicadas" e "2 de 60" seriam mentira -- as outras
// partes só não estão na lista. Fica a contagem do que está nela. A "próxima"
// continua valendo: um filtro por estado traz todas as agendadas ou nenhuma.
export function resumoDaSerie(grupos, { filtrada = false } = {}) {
  const porConta = {};
  const contas = [];
  for (const grupo of grupos) {
    for (const p of grupo.galhos) {
      const id = p.account?.id || p.account_id || p.id;
      if (!porConta[id]) {
        porConta[id] = { chave: id, conta: p.account || {}, galhos: [] };
        contas.push(porConta[id]);
      }
      porConta[id].galhos.push(p);
    }
  }
  contas.sort((a, b) => posicaoDaPlataforma(a.galhos[0]) - posicaoDaPlataforma(b.galhos[0]));
  const parte = (p) => p.serie?.parte ?? 0;
  for (const c of contas) {
    const galhos = [...c.galhos].sort((a, b) => parte(a) - parte(b));
    const publicadas = galhos.filter((p) => p.status === 'published').length;
    const puladas = galhos.filter((p) => p.status === 'cancelled').length;
    const paradas = galhos.filter((p) => p.status === 'scheduled' && p.parada).length;
    const atras = paradas ? ` · ${plural(paradas, 'parada atrás dela', 'paradas atrás dela')}` : '';
    c.contagem = filtrada
      ? plural(galhos.length, 'parte', 'partes')
      : `${publicadas} de ${galhos.length} publicada${galhos.length === 1 ? '' : 's'}`;
    c.foco = null;
    const falhou = galhos.find((p) => p.status === 'failed');
    const subindo = galhos.find((p) => p.status === 'publishing');
    const suaVez = galhos.filter((p) => p.status === 'scheduled' && !p.scheduled_at);
    const parada = galhos.find((p) => p.status === 'scheduled' && p.parada);
    const proxima = galhos.find((p) => p.status === 'scheduled' && p.scheduled_at && !p.parada);
    if (falhou) {
      c.foco = falhou;
      c.texto = `a parte ${parte(falhou)} falhou${atras}`;
      c.cor = 'text-danger';
    } else if (subindo) {
      c.foco = subindo;
      c.texto = `a parte ${parte(subindo)} está subindo${atras}`;
      c.cor = 'text-brass';
    } else if (suaVez.length) {
      c.foco = suaVez[0];
      const mais = suaVez.length > 1 ? ` (e mais ${suaVez.length - 1})` : '';
      c.texto = `a parte ${parte(suaVez[0])} espera você postar${mais}`;
      c.cor = 'text-brass';
    } else if (parada) {
      // A que segura as outras não está nesta lista (filtrada por estado).
      c.texto = estadoDoGalho(parada).texto;
      c.cor = 'text-danger';
    } else if (proxima) {
      c.texto = `próxima: parte ${parte(proxima)} · ${quando(proxima.scheduled_at)}`;
      c.cor = 'text-ink2';
    } else if (filtrada) {
      c.texto = '';
      c.cor = 'text-muted';
    } else {
      c.texto = puladas ? `terminou · ${plural(puladas, 'pulada', 'puladas')}` : 'todas publicadas';
      c.cor = 'text-ok';
    }
  }
  return contas;
}

// O destino de uma publicação: um canal inteiro (um galho por conta ligada a
// ele) ou uma conta só. Vai no corpo como `channel_id` ou `account_id`, e o
// motor recusa os dois juntos.
export function corpoDoDestino(jobId, destino) {
  const [tipo, id] = (destino || '').split(':');
  if (!jobId || !id || (tipo !== 'canal' && tipo !== 'conta')) return null;
  return tipo === 'canal' ? { job_id: jobId, channel_id: id } : { job_id: jobId, account_id: id };
}

// O canal cuja agenda vale para um destino (7.5): o próprio canal, ou o canal
// a que a conta está ligada. Conta solta não tem canal, e ali valem as janelas
// da instalação -- é o que o motor faz ao agendar.
export function canalDoDestino(destino, contas) {
  const [tipo, id] = (destino || '').split(':');
  if (!id) return null;
  if (tipo === 'canal') return id;
  if (tipo !== 'conta') return null;
  return (contas || []).find((c) => c.id === id)?.channel_id || null;
}

// A agenda que o texto do "agendar" descreve. Com o canal, a dele (as janelas
// e o por-dia que ele escolheu); um motor de antes da 7.5 ignora o `canal` e
// responde a da instalação, que era a única que existia.
export function caminhoDaAgenda(canalId) {
  return canalId ? `/api/agenda?${new URLSearchParams({ canal: canalId })}` : '/api/agenda';
}

// As plataformas que o pacote do dia oferece: as das contas, na ordem de
// sempre -- ou as três, quando ainda não há conta (o pacote serve até sem
// conta nenhuma).
export function plataformasDoPacote(contas) {
  const tem = new Set((contas || []).map((c) => c.platform));
  const delas = ORDEM_DAS_PLATAFORMAS.filter((p) => tem.has(p));
  return delas.length ? delas : [...ORDEM_DAS_PLATAFORMAS];
}

// O endereço do pacote de um dia para uma plataforma. A legenda de cada corte
// é escrita para ela: no Instagram, com no máximo 5 hashtags (o limite do app
// desde dez-2025). Sem a plataforma, o motor responde o do YouTube -- era o
// único que o painel pedia até a 7.3d.
export function caminhoDoPacote(dia, plataforma) {
  const q = new URLSearchParams({ dia, plataforma: plataforma || 'youtube' });
  return `/api/publicacoes/pacote?${q}`;
}

// Quantos cortes vão no pacote de um dia para uma plataforma. O vídeo longo
// (7.8) só vai no do YouTube, e o motor conta por plataforma
// (`por_plataforma`); um motor de antes da 7.8 manda só o total.
export function cortesNoPacote(dia, plataforma) {
  const n = dia?.por_plataforma?.[plataforma || 'youtube'];
  return Number.isFinite(n) ? n : (Number(dia?.cortes) || 0);
}

// Os dias que têm pacote para a plataforma: um dia só com vídeo longo não tem
// pacote do TikTok nem do Instagram.
export function diasDoPacote(dias, plataforma) {
  return (dias || []).filter((d) => cortesNoPacote(d, plataforma) > 0);
}

// O vídeo longo (7.8) vai só para o YouTube: ele é horizontal, e o motor pula
// os galhos do TikTok e do Instagram (`app._fora_do_destino`, com a mesma lista
// em `app.PLATAFORMAS_DO_VIDEO_LONGO`; o teste compara as duas).
export const PLATAFORMAS_DO_VIDEO_LONGO = ['youtube'];

export function aceitaVideoLongo(conta) {
  return PLATAFORMAS_DO_VIDEO_LONGO.includes(conta?.platform);
}
