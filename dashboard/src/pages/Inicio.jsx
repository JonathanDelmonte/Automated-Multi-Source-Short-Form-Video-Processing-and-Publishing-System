import React, { useState } from 'react';
import { ArrowRight, CalendarDays, Image, Plus, Scissors } from 'lucide-react';
import CartaoDoCanal from '../components/CartaoDoCanal';
import PrimeirosPassos from '../components/PrimeirosPassos';
import ProjectsList from '../components/ProjectsList';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import { SituacaoDosCanais } from './Canais';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// Início (etapa 7.1): os canais, o que está em andamento e o próximo passo.
// Para quem chega pela primeira vez, os primeiros passos vêm antes de tudo;
// eles somem sozinhos quando os quatro estão feitos, ou quando a pessoa manda.

const ESCONDIDO = 'cortes_primeiros_passos';

function lerEscondido() {
  try {
    return localStorage.getItem(ESCONDIDO) === 'escondido';
  } catch {
    return false;
  }
}

function Atalho({ href, icone, titulo, texto }) {
  const Icone = icone;
  return (
    <a href={hrefDe(href)} className="card p-4 flex items-center gap-3 group hover:border-rule2 transition-colors min-w-0">
      <span className="w-9 h-9 rounded-input bg-paper3 flex items-center justify-center shrink-0 text-ink2">
        <Icone size={17} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-ink">{titulo}</span>
        <span className="block text-xs text-muted truncate">{texto}</span>
      </span>
      <ArrowRight size={15} className="text-muted group-hover:text-ink shrink-0 transition-colors" />
    </a>
  );
}

export default function Inicio() {
  const { canais, keysMissing } = usePainel();
  const [escondido, setEscondido] = useState(lerEscondido);
  const [projetos, setProjetos] = useState(null);

  const temProjetos = (projetos || 0) > 0;
  const tudoFeito = !keysMissing && canais.canais.length > 0
    && canais.canais.some((c) => c.contas.length > 0) && temProjetos;
  const esconder = () => {
    try { localStorage.setItem(ESCONDIDO, 'escondido'); } catch { /* vale só nesta aba */ }
    setEscondido(true);
  };

  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="início"
        titulo="Virtu Clips"
        descricao="Seus canais, o que está em andamento e o próximo passo."
        acoes={(
          <>
            <a href={hrefDe('/canais/novo')} className="btn-ghost px-4 py-2 text-sm"><Plus size={15} /> canal</a>
            <a href={hrefDe('/criar/cortes')} className="btn-primary px-4 py-2 text-sm"><Scissors size={15} /> criar cortes</a>
          </>
        )}
      />

      {!escondido && !tudoFeito && projetos !== null && (
        <PrimeirosPassos temProjetos={temProjetos} aoEsconder={esconder} />
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="eyebrow">seus canais</p>
          {canais.canais.length > 0 && (
            <a href={hrefDe('/canais')} className="text-xs text-muted hover:text-ink2">ver todos</a>
          )}
        </div>
        <SituacaoDosCanais canais={canais} />
        {canais.situacao === 'ok' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {canais.canais.slice(0, 7).map((c) => <CartaoDoCanal key={c.id} canal={c} compacto />)}
            <a
              href={hrefDe('/canais/novo')}
              className="card border-dashed min-h-[8rem] flex flex-col items-center justify-center gap-2 text-muted hover:text-ink hover:border-rule2 transition-colors"
            >
              <Plus size={20} />
              <span className="text-sm">{canais.canais.length ? 'novo canal' : 'criar o primeiro canal'}</span>
            </a>
          </div>
        )}
      </section>

      <ProjectsList
        titulo="recentes"
        limite={6}
        onOpen={(id) => ir(`/projetos/${id}`)}
        onApagado={() => canais.carregar()}
        aoCarregar={(lista) => setProjetos(lista.length)}
      />

      <section className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Atalho href="/ferramentas/studio" icone={Image} titulo="YouTube Studio" texto="títulos e miniaturas para um vídeo" />
        <Atalho href="/agenda" icone={CalendarDays} titulo="Agenda" texto="pacote do dia, publicar e a fila" />
      </section>
    </Pagina>
  );
}
