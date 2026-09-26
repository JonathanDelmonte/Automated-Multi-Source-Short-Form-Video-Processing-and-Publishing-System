import { apiFetch } from './api';

// O envio de um vídeo ao motor (`POST /api/process`). Morava dentro do App.jsx;
// saiu para cá na 7.1 porque agora duas telas enviam -- Criar e o "criar cortes
// deste vídeo" do YouTube Studio -- e o corpo do pedido tem de ser um só.
//
// Devolve o JSON do motor: `{ job_id }`, ou `{ needs_confirmation, quality_check }`
// quando a fonte tem resolução baixa e a pessoa precisa decidir antes. Erro de
// rede ou recusa do motor sobe como `Error` com o texto dele.
export async function enviarVideo(dados, { apiKey = '', forcarBaixaQualidade = false, canalId = null } = {}) {
  // A chave do navegador vai no cabeçalho; a do programa, o motor já tem.
  const headers = apiKey ? { 'X-Gemini-Key': apiKey } : {};

  // Os controles avançados só viajam quando a pessoa mexeu neles, e o pedido
  // padrão continua idêntico ao de antes deles.
  const avancado = {
    target_clips: dados.targetClips || null,
    clip_min_seconds: dados.clipMinSeconds || null,
    clip_max_seconds: dados.clipMaxSeconds || null,
    // Mandado nos dois sentidos: ausente quer dizer desligado para quem chama a
    // API crua, mas o painel sempre diz a escolha da pessoa.
    auto_hook: dados.autoHook ? '1' : '0',
    auto_hook_style: dados.autoHook ? (dados.autoHookStyle || 'classic') : null,
    // 'auto' é o padrão do motor, então só uma escolha deliberada viaja.
    layouts: dados.layout && dados.layout !== 'auto' ? dados.layout : null,
    // O canal para o qual o projeto é feito (Fase 7). Sem canal, o de sempre.
    channel_id: canalId || null,
  };
  const presentes = Object.fromEntries(Object.entries(avancado).filter(([, v]) => v != null));

  let body;
  if (dados.type === 'url') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify({
      url: dados.payload,
      acknowledged: !!dados.acknowledged,
      output_format: dados.outputFormat || 'auto',
      force_low_quality: forcarBaixaQualidade,
      ...presentes,
    });
  } else if (dados.type === 'thumbnail_session') {
    // Do YouTube Studio (issue #68 do upstream): o vídeo e a transcrição já
    // estão no motor, guardados pela sessão do Studio.
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify({
      thumbnail_session_id: dados.payload,
      acknowledged: !!dados.acknowledged,
      output_format: dados.outputFormat || 'auto',
      ...presentes,
    });
  } else {
    const formulario = new FormData();
    formulario.append('file', dados.payload);
    formulario.append('acknowledged', dados.acknowledged ? 'true' : 'false');
    formulario.append('output_format', dados.outputFormat || 'auto');
    for (const [k, v] of Object.entries(presentes)) formulario.append(k, v);
    body = formulario;
  }

  const res = await apiFetch('/api/process', { method: 'POST', headers, body });
  if (!res.ok) {
    const texto = await res.text();
    let detalhe = texto;
    try {
      const d = JSON.parse(texto).detail;
      if (typeof d === 'string') detalhe = d;
    } catch { /* não era JSON: fica o texto */ }
    throw new Error(detalhe);
  }
  return res.json();
}

// A prévia do vídeo enquanto ele processa. Um arquivo enviado só existe como
// `File` na aba que o enviou, e a tela do projeto é outra rota: o envio deixa a
// mídia aqui, pelo id do job, e a tela do projeto a pega. Reaberto depois (ou
// noutra aba), o projeto usa a cópia que o motor guarda (`/api/source`).
const midias = new Map();

export function guardarMidia(jobId, midia) {
  if (jobId && midia) midias.set(jobId, midia);
}

export function midiaDoProjeto(jobId) {
  return midias.get(jobId) || (jobId ? { type: 'server', payload: `/api/source/${jobId}` } : null);
}
