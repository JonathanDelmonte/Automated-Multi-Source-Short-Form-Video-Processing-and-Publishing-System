// A compilação dos cortes no painel (etapa 7.8): um vídeo horizontal longo para
// o YouTube, feito dos cortes escolhidos, na ordem escolhida. As regras moram no
// motor (`compilacao.py`); aqui fica o que a tela precisa ANTES do clique -- o
// total, os limites e os capítulos que vão sair. Sem React, para o teste rodar
// no `node` e comparar com o motor.

export const TRECHOS = { min: 2, max: 60 };
export const DURACAO_MAX_S = 3600;
export const TITULO_MAX = 100;
export const DESCRICAO_MAX = 1500;
export const CAPITULO_MINIMO_S = 10;

// Um corte escolhido é `{jobId, clip, titulo, duracao_s}`; a chave dele é o par.
export const chaveDoCorte = (c) => `${c.jobId}:${c.clip}`;

export function duracaoTotal(escolhidos) {
  return (escolhidos || []).reduce((soma, c) => soma + (Number(c.duracao_s) || 0), 0);
}

// "m:ss" (ou "h:mm:ss"), como o YouTube escreve os capítulos.
export function tempo(segundos) {
  const total = Math.max(0, Math.floor(Number(segundos) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = String(total % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
}

// Os capítulos que vão sair, pela regra do motor (`capitulos.validos`): o
// primeiro em 0:00, o curto demais sai (o trecho dele fica com o anterior), e
// com menos de três não há lista -- o YouTube a ignoraria.
export function capitulosPrevistos(escolhidos) {
  const itens = [];
  let inicio = 0;
  for (const c of escolhidos || []) {
    const titulo = String(c.titulo || '').replace(/\s+/g, ' ').trim();
    if (titulo) itens.push([Math.floor(inicio), titulo]);
    inicio += Number(c.duracao_s) || 0;
  }
  const total = Math.floor(inicio);
  const saida = [];
  itens.forEach(([segundos, titulo], i) => {
    const comeco = saida.length ? segundos : 0;
    const fim = i + 1 < itens.length ? itens[i + 1][0] : total;
    if (fim - comeco >= CAPITULO_MINIMO_S) saida.push([comeco, titulo]);
  });
  return saida.length >= 3 ? saida : [];
}

// O que impede montar agora, ou null. As mesmas regras do `compilacao.planejar`.
export function porQueNaoMonta({ titulo, escolhidos }) {
  const n = (escolhidos || []).length;
  if (n < TRECHOS.min) return `Escolha pelo menos ${TRECHOS.min} cortes.`;
  if (n > TRECHOS.max) return `No máximo ${TRECHOS.max} cortes numa compilação.`;
  if (duracaoTotal(escolhidos) > DURACAO_MAX_S) {
    return `A compilação passaria de ${DURACAO_MAX_S / 60} minutos. Escolha menos cortes.`;
  }
  if (!String(titulo || '').trim()) return 'Dê um título: é o título do vídeo no YouTube.';
  return null;
}

// Tirar ou pôr um corte na lista (no fim), e mudar a ordem.
export function alternar(escolhidos, corte) {
  const chave = chaveDoCorte(corte);
  return escolhidos.some((c) => chaveDoCorte(c) === chave)
    ? escolhidos.filter((c) => chaveDoCorte(c) !== chave)
    : [...escolhidos, corte];
}

export function mover(escolhidos, indice, passo) {
  const destino = indice + passo;
  if (destino < 0 || destino >= escolhidos.length) return escolhidos;
  const lista = [...escolhidos];
  [lista[indice], lista[destino]] = [lista[destino], lista[indice]];
  return lista;
}

export function corpoDaCompilacao({ titulo, descricao, canalId, legenda, escolhidos }) {
  const corpo = {
    titulo: String(titulo || '').replace(/\s+/g, ' ').trim(),
    descricao: String(descricao || '').trim(),
    legenda: legenda || 'limpo',
    cortes: (escolhidos || []).map((c) => ({ job_id: c.jobId, clip: c.clip })),
  };
  if (canalId) corpo.channel_id = canalId;
  return corpo;
}
