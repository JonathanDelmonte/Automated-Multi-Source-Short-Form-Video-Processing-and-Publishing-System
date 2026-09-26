import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Baby, Bot, CalendarDays, Inbox, Loader2, Power, RefreshCw, ShieldCheck, Zap } from 'lucide-react';
import CaixaDeAprovacao from './CaixaDeAprovacao';
import CaixaDeEntrada from './CaixaDeEntrada';
import ReceitaDoCanal from './ReceitaDoCanal';
import { Secao } from '../ui/Pagina';
import { buscarAgora, lerReceita, listarCandidatos, rodarAgora } from '../../lib/automacao';
import { janelasEmTexto, rotuloDoOffset } from '../../lib/receita.js';
import { quando } from '../../lib/publicacoes.js';
import { hrefDe } from '../../lib/rota';

// A aba Automação do canal (etapa 7.5): a receita trabalhando sozinha. Em cima,
// o que ela está fazendo agora; depois a caixa de aprovação (canal que pede),
// a receita e a caixa de entrada de fontes.

// De quanto em quanto tempo a aba pergunta de novo. O laço do motor anda de
// cinco em cinco minutos; meio minuto basta para a tela acompanhar.
const RECARGA_MS = 30_000;

function Numero({ valor, rotulo }) {
  return (
    <div className="rounded-input border border-rule px-3 py-2 min-w-0">
      <p className="text-lg font-semibold text-ink leading-none tabular-nums">{valor ?? '—'}</p>
      <p className="readout mt-1 truncate">{rotulo}</p>
    </div>
  );
}

