import React from 'react';
import { Plus } from 'lucide-react';
import AvatarDoCanal from './ui/AvatarDoCanal';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// "Para qual canal?" -- a primeira pergunta do Criar (etapa 7.1). O canal
// escolhido vai junto do vídeo (`channel_id`), e o projeto aparece no canal e
// em Projetos. "Sem canal" continua valendo: cortar sem canal é o que já
// funcionava, e nada disso pode parar de funcionar.
//
// Com um motor de antes dos canais, não mostra nada: o vídeo vai sem canal, do
// jeito de antes, e o aviso do topo diz que há versão nova.
export default function SeletorDeCanal({ valor, aoEscolher }) {
  const { canais } = usePainel();
  if (canais.situacao !== 'ok') return null;

  const opcao = (ativo) =>
    `inline-flex items-center gap-2 pl-1.5 pr-3 py-1.5 rounded-full border text-sm transition-colors ${
      ativo ? 'border-[color:var(--color-accent)] bg-paper3 text-ink' : 'border-rule2 text-muted hover:text-ink2'}`;

  return (
    <div role="radiogroup" aria-label="canal do projeto" className="flex flex-wrap gap-2">
      <button type="button" role="radio" aria-checked={!valor} onClick={() => aoEscolher(null)} className={opcao(!valor)}>
        <AvatarDoCanal canal={null} size={22} />
        sem canal
      </button>
      {canais.canais.map((c) => (
        <button
          key={c.id}
          type="button"
          role="radio"
          aria-checked={valor === c.id}
          onClick={() => aoEscolher(c.id)}
          className={opcao(valor === c.id)}
        >
          <AvatarDoCanal canal={c} size={22} />
          <span className="truncate max-w-[12rem]">{c.name}</span>
        </button>
      ))}
      <a href={hrefDe('/canais/novo')} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm text-muted hover:text-ink2 transition-colors">
        <Plus size={14} /> novo canal
      </a>
    </div>
  );
}
