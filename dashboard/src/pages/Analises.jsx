import React from 'react';
import CanaisLadoALado from '../components/analises/CanaisLadoALado';
import PainelDeAnalises from '../components/analises/PainelDeAnalises';
import IconePlataforma from '../components/ui/IconePlataforma';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import { hrefDe } from '../lib/rota';

// Análises, no menu (etapa 7.4): todos os canais lado a lado, e a soma de
// todos -- na aba Geral e na de cada plataforma. As telas de UM canal moram na
// aba Análises dele. Os números vêm das APIs de cada plataforma, lidos pelo
// motor a cada 6 horas (ou quando alguém aperta "medir agora").

const ABAS = [
  { id: 'geral', rotulo: 'Geral' },
  { id: 'youtube', rotulo: 'YouTube', plataforma: 'youtube' },
  { id: 'tiktok', rotulo: 'TikTok', plataforma: 'tiktok' },
  { id: 'instagram', rotulo: 'Instagram', plataforma: 'instagram' },
];

export default function Analises({ aba = 'geral' }) {
  const atual = ABAS.find((a) => a.id === aba) || ABAS[0];

  return (
    <Pagina largura="cheia">
      <CabecalhoDaPagina
        rotulo="análises"
        titulo="Análises"
        descricao="Como os canais estão indo: todos lado a lado, a soma geral e a de cada plataforma."
      />

      <nav aria-label="análises" className="-mx-4 sm:mx-0 px-4 sm:px-0 overflow-x-auto custom-scrollbar">
        <div className="flex gap-1 border-b border-rule min-w-max">
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
        </div>
      </nav>

      {atual.id === 'geral' && (
        <section className="space-y-3">
          <p className="eyebrow">os canais lado a lado</p>
          <CanaisLadoALado />
        </section>
      )}

      <section className="space-y-3">
        <p className="eyebrow">{atual.plataforma ? `todos os canais no ${atual.rotulo}` : 'todos os canais somados'}</p>
        <PainelDeAnalises key={atual.id} plataforma={atual.plataforma || null} />
      </section>
    </Pagina>
  );
}
