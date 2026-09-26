import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { FolderOpen, ArrowLeft, Youtube, Instagram, Share2, ChevronDown, Check, Activity, LayoutDashboard, Settings, Plus, History, X, Terminal, Shield, Image, RotateCcw, AlertTriangle, KeyRound, Copy, Loader2, Download, Menu } from 'lucide-react';
import ChavesDeIA from './components/ChavesDeIA';
import MediaInput from './components/MediaInput';
import ProjectsList from './components/ProjectsList';
import ProjectsGrid from './components/ProjectsGrid';
import PublicacoesTab from './components/PublicacoesTab';
import Tranca from './components/Tranca';
import McpConnectCard from './components/McpConnectCard';
import Versoes from './components/Versoes';
import { seloDaIA } from './lib/seloDaIA';
import ResultCard from './components/ResultCard';
import ProcessingAnimation from './components/ProcessingAnimation';
import ThumbnailStudio from './components/ThumbnailStudio';
import ClipEditor from './components/ClipEditor';
import ReframeEditor from './components/ReframeEditor';
import Modal from './components/ui/Modal';
import { useAuth } from './contexts/AuthContext';
import { apiFetch } from './lib/api';
import { API_BASE_URL } from './config';
import { URL_DO_INSTALADOR } from './lib/ajudante';
import AvisoDoMotor from './components/AvisoDoMotor';
import { useAquecerTranscricao } from './lib/aquecerTranscricao';

// Simple TikTok icon sine Lucide might not have it or it varies
const TikTokIcon = ({ size = 16, className = "" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className}>
    <path d="M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743l-.002-.001.002.001a2.895 2.895 0 0 1 3.183-4.51v-3.5a6.329 6.329 0 0 0-5.394 10.692 6.33 6.33 0 0 0 10.857-4.424V8.687a8.182 8.182 0 0 0 4.773 1.526V6.79a4.831 4.831 0 0 1-1.003-.104z" />
  </svg>
);

const formatRetention = (seconds) => {
  if (seconds >= 86400) return `${Math.round(seconds / 86400)} dia${seconds >= 172800 ? 's' : ''}`;
  if (seconds >= 3600) return `${Math.round(seconds / 3600)} hora${seconds >= 7200 ? 's' : ''}`;
  return `${Math.max(1, Math.round(seconds / 60))} min`;
};


const SESSION_KEY = 'openshorts_session';
// Matches the self-host JOB_RETENTION_SECONDS default. A restore whose job was
// already purged server-side fails gracefully and clears the saved session.
// (Neste fork o projeto nao e mais apagado por idade: isto so decide se a tela
// reabre sozinha o ultimo projeto. Depois de 24h ele segue na aba Projetos.)
const SESSION_MAX_AGE = 86400000; // 24 hours

// Erro proprio para "esse job nao existe mais", que e diferente de "a rede
// falhou". A distincao importa: erro de rede se tenta de novo, job inexistente
// nao -- insistir nele e o que prendia a tela para sempre.
class JobSumiu extends Error {}

// Uma linha do log e texto puro ou { texto, t }. O backend carimba a hora em
// que cada linha NASCEU (`log_times`, epoch); antes a tela escrevia
// `new Date()` ao desenhar, e todas as linhas saiam com a hora de quem olhava.
// Linha escrita pelo proprio painel ("Starting process...") fica sem hora:
// melhor sem hora do que com a hora errada, que era o defeito.
const linhasDoStatus = (data) => {
  const linhas = data?.logs || [];
  const horas = data?.log_times;
  if (!Array.isArray(horas) || horas.length !== linhas.length) return linhas;
  return linhas.map((texto, i) => (horas[i] ? { texto, t: horas[i] } : texto));
};
const textoDaLinha = (linha) => (typeof linha === 'string' ? linha : linha.texto);
const horaDaLinha = (linha) =>
  (typeof linha === 'string' || !linha.t ? '' : new Date(linha.t * 1000).toLocaleTimeString());

// Enquanto `/api/config` não responde. Era uma tela vazia -- e, com a config
// agora esperada até o servidor responder, "vazia" viraria "preta para
// sempre" se o backend não subir. Diz o que está acontecendo e, se demorar,
// o que fazer.
//
// No site do Cloudflare (`build:site`) há uma causa a mais, e a mais provável
// na primeira visita: o Chrome pergunta se o site pode falar com este
// computador, e um "Bloquear" por engano deixa esta tela girando para sempre
// sem erro nenhum. O servidor nunca fica sabendo -- só a tela pode dizer.
const ABERTO_PELO_SITE = /^https?:\/\//.test(API_BASE_URL);

