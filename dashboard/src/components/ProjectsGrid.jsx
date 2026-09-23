import React, { useState, useEffect, useCallback } from 'react';
import { Trash2, Loader2, Plus, AlertTriangle, RotateCcw, Film } from 'lucide-react';
import { apiFetch, apiJson } from '../lib/api';

// A tela de projetos: uma grade de cartoes, um por vídeo processado.
//
// O painel herdado so conhecia UM projeto -- o da sessao atual, no
// localStorage. Nao havia tela nenhuma listando o que ja foi feito, nem como
// voltar de um projeto aberto para escolher outro: o unico botao no topo dizia
// "New Project", que **cria** em vez de voltar. Quem quisesse rever um corte de
// ontem nao tinha caminho.
//
// **A capa e o proprio clipe**, com `preload="metadata"`: o navegador baixa so
// o cabecalho do mp4 e desenha o primeiro quadro. Nao ha campo de thumbnail no
// backend, e inventar um significaria gerar e guardar imagem por clipe -- por
// um cartao que o navegador ja sabe desenhar de graca.

const RELOGIO = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' };

function quando(ts) {
  if (!ts) return '';
  try {
    return new Date(ts * 1000).toLocaleString(undefined, RELOGIO);
  } catch {
    return '';
  }
}

const ESTADO = {
  completed: { texto: 'pronto', cor: 'text-ok' },
  processing: { texto: 'processando', cor: 'text-brass' },
  queued: { texto: 'na fila', cor: 'text-muted' },
  failed: { texto: 'falhou', cor: 'text-danger' },
  cancelled: { texto: 'cancelado', cor: 'text-muted' },
};

