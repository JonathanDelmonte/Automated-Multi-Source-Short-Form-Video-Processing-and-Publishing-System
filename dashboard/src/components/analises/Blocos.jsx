import React from 'react';
import { ExternalLink } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import {
  COR_DA_PLATAFORMA, NOMES_DAS_FAIXAS, coeficiente, fraseDoHorario, frasesDaCalibracao, numeroCurto,
  numeroInteiro, porcentagem, segundos,
} from '../../lib/analises';
import { PLATAFORMAS } from '../../lib/plataformas';
import { hrefDe } from '../../lib/rota';

// Os blocos da tela de análises (etapa 7.4). Os números vêm somados do motor
// (`analises.py`); aqui só se desenha. Um número que ninguém mediu aparece
// como traço, e nunca como zero.

// Um número da fileira de cima. A letra é a do corpo (Geist), e não a da
// marca: "12,9 mil" em Anton, condensada e em caixa alta, se lê pior.
export function Numero({ rotulo, valor, detalhe, titulo }) {
  return (
    <div className="card px-4 py-3 min-w-0" title={titulo}>
      <p className="text-[26px] leading-none font-semibold text-ink truncate">{valor}</p>
      <p className="readout mt-1.5 truncate">{rotulo}</p>
      {detalhe && <p className="text-[11px] text-muted mt-1 truncate">{detalhe}</p>}
    </div>
  );
}

export function FileiraDeNumeros({ totais, ganho, plataforma }) {
  if (!totais) return null;
  const mais = (v) => (v === null || v === undefined ? null : `+${numeroCurto(v)} em 24 h`);
  const semRetencao = plataforma === 'tiktok';
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 2xl:grid-cols-6 gap-2.5">
      <Numero rotulo="visualizações" valor={numeroCurto(totais.views)} detalhe={mais(ganho?.views)}
              titulo={totais.views === null ? 'Nenhum corte medido ainda.' : `${numeroInteiro(totais.views)} visualizações`} />
      <Numero rotulo="curtidas" valor={numeroCurto(totais.likes)} detalhe={mais(ganho?.likes)} />
      <Numero rotulo="comentários" valor={numeroCurto(totais.comments)} detalhe={mais(ganho?.comments)} />
      <Numero rotulo="compartilhamentos" valor={numeroCurto(totais.shares)} detalhe={mais(ganho?.shares)} />
      {plataforma === 'instagram' || (totais.saves !== null && totais.saves !== undefined) ? (
        <Numero rotulo="salvamentos" valor={numeroCurto(totais.saves)} detalhe={mais(ganho?.saves)} />
      ) : (
        <Numero rotulo="tempo médio" valor={segundos(totais.tempo_medio_s)} detalhe="assistido em média" />
      )}
      <Numero
        rotulo="retenção média"
        valor={semRetencao ? '—' : porcentagem(totais.retencao_media)}
        detalhe={semRetencao ? 'o TikTok não dá' : `${totais.com_retencao || 0} de ${totais.publicados} cortes`}
        titulo="Quanto do corte a pessoa assiste, em média. No Instagram é o tempo médio dividido pela duração do corte."
      />
    </div>
  );
}

