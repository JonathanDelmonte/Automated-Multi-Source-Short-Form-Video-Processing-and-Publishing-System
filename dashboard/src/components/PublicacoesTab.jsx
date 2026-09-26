import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Download, Trash2, Loader2, Plus,
         AlertTriangle, Send, Clock } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { getApiUrl } from '../config';
import IconePlataforma from './ui/IconePlataforma';
import AvatarDoCanal from './ui/AvatarDoCanal';
import FilaDePublicacoes from './FilaDePublicacoes';
import ConexaoDaConta from './ConexaoDaConta';
import { DRIVERS, ORDEM_DAS_PLATAFORMAS, PLATAFORMAS } from '../lib/plataformas';
import { usePainel } from '../lib/painel';
import {
  caminhoDaAgenda, caminhoDoPacote, canalDoDestino, corpoDoDestino, plataformasDoPacote,
} from '../lib/publicacoes';
import { janelasEmTexto } from '../lib/receita.js';
import { useAplicativos } from '../lib/aplicativo';
import { TIPOS_DE, situacaoDoAplicativo } from '../lib/conexoes';
import { hrefDe } from '../lib/rota';

// A publicação (Fase 3, bloco 3.5), em partes desde a 7.1: o pacote do dia, o
// publicar e a fila moram na Agenda; as contas, nas Configurações; e a página
// de cada canal usa a fila filtrada pelas contas dele (`contasDoCanal`) e pelo
// estado (`status`). Quem desenha o cabeçalho é a página.
//
// A ordem das partes é a ordem de importância do §6, não a de implementação: o
// **pacote do dia** primeiro, porque o driver `manual` é o default e o que
// entrega valor hoje.

