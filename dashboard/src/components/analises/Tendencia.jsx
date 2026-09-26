import React from 'react';
import { numeroInteiro, pontosDaTendencia } from '../../lib/analises';

// A tendência de um canal nos cartões lado a lado: a linha dos dias em cinza
// e o último dia com número em branco (a linha fica em segundo plano; o dia de
// hoje é o que se lê). Sem dica ao passar o mouse -- é a miniatura de um
// cartão; os números estão no cartão e na tela do canal.

export default function Tendencia({ serie, largura = 132, altura = 34 }) {
  const pontos = pontosDaTendencia(serie, { largura, altura, margem: 5 });
  const descricao = (serie || [])
    .filter((d) => d.views !== null && d.views !== undefined)
    .map((d) => `${d.dia}: ${numeroInteiro(d.views)}`)
    .join('; ');
  if (pontos.length === 0) {
    return <span className="block text-[11px] text-muted">sem leitura nos últimos dias</span>;
  }
  const [ux, uy] = pontos[pontos.length - 1];
  return (
    <svg width={largura} height={altura} role="img" aria-label={`visualizações por dia: ${descricao}`} className="block overflow-visible">
      {pontos.length > 1 && (
        <polyline points={pontos.map(([x, y]) => `${x},${y}`).join(' ')} fill="none"
                  stroke="#8c8c8c" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      )}
      <circle cx={ux} cy={uy} r="4" fill="#f5f5f5" stroke="#0e0e0e" strokeWidth="2" />
    </svg>
  );
}
