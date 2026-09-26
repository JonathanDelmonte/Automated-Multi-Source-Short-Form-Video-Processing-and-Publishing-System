// As regras das telas de análises (etapa 7.4), sem React: o número curto, a
// escala do eixo, a geometria das colunas e as frases. O teste do painel roda
// este arquivo no `node` de verdade (tests/test_painel_da_plataforma.py).
//
// Quem SOMA é o motor (`analises.py`): o último número conhecido de cada corte,
// o ganho só com base, o horário só com amostra. Aqui só se desenha o que veio.

// A cor de cada plataforma NOS GRÁFICOS. Não é a cor da marca delas (YouTube,
// TikTok e Instagram são três vermelhos e rosas, que se confundem entre si e
// com o vermelho de erro): são as três primeiras vagas da paleta categórica
// validada para fundo escuro, conferida contra o fundo dos cartões (#0e0e0e)
// com o validador de paleta -- contraste, faixa de luminosidade e separação
// para daltonismo, em todos os pares. A cor segue a PLATAFORMA, nunca a
// posição: o TikTok é laranja mesmo quando aparece sozinho.
export const COR_DA_PLATAFORMA = {
  youtube: '#3987e5',
  tiktok: '#d95926',
  instagram: '#199e70',
};

export const ORDEM = ['youtube', 'tiktok', 'instagram'];

// O fuso deste navegador, em minutos a leste de UTC (Brasil: -180). O motor
// roda em UTC no Docker; o dia e a faixa de horário são os de quem olha.
export function fusoDoNavegador(data = new Date()) {
  return -data.getTimezoneOffset();
}

export function caminhoDasAnalises({ canal, plataforma, dias = 28, fuso = 0 } = {}) {
  const q = new URLSearchParams();
  if (canal) q.set('canal', canal);
  if (plataforma) q.set('plataforma', plataforma);
  q.set('dias', String(dias));
  q.set('fuso_min', String(fuso));
  return `/api/analises?${q.toString()}`;
}

export function caminhoDaCalibracao({ canal, plataforma } = {}) {
  const q = new URLSearchParams();
  if (canal) q.set('canal', canal);
  if (plataforma) q.set('plataforma', plataforma);
  const busca = q.toString();
  return `/api/calibracao${busca ? `?${busca}` : ''}`;
}

