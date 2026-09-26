import React from 'react';
import { AlertTriangle, Loader2, Plus, Tv } from 'lucide-react';
import CartaoDoCanal from '../components/CartaoDoCanal';
import FormularioDoCanal from '../components/FormularioDoCanal';
import IconePlataforma from '../components/ui/IconePlataforma';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// Canais (etapa 7.1): a lista, e o "novo canal" em `#/canais/novo`.
//
// O canal é o centro da plataforma: a marca num nicho, com as contas de cada
// plataforma -- "dois galhos", nas palavras do autor: o mesmo canal no YouTube
// e no TikTok. Projetos, automação, agenda e análises passam a ser DELE.

// O que a tela diz quando a lista não veio. Motor antigo e banco fora do ar
// têm consertos diferentes, e "nenhum canal" seria mentira nos dois.
export function SituacaoDosCanais({ canais }) {
  if (canais.situacao === 'carregando') {
    return (
      <div className="py-10 flex items-center justify-center gap-2 text-muted text-sm">
        <Loader2 size={15} className="animate-spin" /> carregando os canais…
      </div>
    );
  }
  if (canais.situacao === 'motor-antigo') {
    return (
      <div className="card p-5 flex items-start gap-3">
        <AlertTriangle size={17} className="text-warn shrink-0 mt-0.5" />
        <div className="text-sm space-y-1">
          <p className="text-ink">O programa deste computador ainda não tem canais.</p>
          <p className="text-muted">
            Ele é de antes desta versão do site. Atualize pelo aviso no topo da página (o botão
            “atualizar agora”) e os canais aparecem aqui.
          </p>
        </div>
      </div>
    );
  }
  if (canais.situacao === 'erro') {
    return (
      <div className="card p-5 flex items-start gap-3">
        <AlertTriangle size={17} className="text-danger shrink-0 mt-0.5" />
        <div className="text-sm space-y-2">
          <p className="text-ink">Não consegui carregar os canais.</p>
          {canais.detalhe && <p className="text-muted">{canais.detalhe}</p>}
          <button type="button" onClick={canais.carregar} className="btn-quiet px-3 py-1.5 text-xs">tentar de novo</button>
        </div>
      </div>
    );
  }
  return null;
}

export function NovoCanal() {
  return (
    <Pagina largura="media">
      <CabecalhoDaPagina
        rotulo="canais · novo"
        titulo="Novo canal"
        descricao="A marca, o nicho e as contas por onde os cortes vão sair."
      />
      <FormularioDoCanal
        aoSalvar={(canal) => ir(`/canais/${canal.id}`)}
        aoCancelar={() => ir('/canais')}
      />
    </Pagina>
  );
}

export default function Canais() {
  const { canais } = usePainel();
  const pronto = canais.situacao === 'ok';

  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="canais"
        titulo="Canais"
        descricao="Cada canal é uma marca num nicho, com as contas dele no YouTube, no TikTok e no Instagram: os galhos por onde os cortes saem."
        acoes={pronto && (
          <a href={hrefDe('/canais/novo')} className="btn-primary px-4 py-2 text-sm">
            <Plus size={15} /> novo canal
          </a>
        )}
      />

      <SituacaoDosCanais canais={canais} />

      {pronto && canais.canais.length === 0 && (
        <div className="card p-8 sm:p-10 text-center space-y-4">
          <Tv size={30} className="mx-auto text-muted" />
          <div className="space-y-1.5 max-w-md mx-auto">
            <p className="text-ink">Nenhum canal ainda.</p>
            <p className="text-muted text-sm leading-relaxed">
              Crie um canal para cada nicho, como “Canal infantil” ou “Finanças em 1 minuto”, e ligue a ele
              as contas de cada plataforma. Os cortes que você fizer para ele ficam juntos, num lugar só.
            </p>
          </div>
          <div className="flex justify-center gap-3" aria-hidden="true">
            <IconePlataforma platform="youtube" size={26} />
            <IconePlataforma platform="tiktok" size={26} />
            <IconePlataforma platform="instagram" size={26} />
          </div>
          <a href={hrefDe('/canais/novo')} className="btn-primary px-5 py-2.5 text-sm">
            <Plus size={15} /> criar o primeiro canal
          </a>
        </div>
      )}

      {pronto && canais.canais.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {canais.canais.map((c) => <CartaoDoCanal key={c.id} canal={c} />)}
          <a
            href={hrefDe('/canais/novo')}
            className="card border-dashed min-h-[9rem] flex flex-col items-center justify-center gap-2 text-muted hover:text-ink hover:border-rule2 transition-colors"
          >
            <Plus size={20} />
            <span className="text-sm">novo canal</span>
          </a>
        </div>
      )}
    </Pagina>
  );
}
