import React, { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Cable, Cloud, Loader2, Monitor, Pencil, Smartphone, Trash2, Wifi } from 'lucide-react';
import Pagina, { CabecalhoDaPagina, Secao } from '../ui/Pagina';
import ContasDoAparelho from './ContasDoAparelho';
import EnsinoDoApp from './EnsinoDoApp';
import HistoricoDoAparelho from './HistoricoDoAparelho';
import RoteirosDoAparelho from './RoteirosDoAparelho';
import TelaAoVivo from './TelaAoVivo';
import { apagarAparelho, editarAparelho, lerAparelho, lerEnsino } from '../../lib/frotaNoMotor';
import { TIPOS, resumoDoEstado } from '../../lib/frota.js';
import { hrefDe, ir } from '../../lib/rota';

// Um aparelho da frota (`#/frota/<id>`, etapa 7.9): a tela ao vivo e o controle
// remoto, as contas que moram nele, o roteiro de cada app e o que ele fez.

const RECARGA_MS = 10_000;
const ICONES = { cabo: Cable, rede: Wifi, nuvem: Cloud };
const CLASSES = { ok: 'badge-ok', aviso: 'badge-warn', erro: 'badge-danger', info: 'badge-warn' };

export default function DetalheDoAparelho({ id, frota, aoMudar }) {
  const [aparelho, setAparelho] = useState(null);
  const [erro, setErro] = useState(null);
  const [ensino, setEnsino] = useState(null);
  const [nome, setNome] = useState(null);
  const [apagando, setApagando] = useState(false);

  const carregar = useCallback(async () => {
    const r = await lerAparelho(id);
    if (!r.ok) return setErro(r);
    setErro(null);
    setAparelho(r.data);
    return r.data;
  }, [id]);

  useEffect(() => {
    let vivo = true;
    carregar().then(async (a) => {
      // Um ensino em andamento (a página recarregada no meio) volta para a tela.
      if (vivo && a?.ensinando) {
        const e = await lerEnsino(id);
        if (vivo && e.ok) setEnsino({ plataforma: e.data.plataforma, estado: e.data });
      }
    });
    const intervalo = setInterval(() => {
      if (document.visibilityState === 'visible') carregar();
    }, RECARGA_MS);
    return () => { vivo = false; clearInterval(intervalo); };
  }, [carregar, id]);

  const mudou = () => {
    carregar();
    aoMudar?.();
  };

  const salvarNome = async () => {
    const r = await editarAparelho(id, { nome });
    if (r.ok) {
      setAparelho({ ...aparelho, ...r.data });
      setNome(null);
      aoMudar?.();
    }
  };

  const apagar = async () => {
    if (!window.confirm(`Tirar ${aparelho.nome} da frota? As contas dele voltam a postar pelo caminho de antes, e o histórico sai.`)) return;
    setApagando(true);
    const r = await apagarAparelho(id);
    setApagando(false);
    if (r.ok) {
      aoMudar?.();
      ir('/frota');
    }
  };

  const voltar = (
    <a href={hrefDe('/frota')} className="btn-ghost px-3 py-1.5 text-xs"><ArrowLeft size={13} /> frota</a>
  );

  if (erro) {
    return (
      <Pagina largura="larga">
        <CabecalhoDaPagina rotulo="frota" titulo="Aparelho" acoes={voltar} />
        <section className="card p-5 text-sm text-ink2">
          {erro.status === 404 && !erro.motorAntigo ? 'Este aparelho não está mais na frota.' : erro.erro}
        </section>
      </Pagina>
    );
  }
  if (!aparelho) {
    return (
      <Pagina largura="larga">
        <div className="grid place-items-center py-20 text-muted"><Loader2 size={18} className="animate-spin" /></div>
      </Pagina>
    );
  }

  const Icone = ICONES[aparelho.tipo] || Smartphone;
  const estado = aparelho.estado;
  const plataformas = frota?.plataformas || [];

  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="frota"
        titulo={aparelho.nome}
        acoes={voltar}
      >
        <div className="flex flex-wrap items-center gap-1.5 mt-2">
          <span className="readout inline-flex items-center gap-1"><Icone size={12} /> {TIPOS[aparelho.tipo]}</span>
          <span className="readout">{estado?.modelo || ''}{estado?.android ? ` · Android ${estado.android}` : ''}</span>
          {resumoDoEstado(estado).map((r) => <span key={r.texto} className={CLASSES[r.tipo]}>{r.texto}</span>)}
        </div>
      </CabecalhoDaPagina>

      {ensino ? (
        <EnsinoDoApp aparelhoId={id} plataforma={ensino.plataforma} estado={ensino.estado}
                     aoTerminar={() => { setEnsino(null); mudou(); }} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[18rem_1fr] items-start">
          <Secao titulo="ao vivo" icone={Monitor}>
            <TelaAoVivo aparelhoId={id} ocupado={aparelho.ocupado} />
          </Secao>
          <div className="space-y-6 min-w-0">
            <ContasDoAparelho aparelho={aparelho} plataformas={plataformas} limite={frota?.limite} aoMudar={mudou} />
            <RoteirosDoAparelho aparelho={aparelho} estado={estado} plataformas={plataformas}
                                aoEnsinar={(plataforma, estadoDoEnsino) => setEnsino({ plataforma, estado: estadoDoEnsino })}
                                aoMudar={mudou} />
          </div>
        </div>
      )}

      <HistoricoDoAparelho aparelhoId={id} execucoes={aparelho.execucoes} />

      <Secao titulo="este aparelho" icone={Smartphone}>
        <div className="flex flex-wrap items-end gap-2">
          <label className="space-y-1 min-w-0 flex-1">
            <span className="readout block">nome</span>
            <input className="input-field py-1.5 text-sm w-full" value={nome ?? aparelho.nome}
                   onChange={(e) => setNome(e.target.value)} aria-label="nome do aparelho" />
          </label>
          {nome !== null && nome !== aparelho.nome && (
            <button type="button" className="btn-primary px-3 py-1.5 text-xs" onClick={salvarNome}>
              <Pencil size={13} /> salvar o nome
            </button>
          )}
        </div>
        <p className="readout break-all">serial {aparelho.serial}{aparelho.endereco ? ` · ${aparelho.endereco}` : ''}</p>
        <button type="button" className="btn-danger px-3 py-1.5 text-xs" disabled={apagando} onClick={apagar}>
          <Trash2 size={13} /> tirar da frota
        </button>
      </Secao>
    </Pagina>
  );
}
