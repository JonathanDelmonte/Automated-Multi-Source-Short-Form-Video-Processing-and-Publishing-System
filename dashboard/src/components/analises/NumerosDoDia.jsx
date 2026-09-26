import React, { useEffect, useState } from 'react';
import { ArrowRight, ExternalLink } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import AvatarDoCanal from '../ui/AvatarDoCanal';
import { apiFetch } from '../../lib/api';
import { fusoDoNavegador, numeroCurto } from '../../lib/analises';
import { usePainel } from '../../lib/painel';
import { hrefDe } from '../../lib/rota';

// Os números do dia, no Início (etapa 7.4): o que cresceu nas últimas 24 h, o
// que foi ao ar hoje e o corte que mais cresceu. Com um programa de antes da
// 7.4 (404), o bloco some: o Início não é lugar de mandar atualizar -- o aviso
// do topo já faz isso.

export default function NumerosDoDia() {
  const { canais } = usePainel();
  const [dia, setDia] = useState(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const r = await apiFetch(`/api/analises/hoje?fuso_min=${fusoDoNavegador()}`);
        if (vivo && r.ok) setDia(await r.json());
      } catch { /* sem o bloco */ }
    })();
    return () => { vivo = false; };
  }, []);

  if (!dia || !dia.publicados) return null;
  const g = dia.ganho_24h || {};
  const semMedida = !dia.medidos;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="eyebrow">números do dia</p>
        <a href={hrefDe('/analises')} className="text-xs text-muted hover:text-ink2 inline-flex items-center gap-1">
          análises <ArrowRight size={12} />
        </a>
      </div>
      {semMedida ? (
        <div className="card p-4 text-sm text-muted leading-snug">
          {dia.publicados} corte{dia.publicados === 1 ? '' : 's'} no ar, e nenhum medido ainda. Os números chegam
          sozinhos depois que as contas estão conectadas para medir.{' '}
          <a href={hrefDe('/configuracoes/contas')} className="text-ink2 underline underline-offset-2">ir às contas</a>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="card px-4 py-3 min-w-0">
            <p className="text-[26px] leading-none font-semibold text-ink">
              {g.views === null || g.views === undefined ? '—' : `+${numeroCurto(g.views)}`}
            </p>
            <p className="readout mt-1.5">visualizações em 24 h</p>
          </div>
          <div className="card px-4 py-3 min-w-0">
            <p className="text-[26px] leading-none font-semibold text-ink">
              {g.likes === null || g.likes === undefined ? '—' : `+${numeroCurto(g.likes)}`}
            </p>
            <p className="readout mt-1.5">curtidas em 24 h</p>
          </div>
          <div className="card px-4 py-3 min-w-0">
            <p className="text-[26px] leading-none font-semibold text-ink">{dia.publicados_hoje}</p>
            <p className="readout mt-1.5">no ar hoje</p>
          </div>
          <div className="card px-4 py-3 min-w-0 col-span-2 lg:col-span-1">
            {dia.destaque ? (
              <>
                <p className="text-[11px] text-muted">o que mais cresceu</p>
                <p className="text-sm text-ink truncate mt-0.5 flex items-center gap-1.5">
                  <IconePlataforma platform={dia.destaque.plataforma} size={13} />
                  <span className="truncate">{dia.destaque.titulo || 'corte'}</span>
                  {dia.destaque.url && (
                    <a href={dia.destaque.url} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-ink2 shrink-0"
                       aria-label="abrir o post"><ExternalLink size={12} /></a>
                  )}
                </p>
                <p className="text-[11px] text-muted mt-0.5">+{numeroCurto(dia.destaque.ganho_views)} visualizações em 24 h</p>
              </>
            ) : (
              <p className="text-[12px] text-muted leading-snug">Nenhum corte cresceu nas últimas 24 h (ou ainda falta a leitura de ontem).</p>
            )}
          </div>
        </div>
      )}
      {!semMedida && (dia.por_canal || []).length > 1 && (
        <ul className="flex flex-wrap gap-2">
          {dia.por_canal.map((l) => {
            const canal = canais.porId[l.canal.id] || l.canal;
            const v = l.ganho_24h?.views;
            return (
              <li key={l.canal.id}>
                <a href={hrefDe(`/canais/${l.canal.id}/analises`)}
                   className="inline-flex items-center gap-2 pl-1 pr-3 py-1 rounded-full bg-paper3 text-xs text-ink2 hover:text-ink">
                  <AvatarDoCanal canal={canal} size={20} />
                  {canal.name}
                  <span className="text-muted">{v === null || v === undefined ? '—' : `+${numeroCurto(v)}`}</span>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
