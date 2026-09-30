import React, { useId } from 'react';

// Os ícones de YouTube, TikTok e Instagram, desenhados aqui: o lucide desta
// versão tem YouTube e Instagram só em traço e não tem TikTok, e o autor quer
// "um visual bem bonito" -- as três marcas com a cor delas, onde o painel
// inteiro é preto e branco, são o que diz de relance em que galho um corte vai
// sair. `mono` desenha na cor do texto, para os lugares onde a cor gritaria.
//
// As chinesas (7.10) são uma lembrança da marca, não a logo: a nota do TikTok
// num quadrado escuro é o Douyin (é a mesma nota, na mesma empresa), a câmera
// num quadrado laranja é o Kuaishou, a TV com antenas é o Bilibili, e o
// quadrado vermelho com o nome é o Xiaohongshu -- a logo dele é o próprio nome.
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

// A nota do TikTok encolhida para caber no quadrado do app.
const NOTA_NO_QUADRADO = 'translate(4.9 4.9) scale(0.59)';

function Douyin({ mono }) {
  if (mono) {
    return (
      <>
        <rect x="2" y="2" width="20" height="20" rx="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d={NOTA} fill="currentColor" transform={NOTA_NO_QUADRADO} />
      </>
    );
  }
  return (
    <>
      <rect x="1.5" y="1.5" width="21" height="21" rx="5.2" fill="#161823" stroke="#3a3d4a" strokeWidth="0.8" />
      <g transform={NOTA_NO_QUADRADO}>
        <path d={NOTA} fill="#25f4ee" transform="translate(-0.9 -0.9)" />
        <path d={NOTA} fill="#fe2c55" transform="translate(0.9 0.9)" />
        <path d={NOTA} fill="#fff" />
      </g>
    </>
  );
}

function Kuaishou({ mono }) {
  const traco = mono ? 'currentColor' : '#fff';
  return (
    <>
      {mono
        ? <rect x="2" y="2" width="20" height="20" rx="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        : <rect x="1.5" y="1.5" width="21" height="21" rx="5.5" fill="#ff4906" />}
      <circle cx="8.7" cy="8.3" r="2.5" fill={traco} />
      <circle cx="14.3" cy="8.7" r="1.9" fill={traco} />
      <rect x="5.8" y="11.6" width="9.8" height="6.6" rx="1.8" fill={traco} />
      <path d="M15.3 13.5 18.7 11.8v6.2l-3.4-1.7Z" fill={traco} />
    </>
  );
}

function Bilibili({ mono }) {
  const cor = mono ? 'currentColor' : '#00aeec';
  return (
    <g fill="none" stroke={cor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2.5" y="6.5" width="19" height="14" rx="3.6" />
      <path d="M7.6 2.8 10 6.3M16.4 2.8 14 6.3" />
      <path d="M7.8 11.7l2 .9M16.2 11.7l-2 .9" />
      <path d="M10 15.8c.7.8 1.3.8 2 0 .7.8 1.3.8 2 0" strokeWidth="1.5" />
    </g>
  );
}

function Xiaohongshu({ mono }) {
  return (
    <>
      {mono
        ? <rect x="2" y="2" width="20" height="20" rx="5" fill="none" stroke="currentColor" strokeWidth="1.6" />
        : <rect x="1.5" y="1.5" width="21" height="21" rx="5.2" fill="#ff2442" />}
      <text
        x="12"
        y="14.6"
        textAnchor="middle"
        fontSize="6.6"
        fontWeight="700"
        fill={mono ? 'currentColor' : '#fff'}
        fontFamily="'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans CJK SC','Noto Sans SC',sans-serif"
      >
        小红书
      </text>
    </>
  );
}

const DESENHOS = {
  youtube: YouTube,
  tiktok: TikTok,
  instagram: Instagram,
  douyin: Douyin,
  kuaishou: Kuaishou,
  bilibili: Bilibili,
  xiaohongshu: Xiaohongshu,
};

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
