import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowDown, ArrowUp, ChevronDown, Film, Loader2, X } from 'lucide-react';
import { apiJson } from '../../lib/api';
import { LEGENDAS } from '../../lib/criacao.js';
import {
  DESCRICAO_MAX, TITULO_MAX, alternar, capitulosPrevistos, chaveDoCorte, corpoDaCompilacao,
  duracaoTotal, mover, porQueNaoMonta, tempo,
} from '../../lib/compilacao.js';
import { criarCompilacao, lerCortesDoProjeto } from '../../lib/criacaoNoMotor';
import { ir } from '../../lib/rota';

// A compilação dos cortes (etapa 7.8): um vídeo horizontal longo para o YouTube,
// feito dos cortes escolhidos -- de um projeto ou de vários --, na ordem
// escolhida. Cada corte sai da ORIGEM deitada quando ela ainda está no disco;
// sem ela, entra o próprio corte vertical sobre um fundo desfocado, e a tela diz
// isso antes. Os capítulos (um por corte) aparecem antes do clique, pela mesma
// regra do motor. Sem IA: nada aqui gasta cota.

// Um projeto que já é vídeo longo (episódio ou compilação) não entra.
const serveDeFonte = (p) => p.status === 'completed' && p.clip_count > 0
  && !p.compilacao && p.criacao?.formato !== 'longo';

