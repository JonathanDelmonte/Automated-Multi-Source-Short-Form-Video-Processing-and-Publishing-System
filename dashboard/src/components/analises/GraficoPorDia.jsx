import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Table2 } from 'lucide-react';
import {
  COR_DA_PLATAFORMA, caminhoDaColuna, colunas, diaCurto, escala, numeroCurto, numeroInteiro,
  plataformasDaSerie, rotuloDoEixo,
} from '../../lib/analises';
import { PLATAFORMAS } from '../../lib/plataformas';

// Visualizações ganhas por dia (etapa 7.4): colunas empilhadas por plataforma.
// Feito à mão, em SVG, sem biblioteca -- dependência nova no painel muda o
// `package.json`, e o botão de atualizar do Docker recusa essa mudança.
//
// As regras de desenho (ver o skill de gráficos): colunas finas (até 24 px),
// topo arredondado e base reta, 2 px de fundo entre os pedaços (e não borda),
// grade de linha fina, legenda sempre que há mais de uma plataforma, e o
// número escrito só no dia maior -- os outros estão na dica e na tabela.
// Dia sem base fica sem coluna: um buraco honesto, e não um zero.

const ALTURA = 170;
const EIXO_Y = 44;
const EIXO_X = 24;
const TOPO = 18;

function useLargura(ref) {
  const [largura, setLargura] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const medir = () => setLargura(Math.max(260, Math.round(el.getBoundingClientRect().width)));
    medir();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const obs = new ResizeObserver(medir);
    obs.observe(el);
    return () => obs.disconnect();
  }, [ref]);
  return largura;
}

function nomeDa(p) {
  return PLATAFORMAS[p]?.nome || p;
}

