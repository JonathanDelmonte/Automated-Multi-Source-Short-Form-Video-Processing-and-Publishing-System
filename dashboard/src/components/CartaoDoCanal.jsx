import React from 'react';
import { ChevronRight } from 'lucide-react';
import AvatarDoCanal from './ui/AvatarDoCanal';
import IconePlataforma from './ui/IconePlataforma';
import { PLATAFORMAS } from '../lib/plataformas';
import { hrefDe } from '../lib/rota';

// Um canal na lista: a faixa na cor dele, a cara, o nicho e os galhos -- um
// ícone por plataforma ligada, que é o que diz de relance onde ele publica.
export default function CartaoDoCanal({ canal, compacto = false }) {
  const cor = canal.color || '#525252';
  return (
    <a
      href={hrefDe(`/canais/${canal.id}`)}
      className="card overflow-hidden group flex flex-col hover:border-rule2 transition-colors min-w-0"
    >
      <div
        className={compacto ? 'h-10' : 'h-16'}
        style={{ background: `linear-gradient(120deg, ${cor} 0%, color-mix(in oklab, ${cor} 35%, var(--color-paper-2)) 70%)` }}
        aria-hidden="true"
      />
      <div className="px-4 pb-4 -mt-6 flex flex-col gap-2 min-w-0">
        <div className="flex items-end justify-between gap-2">
          <AvatarDoCanal canal={canal} size={compacto ? 44 : 52} className="ring-4 ring-[color:var(--color-paper-2)]" />
          <ChevronRight size={16} className="text-muted group-hover:text-ink transition-colors mb-1" />
        </div>
        <div className="min-w-0">
          <p className="text-ink font-medium truncate">{canal.name}</p>
          <p className="text-muted text-xs truncate">{canal.niche || 'sem nicho'}</p>
        </div>
        <div className="flex items-center justify-between gap-2 min-w-0">
          <span className="flex items-center gap-1.5 min-w-0">
            {canal.contas.length === 0 ? (
              <span className="text-muted text-xs">nenhuma conta ligada</span>
            ) : canal.contas.map((c) => (
              <IconePlataforma
                key={c.id}
                platform={c.platform}
                size={18}
                title={`${PLATAFORMAS[c.platform]?.nome || c.platform}: ${c.handle}`}
              />
            ))}
          </span>
          <span className="readout shrink-0">
            {canal.projetos || 0} projeto{canal.projetos === 1 ? '' : 's'}
          </span>
        </div>
      </div>
    </a>
  );
}
