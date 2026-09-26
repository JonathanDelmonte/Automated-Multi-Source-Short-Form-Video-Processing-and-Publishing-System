// A receita do canal na tela (etapa 7.5): as escolhas, os modelos por nicho e
// as frases. As regras de verdade moram no motor (`receitas.py`); aqui fica o
// que a tela precisa para desenhar e avisar antes do clique. Sem React, de
// propósito: o teste do painel roda este arquivo no `node` de verdade.

export const FONTES = [
  {
    id: 'busca',
    nome: 'busca por tema',
    texto: 'Acha vídeos com licença Creative Commons no YouTube e confere a licença de cada um antes de cortar.',
  },
  {
    id: 'links',
    nome: 'links',
    texto: 'Vídeos, playlists ou canais que você escolheu. Os vídeos novos de uma playlist entram sozinhos.',
  },
  {
    id: 'twitch',
    nome: 'live da Twitch',
    texto: 'Enquanto o canal está no ar, grava um bloco da live e corta.',
  },
  {
    id: 'pasta',
    nome: 'pasta',
    texto: 'Os vídeos que você puser na pasta do canal, neste computador.',
  },
];

export const DURACOES = [
  { id: 'longa', nome: 'mais de 20 min' },
  { id: 'media', nome: '4 a 20 min' },
  { id: 'qualquer', nome: 'qualquer' },
];

export const LAYOUTS = [
  { id: 'auto', nome: 'automático', texto: 'a IA escolhe por vídeo' },
  { id: 'none', nome: 'recorte simples', texto: 'só o enquadramento' },
  { id: 'split', nome: 'duas pessoas', texto: 'uma em cima da outra' },
  { id: 'screencast', nome: 'tela e pessoa', texto: 'a tela em cima' },
];

// A mesma do motor (`receitas.PADRAO`). O teste compara as duas.
export const RECEITA_PADRAO = {
  fonte: { tipo: 'busca', tema: '', duracao: 'longa', links: [], twitch: '' },
  edicao: {
    cortes_por_video: 5, duracao_min: 20, duracao_max: 60, layout: 'auto',
    legenda: true, gancho: true, template_id: null,
  },
  ritmo: { videos_por_dia: 1 },
  direitos: null,
};

// Modelos por nicho: um ponto de partida para começar um canal rápido (o
// plano: "receitas prontas por nicho"). NUNCA é aplicado sozinho -- o autor
// pediu que nada venha do nicho sem ele escolher (26-set-2026); a tela oferece
// o modelo com um botão, e a pessoa muda o que quiser.
export const MODELOS = [
  {
    id: 'infantil', palavras: ['infantil', 'crianca', 'criancas', 'kids', 'desenho', 'desenhos', 'bebe'],
    nome: 'infantil',
    temas: ['desenho animado infantil', 'histórias para crianças', 'animação curta infantil'],
    fonte: { duracao: 'longa' },
    edicao: { cortes_por_video: 4, duracao_min: 25, duracao_max: 60 },
  },
  {
    id: 'filmes', palavras: ['filme', 'filmes', 'serie', 'series', 'cinema'],
    nome: 'filmes e séries',
    temas: ['filme de domínio público', 'curta-metragem', 'animação independente'],
    fonte: { duracao: 'longa' },
    edicao: { cortes_por_video: 6, duracao_min: 30, duracao_max: 90 },
  },
  {
    id: 'curiosidades', palavras: ['curiosidade', 'curiosidades', 'fatos', 'desconhecidos', 'ciencia'],
    nome: 'curiosidades e fatos',
    temas: ['documentário de ciência', 'curiosidades do mundo', 'história explicada'],
    fonte: { duracao: 'media' },
    edicao: { cortes_por_video: 5, duracao_min: 20, duracao_max: 50 },
  },
  {
    id: 'financas', palavras: ['financas', 'dinheiro', 'investimento', 'investimentos', 'economia'],
    nome: 'finanças',
    temas: ['educação financeira', 'investimentos para iniciantes', 'palestra de economia'],
    fonte: { duracao: 'longa' },
    edicao: { cortes_por_video: 5, duracao_min: 25, duracao_max: 60 },
  },
  {
    id: 'acidentes', palavras: ['acidente', 'acidentes', 'dashcam'],
    nome: 'acidentes',
    temas: ['câmera de carro', 'acidentes de trânsito educativo'],
    fonte: { duracao: 'media' },
    edicao: { cortes_por_video: 6, duracao_min: 15, duracao_max: 40 },
  },
  {
    id: 'podcasts', palavras: ['podcast', 'podcasts', 'entrevista', 'entrevistas'],
    nome: 'podcasts',
    temas: ['podcast entrevista', 'bate-papo', 'palestra'],
    fonte: { duracao: 'longa' },
    edicao: { cortes_por_video: 6, duracao_min: 30, duracao_max: 75 },
  },
];

