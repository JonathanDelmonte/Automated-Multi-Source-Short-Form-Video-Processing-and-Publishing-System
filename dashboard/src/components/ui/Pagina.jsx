import React from 'react';
import { Sparkles } from 'lucide-react';

// A moldura de toda página (Fase 7, etapa 7.1): a rolagem dela, a largura do
// texto e o cabeçalho com o rótulo pequeno, o título na letra da marca e as
// ações à direita. Cada página tinha o seu jeito; agora as dez têm o mesmo.

const LARGURAS = {
  estreita: 'max-w-2xl',
  media: 'max-w-3xl',
  larga: 'max-w-5xl',
  cheia: 'max-w-6xl',
};

export default function Pagina({ largura = 'larga', children }) {
  return (
    <div className="h-full overflow-y-auto custom-scrollbar animate-fade">
      <div className={`${LARGURAS[largura] || LARGURAS.larga} mx-auto px-4 py-5 sm:px-8 sm:py-8 space-y-6`}>
        {children}
      </div>
    </div>
  );
}

export function CabecalhoDaPagina({ rotulo, titulo, descricao, acoes, children }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
      <div className="min-w-0">
        {rotulo && <p className="eyebrow mb-1.5">{rotulo}</p>}
        <h1 className="font-display uppercase tracking-wide text-2xl sm:text-3xl text-ink leading-tight break-words">
          {titulo}
        </h1>
        {descricao && <p className="text-muted text-sm mt-1.5 max-w-2xl leading-relaxed">{descricao}</p>}
        {children}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-2 shrink-0">{acoes}</div>}
    </div>
  );
}

// O lugar de uma função que ainda não existe. O plano manda que todo o mapa
// tenha lugar visível desde a 7.1, marcado "em breve" e dizendo O QUE vai fazer
// -- uma tela vazia não ensina nada, e um botão que não faz nada engana.
export function EmBreve({ titulo, etapa, children, itens = [] }) {
  return (
    <section className="card p-5 sm:p-6 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge-brass"><Sparkles size={11} /> em breve</span>
        {etapa && <span className="readout">etapa {etapa}</span>}
      </div>
      {titulo && <h2 className="text-ink text-base font-medium">{titulo}</h2>}
      {children && <div className="text-muted text-sm leading-relaxed space-y-2">{children}</div>}
      {itens.length > 0 && (
        <ul className="space-y-1.5 text-sm text-ink2">
          {itens.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-muted" aria-hidden="true">·</span>
              <span className="min-w-0">{item}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Um bloco de conteúdo com título: o `card` com o `h2` pequeno que as páginas
// repetiam à mão.
export function Secao({ titulo, icone: Icone, acoes, id, children, className = '' }) {
  return (
    <section id={id} className={`card p-4 sm:p-5 space-y-3 scroll-mt-4 ${className}`}>
      {(titulo || acoes) && (
        <div className="flex items-center justify-between gap-3">
          {titulo && (
            <h2 className="text-ink text-sm font-medium inline-flex items-center gap-1.5 min-w-0">
              {Icone && <Icone size={15} className="text-muted shrink-0" />}
              <span className="truncate">{titulo}</span>
            </h2>
          )}
          {acoes && <div className="flex items-center gap-2 shrink-0">{acoes}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
