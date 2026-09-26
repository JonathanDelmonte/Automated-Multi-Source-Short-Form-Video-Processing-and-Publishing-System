// As plataformas onde um canal publica, na ordem em que aparecem na tela -- a
// mesma do motor (`publish_queue.PLATAFORMAS`), que devolve as contas de um
// canal nessa ordem. YouTube e TikTok são as principais; o Instagram entra
// junto, "menos trabalhado", e é o que a frota de aparelhos mais vai usar
// (decisão do autor, 26-set-2026).
export const PLATAFORMAS = {
  youtube: { nome: 'YouTube', cor: '#ff0033' },
  tiktok: { nome: 'TikTok', cor: '#fe2c55' },
  instagram: { nome: 'Instagram', cor: '#d62976' },
};

export const ORDEM_DAS_PLATAFORMAS = ['youtube', 'tiktok', 'instagram'];

// O que cada driver de publicação faz, numa linha. É o que responde "por que
// este corte não subiu sozinho?" sem obrigar ninguém a ler o plano.
export const DRIVERS = {
  'youtube-api': 'sobe sozinho pela API oficial',
  aggregator: 'agregador (não configurado)',
  manual: 'fila manual: o corte e a legenda ficam prontos',
  browser: 'navegador (desligado por decisão)',
};
