import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowLeft, Check, Languages, Loader2, Plus, ShieldCheck, Trash2, Zap } from 'lucide-react';
import AgendaDoCanal from '../components/AgendaDoCanal';
import AutomacaoDoCanal from '../components/automacao/AutomacaoDoCanal';
import CalendarioDosCanais from '../components/CalendarioDosCanais';
import ConexaoDaConta from '../components/ConexaoDaConta';
import PainelDeAnalises from '../components/analises/PainelDeAnalises';
import FormularioDoCanal from '../components/FormularioDoCanal';
import ProjectsGrid from '../components/ProjectsGrid';
import PublicacoesTab from '../components/PublicacoesTab';
import TiposDeCriacao from '../components/TiposDeCriacao';
import AvatarDoCanal from '../components/ui/AvatarDoCanal';
import IconePlataforma from '../components/ui/IconePlataforma';
import Pagina, { Secao } from '../components/ui/Pagina';
import { SituacaoDosCanais } from './Canais';
import { apiFetch } from '../lib/api';
import { useAplicativos } from '../lib/aplicativo';
import { situacaoDoAplicativo } from '../lib/conexoes';
import { apagarCanal, IDIOMAS } from '../lib/canais';
import { DRIVERS, ORDEM_DAS_PLATAFORMAS, PLATAFORMAS } from '../lib/plataformas';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// A página de um canal (etapa 7.1), com as sete abas do mapa do plano. Onde há
// dado, o dado: os projetos, as contas, a fila e o que já saiu. Onde ainda não
// há, o "em breve" dizendo o que vai fazer e em que etapa chega.

const ABAS = [
  { id: 'visao', rotulo: 'Visão geral' },
  { id: 'criar', rotulo: 'Criar' },
  { id: 'automacao', rotulo: 'Automação' },
  { id: 'agenda', rotulo: 'Agenda' },
  { id: 'publicados', rotulo: 'Publicados' },
  { id: 'analises', rotulo: 'Análises' },
  { id: 'ajustes', rotulo: 'Ajustes' },
];

function Numero({ valor, rotulo }) {
  return (
    <div className="card px-4 py-3 min-w-0">
      <p className="font-display text-2xl text-ink leading-none">{valor ?? '—'}</p>
      <p className="readout mt-1.5 truncate">{rotulo}</p>
    </div>
  );
}

function VisaoGeral({ canal }) {
  const { canais } = usePainel();
  const [contas, setContas] = useState(null);
  const [publicacoes, setPublicacoes] = useState(null);
  const aplicativos = useAplicativos();

  const carregar = useCallback(async () => {
    try {
      const [rContas, rPub] = await Promise.all([apiFetch('/api/contas'), apiFetch('/api/publicacoes')]);
      const dadosContas = rContas.ok ? await rContas.json() : {};
      const dadosPub = rPub.ok ? await rPub.json() : null;
      setContas(dadosContas.contas || []);
      setPublicacoes(dadosPub ? dadosPub.publicacoes || [] : null);
    } catch {
      setContas([]);
      setPublicacoes(null);
    }
  }, []);
  useEffect(() => { carregar(); }, [canal.id, carregar]);

  const ids = canal.contas.map((c) => c.id);
  const doCanal = publicacoes?.filter((p) => ids.includes(p.account?.id));
  const contar = (status) => (doCanal ? doCanal.filter((p) => p.status === status).length : null);
  const porId = Object.fromEntries((contas || []).map((c) => [c.id, c]));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <Numero valor={canal.projetos || 0} rotulo="projetos" />
        <Numero valor={canal.contas.length} rotulo="contas ligadas" />
        <Numero valor={contar('scheduled')} rotulo="na fila" />
        <Numero valor={contar('published')} rotulo="publicados" />
      </div>

      <Secao titulo="os galhos do canal">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          {ORDEM_DAS_PLATAFORMAS.map((p) => {
            const daPlataforma = canal.contas.filter((c) => c.platform === p);
            if (daPlataforma.length === 0) {
              return (
                <a
                  key={p}
                  href={hrefDe(`/canais/${canal.id}/ajustes`)}
                  className="flex items-center gap-2.5 p-3 rounded-input border border-dashed border-rule2 text-muted hover:text-ink2 hover:border-[color:var(--color-accent)] transition-colors"
                >
                  <IconePlataforma platform={p} size={20} mono />
                  <span className="text-sm">ligar a conta do {PLATAFORMAS[p].nome}</span>
                </a>
              );
            }
            return daPlataforma.map((c) => (
              <div key={c.id} className="p-3 rounded-input border border-rule2 min-w-0 space-y-2" data-conta={c.handle}>
                <div className="flex items-center gap-2.5 min-w-0">
                  <IconePlataforma platform={p} size={20} />
                  <span className="min-w-0">
                    <span className="block text-sm text-ink truncate">{c.handle}</span>
                    <span className="block text-[11px] text-muted truncate">
                      {porId[c.id] ? (DRIVERS[porId[c.id].driver_agora] || porId[c.id].driver_agora) : PLATAFORMAS[p].nome}
                    </span>
                  </span>
                </div>
                {porId[c.id] && (
                  <ConexaoDaConta conta={porId[c.id]} aplicativo={situacaoDoAplicativo(aplicativos.prontos, p)}
                                  aoMudar={carregar} />
                )}
              </div>
            ));
          })}
        </div>
      </Secao>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-ink text-sm font-medium">projetos do canal</h2>
          {canal.projetos > 6 && (
            <a href={hrefDe(`/projetos?canal=${canal.id}`)} className="text-xs text-muted hover:text-ink2">ver todos ({canal.projetos})</a>
          )}
        </div>
        <ProjectsGrid
          canal={canal.id}
          limite={6}
          onOpen={(id) => ir(`/projetos/${id}`)}
          onNew={() => ir(`/criar/cortes?canal=${canal.id}`)}
          onApagado={() => canais.carregar()}
        />
      </div>
    </div>
  );
}