// Por plataforma, na aba Geral: uma tabela curta (três linhas no máximo).
export function PorPlataforma({ linhas }) {
  if (!linhas || linhas.length < 2) return null;
  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-muted text-xs text-left">
            <th className="font-normal py-1.5 pr-3">plataforma</th>
            <th className="font-normal py-1.5 pr-3 text-right hidden sm:table-cell">cortes</th>
            <th className="font-normal py-1.5 pr-3 text-right">views</th>
            <th className="font-normal py-1.5 pr-3 text-right hidden sm:table-cell">curtidas</th>
            <th className="font-normal py-1.5 text-right">retenção</th>
          </tr>
        </thead>
        <tbody className="tabular-nums">
          {linhas.map((l) => (
            <tr key={l.plataforma} className="border-t border-rule text-ink2">
              <td className="py-2 pr-3">
                <span className="inline-flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: COR_DA_PLATAFORMA[l.plataforma] || '#8c8c8c' }} aria-hidden="true" />
                  <IconePlataforma platform={l.plataforma} size={14} />
                  {PLATAFORMAS[l.plataforma]?.nome || l.plataforma}
                </span>
              </td>
              <td className="py-2 pr-3 text-right hidden sm:table-cell">{l.publicados}</td>
              <td className="py-2 pr-3 text-right text-ink">{numeroInteiro(l.views)}</td>
              <td className="py-2 pr-3 text-right hidden sm:table-cell">{numeroInteiro(l.likes)}</td>
              <td className="py-2 text-right">{l.plataforma === 'tiktok' ? '—' : porcentagem(l.retencao_media)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Os cortes que mais renderam.
export function Melhores({ itens }) {
  if (!itens || itens.length === 0) {
    return <p className="text-muted text-sm">Nenhum corte medido ainda.</p>;
  }
  return (
    <ol className="space-y-1.5">
      {itens.map((m, i) => (
        <li key={m.publication_id} className="flex items-center gap-3 p-2.5 rounded-input border border-rule min-w-0">
          <span className="text-muted text-xs w-4 text-right tabular-nums shrink-0">{i + 1}</span>
          <IconePlataforma platform={m.plataforma} size={16} />
          <span className="min-w-0 flex-1">
            {m.job_id ? (
              <a href={hrefDe(`/projetos/${m.job_id}`)} className="block text-sm text-ink truncate hover:underline underline-offset-2">
                {m.titulo || `Corte ${(m.clip_index ?? 0) + 1}`}
              </a>
            ) : (
              <span className="block text-sm text-ink truncate">{m.titulo || 'Corte'}</span>
            )}
            <span className="block text-[11px] text-muted truncate">
              {m.handle}
              {m.likes !== null && m.likes !== undefined && ` · ${numeroCurto(m.likes)} curtidas`}
              {m.retention_pct !== null && m.retention_pct !== undefined && ` · retenção ${porcentagem(m.retention_pct)}`}
            </span>
          </span>
          <span className="text-right shrink-0">
            <span className="block text-sm font-semibold text-ink">{numeroCurto(m.views)}</span>
            <span className="block text-[11px] text-muted">visualizações</span>
          </span>
          {m.url && (
            <a href={m.url} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-ink2 shrink-0"
               title="abrir o post" aria-label={`abrir o post de ${m.titulo || 'corte'}`}>
              <ExternalLink size={14} />
            </a>
          )}
        </li>
      ))}
    </ol>
  );
}

// O horário: as visualizações do PRIMEIRO dia de cada post, por faixa do dia
// (hora de quem olha). Faixa sem amostra fica cinza e fora da conclusão.
export function Horarios({ porHorario }) {
  if (!porHorario) return null;
  const faixas = porHorario.faixas || [];
  const maximo = Math.max(1, ...faixas.map((f) => f.views_do_primeiro_dia_mediana || 0));
  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {faixas.map((f) => {
          const valor = f.views_do_primeiro_dia_mediana;
          const largura = valor ? Math.max(2, (valor / maximo) * 100) : 0;
          const melhor = porHorario.melhor === f.faixa;
          return (
            <li key={f.faixa} className="grid grid-cols-[7.5rem_1fr_auto] sm:grid-cols-[9rem_1fr_auto] items-center gap-3 text-xs">
              <span className={melhor ? 'text-ink' : 'text-ink2'}>{NOMES_DAS_FAIXAS[f.faixa] || f.faixa}</span>
              <span className="h-2.5 rounded-r-[4px] bg-[rgba(245,245,245,0.06)] overflow-hidden" aria-hidden="true">
                {largura > 0 && (
                  <span className="block h-full rounded-r-[4px]"
                        style={{ width: `${largura}%`, background: f.amostra_suficiente ? '#3987e5' : '#5c5c5c' }} />
                )}
              </span>
              <span className="text-right tabular-nums text-muted whitespace-nowrap">
                <span className="text-ink2">{valor === null || valor === undefined ? '—' : numeroCurto(valor)}</span>
                {' · '}{f.posts} post{f.posts === 1 ? '' : 's'}
                {!f.amostra_suficiente && f.posts > 0 && ' · amostra pequena'}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-muted text-[13px] leading-snug">{fraseDoHorario(porHorario)}</p>
    </div>
  );
}

// A calibração: o que a IA previu contra o que rendeu. Abaixo do mínimo, o
// relatório não publica coeficiente -- e a tela também não inventa um.
export function Calibracao({ relatorio }) {
  if (!relatorio) return null;
  const minimo = relatorio.minimo_para_correlacao || 10;
  const linhas = relatorio.por_plataforma || [];
  return (
    <div className="space-y-3">
      <p className="text-sm text-ink2">
        <span className="text-ink font-semibold">{relatorio.clipes_medidos}</span> de {relatorio.clipes_publicados} cortes
        publicados já têm números. O coeficiente sai com {minimo} ou mais.
      </p>
      {linhas.length > 0 && (
        <ul className="space-y-1.5">
          {linhas.map((l) => (
            <li key={l.plataforma} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink2">
              <span className="inline-flex items-center gap-1.5 w-24">
                <IconePlataforma platform={l.plataforma} size={14} /> {PLATAFORMAS[l.plataforma]?.nome || l.plataforma}
              </span>
              <span>
                IA × visualizações:{' '}
                {l.rho_score_views === null
                  ? <span className="text-muted">faltam {Math.max(0, minimo - l.com_views)}</span>
                  : <span className="text-ink font-medium">{coeficiente(l.rho_score_views)}</span>}
              </span>
              {l.plataforma !== 'tiktok' && (
                <span>
                  IA × retenção:{' '}
                  {l.rho_score_retencao === null
                    ? <span className="text-muted">faltam {Math.max(0, minimo - l.com_retencao)}</span>
                    : <span className="text-ink font-medium">{coeficiente(l.rho_score_retencao)}</span>}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      <ul className="space-y-1 text-[13px] text-muted leading-snug">
        {frasesDaCalibracao(relatorio).map((f) => <li key={f}>{f}</li>)}
      </ul>
    </div>
  );
}
