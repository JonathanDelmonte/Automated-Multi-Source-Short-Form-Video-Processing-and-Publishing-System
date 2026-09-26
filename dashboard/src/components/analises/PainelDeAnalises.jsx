import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import GraficoPorDia from './GraficoPorDia';
import { Calibracao, FileiraDeNumeros, Horarios, Melhores, PorPlataforma } from './Blocos';
import { Secao } from '../ui/Pagina';
import IconePlataforma from '../ui/IconePlataforma';
import { apiFetch } from '../../lib/api';
import {
  caminhoDaCalibracao, caminhoDasAnalises, contasSemMedir, fusoDoNavegador, rotuloDoRecorte,
} from '../../lib/analises';
import { PLATAFORMAS } from '../../lib/plataformas';
import { hrefDe } from '../../lib/rota';

// A tela de análises de um recorte (etapa 7.4): um canal (ou todos), no geral
// ou de uma plataforma. Tudo o que ela mostra vem de `GET /api/analises`, que
// soma pelo motor; a calibração vem de `GET /api/calibracao`, no mesmo recorte.
//
// Recarregar mantém o desenho anterior esmaecido (sem "esqueleto" piscando), e
// o "medir agora" pede uma coleta ao motor -- descobrir se a conexão de medir
// funciona não pode custar as 6 horas do laço.