function Ajustes({ canal }) {
  const { canais } = usePainel();
  const [salvo, setSalvo] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [erro, setErro] = useState(null);

  const apagar = async () => {
    setApagando(true);
    setErro(null);
    const r = await apagarCanal(canal.id);
    setApagando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    await canais.carregar();
    ir('/canais');
  };

  return (
    <div className="space-y-6">
      {salvo && (
        <p className="flex items-center gap-2 text-sm text-ok"><Check size={15} /> Canal salvo.</p>
      )}
      <FormularioDoCanal key={canal.id} canal={canal} aoSalvar={() => setSalvo(true)} />
      <AgendaDoCanal key={`agenda-${canal.id}`} canal={canal} />

      <section className="card p-4 sm:p-5 space-y-3 border-[color:color-mix(in_oklab,var(--color-danger)_35%,transparent)]">
        <h2 className="text-danger text-sm font-medium">apagar o canal</h2>
        <p className="text-muted text-[13px] leading-snug">
          Apagar o canal é reorganizar: as contas e os projetos ficam, soltos, sem canal. Nenhum corte e
          nenhum histórico de publicação vai junto.
        </p>
        {erro && <p className="text-danger text-sm">{erro}</p>}
        {confirmando ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-ink2">Apagar “{canal.name}”?</span>
            <button type="button" className="btn-danger" onClick={apagar} disabled={apagando}>
              {apagando ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} apagar
            </button>
            <button type="button" className="btn-quiet" onClick={() => setConfirmando(false)}>não</button>
          </div>
        ) : (
          <button type="button" className="btn-danger" onClick={() => setConfirmando(true)}>
            <Trash2 size={14} /> apagar o canal
          </button>
        )}
      </section>
    </div>
  );
}