function EsperandoServidor() {
  // No site, quem chega pela primeira vez não tem motor nenhum: esperar os
  // 15 s do Docker para dizer o que fazer seria 15 s olhando um "conectando"
  // que nunca termina. Quem já tem o ajudante aberto não chega a ver isto --
  // a config responde antes.
  const [demorou, setDemorou] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDemorou(true), ABERTO_PELO_SITE ? 4000 : 15000);
    return () => clearTimeout(t);
  }, []);

  if (ABERTO_PELO_SITE) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center p-6">
        <div className="max-w-md text-center space-y-4">
          {/* A primeira coisa que quem chega pelo site vê: a marca, antes de
              qualquer explicação. */}
          <img src="/virtu-clips.png" alt="Virtu Clips" className="mx-auto h-20 w-auto mb-2" />
          <p className="flex items-center justify-center gap-2 text-sm text-ink2">
            <Loader2 size={15} className="animate-spin text-brass" /> procurando o Virtu Clips neste computador…
          </p>
          {demorou && (
            <>
              <p className="text-sm text-ink2 leading-relaxed">
                Este site é só a tela. Quem baixa, transcreve e corta os vídeos é um
                programa no seu computador, que usa a placa de vídeo se houver.
              </p>
              <a href={URL_DO_INSTALADOR} className="btn-primary px-4 py-2 text-sm inline-flex">
                <Download size={15} /> Baixar o Virtu Clips para Windows
              </a>
              <p className="text-xs text-muted leading-relaxed">
                Abra o arquivo baixado: ele instala tudo sem pedir administrador (leva
                alguns minutos) e abre este site sozinho. Se o Windows disser que
                protegeu o computador, clique em “Mais informações” e depois em
                “Executar assim mesmo”.
              </p>
              <div className="text-xs text-muted leading-relaxed space-y-1.5 text-left border-t border-rule pt-3">
                <p>
                  <span className="text-ink2">Já instalou?</span> Abra o Virtu Clips pelo menu
                  Iniciar; o ícone dele fica perto do relógio.
                </p>
                <p>
                  <span className="text-ink2">O navegador perguntou</span> se este site pode
                  acessar apps e serviços deste dispositivo? A resposta é Permitir. Se
                  bloqueou, libere no ícone à esquerda do endereço e recarregue a página.
                </p>
                <p>
                  <span className="text-ink2">Usa o Docker?</span> Abra o Docker Desktop ou
                  rode atalhos\subir.bat.
                </p>
                <p>Mac e Linux ainda não têm o ajudante.</p>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-paper flex items-center justify-center p-6">
      <div className="max-w-sm text-center space-y-2">
        <p className="flex items-center justify-center gap-2 text-sm text-ink2">
          <Loader2 size={15} className="animate-spin text-brass" /> conectando ao servidor…
        </p>
        {demorou && (
          <p className="text-xs text-muted leading-relaxed">
            Logo depois de atualizar, o servidor leva alguns segundos para subir.
            Se passar de um minuto, confira se o Docker Desktop está aberto e rode
            atalhos\subir.bat.
          </p>
        )}
      </div>
    </div>
  );
}

const pollJob = async (jobId) => {
  const res = await apiFetch(`/api/status/${jobId}`);
  if (res.status === 404) throw new JobSumiu('job não existe mais');
  if (!res.ok) throw new Error('Status check failed');
  return res.json();
};