function Situacao({ canal, tela, candidatos, aoRodar, rodando, resposta }) {
  const receita = tela.receita;
  const estado = receita.estado || {};
  const fila = (candidatos || []).filter((c) => c.status === 'novo' || c.status === 'escolhido').length;
  return (
    <section className="card p-4 sm:p-5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink text-sm font-medium flex items-center gap-2">
            {receita.ativa
              ? <><span className="w-2 h-2 rounded-full bg-[color:var(--color-ok)] shrink-0" aria-hidden="true" /> receita ligada</>
              : <><Power size={14} className="text-muted shrink-0" /> receita desligada</>}
          </p>
          <p className="text-sm text-ink2 mt-1 leading-snug">
            {receita.ativa
              ? (resposta || estado.situacao || 'Esperando a primeira volta do motor.')
              : 'Ligue a receita para o canal trabalhar sozinho.'}
          </p>
          {receita.ativa && estado.ultima_volta && (
            <p className="text-[11px] text-muted mt-1">
              última volta {quando(estado.ultima_volta)} · o motor olha de {tela.intervalo_min} em {tela.intervalo_min} min
            </p>
          )}
        </div>
        {receita.ativa && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={aoRodar} disabled={rodando}>
            {rodando ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} verificar agora
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Numero valor={tela.estoque?.agendados} rotulo="posts na agenda" />
        <Numero valor={tela.estoque?.esperando_aprovacao} rotulo="esperando você" />
        <Numero valor={candidatos ? fila : null} rotulo="vídeos na fila" />
        <Numero valor={tela.agenda?.por_dia} rotulo="posts por dia" />
      </div>
      <ul className="text-[13px] text-ink2 space-y-1.5">
        <li className="flex items-start gap-2">
          <CalendarDays size={14} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0">
            Posta às {janelasEmTexto(tela.agenda?.janelas)}, no máximo {tela.agenda?.por_dia} por dia em cada conta,
            no fuso {tela.agenda?.fuso?.nome || rotuloDoOffset(tela.agenda?.fuso?.offset_min)}.{' '}
            <a href={hrefDe(`/canais/${canal.id}/ajustes`)} className="text-muted underline underline-offset-2 hover:text-ink2">mudar</a>
          </span>
        </li>
        <li className="flex items-start gap-2">
          {canal.requires_approval
            ? <ShieldCheck size={14} className="shrink-0 mt-0.5 text-muted" />
            : <Zap size={14} className="shrink-0 mt-0.5 text-muted" />}
          <span className="min-w-0">
            {canal.requires_approval
              ? 'Cada corte espera a sua aprovação antes de ir para a agenda.'
              : 'Os cortes vão direto para a agenda, sem esperar aprovação.'}
          </span>
        </li>
        {tela.criancas?.valor && (
          <li className="flex items-start gap-2">
            <Baby size={14} className="shrink-0 mt-0.5 text-muted" />
            <span className="min-w-0">
              Todo envio pelo YouTube sai marcado “feito para crianças”
              {tela.criancas.origem === 'nicho' ? ', porque o nicho do canal é infantil' : ''}.
            </span>
          </li>
        )}
        <li className="flex items-start gap-2">
          <Bot size={14} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0 text-muted">
            A automação roda neste computador: ele precisa estar ligado, com o programa aberto. O ajudante já abre com
            o Windows; no Docker, deixe o Docker Desktop iniciar com o Windows. Post cuja hora passou com o computador
            desligado sai quando ele volta, um de cada vez.
          </span>
        </li>
      </ul>
    </section>
  );
}

export default function AutomacaoDoCanal({ canal }) {
  const [tela, setTela] = useState(null);
  const [erro, setErro] = useState(null);
  const [candidatos, setCandidatos] = useState(null);
  const [rodando, setRodando] = useState(false);
  const [resposta, setResposta] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [avisoDaBusca, setAvisoDaBusca] = useState(null);

  const carregar = useCallback(async () => {
    const [r, c] = await Promise.all([lerReceita(canal.id), listarCandidatos(canal.id)]);
    if (!r.ok) {
      setErro(r);
      return;
    }
    setErro(null);
    setTela(r.data);
    setCandidatos(c.ok ? c.data.candidatos || [] : []);
  }, [canal.id]);

  useEffect(() => {
    carregar();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') carregar();
    }, RECARGA_MS);
    return () => clearInterval(id);
  }, [carregar]);

  const rodar = async () => {
    setRodando(true);
    const r = await rodarAgora(canal.id);
    setRodando(false);
    setResposta(r.ok ? r.data.situacao : r.erro);
    carregar();
  };

  const buscar = async () => {
    setBuscando(true);
    setAvisoDaBusca(null);
    const r = await buscarAgora(canal.id);
    setBuscando(false);
    if (!r.ok) {
      setAvisoDaBusca(r.erro);
    } else if (r.data.erro) {
      setAvisoDaBusca(`A busca falhou: ${r.data.erro}`);
    } else {
      const novos = r.data.novos || 0;
      setAvisoDaBusca(novos
        ? `${novos} vídeo(s) novo(s) na fila${r.data.via === 'api' ? ', pela API do YouTube' : ''}.`
        : 'Nenhum vídeo novo desta vez.');
    }
    carregar();
  };

  if (erro) {
    return (
      <div className="card p-6 text-center space-y-2">
        <AlertTriangle size={22} className="mx-auto text-muted" />
        <p className="text-ink text-sm">{erro.motorAntigo ? 'O programa deste computador ainda não tem a automação.' : erro.erro}</p>
        {erro.motorAntigo && <p className="text-muted text-[13px]">Atualize o programa pelo aviso no topo da página.</p>}
      </div>
    );
  }
  if (tela === null) {
    return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;
  }

  const receita = tela.receita;
  const pendentes = tela.estoque?.esperando_aprovacao || 0;

  return (
    <div className="space-y-4">
      <Situacao canal={canal} tela={tela} candidatos={candidatos} aoRodar={rodar} rodando={rodando} resposta={resposta} />

      {(canal.requires_approval || pendentes > 0) && (
        <Secao titulo="caixa de aprovação" icone={ShieldCheck} id="aprovacao">
          <CaixaDeAprovacao canalId={canal.id} aoMudar={carregar}
                            vazio="Nada esperando a sua aprovação. Os cortes da receita aparecem aqui antes de ir para a agenda." />
        </Secao>
      )}

      <Secao titulo="a receita" icone={Bot}>
        <ReceitaDoCanal key={receita.updated_at || 'nova'} canal={canal} tela={tela} aoSalvar={(dados) => { setTela(dados); carregar(); }} />
      </Secao>

      {receita.id && (
        <Secao titulo="caixa de entrada de fontes" icone={Inbox}>
          {avisoDaBusca && <p className="text-sm text-ink2">{avisoDaBusca}</p>}
          <CaixaDeEntrada
            candidatos={candidatos}
            tipoDaFonte={receita.spec?.fonte?.tipo}
            aoMudar={carregar}
            aoBuscar={receita.spec?.fonte?.tipo !== 'twitch' ? buscar : null}
            buscando={buscando}
          />
        </Secao>
      )}
    </div>
  );
}