export default function GraficoPorDia({ serie, titulo = 'visualizações ganhas por dia', plataformas: fixas }) {
  const caixa = useRef(null);
  const largura = useLargura(caixa);
  const [ativo, setAtivo] = useState(null);
  const [tabela, setTabela] = useState(false);

  const plataformas = fixas || plataformasDaSerie(serie);
  const totais = (serie || []).map((d) => d.views).filter((v) => v !== null && v !== undefined);
  const { teto, marcas } = escala(totais.length ? Math.max(...totais) : 0);
  const larguraDoPlot = largura - EIXO_Y;
  const n = (serie || []).length || 1;
  const faixa = larguraDoPlot / n;
  const larguraDaColuna = Math.max(3, Math.min(24, faixa * 0.62));
  const geometria = useMemo(() => colunas(serie, { altura: ALTURA, teto, plataformas }),
    [serie, teto, plataformas]);
  const maior = geometria.reduce((m, c) => (c.total !== null && (m === null || c.total > m.total) ? c : m), null);
  const semNada = totais.length === 0;
  // Uma data a cada ~7 dias no eixo, e sempre a última.
  const passoDoEixo = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(larguraDoPlot / 64))));

  const indiceDoPonteiro = (e) => {
    const r = caixa.current?.getBoundingClientRect();
    if (!r) return null;
    const x = e.clientX - r.left - EIXO_Y;
    if (x < 0) return null;
    return Math.max(0, Math.min(n - 1, Math.floor(x / faixa)));
  };

  const teclas = (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    setAtivo((atual) => {
      const agora = atual === null ? n - 1 : atual;
      if (e.key === 'Home') return 0;
      if (e.key === 'End') return n - 1;
      return Math.max(0, Math.min(n - 1, agora + (e.key === 'ArrowLeft' ? -1 : 1)));
    });
  };

  const diaAtivo = ativo !== null && serie ? serie[ativo] : null;
  const xDoAtivo = ativo !== null ? EIXO_Y + ativo * faixa + faixa / 2 : 0;

  return (
    <figure className="space-y-2.5">
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-ink text-sm font-medium">{titulo}</span>
        <span className="flex flex-wrap items-center gap-3">
          {plataformas.length > 1 && (
            <span className="flex flex-wrap items-center gap-3" aria-label="legenda">
              {plataformas.map((p) => (
                <span key={p} className="inline-flex items-center gap-1.5 text-xs text-ink2">
                  <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: COR_DA_PLATAFORMA[p] || '#8c8c8c' }} aria-hidden="true" />
                  {nomeDa(p)}
                </span>
              ))}
            </span>
          )}
          <button type="button" onClick={() => setTabela((v) => !v)} aria-pressed={tabela}
                  className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink2">
            <Table2 size={13} /> {tabela ? 'ver o gráfico' : 'ver como tabela'}
          </button>
        </span>
      </figcaption>

      {tabela ? (
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full text-xs tabular-nums">
            <thead>
              <tr className="text-muted text-left">
                <th className="font-normal py-1 pr-3">dia</th>
                {plataformas.map((p) => <th key={p} className="font-normal py-1 pr-3 text-right">{nomeDa(p)}</th>)}
                <th className="font-normal py-1 text-right">total</th>
              </tr>
            </thead>
            <tbody>
              {[...(serie || [])].reverse().map((d) => (
                <tr key={d.dia} className="border-t border-rule text-ink2">
                  <td className="py-1 pr-3">{diaCurto(d.dia)}</td>
                  {plataformas.map((p) => (
                    <td key={p} className="py-1 pr-3 text-right">
                      {d.views === null ? '—' : numeroInteiro((d.por_plataforma || {})[p] || 0)}
                    </td>
                  ))}
                  <td className="py-1 text-right text-ink">{d.views === null ? 'sem base' : numeroInteiro(d.views)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div
          ref={caixa}
          className="relative outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--color-focus)] rounded"
          tabIndex={0}
          role="group"
          aria-label={`${titulo}: gráfico de colunas. Use as setas para ler cada dia, ou "ver como tabela".`}
          onKeyDown={teclas}
          onFocus={() => setAtivo((a) => (a === null ? n - 1 : a))}
          onBlur={() => setAtivo(null)}
          onPointerMove={(e) => setAtivo(indiceDoPonteiro(e))}
          onPointerLeave={() => setAtivo(null)}
        >
          <svg width={largura} height={ALTURA + EIXO_X + TOPO} aria-hidden="true" className="block">
            <g transform={`translate(0 ${TOPO})`}>
              {marcas.map((m) => {
                const y = ALTURA - (m / teto) * ALTURA;
                return (
                  <g key={m}>
                    <line x1={EIXO_Y} x2={largura} y1={y + 0.5} y2={y + 0.5}
                          stroke={m === 0 ? 'rgba(245,245,245,0.18)' : 'rgba(245,245,245,0.08)'} strokeWidth="1" />
                    <text x={EIXO_Y - 8} y={y + 4} textAnchor="end" fontSize="11" fill="#8c8c8c"
                          style={{ fontVariantNumeric: 'tabular-nums' }}>{rotuloDoEixo(m, teto)}</text>
                  </g>
                );
              })}
              {ativo !== null && (
                <rect x={EIXO_Y + ativo * faixa} y={0} width={faixa} height={ALTURA} fill="rgba(245,245,245,0.05)" />
              )}
              {geometria.map((c) => {
                const x = EIXO_Y + c.i * faixa + (faixa - larguraDaColuna) / 2;
                return (
                  <g key={c.dia} opacity={ativo === null || ativo === c.i ? 1 : 0.55}>
                    {c.pedacos.map((pd) => (pd.topo ? (
                      <path key={pd.plataforma} d={caminhoDaColuna(x, pd.y, larguraDaColuna, pd.altura)}
                            fill={COR_DA_PLATAFORMA[pd.plataforma] || '#8c8c8c'} />
                    ) : (
                      <rect key={pd.plataforma} x={x} y={pd.y} width={larguraDaColuna} height={pd.altura}
                            fill={COR_DA_PLATAFORMA[pd.plataforma] || '#8c8c8c'} />
                    )))}
                  </g>
                );
              })}
              {maior && maior.total > 0 && ativo === null && (
                <text x={EIXO_Y + maior.i * faixa + faixa / 2}
                      y={ALTURA - (maior.total / teto) * ALTURA - 6}
                      textAnchor="middle" fontSize="11" fill="#d1d1d1">
                  {numeroCurto(maior.total)}
                </text>
              )}
              {(serie || []).map((d, i) => {
                if (!((i % passoDoEixo === 0 && n - 1 - i >= passoDoEixo / 2) || i === n - 1)) return null;
                // A última data encosta na borda: ancorada pelo fim, ela não
                // sai do gráfico (no celular, "26/9" virava "26/").
                const centro = EIXO_Y + i * faixa + faixa / 2;
                const noFim = i === n - 1 && centro + 16 > largura;
                return (
                  <text key={d.dia} x={noFim ? largura - 1 : centro} y={ALTURA + 16}
                        textAnchor={noFim ? 'end' : 'middle'} fontSize="11" fill="#8c8c8c">{diaCurto(d.dia)}</text>
                );
              })}
            </g>
          </svg>
          {semNada && (
            <p className="absolute inset-x-0 top-1/3 text-center text-xs text-muted px-6">
              Nenhum dia com leitura ainda. A primeira coleta com a conta conectada começa a desenhar este gráfico.
            </p>
          )}
          {diaAtivo && (
            <div
              className="pointer-events-none absolute z-10 min-w-[9rem] rounded-input border border-rule2 bg-paper3 px-3 py-2 text-xs shadow-lg"
              style={{ left: Math.min(Math.max(8, xDoAtivo - 72), largura - 160), top: 0 }}
              role="status"
            >
              <p className="text-muted mb-1">{diaCurto(diaAtivo.dia)}</p>
              {diaAtivo.views === null ? (
                <p className="text-ink2 leading-snug">Sem base neste dia: o primeiro número dos cortes antigos veio depois.</p>
              ) : (
                <>
                  <p className="text-ink font-semibold text-sm">{numeroInteiro(diaAtivo.views)} <span className="font-normal text-muted text-xs">visualizações</span></p>
                  {plataformas.length > 1 && plataformas.map((p) => (
                    <p key={p} className="flex items-center gap-1.5 text-ink2 mt-0.5">
                      <span className="w-3 h-0.5 rounded-full" style={{ background: COR_DA_PLATAFORMA[p] || '#8c8c8c' }} aria-hidden="true" />
                      <span className="text-ink font-medium">{numeroInteiro((diaAtivo.por_plataforma || {})[p] || 0)}</span>
                      <span className="text-muted">{nomeDa(p)}</span>
                    </p>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </figure>
  );
}