export default function ProjectsGrid({ onOpen, onNew, onApagado, refreshKey = 0 }) {
  const [projetos, setProjetos] = useState(null);
  const [erro, setErro] = useState(null);
  const [apagando, setApagando] = useState(null);
  const [confirmando, setConfirmando] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/jobs');
      if (!res.ok) throw new Error('falhou');
      const data = await res.json();
      setProjetos(data.jobs || []);
      setErro(null);
    } catch {
      setErro('Não consegui carregar os projetos.');
      setProjetos([]);
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar, refreshKey]);

  // Só enquanto houver job vivo: um projeto em andamento muda de estágio
  // sozinho, e sem isto a grade mentiria até alguém recarregar a página.
  useEffect(() => {
    const vivo = (projetos || []).some(
      (p) => p.status === 'processing' || p.status === 'queued');
    if (!vivo) return undefined;
    const t = setInterval(carregar, 5000);
    return () => clearInterval(t);
  }, [projetos, carregar]);

  const apagar = async (jobId, e) => {
    e.stopPropagation();
    setApagando(jobId);
    setConfirmando(null);
    try {
      // `apiJson` e nao `apiFetch`: o `apiFetch` nao falha em 409, e o servidor
      // responde 409 quando um arquivo do projeto ficou preso no disco. Antes
      // o cartao sumia da tela com o arquivo ainda la.
      await apiJson(`/api/jobs/${jobId}`, { method: 'DELETE' });
      setProjetos((atual) => (atual || []).filter((p) => p.job_id !== jobId));
      setErro(null);
      // Quem abriu este projeto no Clip Generator precisa soltá-lo: senão a
      // tela continua mostrando os cortes de um projeto que não existe mais.
      if (onApagado) onApagado(jobId);
    } catch (err) {
      setErro(err?.detail || 'Não consegui apagar esse projeto.');
      carregar();
    } finally {
      setApagando(null);
    }
  };

  if (projetos === null) {
    return (
      <div className="h-full flex items-center justify-center gap-2 text-muted text-sm">
        <Loader2 size={15} className="animate-spin" /> carregando projetos…
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto custom-scrollbar animate-fade p-4 sm:p-6">
      <div className="max-w-5xl mx-auto space-y-5">

        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div>
            <p className="eyebrow hidden sm:block">02 · projetos</p>
            <h1 className="font-display lowercase text-2xl sm:text-3xl text-ink">
              seus projetos
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={carregar}
              title="Atualizar"
              aria-label="Atualizar a lista"
              className="btn-quiet px-2.5 py-1.5"
            >
              <RotateCcw size={14} />
            </button>
            <button type="button" onClick={onNew} className="btn-primary px-3 py-1.5 text-sm">
              <Plus size={15} /> novo projeto
            </button>
          </div>
        </div>

        {erro && (
          <p className="flex items-center gap-2 text-sm text-danger">
            <AlertTriangle size={14} /> {erro}
          </p>
        )}

        {projetos.length === 0 ? (
          <div className="card p-10 text-center space-y-3">
            <Film size={28} className="mx-auto text-muted" />
            <p className="text-muted text-sm">
              Nenhum projeto ainda. O primeiro vídeo que você enviar aparece aqui.
            </p>
            <button type="button" onClick={onNew} className="btn-primary px-4 py-2 text-sm mx-auto">
              <Plus size={15} /> começar
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
            {projetos.map((p) => {
              const estado = ESTADO[p.status] || { texto: p.status, cor: 'text-muted' };
              const capa = p.first_clip_url;
              return (
                <div
                  key={p.job_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onOpen(p.job_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(p.job_id); }
                  }}
                  className="card overflow-hidden hover:border-rule2 transition-colors cursor-pointer group flex flex-col"
                >
                  <div className="relative aspect-video bg-paper flex items-center justify-center overflow-hidden">
                    {capa ? (
                      // O proprio clipe como capa: `metadata` baixa so o
                      // cabecalho e o navegador desenha o primeiro quadro.
                      <video
                        src={capa}
                        preload="metadata"
                        muted
                        playsInline
                        className="w-full h-full object-cover"
                      />
                    ) : p.status === 'processing' ? (
                      <Loader2 size={22} className="animate-spin text-brass" />
                    ) : (
                      <Film size={22} className="text-muted opacity-40" />
                    )}

                    {confirmando === p.job_id ? (
                      <div
                        className="absolute inset-0 bg-paper/95 flex flex-col items-center justify-center gap-2 p-3 text-center"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <p className="text-xs text-ink2">Apagar este projeto?</p>
                        <p className="text-[11px] text-muted">Os cortes vão junto.</p>
                        <div className="flex gap-2 pt-1">
                          <button
                            type="button"
                            onClick={(e) => apagar(p.job_id, e)}
                            className="btn-quiet px-3 py-1 text-xs text-danger"
                          >
                            apagar
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setConfirmando(null); }}
                            className="btn-quiet px-3 py-1 text-xs"
                          >
                            cancelar
                          </button>
                        </div>
                      </div>
                    ) : (
                      // Confirmacao antes de apagar: o `DELETE` leva os cortes
                      // junto e nao ha desfazer.
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); setConfirmando(p.job_id); }}
                        disabled={apagando === p.job_id}
                        aria-label="Apagar este projeto"
                        title="Apagar este projeto"
                        className="absolute top-2 right-2 p-1.5 rounded-input bg-paper/80 text-muted opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-danger transition-all"
                      >
                        {apagando === p.job_id
                          ? <Loader2 size={14} className="animate-spin" />
                          : <Trash2 size={14} />}
                      </button>
                    )}
                  </div>

                  <div className="p-3 space-y-1 min-w-0">
                    <p className="text-sm text-ink2 truncate">
                      {p.title || p.source_url || 'projeto sem título'}
                    </p>
                    <p className="text-xs text-muted flex items-center gap-1.5 flex-wrap">
                      <span className={estado.cor}>{estado.texto}</span>
                      {p.status === 'processing' && p.stage_label && (
                        <span>· {p.stage_index}/{p.stage_total} {p.stage_label}</span>
                      )}
                      {p.clip_count > 0 && <span>· {p.clip_count} corte(s)</span>}
                      {quando(p.created_at) && <span>· {quando(p.created_at)}</span>}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