export default function CompilarCortes({ canalId, projetoInicial = null, aoCriar }) {
  const [projetos, setProjetos] = useState(null);
  const [abertos, setAbertos] = useState({});
  const [escolhidos, setEscolhidos] = useState([]);
  const [titulo, setTitulo] = useState('');
  const [descricao, setDescricao] = useState('');
  const [legenda, setLegenda] = useState('limpo');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true;
    const filtro = canalId ? `?canal=${encodeURIComponent(canalId)}` : '';
    apiJson(`/api/jobs${filtro}`)
      .then((data) => { if (vivo) setProjetos((data.jobs || []).filter(serveDeFonte)); })
      .catch(() => { if (vivo) setProjetos([]); });
    return () => { vivo = false; };
  }, [canalId]);

  const abrir = useCallback(async (jobId, escolherTodos = false) => {
    setAbertos((a) => ({ ...a, [jobId]: { ...(a[jobId] || {}), aberto: true, carregando: !a[jobId]?.cortes } }));
    const r = await lerCortesDoProjeto(jobId);
    setAbertos((a) => ({
      ...a,
      [jobId]: { aberto: true, carregando: false, cortes: r.ok ? r.data.cortes : [],
                 origem: r.ok ? r.data.origem : true, erro: r.ok ? null : r.erro },
    }));
    if (escolherTodos && r.ok) {
      const novos = r.data.cortes.filter((c) => c.formato !== 'longo').map((c) => ({
        jobId, clip: c.clip, titulo: c.titulo, duracao_s: c.duracao_s, vertical: !r.data.origem,
      }));
      // Sem repetir: o efeito pode rodar duas vezes (o modo estrito do React).
      setEscolhidos((atual) => {
        const ja = new Set(atual.map(chaveDoCorte));
        return [...atual, ...novos.filter((c) => !ja.has(chaveDoCorte(c)))];
      });
    }
  }, []);

  // "Vídeo longo com estes cortes", da tela do projeto: ele já vem aberto e
  // com todos os cortes escolhidos, na ordem do projeto.
  useEffect(() => {
    if (projetoInicial) abrir(projetoInicial, true);
  }, [projetoInicial, abrir]);

  const alternarProjeto = (jobId) => {
    const estado = abertos[jobId];
    if (estado?.aberto) setAbertos((a) => ({ ...a, [jobId]: { ...estado, aberto: false } }));
    else abrir(jobId);
  };

  const total = duracaoTotal(escolhidos);
  const capitulos = capitulosPrevistos(escolhidos);
  const bloqueio = porQueNaoMonta({ titulo, escolhidos });
  const escolhido = new Set(escolhidos.map(chaveDoCorte));

  const montar = async () => {
    setEnviando(true);
    setErro(null);
    const r = await criarCompilacao(corpoDaCompilacao({ titulo, descricao, canalId, legenda, escolhidos }));
    setEnviando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    if (aoCriar) aoCriar(r.data.job_id);
    ir(`/projetos/${r.data.job_id}`);
  };

  return (
    <div className="space-y-5" data-compilar-cortes>
      <div className="space-y-2">
        <p className="eyebrow">1. escolha os cortes{canalId ? ' (projetos deste canal)' : ''}</p>
        {projetos === null && <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />}
        {projetos && projetos.length === 0 && (
          <p className="text-sm text-ink2">Nenhum projeto pronto com cortes{canalId ? ' neste canal' : ''}.</p>
        )}
        <ul className="space-y-2">
          {(projetos || []).map((p) => {
            const estado = abertos[p.job_id] || {};
            return (
              <li key={p.job_id} className="rounded-input border border-rule2">
                <button type="button" className="w-full flex items-center gap-2 px-3 py-2.5 text-left min-w-0"
                        aria-expanded={Boolean(estado.aberto)} onClick={() => alternarProjeto(p.job_id)}>
                  <Film size={15} className="text-muted shrink-0" />
                  <span className="text-sm text-ink truncate min-w-0 flex-1">{p.title || 'projeto sem título'}</span>
                  <span className="readout normal-case shrink-0">{p.clip_count} corte{p.clip_count === 1 ? '' : 's'}</span>
                  <ChevronDown size={15} className={`text-muted shrink-0 transition-transform ${estado.aberto ? 'rotate-180' : ''}`} />
                </button>
                {estado.aberto && (
                  <div className="px-3 pb-3 space-y-1.5">
                    {estado.carregando && <Loader2 size={15} className="animate-spin text-muted" />}
                    {estado.erro && <p className="text-sm text-danger">{estado.erro}</p>}
                    {estado.cortes && estado.origem === false && (
                      <p className="text-[12px] text-muted leading-snug">
                        O vídeo de origem deste projeto não está mais no disco: entra o próprio corte vertical,
                        no meio da tela, sobre um fundo desfocado.
                      </p>
                    )}
                    {(estado.cortes || []).map((c) => {
                      const corte = { jobId: p.job_id, clip: c.clip, titulo: c.titulo, duracao_s: c.duracao_s,
                                      vertical: !estado.origem };
                      const marcado = escolhido.has(chaveDoCorte(corte));
                      return (
                        <label key={c.clip} className="flex items-center gap-2 text-sm min-w-0 cursor-pointer">
                          <input type="checkbox" checked={marcado} disabled={c.formato === 'longo'}
                                 onChange={() => setEscolhidos((atual) => alternar(atual, corte))} />
                          <span className="truncate min-w-0 flex-1 text-ink2">{c.titulo || `corte ${c.clip + 1}`}</span>
                          <span className="readout normal-case shrink-0">{tempo(c.duracao_s)}</span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      {escolhidos.length > 0 && (
        <div className="space-y-2" data-escolhidos>
          <p className="eyebrow">2. a ordem ({escolhidos.length} corte{escolhidos.length === 1 ? '' : 's'}, {tempo(total)})</p>
          <ol className="space-y-1.5">
            {escolhidos.map((c, i) => (
              <li key={chaveDoCorte(c)} className="flex items-center gap-2 text-sm min-w-0 rounded-input bg-paper3 px-2.5 py-1.5">
                <span className="readout shrink-0 w-6 text-right">{i + 1}</span>
                <span className="truncate min-w-0 flex-1 text-ink">{c.titulo || `corte ${c.clip + 1}`}</span>
                <span className="readout normal-case shrink-0">{tempo(c.duracao_s)}</span>
                <button type="button" className="text-muted hover:text-ink disabled:opacity-30" aria-label="subir"
                        disabled={i === 0} onClick={() => setEscolhidos((a) => mover(a, i, -1))}><ArrowUp size={14} /></button>
                <button type="button" className="text-muted hover:text-ink disabled:opacity-30" aria-label="descer"
                        disabled={i === escolhidos.length - 1} onClick={() => setEscolhidos((a) => mover(a, i, 1))}><ArrowDown size={14} /></button>
                <button type="button" className="text-muted hover:text-danger" aria-label="tirar"
                        onClick={() => setEscolhidos((a) => alternar(a, c))}><X size={14} /></button>
              </li>
            ))}
          </ol>
          <p className="text-[12px] text-muted leading-snug" data-capitulos-previstos>
            {capitulos.length
              ? `Capítulos na descrição: ${capitulos.map(([s, t]) => `${tempo(s)} ${t}`).join(' · ')}`
              : 'Sem capítulos: o YouTube pede pelo menos três, de 10 segundos cada, e cada corte com título abre um.'}
          </p>
        </div>
      )}

      <div className="space-y-3">
        <p className="eyebrow">3. o vídeo</p>
        <label className="block" htmlFor="compilacao-titulo">
          <span className="text-[12px] text-muted">título no YouTube</span>
          <input id="compilacao-titulo" className="input-field mt-1" maxLength={TITULO_MAX} value={titulo}
                 onChange={(e) => setTitulo(e.target.value)} placeholder="Ex.: Os melhores momentos da semana" />
        </label>
        <label className="block" htmlFor="compilacao-descricao">
          <span className="text-[12px] text-muted">descrição (opcional; os capítulos entram sozinhos)</span>
          <textarea id="compilacao-descricao" className="input-field mt-1 min-h-[4rem]" maxLength={DESCRICAO_MAX}
                    value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </label>
        <label className="block" htmlFor="compilacao-legenda">
          <span className="text-[12px] text-muted">legenda (da transcrição dos projetos)</span>
          <select id="compilacao-legenda" className="input-field mt-1" value={legenda} onChange={(e) => setLegenda(e.target.value)}>
            {LEGENDAS.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}
          </select>
        </label>
      </div>

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0 break-words">{erro}</span>
        </p>
      )}
      {bloqueio && escolhidos.length > 0 && (
        <p className="text-[12px] text-muted" data-bloqueio-da-compilacao>{bloqueio}</p>
      )}
      <button type="button" className="btn-primary px-4 py-2.5 text-sm w-full sm:w-auto" onClick={montar}
              disabled={Boolean(bloqueio) || enviando}>
        {enviando ? <Loader2 size={15} className="animate-spin" /> : <Film size={15} />} montar a compilação
      </button>
      <p className="text-[12px] text-muted leading-snug">
        Horizontal (1920x1080), com meio segundo de escuro entre um corte e outro: ela vai só para o YouTube.
        O crédito das fontes Creative Commons entra na descrição sozinho.
      </p>
    </div>
  );
}
