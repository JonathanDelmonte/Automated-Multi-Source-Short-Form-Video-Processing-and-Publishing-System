// O índice de um corte (etapa 7.6). O resultado de um projeto só traz os cortes
// que renderizaram: com o terceiro de cinco falhando, a posição 2 da lista é o
// QUARTO corte. O motor pendura em cada um o `clip_index` (a posição dele no
// projeto), e é ele que vai nas chamadas -- legenda, gancho, edição, publicar.
// Pela posição, trocar a legenda do corte 3 mexia no 4; numa série, a Parte 4
// iria ao ar com o título da 3.
//
// Sem React, para o teste do painel rodar este arquivo no `node`.

export function indiceDoCorte(clip, posicao) {
  return Number.isInteger(clip?.clip_index) && clip.clip_index >= 0 ? clip.clip_index : posicao;
}

// O corte de um índice, ou undefined. Um motor de antes da 7.6 não manda o
// `clip_index`, e ali a posição É o índice.
export function corteDoIndice(clips, indice) {
  return (clips || []).find((clip, posicao) => indiceDoCorte(clip, posicao) === indice);
}

// A lista com o corte daquele índice trocado por `mudar(corte)`.
export function comCorteTrocado(clips, indice, mudar) {
  return (clips || []).map((clip, posicao) =>
    (indiceDoCorte(clip, posicao) === indice ? mudar(clip) : clip));
}

// Os cortes na ordem da tela: numa série, a ordem das partes; nos cortes, o
// melhor primeiro (a nota do modelo), empatando pela ordem do vídeo.
export function naOrdemDaTela(clips) {
  const lista = (clips || []).map((clip, posicao) => ({ clip, index: indiceDoCorte(clip, posicao) }));
  const serie = lista.some(({ clip }) => clip?.serie?.parte);
  return lista.sort((a, b) => {
    if (serie) return (a.clip?.serie?.parte ?? a.index) - (b.clip?.serie?.parte ?? b.index);
    const sa = Number.isFinite(a.clip?.predicted_score) ? a.clip.predicted_score : -1;
    const sb = Number.isFinite(b.clip?.predicted_score) ? b.clip.predicted_score : -1;
    return sb - sa || a.index - b.index;
  });
}
