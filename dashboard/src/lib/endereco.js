// A parte pura do endereço das telas (`rota.js`): ler e montar, sem React e
// sem `window` -- é o que deixa o teste rodar no `node` puro, sem as
// dependências do painel instaladas (tests/test_painel_da_plataforma.py).

function decodificar(parte) {
  try {
    return decodeURIComponent(parte);
  } catch {
    return parte;
  }
}

// `#/canais/abc/agenda?x=1` -> { partes: ['canais', 'abc', 'agenda'], busca }.
// O `#app` das versões antigas (o link da marca) e qualquer endereço que não
// é tela nenhuma caem no início -- quem decide isso é o App, pelas partes.
export function lerRota(hash = '') {
  const bruto = (hash || '').replace(/^#\/?/, '');
  const [caminho, consulta = ''] = bruto.split('?');
  return {
    partes: caminho.split('/').filter(Boolean).map(decodificar),
    busca: new URLSearchParams(consulta),
  };
}

// O `href` de uma tela, para `<a>`: `hrefDe('/canais')` -> `#/canais`.
export function hrefDe(caminho) {
  if (caminho.startsWith('#')) return caminho;
  return `#${caminho.startsWith('/') ? '' : '/'}${caminho}`;
}
