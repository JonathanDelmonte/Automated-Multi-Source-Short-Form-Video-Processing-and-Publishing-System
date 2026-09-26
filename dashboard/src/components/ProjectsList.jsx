import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Trash2, Loader2, Film, AlertTriangle, RotateCcw } from 'lucide-react';
import { apiFetch, apiJson } from '../lib/api';
import AvatarDoCanal from './ui/AvatarDoCanal';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// Lista de projetos: o que existe em `output/`, do mais novo para o mais velho.
//
// Antes disto o painel so conhecia UM job -- o da sessao atual, guardado no
// localStorage. Um job anterior continuava no disco, ocupando espaco, sem forma
// de abrir nem de apagar pela interface: era ir na pasta a mao. E apagar a
// pasta com o job vivo deixava um `main.py` orfao escrevendo num diretorio que
// ja nao existia, que foi exatamente o bug reportado.
//
// Por isso apagar aqui chama `DELETE /api/jobs/{id}`, que cancela antes de
// remover, em vez de mexer no disco.
//
// Desde a 7.1 ela e a lista curta do Inicio: os `limite` mais recentes, com o
// canal de cada um, e o link para a grade completa em Projetos.

const RELOGIO = { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' };

function quando(ts) {
  if (!ts) return '';
  try {
    return new Date(ts * 1000).toLocaleString(undefined, RELOGIO);
  } catch {
    return '';
  }
}

const CORES = {
  completed: 'text-ok',
  processing: 'text-brass',
  queued: 'text-muted',
  failed: 'text-danger',
  cancelled: 'text-muted',
};

const ROTULOS = {
  completed: 'pronto',
  processing: 'processando',
  queued: 'na fila',
  failed: 'falhou',
  cancelled: 'cancelado',
};

export default function ProjectsList({ onOpen, onApagado, refreshKey = 0, limite = 6, titulo = 'projetos', aoCarregar = null }) {
  const { canais } = usePainel();
  const [projetos, setProjetos] = useState(null);   // null = ainda carregando
  // Quem mostra os primeiros passos precisa saber se ja existe projeto. Numa
  // ref, e nao nas dependencias do `carregar`: a funcao chega nova a cada
  // render de quem chama, e o efeito de carga rodaria sem parar.
  const avisar = useRef(aoCarregar);
  useEffect(() => { avisar.current = aoCarregar; });
  const [erro, setErro] = useState(null);
  const [apagando, setApagando] = useState(null);

  const carregar = useCallback(async () => {
    let lista = [];
    try {
      const res = await apiFetch('/api/jobs');
      if (!res.ok) throw new Error('falhou');
      const data = await res.json();
      lista = data.jobs || [];
      setErro(null);
    } catch (e) {
      setErro('Não consegui carregar os projetos.');
    }
    setProjetos(lista);
    if (avisar.current) avisar.current(lista);
  }, []);

  useEffect(() => { carregar(); }, [carregar, refreshKey]);

  // Um job em andamento muda de estagio sozinho; sem isto a lista mentiria ate
  // alguem recarregar a pagina. 5s porque a lista e barata (nao traz o log).
  useEffect(() => {
    const algumVivo = (projetos || []).some(
      (p) => p.status === 'processing' || p.status === 'queued');
    if (!algumVivo) return undefined;
    const t = setInterval(carregar, 5000);
    return () => clearInterval(t);
  }, [projetos, carregar]);

  const apagar = async (jobId, e) => {
    e.stopPropagation();   // o cartao inteiro abre o projeto; a lixeira nao deve
    setApagando(jobId);
    try {
      // 409 = arquivo preso no disco; o `apiJson` falha nele, o `apiFetch` nao.
      await apiJson(`/api/jobs/${jobId}`, { method: 'DELETE' });
      setProjetos((atual) => (atual || []).filter((p) => p.job_id !== jobId));
      setErro(null);
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
      <div className="flex items-center justify-center gap-2 py-6 text-muted text-sm">
        <Loader2 size={14} className="animate-spin" /> carregando projetos…
      </div>
    );
  }

  if (projetos.length === 0) return null;   // primeira visita: nada a listar

  const lista = limite ? projetos.slice(0, limite) : projetos;

  return (
    <div className="w-full text-left space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow">{titulo}</p>
        <span className="flex items-center gap-3">
          {limite && projetos.length > limite && (
            <a href={hrefDe('/projetos')} className="text-xs text-muted hover:text-ink2 transition-colors">
              ver todos ({projetos.length})
            </a>
          )}
          <button
            type="button"
            onClick={carregar}
            title="Atualizar a lista"
            className="text-muted hover:text-ink transition-colors"
          >
            <RotateCcw size={13} />
          </button>
        </span>
      </div>

      {erro && (
        <p className="flex items-center gap-2 text-xs text-danger">
          <AlertTriangle size={13} /> {erro}
        </p>
      )}

      <div className="space-y-1.5">
        {lista.map((p) => (
          <div
            key={p.job_id}
            role="button"
            tabIndex={0}
            onClick={() => onOpen(p.job_id)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(p.job_id); } }}
            className="w-full card px-3.5 py-2.5 flex items-center gap-3 hover:border-rule2 transition-colors cursor-pointer text-left"
          >
            {p.channel_id && canais.porId[p.channel_id]
              ? <AvatarDoCanal canal={canais.porId[p.channel_id]} size={22} />
              : <Film size={15} className="shrink-0 text-muted" />}

            <div className="min-w-0 flex-1">
              <p className="text-sm text-ink2 truncate">
                {p.title || p.source_url || 'projeto sem título'}
              </p>
              <p className="text-xs text-muted flex items-center gap-2 flex-wrap">
                <span className={CORES[p.status] || 'text-muted'}>
                  {ROTULOS[p.status] || p.status}
                </span>
                {/* Em andamento, o estagio diz mais que a data. */}
                {p.status === 'processing' && p.stage_label && (
                  <span>· {p.stage_index}/{p.stage_total} {p.stage_label}</span>
                )}
                {p.clip_count > 0 && <span>· {p.clip_count} corte(s)</span>}
                {quando(p.created_at) && <span>· {quando(p.created_at)}</span>}
              </p>
            </div>

            <button
              type="button"
              onClick={(e) => apagar(p.job_id, e)}
              disabled={apagando === p.job_id}
              title="Apagar este projeto"
              aria-label="Apagar este projeto"
              className="shrink-0 text-muted hover:text-danger transition-colors disabled:opacity-50"
            >
              {apagando === p.job_id
                ? <Loader2 size={14} className="animate-spin" />
                : <Trash2 size={14} />}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
