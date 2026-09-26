import React, { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, ShieldCheck, X } from 'lucide-react';
import { getApiUrl } from '../../config';
import { decidirAprovacoes, listarAprovacoes } from '../../lib/automacao';
import { duracaoCurta } from '../../lib/receita.js';
import { hrefDe } from '../../lib/rota';

// A caixa de aprovação (etapa 7.5): os cortes que a automação fez para um
// canal que pede "ver antes de postar". Aprovar põe o corte na agenda do
// canal, um galho por conta; recusar deixa o corte no projeto, fora do ar.

function Previa({ url, titulo }) {
  if (!url) {
    return (
      <div className="aspect-[9/16] w-full rounded-input bg-paper3 flex items-center justify-center text-muted text-xs p-3 text-center">
        o arquivo não está mais na pasta
      </div>
    );
  }
  return (
    <video
      src={getApiUrl(url)}
      controls
      preload="metadata"
      playsInline
      className="aspect-[9/16] w-full rounded-input bg-black object-contain"
      aria-label={`prévia de ${titulo || 'corte'}`}
    />
  );
}

export default function CaixaDeAprovacao({ canalId, aoMudar, vazio = 'Nada esperando a sua aprovação.' }) {
  const [lista, setLista] = useState(null);
  const [erro, setErro] = useState(null);
  const [ocupados, setOcupados] = useState({});
  const [avisos, setAvisos] = useState({});

  const carregar = useCallback(async () => {
    const r = await listarAprovacoes(canalId);
    if (!r.ok) {
      setErro(r.erro);
      setLista([]);
      return;
    }
    setErro(null);
    setLista(r.data.aprovacoes || []);
  }, [canalId]);
  useEffect(() => { carregar(); }, [carregar]);

  const decidir = async (ids, decisao) => {
    setOcupados((o) => ({ ...o, ...Object.fromEntries(ids.map((i) => [i, decisao])) }));
    const r = await decidirAprovacoes(ids, decisao);
    setOcupados((o) => Object.fromEntries(Object.entries(o).filter(([k]) => !ids.includes(k))));
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    const falhas = Object.fromEntries((r.data.resultados || [])
      .filter((x) => !x.ok).map((x) => [x.id, x.detail || 'não deu certo']));
    setAvisos(falhas);
    await carregar();
    aoMudar?.();
  };

  if (lista === null) {
    return <Loader2 size={16} className="animate-spin text-muted" aria-label="carregando" />;
  }
  if (erro && lista.length === 0) {
    return <p className="text-muted text-sm">{erro}</p>;
  }
  if (lista.length === 0) {
    return <p className="text-muted text-sm">{vazio}</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink2 flex items-center gap-2">
          <ShieldCheck size={15} className="shrink-0" />
          {lista.length === 1 ? '1 corte esperando você' : `${lista.length} cortes esperando você`}
        </p>
        {lista.length > 1 && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs"
                  onClick={() => decidir(lista.map((a) => a.id), 'aprovar')}
                  disabled={Object.keys(ocupados).length > 0}>
            <Check size={14} /> aprovar todos
          </button>
        )}
      </div>
      {erro && <p className="text-danger text-sm">{erro}</p>}
      <ul className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 11.5rem), 1fr))' }}>
        {lista.map((a) => {
          const ocupado = ocupados[a.id];
          return (
            <li key={a.id} className="card p-2.5 space-y-2 min-w-0" data-aprovacao={a.id}>
              <Previa url={a.clip.video_url} titulo={a.clip.titulo} />
              <div className="min-w-0 px-0.5">
                <p className="text-sm text-ink leading-snug line-clamp-2">{a.clip.titulo || `Corte ${a.clip.clip_index + 1}`}</p>
                <p className="text-[11px] text-muted mt-0.5">
                  {[a.clip.duracao_s ? duracaoCurta(a.clip.duracao_s) : null,
                    a.clip.score !== null && a.clip.score !== undefined ? `nota ${Math.round(a.clip.score)}` : null]
                    .filter(Boolean).join(' · ')}
                  {a.clip.job_id && (
                    <>
                      {' · '}
                      <a href={hrefDe(`/projetos/${a.clip.job_id}`)} className="underline underline-offset-2 hover:text-ink2">projeto</a>
                    </>
                  )}
                </p>
                {avisos[a.id] && <p className="text-danger text-[11px] mt-1 leading-snug">{avisos[a.id]}</p>}
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <button type="button" className="btn-primary px-2 py-1.5 text-xs justify-center"
                        onClick={() => decidir([a.id], 'aprovar')} disabled={Boolean(ocupado)}>
                  {ocupado === 'aprovar' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} aprovar
                </button>
                <button type="button" className="btn-ghost px-2 py-1.5 text-xs justify-center"
                        onClick={() => decidir([a.id], 'recusar')} disabled={Boolean(ocupado)}>
                  {ocupado === 'recusar' ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />} recusar
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-muted text-[12px] leading-snug">
        Aprovado, o corte entra na agenda do canal, um post em cada conta, nas janelas dele. Recusado, ele
        continua no projeto e não vai ao ar.
      </p>
    </div>
  );
}
