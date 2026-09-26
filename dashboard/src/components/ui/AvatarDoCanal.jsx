import React from 'react';
import { iniciais } from '../../lib/canais';

// A cara do canal em todo lugar que o nomeia: a imagem enviada, ou, sem ela,
// as iniciais sobre a cor do canal (o avatar "gerado" do plano). `canal` nulo
// desenha o "sem canal": um círculo tracejado, que diz que ali cabe um.
export default function AvatarDoCanal({ canal, size = 32, className = '' }) {
  const estilo = { width: size, height: size };
  if (!canal) {
    return (
      <span
        className={`inline-block shrink-0 rounded-full border border-dashed border-rule2 ${className}`}
        style={estilo}
        aria-hidden="true"
      />
    );
  }
  if (canal.avatar) {
    return (
      <img
        src={canal.avatar}
        alt=""
        className={`shrink-0 rounded-full object-cover bg-paper3 ${className}`}
        style={estilo}
      />
    );
  }
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-display tracking-wide text-white select-none ${className}`}
      style={{
        ...estilo,
        fontSize: Math.max(10, Math.round(size * 0.38)),
        background: `linear-gradient(145deg, ${canal.color || '#525252'}, color-mix(in oklab, ${canal.color || '#525252'} 55%, black))`,
      }}
      aria-hidden="true"
    >
      {iniciais(canal.name)}
    </span>
  );
}