// Separador de milhar e vírgula decimal, à mão: o resultado não pode depender
// de o `node` (ou o navegador) ter os dados de idioma.
function milhar(inteiro) {
  return String(inteiro).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

function umaCasa(valor) {
  const arredondado = Math.round(valor * 10) / 10;
  return (Number.isInteger(arredondado) ? String(arredondado) : arredondado.toFixed(1)).replace('.', ',');
}

// 1.284 · 12,9 mil · 4,2 mi. `null` é "não medido", e aparece como um traço
// -- nunca como zero.
export function numeroCurto(valor) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return '—';
  const n = Number(valor);
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${umaCasa(n / 1e9)} bi`;
  if (abs >= 1e6) return `${umaCasa(n / 1e6)} mi`;
  if (abs >= 1e4) return `${umaCasa(n / 1e3)} mil`;
  return milhar(Math.round(n));
}

// O número inteiro, com separador de milhar (tabela e dica).
export function numeroInteiro(valor) {
  if (valor === null || valor === undefined || Number.isNaN(Number(valor))) return '—';
  return milhar(Math.round(Number(valor)));
}

export function porcentagem(valor) {
  if (valor === null || valor === undefined) return '—';
  return `${umaCasa(Number(valor))}%`;
}

export function segundos(valor) {
  if (valor === null || valor === undefined) return '—';
  const s = Number(valor);
  if (s < 60) return `${umaCasa(s)} s`;
  const min = Math.floor(s / 60);
  const resto = Math.round(s - min * 60);
  return resto ? `${min} min ${resto} s` : `${min} min`;
}

// '2026-09-24' -> '24/9'. Sem `Date`: a data do motor já é o dia de quem olha.
export function diaCurto(isoDia) {
  const [, mes, dia] = String(isoDia || '').split('-').map(Number);
  return mes && dia ? `${dia}/${mes}` : String(isoDia || '');
}

// O rótulo de uma marca do eixo: todas no mesmo formato. "5.000" ao lado de
// "10 mil" parece duas unidades; acima de 10 mil, todas em "mil".
export function rotuloDoEixo(valor, teto) {
  if (!Number(valor)) return '0';
  if (Number(teto) >= 1e6) return `${umaCasa(valor / 1e6)} mi`;
  if (Number(teto) >= 1e4) return `${umaCasa(valor / 1e3)} mil`;
  return numeroInteiro(valor);
}

// A escala do eixo: o teto e até quatro marcas redondas (1, 2 ou 5 vezes uma
// potência de 10). O teto nunca é zero: um canal sem views ainda desenha o eixo.
export function escala(maximo, marcas = 4) {
  const topo = Math.max(1, Number(maximo) || 0);
  const bruto = topo / marcas;
  const potencia = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 5, 10].map((m) => m * potencia).find((p) => p >= bruto) || 10 * potencia;
  const passoInteiro = Math.max(1, passo);
  const teto = Math.ceil(topo / passoInteiro) * passoInteiro;
  const lista = [];
  for (let v = 0; v <= teto + 1e-9; v += passoInteiro) lista.push(Math.round(v));
  return { teto, marcas: lista };
}

// As plataformas que aparecem numa série, na ordem das telas.
export function plataformasDaSerie(serie) {
  const presentes = new Set();
  for (const dia of serie || []) {
    for (const [p, v] of Object.entries(dia.por_plataforma || {})) if (v !== null && v !== undefined) presentes.add(p);
  }
  return ORDEM.filter((p) => presentes.has(p)).concat([...presentes].filter((p) => !ORDEM.includes(p)).sort());
}

// A geometria das colunas empilhadas: para cada dia, os pedaços de baixo para
// cima, na ordem das plataformas, com 2 px de fundo entre um e outro (o
// espaço é o que separa os pedaços, e não uma borda). Dia sem base (`views`
// nulo) não tem coluna: um buraco honesto, e não um zero.
export const VAO = 2;

export function colunas(serie, { altura, teto, plataformas }) {
  const ordem = plataformas || plataformasDaSerie(serie);
  return (serie || []).map((dia, i) => {
    if (dia.views === null || dia.views === undefined) {
      return { i, dia: dia.dia, total: null, pedacos: [] };
    }
    let base = altura;
    const pedacos = [];
    const valores = ordem
      .map((p) => ({ plataforma: p, valor: Number((dia.por_plataforma || {})[p] || 0) }))
      .filter((pd) => pd.valor > 0);
    valores.forEach((pd, k) => {
      const h = teto > 0 ? (pd.valor / teto) * altura : 0;
      const vao = k > 0 ? VAO : 0;
      const alturaVisivel = Math.max(0, h - vao);
      const y = base - h;
      pedacos.push({ ...pd, y, altura: alturaVisivel, topo: k === valores.length - 1 });
      base = y;
    });
    return { i, dia: dia.dia, total: Number(dia.views), pedacos };
  });
}

// O caminho de uma coluna com o topo arredondado (4 px) e a base reta: o dado
// cresce de uma linha de base só.
export function caminhoDaColuna(x, y, largura, altura, raio = 4) {
  if (altura <= 0) return '';
  const r = Math.min(raio, largura / 2, altura);
  return `M${x},${y + altura}V${y + r}Q${x},${y} ${x + r},${y}H${x + largura - r}Q${x + largura},${y} ${x + largura},${y + r}V${y + altura}Z`;
}

// A linha da tendência (a "sparkline" dos cartões dos canais): pontos só onde
// o dia tem número, ligados pelos que têm.
export function pontosDaTendencia(serie, { largura, altura, margem = 2 }) {
  const valores = (serie || []).map((d) => (d.views === null || d.views === undefined ? null : Number(d.views)));
  const maximo = Math.max(1, ...valores.filter((v) => v !== null));
  const passo = valores.length > 1 ? (largura - 2 * margem) / (valores.length - 1) : 0;
  return valores
    .map((v, i) => (v === null ? null : [margem + i * passo, margem + (altura - 2 * margem) * (1 - v / maximo)]))
    .filter(Boolean);
}

export const NOMES_DAS_FAIXAS = {
  madrugada: 'madrugada (0h–6h)',
  manha: 'manhã (6h–12h)',
  tarde: 'tarde (12h–18h)',
  noite: 'noite (18h–24h)',
};

// A frase do horário. A conclusão só sai quando o motor a deu (amostra
// mínima em pelo menos duas faixas); antes disso, a frase diz o que falta.
export function fraseDoHorario(porHorario) {
  if (!porHorario) return '';
  const faixas = porHorario.faixas || [];
  const minimo = porHorario.minimo || 5;
  if (porHorario.melhor) {
    const f = faixas.find((x) => x.faixa === porHorario.melhor);
    return `Pelos posts medidos, a ${NOMES_DAS_FAIXAS[porHorario.melhor] || porHorario.melhor} rende mais no primeiro dia `
      + `(mediana de ${numeroInteiro(f?.views_do_primeiro_dia_mediana)} visualizações). É um indício, não uma regra: `
      + 'os horários da Agenda continuam sendo escolha sua.';
  }
  if (porHorario.parecidas) {
    const comAmostra = faixas.filter((f) => f.amostra_suficiente);
    const lista = comAmostra
      .map((f) => `${(NOMES_DAS_FAIXAS[f.faixa] || f.faixa).split(' ')[0]} ${numeroInteiro(f.views_do_primeiro_dia_mediana)}`)
      .join(', ');
    return `As faixas com amostra rendem parecido no primeiro dia (${lista}): nenhuma passa as outras por uma `
      + 'margem que não seja acaso. Os horários da Agenda podem ficar como estão.';
  }
  const comNumero = faixas.filter((f) => f.com_views_do_primeiro_dia > 0);
  if (comNumero.length === 0) {
    return 'Ainda não há post com a leitura do primeiro dia. Com a conta conectada para medir, ela chega sozinha, '
      + 'a cada 6 horas.';
  }
  const hoje = comNumero.map((f) => `${(NOMES_DAS_FAIXAS[f.faixa] || f.faixa).split(' ')[0]} ${f.com_views_do_primeiro_dia}`).join(', ');
  return `Ainda não dá para dizer qual horário rende mais: a comparação precisa de ${minimo} posts medidos em pelo `
    + `menos duas faixas. Hoje: ${hoje}.`;
}

// As contas do recorte que ainda não medem -- a tela diz o que fazer em vez
// de mostrar zero.
export function contasSemMedir(contas) {
  return (contas || []).filter((c) => !c.medir);
}

// Quando a análise é de uma plataforma, o título dela; senão, "todas".
export function rotuloDoRecorte(plataforma, nomes) {
  return plataforma ? (nomes?.[plataforma]?.nome || plataforma) : 'todas as plataformas';
}

const NOME_DA_PLATAFORMA = { youtube: 'YouTube', tiktok: 'TikTok', instagram: 'Instagram' };
const NOME_DA_FAIXA_DE_NOTA = { baixo: 'nota baixa (até 59)', medio: 'nota média (60 a 79)', alto: 'nota alta (80 ou mais)' };

export function coeficiente(rho) {
  return `ρ = ${rho >= 0 ? '+' : '−'}${Math.abs(rho).toFixed(2).replace('.', ',')}`;
}

function direcao(rho) {
  if (rho > 0.3) return 'acompanha';
  if (rho < -0.3) return 'vai contra';
  return 'não acompanha';
}

// As frases da calibração, escritas pela tela (o motor manda os números). A
// regra do motor vale aqui: abaixo do mínimo, nenhum coeficiente é dito -- com
// poucos cortes, um número alto acontece por acaso, e escrito vira motivo.
export function frasesDaCalibracao(relatorio) {
  if (!relatorio) return [];
  const minimo = relatorio.minimo_para_correlacao || 10;
  if (!relatorio.clipes_medidos) {
    return ['Nenhum corte publicado tem números ainda. Eles chegam sozinhos, a cada 6 horas, depois que as contas estão conectadas para medir.'];
  }
  const frases = [];
  const linhas = relatorio.por_plataforma || [];
  let algum = false;
  for (const l of linhas) {
    const nome = NOME_DA_PLATAFORMA[l.plataforma] || l.plataforma;
    if (l.rho_score_views !== null && l.rho_score_views !== undefined) {
      algum = true;
      frases.push(`No ${nome}, a ordem que a IA deu aos cortes ${direcao(l.rho_score_views)} a ordem das visualizações (${coeficiente(l.rho_score_views)}, ${l.com_views} cortes).`);
    }
    if (l.rho_score_retencao !== null && l.rho_score_retencao !== undefined) {
      algum = true;
      frases.push(`No ${nome}, ela ${direcao(l.rho_score_retencao)} a ordem da retenção (${coeficiente(l.rho_score_retencao)}, ${l.com_retencao} cortes).`);
    }
  }
  if (!algum) {
    frases.push(`Ainda não dá para dizer se a nota da IA acerta: com menos de ${minimo} cortes medidos numa plataforma, um coeficiente alto acontece por acaso. Os números de cada corte já estão aqui em cima.`);
  }
  if (linhas.length > 1) {
    frases.push('Cada plataforma é comparada sozinha: uma visualização do TikTok não é uma do YouTube.');
  }
  const faixas = (relatorio.por_faixa || []).filter((f) => f.clipes && f.retencao_media !== null && f.retencao_media !== undefined);
  if (faixas.length >= 2) {
    frases.push(faixas.map((f) => `${NOME_DA_FAIXA_DE_NOTA[f.faixa] || f.faixa}: ${porcentagem(f.retencao_media)} de retenção média (${f.clipes} cortes)`).join('; ') + '.');
  }
  return frases;
}
