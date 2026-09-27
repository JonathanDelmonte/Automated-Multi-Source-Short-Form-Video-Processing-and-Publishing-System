// A série em partes do lado da tela (etapa 7.6): um vídeo longo vira Parte 1,
// 2, 3... O motor (`series.py`) é quem corta; aqui ficam as regras que o
// formulário precisa, sem React, para o teste do painel rodar este arquivo no
// `node` de verdade.

// As durações de cada parte que o formulário oferece, em segundos. O minuto é
// o que o autor pediu; três minutos é o teto dos Shorts e dos Reels.
export const DURACOES = [30, 60, 90, 120, 180];
export const DURACAO_PADRAO = 60;

// O "Parte N" no vídeo. No título ele vai sempre.
export const ROTULOS = [
  { value: 'inicio', label: 'no começo', hint: '5 s' },
  { value: 'sempre', label: 'o tempo todo' },
  { value: 'nao', label: 'não mostrar' },
];

// Os estilos do rótulo são os do gancho (`hooks.HOOK_STYLES` no motor; há
// teste comparando).
export const ESTILOS = [
  { value: 'classic', label: 'clássico' },
  { value: 'dark', label: 'escuro' },
  { value: 'yellow', label: 'amarelo' },
  { value: 'red', label: 'vermelho' },
  { value: 'outline', label: 'contorno' },
  { value: 'outline_yellow', label: 'contorno amarelo' },
];

// Uma live da Twitch no ar é gravada por até este tanto (o teto do gravador).
export const BLOCOS = [30, 60, 90, 120];
export const BLOCO_PADRAO = 60;

// O mesmo teto do motor (`series.MAX_PARTES`).
export const MAX_PARTES = 500;

// "1:02:30", "2:05" ou "90" em segundos. Vazio é null (não escolhido);
// qualquer outra coisa é NaN, e o formulário diz que não entendeu.
export function lerTempo(texto) {
  const limpo = String(texto ?? '').trim();
  if (!limpo) return null;
  if (!/^\d+(:\d{1,2}){0,2}$/.test(limpo)) return NaN;
  const partes = limpo.split(':').map(Number);
  if (partes.slice(1).some((n) => n >= 60)) return NaN;
  return partes.reduce((total, n) => total * 60 + n, 0);
}

export function formatarTempo(segundos) {
  const s = Math.max(0, Math.round(Number(segundos) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`;
}

// "1 min", "30 s", "1 min 30 s".
export function duracaoEmTexto(segundos) {
  const s = Math.round(Number(segundos) || 0);
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (!m) return `${r} s`;
  return r ? `${m} min ${r} s` : `${m} min`;
}

// Quantas partes, pela mesma conta do motor (`series.quantas_partes`): o
// trecho dividido pelo alvo, meio para cima -- 150 s com partes de 60 viram
// três de 50.
export function quantasPartes(duracao, alvo, inicio = null, fim = null) {
  const total = Number(duracao) || 0;
  const ini = Math.min(Math.max(0, Number(inicio) || 0), total);
  const ate = fim == null || Number(fim) > total ? total : Math.max(ini, Number(fim));
  const trecho = ate - ini;
  if (trecho <= 0) return 0;
  return Math.max(1, Math.floor(trecho / Math.max(1, Number(alvo) || DURACAO_PADRAO) + 0.5));
}

// A frase que o formulário mostra quando a duração do vídeo é conhecida (um
// arquivo escolhido: o navegador lê a duração sem enviar nada).
export function previsao(duracao, alvo, inicio = null, fim = null) {
  if (!duracao) return null;
  const n = quantasPartes(duracao, alvo, inicio, fim);
  if (n === 0) return { erro: 'O trecho escolhido fica fora do vídeo.' };
  if (n > MAX_PARTES) {
    return { erro: `Seriam ${n} partes, e o limite é ${MAX_PARTES}. Escolha partes mais longas ou um trecho menor.` };
  }
  const ini = Math.max(0, Number(inicio) || 0);
  const ate = fim == null || Number(fim) > duracao ? duracao : Number(fim);
  return { partes: n, texto: `${n} parte${n === 1 ? '' : 's'} de cerca de ${duracaoEmTexto((ate - ini) / n)}` };
}

// O link de um canal da Twitch AO VIVO (não um VOD, não um clipe): é quando o
// motor grava um bloco da live, e o formulário pergunta de quanto tempo.
export function ehLiveDaTwitch(url) {
  try {
    const u = new URL(String(url || '').trim());
    // `clips.twitch.tv/<id>` é um clipe, e não o canal.
    if (!/^(www\.|m\.)?twitch\.tv$/i.test(u.hostname)) return false;
    const caminho = u.pathname.split('/').filter(Boolean);
    return caminho.length === 1 && !['videos', 'directory', 'search', 'settings'].includes(caminho[0].toLowerCase());
  } catch {
    return false;
  }
}

// O pedido que vai ao motor (`serie` no `POST /api/process`). Só viaja o que a
// pessoa escolheu; o motor põe os padrões e valida de novo.
export function corpoDaSerie(escolhas) {
  const corpo = {
    duracao_parte_s: Number(escolhas.duracao) || DURACAO_PADRAO,
    rotulo: escolhas.rotulo || 'inicio',
    estilo_rotulo: escolhas.estilo || 'classic',
    agendar: !!escolhas.agendar,
  };
  const nome = String(escolhas.nome || '').replace(/\s+/g, ' ').trim();
  if (nome) corpo.nome = nome;
  const inicio = lerTempo(escolhas.inicio);
  const fim = lerTempo(escolhas.fim);
  if (Number.isFinite(inicio)) corpo.inicio_s = inicio;
  if (Number.isFinite(fim)) corpo.fim_s = fim;
  if (escolhas.bloco) corpo.bloco_min = Number(escolhas.bloco);
  return corpo;
}

// O que há de errado no que a pessoa digitou, antes de enviar.
export function problemaDoTrecho(inicioTexto, fimTexto) {
  const inicio = lerTempo(inicioTexto);
  const fim = lerTempo(fimTexto);
  if (Number.isNaN(inicio) || Number.isNaN(fim)) return 'Escreva o tempo como 1:30 ou 1:02:30.';
  if (inicio != null && fim != null && fim - inicio < 20) return 'O trecho escolhido é curto demais para uma série.';
  return null;
}

// A linha curta de uma série nos cartões (lista de projetos, página do
// projeto): "série · 60 partes de ~1 min".
export function textoDaSerie(serie) {
  if (!serie) return '';
  const partes = serie.partes || serie.prontas;
  const cada = serie.duracao_parte_s ? ` de ~${duracaoEmTexto(serie.duracao_parte_s)}` : '';
  return partes ? `série · ${partes} parte${partes === 1 ? '' : 's'}${cada}` : 'série em partes';
}
