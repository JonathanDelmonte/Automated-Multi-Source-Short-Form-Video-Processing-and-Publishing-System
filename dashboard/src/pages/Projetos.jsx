import React, { useState } from 'react';
import { Plus, RotateCcw } from 'lucide-react';
import ProjectsGrid from '../components/ProjectsGrid';
import AvatarDoCanal from '../components/ui/AvatarDoCanal';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// Projetos (etapa 7.1): todos os vídeos processados, de todos os canais, com o
// filtro por canal no endereço (`#/projetos?canal=<id>`, ou `sem` para os que
// não estão em canal nenhum -- todo projeto de antes da Fase 7).
export default function Projetos({ canal = null }) {
  const { canais } = usePainel();
  const [versao, setVersao] = useState(0);
  const filtro = (id) => hrefDe(id ? `/projetos?canal=${encodeURIComponent(id)}` : '/projetos');
  const opcao = (ativo) =>
    `inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm whitespace-nowrap transition-colors ${
      ativo ? 'border-[color:var(--color-accent)] bg-paper3 text-ink' : 'border-rule2 text-muted hover:text-ink2'}`;
  const novo = canal && canal !== 'sem' ? `/criar/cortes?canal=${canal}` : '/criar/cortes';

  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="projetos"
        titulo="Projetos"
        descricao="Cada vídeo processado, com os cortes dele. Clique para abrir; troque o canal pelo seletor do cartão."
        acoes={(
          <>
            <button
              type="button"
              onClick={() => setVersao((v) => v + 1)}
              title="Atualizar"
              aria-label="Atualizar a lista"
              className="btn-quiet px-2.5 py-2"
            >
              <RotateCcw size={14} />
            </button>
            <a href={hrefDe(novo)} className="btn-primary px-4 py-2 text-sm">
              <Plus size={15} /> criar cortes
            </a>
          </>
        )}
      />

      {canais.situacao === 'ok' && canais.canais.length > 0 && (
        <nav aria-label="filtrar por canal" className="-mx-4 sm:mx-0 px-4 sm:px-0 overflow-x-auto custom-scrollbar">
          <div className="flex gap-2 min-w-max pb-1">
            <a href={filtro(null)} className={opcao(!canal)}>todos</a>
            {canais.canais.map((c) => (
              <a key={c.id} href={filtro(c.id)} className={opcao(canal === c.id)}>
                <AvatarDoCanal canal={c} size={18} /> {c.name}
              </a>
            ))}
            <a href={filtro('sem')} className={opcao(canal === 'sem')}>sem canal</a>
          </div>
        </nav>
      )}

      <ProjectsGrid
        key={canal || 'todos'}
        canal={canal}
        refreshKey={versao}
        onOpen={(id) => ir(`/projetos/${id}`)}
        onNew={() => ir(novo)}
        onApagado={() => canais.carregar()}
      />
    </Pagina>
  );
}
