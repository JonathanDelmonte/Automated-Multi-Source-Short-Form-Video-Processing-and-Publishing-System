import React, { useState, useEffect, useCallback } from 'react';
import { Download, Trash2, Loader2, Plus, CheckCircle2, Youtube,
         Instagram, AlertTriangle, Send, Clock } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { getApiUrl } from '../config';
import { CartaoDeTempo } from './OndeVaiOTempo';

// A tela de publicação (Fase 3, bloco 3.5).
//
// **A adição é deliberadamente pequena**, pelo mesmo motivo do bloco 2.3b: o
// frontend inteiro vai ser trocado, e investir num componente marcado para sair
// é trabalho jogado fora. O que é durável aqui é o contrato do backend que
// estes controles exercitam — o pacote do dia, as contas e a fila.
//
// A ordem da tela é a ordem de importância do §6, não a de implementação: o
// **pacote do dia** primeiro, porque o driver `manual` é o default e o que
// entrega valor hoje; as contas depois, porque é lá que se liga o automático.

const PLATAFORMAS = {
  youtube: { nome: 'YouTube', Icone: Youtube },
  instagram: { nome: 'Instagram', Icone: Instagram },
  tiktok: { nome: 'TikTok', Icone: Send },
};

// O que cada driver significa em uma linha. É o que responde "por que este
// corte não subiu sozinho?" sem obrigar ninguém a ler o plano.
const DRIVERS = {
  'youtube-api': 'sobe sozinho pela API oficial',
  aggregator: 'agregador (não configurado)',
  manual: 'fila manual — o corte e a legenda ficam prontos',
  browser: 'navegador (desligado por decisão)',
};

const ESTADO = {
  // `scheduled` cobre duas esperas: a fila manual (sem data, esperando uma
  // pessoa) e a agendada (com data, esperando a hora). A data distingue as
  // duas na linha, e é por isso que ela aparece ao lado do estado.
  scheduled: { texto: 'na fila', cor: 'text-brass' },
  publishing: { texto: 'subindo', cor: 'text-brass' },
  published: { texto: 'publicado', cor: 'text-ok' },
  failed: { texto: 'falhou', cor: 'text-danger' },
  cancelled: { texto: 'cancelado', cor: 'text-muted' },
};

