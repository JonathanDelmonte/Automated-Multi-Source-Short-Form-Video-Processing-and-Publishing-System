import React, { useEffect, useMemo, useState } from 'react';
import { Check, FolderOpen, Link2, Loader2, Radio, Search, Sparkles } from 'lucide-react';
import SegmentedControl from '../ui/SegmentedControl';
import { lerTemplates, salvarReceita } from '../../lib/automacao';
import {
  DURACOES, FONTES, LAYOUTS, RECEITA_PADRAO, aplicarModelo, faltaParaLigar, linksDoTexto,
  modeloDoNicho, precisaDeDireitos,
} from '../../lib/receita.js';

// O editor da receita do canal (etapa 7.5): de onde vêm os vídeos e como
// editar. Quando postar é a agenda do canal (nos ajustes), e se espera
// aprovação é escolha do canal desde a 7.1 -- a receita só os mostra.
//
// O estado nasce da receita gravada UMA vez: quem o usa monta o editor com
// `key` na hora da gravação, e o recarregar periódico da aba não apaga o que
// a pessoa está digitando.

const ICONES = { busca: Search, links: Link2, twitch: Radio, pasta: FolderOpen };

function Numero({ rotulo, valor, aoMudar, min, max, sufixo, id }) {
  return (
    <label className="block min-w-0" htmlFor={id}>
      <span className="eyebrow">{rotulo}</span>
      <span className="mt-1.5 flex items-center gap-2">
        <input
          id={id}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          className="input-field w-24"
          value={valor}
          onChange={(e) => aoMudar(e.target.value === '' ? '' : Number(e.target.value))}
        />
        {sufixo && <span className="text-xs text-muted">{sufixo}</span>}
      </span>
    </label>
  );
}

function Marcar({ marcado, aoMudar, children, id }) {
  return (
    <label className="flex items-start gap-2.5 text-sm text-ink2 cursor-pointer" htmlFor={id}>
      <input id={id} type="checkbox" className="mt-0.5 accent-[color:var(--color-accent)] w-4 h-4 shrink-0"
             checked={marcado} onChange={(e) => aoMudar(e.target.checked)} />
      <span className="min-w-0">{children}</span>
    </label>
  );
}

