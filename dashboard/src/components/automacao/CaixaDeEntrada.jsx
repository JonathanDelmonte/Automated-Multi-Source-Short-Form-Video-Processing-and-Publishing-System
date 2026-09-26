import React, { useMemo, useState } from 'react';
import { ExternalLink, Film, Loader2, RefreshCw, Scissors, Undo2, X } from 'lucide-react';
import { decidirCandidato } from '../../lib/automacao';
import {
  duracaoCurta, grupoDoCandidato, rotuloDaLicenca, rotuloDoCandidato,
} from '../../lib/receita.js';
import { hrefDe } from '../../lib/rota';

// A caixa de entrada de fontes (etapa 7.5): os vídeos que a receita achou,
// com a licença de cada um. A automação corta pela ordem (os escolhidos
// primeiro); aqui a pessoa escolhe o próximo, tira um da fila ou vê por que
// um ficou de fora.

const MONTES = [
  { id: 'fila', rotulo: 'na fila' },
  { id: 'cortados', rotulo: 'cortados' },
  { id: 'fora', rotulo: 'fora' },
];

// Os neutros no mesmo formato dos selos coloridos (a letra mono, em caixa
// alta), só que sem cor: lado a lado, "na fila" e "Creative Commons" são a
// mesma coisa, um selo.
const SELO_SEM_COR = 'font-mono text-[10.5px] uppercase tracking-[0.06em] rounded-full px-2.5 py-0.5 border border-rule inline-flex items-center';
const TONS = {
  ok: 'badge-ok',
  aviso: 'badge-warn',
  erro: 'badge-danger',
  destaque: 'badge-brass',
  neutro: `${SELO_SEM_COR} text-ink2`,
  apagado: `${SELO_SEM_COR} text-muted`,
};

function Selo({ tom, children, titulo }) {
  return <span className={`${TONS[tom] || TONS.neutro} whitespace-nowrap`} title={titulo}>{children}</span>;
}

// `self-start`: na linha flex, o padrão (stretch) esticava a miniatura até a
// altura do texto ao lado, e no celular ela virava uma faixa em pé.
function Miniatura({ src }) {
  const [quebrou, setQuebrou] = useState(false);
  if (!src || quebrou) {
    return (
      <span className="w-24 sm:w-28 aspect-video self-start rounded-input bg-paper3 flex items-center justify-center text-muted shrink-0">
        <Film size={16} />
      </span>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setQuebrou(true)}
      className="w-24 sm:w-28 aspect-video self-start rounded-input object-cover bg-paper3 shrink-0"
    />
  );
}