function semAcento(texto) {
  return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

// O modelo que combina com o nicho do canal, ou null.
export function modeloDoNicho(nicho) {
  const palavras = new Set(semAcento(nicho).match(/[a-z]+/g) || []);
  return MODELOS.find((m) => m.palavras.some((p) => palavras.has(p))) || null;
}

// A receita com o modelo por cima: o tema vira o primeiro sugerido, a menos
// que a pessoa já tenha escrito um.
export function aplicarModelo(spec, modelo) {
  const base = spec || RECEITA_PADRAO;
  return {
    ...base,
    fonte: {
      ...base.fonte,
      ...modelo.fonte,
      tipo: 'busca',
      tema: base.fonte?.tema || modelo.temas[0],
    },
    edicao: { ...base.edicao, ...modelo.edicao },
  };
}

// Os links de um texto, um por linha (ou separados por espaço ou vírgula).
export function linksDoTexto(texto) {
  const vistos = [];
  for (const pedaco of String(texto || '').split(/[\s,]+/)) {
    const link = pedaco.trim();
    if (link && !vistos.includes(link)) vistos.push(link);
  }
  return vistos;
}

export const precisaDeDireitos = (spec) => (spec?.fonte?.tipo || 'busca') !== 'busca';

// O que falta para ligar, na mesma regra do motor (`receitas.pronta`), para a
// tela avisar antes do clique. O motor confere de novo.
export function faltaParaLigar(spec, direitosNaTela = false) {
  const fonte = spec?.fonte || {};
  if (fonte.tipo === 'busca' && !String(fonte.tema || '').trim()) return 'Escreva o tema da busca.';
  if (fonte.tipo === 'links' && !(fonte.links || []).length) return 'Cole pelo menos um link.';
  if (fonte.tipo === 'twitch' && !String(fonte.twitch || '').trim()) return 'Escreva o canal da Twitch.';
  if (precisaDeDireitos(spec) && !spec.direitos && !direitosNaTela) {
    return 'Confirme que você tem os direitos sobre esses vídeos.';
  }
  return null;
}

export const LICENCAS = {
  'cc-by': { texto: 'Creative Commons', tom: 'ok', dica: 'Licença livre, conferida no vídeo: pode reusar dando o crédito, que vai na descrição.' },
  'dominio-publico': { texto: 'domínio público', tom: 'ok', dica: 'Sem direitos autorais.' },
  youtube: { texto: 'licença padrão', tom: 'aviso', dica: 'A licença padrão do YouTube não permite reuso sem autorização.' },
  propria: { texto: 'seu', tom: 'neutro', dica: 'Você disse que o vídeo é seu.' },
  autorizada: { texto: 'com autorização', tom: 'neutro', dica: 'Você confirmou ter os direitos sobre este vídeo.' },
  desconhecida: { texto: 'licença não confirmada', tom: 'aviso', dica: 'A página do vídeo não mostrou a licença.' },
};

export const rotuloDaLicenca = (licenca) => LICENCAS[licenca] || LICENCAS.desconhecida;

export const STATUS_DOS_CANDIDATOS = {
  novo: { texto: 'na fila', tom: 'neutro' },
  escolhido: { texto: 'o próximo', tom: 'destaque' },
  processando: { texto: 'cortando', tom: 'destaque' },
  processado: { texto: 'cortado', tom: 'ok' },
  recusado: { texto: 'fora', tom: 'apagado' },
  repetido: { texto: 'já usado', tom: 'apagado' },
  falhou: { texto: 'falhou', tom: 'erro' },
};

export const rotuloDoCandidato = (status) => STATUS_DOS_CANDIDATOS[status] || { texto: status, tom: 'neutro' };

// A caixa de entrada em três montes: o que espera a vez, o que já foi
// cortado, e o que ficou de fora (com o motivo).
export function grupoDoCandidato(status) {
  if (status === 'novo' || status === 'escolhido') return 'fila';
  if (status === 'processando' || status === 'processado') return 'cortados';
  return 'fora';
}

// "25 min", "1 h 05", "45 s".
export function duracaoCurta(segundos) {
  const s = Number(segundos);
  if (!Number.isFinite(s) || s <= 0) return '';
  if (s < 60) return `${Math.round(s)} s`;
  const minutos = Math.round(s / 60);
  if (minutos < 60) return `${minutos} min`;
  const h = Math.floor(minutos / 60);
  return `${h} h ${String(minutos % 60).padStart(2, '0')}`;
}

// "11h, 15h e 19h".
export function janelasEmTexto(janelas) {
  const horas = (janelas || []).map((h) => `${h}h`);
  if (horas.length <= 1) return horas.join('');
  return `${horas.slice(0, -1).join(', ')} e ${horas[horas.length - 1]}`;
}

// O fuso deste navegador, como o motor guarda (`PUT /api/fuso`): o nome e a
// diferença para UTC agora, em minutos (positiva a leste).
export function fusoDoNavegador(agora = new Date()) {
  let nome = null;
  try {
    nome = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    nome = null;
  }
  return { nome: nome || 'UTC', offset_min: -agora.getTimezoneOffset() };
}

// "UTC−3", "UTC+1", "UTC".
export function rotuloDoOffset(minutos) {
  const m = Number(minutos) || 0;
  if (m === 0) return 'UTC';
  const sinal = m > 0 ? '+' : '−';
  const abs = Math.abs(m);
  const horas = Math.floor(abs / 60);
  const resto = abs % 60;
  return `UTC${sinal}${horas}${resto ? `:${String(resto).padStart(2, '0')}` : ''}`;
}