export default function ReceitaDoCanal({ canal, tela, aoSalvar }) {
  const receita = tela.receita;
  const [spec, setSpec] = useState(receita.spec || RECEITA_PADRAO);
  const [textoDosLinks, setTextoDosLinks] = useState((receita.spec?.fonte?.links || []).join('\n'));
  const [direitos, setDireitos] = useState(false);
  const [templates, setTemplates] = useState(null);
  const [salvando, setSalvando] = useState(null);
  const [erro, setErro] = useState(null);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    let vivo = true;
    lerTemplates().then((r) => { if (vivo) setTemplates(r.ok ? r.data.templates || [] : []); });
    return () => { vivo = false; };
  }, []);

  const modelo = useMemo(() => modeloDoNicho(canal.niche), [canal.niche]);
  const fonte = spec.fonte || RECEITA_PADRAO.fonte;
  const edicao = spec.edicao || RECEITA_PADRAO.edicao;
  const specParaSalvar = useMemo(() => ({
    ...spec,
    fonte: { ...fonte, links: linksDoTexto(textoDosLinks) },
  }), [spec, fonte, textoDosLinks]);
  // A confirmação vale para a fonte que estava na tela quando foi dada.
  const fonteConfirmada = Boolean(receita.spec?.direitos)
    && JSON.stringify(receita.spec?.fonte?.links || []) === JSON.stringify(specParaSalvar.fonte.links)
    && receita.spec?.fonte?.tipo === fonte.tipo
    && (receita.spec?.fonte?.twitch || '') === (fonte.twitch || '');
  const falta = faltaParaLigar({ ...specParaSalvar, direitos: fonteConfirmada ? 'sim' : null }, direitos);

  const mudarFonte = (campo, valor) => setSpec((s) => ({ ...s, fonte: { ...s.fonte, [campo]: valor } }));
  const mudarEdicao = (campo, valor) => setSpec((s) => ({ ...s, edicao: { ...s.edicao, [campo]: valor } }));
  const mudarRitmo = (valor) => setSpec((s) => ({ ...s, ritmo: { ...s.ritmo, videos_por_dia: valor } }));

  const salvar = async (ativa) => {
    setSalvando(ativa === undefined ? 'salvar' : ativa ? 'ligar' : 'desligar');
    setErro(null);
    setSalvo(false);
    const r = await salvarReceita(canal.id, {
      spec: specParaSalvar,
      ativa: ativa === undefined ? receita.ativa && !falta : ativa,
      confirmarDireitos: direitos,
    });
    setSalvando(null);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    setSalvo(true);
    aoSalvar(r.data);
  };

  return (
    <div className="space-y-5">
      {modelo && !receita.id && (
        <div className="rounded-input border border-rule2 p-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-ink2 flex items-center gap-2 min-w-0">
            <Sparkles size={15} className="shrink-0 text-muted" />
            <span className="min-w-0">Um ponto de partida para o nicho <strong className="text-ink font-medium">{modelo.nome}</strong>: tema, duração e quantos cortes por vídeo. Você muda o que quiser.</span>
          </p>
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={() => setSpec((s) => aplicarModelo(s, modelo))}>
            usar o modelo
          </button>
        </div>
      )}

      <section className="space-y-3">
        <p className="eyebrow">de onde vêm os vídeos</p>
        <SegmentedControl
          options={FONTES.map((f) => {
            const Icone = ICONES[f.id];
            return { value: f.id, label: f.nome, icon: <Icone size={15} /> };
          })}
          value={fonte.tipo}
          onChange={(v) => mudarFonte('tipo', v)}
          columns={4}
          minColPx={120}
        />
        <p className="text-muted text-[13px] leading-snug">{FONTES.find((f) => f.id === fonte.tipo)?.texto}</p>

        {fonte.tipo === 'busca' && (
          <div className="space-y-3">
            <label className="block" htmlFor="receita-tema">
              <span className="eyebrow">tema</span>
              <input id="receita-tema" className="input-field mt-1.5" maxLength={120} value={fonte.tema || ''}
                     onChange={(e) => mudarFonte('tema', e.target.value)}
                     placeholder="Ex.: desenho animado infantil" />
            </label>
            {modelo && (
              <div className="flex flex-wrap gap-1.5" aria-label="ideias de tema">
                {modelo.temas.map((t) => (
                  <button key={t} type="button" onClick={() => mudarFonte('tema', t)}
                          className={`px-2.5 py-1 rounded-full border text-xs transition-colors ${
                            fonte.tema === t ? 'border-brass text-ink bg-paper3' : 'border-rule text-muted hover:text-ink2'}`}>
                    {t}
                  </button>
                ))}
              </div>
            )}
            <div>
              <span className="eyebrow">duração do vídeo original</span>
              <div className="mt-1.5">
                <SegmentedControl size="sm" options={DURACOES.map((d) => ({ value: d.id, label: d.nome }))}
                                  value={fonte.duracao} onChange={(v) => mudarFonte('duracao', v)} />
              </div>
            </div>
            <p className="text-muted text-[12px] leading-snug">
              Só entra vídeo com a licença Creative Commons conferida no próprio vídeo, e o crédito do autor vai
              na descrição de cada post. {tela.busca_pela_api
                ? 'Com uma conta do YouTube conectada para medir, a busca usa a API do YouTube (100 por dia); sem ela, a página do YouTube.'
                : 'As buscas pela API do YouTube de hoje acabaram; até amanhã, vai pela página do YouTube.'}
            </p>
          </div>
        )}

        {fonte.tipo === 'links' && (
          <label className="block" htmlFor="receita-links">
            <span className="eyebrow">links, um por linha</span>
            <textarea id="receita-links" className="input-field mt-1.5 min-h-[7rem] font-mono text-[12px]" value={textoDosLinks}
                      onChange={(e) => setTextoDosLinks(e.target.value)}
                      placeholder={'https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/playlist?list=...\nhttps://www.youtube.com/@canal'} />
            <span className="block text-muted text-[12px] mt-1.5 leading-snug">
              Uma playlist ou um canal entram pelos vídeos mais novos. A licença de cada vídeo fica registrada, e o
              crédito vai na descrição quando ela for Creative Commons.
            </span>
          </label>
        )}

        {fonte.tipo === 'twitch' && (
          <label className="block" htmlFor="receita-twitch">
            <span className="eyebrow">canal da Twitch</span>
            <input id="receita-twitch" className="input-field mt-1.5" value={fonte.twitch || ''}
                   onChange={(e) => mudarFonte('twitch', e.target.value)} placeholder="twitch.tv/nome-do-canal" />
            <span className="block text-muted text-[12px] mt-1.5 leading-snug">
              A cada volta, se o canal estiver no ar, um bloco da live é gravado e cortado. Fora do ar, nada acontece.
            </span>
          </label>
        )}

        {fonte.tipo === 'pasta' && (
          <div className="rounded-input border border-rule p-3 space-y-1.5">
            {receita.pasta && receita.spec?.fonte?.tipo === 'pasta' ? (
              <>
                <p className="text-sm text-ink2">Ponha os vídeos nesta pasta:</p>
                <p className="font-mono text-[12px] text-ink break-all select-all">{receita.pasta.caminho}</p>
                <p className="text-muted text-[12px] leading-snug">
                  No Docker, ela fica dentro da pasta do projeto, em <span className="font-mono">{receita.pasta.relativo}</span>.
                  Cada vídeo é cortado uma vez; o original fica na pasta.
                </p>
              </>
            ) : (
              <p className="text-muted text-[13px]">Salve a receita para o programa criar a pasta do canal.</p>
            )}
          </div>
        )}

        {precisaDeDireitos(specParaSalvar) && (
          fonteConfirmada && !direitos ? (
            <p className="text-sm text-ok flex items-center gap-2"><Check size={15} /> Você confirmou ter os direitos sobre esta fonte.</p>
          ) : (
            <Marcar id="receita-direitos" marcado={direitos} aoMudar={setDireitos}>
              {fonte.tipo === 'pasta'
                ? 'Os vídeos que eu puser nesta pasta são meus ou tenho autorização para usá-los.'
                : fonte.tipo === 'twitch'
                  ? 'A live é minha ou tenho autorização de quem transmite para cortá-la e postar.'
                  : 'Os vídeos destes links são meus, têm licença livre ou tenho autorização para usá-los.'}
            </Marcar>
          )
        )}
      </section>

      <section className="space-y-3">
        <p className="eyebrow">como editar</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Numero id="receita-cortes" rotulo="cortes por vídeo" valor={edicao.cortes_por_video} min={1} max={15}
                  aoMudar={(v) => mudarEdicao('cortes_por_video', v)} />
          <Numero id="receita-min" rotulo="corte mínimo" valor={edicao.duracao_min} min={5} max={175} sufixo="s"
                  aoMudar={(v) => mudarEdicao('duracao_min', v)} />
          <Numero id="receita-max" rotulo="corte máximo" valor={edicao.duracao_max} min={10} max={180} sufixo="s"
                  aoMudar={(v) => mudarEdicao('duracao_max', v)} />
          <Numero id="receita-por-dia" rotulo="vídeos por dia" valor={spec.ritmo?.videos_por_dia ?? 1} min={1} max={10}
                  aoMudar={mudarRitmo} />
        </div>
        <div>
          <span className="eyebrow">layout</span>
          <div className="mt-1.5">
            {/* Duas por linha no celular: a dica de cada layout é mono, e
                "só o enquadramento" não cabe num quarto da tela. */}
            <SegmentedControl size="sm" minColPx={130}
                              options={LAYOUTS.map((l) => ({ value: l.id, label: l.nome, hint: l.texto }))}
                              value={edicao.layout} onChange={(v) => mudarEdicao('layout', v)} />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-2.5">
            <Marcar id="receita-legenda" marcado={Boolean(edicao.legenda)} aoMudar={(v) => mudarEdicao('legenda', v)}>
              legenda nos cortes
            </Marcar>
            <Marcar id="receita-gancho" marcado={Boolean(edicao.gancho)} aoMudar={(v) => mudarEdicao('gancho', v)}>
              gancho escrito no começo do corte
            </Marcar>
          </div>
          <label className="block" htmlFor="receita-template">
            <span className="eyebrow">estilo da legenda</span>
            <select id="receita-template" className="input-field mt-1.5" value={edicao.template_id || ''}
                    disabled={!edicao.legenda} onChange={(e) => mudarEdicao('template_id', e.target.value || null)}>
              <option value="">o padrão do programa</option>
              {(templates || []).map((t) => (
                <option key={t.id} value={t.id}>{t.name}{t.version > 1 ? ` (versão ${t.version})` : ''}</option>
              ))}
            </select>
          </label>
        </div>
        <p className="text-muted text-[12px] leading-snug">
          A receita corta um vídeo de cada vez, e para quando a agenda do canal já tem posts para os próximos dias —
          ou cortes esperando a sua aprovação.
        </p>
      </section>

      {erro && <p className="text-danger text-sm" role="alert">{erro}</p>}
      {salvo && !erro && <p className="text-ok text-sm flex items-center gap-2"><Check size={15} /> Receita salva.</p>}
      <div className="flex flex-wrap items-center gap-2">
        {receita.ativa ? (
          <>
            <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => salvar()} disabled={Boolean(salvando) || Boolean(falta)}>
              {salvando === 'salvar' ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} salvar
            </button>
            <button type="button" className="btn-ghost px-4 py-2 text-sm" onClick={() => salvar(false)} disabled={Boolean(salvando)}>
              {salvando === 'desligar' && <Loader2 size={15} className="animate-spin" />} desligar a receita
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={() => salvar(true)} disabled={Boolean(salvando) || Boolean(falta)}>
              {salvando === 'ligar' ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} salvar e ligar
            </button>
            <button type="button" className="btn-ghost px-4 py-2 text-sm" onClick={() => salvar(false)} disabled={Boolean(salvando)}>
              {salvando === 'desligar' && <Loader2 size={15} className="animate-spin" />} só salvar
            </button>
          </>
        )}
        {falta && <span className="text-xs text-muted">{falta}</span>}
      </div>
    </div>
  );
}
