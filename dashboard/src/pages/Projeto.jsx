import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Activity, ArrowLeft, Check, ChevronDown, Copy, Download, FolderOpen, Loader2, Plus, Terminal } from 'lucide-react';
import ResultCard from '../components/ResultCard';
import ProcessingAnimation from '../components/ProcessingAnimation';
import ClipEditor from '../components/ClipEditor';
import ReframeEditor from '../components/ReframeEditor';
import MoverParaCanal from '../components/MoverParaCanal';
import AvatarDoCanal from '../components/ui/AvatarDoCanal';
import { useAuth } from '../contexts/AuthContext';
import { apiFetch } from '../lib/api';
import { seloDaIA } from '../lib/seloDaIA';
import { midiaDoProjeto } from '../lib/processar';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// Um projeto aberto: o vídeo processando, o log e os cortes (`#/projetos/<id>`).
//
// Era a metade do App.jsx que se chamava "Clip Generator", com o projeto aberto
// guardado no localStorage para voltar depois de um F5. Na 7.1 ganhou endereço
// próprio, e o endereço É a memória: recarregar, voltar ou mandar o link
// reabre o mesmo projeto, perguntando ao motor -- sem cópia no navegador que
// possa ficar velha.

// Erro proprio para "esse job nao existe mais", que e diferente de "a rede
// falhou". A distincao importa: erro de rede se tenta de novo, job inexistente
// nao -- insistir nele e o que prendia a tela para sempre.
class JobSumiu extends Error {}

const pollJob = async (jobId) => {
  const res = await apiFetch(`/api/status/${jobId}`);
  if (res.status === 404) throw new JobSumiu('job não existe mais');
  if (!res.ok) throw new Error('Status check failed');
  return res.json();
};

// Uma linha do log e texto puro ou { texto, t }. O backend carimba a hora em
// que cada linha NASCEU (`log_times`, epoch); antes a tela escrevia a hora ao
// DESENHAR, e todas as linhas saiam com a hora de quem olhava. Linha escrita
// pelo proprio painel fica sem hora: melhor sem hora do que com a hora errada.
const linhasDoStatus = (data) => {
  const linhas = data?.logs || [];
  const horas = data?.log_times;
  if (!Array.isArray(horas) || horas.length !== linhas.length) return linhas;
  return linhas.map((texto, i) => (horas[i] ? { texto, t: horas[i] } : texto));
};
const textoDaLinha = (linha) => (typeof linha === 'string' ? linha : linha.texto);
const horaDaLinha = (linha) =>
  (typeof linha === 'string' || !linha.t ? '' : new Date(linha.t * 1000).toLocaleTimeString());

