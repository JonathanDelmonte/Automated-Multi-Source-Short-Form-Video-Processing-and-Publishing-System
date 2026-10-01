import React, { useState } from 'react';
import { History, Images, Loader2 } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import { Secao } from '../ui/Pagina';
import { lerFotos } from '../../lib/frotaNoMotor';
import { TIPOS_DE_EXECUCAO, situacaoDaExecucao } from '../../lib/frota.js';
import { quando } from '../../lib/publicacoes.js';

// O que o aparelho fez (etapa 7.9): cada entrega, ensaio e post automático,
// com a tela de cada passo. É a resposta para "por que este post não saiu?".

const CLASSES = { ok: 'badge-ok', aviso: 'badge-warn', erro: 'badge-danger', info: 'badge-warn' };

function Execucao({ aparelhoId, e }) {
  const [fotos, setFotos] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const situacao = situacaoDaExecucao(e.situacao);

  const ver = async () => {
    if (fotos) return setFotos(null);
    setCarregando(true);
    const r = await lerFotos(aparelhoId, e.id);
    setCarregando(false);
    return setFotos(r.ok ? r.data.fotos : []);
  };

  return (
    <li className="py-2.5 space-y-1.5" data-execucao={e.id}>
      <div className="flex flex-wrap items-center gap-2">
        {e.plataforma && <IconePlataforma platform={e.plataforma} size={14} />}
        <span className="text-sm text-ink">{TIPOS_DE_EXECUCAO[e.tipo] || e.tipo}</span>
        {e.conta && <span className="readout">{e.conta}</span>}
        <span className={CLASSES[situacao.tipo]}>{situacao.texto}</span>
        <span className="text-[11px] text-muted ml-auto">{quando(e.fim || e.inicio)}</span>
      </div>
      {e.detalhe && <p className="text-[12px] text-ink2 leading-snug break-words">{e.detalhe}</p>}
      {e.fotos?.length > 0 && (
        <button type="button" className="btn-quiet px-2 py-1 text-[11px]" onClick={ver}>
          {carregando ? <Loader2 size={12} className="animate-spin" /> : <Images size={12} />}
          {fotos ? 'esconder as telas' : `ver as telas (${e.fotos.length})`}
        </button>
      )}
      {fotos && (
        <div className="flex gap-2 overflow-x-auto pb-1 custom-scrollbar">
          {fotos.map((f) => (
            <figure key={f.nome} className="shrink-0 w-24 space-y-1">
              <img src={f.imagem} alt={f.nome} className="w-24 rounded-[8px] border border-rule" />
              <figcaption className="text-[10px] text-muted truncate">{f.nome.replace(/^\d+-/, '').replace(/\.\w+$/, '')}</figcaption>
            </figure>
          ))}
          {!fotos.length && <p className="text-[12px] text-muted">As telas desta vez não foram guardadas.</p>}
        </div>
      )}
    </li>
  );
}

export default function HistoricoDoAparelho({ aparelhoId, execucoes }) {
  return (
    <Secao titulo="o que ele fez" icone={History}>
      {execucoes?.length ? (
        <ul className="divide-y divide-[color:var(--color-rule)]">
          {execucoes.map((e) => <Execucao key={e.id} aparelhoId={aparelhoId} e={e} />)}
        </ul>
      ) : <p className="text-sm text-muted">Nada ainda: entregas, ensaios e posts aparecem aqui, com a tela de cada passo.</p>}
    </Secao>
  );
}
