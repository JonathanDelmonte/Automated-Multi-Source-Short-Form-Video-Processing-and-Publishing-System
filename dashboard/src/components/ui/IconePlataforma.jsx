import React, { useId } from 'react';

// Os ícones de YouTube, TikTok e Instagram, desenhados aqui: o lucide desta
// versão tem YouTube e Instagram só em traço e não tem TikTok, e o autor quer
// "um visual bem bonito" -- as três marcas com a cor delas, onde o painel
// inteiro é preto e branco, são o que diz de relance em que galho um corte vai
// sair. `mono` desenha na cor do texto, para os lugares onde a cor gritaria.
//
// O gradiente do Instagram tem id por instância (`useId`): com um id só, o
// navegador usa a primeira definição da página, e se ela estiver num trecho
// escondido (`display: none`) o Chrome deixa todas as outras sem cor.

function YouTube({ mono }) {
  return (
    <>
      <rect x="1.5" y="5" width="21" height="14" rx="4.2" fill={mono ? 'currentColor' : '#ff0033'} />
      <path d="M10 8.9 15.4 12 10 15.1Z" fill={mono ? 'var(--color-paper)' : '#fff'} />
    </>
  );
}

// A nota do TikTok, a mesma que o painel desenhava desde o upstream.
const NOTA = 'M19.589 6.686a4.793 4.793 0 0 1-3.77-4.245V2h-3.445v13.672a2.896 2.896 0 0 1-5.201 1.743l-.002-.001.002.001a2.895 2.895 0 0 1 3.183-4.51v-3.5a6.329 6.329 0 0 0-5.394 10.692 6.33 6.33 0 0 0 10.857-4.424V8.687a8.182 8.182 0 0 0 4.773 1.526V6.79a4.831 4.831 0 0 1-1.003-.104z';

function TikTok({ mono }) {
  if (mono) return <path d={NOTA} fill="currentColor" />;
  // As duas sombras (ciano e rosa) deslocadas são o que faz a nota ser a do
  // TikTok, e não uma nota qualquer.
  return (
    <g>
      <path d={NOTA} fill="#25f4ee" transform="translate(-0.6 -0.6)" />
      <path d={NOTA} fill="#fe2c55" transform="translate(0.6 0.6)" />
      <path d={NOTA} fill="#fff" />
    </g>
  );
}

function Instagram({ mono, id }) {
  const cor = mono ? 'currentColor' : `url(#${id})`;
  return (
    <>
      {!mono && (
        <defs>
          <linearGradient id={id} x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stopColor="#feda75" />
            <stop offset="0.3" stopColor="#fa7e1e" />
            <stop offset="0.6" stopColor="#d62976" />
            <stop offset="0.85" stopColor="#962fbf" />
            <stop offset="1" stopColor="#4f5bd5" />
          </linearGradient>
        </defs>
      )}
      <rect x="3" y="3" width="18" height="18" rx="5.2" fill="none" stroke={cor} strokeWidth="2" />
      <circle cx="12" cy="12" r="4.1" fill="none" stroke={cor} strokeWidth="2" />
      <circle cx="17.4" cy="6.6" r="1.25" fill={cor} />
    </>
  );
}

const DESENHOS = { youtube: YouTube, tiktok: TikTok, instagram: Instagram };

export default function IconePlataforma({ platform, size = 16, mono = false, className = '', title }) {
  const id = `ig-${useId().replace(/:/g, '')}`;
  const Desenho = DESENHOS[platform];
  if (!Desenho) return null;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={`shrink-0 ${className}`}
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {title && <title>{title}</title>}
      <Desenho mono={mono} id={id} />
    </svg>
  );
}