const formatRetention = (seconds) => {
  if (seconds >= 86400) return `${Math.round(seconds / 86400)} dia${seconds >= 172800 ? 's' : ''}`;
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} hora${seconds >= 7200 ? 's' : ''}`;
  return `${Math.max(1, Math.round(seconds / 60))} min`;
};

// O estado do motor, no vocabulário desta tela. Tudo o que não terminou é
// "processando": na fila também é andamento, e a barra diz o estágio.
const DO_MOTOR = { completed: 'complete', failed: 'error', cancelled: 'cancelado' };

const SELO = {
  processing: { texto: 'processando', classe: 'badge-brass' },
  complete: { texto: 'pronto', classe: 'badge-ok' },
  error: { texto: 'falhou', classe: 'badge-danger' },
};

export default function Projeto({ jobId }) {
  const { apiKey, geminiNoMotor, canais } = usePainel();
  const { jobRetentionSeconds } = useAuth();
  // carregando, processing, complete, error, cancelado, sumiu
  const [status, setStatus] = useState('carregando');
  // Progresso vem do backend por estagio, nao por porcentagem: o pipeline sabe
  // onde esta, nao quanto falta dentro do estagio. Ver `_stage_view` no app.py.
  const [stage, setStage] = useState(null);
  const [canalId, setCanalId] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [logs, setLogs] = useState([]);
  const [logsCopied, setLogsCopied] = useState(false);
  const [results, setResults] = useState(null);
  // Collapsed on phones: the log tail is the least useful thing on a 360px
  // screen and it was pushing the actual clips a full scroll down.
  const [logsVisible, setLogsVisible] = useState(() => {
    try { return window.innerWidth >= 768; } catch { return true; }
  });
  // Bulk subtitles: apply one style to every clip of the job (triggered from
  // within a clip's subtitle modal via "apply to all").
  const [bulkSub, setBulkSub] = useState({ running: false, current: 0, total: 0, errors: 0 });
  const [downloadingAll, setDownloadingAll] = useState(false);
  const [editingClip, setEditingClip] = useState(null);
  const [reframingClip, setReframingClip] = useState(null);
  // A prévia: o arquivo ou o link que acabou de ser enviado, ou a cópia que o
  // motor guarda (`/api/source`) quando o projeto é reaberto.
  const midia = useMemo(() => midiaDoProjeto(jobId), [jobId]);

  // Sync state for original video playback
  const [syncedTime, setSyncedTime] = useState(0);
  const [isSyncedPlaying, setIsSyncedPlaying] = useState(false);
  const [syncTrigger, setSyncTrigger] = useState(0);

  // Best clips first. The backend hands them back in transcript order, which
  // buries the strongest one wherever it happens to fall in the video.
  //
  // The ORIGINAL array position travels with each clip and is what gets passed
  // down as `index`: it is the clip's identity everywhere else (clip_index on
  // /api/subtitle, /api/edit and publishing, the clip-N.mp4 download name).
  // Sorting the array itself would silently repoint all of that at the wrong
  // clip.
  const rankedClips = useMemo(() => {
    const clips = results?.clips;
    if (!Array.isArray(clips)) return [];
    return clips
      .map((clip, index) => ({ clip, index }))
      .sort((a, b) => {
        const sa = Number.isFinite(a.clip?.predicted_score) ? a.clip.predicted_score : -1;
        const sb = Number.isFinite(b.clip?.predicted_score) ? b.clip.predicted_score : -1;
        return sb - sa || a.index - b.index;
      });
  }, [results]);

  const aplicar = useCallback((data) => {
    setLogs(linhasDoStatus(data));
    if (data.result) setResults(data.result);
    if ('channel_id' in data) setCanalId(data.channel_id || null);
    setStage(data.stage_index
      ? { label: data.stage_label, index: data.stage_index, total: data.stage_total }
      : null);
  }, []);

  // Abrir: um pedido ao motor. Um job ainda rodando volta para 'processing', e
  // o efeito de polling faz o resto -- e por isso que reabrir um job em
  // andamento retoma a barra em vez de mostrar uma tela morta.
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const data = await pollJob(jobId);
        if (!vivo) return;
        aplicar(data);
        setStatus(DO_MOTOR[data.status] || 'processing');
      } catch (e) {
        if (!vivo) return;
        // Falha de rede não é projeto perdido: o polling segue perguntando, e
        // o estado certo chega quando o programa responder.
        setStatus(e instanceof JobSumiu ? 'sumiu' : 'processing');
      }
    })();
    return () => { vivo = false; };
  }, [jobId, aplicar]);

  useEffect(() => {
    if (status !== 'processing') return undefined;
    const interval = setInterval(async () => {
      try {
        const data = await pollJob(jobId);
        if (data.result) setResults(data.result);
        if (data.stage_index) {
          setStage({ label: data.stage_label, index: data.stage_index, total: data.stage_total });
        }
        if (data.status === 'cancelled') {
          // Desfecho proprio, nao erro: quem clicou em cancelar nao deve ver
          // a tela vermelha de falha.
          setStatus('cancelado');
          setStage(null);
          setCancelling(false);
        } else if (data.status === 'completed') {
          // O fim do log (o resumo de tempo do job) sai entre o ultimo poll
          // e este: sem isto, so aparecia reabrindo o projeto.
          if (data.logs) setLogs(linhasDoStatus(data));
          setStatus('complete');
        } else if (data.status === 'failed') {
          const errorMsg = data.error || (data.logs && data.logs.length > 0 ? data.logs[data.logs.length - 1] : 'Process failed');
          setLogs((prev) => [...(data.logs ? linhasDoStatus(data) : prev), `Error: ${errorMsg}`]);
          setStatus('error');
        } else if (data.logs) {
          setLogs(linhasDoStatus(data));
        }
      } catch (e) {
        if (e instanceof JobSumiu) {
          // Apagado noutra aba, ou a pasta saiu do disco: antes o poll batia
          // num 404 a cada 2s para sempre, e a tela ficava presa num projeto
          // fantasma. Agora diz que ele não existe mais.
          setStatus('sumiu');
          return;
        }
        console.error('Polling error', e);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [status, jobId]);

  // Cancela de verdade: o backend mata o subprocesso E apaga o manifesto de
  // resume. Sem o segundo passo o job voltava sozinho 30s depois.
  const handleCancel = useCallback(async () => {
    if (cancelling) return;
    setCancelling(true);
    try {
      await apiFetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      setStatus('cancelado');
      setStage(null);
    } catch (e) {
      console.error('Cancel failed', e);
    } finally {
      setCancelling(false);
    }
  }, [jobId, cancelling]);

  const handleCopyLogs = useCallback(async () => {
    try {
      // Com a hora na frente: quem cola o log para investigar lentidao ve
      // quanto cada passo levou, e nao so o que aconteceu.
      const texto = logs.map((linha) => {
        const hora = horaDaLinha(linha);
        return hora ? `[${hora}] ${textoDaLinha(linha)}` : textoDaLinha(linha);
      }).join('\n');
      await navigator.clipboard.writeText(texto);
      setLogsCopied(true);
      setTimeout(() => setLogsCopied(false), 2000);
    } catch (e) {
      console.error('Copy failed', e);
    }
  }, [logs]);

  const handleClipPlay = (startTime) => {
    setSyncedTime(startTime);
    setIsSyncedPlaying(true);
    setSyncTrigger((prev) => prev + 1);
  };

  // A recut replaced the clip's server file with a fresh render (burned layers
  // reset), so update the results and let the ResultCard remount from the new
  // file.
  const handleClipRerendered = (index, data) => {
    setResults((prev) => {
      if (!prev?.clips?.[index]) return prev;
      const clips = prev.clips.slice();
      clips[index] = {
        ...clips[index],
        video_url: data.new_video_url,
        start: data.start,
        end: data.end,
        recipe: data.recipe,
      };
      return { ...prev, clips };
    });
  };

  // Apply one subtitle style to every clip of the job, sequentially.
  const handleBulkSubtitles = async (options) => {
    const clips = results?.clips || [];
    const total = clips.length;
    if (!total) return;
    setBulkSub({ running: true, current: 0, total, errors: 0 });
    let errors = 0;
    for (let i = 0; i < total; i++) {
      setBulkSub({ running: true, current: i + 1, total, errors });
      try {
        const res = await apiFetch('/api/subtitle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            job_id: jobId,
            clip_index: i,
            position: options.position,
            font_size: options.fontSize,
            font_name: options.fontName,
            font_color: options.fontColor,
            border_color: options.borderColor,
            border_width: options.borderWidth,
            bg_color: options.bgColor,
            bg_opacity: options.bgOpacity,
            style: options.style || 'classic',
            highlight_color: options.highlightColor || '#FFD700',
            effect: options.effect || 'none',
            base_opacity: options.baseOpacity ?? 1.0,
            uppercase: options.uppercase || false,
            // Chain from the clip's current server file (its video_url basename).
            input_filename: (clips[i].video_url || '').split('/').pop(),
          }),
        });
        if (!res.ok) errors++;
      } catch {
        errors++;
      }
    }
    setBulkSub({ running: false, current: total, total, errors });
    // Refresh results so each ResultCard picks up its new subtitled video_url.
    try {
      const data = await pollJob(jobId);
      if (data.result) setResults(data.result);
    } catch { /* keep current results */ }
  };

  const handleDownloadAll = async () => {
    setDownloadingAll(true);
    try {
      const res = await apiFetch(`/api/jobs/${jobId}/download-all`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `virtu-clips_${(jobId || '').slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Não consegui baixar: ${e.message}`);
    } finally {
      setDownloadingAll(false);
    }
  };

  const doCanal = canalId ? canais.porId[canalId] : null;
  const novoHref = hrefDe(`/criar/cortes${canalId ? `?canal=${canalId}` : ''}`);

  // A barra de cima: voltar, o canal do projeto (e trocar), e criar outro.
  // Dentro de um projeto, o que falta e VOLTAR -- o painel herdado so tinha
  // "New Project", que cria em vez de voltar.
  const barra = (
    <div className="shrink-0 px-3 sm:px-4 pt-3 flex flex-wrap items-center gap-2">
      <a href={hrefDe(doCanal ? `/canais/${doCanal.id}` : '/projetos')} className="btn-quiet px-3 py-1.5 text-xs">
        <ArrowLeft size={14} /> {doCanal ? doCanal.name : 'projetos'}
      </a>
      {status !== 'sumiu' && (
        <span className="inline-flex items-center gap-1.5 min-w-0">
          {doCanal && <AvatarDoCanal canal={doCanal} size={20} />}
          <MoverParaCanal jobId={jobId} canalId={canalId} aoMover={setCanalId} />
        </span>
      )}
      <a href={novoHref} className="btn-quiet px-3 py-1.5 text-xs ml-auto">
        <Plus size={14} /> novo
      </a>
    </div>
  );

  if (status === 'carregando') {
    return (
      <div className="h-full flex items-center justify-center gap-2 text-muted text-sm">
        <Loader2 size={15} className="animate-spin" /> abrindo o projeto…
      </div>
    );
  }

  if (status === 'sumiu' || status === 'cancelado') {
    return (
      <div className="h-full flex flex-col">
        {barra}
        <div className="flex-1 flex items-center justify-center p-6">
          <div className="card p-8 max-w-md text-center space-y-3">
            <FolderOpen size={26} className="mx-auto text-muted" />
            <p className="text-ink">
              {status === 'sumiu' ? 'Este projeto não existe mais.' : 'O processamento foi cancelado.'}
            </p>
            <p className="text-muted text-sm">
              {status === 'sumiu'
                ? 'Ele foi apagado, ou a pasta dele saiu do disco.'
                : 'O projeto continua na lista, marcado como cancelado. Dá para começar outro com o mesmo vídeo.'}
            </p>
            <div className="flex flex-wrap justify-center gap-2 pt-1">
              <a href={hrefDe('/projetos')} className="btn-ghost px-4 py-2 text-sm">ver os projetos</a>
              <a href={novoHref} className="btn-primary px-4 py-2 text-sm"><Plus size={15} /> criar cortes</a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const selo = SELO[status] || SELO.processing;

  return (
    <div className="h-full flex flex-col">
      {barra}
      <div className="flex-1 min-h-0 flex flex-col md:flex-row gap-3 md:gap-4 p-3 md:p-4 overflow-y-auto md:overflow-y-hidden custom-scrollbar animate-fade">

        {/* Left Panel: Preview & Status */}
        <div className={`${status === 'complete' ? 'w-full md:w-[30%] lg:w-[25%]' : 'w-full md:w-[55%] lg:w-[60%]'} md:h-full flex flex-col shrink-0 md:shrink card p-3.5 sm:p-6 md:overflow-y-auto custom-scrollbar transition-all duration-700 ease-in-out`}>
          <div className="mb-4 sm:mb-6 flex items-center justify-between gap-2">
            <h2 className="text-sm font-medium text-ink lowercase flex items-center gap-2">
              <Activity className={`text-brass ${status === 'processing' ? 'animate-pulse' : ''}`} size={18} />
              análise ao vivo
            </h2>
            <span className={selo.classe}>{selo.texto}</span>
          </div>

          {midia && (
            <ProcessingAnimation
              media={midia}
              isComplete={status === 'complete'}
              syncedTime={syncedTime}
              isSyncedPlaying={isSyncedPlaying}
              syncTrigger={syncTrigger}
            />
          )}

          {/* Phones only. The log terminal below starts collapsed, so without
              this the screen would say nothing about what the job is doing. */}
          {status === 'processing' && (
            <div className="sm:hidden mb-3 flex items-start gap-2 text-xs text-ink2 min-w-0">
              <Loader2 size={14} className="animate-spin text-brass shrink-0 mt-px" />
              <span className="min-w-0 leading-snug break-words">
                {logs.length ? textoDaLinha(logs[logs.length - 1]) : 'começando…'}
              </span>
            </div>
          )}

          {/* Progresso e cancelamento. Em CPU a transcricao fica minutos em
              silencio, e silencio sem sinal e o que faz alguem recarregar a
              pagina no meio de um render. */}
          {status === 'processing' && (
            <div className="my-3 space-y-2">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="text-ink2 min-w-0 truncate">
                  {stage ? `${stage.index}/${stage.total} · ${stage.label}` : 'preparando…'}
                </span>
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={cancelling}
                  className="shrink-0 lowercase text-muted hover:text-danger transition-colors disabled:opacity-50"
                >
                  {cancelling ? 'cancelando…' : 'cancelar'}
                </button>
              </div>
              {/* Sem estagio ainda, a barra pulsa em vez de fingir 0%: a fila
                  nao sabe quanto falta e mentir seria pior. */}
              <div className="h-1 w-full bg-paper2 rounded-full overflow-hidden">
                <div
                  className={`h-full bg-brass transition-all duration-700 ease-out ${stage ? '' : 'animate-pulse w-1/6'}`}
                  style={stage ? { width: `${(stage.index / stage.total) * 100}%` } : undefined}
                />
              </div>
            </div>
          )}

          {/* Logs Terminal */}
          <div className={`bg-paper rounded-card border border-rule overflow-hidden flex flex-col transition-all duration-500 ${status === 'complete' ? `min-h-0 opacity-50 hover:opacity-100 ${logsVisible ? 'h-32' : 'h-auto'}` : `flex-1 ${logsVisible ? 'min-h-[160px] sm:min-h-[200px]' : 'min-h-0 flex-none'}`}`}>
            {/* Dois botoes lado a lado, nao um dentro do outro: aninhar o de
                copiar dentro do cabecalho-botao seria HTML invalido. */}
            <div className="w-full px-3.5 sm:px-4 py-2.5 border-b border-rule flex items-center justify-between gap-2 bg-paper2 shrink-0">
              <button
                type="button"
                onClick={() => setLogsVisible(!logsVisible)}
                aria-expanded={logsVisible}
                className="flex items-center gap-2 min-w-0 text-left"
              >
                <span className="readout flex items-center gap-2">
                  <Terminal size={12} /> log
                </span>
              </button>
              <span className="flex items-center gap-2 text-muted shrink-0">
                {!logsVisible && logs.length > 0 && (
                  <span className="readout normal-case">{logs.length}</span>
                )}
                {logs.length > 0 && (
                  <button
                    type="button"
                    onClick={handleCopyLogs}
                    title="Copiar o log inteiro"
                    className="hover:text-ink transition-colors"
                  >
                    {logsCopied ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setLogsVisible(!logsVisible)}
                  aria-expanded={logsVisible}
                  aria-label={logsVisible ? 'Esconder o log' : 'Mostrar o log'}
                  className="hover:text-ink transition-colors"
                >
                  <ChevronDown size={16} className={logsVisible ? '' : 'rotate-180'} />
                </button>
              </span>
            </div>
            {logsVisible && (
              <div className="flex-1 p-3.5 sm:p-4 overflow-y-auto font-mono text-[11px] sm:text-xs space-y-1.5 custom-scrollbar text-muted break-words">
                {logs.map((linha, i) => {
                  const texto = textoDaLinha(linha);
                  return (
                    <div key={i} className={`flex gap-2 ${texto.toLowerCase().includes('error') ? 'text-danger' : 'text-muted'}`}>
                      <span className="text-muted opacity-50 shrink-0 hidden sm:inline min-w-[8ch] tabular-nums">{horaDaLinha(linha)}</span>
                      <span className="min-w-0 break-words">{texto}</span>
                    </div>
                  );
                })}
                {status === 'processing' && (
                  <div className="animate-pulse text-brass">_</div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Panel: Results Grid */}
        <div className={`${status === 'complete' ? 'w-full md:w-[70%] lg:w-[75%]' : 'w-full md:w-[45%] lg:w-[40%]'} md:h-full flex flex-col shrink-0 md:shrink card p-3.5 sm:p-6 transition-all duration-700 ease-in-out`}>
          <div className="mb-4 sm:mb-6 shrink-0 space-y-3">
            <h2 className="font-display uppercase tracking-wide text-lg sm:text-xl text-ink flex flex-wrap items-center gap-2">
              <span className="mr-auto">cortes</span>
              {results?.clips?.length > 0 && (
                <span className="readout bg-paper3 px-2.5 py-1 rounded-full">
                  {results.clips.length} corte{results.clips.length === 1 ? '' : 's'}
                </span>
              )}
              {/* Tokens, e nao dolares (25-set-2026): o selo dizia "GEMINI · $0.012"
                  com chave gratuita, que nao cobra nada. Quem respondeu e quanto
                  custaria ficam no title. */}
              {results?.cost_analysis && (
                <span className="readout bg-paper3 px-2.5 py-1 rounded-full" title={seloDaIA(results.cost_analysis).detalhe}>
                  {seloDaIA(results.cost_analysis).texto}
                </span>
              )}
            </h2>
            {results?.clips?.length > 0 && status === 'complete' && (
              <div className="flex flex-col sm:flex-row sm:justify-end items-stretch sm:items-center gap-2">
                <button
                  onClick={handleDownloadAll}
                  disabled={downloadingAll}
                  className="btn-ghost px-3 py-2 text-xs"
                  title="Baixar todos os cortes num ZIP"
                >
                  {downloadingAll
                    ? <><Loader2 size={14} className="animate-spin" />juntando…</>
                    : <><Download size={14} />baixar todos</>}
                </button>
              </div>
            )}
          </div>

          {status === 'complete' && results?.clips?.length > 0 && jobRetentionSeconds > 0 && (
            // Só aparece se alguém ligou a limpeza por idade
            // (JOB_RETENTION_SECONDS): o padrão deste fork é nunca apagar.
            <div className="mb-2 px-3 py-2.5 rounded-input bg-paper3 border border-paper3 text-sm">
              <span className="text-ink">Os cortes ficam guardados por {formatRetention(jobRetentionSeconds)} e depois são apagados.</span>{' '}
              <span className="text-muted">Baixe o que quiser manter, ou aumente o JOB_RETENTION_SECONDS no .env.</span>
            </div>
          )}

          <div className="flex-1 overflow-y-auto custom-scrollbar p-1">
            {results && results.clips && results.clips.length > 0 ? (
              <div className={`grid gap-4 pb-10 ${status === 'complete' ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1'}`}>
                {rankedClips.map(({ clip, index: i }) => (
                  <ResultCard
                    key={`${jobId}-${i}-${clip.video_url || ''}`}
                    clip={clip}
                    index={i}
                    jobId={jobId}
                    onEditClip={(index) => setEditingClip(index)}
                    onReframeClip={(index) => setReframingClip(index)}
                    geminiApiKey={apiKey}
                    geminiNoMotor={geminiNoMotor}
                    onPlay={(time) => handleClipPlay(time)}
                    onPause={() => setIsSyncedPlaying(false)}
                    onBulkSubtitle={handleBulkSubtitles}
                    clipCount={results.clips.length}
                    bulkProgress={bulkSub}
                  />
                ))}
              </div>
            ) : status === 'processing' ? (
              <div className="h-full min-h-[140px] flex flex-col items-center justify-center text-muted space-y-3 text-center px-4">
                <Loader2 size={28} className="animate-spin text-brass" />
                <p className="text-sm lowercase">esperando os cortes…</p>
                <p className="text-xs text-muted/80 max-w-[26ch] leading-snug">
                  Eles aparecem aqui um a um, conforme cada um termina.
                </p>
              </div>
            ) : status === 'error' ? (
              <div className="h-full min-h-[120px] flex flex-col items-center justify-center text-center gap-2 px-4">
                <p className="text-danger">O processamento falhou.</p>
                <p className="text-muted text-xs max-w-[32ch]">O log ao lado diz onde. Copie e cole na conversa para pedir ajuda.</p>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {editingClip !== null && results?.clips?.[editingClip] && (
        <ClipEditor
          jobId={jobId}
          clipIndex={editingClip}
          clipTitle={results.clips[editingClip].video_title_for_youtube_short || ''}
          onClose={() => setEditingClip(null)}
          onRerendered={handleClipRerendered}
        />
      )}
      {reframingClip !== null && results?.clips?.[reframingClip] && (
        <ReframeEditor
          jobId={jobId}
          clipIndex={reframingClip}
          clipTitle={results.clips[reframingClip].video_title_for_youtube_short || ''}
          onClose={() => setReframingClip(null)}
          onReframed={handleClipRerendered}
        />
      )}
    </div>
  );
}
