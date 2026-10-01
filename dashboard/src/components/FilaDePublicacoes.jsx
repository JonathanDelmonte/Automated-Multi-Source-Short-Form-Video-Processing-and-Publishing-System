import React, { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronUp, ExternalLink, Link2, ListVideo, Loader2, RotateCcw, Smartphone, Trash2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { hrefDe } from '../lib/rota';
import { usePainel } from '../lib/painel';
import IconePlataforma from './ui/IconePlataforma';
import AvatarDoCanal from './ui/AvatarDoCanal';
import { PLATAFORMAS } from '../lib/plataformas';
import { agruparNaFila, estadoDoGalho } from '../lib/publicacoes';
import { situacaoDaExecucao } from '../lib/frota.js';

// A fila de publicações, por corte (etapa 7.3): cada corte com os galhos dele,
// um por conta. O autor, 25-set-2026: "vai virar uma ramificação, dois galhos
// (...) e depois você gerencia cada um individualmente" -- por isso cada linha
// tem as ações dela, e o corte é só o agrupador.
//
// O "já publiquei" pede o link do post: sem ele, o que se posta à mão nunca é
// medido. Dá para marcar sem link, e o link pode vir depois (a linha publicada
// sem link oferece "adicionar link").
//
// A que falhou tem "tentar de novo" (7.6): volta para a fila e sai na próxima
// volta do agendador. Numa série, a lixeira é "pular esta parte" -- as
// seguintes, paradas atrás dela, voltam a andar na ordem.
//
// Uma série é um item só (`agruparNaFila`): uma linha por conta com a
// contagem e a parte que pede atenção -- é nela que estão as ações --, e as
// partes, em ordem, num clique. Aberta por inteiro, uma live de 1 hora eram
// 60 grupos, e a parte que falhou ficava no fim da página.

function FormularioDoLink({ publicacao, aoTerminar, cancelar }) {
  const [link, setLink] = useState(publicacao.url || '');
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const nome = PLATAFORMAS[publicacao.account?.platform]?.nome || 'plataforma';

  const enviar = async (comLink) => {
    setEnviando(true);
    setErro(null);
    try {
      const res = await apiFetch(`/api/publicacoes/${publicacao.id}/publicado`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(comLink ? { url: link.trim() } : {}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro(data.detail || 'Não deu para marcar.');
        return;
      }
      aoTerminar(data.aviso || null);
    } catch {
      setErro('Não consegui falar com o programa.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => { e.preventDefault(); if (link.trim()) enviar(true); }}
    >
      <label className="block text-[12px] text-muted" htmlFor={`link-${publicacao.id}`}>
        {PLATAFORMAS[publicacao.account?.platform]?.chinesa
          // As chinesas (7.10): o "compartilhar" do app copia um texto com o
          // link no meio, e o motor o tira de lá. Números, só no app.
          ? `Cole o link do post no ${nome} (ou o texto inteiro que o "compartilhar" do app copia). `
            + 'Ele fica guardado com a publicação; os números do post ficam só no app.'
          : `Cole o link do post no ${nome}. É com ele que o programa mede as visualizações.`}
      </label>
      <div className="flex flex-wrap gap-2">
        <input
          id={`link-${publicacao.id}`}
          className="input-field text-sm py-1.5 flex-1 min-w-[14rem]"
          placeholder={PLATAFORMAS[publicacao.account?.platform]?.exemploDeLink || 'https://…'}
          value={link}
          onChange={(e) => setLink(e.target.value)}
          autoFocus
          inputMode="url"
        />
        <button type="submit" className="btn-primary text-sm" disabled={enviando || !link.trim()}>
          {enviando ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
          salvar
        </button>
        <button type="button" className="btn-quiet text-sm" onClick={cancelar} disabled={enviando}>
          voltar
        </button>
      </div>
      {publicacao.status !== 'published' && (
        <button type="button" className="text-[12px] text-muted hover:text-ink2 underline underline-offset-2"
                onClick={() => enviar(false)} disabled={enviando}>
          marcar como publicado sem o link
        </button>
      )}
      {erro && <p className="text-danger text-[13px]">{erro}</p>}
    </form>
  );
}

export default function FilaDePublicacoes({ publicacoes, ocupado, aoMudar, vazio, filtrada = false }) {
  const { canais } = usePainel();
  // O formulário do link aberto: `lugar:id`, porque a mesma parte de uma série
  // aparece no resumo da conta e na lista das partes.
  const [abertoPara, setAbertoPara] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [tirando, setTirando] = useState(null);
  const [tentando, setTentando] = useState(null);
  const [seriesAbertas, setSeriesAbertas] = useState(() => new Set());

  if (publicacoes.length === 0) {
    return <p className="text-muted text-[13px]">{vazio}</p>;
  }

  const tirar = async (p) => {
    setTirando(p.id);
    try {
      await apiFetch(`/api/publicacoes/${p.id}`, { method: 'DELETE' });
      await aoMudar();
    } finally {
      setTirando(null);
    }
  };

  const tentarDeNovo = async (p) => {
    setTentando(p.id);
    setAviso(null);
    try {
      const res = await apiFetch(`/api/publicacoes/${p.id}/tentar`, { method: 'POST' });
      if (res.status === 404 || res.status === 405) {
        // O programa de antes da 7.6 não tem a rota.
        setAviso('Para tentar de novo, atualize o programa deste computador. O aviso no topo do site tem o botão.');
      } else if (!res.ok) {
        setAviso((await res.json().catch(() => ({}))).detail || 'Não deu para tentar de novo.');
      } else {
        setAviso('Voltou para a fila: sai na próxima volta do agendador, em até um minuto, pela trava de sempre.');
        await aoMudar();
      }
    } catch {
      setAviso('Não consegui falar com o programa.');
    } finally {
      setTentando(null);
    }
  };

  const alternarSerie = (chave) => setSeriesAbertas((antes) => {
    const depois = new Set(antes);
    if (depois.has(chave)) depois.delete(chave);
    else depois.add(chave);
    return depois;
  });

  // O canal de um grupo de galhos, quando todos são do mesmo.
  const canalDe = (galhos) => {
    const ids = [...new Set(galhos.map((g) => g.account?.channel_id).filter(Boolean))];
    return ids.length === 1 ? canais.porId[ids[0]] : null;
  };

  // Uma linha por galho: a conta, o estado e as ações. Com `resumo` (uma conta
  // de uma série), o estado dá lugar à contagem e ao que pede atenção.
  const linhaDoGalho = (p, lugar, resumo = null) => {
    const estado = estadoDoGalho(p);
    const nome = PLATAFORMAS[p.account?.platform]?.nome || p.account?.platform;
    const chave = `${lugar}:${p.id}`;
    const aberto = abertoPara === chave;
    return (
      <li key={p.id} className="text-[13px]" data-plataforma={p.account?.platform}>
        <div className="flex items-center gap-2 min-w-0">
          <IconePlataforma platform={p.account?.platform} size={15} title={nome} />
          {/* No celular o estado desce para a linha de baixo em vez de ser
              cortado: "agendado · 26 de set., 13:…" escondia justamente a hora. */}
          <span className="min-w-0 flex flex-wrap items-baseline gap-x-2">
            <span className="text-ink2 truncate max-w-full sm:max-w-[14rem]">{p.account?.handle}</span>
            {resumo ? (
              <>
                <span className="text-xs text-muted whitespace-nowrap">{resumo.contagem}</span>
                {resumo.texto && <span className={`text-xs ${resumo.cor}`}>{resumo.texto}</span>}
              </>
            ) : (
              <span className={`text-xs ${estado.cor} whitespace-nowrap`}>{estado.texto}</span>
            )}
          </span>
          <span className="ml-auto flex items-center gap-2.5 shrink-0">
            {p.url && (
              <a href={p.url} target="_blank" rel="noopener noreferrer"
                 className="text-muted hover:text-ink2" title="abrir o post">
                <ExternalLink size={14} />
              </a>
            )}
            {p.status === 'published' && !p.url && !aberto && (
              <button type="button" className="text-xs text-muted hover:text-ink2 inline-flex items-center gap-1"
                      onClick={() => setAbertoPara(chave)} disabled={ocupado}>
                <Link2 size={13} /> adicionar link
              </button>
            )}
            {p.status === 'scheduled' && !aberto && (
              <button type="button" className="text-muted hover:text-ok" title="já publiquei"
                      onClick={() => { setAviso(null); setAbertoPara(chave); }} disabled={ocupado}>
                <CheckCircle2 size={15} />
              </button>
            )}
            {p.status === 'failed' && (
              <button type="button" className="text-muted hover:text-brass"
                      title="tentar de novo (confira antes, na plataforma, se ele não subiu mesmo assim)"
                      onClick={() => tentarDeNovo(p)} disabled={ocupado || tentando === p.id}>
                {tentando === p.id ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
              </button>
            )}
            {p.status !== 'published' && (
              <button type="button" className="text-muted hover:text-danger"
                      title={p.serie ? 'pular esta parte (a série segue sem ela)' : 'tirar da fila'}
                      onClick={() => tirar(p)} disabled={ocupado || tirando === p.id}>
                {tirando === p.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              </button>
            )}
          </span>
        </div>
        {p.aparelho && (
          // A frota (7.9): em que celular este galho saiu e o que aconteceu la.
          <p className="mt-1 pl-6 text-[12px] text-muted leading-snug flex items-start gap-1.5" data-no-aparelho>
            <Smartphone size={12} className="shrink-0 mt-0.5" />
            <span className="min-w-0">
              <a href={hrefDe(`/frota/${p.aparelho.device_id}`)} className="text-ink2 hover:underline">
                {p.aparelho.nome || 'aparelho'}
              </a>
              {p.aparelho.situacao ? `: ${situacaoDaExecucao(p.aparelho.situacao).texto}` : ''}
              {p.aparelho.detalhe && p.aparelho.situacao !== 'publicado' && p.aparelho.situacao !== 'entregue'
                ? ` — ${p.aparelho.detalhe}` : ''}
            </span>
          </p>
        )}
        {aberto && (
          <FormularioDoLink
            publicacao={p}
            cancelar={() => setAbertoPara(null)}
            aoTerminar={async (msg) => {
              setAbertoPara(null);
              setAviso(msg);
              await aoMudar();
            }}
          />
        )}
      </li>
    );
  };

  const umCorte = (grupo) => {
    const canal = canalDe(grupo.galhos);
    const titulo = grupo.clip.title || `corte ${(grupo.clip.index ?? 0) + 1}`;
    return (
      <li key={grupo.chave} className="border-t border-rule pt-3 first:border-0 first:pt-0">
        <div className="flex items-center gap-2 min-w-0">
          {canal && <AvatarDoCanal canal={canal} size={18} />}
          <span className="text-ink text-sm truncate flex-1" title={titulo}>{titulo}</span>
          {grupo.clip.job_id && (
            <a href={hrefDe(`/projetos/${grupo.clip.job_id}`)}
               className="text-[11px] text-muted hover:text-ink2 shrink-0">projeto</a>
          )}
        </div>
        <ul className="mt-1.5 space-y-1.5 pl-1">
          {grupo.galhos.map((p) => linhaDoGalho(p, 'corte'))}
        </ul>
      </li>
    );
  };

  // Uma série inteira num item: o resumo de cada conta (com a parte que pede
  // atenção e as ações dela) e, num clique, as partes em ordem.
  const umaSerie = (item) => {
    const galhos = item.grupos.flatMap((g) => g.galhos);
    const canal = canalDe(galhos);
    const titulo = item.serie.nome || 'série';
    const jobId = item.grupos.find((g) => g.clip.job_id)?.clip.job_id;
    const playlist = galhos.find((g) => g.serie?.playlist)?.serie.playlist;
    const partes = item.serie.partes || item.grupos.length;
    const aberta = seriesAbertas.has(item.chave);
    return (
      <li key={item.chave} data-serie={item.serie.id}
          className="border-t border-rule pt-3 first:border-0 first:pt-0">
        <div className="flex items-center gap-2 min-w-0">
          {canal && <AvatarDoCanal canal={canal} size={18} />}
          <span className="text-ink text-sm truncate flex-1" title={titulo}>{titulo}</span>
          {jobId && (
            <a href={hrefDe(`/projetos/${jobId}`)}
               className="text-[11px] text-muted hover:text-ink2 shrink-0">projeto</a>
          )}
        </div>
        <p className="mt-0.5 flex items-center gap-2 min-w-0 text-[11px] text-muted">
          <ListVideo size={12} className="shrink-0" />
          <span className="truncate">série de {partes} parte{partes === 1 ? '' : 's'}</span>
          {playlist && (
            <a href={playlist} target="_blank" rel="noopener noreferrer"
               className="shrink-0 inline-flex items-center gap-1 hover:text-ink2">
              playlist <ExternalLink size={11} />
            </a>
          )}
        </p>
        <ul className="mt-1.5 space-y-1.5 pl-1">
          {item.contas.map((c) => (c.foco ? linhaDoGalho(c.foco, 'resumo', c) : (
            <li key={c.chave} className="text-[13px]" data-plataforma={c.conta.platform}>
              <div className="flex items-center gap-2 min-w-0">
                <IconePlataforma platform={c.conta.platform} size={15}
                                 title={PLATAFORMAS[c.conta.platform]?.nome || c.conta.platform} />
                <span className="min-w-0 flex flex-wrap items-baseline gap-x-2">
                  <span className="text-ink2 truncate max-w-full sm:max-w-[14rem]">{c.conta.handle}</span>
                  <span className="text-xs text-muted whitespace-nowrap">{c.contagem}</span>
                  {c.texto && <span className={`text-xs ${c.cor}`}>{c.texto}</span>}
                </span>
              </div>
            </li>
          )))}
        </ul>
        <button type="button" onClick={() => alternarSerie(item.chave)} aria-expanded={aberta}
                className="mt-1.5 inline-flex items-center gap-1 text-[12px] text-muted hover:text-ink2">
          {aberta ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          {aberta ? 'esconder as partes' : `ver as ${item.grupos.length} parte${item.grupos.length === 1 ? '' : 's'}`}
        </button>
        {aberta && (
          <ul className="mt-2 space-y-2.5 pl-3 border-l border-rule">
            {item.grupos.map((grupo) => (
              <li key={grupo.chave}>
                <span className="block text-ink2 text-[13px] truncate"
                      title={grupo.clip.title || ''}>
                  {grupo.clip.title || `parte ${grupo.serie?.parte ?? ''}`}
                </span>
                <ul className="mt-1 space-y-1.5 pl-1">
                  {grupo.galhos.map((p) => linhaDoGalho(p, 'lista'))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <div className="space-y-3">
      {aviso && <p className="text-[13px] text-brass">{aviso}</p>}
      <ul className="space-y-3">
        {agruparNaFila(publicacoes, { filtrada }).map((item) => (
          item.tipo === 'serie' ? umaSerie(item) : umCorte(item.grupo)
        ))}
      </ul>
    </div>
  );
}
