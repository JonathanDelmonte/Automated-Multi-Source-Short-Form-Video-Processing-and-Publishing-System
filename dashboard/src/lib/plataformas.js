// As plataformas onde um canal publica, na ordem em que aparecem na tela -- a
// mesma do motor (`plataformas.py`), que devolve as contas de um canal nessa
// ordem. YouTube e TikTok são as principais; o Instagram entra junto, "menos
// trabalhado", e é o que a frota de aparelhos mais vai usar (decisão do autor,
// 26-set-2026). As chinesas entraram na etapa 7.10: publicam pelo pacote do
// dia, com o texto em chinês, e o programa não mede os números delas.
//
// `exemploDeLink` é o formato que o botão "copiar link" de cada app dá -- é o
// que aparece no campo do "já publiquei" (etapa 7.3). `exigencia` é o que o
// cadastro da conta pede, dito na hora de ligá-la ao canal.
export const PLATAFORMAS = {
  youtube: { nome: 'YouTube', cor: '#ff0033', exemploDeLink: 'https://youtube.com/shorts/…' },
  tiktok: { nome: 'TikTok', cor: '#fe2c55', exemploDeLink: 'https://vm.tiktok.com/…' },
  instagram: { nome: 'Instagram', cor: '#d62976', exemploDeLink: 'https://www.instagram.com/reel/…' },
  douyin: {
    nome: 'Douyin',
    cor: '#25f4ee',
    exemploDeLink: 'https://v.douyin.com/…',
    chinesa: true,
    exigencia: 'O Douyin é o app da China continental (o TikTok é o de fora). O cadastro pede '
      + 'telefone chinês e a verificação de nome real, e passaporte estrangeiro em geral não passa nela.',
  },
  kuaishou: {
    nome: 'Kuaishou',
    cor: '#ff4906',
    exemploDeLink: 'https://v.kuaishou.com/…',
    chinesa: true,
    exigencia: 'O Kuaishou pede telefone e a verificação de nome real, que aceita passaporte pela '
      + 'leitura do chip (NFC). O Kwai, que é dele e é grande no Brasil, é outro app: não é esta conta.',
  },
  bilibili: {
    nome: 'Bilibili',
    cor: '#00aeec',
    exemploDeLink: 'https://b23.tv/…',
    chinesa: true,
    exigencia: 'O Bilibili pede a verificação de nome real para publicar, e ela aceita passaporte. '
      + 'É o YouTube de lá: o vídeo longo e deitado também vai para ele.',
  },
  xiaohongshu: {
    nome: 'Xiaohongshu',
    cor: '#ff2442',
    exemploDeLink: 'http://xhslink.com/…',
    chinesa: true,
    exigencia: 'O Xiaohongshu (o RED) aceita telefone de fora da China, e a conta pessoal não pede '
      + 'documento.',
  },
};

// As três de sempre: o que um programa de antes da 7.10 conhece, e o pacote
// do dia sem conta nenhuma.
export const PRINCIPAIS = ['youtube', 'tiktok', 'instagram'];
export const CHINESAS = ['douyin', 'kuaishou', 'bilibili', 'xiaohongshu'];
export const ORDEM_DAS_PLATAFORMAS = [...PRINCIPAIS, ...CHINESAS];

// As que o programa mede (7.4): só elas ganham tela de análises.
export const MEDIDAS = ['youtube', 'tiktok', 'instagram'];

// As plataformas que o programa DESTE computador conhece, na ordem da tela. O
// site é publicado antes de o programa de quem usa ser atualizado: um programa
// de antes da 7.10 responde só as três de sempre (`/api/contas` e
// `/api/canais` mandam a lista), e oferecer o Douyin a ele só daria erro ao
// salvar. Sem a lista, as três.
export function plataformasDoMotor(lista) {
  if (!Array.isArray(lista) || !lista.length) return [...PRINCIPAIS];
  const conhecidas = ORDEM_DAS_PLATAFORMAS.filter((p) => lista.includes(p));
  return conhecidas.length ? conhecidas : [...PRINCIPAIS];
}

// O que cada driver de publicação faz, numa linha. É o que responde "por que
// este corte não subiu sozinho?" sem obrigar ninguém a ler o plano.
export const DRIVERS = {
  'youtube-api': 'sobe sozinho pela API oficial',
  'tiktok-api': 'sobe sozinho pela API do TikTok',
  aggregator: 'agregador (não configurado)',
  manual: 'fila manual: o corte e a legenda ficam prontos',
  browser: 'navegador (desligado por decisão)',
};
