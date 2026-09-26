import React, { useEffect, useState } from 'react';
import IconePlataforma from '../components/ui/IconePlataforma';
import Pagina, { CabecalhoDaPagina, EmBreve } from '../components/ui/Pagina';
import { apiFetch } from '../lib/api';
import { hrefDe } from '../lib/rota';

// Análises (etapa 7.1): as três telas que o autor pediu -- a geral, a do
// YouTube e a do TikTok. Os números de verdade chegam na etapa 7.4; o que já dá
// para mostrar hoje é quanto saiu por cada galho, e é isso que aparece.

const ABAS = [
  { id: 'geral', rotulo: 'Geral' },
  { id: 'youtube', rotulo: 'YouTube', plataforma: 'youtube' },
  { id: 'tiktok', rotulo: 'TikTok', plataforma: 'tiktok' },
];

const O_QUE_VEM = {
  geral: [
    'Todos os canais lado a lado: visualizações, retenção e crescimento.',
    'Os cortes que mais renderam, de qualquer canal.',
    'O que a IA achou que ia render contra o que rendeu de verdade.',
  ],
  youtube: [
    'Visualizações, retenção e inscritos de cada Short, pela API oficial do YouTube.',
    'Os horários em que os Shorts do canal rendem mais.',
  ],
  tiktok: [
    'Visualizações, curtidas, comentários e compartilhamentos de cada vídeo.',
    'Os horários em que os vídeos do canal rendem mais.',
  ],
};

export default function Analises({ aba = 'geral' }) {
  const atual = ABAS.find((a) => a.id === aba) || ABAS[0];
  const [publicacoes, setPublicacoes] = useState(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await apiFetch('/api/publicacoes');
        const data = res.ok ? await res.json() : null;
        if (vivo) setPublicacoes(data ? data.publicacoes || [] : []);
      } catch {
        if (vivo) setPublicacoes([]);
      }
    })();
    return () => { vivo = false; };
  }, []);

  const publicadas = (publicacoes || []).filter((p) => p.status === 'published'
    && (!atual.plataforma || p.account?.platform === atual.plataforma));

  return (
    <Pagina largura="media">
      <CabecalhoDaPagina
        rotulo="análises"
        titulo="Análises"
        descricao="Como os canais estão indo: a visão geral e a de cada plataforma."
      />

      <nav aria-label="análises" className="flex gap-1 border-b border-rule">
        {ABAS.map((a) => (
          <a
            key={a.id}
            href={hrefDe(a.id === 'geral' ? '/analises' : `/analises/${a.id}`)}
            aria-current={atual.id === a.id ? 'page' : undefined}
            className={`inline-flex items-center gap-1.5 px-3 py-2.5 -mb-px border-b-2 text-sm whitespace-nowrap transition-colors ${
              atual.id === a.id ? 'border-[color:var(--color-accent)] text-ink' : 'border-transparent text-muted hover:text-ink2'}`}
          >
            {a.plataforma && <IconePlataforma platform={a.plataforma} size={15} mono={atual.id !== a.id} />}
            {a.rotulo}
          </a>
        ))}
      </nav>

      <section className="card p-4 sm:p-5">
        <p className="font-display text-3xl text-ink leading-none">{publicacoes === null ? '…' : publicadas.length}</p>
        <p className="text-muted text-sm mt-1.5">
          {publicadas.length === 1 ? 'corte publicado' : 'cortes publicados'}
          {atual.plataforma ? ` no ${atual.rotulo}` : ' em todas as plataformas'}
          {' '}pela fila do Virtu Clips.
        </p>
      </section>

      <EmBreve etapa="7.4" titulo="Os números de cada corte" itens={O_QUE_VEM[atual.id]} />
    </Pagina>
  );
}