function App() {
  const { isSignedIn, jobRetentionSeconds, localLlm, geminiNoMotor, configCarregada, authAtiva, motor, loading: authLoading } = useAuth();
  // Segura o modelo de transcrição na placa enquanto esta aba estiver aberta.
  // Só depois da config, e só com sessão quando a instalação tem senha: antes
  // disso o servidor responderia 401 a cada dois minutos.
  useAquecerTranscricao(configCarregada && (!authAtiva || isSignedIn));
  const [apiKey, setApiKey] = useState(localStorage.getItem('gemini_key') || '');
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState('idle'); // idle, processing, complete, error
  // Progresso vem do backend por estagio, nao por porcentagem: o pipeline sabe
  // onde esta, nao quanto falta dentro do estagio (a transcricao nao reporta
  // nada, e o render varia com o numero de cortes). Ver `_stage_view` no app.py.
  const [stage, setStage] = useState(null);   // { label, index, total }
  const [cancelling, setCancelling] = useState(false);
  // Incrementado ao voltar para a tela inicial, para a lista refletir o job que
  // acabou de terminar/ser cancelado sem depender do polling de 5s dela.
  const [projectsKey, setProjectsKey] = useState(0);
  const [logsCopied, setLogsCopied] = useState(false);
  const [results, setResults] = useState(null);
  // Best clips first. The backend hands them back in transcript order, which
  // buries the strongest one wherever it happens to fall in the video — and
  // the first card is the one people actually watch and publish.
  //
  // The ORIGINAL array position travels with each clip and is what gets passed
  // down as `index`: it is the clip's identity everywhere else (clip_index on
  // /api/subtitle, /api/edit and publishing, the clip-N.mp4 download name, the
  // saved per-clip project state). Sorting the array itself would silently
  // repoint all of that at the wrong clip.
  const rankedClips = useMemo(() => {
    const clips = results?.clips;
    if (!Array.isArray(clips)) return [];
    return clips
      .map((clip, index) => ({ clip, index }))
      .sort((a, b) => {
        const sa = Number.isFinite(a.clip?.predicted_score) ? a.clip.predicted_score : -1;
        const sb = Number.isFinite(b.clip?.predicted_score) ? b.clip.predicted_score : -1;
        // Ties (and clips with no score at all) keep transcript order.
        return sb - sa || a.index - b.index;
      });
  }, [results]);
  // Bulk subtitles: apply one style to every clip of the job (triggered from
  // within a clip's subtitle modal via "apply to all").
  const [bulkSub, setBulkSub] = useState({ running: false, current: 0, total: 0, errors: 0 });
  const [downloadingAll, setDownloadingAll] = useState(false);
  // Pre-flight quality gate: { info: {max_height, min_height, cookies_invalid}, data }
  const [qualityGate, setQualityGate] = useState(null);
  const [logs, setLogs] = useState([]);
  // Collapsed on phones: the log tail is the least useful thing on a 360px
  // screen and it was pushing the actual clips a full scroll down.
  const [logsVisible, setLogsVisible] = useState(() => {
    try { return window.innerWidth >= 768; } catch { return true; }
  });
  const [processingMedia, setProcessingMedia] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard'); // dashboard, settings
  // Mobile only: the full nav lives in a drawer behind the header's menu button.
  const [navOpen, setNavOpen] = useState(false);
  const [sessionRecovered, setSessionRecovered] = useState(false);
  // Clip editor overlay: index of the clip being edited, or null.
  const [editingClip, setEditingClip] = useState(null);
  const [reframingClip, setReframingClip] = useState(null);

  // Sync state for original video playback
  const [syncedTime, setSyncedTime] = useState(0);
  const [isSyncedPlaying, setIsSyncedPlaying] = useState(false);
  const [syncTrigger, setSyncTrigger] = useState(0);

  const handleClipPlay = (startTime) => {
    setSyncedTime(startTime);
    setIsSyncedPlaying(true);
    setSyncTrigger(prev => prev + 1);
  };

  const handleClipPause = () => {
    setIsSyncedPlaying(false);
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
    if (!jobId) return;
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
      alert(`Download failed: ${e.message}`);
    } finally {
      setDownloadingAll(false);
    }
  };

  // Session Recovery: Restore on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(SESSION_KEY);
      if (!saved) return;
      const session = JSON.parse(saved);
      if (Date.now() - session.timestamp > SESSION_MAX_AGE) {
        localStorage.removeItem(SESSION_KEY);
        return;
      }
      if (session.jobId && session.status && session.status !== 'idle') {
        setJobId(session.jobId);
        setResults(session.results || null);
        // Restore the source preview. Older sessions (or uploads) saved no
        // media, so fall back to the backend-served source for this job.
        if (session.processingMedia) setProcessingMedia(session.processingMedia);
        else setProcessingMedia({ type: 'server', payload: `/api/source/${session.jobId}` });
        if (session.activeTab) setActiveTab(session.activeTab);
        // If was processing, resume polling; if complete/error, just show results
        setStatus(session.status === 'processing' ? 'processing' : session.status);
        setSessionRecovered(true);
        setTimeout(() => setSessionRecovered(false), 5000);
      }
    } catch (e) {
      localStorage.removeItem(SESSION_KEY);
    }
  }, []);

  // Session Recovery: Save state changes
  useEffect(() => {
    if (status === 'idle') {
      localStorage.removeItem(SESSION_KEY);
      return;
    }
    try {
      // URL (YouTube) media serializes as-is. Uploaded 'file' media is a blob
      // that can't be persisted, so point the recovered preview at the source
      // served by the backend instead of dropping it.
      let persistMedia = null;
      if (processingMedia?.type === 'url') persistMedia = processingMedia;
      else if (processingMedia && jobId) persistMedia = { type: 'server', payload: `/api/source/${jobId}` };
      const sessionData = {
        jobId,
        status,
        results,
        processingMedia: persistMedia,
        activeTab,
        timestamp: Date.now()
      };
      localStorage.setItem(SESSION_KEY, JSON.stringify(sessionData));
    } catch (e) {
      // localStorage full or serialization error - ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, status, results, activeTab]);

  useEffect(() => {
    // A chave do Gemini no NAVEGADOR é a de antes das chaves no programa
    // (ChavesDeIA): a tela a leva para lá e a esquece aqui -- e esquecer tem de
    // apagar, ou ela voltaria no próximo F5 e seguiria indo no `X-Gemini-Key`.
    try {
      if (apiKey) localStorage.setItem('gemini_key', apiKey);
      else localStorage.removeItem('gemini_key');
    } catch { /* localStorage bloqueado: vale só nesta aba */ }
  }, [apiKey]);

  // Declarado aqui, e nao mais abaixo: o efeito de polling passou a depender
  // dele para limpar a sessao de um job que sumiu, e `const` nao sofre
  // hoisting -- no array de dependencias ele cairia na zona morta temporal.
  const handleReset = useCallback(() => {
    setStatus('idle');
    setJobId(null);
    setResults(null);
    setLogs([]);
    setProcessingMedia(null);
    setStage(null);
    // Voltar para a tela inicial e o momento em que a lista precisa estar certa:
    // o job que acabou de terminar tem de aparecer nela sem esperar o polling.
    setProjectsKey((k) => k + 1);
    localStorage.removeItem(SESSION_KEY);
  }, []);

  // Um projeto apagado na aba Projetos pode ser o que está aberto no Clip
  // Generator. Sem isto a tela continuava mostrando os cortes dele -- a pessoa
  // apagava, voltava, e o projeto "ainda estava lá". A sessão salva no
  // localStorage sai junto (o `handleReset` cuida), senão ele voltava no F5.
  const handleProjetoApagado = useCallback((id) => {
    if (id === jobId) handleReset();
  }, [jobId, handleReset]);

  // Abre um projeto da lista: carrega o estado dele e entra no modo certo.
  // Um job ainda rodando volta para 'processing', e o efeito de polling faz o
  // resto -- e por isso que reabrir um job em andamento retoma a barra em vez
  // de mostrar uma tela morta.
  const handleOpenProject = useCallback(async (id) => {
    try {
      const res = await apiFetch(`/api/status/${id}`);
      if (!res.ok) throw new Error('não consegui abrir');
      const data = await res.json();
      setJobId(id);
      setLogs(linhasDoStatus(data));
      setResults(data.result || null);
      setStage(data.stage_index
        ? { label: data.stage_label, index: data.stage_index, total: data.stage_total }
        : null);
      if (data.status === 'completed') setStatus('complete');
      else if (data.status === 'failed') setStatus('error');
      else setStatus('processing');
    } catch (e) {
      console.error('Open project failed', e);
    }
  }, []);

  // Cancela de verdade: o backend mata o subprocesso E apaga o manifesto de
  // resume. Sem o segundo passo o job voltava sozinho 30s depois (ver o
  // endpoint em app.py).
  const handleCancel = useCallback(async () => {
    if (!jobId || cancelling) return;
    setCancelling(true);
    try {
      await apiFetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
      setStatus('idle');
      setStage(null);
      setResults(null);
      setProjectsKey((k) => k + 1);
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

  useEffect(() => {
    let interval;
    if ((status === 'processing' || status === 'completed') && jobId) {
      interval = setInterval(async () => {
        try {
          const data = await pollJob(jobId);
          console.log("Job status:", data);

          // Update results if available (real-time)
          if (data.result) {
            setResults(data.result);
          }

          if (data.stage_index) {
            setStage({ label: data.stage_label, index: data.stage_index, total: data.stage_total });
          }

          if (data.status === 'cancelled') {
            // Desfecho proprio, nao erro: quem clicou em cancelar nao deve ver
            // a tela vermelha de falha.
            setStatus('idle');
            setStage(null);
            setCancelling(false);
            clearInterval(interval);
          } else if (data.status === 'completed') {
            // O fim do log (o resumo de tempo do job) sai entre o ultimo poll
            // e este: sem isto, so aparecia reabrindo o projeto.
            if (data.logs) setLogs(linhasDoStatus(data));
            setStatus('complete');
            clearInterval(interval);
          } else if (data.status === 'failed') {
            setStatus('error');
            const errorMsg = data.error || (data.logs && data.logs.length > 0 ? data.logs[data.logs.length - 1] : "Process failed");
            setLogs(prev => [...(data.logs ? linhasDoStatus(data) : prev), "Error: " + errorMsg]);
            clearInterval(interval);
          } else {
            // Update logs if available
            if (data.logs) setLogs(linhasDoStatus(data));
          }
        } catch (e) {
          if (e instanceof JobSumiu) {
            // A sessao restaurada aponta para um job que nao existe mais: o
            // container foi recriado, a pasta foi apagada, ou ele expirou na
            // limpeza por idade. Antes disto o poll batia num 404 a cada 2s
            // para sempre, e a tela ficava presa em "preparando…" com a lista
            // de projetos escondida atras de um job fantasma.
            console.warn('Job não existe mais; limpando a sessão.');
            clearInterval(interval);
            handleReset();
            return;
          }
          console.error("Polling error", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [status, jobId, handleReset]);


  // A chave do navegador, um LLM local (LLM_BASE_URL) ou a do programa deste
  // computador bastam para o motor achar os momentos.
  // `geminiNoMotor`: a chave colada nas Configurações mora no programa deste
  // computador, e não no navegador (chaves_ia.py).
  const geminiOk = !!apiKey || !!localLlm || geminiNoMotor;
  // So com a config em mãos: antes dela, `localLlm` nulo quer dizer "ainda não
  // sei", não "não tem". Confundir os dois era o aviso de chave que aparecia
  // logo depois do atualizar.bat e sumia no F5.
  const keysMissing = configCarregada && !geminiOk;

  const handleProcess = async (data, forceLowQuality = false) => {
    if (keysMissing) {
      setShowKeyModal(true);
      return;
    }
    setStatus('processing');
    setLogs(["Starting process..."]);
    setResults(null);
    // Studio handovers have no local media object; the preview switches to the
    // backend-served source once the job id is known.
    setProcessingMedia(data.type === 'thumbnail_session' ? null : data);
    setQualityGate(null);

    try {
      let body;
      // A chave do navegador vai no cabeçalho; a do programa, o motor já tem.
      const headers = apiKey ? { 'X-Gemini-Key': apiKey } : {};

      // Advanced generation controls: only sent when the user set them, so the
      // default request stays byte-identical to the pre-feature one.
      const advanced = {
        target_clips: data.targetClips || null,
        clip_min_seconds: data.clipMinSeconds || null,
        clip_max_seconds: data.clipMaxSeconds || null,
        // Sent explicitly both ways: absent means off for raw API callers,
        // but the dashboard always states the user's choice.
        auto_hook: data.autoHook ? '1' : '0',
        auto_hook_style: data.autoHook ? (data.autoHookStyle || 'classic') : null,
        // 'auto' is the server default, so only a deliberate choice travels.
        layouts: data.layout && data.layout !== 'auto' ? data.layout : null,
      };

      if (data.type === 'url') {
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({
          url: data.payload,
          acknowledged: !!data.acknowledged,
          output_format: data.outputFormat || 'auto',
          force_low_quality: forceLowQuality,
          ...Object.fromEntries(Object.entries(advanced).filter(([, v]) => v != null)),
        });
      } else if (data.type === 'thumbnail_session') {
        // Handover from Thumbnail Studio (issue #68): the video and transcript
        // already live server-side, keyed by the Studio session.
        headers['Content-Type'] = 'application/json';
        body = JSON.stringify({
          thumbnail_session_id: data.payload,
          acknowledged: !!data.acknowledged,
          output_format: data.outputFormat || 'auto',
          ...Object.fromEntries(Object.entries(advanced).filter(([, v]) => v != null)),
        });
      } else {
        const formData = new FormData();
        formData.append('file', data.payload);
        formData.append('acknowledged', data.acknowledged ? 'true' : 'false');
        formData.append('output_format', data.outputFormat || 'auto');
        for (const [k, v] of Object.entries(advanced)) {
          if (v != null) formData.append(k, v);
        }
        body = formData;
      }

      const res = await apiFetch('/api/process', { method: 'POST', headers, body });

      if (!res.ok) throw new Error(await res.text());
      const resData = await res.json();

      // Quality gate: the source is below the min resolution — ask before burning
      // 20 min on it. On confirm we resend with force_low_quality.
      if (resData.needs_confirmation) {
        setStatus('idle');
        setQualityGate({ info: resData.quality_check, data });
        return;
      }

      setJobId(resData.job_id);
      if (data.type === 'thumbnail_session') {
        setProcessingMedia({ type: 'server', payload: `/api/source/${resData.job_id}` });
      }

    } catch (e) {
      setStatus('error');
      setLogs(l => [...l, `Error starting job: ${e.message}`]);
    }
  };

  // --- UI Components ---

  // One nav definition drives all three surfaces: the desktop rail, the mobile
  // drawer, and the bottom tab bar. `short` is the tab-bar label — the full one
  // wraps to two lines in a 5-up bar on a 360px phone.
  //
  // O `ord` é o número que aparece à direita de cada item, e ele é **calculado
  // pela posição**, não escrito à mão. Escrito à mão era o que estava aqui, e
  // a lista mostrava `01 03 05 07`: os pares eram as abas AI Shorts, UGC
  // Gallery e History, que saíram com as dependências pagas (Fase 0.3) e com o
  // módulo comercial (ADR-001), deixando buracos que não querem dizer nada
  // para quem olha. Numerar pela posição também acerta sozinho o caso do
  // `history`, que só existe em modo cloud: sem ele os números seguem
  // seguidos, com ele também.
  const navItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: 'Clip Generator', short: 'clips', primary: true },
    { id: 'projects', icon: FolderOpen, label: 'Projetos', short: 'projetos', primary: true },
    { id: 'thumbnails', icon: Image, label: 'YouTube Studio', short: 'studio', primary: true },
    { id: 'publicar', icon: Share2, label: 'Publicação', short: 'publicar', primary: true },
    { id: 'settings', icon: Settings, label: 'Configurações', short: 'config' },
  ].map((item, i) => ({ ...item, ord: String(i + 1).padStart(2, '0') }));
  const activeNav = navItems.find((n) => n.id === activeTab);

  // Escape closes the mobile drawer. The shell itself is overflow-hidden, so
  // there is no body scroll to lock behind it.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') setNavOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [navOpen]);

  const goToTab = (id) => {
    setActiveTab(id);
    setNavOpen(false);
  };

  // Shared footer links (landing, repo, pricing, contact) — same list in the
  // desktop rail and the mobile drawer, so they can never drift apart.
  const NavFooterLinks = ({ collapsed = false }) => (
    <>
      <a
        href="https://github.com/JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System"
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-2 px-3 py-2 text-xs lowercase text-muted hover:text-ink2 transition-colors"
      >
        <svg height="14" viewBox="0 0 16 16" version="1.1" width="14" aria-hidden="true" fill="currentColor" className="shrink-0"><path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>
        <span className={collapsed ? 'hidden lg:block truncate' : 'truncate'}>open source</span>
      </a>
    </>
  );

  // Desktop rail: icon-only from md, labelled from lg. Below md it is gone
  // entirely — an unlabelled 80px rail ate a fifth of a phone screen.
  const Sidebar = () => (
    <div className="hidden md:flex w-20 lg:w-64 bg-paper2 border-r border-rule flex-col h-full shrink-0 transition-all duration-300">
      {/* A marca: a logo inteira quando a barra tem rótulo (lg), e o V dela
          no trilho estreito (md), onde a logo seria um borrão de 32 px. */}
      <a href="#app" className="p-6 pb-4 flex items-center" title="início">
        <img src="/favicon.png" alt="Virtu Clips" className="w-8 h-8 rounded-input shrink-0 lg:hidden" />
        <img src="/virtu-clips.png" alt="Virtu Clips" className="hidden lg:block h-12 w-auto" />
      </a>

      <nav className="flex-1 px-4 py-4 space-y-1">
        {navItems.map((item) => {
          const NavIcon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => goToTab(item.id)}
              title={item.label}
              className={`relative w-full flex items-center gap-3 px-3 py-2.5 rounded-input transition-colors ${isActive ? 'bg-paper3 text-ink' : 'text-muted hover:text-ink2 hover:bg-paper3/50'}`}
            >
              {isActive && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-brass rounded-full" aria-hidden="true" />
              )}
              <NavIcon size={18} className={`shrink-0 ${isActive ? 'text-brass' : ''}`} />
              <span className="text-sm lowercase hidden lg:block flex-1 text-left truncate">{item.label}</span>
              <span className="readout hidden lg:block">{item.ord}</span>
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-rule space-y-1">
        <NavFooterLinks collapsed />
      </div>
    </div>
  );

  // Mobile drawer: the complete nav, reachable from the header's menu button.
  const MobileNavDrawer = () => (
    <div
      className="md:hidden fixed inset-0 z-[90] flex"
      role="dialog"
      aria-modal="true"
      aria-label="Navigation"
    >
      <div
        className="absolute inset-0 bg-black/60 animate-fade"
        onClick={() => setNavOpen(false)}
        aria-hidden="true"
      />
      <div className="relative w-[17rem] max-w-[82vw] h-full bg-paper2 border-r border-rule flex flex-col animate-slide-in-left">
        <div className="flex items-center justify-between px-5 h-14 border-b border-rule shrink-0">
          <a href="#app" className="flex items-center" onClick={() => setNavOpen(false)}>
            <img src="/virtu-clips.png" alt="Virtu Clips" className="h-8 w-auto" />
          </a>
          <button
            onClick={() => setNavOpen(false)}
            aria-label="close navigation"
            className="p-2 -mr-2 text-muted hover:text-ink transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3 space-y-1">
          {navItems.map((item) => {
            const NavIcon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => goToTab(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`relative w-full flex items-center gap-3 px-3 py-3 rounded-input transition-colors ${isActive ? 'bg-paper3 text-ink' : 'text-muted active:bg-paper3/60'}`}
              >
                {isActive && (
                  <span className="absolute left-0 top-2 bottom-2 w-0.5 bg-brass rounded-full" aria-hidden="true" />
                )}
                <NavIcon size={18} className={`shrink-0 ${isActive ? 'text-brass' : ''}`} />
                <span className="text-[0.95rem] lowercase flex-1 text-left truncate">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="px-3 py-3 border-t border-rule space-y-0.5 safe-bottom shrink-0">
          <NavFooterLinks />
        </div>
      </div>
    </div>
  );

  // Bottom tab bar: the four everyday destinations plus "more" for the rest.
  // It is a flex sibling of the scrolling pane rather than `fixed`, so nothing
  // ever hides behind it and no pane needs compensating padding.
  const MobileTabBar = () => {
    const tabs = navItems.filter((n) => n.primary);
    const moreActive = !tabs.some((t) => t.id === activeTab);
    return (
      <nav className="md:hidden shrink-0 border-t border-rule bg-paper2/95 backdrop-blur-sm safe-bottom">
        <div className="flex items-stretch">
          {tabs.map((item) => {
            const NavIcon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => goToTab(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] transition-colors ${isActive ? 'text-ink' : 'text-muted active:text-ink2'}`}
              >
                <NavIcon size={19} className={isActive ? 'text-brass' : ''} />
                <span className="text-[10.5px] lowercase leading-none truncate max-w-full px-0.5">{item.short}</span>
              </button>
            );
          })}
          <button
            onClick={() => setNavOpen(true)}
            aria-label="more sections"
            aria-expanded={navOpen}
            className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] transition-colors ${moreActive ? 'text-ink' : 'text-muted active:text-ink2'}`}
          >
            <Menu size={19} className={moreActive ? 'text-brass' : ''} />
            <span className="text-[10.5px] lowercase leading-none">more</span>
          </button>
        </div>
      </nav>
    );
  };

  // A tranca da Fase 4, antes de qualquer outra coisa. Com a auth ligada e sem
  // sessão, o painel inteiro dá lugar à tela de entrada — não adianta desenhar
  // abas cujas chamadas todas voltariam 401.
  //
  // `authLoading` importa: sem ele, a primeira renderização (antes de
  // `/api/config` responder) mostraria a tela de login por um instante para
  // quem já está logado, e pior, para quem nem tem auth ligada.
  if (authLoading) {
    return <EsperandoServidor />;
  }
  if (authAtiva && !isSignedIn) {
    return <Tranca />;
  }

  return (
    /* h-dvh where supported: on mobile Safari/Chrome `100vh` is the tallest the
       viewport ever gets, so a h-screen shell hides its own bottom bar behind
       the browser chrome until the user scrolls. */
    <div className="flex h-screen supports-[height:100dvh]:h-[100dvh] bg-paper overflow-hidden">
      <Sidebar />
      {navOpen && <MobileNavDrawer />}

      <main className="flex-1 min-w-0 flex flex-col h-full overflow-hidden relative">
        {/* Top Header */}
        <header className="h-14 border-b border-rule bg-paper flex items-center justify-between gap-2 px-3 sm:px-6 shrink-0 z-10">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0">
            {/* Mobile: the drawer handle, and the section name the icon rail
                used to carry. Without it a phone has no "where am I". */}
            <button
              onClick={() => setNavOpen(true)}
              aria-label="open navigation"
              className="md:hidden -ml-1 p-2 rounded-input text-muted active:bg-paper3 transition-colors shrink-0"
            >
              <Menu size={20} />
            </button>
            <span className="md:hidden font-display uppercase tracking-wide text-base text-ink truncate">
              {activeNav?.label || 'Virtu Clips'}
            </span>
            {/* Dentro de um projeto, o que falta e VOLTAR -- o unico botao
                aqui dizia "New Project", que cria em vez de voltar, e nao
                havia caminho nenhum de um projeto aberto para escolher outro.
                Agora sao dois, e o de voltar vem primeiro. */}
            {status !== 'idle' && (
              <>
                <button
                  onClick={() => { handleReset(); goToTab('projects'); }}
                  className="btn-quiet px-3 py-1.5 text-xs shrink-0"
                  aria-label="Voltar aos projetos"
                >
                  <ArrowLeft size={14} />
                  <span className="hidden sm:inline">projetos</span>
                </button>
                <button
                  onClick={handleReset}
                  className="btn-quiet px-3 py-1.5 text-xs shrink-0"
                  aria-label="Novo projeto"
                >
                  <Plus size={14} />
                  <span className="hidden sm:inline">novo</span>
                </button>
              </>
            )}
          </div>

          <div className="flex items-center gap-2 sm:gap-4 shrink-0">

            {/* Hidden below sm: the standing banner underneath already says the
                same thing, and two warnings in a 360px header is just noise. */}
            {keysMissing && (
              <button
                onClick={() => goToTab('settings')}
                className="badge-warn hover:brightness-125 transition-all hidden sm:inline-flex"
                title="Colocar uma chave de IA"
              >
                <AlertTriangle size={12} />
                <span className="hidden md:inline">
                  falta a chave de IA
                </span>
                <span className="md:hidden">sem chave</span>
              </button>
            )}
          </div>
        </header>

        {/* Persistent Missing Keys Banner — visible on every screen */}
        {keysMissing && activeTab !== 'settings' && (
          <div className="mx-3 sm:mx-6 mt-3 px-3.5 sm:px-4 py-3 bg-paper2 border border-rule rounded-card flex flex-wrap items-center justify-between gap-2.5 sm:gap-4 shrink-0 animate-fade">
            <div className="flex items-start sm:items-center gap-2.5 sm:gap-3 text-sm text-ink2 min-w-0 flex-1">
              <KeyRound size={16} className="shrink-0 text-warn mt-0.5 sm:mt-0" />
              <div className="min-w-0">
                <span className="font-medium text-ink">Falta uma chave de IA.</span>{' '}
                <span className="text-muted">
                  O Virtu Clips usa IAs gratuitas para achar os melhores momentos. A chave é grátis e leva um minuto.
                </span>
              </div>
            </div>
            <button
              onClick={() => goToTab('settings')}
              className="btn-quiet px-3 py-1.5 text-xs shrink-0 w-full sm:w-auto"
            >
              colocar a chave
            </button>
          </div>
        )}

        {/* O motor atrás do site, com o botão que o atualiza (Docker e ajudante). */}
        <AvisoDoMotor motor={motor} />

        {/* Session Recovery Banner */}
        {sessionRecovered && (
          <div className="mx-3 sm:mx-6 mt-2 px-3.5 sm:px-4 py-3 bg-paper2 border border-rule rounded-card flex items-start justify-between gap-3 animate-fade shrink-0">
            <div className="flex items-start sm:items-center gap-2 text-sm text-ink2 flex-wrap min-w-0">
              <RotateCcw size={16} className="text-brass shrink-0 mt-0.5 sm:mt-0" />
              <span className="font-medium">Session recovered</span>
              <span className="text-muted text-xs">Your previous work has been restored.</span>
            </div>
            <button
              onClick={() => setSessionRecovered(false)}
              aria-label="dismiss"
              className="text-muted hover:text-ink transition-colors shrink-0 -m-1 p-1"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Main Workspace */}
        <div className="flex-1 overflow-hidden relative">

          {/* View: Settings */}
          {activeTab === 'settings' && (
            <div className="h-full overflow-y-auto p-4 sm:p-8 max-w-2xl mx-auto animate-fade">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
                <div>
                  <p className="eyebrow mb-1.5">{activeNav?.ord} · CONFIGURAÇÕES</p>
                  <h1 className="font-display uppercase tracking-wide text-2xl text-ink">Configurações</h1>
                </div>
                <div className="flex items-center gap-2 text-xs text-muted mt-1">
                  <Shield size={12} className="text-ok shrink-0" /> As chaves ficam no programa deste computador, não no site
                </div>
              </div>
              {/* As chaves primeiro: sem elas nada processa. */}
              <ChavesDeIA chaveDoNavegador={apiKey} esquecerChaveDoNavegador={() => setApiKey('')} />
              <div className="mb-6"><McpConnectCard /></div>
              {/* Por ultimo: e o que se copia para pedir ajuda, nao o que se usa. */}
              <Versoes />
            </div>
          )}


          {activeTab === 'thumbnails' && (
            <ThumbnailStudio
              geminiApiKey={apiKey}
              geminiNoMotor={geminiNoMotor}
              onCreateClips={(sessionId) => {
                setActiveTab('dashboard');
                // The Studio source is the user's own upload, published to their
                // own channel; the handover carries that same attestation.
                handleProcess({ type: 'thumbnail_session', payload: sessionId, acknowledged: true });
              }}
            />
          )}

          {activeTab === 'publicar' && <PublicacoesTab />}

          {activeTab === 'projects' && (
            <ProjectsGrid
              refreshKey={projectsKey}
              onNew={() => { handleReset(); goToTab('dashboard'); }}
              onOpen={(id) => { goToTab('dashboard'); handleOpenProject(id); }}
              onApagado={handleProjetoApagado}
            />
          )}

          {/* View: Dashboard (Idle) */}
          {activeTab === 'dashboard' && status === 'idle' && (
            <div className="h-full overflow-y-auto custom-scrollbar animate-fade">
              <div className="min-h-full flex flex-col items-center justify-center px-4 py-5 sm:p-6">
              {/* On a phone the hero used to fill the fold on its own and push
                  the uploader — the whole point of the screen — below it. The
                  eyebrow, the display size and the gaps all shrink first. */}
              <div className="max-w-xl w-full text-center space-y-5 sm:space-y-8">
                <div className="space-y-2.5 sm:space-y-4">
                  <p className="eyebrow hidden sm:block">01 · CLIP GENERATOR</p>
                  <h1 className="font-display uppercase tracking-wide text-3xl sm:text-4xl md:text-5xl text-ink">
                    Create Viral Shorts
                  </h1>
                  <p className="text-muted text-[15px] sm:text-lg leading-snug sm:leading-normal max-w-sm sm:max-w-none mx-auto">
                    Drop your long-form video below to instantly generate viral clips with AI.
                  </p>
                  {/* The same pipeline is an MCP server: point people at the
                      one place that explains how to drive it from an agent. */}
                  <p className="text-xs text-muted">
                    Ou deixe um agente de IA fazer:{' '}
                    <button
                      type="button"
                      onClick={() => goToTab('settings')}
                      className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors"
                    >
                      conectar o Claude, o Cursor ou o n8n →
                    </button>
                  </p>
                </div>

                <MediaInput onProcess={handleProcess} isProcessing={status === 'processing'} />

                {/* Some sozinha na primeira visita (a lista vazia nao renderiza
                    nada), entao a tela de quem nunca rodou um job continua
                    sendo so o formulario. */}
                <ProjectsList onOpen={handleOpenProject} onApagado={handleProjetoApagado} refreshKey={projectsKey} />

                <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-8 text-muted text-xs sm:text-sm">
                  <span className="flex items-center gap-2"><Youtube size={16} /> YouTube</span>
                  <span className="flex items-center gap-2"><Instagram size={16} /> Instagram</span>
                  <span className="flex items-center gap-2"><TikTokIcon size={16} /> TikTok</span>
                </div>
              </div>
              </div>
            </div>
          )}

          {/* View: Processing / Results (Split View) */}
          {activeTab === 'dashboard' && (status === 'processing' || status === 'complete' || status === 'error') && (
            <div className="h-full flex flex-col md:flex-row gap-3 md:gap-4 p-3 md:p-4 overflow-y-auto md:overflow-y-hidden custom-scrollbar animate-fade">

              {/* Left Panel: Preview & Status */}
              <div className={`${status === 'complete' ? 'w-full md:w-[30%] lg:w-[25%]' : 'w-full md:w-[55%] lg:w-[60%]'} md:h-full flex flex-col shrink-0 md:shrink card p-3.5 sm:p-6 md:overflow-y-auto custom-scrollbar transition-all duration-700 ease-in-out`}>
                <div className="mb-4 sm:mb-6 flex items-center justify-between gap-2">
                  <h2 className="text-sm font-medium text-ink lowercase flex items-center gap-2">
                    <Activity className={`text-brass ${status === 'processing' ? 'animate-pulse' : ''}`} size={18} />
                    Live Analysis
                  </h2>
                  <span className={status === 'processing' ? 'badge-brass' :
                    status === 'complete' ? 'badge-ok' :
                      'badge-danger'
                    }>
                    {status.toUpperCase()}
                  </span>
                </div>

                {/* Video Preview */}
                {processingMedia && (
                  <ProcessingAnimation
                    media={processingMedia}
                    isComplete={status === 'complete'}
                    syncedTime={syncedTime}
                    isSyncedPlaying={isSyncedPlaying}
                    syncTrigger={syncTrigger}
                  />
                )}

                {/* Phones only. The scan box drops its invented telemetry at
                    this size and the log terminal below starts collapsed, so
                    without this the screen would say nothing about what the job
                    is actually doing. The log tail is the real answer. */}
                {status === 'processing' && (
                  <div className="sm:hidden mb-3 flex items-start gap-2 text-xs text-ink2 min-w-0">
                    <Loader2 size={14} className="animate-spin text-brass shrink-0 mt-px" />
                    <span className="min-w-0 leading-snug break-words">
                      {logs.length ? textoDaLinha(logs[logs.length - 1]) : 'starting up…'}
                    </span>
                  </div>
                )}

                {/* Progresso e cancelamento. Antes daqui nao havia nem um nem
                    outro: o /api/status nao devolvia estagio nenhum, e o handle
                    do subprocesso so existia dentro de run_job, entao nada na
                    tela alcancava o job. Em CPU a transcricao fica minutos em
                    silencio, e silencio sem sinal e o que faz alguem recarregar
                    a pagina no meio de um render. */}
                {status === 'processing' && (
                  <div className="my-3 space-y-2">
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-ink2 min-w-0 truncate">
                        {stage
                          ? `${stage.index}/${stage.total} · ${stage.label}`
                          : 'preparando…'}
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
                    {/* Sem estagio ainda, a barra pulsa em vez de fingir 0%:
                        a fila nao sabe quanto falta e mentir seria pior. */}
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
                  {/* Dois botoes lado a lado, nao um dentro do outro: o
                      cabecalho inteiro era um <button>, e aninhar o de copiar
                      dentro dele seria HTML invalido. */}
                  <div className="w-full px-3.5 sm:px-4 py-2.5 border-b border-rule flex items-center justify-between gap-2 bg-paper2 shrink-0">
                    <button
                      type="button"
                      onClick={() => setLogsVisible(!logsVisible)}
                      aria-expanded={logsVisible}
                      className="flex items-center gap-2 min-w-0 text-left"
                    >
                      <span className="readout flex items-center gap-2">
                        <Terminal size={12} /> System Logs
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
                {/* Title + counters on one row, the two actions on their own row
                    below. Wrapping them all together dropped a lone half-width
                    "schedule week" pill under the title on a phone. */}
                <div className="mb-4 sm:mb-6 shrink-0 space-y-3">
                  <h2 className="font-display uppercase tracking-wide text-lg sm:text-xl text-ink flex flex-wrap items-center gap-2">
                    <span className="mr-auto">Generated Shorts</span>
                    {results?.clips?.length > 0 && (
                      <span className="readout bg-paper3 px-2.5 py-1 rounded-full">
                        {results.clips.length} Clips
                      </span>
                    )}
                    {/* Tokens, e nao dolares (25-set-2026): o selo dizia "GEMINI · $0.012"
                        com chave gratuita, que nao cobra nada -- e o preco e o do plano
                        pago. Quem respondeu e quanto custaria ficam no title. */}
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
                        title="Download all clips as a ZIP"
                      >
                        {downloadingAll
                          ? <><Loader2 size={14} className="animate-spin" />zipping…</>
                          : <><Download size={14} />download all</>}
                      </button>
                    </div>
                  )}
                </div>

                {status === 'complete' && results?.clips?.length > 0 && (
                  <div className="mb-2 space-y-2">
                    {/* Só aparece se alguém ligou a limpeza por idade
                        (JOB_RETENTION_SECONDS): o padrão deste fork é nunca apagar. */}
                    {jobRetentionSeconds > 0 && (
                      <div className="px-3 py-2.5 rounded-input bg-paper3 border border-paper3 text-sm">
                        <span className="text-ink">Os cortes ficam guardados por {formatRetention(jobRetentionSeconds)} e depois são apagados.</span>{' '}
                        <span className="text-muted">Baixe o que quiser manter, ou aumente o JOB_RETENTION_SECONDS no .env.</span>
                      </div>
                    )}
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
                          onPause={handleClipPause}
                          onBulkSubtitle={handleBulkSubtitles}
                          clipCount={results.clips.length}
                          bulkProgress={bulkSub}
                        />
                      ))}
                    </div>
                  ) : (
                    status === 'processing' ? (
                      <div className="h-full min-h-[140px] flex flex-col items-center justify-center text-muted space-y-3 text-center px-4">
                        <Loader2 size={28} className="animate-spin text-brass" />
                        <p className="text-sm lowercase">Waiting for clips...</p>
                        <p className="text-xs text-muted/80 max-w-[26ch] leading-snug">
                          They appear here one by one as each finishes rendering.
                        </p>
                      </div>
                    ) : status === 'error' ? (
                      <div className="h-full min-h-[120px] flex flex-col items-center justify-center text-danger space-y-2">
                        <p>Generation failed.</p>
                      </div>
                    ) : null
                  )}
                </div>
              </div>

            </div>
          )}

        </div>

        {/* Phone navigation. A flex sibling of the scrolling pane, not a fixed
            overlay, so content is never trapped behind it. */}
        <MobileTabBar />

      </main>

      {/* Falta a chave de IA: o caminho é colar nas Configurações (ChavesDeIA). */}
      <Modal
        isOpen={showKeyModal}
        onClose={() => setShowKeyModal(false)}
        eyebrow="PRIMEIRO PASSO"
        title="Falta a chave de IA"
        footer={
          <div className="flex gap-3">
            <button
              onClick={() => setShowKeyModal(false)}
              className="btn-ghost flex-1 px-4 py-2 text-sm"
            >
              agora não
            </button>
            <button
              onClick={() => { setShowKeyModal(false); goToTab('settings'); }}
              className="btn-primary flex-1 px-4 py-2 text-sm"
            >
              colocar a chave
            </button>
          </div>
        }
      >
        <div className="space-y-3 text-sm text-muted leading-relaxed">
          <p>
            O Virtu Clips usa IAs gratuitas para achar os melhores momentos do vídeo, e cada uma
            pede uma chave. É grátis e leva um minuto: nas Configurações, clique em
            <span className="text-ink2"> criar chave grátis</span>, copie e cole.
          </p>
          <p>
            As recomendadas são a do <span className="text-ink2">Google Gemini</span> e a do
            <span className="text-ink2"> Groq</span>. Uma só já basta para começar.
          </p>
        </div>
      </Modal>


      {/* Pre-flight quality gate */}
      {qualityGate && (
        <Modal isOpen={true} onClose={() => setQualityGate(null)} size="md" eyebrow="HEADS UP" title="low source quality">
          <div className="space-y-4">
            <p className="text-sm text-ink2">
              YouTube only offers <span className="text-brass font-semibold">{qualityGate.info.max_height}p</span> for this video
              (below the {qualityGate.info.min_height}p we recommend). Processing anyway will produce lower-quality clips.
            </p>
            {qualityGate.info.cookies_invalid && (
              <p className="text-xs text-muted">
                Your YouTube cookies look expired — refreshing them (export again from an incognito window) often unlocks HD.
              </p>
            )}
            <div className="flex gap-2 justify-end pt-2">
              <button onClick={() => setQualityGate(null)} className="btn-ghost">cancel</button>
              <button
                onClick={() => { const d = qualityGate.data; setQualityGate(null); handleProcess(d, true); }}
                className="btn-primary"
              >
                process anyway
              </button>
            </div>
          </div>
        </Modal>
      )}


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

export default App;
