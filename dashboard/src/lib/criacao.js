// O vídeo criado por IA no painel (etapa 7.7): os nomes das escolhas do estilo
// e as frases da tela. As regras moram no motor (`estilos.py`, `midia_ia.py`,
// `receitas.py`), que manda as listas junto com o estilo; aqui fica o que a tela
// escreve em português. Sem React, de propósito: o teste roda este arquivo no
// `node` de verdade e compara as chaves com as do motor.
//
// Decisão do autor (26-set-2026): o estilo é configurado, nunca adivinhado.
// Nada aqui olha o nicho do canal.

export const FORMATOS = [
  { id: 'historia', nome: 'história', texto: 'começo, meio e fim, contada por um narrador' },
  { id: 'fatos', nome: 'fatos curiosos', texto: 'um atrás do outro' },
  { id: 'explicacao', nome: 'explicação', texto: 'um assunto, passo a passo' },
  { id: 'livre', nome: 'livre', texto: 'o que as instruções pedirem' },
];

export const VISUAIS = [
  { id: 'livro-infantil', nome: 'livro infantil', texto: 'ilustração 2D, cores suaves' },
  { id: 'animacao-3d', nome: 'animação 3D', texto: 'como filme de animação' },
  { id: 'anime', nome: 'anime', texto: 'traço limpo, cores vivas' },
  { id: 'aquarela', nome: 'aquarela', texto: 'pintura de bordas suaves' },
  { id: 'quadrinhos', nome: 'quadrinhos', texto: 'contorno forte, cor chapada' },
  { id: 'realista', nome: 'realista', texto: 'como foto de cinema' },
  { id: 'pixel-art', nome: 'pixel art', texto: 'videogame de 16 bits' },
  { id: 'nenhum', nome: 'descrevo eu', texto: 'só a sua descrição' },
];

// Os presets de legenda do `template.py`, mais "sem legenda".
export const LEGENDAS = [
  { id: 'karaoke_fill', nome: 'amarela, palavra por palavra' },
  { id: 'karaoke_glow', nome: 'brilho azul' },
  { id: 'karaoke_box', nome: 'palavra em caixa' },
  { id: 'base_apagada', nome: 'base apagada' },
  { id: 'limpo', nome: 'simples, como filme' },
  { id: 'centro', nome: 'no meio da tela' },
  { id: 'nenhuma', nome: 'sem legenda' },
];

export const DURACAO = { min: 20, max: 90 };
export const CENAS = { min: 3, max: 14 };
export const MAX_PERSONAGENS = 4;
export const MAX_IDEIAS = 200;

// O estilo novo, como o motor o cria (`estilos.padrao()`), menos a semente:
// quem a sorteia é o motor, uma vez, e ela fica.
export const ESTILO_PADRAO = {
  versao: 1,
  formato: 'historia',
  publico: '',
  tom: '',
  instrucoes: '',
  duracao_s: 60,
  cenas: 8,
  visual: { preset: 'livro-infantil', descricao: '', evitar: '' },
  personagens: [],
  voz: { nome: 'Kore', instrucao: '' },
  legenda: { preset: 'karaoke_fill' },
};

export function nomeDe(lista, id) {
  return (lista.find((item) => item.id === id) || {}).nome || id || '';
}

// Quantos vídeos inteiros cabem hoje na cota de imagem: cada cena é uma imagem.
export function videosQueCabem(cota, cenas) {
  const imagens = Number(cota?.imagens_hoje) || 0;
  const porVideo = Math.max(1, Number(cenas) || 1);
  return Math.floor(imagens / porVideo);
}

export function fraseDaCota(cota, cenas) {
  if (!cota) return null;
  const imagens = Number(cota.imagens_hoje) || 0;
  if (imagens <= 0) {
    return `A cota grátis de imagem de hoje acabou. Ela volta ${cota.imagem_volta || 'à meia-noite UTC'}.`;
  }
  const videos = videosQueCabem(cota, cenas);
  const quantos = videos === 0 ? 'não dá para um vídeo inteiro'
    : videos === 1 ? 'dá para 1 vídeo' : `dá para ${videos} vídeos`;
  return `Hoje ainda cabem ${imagens} imagens na cota grátis: ${quantos} de ${cenas} cenas.`;
}

// Uma linha que diz como é o vídeo deste estilo. No episódio longo (7.8) a
// duração e as cenas são as escolhidas na tela, e não as do vídeo curto do
// estilo: `{ duracao: false }` tira as duas da linha.
export function resumoDoEstilo(spec, { duracao = true } = {}) {
  if (!spec) return '';
  const partes = [
    nomeDe(FORMATOS, spec.formato),
    duracao ? `${spec.duracao_s} s` : null,
    duracao ? `${spec.cenas} cenas` : null,
    spec.visual?.preset === 'nenhum' ? 'visual descrito' : nomeDe(VISUAIS, spec.visual?.preset),
    `voz ${spec.voz?.nome || 'Kore'}`,
  ];
  const nomes = (spec.personagens || []).map((p) => p.nome).filter(Boolean);
  if (nomes.length) partes.push(nomes.join(', '));
  return partes.filter(Boolean).join(' · ');
}

// O site é publicado antes de o programa de quem usa ser atualizado: um motor
// de antes da 7.7 não tem o `/api/criacoes`, e a tela diz para atualizar ANTES
// do clique (`/api/config.criacao`).
export function situacaoDaCriacao({ configCarregada, criacaoNoMotor }) {
  if (!configCarregada) return 'carregando';
  return criacaoNoMotor ? 'pronto' : 'motor-antigo';
}

function semAcento(texto) {
  return String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '');
}