function Linha({ c, tipoDaFonte, aoMudar }) {
  const [ocupado, setOcupado] = useState(null);
  const [erro, setErro] = useState(null);
  const status = rotuloDoCandidato(c.status);
  const licenca = rotuloDaLicenca(c.license);

  const agir = async (acao) => {
    setOcupado(acao);
    setErro(null);
    const r = await decidirCandidato(c.id, acao);
    setOcupado(null);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    aoMudar?.();
  };

  const podeEscolher = ['novo', 'falhou'].includes(c.status)
    || (c.status === 'recusado' && (tipoDaFonte !== 'busca' || ['cc-by', 'dominio-publico'].includes(c.license)));
  const link = /^https?:\/\//.test(c.url) ? c.url : null;

  return (
    <li className="flex gap-3 p-2.5 rounded-input border border-rule min-w-0" data-candidato={c.key}>
      <Miniatura src={c.thumbnail} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-start gap-2 min-w-0">
          <p className="text-sm text-ink leading-snug line-clamp-2 flex-1 min-w-0">{c.title || c.url}</p>
          {link && (
            <a href={link} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-ink2 shrink-0 mt-0.5"
               title="abrir o vídeo original" aria-label={`abrir o original de ${c.title || 'vídeo'}`}>
              <ExternalLink size={13} />
            </a>
          )}
        </div>
        <p className="text-[11px] text-muted truncate">
          {[c.author, duracaoCurta(c.duration_s), c.views ? `${c.views.toLocaleString('pt-BR')} views` : null]
            .filter(Boolean).join(' · ')}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <Selo tom={status.tom}>{status.texto}</Selo>
          <Selo tom={licenca.tom} titulo={licenca.dica}>{licenca.texto}</Selo>
          {c.job_id && (
            <a href={hrefDe(`/projetos/${c.job_id}`)} className="text-[11px] text-muted underline underline-offset-2 hover:text-ink2">
              projeto
            </a>
          )}
        </div>
        {c.reason && grupoDoCandidato(c.status) === 'fora' && (
          <p className="text-[12px] text-muted leading-snug">{c.reason}</p>
        )}
        {erro && <p className="text-[12px] text-danger leading-snug">{erro}</p>}
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {podeEscolher && c.status !== 'escolhido' && (
            <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => agir('escolher')} disabled={Boolean(ocupado)}>
              {ocupado === 'escolher' ? <Loader2 size={13} className="animate-spin" /> : <Scissors size={13} />} cortar este primeiro
            </button>
          )}
          {['novo', 'escolhido', 'falhou'].includes(c.status) && (
            <button type="button" className="btn-quiet px-2.5 py-1 text-xs" onClick={() => agir('recusar')} disabled={Boolean(ocupado)}>
              {ocupado === 'recusar' ? <Loader2 size={13} className="animate-spin" /> : <X size={13} />} tirar da fila
            </button>
          )}
          {c.status === 'escolhido' && (
            <button type="button" className="btn-quiet px-2.5 py-1 text-xs" onClick={() => agir('voltar')} disabled={Boolean(ocupado)}>
              <Undo2 size={13} /> voltar à ordem
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

export default function CaixaDeEntrada({ candidatos, tipoDaFonte, aoMudar, aoBuscar, buscando }) {
  const [monte, setMonte] = useState('fila');
  const porMonte = useMemo(() => {
    const saida = { fila: [], cortados: [], fora: [] };
    for (const c of candidatos || []) saida[grupoDoCandidato(c.status)].push(c);
    // Na fila, os escolhidos primeiro: é a ordem em que a automação corta.
    saida.fila.sort((a, b) => (a.status === 'escolhido' ? 0 : 1) - (b.status === 'escolhido' ? 0 : 1));
    return saida;
  }, [candidatos]);

  if (candidatos === null) {
    return <Loader2 size={16} className="animate-spin text-muted" aria-label="carregando" />;
  }
  const lista = porMonte[monte];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <nav aria-label="caixa de entrada" className="flex flex-wrap gap-1.5">
          {MONTES.map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setMonte(m.id)}
              aria-pressed={monte === m.id}
              className={`px-3 py-1.5 rounded-full border text-xs transition-colors ${
                monte === m.id ? 'border-brass bg-paper3 text-ink' : 'border-rule text-muted hover:text-ink2 hover:border-rule2'}`}
            >
              {m.rotulo} <span className="tabular-nums text-muted">{porMonte[m.id].length}</span>
            </button>
          ))}
        </nav>
        {aoBuscar && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={aoBuscar} disabled={buscando}>
            {buscando ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            {tipoDaFonte === 'pasta' ? 'ler a pasta agora' : 'buscar agora'}
          </button>
        )}
      </div>
      {lista.length === 0 ? (
        <p className="text-muted text-sm">
          {monte === 'fila' && (tipoDaFonte === 'twitch'
            ? 'A live não passa pela fila: quando o canal está no ar, o bloco é cortado na hora.'
            : 'Nada na fila. A receita busca de novo sozinha, ou use o botão acima.')}
          {monte === 'cortados' && 'Nenhum vídeo cortado ainda.'}
          {monte === 'fora' && 'Nenhum vídeo ficou de fora.'}
        </p>
      ) : (
        <ul className="space-y-2">
          {lista.map((c) => <Linha key={c.id} c={c} tipoDaFonte={tipoDaFonte} aoMudar={aoMudar} />)}
        </ul>
      )}
    </div>
  );
}
