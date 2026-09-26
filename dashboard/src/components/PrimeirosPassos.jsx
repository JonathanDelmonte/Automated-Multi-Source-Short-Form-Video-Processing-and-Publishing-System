import React from 'react';
import { ArrowRight, Check } from 'lucide-react';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// Primeiros passos (etapa 7.1): para quem abre o Virtu Clips pela primeira vez
// e não sabe por onde começar. Cada passo se marca sozinho pelo que o motor já
// sabe -- a chave, os canais, as contas, os projetos --, e não por um
// "concluído" que a pessoa clica e esquece.
export default function PrimeirosPassos({ temProjetos = false, aoEsconder = null }) {
  const { keysMissing, canais } = usePainel();
  const semCanais = canais.situacao === 'motor-antigo';
  const primeiro = canais.canais[0];
  const passos = [
    {
      feito: !keysMissing,
      titulo: 'Colocar uma chave de IA',
      texto: 'É grátis e leva um minuto: a IA acha os melhores momentos dos vídeos.',
      href: '/configuracoes/chaves',
    },
    {
      feito: canais.canais.length > 0,
      titulo: 'Criar o primeiro canal',
      texto: semCanais
        ? 'O programa deste computador ainda não tem canais: atualize pelo aviso do topo.'
        : 'Um canal é a sua marca num nicho, como "Canal infantil" ou "Finanças em 1 minuto".',
      href: '/canais/novo',
    },
    {
      feito: canais.canais.some((c) => c.contas.length > 0),
      titulo: 'Ligar as contas do canal',
      texto: 'O @ do canal no YouTube, no TikTok e no Instagram.',
      href: primeiro ? `/canais/${primeiro.id}/ajustes` : '/canais/novo',
    },
    {
      feito: temProjetos,
      titulo: 'Fazer os primeiros cortes',
      texto: 'Cole o link de um vídeo e escolha o canal.',
      href: primeiro ? `/criar/cortes?canal=${primeiro.id}` : '/criar/cortes',
    },
  ];
  const feitos = passos.filter((p) => p.feito).length;

  return (
    <section className="card p-4 sm:p-5 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-ink text-sm font-medium">primeiros passos</h2>
        <span className="flex items-center gap-3">
          <span className="readout">{feitos} de {passos.length}</span>
          {aoEsconder && (
            <button type="button" onClick={aoEsconder} className="text-xs text-muted hover:text-ink2 transition-colors">
              esconder
            </button>
          )}
        </span>
      </div>
      <ol className="space-y-1">
        {passos.map((p, i) => (
          <li key={p.titulo}>
            <a
              href={hrefDe(p.href)}
              className="flex items-center gap-3 p-2 -mx-2 rounded-input hover:bg-paper3/60 transition-colors group"
            >
              <span className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 text-xs ${
                p.feito ? 'bg-ok/15 text-ok' : 'border border-rule2 text-muted'}`}>
                {p.feito ? <Check size={13} /> : i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className={`block text-sm ${p.feito ? 'text-muted line-through decoration-rule2' : 'text-ink'}`}>{p.titulo}</span>
                {!p.feito && <span className="block text-[12px] text-muted leading-snug">{p.texto}</span>}
              </span>
              {!p.feito && <ArrowRight size={15} className="text-muted group-hover:text-ink shrink-0 transition-colors" />}
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