export default function PublicacoesTab({
  secoes = ['pacote', 'publicar', 'fila'],
  canal = null,
  contasDoCanal = null,
  status = null,
  tituloDaFila = 'fila',
  vazioDaFila = 'Nada publicado ainda.',
  // Na tela de um projeto: o projeto já está escolhido, e o destino começa no
  // canal dele.
  projeto = null,
  canalDoProjeto = null,
}) {
  const { canais } = usePainel();
  const mostra = (secao) => secoes.includes(secao);
  const [dias, setDias] = useState([]);
  const [contas, setContas] = useState(null);
  const [quota, setQuota] = useState(null);
  const [fila, setFila] = useState([]);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [nova, setNova] = useState({ platform: 'youtube', handle: '' });
  const [projetos, setProjetos] = useState([]);
  const [envio, setEnvio] = useState({
    job_id: projeto || '',
    destino: canal ? `canal:${canal}` : (canalDoProjeto ? `canal:${canalDoProjeto}` : ''),
  });
  const [ultimoEnvio, setUltimoEnvio] = useState(null);
  const [plataformaDoPacote, setPlataformaDoPacote] = useState(null);
  const [confirmando, setConfirmando] = useState(null);
  const [agenda, setAgenda] = useState(null);
  const destinoAtual = useRef('');
  const aplicativos = useAplicativos();

  const carregar = useCallback(async () => {
    try {
      const [rDias, rContas, rFila, rJobs] = await Promise.all([
        apiFetch('/api/publicacoes/dias'),
        apiFetch('/api/contas'),
        apiFetch('/api/publicacoes'),
        apiFetch(canal ? `/api/jobs?canal=${encodeURIComponent(canal)}` : '/api/jobs'),
      ]);
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
  }, [canal]);

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

  // O pacote e escrito para UMA plataforma: a legenda de cada corte e a dela.
  const opcoesDoPacote = plataformasDoPacote(contasDoCanal
    ? (contas || []).filter((c) => contasDoCanal.includes(c.id))
    : contas);
  const pacotePara = opcoesDoPacote.includes(plataformaDoPacote)
    ? plataformaDoPacote : opcoesDoPacote[0];

  const baixarPacote = (dia) => {
    // Download direto pelo navegador: o ZIP pode ter centenas de MB e passá-lo
    // por fetch() significaria carregá-lo inteiro na memória da aba antes de
    // salvar.
    // Pelo `getApiUrl`: no site do Cloudflare o servidor nao e a mesma origem
    // da pagina, e um caminho solto baixaria do Cloudflare (404).
    window.location.href = getApiUrl(caminhoDoPacote(dia, pacotePara));
  };

  const enviar = (rota, falha) => acao(async () => {
    const corpo = corpoDoDestino(envio.job_id, destinoAtual.current);
    if (!corpo) return;
    const res = await apiFetch(rota, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      setErro(data.detail || falha);
      setUltimoEnvio(null);
      return;
    }
    setErro(null);
    setUltimoEnvio(data.resultados || []);
  });
  const publicar = () => enviar('/api/publicar', 'Não deu para publicar.');
  const agendar = () => enviar('/api/agendar', 'Não deu para agendar.');

  const maisRecente = dias[0];
  // Na página de um canal, só o que é dele: as contas dele como destino, e a
  // fila das publicações que saíram (ou vão sair) por elas.
  const contasDestino = contasDoCanal
    ? (contas || []).filter((c) => contasDoCanal.includes(c.id))
    : (contas || []);
  const filaVisivel = fila.filter((p) =>
    (!contasDoCanal || contasDoCanal.includes(p.account?.id))
    && (!status || p.status === status));
  // Os canais que servem de destino: os que têm conta ligada. Na página de um
  // canal, só ele.
  const contasPorCanal = {};
  for (const c of contas || []) {
    if (c.channel_id) (contasPorCanal[c.channel_id] ||= []).push(c);
  }
  const canaisDestino = (canais.canais || []).filter((c) =>
    contasPorCanal[c.id]?.length && (!canal || c.id === canal));
  // A publicação precisa dos dois: um projeto com cortes e um destino. O
  // driver NÃO entra aqui de propósito — quem escolhe é o resolvedor do
  // backend, e um seletor de driver na tela seria a porta que o ADR-010 fecha,
  // reaberta por fora.
  // O destino que veio pronto (o canal do projeto, o canal da página) só vale
  // se ainda for um destino possível: um canal sem conta ligada não é.
  const destinos = new Set([
    ...canaisDestino.map((c) => `canal:${c.id}`),
    ...contasDestino.map((c) => `conta:${c.id}`),
  ]);
  const destino = destinos.has(envio.destino) ? envio.destino : '';
  destinoAtual.current = destino;
  const podePublicar = corpoDoDestino(envio.job_id, destino) && !ocupado;
  const destinoEhCanal = destino.startsWith('canal:');
  // A agenda que o "agendar" vai seguir: a do canal do destino (7.5) -- o
  // canal inteiro, ou o canal da conta escolhida --, ou a da instalação para
  // uma conta solta. Pedida de novo a cada troca de destino: o texto não pode
  // descrever as janelas de outro canal.
  const canalDaAgenda = canalDoDestino(destino, contas);
  const nomeDoCanalDaAgenda = canalDaAgenda ? canais.porId[canalDaAgenda]?.name : null;
  useEffect(() => {
    let vivo = true;
    apiFetch(caminhoDaAgenda(canalDaAgenda))
      .then((r) => (r.ok ? r.json() : null))
      .then((dados) => { if (vivo) setAgenda(dados); })
      .catch(() => { if (vivo) setAgenda(null); });
    return () => { vivo = false; };
  }, [canalDaAgenda]);

  return (
      <div className="space-y-6">
        {erro && (
          <div className="card p-3 flex items-start gap-2 text-sm text-danger">
            <AlertTriangle size={15} className="mt-0.5 shrink-0" />
            <span>{erro}</span>
          </div>
        )}

        {/* 1. O pacote do dia — o que o driver `manual` entrega. */}
        {mostra('pacote') && (
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">pacote do dia</h3>
          <p className="text-muted text-[13px] leading-snug">
            Os cortes do dia mais um arquivo de legenda por corte, escrito para a
            plataforma escolhida e pronto para selecionar tudo e colar: título,
            descrição e hashtags.
            {pacotePara === 'instagram' && ' No Instagram, com no máximo 5 hashtags: é o limite do app.'}
          </p>
          {opcoesDoPacote.length > 1 && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="plataforma do pacote">
              {opcoesDoPacote.map((p) => (
                <button
                  key={p}
                  type="button"
                  data-plataforma={p}
                  aria-pressed={p === pacotePara}
                  onClick={() => setPlataformaDoPacote(p)}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs transition-colors ${
                    p === pacotePara
                      ? 'border-[color:var(--color-accent)] text-ink'
                      : 'border-rule2 text-muted hover:text-ink2'}`}
                >
                  <IconePlataforma platform={p} size={14} mono={p !== pacotePara} />
                  {PLATAFORMAS[p].nome}
                </button>
              ))}
            </div>
          )}
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
        )}

        {/* 2. Contas — onde se liga o automático. */}
        {mostra('contas') && (
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
                const nome = PLATAFORMAS[c.platform]?.nome || c.platform;
                const doCanal = c.channel_id ? canais.porId[c.channel_id] : null;
                return (
                  <li key={c.id}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm border-t border-rule pt-2 first:border-0 first:pt-0"
                      data-conta={c.handle}>
                    <IconePlataforma platform={c.platform} size={17} title={nome} />
                    <span className="text-ink">{c.handle}</span>
                    {doCanal ? (
                      <a href={hrefDe(`/canais/${doCanal.id}`)}
                         className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-ink2">
                        <AvatarDoCanal canal={doCanal} size={16} /> {doCanal.name}
                      </a>
                    ) : (
                      <span className="text-muted text-xs">sem canal</span>
                    )}
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
                    {c.conexao && (TIPOS_DE[c.platform] || c.platform === 'instagram') && (
                      <div className="basis-full pl-7">
                        <ConexaoDaConta conta={c} aplicativo={situacaoDoAplicativo(aplicativos.prontos, c.platform)}
                                        aoMudar={carregar} />
                      </div>
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
              {ORDEM_DAS_PLATAFORMAS.map((id) => (
                <option key={id} value={id}>{PLATAFORMAS[id].nome}</option>
              ))}
            </select>
            <input
              className="input-field text-sm py-1.5 flex-1 min-w-[10rem]"
              placeholder="@ da conta"
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
            Para o YouTube subir sozinho, conecte a conta (o botão aparece depois
            do cadastro do aplicativo, logo acima) — sem isso a conta usa a fila
            manual, que continua entregando o corte e a legenda prontos. Para
            ligar a conta a um canal, use os ajustes do canal.
          </p>
        </section>
        )}

        {/* 3. Publicar um projeto. */}
        {mostra('publicar') && (
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">publicar</h3>
          {(projeto ? false : projetos.length === 0) || (canaisDestino.length === 0 && contasDestino.length === 0) ? (
            <p className="text-muted text-[13px]">
              {!projeto && projetos.length === 0
                ? 'Nenhum projeto com cortes ainda.'
                : 'Ligue uma conta a um canal (ou cadastre uma nas Configurações) para escolher um destino.'}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-2">
                {!projeto && (
                  <select
                    className="input-field text-sm py-1.5 flex-1 min-w-[12rem]"
                    value={envio.job_id}
                    onChange={(e) => setEnvio({ ...envio, job_id: e.target.value })}
                    aria-label="projeto"
                  >
                    <option value="">escolha um projeto…</option>
                    {projetos.map((j) => (
                      <option key={j.job_id} value={j.job_id}>
                        {j.title || j.job_id.slice(0, 8)} · {j.clip_count} corte
                        {j.clip_count === 1 ? '' : 's'}
                      </option>
                    ))}
                  </select>
                )}
                <select
                  className="input-field text-sm py-1.5 flex-1 min-w-[12rem] sm:flex-none sm:w-auto"
                  value={destino}
                  onChange={(e) => setEnvio({ ...envio, destino: e.target.value })}
                  aria-label="destino"
                >
                  <option value="">para onde…</option>
                  {canaisDestino.length > 0 && (
                    <optgroup label="o canal inteiro (um galho por conta)">
                      {canaisDestino.map((c) => (
                        <option key={c.id} value={`canal:${c.id}`}>
                          {c.name} · {contasPorCanal[c.id].map((x) => PLATAFORMAS[x.platform]?.nome || x.platform).join(', ')}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="uma conta só">
                    {contasDestino.map((c) => (
                      <option key={c.id} value={`conta:${c.id}`}>
                        {PLATAFORMAS[c.platform]?.nome || c.platform} · {c.handle}
                      </option>
                    ))}
                  </optgroup>
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
                {destinoEhCanal
                  ? 'No canal, cada corte vira um galho por conta: o texto da plataforma de cada uma, e horário próprio ao agendar.'
                  : 'O destino é a conta; o driver é consequência.'}{' '}
                Com a conta conectada, o corte sobe sozinho; sem, ele entra na fila manual com a
                legenda pronta, e você marca “já publiquei” com o link do post.
              </p>
              {agenda && (
                // O horário aparece ANTES de agendar. Descobrir a que horas o
                // sistema publicou depois do post é tarde para discordar.
                <p className="text-muted text-[12px] leading-snug" data-agenda={canalDaAgenda || 'instalacao'}>
                  <strong className="text-ink2">agendar</strong>{' '}
                  {nomeDoCanalDaAgenda
                    ? <>segue a agenda de <span className="text-ink2">{nomeDoCanalDaAgenda}</span>:</>
                    : 'espalha os cortes em'}{' '}
                  {janelasEmTexto(agenda.janelas)}
                  {agenda.fuso?.nome ? ` (${agenda.fuso.nome})` : ''}, no
                  máximo {agenda.por_dia} por dia em cada conta, com ±{agenda.jitter_min} min
                  de variação — horário exato todo dia é um dos sinais que a
                  detecção de automação cruza. Se o computador estiver desligado na
                  hora, os atrasados saem um de cada vez quando ele voltar.
                  {nomeDoCanalDaAgenda && (
                    <>
                      {' '}
                      <a href={hrefDe(`/canais/${canalDaAgenda}/ajustes`)}
                         className="underline underline-offset-2 hover:text-ink2">mudar a agenda do canal</a>
                    </>
                  )}
                </p>
              )}
            </>
          )}
          {ultimoEnvio && (
            <ul className="text-[13px] space-y-1 pt-1">
              {ultimoEnvio.map((r, i) => (
                <li key={`${r.clip_index}-${r.account_id || i}`}
                    className={`flex items-center gap-1.5 ${r.ok ? 'text-muted' : 'text-danger'}`}>
                  {r.platform && <IconePlataforma platform={r.platform} size={13} />}
                  <span>
                    corte {r.clip_index + 1}{r.handle ? ` · ${r.handle}` : ''}:{' '}
                    {r.scheduled_at && r.ok
                      ? `agendado para ${new Date(r.scheduled_at).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}`
                      : (r.detail || (r.ok ? 'ok' : 'falhou'))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        )}

        {/* 4. A fila. ("Onde vai o tempo" morava aqui, "porque é onde o autor já
            olha"; foi para Configurações -> Desempenho na 7.1.) */}
        {mostra('fila') && (
        <section className="card p-4 space-y-3">
          <h3 className="text-ink text-sm font-medium">{tituloDaFila}</h3>
          <FilaDePublicacoes
            publicacoes={filaVisivel}
            ocupado={ocupado}
            aoMudar={carregar}
            vazio={vazioDaFila}
          />
        </section>
        )}
      </div>
  );
}
