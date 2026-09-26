// O calendário de todos os canais (etapa 7.5): os posts da semana, dia a dia,
// no relógio de quem olha. Sem React, de propósito: o teste do painel roda
// este arquivo no `node` de verdade.

const DIA_MS = 24 * 60 * 60 * 1000;

// O dia local (`AAAA-MM-DD`) de uma data, no fuso deste navegador.
export function diaLocal(data) {
  const d = data instanceof Date ? data : new Date(data);
  if (Number.isNaN(d.getTime())) return null;
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

// A meia-noite local de um dia, somando `dias` (pode ser negativo).
export function somarDias(data, dias) {
  const d = new Date(data);
  d.setHours(0, 0, 0, 0);
  // Somar pelo calendário, e não por 24 h: no dia em que o relógio muda, 24 h
  // depois da meia-noite não é a meia-noite seguinte.
  d.setDate(d.getDate() + dias);
  return d;
}

// A hora que vale para o post no calendário: quando foi ao ar, se já foi;
// senão, a hora marcada. Um post da fila manual (sem hora) não tem lugar no
// calendário -- ele espera uma pessoa, e aparece na fila.
export function horaDoPost(p) {
  return p.posted_at || p.scheduled_at || null;
}

// Os 7 dias a partir de `inicio`, cada um com os posts dele, na ordem da hora.
// Só entram os agendados e os publicados: falhou e cancelado não vão ao ar.
export function semana(publicacoes, inicio) {
  const primeiro = somarDias(inicio, 0);
  const dias = Array.from({ length: 7 }, (_, i) => {
    const data = somarDias(primeiro, i);
    return { dia: diaLocal(data), data: data.toISOString(), posts: [] };
  });
  const porDia = Object.fromEntries(dias.map((d) => [d.dia, d]));
  for (const p of publicacoes || []) {
    if (p.status !== 'scheduled' && p.status !== 'published' && p.status !== 'publishing') continue;
    const hora = horaDoPost(p);
    if (!hora) continue;
    const alvo = porDia[diaLocal(hora)];
    if (alvo) alvo.posts.push(p);
  }
  for (const d of dias) {
    d.posts.sort((a, b) => new Date(horaDoPost(a)) - new Date(horaDoPost(b)));
  }
  return dias;
}

// "seg, 29 set".
export function rotuloDoDia(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString('pt-BR', { weekday: 'short', day: 'numeric', month: 'short' })
    .replace(/\./g, '');
}

// "14:05".
export function horaCurta(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export const eHoje = (dia, agora = new Date()) => dia === diaLocal(agora);

export { DIA_MS };
