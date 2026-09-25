// Nome e versão do navegador, e o sistema, para Configurações → Versões
// (25-set-2026). É a primeira pergunta de todo "no meu computador não abre".
//
// Nos derivados do Chromium, `navigator.userAgentData` lista marcas, e duas
// não servem: o próprio Chromium e uma marca de mentira ("Not A Brand", que o
// Chrome sorteia de propósito). A que interessa é a outra: Google Chrome,
// Microsoft Edge, Brave, Opera. Firefox e Safari não têm `userAgentData`, e
// ali vale o texto do userAgent -- com o Edge e o Opera testados ANTES do
// Chrome, porque os dois também escrevem "Chrome/" no deles.

// O Windows 11 diz "Windows NT 10.0" no userAgent, igual ao 10. Só a pergunta
// de alta entropia separa os dois: `platformVersion` 13 ou mais é o 11 (regra
// publicada pela Microsoft); de 1 a 10, o 10.
export function sistema(plataforma, versaoDaPlataforma) {
  if (plataforma === 'Windows' && versaoDaPlataforma) {
    const maior = Number(String(versaoDaPlataforma).split('.')[0]);
    if (maior >= 13) return 'Windows 11';
    if (maior > 0) return 'Windows 10';
  }
  return plataforma || null;
}

export function pelasMarcas(marcas, plataforma, versaoDaPlataforma) {
  const reais = (marcas || []).filter((m) => m?.brand && !/not.?a.?brand/i.test(m.brand));
  const marca = reais.find((m) => m.brand !== 'Chromium') || reais[0];
  if (!marca) return null;
  return [`${marca.brand} ${marca.version}`, sistema(plataforma, versaoDaPlataforma)]
    .filter(Boolean).join(' · ');
}

export function pelaIdentificacao(ua = '') {
  const achar = (re) => (ua.match(re) || [])[1];
  const nomes = [
    ['Microsoft Edge', /Edg(?:e|A|iOS)?\/([\d.]+)/],
    ['Opera', /OPR\/([\d.]+)/],
    ['Firefox', /(?:Firefox|FxiOS)\/([\d.]+)/],
    ['Chrome', /(?:Chrome|CriOS)\/([\d.]+)/],
  ];
  let nome = null;
  for (const [rotulo, re] of nomes) {
    const v = achar(re);
    if (v) { nome = `${rotulo} ${v}`; break; }
  }
  if (!nome && /Safari\//.test(ua) && achar(/Version\/([\d.]+)/)) nome = `Safari ${achar(/Version\/([\d.]+)/)}`;
  let so = null;
  if (/Windows/.test(ua)) so = 'Windows';
  else if (/iPhone|iPad/.test(ua)) so = 'iOS';
  else if (/Mac OS X/.test(ua)) so = 'macOS';
  else if (/Android/.test(ua)) so = 'Android';
  else if (/Linux/.test(ua)) so = 'Linux';
  return [nome || 'não identificado', so].filter(Boolean).join(' · ');
}

// Nunca lança: sem a pergunta de alta entropia, fica com a versão curta das
// marcas; sem marcas, com o userAgent.
export async function lerNavegador(nav = typeof navigator !== 'undefined' ? navigator : null) {
  const uad = nav?.userAgentData;
  if (uad?.brands?.length) {
    let marcas = uad.brands;
    let versaoDaPlataforma = null;
    try {
      const alta = await uad.getHighEntropyValues(['fullVersionList', 'platformVersion']);
      if (alta?.fullVersionList?.length) marcas = alta.fullVersionList;
      versaoDaPlataforma = alta?.platformVersion || null;
    } catch { /* fica com a versão curta */ }
    const texto = pelasMarcas(marcas, uad.platform, versaoDaPlataforma);
    if (texto) return texto;
  }
  return pelaIdentificacao(nav?.userAgent || '');
}