// A mesma do motor (`receitas.chave_da_ideia`): duas ideias que só diferem em
// acento, pontuação ou maiúscula são a mesma.
export function chaveDaIdeia(ideia) {
  return semAcento(ideia).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

// As ideias da receita, uma por linha, como o motor as guarda.
export function ideiasDoTexto(texto) {
  const vistas = new Set();
  const saida = [];
  for (const linha of String(texto || '').split(/\r?\n/)) {
    const ideia = linha.replace(/\s+/g, ' ').trim();
    const chave = chaveDaIdeia(ideia);
    if (!ideia || vistas.has(chave)) continue;
    vistas.add(chave);
    saida.push(ideia);
  }
  return saida;
}

export function corpoDaCriacao({ canalId, ideia }) {
  return { channel_id: canalId, ideia: String(ideia || '').replace(/\s+/g, ' ').trim() };
}

// A próxima ideia que a receita vai usar, como o motor decide
// (`receitas.proxima_ideia`): a primeira da lista que ainda não virou vídeo nem
// foi pulada; acabadas, uma nova sobre o tema; sem tema, o roteiro inventa.
export function proximaIdeia(spec, feitas = [], puladas = []) {
  const usadas = new Set([...feitas, ...puladas].map(chaveDaIdeia));
  const daLista = (spec?.ideias || []).find((i) => !usadas.has(chaveDaIdeia(i)));
  if (daLista) return { ideia: daLista, daLista: true };
  const tema = String(spec?.tema || '').trim();
  return { ideia: tema ? `uma ideia nova sobre ${tema}` : '', daLista: false };
}

export function fraseDaProximaIdeia(proxima) {
  if (!proxima?.ideia) return 'O próximo vídeo inventa uma ideia nova, no estilo do canal.';
  return proxima.daLista
    ? `Próximo vídeo: “${proxima.ideia}”.`
    : `As ideias da lista acabaram: o próximo vídeo é ${proxima.ideia}.`;
}

// --------------------------------------------------------------------------
// O episódio longo (etapa 7.8): a mesma máquina, horizontal, de 2 a 10 minutos.
// Os números são os do motor (`estilos.py`), e o teste compara.
// --------------------------------------------------------------------------

export const DURACAO_LONGA = { min: 120, max: 600 };
export const SEGUNDOS_POR_CENA_LONGA = 15;
export const CENAS_LONGAS = { min: 8, max: 40 };
export const HISTORIA_MAX = 80;

// Quantas cenas (imagens) tem um episódio desta duração, como o motor conta
// (`estilos.cenas_do_longo`). `Math.round` do JS arredonda 0,5 para cima e o do
// Python para o par: nos minutos inteiros da tela (múltiplos de 60 s ÷ 15) a
// conta nunca cai no meio, e o teste confere todos.
export function cenasDoLongo(segundos) {
  const s = Number(segundos);
  const base = Number.isFinite(s) ? s : DURACAO_LONGA.min;
  return Math.max(CENAS_LONGAS.min, Math.min(CENAS_LONGAS.max, Math.round(base / SEGUNDOS_POR_CENA_LONGA)));
}

export function nomeDaHistoria(texto) {
  return String(texto || '').replace(/\s+/g, ' ').trim();
}

// A mesma do motor (`estilos.chave_da_historia`): "A Lulu" e "a  lulu" são a
// mesma história -- e um nome "novo" igual ao de uma que existe a continua.
export function chaveDaHistoria(texto) {
  return nomeDaHistoria(texto).toLowerCase();
}

// O corpo do `POST /api/criacoes` do episódio. Sem história, ele sai avulso.
export function corpoDoEpisodio({ canalId, ideia, minutos, historia }) {
  const corpo = { ...corpoDaCriacao({ canalId, ideia }), formato: 'longo', duracao_min: Number(minutos) };
  const nome = nomeDaHistoria(historia);
  if (nome) corpo.historia = nome;
  return corpo;
}

// O que a cota do dia diz do episódio desta duração, ANTES do clique.
export function fraseDaCotaDoEpisodio(cota, minutos) {
  if (!cota) return null;
  const cenas = cenasDoLongo(Number(minutos) * 60);
  const imagens = Number(cota.imagens_hoje) || 0;
  if (imagens >= cenas) {
    return { ok: true, texto: `Um episódio de ${minutos} minutos tem ${cenas} cenas: hoje cabem ${imagens} imagens na cota grátis.` };
  }
  return {
    ok: false,
    texto: `Um episódio de ${minutos} minutos tem ${cenas} cenas, e hoje só cabem ${imagens} imagens na cota grátis. `
      + `Escolha um episódio mais curto, ou crie depois que a cota voltar (${cota.imagem_volta || 'à meia-noite UTC'}).`,
  };
}

// A situação da tela do vídeo longo: o site é publicado antes de o programa de
// quem usa ser atualizado, e um motor de antes da 7.8 faria um vídeo CURTO no
// lugar do episódio (ele ignora o `formato`).
export function situacaoDoVideoLongo({ configCarregada, videoLongoNoMotor }) {
  if (!configCarregada) return 'carregando';
  return videoLongoNoMotor ? 'pronto' : 'motor-antigo';
}

// Uma linha sobre a história escolhida: em que episódio ela está.
export function fraseDaHistoria(historia) {
  if (!historia) return 'Episódio avulso: não continua nenhuma história.';
  const ultimo = historia.ultimo || {};
  if (!ultimo.pronto) {
    return `O episódio ${ultimo.episodio} de “${historia.nome}” ainda não terminou: termine (ou apague) ele antes do próximo.`;
  }
  return `Este será o episódio ${ultimo.episodio + 1} de “${historia.nome}”, continuando de onde o ${ultimo.episodio} parou.`;
}
