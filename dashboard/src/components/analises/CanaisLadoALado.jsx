import React, { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import Tendencia from './Tendencia';
import AvatarDoCanal from '../ui/AvatarDoCanal';
import IconePlataforma from '../ui/IconePlataforma';
import { apiFetch } from '../../lib/api';
import { fusoDoNavegador, numeroCurto, porcentagem } from '../../lib/analises';
import { usePainel } from '../../lib/painel';
import { hrefDe } from '../../lib/rota';

// Todos os canais lado a lado (Análises, no menu; etapa 7.4): o total, o que
// cresceu nas últimas 24 h e a tendência de 14 dias de cada um. O cartão leva
// às análises do canal. Os cortes de contas sem canal aparecem num cartão
// próprio no fim, se houver algum.

export default function CanaisLadoALado() {
  const { canais } = usePainel();
  const [linhas, setLinhas] = useState(null);
  const [situacao, setSituacao] = useState('carregando');

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const r = await apiFetch(`/api/analises/canais?dias=14&fuso_min=${fusoDoNavegador()}`);
        if (!vivo) return;
        if (r.status === 404) { setSituacao('motor-antigo'); return; }
        if (!r.ok) { setSituacao('erro'); return; }
        setLinhas((await r.json()).canais || []);
        setSituacao('ok');
      } catch {
        if (vivo) setSituacao('erro');
      }
    })();
    return () => { vivo = false; };
  }, []);

  if (situacao === 'motor-antigo') return null;
  if (situacao === 'carregando') {
    return <p className="text-sm text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> lendo os canais…</p>;
  }
  if (situacao === 'erro') return <p className="text-sm text-danger">Não deu para ler os canais agora.</p>;
  if (!linhas.length) {
    return (
      <p className="text-sm text-muted">
        Nenhum canal ainda. <a href={hrefDe('/canais/novo')} className="text-ink2 underline underline-offset-2">Criar o primeiro</a>
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {linhas.map((l) => {
        const canal = l.canal ? (canais.porId[l.canal.id] || l.canal) : null;
        const t = l.totais || {};
        const conteudo = (
          <>
            <div className="flex items-center gap-2.5 min-w-0">
              {canal ? <AvatarDoCanal canal={canal} size={32} /> : <span className="w-8 h-8 rounded-full bg-paper3 shrink-0" aria-hidden="true" />}
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink truncate">{canal ? canal.name : 'contas sem canal'}</span>
                <span className="flex items-center gap-1 mt-0.5">
                  {(l.plataformas || []).map((p) => <IconePlataforma key={p} platform={p} size={12} />)}

                </span>
              </span>
            </div>
            {t.publicados ? (
              <div className="flex items-end justify-between gap-3">
                <span className="min-w-0">
                  <span className="block text-[22px] leading-none font-semibold text-ink">{numeroCurto(t.views)}</span>
                  <span className="block readout mt-1">visualizações</span>
                  <span className="block text-[11px] text-muted mt-0.5 truncate">
                    {l.ganho_24h?.views !== null && l.ganho_24h?.views !== undefined
                      ? `+${numeroCurto(l.ganho_24h.views)} em 24 h` : 'sem leitura nas últimas 24 h'}
                  </span>
                  {t.retencao_media !== null && t.retencao_media !== undefined && (
                    <span className="block text-[11px] text-muted truncate">retenção {porcentagem(t.retencao_media)}</span>
                  )}
                </span>
                <Tendencia serie={l.serie} />
              </div>
            ) : (
              <p className="text-[12px] text-muted leading-snug">
                Nenhum corte publicado ainda: os números aparecem aqui depois do primeiro post.
              </p>
            )}
          </>
        );
        return canal ? (
          <a key={canal.id} href={hrefDe(`/canais/${canal.id}/analises`)}
             className="card card-hover p-4 space-y-3 min-w-0 block">{conteudo}</a>
        ) : (
          <div key="sem-canal" className="card p-4 space-y-3 min-w-0">{conteudo}</div>
        );
      })}
    </div>
  );
}
