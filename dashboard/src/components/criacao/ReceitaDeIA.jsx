import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, Power, RefreshCw } from 'lucide-react';
import { lerReceita, rodarAgora, salvarReceita } from '../../lib/automacao';
import { MAX_IDEIAS, fraseDaProximaIdeia, ideiasDoTexto } from '../../lib/criacao.js';
import { quando } from '../../lib/publicacoes.js';
import { hrefDe } from '../../lib/rota';

// A receita de IA do canal (etapa 7.7), na aba Automação: o canal cria vídeos
// sozinho, no estilo dele. O estilo diz COMO o vídeo é (aba Criar); a receita
// diz o que contar -- uma lista de ideias, na ordem, e um tema para quando elas
// acabarem -- e quantos por dia. Quando postar e se espera aprovação são do
// canal, como na receita de cortes: o estoque da agenda manda nas duas.

const RECARGA_MS = 30_000;

function Editor({ canal, tela, aoSalvar }) {
  const receita = tela.receita;
  const [texto, setTexto] = useState((receita.spec?.ideias || []).join('\n'));
  const [tema, setTema] = useState(receita.spec?.tema || '');
  const [porDia, setPorDia] = useState(receita.spec?.ritmo?.videos_por_dia || 1);
  const [salvando, setSalvando] = useState(null);
  const [erro, setErro] = useState(null);
  const ideias = ideiasDoTexto(texto);

  const salvar = async (ativa) => {
    setSalvando(ativa === undefined ? 'salvar' : ativa ? 'ligar' : 'desligar');
    setErro(null);
    const r = await salvarReceita(canal.id, {
      spec: { ideias, tema, ritmo: { videos_por_dia: porDia } },
      ativa: ativa === undefined ? receita.ativa : ativa,
    }, 'ia');
    setSalvando(null);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    aoSalvar(r.data);
  };

  return (
    <div className="space-y-3">
      <label className="block" htmlFor="receita-ia-ideias">
        <span className="eyebrow">ideias, uma por linha ({ideias.length} de {MAX_IDEIAS})</span>
        <textarea id="receita-ia-ideias" className="input-field mt-1.5 min-h-[7rem]" value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder={'A Lulu aprende a dividir\nA Lulu tem medo do escuro\nA Lulu ganha um irmãozinho'} />
        <span className="block text-muted text-[12px] mt-1.5 leading-snug">
          Cada ideia vira um vídeo, na ordem. A que já virou vídeo não volta.
        </span>
      </label>
      <label className="block" htmlFor="receita-ia-tema">
        <span className="eyebrow">quando as ideias acabarem, inventar sobre (opcional)</span>
        <input id="receita-ia-tema" className="input-field mt-1.5" maxLength={120} value={tema}
               onChange={(e) => setTema(e.target.value)} placeholder="Ex.: amizade e bondade" />
        <span className="block text-muted text-[12px] mt-1.5 leading-snug">
          Sem tema, o roteiro inventa no estilo do canal. Nunca repete o tema de um vídeo que o canal já fez.
        </span>
      </label>
      <label className="block" htmlFor="receita-ia-por-dia">
        <span className="eyebrow">vídeos por dia, no máximo</span>
        <input id="receita-ia-por-dia" type="number" inputMode="numeric" min={1} max={10} className="input-field mt-1.5 w-24 block"
               value={porDia} onChange={(e) => setPorDia(e.target.value === '' ? '' : Number(e.target.value))} />
      </label>

      {tela.estilo_falta && (
        <p className="flex items-start gap-2 text-sm text-ink2">
          <AlertTriangle size={15} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0">
            A receita só liga com o estilo pronto: {tela.estilo_falta}.{' '}
            <a href={hrefDe(`/canais/${canal.id}/criar`)} className="text-ink underline underline-offset-2">Configurar o estilo</a>
          </span>
        </p>
      )}
      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0">{erro}</span>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {receita.ativa ? (
          <button type="button" className="btn-ghost px-3 py-2 text-sm" onClick={() => salvar(false)} disabled={salvando !== null}>
            {salvando === 'desligar' ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />} desligar
          </button>
        ) : (
          <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => salvar(true)}
                  disabled={salvando !== null || Boolean(tela.estilo_falta)}>
            {salvando === 'ligar' ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />} ligar a receita de IA
          </button>
        )}
        <button type="button" className="btn-quiet px-3 py-2 text-sm" onClick={() => salvar(undefined)} disabled={salvando !== null}>
          {salvando === 'salvar' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} salvar
        </button>
      </div>
    </div>
  );
}