// As telas de análises do canal (etapa 7.4): a Geral (a soma) e uma por
// plataforma ligada -- as "três telas no canal ligado" do plano.
function AnalisesDoCanal({ canal, subaba }) {
  const plataformas = ORDEM_DAS_PLATAFORMAS.filter((p) => canal.contas.some((c) => c.platform === p));
  const atual = plataformas.includes(subaba) ? subaba : null;
  const abas = [{ id: null, rotulo: 'Geral' }, ...plataformas.map((p) => ({ id: p, rotulo: PLATAFORMAS[p].nome }))];
  return (
    <div className="space-y-4">
      {abas.length > 2 && (
        <nav aria-label="análises do canal" className="flex flex-wrap gap-1.5">
          {abas.map((a) => (
            <a
              key={a.id || 'geral'}
              href={hrefDe(`/canais/${canal.id}/analises${a.id ? `/${a.id}` : ''}`)}
              aria-current={atual === a.id ? 'page' : undefined}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-colors ${
                atual === a.id ? 'border-brass bg-paper3 text-ink' : 'border-rule text-muted hover:text-ink2 hover:border-rule2'}`}
            >
              {a.id && <IconePlataforma platform={a.id} size={13} mono={atual !== a.id} />}
              {a.rotulo}
            </a>
          ))}
        </nav>
      )}
      <PainelDeAnalises key={atual || 'geral'} canal={canal.id} plataforma={abas.length > 2 ? atual : plataformas[0] || null}
                        ondeConectar={`/canais/${canal.id}`} />
    </div>
  );
}

function ConteudoDaAba({ aba, canal, subaba }) {
  const ids = canal.contas.map((c) => c.id);
  const semContas = (
    <p className="text-muted text-sm">
      Este canal ainda não tem contas.{' '}
      <a href={hrefDe(`/canais/${canal.id}/ajustes`)} className="text-ink2 underline underline-offset-2">Ligar as contas</a>
    </p>
  );

  switch (aba) {
    case 'criar':
      return (
        <div className="space-y-4">
          <TiposDeCriacao canalId={canal.id} />
          <p className="text-muted text-[13px] leading-snug">
            O estilo dos vídeos criados por IA fica salvo aqui, no canal, e quem o configura é você: ele
            nunca é deduzido do nicho.
          </p>
        </div>
      );
    case 'automacao':
      return <AutomacaoDoCanal canal={canal} />;
    case 'agenda':
      return ids.length === 0 ? semContas : (
        <div className="space-y-4">
          <CalendarioDosCanais canalId={canal.id} />
          <PublicacoesTab
            secoes={['publicar', 'fila']}
            canal={canal.id}
            contasDoCanal={ids}
            status="scheduled"
            tituloDaFila="na fila deste canal"
            vazioDaFila="Nada na fila deste canal."
          />
        </div>
      );
    case 'publicados':
      return ids.length === 0 ? semContas : (
        <PublicacoesTab
          secoes={['fila']}
          contasDoCanal={ids}
          status="published"
          tituloDaFila="publicados"
          vazioDaFila="Nada publicado por este canal ainda."
        />
      );
    case 'analises':
      return ids.length === 0 ? semContas : <AnalisesDoCanal canal={canal} subaba={subaba} />;
    case 'ajustes':
      return <Ajustes canal={canal} />;
    default:
      return <VisaoGeral canal={canal} />;
  }
}

export default function Canal({ canalId, aba = 'visao', subaba = null }) {
  const { canais } = usePainel();
  const canal = canais.porId[canalId];

  if (canais.situacao !== 'ok') {
    return (
      <Pagina largura="larga">
        <SituacaoDosCanais canais={canais} />
      </Pagina>
    );
  }
  if (!canal) {
    return (
      <Pagina largura="media">
        <div className="card p-8 text-center space-y-3">
          <AlertTriangle size={24} className="mx-auto text-muted" />
          <p className="text-ink">Este canal não existe mais.</p>
          <a href={hrefDe('/canais')} className="btn-ghost px-4 py-2 text-sm">ver os canais</a>
        </div>
      </Pagina>
    );
  }

  const abaAtiva = ABAS.some((a) => a.id === aba) ? aba : 'visao';
  const cor = canal.color || '#525252';
  const idioma = IDIOMAS.find((i) => i.id === canal.language)?.nome || canal.language;

  return (
    <Pagina largura="larga">
      <a href={hrefDe('/canais')} className="btn-quiet px-3 py-1.5 text-xs w-fit">
        <ArrowLeft size={14} /> canais
      </a>

      <div className="card overflow-hidden">
        <div
          className="h-20 sm:h-28"
          style={{ background: `linear-gradient(120deg, ${cor} 0%, color-mix(in oklab, ${cor} 30%, var(--color-paper-2)) 75%)` }}
          aria-hidden="true"
        />
        {/* Só o avatar sobe para dentro da faixa; o nome fica embaixo dela,
            onde a cor do canal não briga com a letra. */}
        <div className="px-4 sm:px-6 pb-5 flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-5">
          <AvatarDoCanal canal={canal} size={88} className="-mt-11 ring-4 ring-[color:var(--color-paper-2)]" />
          <div className="min-w-0 flex-1 space-y-1.5 sm:pt-3">
            <h1 className="font-display uppercase tracking-wide text-2xl sm:text-3xl text-ink leading-tight break-words">{canal.name}</h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted">
              {canal.niche && <span>{canal.niche}</span>}
              {idioma && <span className="inline-flex items-center gap-1"><Languages size={12} /> {idioma}</span>}
              <span className="inline-flex items-center gap-1">
                {canal.requires_approval
                  ? <><ShieldCheck size={12} /> revisa antes de postar</>
                  : <><Zap size={12} /> posta sozinho</>}
              </span>
            </div>
            {canal.contas.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {canal.contas.map((c) => (
                  <span key={c.id} className="inline-flex items-center gap-1.5 pl-1.5 pr-2.5 py-0.5 rounded-full bg-paper3 text-xs text-ink2">
                    <IconePlataforma platform={c.platform} size={14} /> {c.handle}
                  </span>
                ))}
              </div>
            )}
          </div>
          <a href={hrefDe(`/criar/cortes?canal=${canal.id}`)} className="btn-primary px-4 py-2 text-sm shrink-0 sm:mt-3">
            <Plus size={15} /> criar cortes
          </a>
        </div>
      </div>

      <nav aria-label="abas do canal" className="-mx-4 sm:mx-0 px-4 sm:px-0 overflow-x-auto custom-scrollbar">
        <div className="flex gap-1 border-b border-rule min-w-max">
          {ABAS.map((a) => (
            <a
              key={a.id}
              href={hrefDe(`/canais/${canal.id}${a.id === 'visao' ? '' : `/${a.id}`}`)}
              aria-current={abaAtiva === a.id ? 'page' : undefined}
              className={`px-3 py-2.5 -mb-px border-b-2 text-sm whitespace-nowrap transition-colors ${
                abaAtiva === a.id ? 'border-[color:var(--color-accent)] text-ink' : 'border-transparent text-muted hover:text-ink2'}`}
            >
              {a.rotulo}
            </a>
          ))}
        </div>
      </nav>

      <ConteudoDaAba aba={abaAtiva} canal={canal} subaba={subaba} />
    </Pagina>
  );
}
