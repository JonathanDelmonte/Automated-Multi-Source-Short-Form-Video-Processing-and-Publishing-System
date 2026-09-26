import React, { useState } from 'react';
import { CheckCircle2, ExternalLink, Link2, Loader2, Trash2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { hrefDe } from '../lib/rota';
import { usePainel } from '../lib/painel';
import IconePlataforma from './ui/IconePlataforma';
import AvatarDoCanal from './ui/AvatarDoCanal';
import { PLATAFORMAS } from '../lib/plataformas';
import { agruparPorCorte, estadoDoGalho } from '../lib/publicacoes';

// A fila de publicações, por corte (etapa 7.3): cada corte com os galhos dele,
// um por conta. O autor, 25-set-2026: "vai virar uma ramificação, dois galhos
// (...) e depois você gerencia cada um individualmente" -- por isso cada linha
// tem as ações dela, e o corte é só o agrupador.
//
// O "já publiquei" pede o link do post: sem ele, o que se posta à mão nunca é
// medido. Dá para marcar sem link, e o link pode vir depois (a linha publicada
// sem link oferece "adicionar link").

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
        Cole o link do post no {nome}. É com ele que o programa mede as visualizações.
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

export default function FilaDePublicacoes({ publicacoes, ocupado, aoMudar, vazio }) {
  const { canais } = usePainel();
  const [abertoPara, setAbertoPara] = useState(null);
  const [aviso, setAviso] = useState(null);
  const [tirando, setTirando] = useState(null);

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

  return (
    <div className="space-y-3">
      {aviso && <p className="text-[13px] text-brass">{aviso}</p>}
      <ul className="space-y-3">
        {agruparPorCorte(publicacoes).map((grupo) => {
          const idsDosCanais = [...new Set(grupo.galhos.map((g) => g.account?.channel_id).filter(Boolean))];
          const canal = idsDosCanais.length === 1 ? canais.porId[idsDosCanais[0]] : null;
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
                {grupo.galhos.map((p) => {
                  const estado = estadoDoGalho(p);
                  const nome = PLATAFORMAS[p.account?.platform]?.nome || p.account?.platform;
                  const aberto = abertoPara === p.id;
                  return (
                    <li key={p.id} className="text-[13px]" data-plataforma={p.account?.platform}>
                      <div className="flex items-center gap-2 min-w-0">
                        <IconePlataforma platform={p.account?.platform} size={15} title={nome} />
                        <span className="text-ink2 truncate max-w-[9rem] sm:max-w-[14rem]">{p.account?.handle}</span>
                        <span className={`text-xs ${estado.cor} truncate`}>{estado.texto}</span>
                        <span className="ml-auto flex items-center gap-2.5 shrink-0">
                          {p.url && (
                            <a href={p.url} target="_blank" rel="noopener noreferrer"
                               className="text-muted hover:text-ink2" title="abrir o post">
                              <ExternalLink size={14} />
                            </a>
                          )}
                          {p.status === 'published' && !p.url && !aberto && (
                            <button type="button" className="text-xs text-muted hover:text-ink2 inline-flex items-center gap-1"
                                    onClick={() => setAbertoPara(p.id)} disabled={ocupado}>
                              <Link2 size={13} /> adicionar link
                            </button>
                          )}
                          {p.status === 'scheduled' && !aberto && (
                            <button type="button" className="text-muted hover:text-ok" title="já publiquei"
                                    onClick={() => { setAviso(null); setAbertoPara(p.id); }} disabled={ocupado}>
                              <CheckCircle2 size={15} />
                            </button>
                          )}
                          {p.status !== 'published' && (
                            <button type="button" className="text-muted hover:text-danger" title="tirar da fila"
                                    onClick={() => tirar(p)} disabled={ocupado || tirando === p.id}>
                              {tirando === p.id ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                            </button>
                          )}
                        </span>
                      </div>
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
                })}
              </ul>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