export default function ReceitaDeIA({ canal }) {
  const [tela, setTela] = useState(null);
  const [erro, setErro] = useState(null);
  const [rodando, setRodando] = useState(false);
  const [resposta, setResposta] = useState(null);

  const carregar = useCallback(async () => {
    const r = await lerReceita(canal.id, 'ia');
    if (!r.ok) {
      setErro(r);
      return;
    }
    setErro(null);
    setTela(r.data);
  }, [canal.id]);

  useEffect(() => {
    carregar();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') carregar();
    }, RECARGA_MS);
    return () => clearInterval(id);
  }, [carregar]);

  if (erro) {
    return (
      <p className="flex items-start gap-2 text-sm text-ink2">
        <AlertTriangle size={15} className="shrink-0 mt-0.5 text-muted" />
        <span>{erro.motorAntigo ? 'O programa deste computador ainda não cria vídeos por IA. Atualize-o pelo aviso no topo.' : erro.erro}</span>
      </p>
    );
  }
  if (tela === null) return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;

  const receita = tela.receita;
  const estado = receita.estado || {};
  const rodar = async () => {
    setRodando(true);
    const r = await rodarAgora(canal.id, 'ia');
    setRodando(false);
    setResposta(r.ok ? r.data.situacao : r.erro);
    carregar();
  };

  return (
    <div className="space-y-4" data-receita-ia>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink text-sm font-medium flex items-center gap-2">
            {receita.ativa
              ? <><span className="w-2 h-2 rounded-full bg-[color:var(--color-ok)] shrink-0" aria-hidden="true" /> criando sozinho</>
              : <><Power size={14} className="text-muted shrink-0" /> desligada</>}
          </p>
          <p className="text-sm text-ink2 mt-1 leading-snug">
            {receita.ativa
              ? (resposta || estado.situacao || 'Esperando a primeira volta do motor.')
              : 'Ligue para o canal criar vídeos sozinho, no estilo dele.'}
          </p>
          {receita.ativa && estado.ultima_volta && (
            <p className="text-[11px] text-muted mt-1">
              última volta {quando(estado.ultima_volta)} · o motor olha de {tela.intervalo_min} em {tela.intervalo_min} min
            </p>
          )}
        </div>
        {receita.ativa && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={rodar} disabled={rodando}>
            {rodando ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} verificar agora
          </button>
        )}
      </div>
      <ul className="text-[13px] text-ink2 space-y-1">
        <li>{fraseDaProximaIdeia({ ideia: tela.proxima_ideia, daLista: tela.proxima_da_lista })}</li>
        {(estado.feitas || []).length > 0 && <li className="text-muted">{estado.feitas.length} ideia(s) da lista já viraram vídeo.</li>}
        {(estado.puladas || []).length > 0 && (
          <li className="text-muted">
            Puladas (não saíram): {estado.puladas.map((p) => `“${p}”`).join(', ')}. Salvar a receita de novo as devolve à fila.
          </li>
        )}
        {estado.ultimo_video?.job_id && (
          <li className="text-muted">
            Último vídeo:{' '}
            <a href={hrefDe(`/projetos/${estado.ultimo_video.job_id}`)} className="underline underline-offset-2 hover:text-ink2">
              {estado.ultimo_video.titulo || 'abrir'}
            </a>
          </li>
        )}
      </ul>
      <Editor key={receita.updated_at || 'nova'} canal={canal} tela={tela} aoSalvar={(dados) => { setTela(dados); carregar(); }} />
    </div>
  );
}
