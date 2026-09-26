import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import AvatarDoCanal from './ui/AvatarDoCanal';
import IconePlataforma from './ui/IconePlataforma';
import { Secao } from './ui/Pagina';
import { apiFetch } from '../lib/api';
import { eHoje, horaCurta, horaDoPost, rotuloDoDia, semana, somarDias } from '../lib/calendario.js';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// O calendário de todos os canais (etapa 7.5): a semana, dia a dia, com a cor e
// a cara de cada canal. O que já foi ao ar aparece apagado, na hora em que foi;
// o que vai sair, na hora marcada -- no relógio de quem olha.

// Duas linhas: a hora e de onde sai em cima, o título embaixo com a largura
// inteira da coluna -- com sete colunas no computador, numa linha só o título
// era espremido até sumir.
function Post({ p, canal }) {
  const hora = horaDoPost(p);
  const saiu = p.status === 'published';
  const conteudo = (
    <>
      <span className="flex items-center gap-1.5 min-w-0">
        <span className="text-[11px] tabular-nums text-muted">{horaCurta(hora)}</span>
        <IconePlataforma platform={p.account?.platform} size={12} mono={saiu} />
        {canal && <AvatarDoCanal canal={canal} size={14} />}
        {saiu && <span className="text-[10px] text-muted">saiu</span>}
      </span>
      <span className={`block min-w-0 text-[12px] leading-snug line-clamp-2 break-words ${saiu ? 'text-muted' : 'text-ink2'}`}>
        {p.clip?.title || `Corte ${(p.clip?.index ?? 0) + 1}`}
      </span>
    </>
  );
  const classe = 'flex flex-col gap-0.5 px-2 py-1.5 rounded-input border min-w-0 transition-colors';
  const cor = canal?.color ? { borderLeftColor: canal.color, borderLeftWidth: 3 } : undefined;
  return p.clip?.job_id ? (
    <a href={hrefDe(`/projetos/${p.clip.job_id}`)} className={`${classe} border-rule hover:border-rule2`} style={cor}
       title={`${p.account?.platform}/${p.account?.handle}${saiu ? ' · publicado' : ''}`}>
      {conteudo}
    </a>
  ) : (
    <div className={`${classe} border-rule`} style={cor}>{conteudo}</div>
  );
}

export default function CalendarioDosCanais({ canalId = null }) {
  const { canais } = usePainel();
  const [publicacoes, setPublicacoes] = useState(null);
  const [inicio, setInicio] = useState(() => somarDias(new Date(), 0));

  const carregar = useCallback(async () => {
    try {
      const r = await apiFetch('/api/publicacoes');
      const dados = r.ok ? await r.json() : {};
      setPublicacoes(dados.publicacoes || []);
    } catch {
      setPublicacoes([]);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const filtradas = useMemo(() => (publicacoes || []).filter(
    (p) => !canalId || p.account?.channel_id === canalId), [publicacoes, canalId]);
  const dias = useMemo(() => semana(filtradas, inicio), [filtradas, inicio]);
  const total = dias.reduce((n, d) => n + d.posts.length, 0);

  return (
    <Secao
      titulo="calendário"
      icone={CalendarDays}
      acoes={(
        <span className="flex items-center gap-1">
          <button type="button" className="btn-quiet px-2 py-1" onClick={() => setInicio((d) => somarDias(d, -7))}
                  aria-label="semana anterior"><ChevronLeft size={15} /></button>
          <button type="button" className="btn-quiet px-2 py-1 text-xs" onClick={() => setInicio(somarDias(new Date(), 0))}>hoje</button>
          <button type="button" className="btn-quiet px-2 py-1" onClick={() => setInicio((d) => somarDias(d, 7))}
                  aria-label="próxima semana"><ChevronRight size={15} /></button>
        </span>
      )}
    >
      {publicacoes === null ? (
        <Loader2 size={16} className="animate-spin text-muted" aria-label="carregando" />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-7 gap-2">
            {dias.map((d) => (
              <div key={d.dia} className={`rounded-input border p-2 space-y-1.5 min-w-0 ${eHoje(d.dia) ? 'border-rule2 bg-paper3' : 'border-rule'}`}
                   data-dia={d.dia}>
                <p className={`text-[11px] ${eHoje(d.dia) ? 'text-ink' : 'text-muted'}`}>
                  {rotuloDoDia(d.data)}{eHoje(d.dia) ? ' · hoje' : ''}
                </p>
                {d.posts.length === 0 ? (
                  <p className="text-[11px] text-muted opacity-60">—</p>
                ) : (
                  d.posts.map((p) => <Post key={p.id} p={p} canal={canais.porId[p.account?.channel_id]} />)
                )}
              </div>
            ))}
          </div>
          <p className="text-[12px] text-muted">
            {total === 0
              ? 'Nada nesta semana. A fila manual (sem hora) fica logo abaixo, na fila.'
              : `${total} post(s) nesta semana. Os apagados já foram ao ar.`}
          </p>
        </>
      )}
    </Secao>
  );
}