export default function PublicacoesTab() {
  const [dias, setDias] = useState([]);
  const [contas, setContas] = useState(null);
  const [quota, setQuota] = useState(null);
  const [fila, setFila] = useState([]);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [nova, setNova] = useState({ platform: 'youtube', handle: '' });
  const [projetos, setProjetos] = useState([]);
  const [envio, setEnvio] = useState({ job_id: '', account_id: '' });
  const [ultimoEnvio, setUltimoEnvio] = useState(null);
  const [confirmando, setConfirmando] = useState(null);
  const [agenda, setAgenda] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const [rDias, rContas, rFila, rJobs] = await Promise.all([
        apiFetch('/api/publicacoes/dias'),
        apiFetch('/api/contas'),
        apiFetch('/api/publicacoes'),
        apiFetch('/api/jobs'),
      ]);
      try {
        const rAgenda = await apiFetch('/api/agenda');
        setAgenda(rAgenda.ok ? await rAgenda.json() : null);
      } catch { setAgenda(null); }
      const prontos = rJobs.ok
        ? ((await rJobs.json()).jobs || []).filter((j) => j.clip_count > 0)
        : [];
      setProjetos(prontos);
      setDias(rDias.ok ? (await rDias.json()).dias || [] : []);
      if (rContas.ok) {
        const data = await rContas.json();
        setContas(data.contas || []);
        setQuota(data.quota_youtube || null);
      } else {
        // 503 é o banco fora do ar, e a mensagem dele já diz o que rodar.
        setContas([]);
        setErro((await rContas.json().catch(() => ({}))).detail || null);
      }
      setFila(rFila.ok ? (await rFila.json()).publicacoes || [] : []);
    } catch {
      setErro('Não consegui falar com o servidor.');
    }
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  const acao = async (fn) => {
    setOcupado(true);
    try { await fn(); await carregar(); } finally { setOcupado(false); }
  };

  const criarConta = () => acao(async () => {
    const res = await apiFetch('/api/contas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nova),
    });
    if (!res.ok) {
      setErro((await res.json().catch(() => ({}))).detail || 'Não deu.');
      return;
    }
    setNova({ ...nova, handle: '' });
    setErro(null);
  });

  const baixarPacote = (dia) => {
    // Download direto pelo navegador: o ZIP pode ter centenas de MB e passá-lo
    // por fetch() significaria carregá-lo inteiro na memória da aba antes de
    // salvar.
    // Pelo `getApiUrl`: no site do Cloudflare o servidor nao e a mesma origem
    // da pagina, e um caminho solto baixaria do Cloudflare (404).
    window.location.href = getApiUrl(`/api/publicacoes/pacote?dia=${encodeURIComponent(dia)}`);
  };

  const publicar = () => acao(async () => {
    const res = await apiFetch('/api/publicar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: envio.job_id, account_id: envio.account_id }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setErro(data.detail || 'Não deu para publicar.');
      setUltimoEnvio(null);
      return;
    }
    setErro(null);
    setUltimoEnvio(data.resultados || []);
  });

  const agendar = () => acao(async () => {
    const res = await apiFetch('/api/agendar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: envio.job_id, account_id: envio.account_id }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setErro(data.detail || 'Não deu para agendar.');
      setUltimoEnvio(null);
      return;
    }
    setErro(null);
    setUltimoEnvio(data.resultados || []);
  });

  const maisRecente = dias[0];
  // A publicação precisa dos dois: um projeto com cortes e uma conta de
  // destino. O driver NÃO entra aqui de propósito — quem escolhe é o
  // resolvedor do backend, e um seletor de driver na tela seria a porta que o
  // ADR-010 fecha, reaberta por fora.
  const podePublicar = envio.job_id && envio.account_id && !ocupado;

  return (
    <div className="h-full overflow-y-auto custom-scrollbar animate-fade px-4 py-5 sm:p-6">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <p className="eyebrow">publicação</p>
          <h2 className="font-display lowercase text-2xl sm:text-3xl text-ink">
            pacote e fila
          </h2>
        </div>

        {erro && (
          <div className="card p-3 flex items-start gap-2 text-sm text-danger">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>{erro}</span>
          </div>
        )}

        {/* 1. O pacote do dia — o que o driver `manual` entrega. */}
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">pacote do dia</h3>
          <p className="text-muted text-[13px] leading-snug">
            Os cortes do dia mais um arquivo de legenda por corte, pronto para
            selecionar tudo e colar: título, descrição e hashtags.
          </p>
          {maisRecente ? (
            <div className="flex flex-wrap items-center gap-2">
              <button
                className="btn-primary text-sm inline-flex items-center gap-2"
                onClick={() => baixarPacote(maisRecente.dia)}
              >
                <Download size={14} />
                {maisRecente.dia} · {maisRecente.cortes} corte
                {maisRecente.cortes === 1 ? '' : 's'}
              </button>
              {dias.slice(1, 5).map((d) => (
                <button key={d.dia} className="btn-quiet text-xs"
                        onClick={() => baixarPacote(d.dia)}>
                  {d.dia} ({d.cortes})
                </button>
              ))}
            </div>
          ) : (
            <p className="text-muted text-[13px]">Nenhum corte em disco ainda.</p>
          )}
        </section>

        {/* 2. Contas — onde se liga o automático. */}
        <section className="card p-4 space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h3 className="text-ink text-sm font-medium">contas</h3>
            {quota && (
              <span className="text-muted text-xs">
                YouTube: {quota.uploads_hoje}/{quota.uploads_por_dia} uploads hoje
              </span>
            )}
          </div>

          {contas === null ? (
            <Loader2 size={16} className="animate-spin text-muted" />
          ) : contas.length === 0 ? (
            <p className="text-muted text-[13px]">
              Nenhuma conta. Sem conta, os cortes ficam só no pacote do dia.
            </p>
          ) : (
            <ul className="space-y-2">
              {contas.map((c) => {
                const { nome, Icone } = PLATAFORMAS[c.platform] || PLATAFORMAS.youtube;
                return (
                  <li key={c.id}
                      className="flex items-center gap-3 text-sm border-t border-rule pt-2 first:border-0 first:pt-0">
                    <Icone size={15} className="text-muted shrink-0" />
                    <span className="text-ink">{c.handle}</span>
                    <span className="text-muted text-xs">{nome}</span>
                    <span className="text-muted text-xs ml-auto text-right">
                      {DRIVERS[c.driver_agora] || c.driver_agora}
                    </span>
                    {confirmando === c.id ? (
                      // Apagar a conta leva o histórico de publicação dela
                      // junto (ON DELETE CASCADE, §7). Mesma confirmação que
                      // apagar um projeto, e pelo mesmo motivo: o clique é
                      // pequeno e o que ele leva não é.
                      <span className="flex items-center gap-2 shrink-0">
                        <button className="text-danger text-xs"
                                disabled={ocupado}
                                onClick={() => acao(async () => {
                                  await apiFetch(`/api/contas/${c.id}`,
                                                 { method: 'DELETE' });
                                  setConfirmando(null);
                                })}>
                          apagar e o histórico
                        </button>
                        <button className="text-muted text-xs"
                                onClick={() => setConfirmando(null)}>
                          não
                        </button>
                      </span>
                    ) : (
                      <button
                        className="text-muted hover:text-danger shrink-0"
                        disabled={ocupado}
                        onClick={() => setConfirmando(c.id)}
                        title="remover conta"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <select
              className="input-field text-sm py-1.5 w-auto"
              value={nova.platform}
              onChange={(e) => setNova({ ...nova, platform: e.target.value })}
            >
              {Object.entries(PLATAFORMAS).map(([id, p]) => (
                <option key={id} value={id}>{p.nome}</option>
              ))}
            </select>
            <input
              className="input-field text-sm py-1.5 flex-1 min-w-[10rem]"
              placeholder="nome do canal"
              value={nova.handle}
              onChange={(e) => setNova({ ...nova, handle: e.target.value })}
            />
            <button className="btn-quiet text-sm inline-flex items-center gap-1.5"
                    disabled={ocupado || !nova.handle.trim()}
                    onClick={criarConta}>
              <Plus size={14} /> adicionar
            </button>
          </div>
          <p className="text-muted text-[12px] leading-snug">
            Para o YouTube subir sozinho, rode <code>python youtube_oauth.py</code>{' '}
            uma vez — sem isso a conta usa a fila manual, que continua entregando
            o corte e a legenda prontos.
          </p>
        </section>

        {/* 3. Publicar um projeto. */}
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">publicar</h3>
          {projetos.length === 0 || (contas || []).length === 0 ? (
            <p className="text-muted text-[13px]">
              {projetos.length === 0
                ? 'Nenhum projeto com cortes ainda.'
                : 'Adicione uma conta acima para escolher um destino.'}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                <select
                  className="input-field text-sm py-1.5 flex-1 min-w-[12rem]"
                  value={envio.job_id}
                  onChange={(e) => setEnvio({ ...envio, job_id: e.target.value })}
                >
                  <option value="">escolha um projeto…</option>
                  {projetos.map((j) => (
                    <option key={j.job_id} value={j.job_id}>
                      {j.title || j.job_id.slice(0, 8)} · {j.clip_count} corte
                      {j.clip_count === 1 ? '' : 's'}
                    </option>
                  ))}
                </select>
                <select
                  className="input-field text-sm py-1.5 w-auto"
                  value={envio.account_id}
                  onChange={(e) => setEnvio({ ...envio, account_id: e.target.value })}
                >
                  <option value="">conta…</option>
                  {(contas || []).map((c) => (
                    <option key={c.id} value={c.id}>{c.handle}</option>
                  ))}
                </select>
                <button className="btn-primary text-sm inline-flex items-center gap-1.5"
                        disabled={!podePublicar} onClick={publicar}>
                  {ocupado ? <Loader2 size={14} className="animate-spin" />
                           : <Send size={14} />}
                  publicar agora
                </button>
                <button className="btn-quiet text-sm inline-flex items-center gap-1.5"
                        disabled={!podePublicar} onClick={agendar}>
                  <Clock size={14} />
                  agendar
                </button>
              </div>
              <p className="text-muted text-[12px] leading-snug">
                O destino é a conta; o driver é consequência. Com credencial e
                quota, o corte sobe sozinho; sem, ele entra na fila manual com a
                legenda pronta.
              </p>
              {agenda && (
                // O horário aparece ANTES de agendar. Descobrir a que horas o
                // sistema publicou depois do post é tarde para discordar.
                <p className="text-muted text-[12px] leading-snug">
                  <strong className="text-ink2">agendar</strong> espalha os
                  cortes em {agenda.janelas.map((h) => `${h}h`).join(', ')}, no
                  máximo {agenda.por_dia} por dia, com ±{agenda.jitter_min} min
                  de variação — horário exato todo dia é um dos sinais que a
                  detecção de automação cruza.
                </p>
              )}
            </>
          )}
          {ultimoEnvio && (
            <ul className="text-[13px] space-y-1 pt-1">
              {ultimoEnvio.map((r) => (
                <li key={r.clip_index}
                    className={r.ok ? 'text-muted' : 'text-danger'}>
                  corte {r.clip_index + 1}: {r.detail || (r.ok ? 'ok' : 'falhou')}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 4. Onde vai o tempo — não é sobre publicação, e está aqui porque é
            onde o autor já olha. Quando houver uma aba de diagnóstico, muda. */}
        <CartaoDeTempo />

        {/* 5. A fila. */}
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">fila</h3>
          {fila.length === 0 ? (
            <p className="text-muted text-[13px]">Nada publicado ainda.</p>
          ) : (
            <ul className="space-y-2">
              {fila.map((p) => {
                const estado = ESTADO[p.status] || { texto: p.status, cor: 'text-muted' };
                return (
                  <li key={p.id}
                      className="flex items-center gap-3 text-sm border-t border-rule pt-2 first:border-0 first:pt-0">
                    <span className="text-ink truncate flex-1">
                      {p.clip.title || `corte ${(p.clip.index ?? 0) + 1}`}
                    </span>
                    <span className="text-muted text-xs hidden sm:inline">
                      {p.account.handle}
                    </span>
                    <span className={`text-xs ${estado.cor}`}>
                      {estado.texto}
                      {p.scheduled_at && p.status === 'scheduled' && (
                        <> · {new Date(p.scheduled_at).toLocaleString(undefined,
                          { day: '2-digit', month: 'short', hour: '2-digit',
                            minute: '2-digit' })}</>
                      )}
                    </span>
                    {p.status === 'scheduled' && (
                      <button
                        className="text-muted hover:text-ok shrink-0"
                        disabled={ocupado}
                        title="já publiquei"
                        onClick={() => acao(() =>
                          apiFetch(`/api/publicacoes/${p.id}/publicado`,
                                   { method: 'POST' }))}
                      >
                        <CheckCircle2 size={15} />
                      </button>
                    )}
                    {p.status !== 'published' && (
                      <button
                        className="text-muted hover:text-danger shrink-0"
                        disabled={ocupado}
                        title="tirar da fila"
                        onClick={() => acao(() =>
                          apiFetch(`/api/publicacoes/${p.id}`, { method: 'DELETE' }))}
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
