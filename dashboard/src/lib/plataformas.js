// As plataformas onde um canal publica, na ordem em que aparecem na tela -- a
// mesma do motor (`publish_queue.PLATAFORMAS`), que devolve as contas de um
// canal nessa ordem. YouTube e TikTok são as principais; o Instagram entra
// junto, "menos trabalhado", e é o que a frota de aparelhos mais vai usar
// (decisão do autor, 26-set-2026).
//
// `exemploDeLink` é o formato que o botão "copiar link" de cada app dá -- é o
// que aparece no campo do "já publiquei" (etapa 7.3).
export const PLATAFORMAS = {
  youtube: { nome: 'YouTube', cor: '#ff0033', exemploDeLink: 'https://youtube.com/shorts/…' },
  tiktok: { nome: 'TikTok', cor: '#fe2c55', exemploDeLink: 'https://vm.tiktok.com/…' },
  instagram: { nome: 'Instagram', cor: '#d62976', exemploDeLink: 'https://www.instagram.com/reel/…' },
};

export const ORDEM_DAS_PLATAFORMAS = ['youtube', 'tiktok', 'instagram'];

// O que cada driver de publicação faz, numa linha. É o que responde "por que
// este corte não subiu sozinho?" sem obrigar ninguém a ler o plano.
export const DRIVERS = {
  'youtube-api': 'sobe sozinho pela API oficial',
  'tiktok-api': 'sobe sozinho pela API do TikTok',
  aggregator: 'agregador (não configurado)',
  manual: 'fila manual: o corte e a legenda ficam prontos',
  browser: 'navegador (desligado por decisão)',
};