export default function PainelDeAnalises({ canal = null, plataforma = null, ondeConectar }) {
  const [dados, setDados] = useState(null);
  const [calibracao, setCalibracao] = useState(null);
  const [situacao, setSituacao] = useState('carregando');
  const [medindo, setMedindo] = useState(false);
  const [resultadoDaColeta, setResultadoDaColeta] = useState(null);
  const vivo = useRef(true);

  const carregar = useCallback(async () => {
    setSituacao((s) => (s === 'ok' ? 'recarregando' : 'carregando'));
    try {
      const fuso = fusoDoNavegador();
      const [ra, rc] = await Promise.all([
        apiFetch(caminhoDasAnalises({ canal, plataforma, fuso })),
        apiFetch(caminhoDaCalibracao({ canal, plataforma })),
      ]);
      if (!vivo.current) return;
      if (ra.status === 404) {
        setSituacao('motor-antigo');
        return;
      }
      if (!ra.ok) {
        setSituacao('erro');
        return;
      }
      setDados(await ra.json());
      setCalibracao(rc.ok ? await rc.json() : null);
      setSituacao('ok');
    } catch {
      if (vivo.current) setSituacao('erro');
    }
  }, [canal, plataforma]);

  useEffect(() => {
    vivo.current = true;
    carregar();
    return () => { vivo.current = false; };
  }, [carregar]);

  const medirAgora = async () => {
    setMedindo(true);
    setResultadoDaColeta(null);
    try {
      const r = await apiFetch('/api/metricas/coletar', { method: 'POST' });
      const corpo = r.ok ? await r.json() : null;
      setResultadoDaColeta(corpo);
      await carregar();
    } catch {
      setResultadoDaColeta({ falhou: true });
    } finally {
      setMedindo(false);
    }
  };

  if (situacao === 'motor-antigo') {
    return (
      <div className="card p-5 space-y-2">
        <p className="text-ink text-sm">As análises precisam do programa deste computador atualizado.</p>
        <p className="text-muted text-[13px]">O aviso no topo do site tem o botão de atualizar.</p>
      </div>
    );
  }
  if (situacao === 'erro' && !dados) {
    return (
      <div className="card p-5 flex items-center gap-2 text-sm text-danger">
        <AlertTriangle size={15} /> Não deu para ler as análises agora.
        <button type="button" className="btn-quiet px-3 py-1 text-xs ml-auto" onClick={carregar}>tentar de novo</button>
      </div>
    );
  }
  if (!dados) {
    return (
      <div className="card p-6 flex items-center justify-center gap-2 text-sm text-muted">
        <Loader2 size={15} className="animate-spin" /> lendo os números…
      </div>
    );
  }

  const faltam = contasSemMedir(dados.contas);
  const totais = dados.totais || {};
  const nada = !totais.publicados;
  const recorte = rotuloDoRecorte(plataforma, PLATAFORMAS);

  return (
    <div className={`space-y-4 transition-opacity ${situacao === 'recarregando' ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted text-[13px]">
          {nada
            ? `Nada publicado ainda em ${recorte}.`
            : `${totais.publicados} corte${totais.publicados === 1 ? '' : 's'} publicado${totais.publicados === 1 ? '' : 's'} em ${recorte}, ${totais.medidos} com números.`}
        </p>
        <button type="button" onClick={medirAgora} disabled={medindo} className="btn-ghost px-3 py-1.5 text-xs">
          {medindo ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} medir agora
        </button>
      </div>
      {resultadoDaColeta && (
        <p className="text-[12px] text-muted" role="status">
          {resultadoDaColeta.falhou
            ? 'Não consegui pedir a coleta ao programa.'
            : `Coleta feita: ${resultadoDaColeta.medidas || 0} corte(s) medido(s)`
              + `${resultadoDaColeta.erros ? `, ${resultadoDaColeta.erros} com erro (o motivo está no log do programa)` : ''}.`}
        </p>
      )}

      {faltam.length > 0 && (
        <div className="card p-3.5 space-y-1.5 border-[color:color-mix(in_oklab,var(--color-warn)_30%,transparent)]">
          <p className="text-sm text-ink2 flex items-center gap-1.5">
            <AlertTriangle size={14} className="text-warn shrink-0" />
            {faltam.length === 1 ? 'Uma conta ainda não é medida:' : `${faltam.length} contas ainda não são medidas:`}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {faltam.map((c) => (
              <li key={c.id} className="inline-flex items-center gap-1.5 pl-1.5 pr-2.5 py-0.5 rounded-full bg-paper3 text-xs text-ink2">
                <IconePlataforma platform={c.platform} size={13} /> {c.handle}
                {c.medir_vencido && <span className="text-warn">· token vencido</span>}
              </li>
            ))}
          </ul>
          <p className="text-[12px] text-muted leading-snug">
            {faltam.some((c) => c.platform === 'instagram')
              ? 'No YouTube e no TikTok, é o botão "conectar para medir" da conta; no Instagram, colar o token de medir. '
              : 'É o botão "conectar para medir" da conta. '}
            <a href={hrefDe(ondeConectar || '/configuracoes/contas')} className="text-ink2 underline underline-offset-2">
              ir às contas
            </a>
          </p>
        </div>
      )}

      <FileiraDeNumeros totais={totais} ganho={dados.ganho_24h} plataforma={plataforma} />

      <Secao>
        <GraficoPorDia serie={dados.serie} plataformas={plataforma ? [plataforma] : undefined}
                       titulo={`visualizações ganhas por dia — últimos ${dados.filtro?.dias || 28} dias`} />
        <p className="text-[12px] text-muted leading-snug">
          Cada dia soma o que os cortes ganharam naquele dia. Um corte antigo medido pela primeira vez não conta as
          visualizações da vida inteira num dia só: ele entra a partir do dia seguinte.
        </p>
      </Secao>

      {!plataforma && dados.por_plataforma?.length > 1 && (
        <Secao titulo="por plataforma">
          <PorPlataforma linhas={dados.por_plataforma} />
        </Secao>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Secao titulo="os que mais renderam">
          <Melhores itens={dados.melhores} />
        </Secao>
        <Secao titulo="o horário de postar">
          <Horarios porHorario={dados.por_horario} />
        </Secao>
      </div>

      {calibracao && (
        <Secao titulo="a IA acertou?">
          <Calibracao relatorio={calibracao} />
        </Secao>
      )}
    </div>
  );
}
