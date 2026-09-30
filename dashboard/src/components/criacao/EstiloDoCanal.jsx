import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, KeyRound, Loader2, Palette, Play, Plus, Sparkles, Square, UsersRound } from 'lucide-react';
import PersonagemDoEstilo from './PersonagemDoEstilo';
import SegmentedControl from '../ui/SegmentedControl';
import { Secao } from '../ui/Pagina';
import {
  CENAS, DURACAO, ESTILO_PADRAO, FORMATOS, LEGENDAS, MAX_PERSONAGENS, VISUAIS, fraseDaCota,
} from '../../lib/criacao.js';
import {
  enviarPersonagem, gerarPersonagem, lerEstilo, ouvirVoz, reduzirSemCortar, salvarEstilo,
} from '../../lib/criacaoNoMotor';
import { hrefDe } from '../../lib/rota';

// O estilo dos vídeos criados por IA (etapa 7.7), na aba Criar do canal. É o que
// faz um vídeo sair parecido com o anterior: o formato, o visual, os
// personagens com imagem de referência, a voz e a legenda. Tudo escolhido por
// quem usa -- nada vem do nicho (decisão do autor, 26-set-2026).
//
// O editor nasce do estilo gravado e só remonta quando ele é gravado de novo
// (`key`): gerar a imagem de um personagem não pode apagar o que a pessoa
// estava digitando nos outros campos.

function Numero({ id, rotulo, valor, aoMudar, min, max, sufixo }) {
  return (
    <label className="block min-w-0" htmlFor={id}>
      <span className="eyebrow">{rotulo}</span>
      <span className="mt-1.5 flex items-center gap-2">
        <input id={id} type="number" inputMode="numeric" min={min} max={max} className="input-field w-24"
               value={valor} onChange={(e) => aoMudar(e.target.value === '' ? '' : Number(e.target.value))} />
        {sufixo && <span className="text-xs text-muted">{sufixo}</span>}
      </span>
    </label>
  );
}

function Texto({ id, rotulo, valor, aoMudar, max, dica, area = false }) {
  const Campo = area ? 'textarea' : 'input';
  return (
    <label className="block min-w-0" htmlFor={id}>
      <span className="eyebrow">{rotulo}</span>
      <Campo id={id} className={`input-field mt-1.5 ${area ? 'min-h-[5rem]' : ''}`} maxLength={max}
             value={valor || ''} onChange={(e) => aoMudar(e.target.value)} placeholder={dica} />
    </label>
  );
}

// O que o motor diz que ainda falta, e as chaves: a tela só mostra.
function Situacao({ tela, cenas, canalId, sujo }) {
  const midia = tela.midia || {};
  const semChave = !midia.imagem || !midia.voz;
  return (
    <div className="card p-4 sm:p-5 space-y-2" data-situacao-do-estilo>
      {semChave ? (
        <p className="flex items-start gap-2 text-sm text-ink2">
          <KeyRound size={15} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0">
            {!midia.imagem && 'Falta a chave da Cloudflare (as imagens grátis). '}
            {!midia.voz && 'Falta a chave do Gemini (a narração grátis). '}
            <a href={hrefDe('/configuracoes/chaves')} className="text-ink underline underline-offset-2">Pôr nas Configurações</a>
          </span>
        </p>
      ) : tela.pode_criar ? (
        <p className="flex items-start gap-2 text-sm text-ink2">
          <AlertTriangle size={15} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0">{tela.pode_criar}</span>
        </p>
      ) : (
        <p className="flex items-start gap-2 text-sm text-ink">
          <Check size={15} className="shrink-0 mt-0.5 text-ok" />
          <span className="min-w-0">
            O estilo está pronto.{' '}
            <a href={hrefDe(`/criar/ia?canal=${canalId}`)} className="underline underline-offset-2">Criar um vídeo agora</a>
            {' '}ou ligar a receita de IA na aba Automação.
          </span>
        </p>
      )}
      {tela.cota && <p className="text-[12px] text-muted leading-snug">{fraseDaCota(tela.cota, cenas)}</p>}
      {sujo && <p className="text-[12px] text-muted">Há mudanças ainda não salvas.</p>}
    </div>
  );
}

function Editor({ canal, tela, aoGravar }) {
  const gravado = tela.estilo?.spec || { ...ESTILO_PADRAO, ...(tela.padrao || {}) };
  const [spec, setSpec] = useState(gravado);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(null);
  const [amostra, setAmostra] = useState({ url: null, carregando: false, erro: null });
  const audio = useRef(null);
  const catalogo = tela.catalogo || {};
  const vozes = catalogo.vozes || [{ nome: 'Kore', jeito: 'firme' }];
  const imagens = tela.estilo?.imagens || {};
  const sujo = JSON.stringify(spec) !== JSON.stringify(gravado);

  useEffect(() => () => { if (amostra.url) URL.revokeObjectURL(amostra.url); }, [amostra.url]);

  const mudar = (campo, valor) => setSpec((s) => ({ ...s, [campo]: valor }));
  const mudarDe = (secao, campo, valor) => setSpec((s) => ({ ...s, [secao]: { ...(s[secao] || {}), [campo]: valor } }));
  const personagens = spec.personagens || [];
  const mudarPersonagem = (i, p) => mudar('personagens', personagens.map((x, j) => (j === i ? p : x)));

  // Grava o que está na tela e devolve o estilo gravado (com o id que o motor
  // deu a cada personagem novo), ou null.
  const gravar = async () => {
    setErro(null);
    const r = await salvarEstilo(canal.id, spec);
    if (!r.ok) {
      setErro(r.erro);
      return null;
    }
    return r.data;
  };

  const salvar = async () => {
    setSalvando(true);
    const dados = await gravar();
    setSalvando(false);
    if (dados) aoGravar(dados);
  };

  // A imagem de um personagem precisa dele gravado (e do id que o motor dá):
  // grava antes, se a tela mudou, e só então pede a imagem.
  const comPersonagemGravado = async (i, acao) => {
    setOcupado(i);
    setErro(null);
    let alvo = personagens[i];
    let estilo = tela.estilo;
    if (sujo || !alvo.id) {
      const dados = await gravar();
      if (!dados) {
        setOcupado(null);
        return;
      }
      estilo = dados.estilo;
      alvo = estilo.spec.personagens[i];
    }
    const r = await acao(alvo.id);
    setOcupado(null);
    if (!r.ok) {
      setErro(r.erro);
      if (estilo !== tela.estilo) aoGravar({ estilo, pode_criar: tela.pode_criar });
      return;
    }
    aoGravar(r.data);
  };

  const gerar = (i) => comPersonagemGravado(i, (pid) => gerarPersonagem(canal.id, pid));
  const enviar = (i, arquivo) => comPersonagemGravado(i, async (pid) => {
    let dataUrl;
    try {
      dataUrl = await reduzirSemCortar(arquivo);
    } catch (e) {
      return { ok: false, erro: e.message };
    }
    return enviarPersonagem(canal.id, pid, dataUrl);
  });

  const ouvir = async () => {
    if (amostra.url) URL.revokeObjectURL(amostra.url);
    setAmostra({ url: null, carregando: true, erro: null });
    const r = await ouvirVoz(canal.id, spec.voz?.nome || 'Kore', spec.voz?.instrucao || '');
    setAmostra(r.ok ? { url: r.url, carregando: false, erro: null } : { url: null, carregando: false, erro: r.erro });
  };
  useEffect(() => {
    if (amostra.url && audio.current) audio.current.play().catch(() => {});
  }, [amostra.url]);

  const visual = spec.visual || ESTILO_PADRAO.visual;
  const opcoesDeVisual = useMemo(() => VISUAIS.map((v) => ({ value: v.id, label: v.nome, hint: v.texto })), []);

  return (
    <div className="space-y-4">
      <Situacao tela={tela} cenas={spec.cenas} canalId={canal.id} sujo={sujo} />

      <Secao titulo="o vídeo" icone={Sparkles}>
        <SegmentedControl options={FORMATOS.map((f) => ({ value: f.id, label: f.nome }))} value={spec.formato}
                          onChange={(v) => mudar('formato', v)} columns={4} minColPx={110} />
        <p className="text-muted text-[13px]">{FORMATOS.find((f) => f.id === spec.formato)?.texto}</p>
        <div className="flex flex-wrap gap-4">
          <Numero id="estilo-duracao" rotulo="duração" valor={spec.duracao_s} min={DURACAO.min} max={DURACAO.max}
                  sufixo={`segundos (${DURACAO.min} a ${DURACAO.max})`} aoMudar={(v) => mudar('duracao_s', v)} />
          <Numero id="estilo-cenas" rotulo="cenas" valor={spec.cenas} min={CENAS.min} max={CENAS.max}
                  sufixo="imagens por vídeo" aoMudar={(v) => mudar('cenas', v)} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Texto id="estilo-publico" rotulo="para quem" max={200} valor={spec.publico}
                 dica="Ex.: crianças de 4 a 8 anos" aoMudar={(v) => mudar('publico', v)} />
          <Texto id="estilo-tom" rotulo="o tom" max={200} valor={spec.tom}
                 dica="Ex.: divertido e carinhoso" aoMudar={(v) => mudar('tom', v)} />
        </div>
        <Texto id="estilo-instrucoes" rotulo="regras do canal (opcional)" max={1200} area valor={spec.instrucoes}
               dica="Ex.: toda história termina com uma lição sobre amizade; nada de monstros assustadores."
               aoMudar={(v) => mudar('instrucoes', v)} />
      </Secao>

      <Secao titulo="o visual" icone={Palette}>
        <SegmentedControl options={opcoesDeVisual} value={visual.preset} onChange={(v) => mudarDe('visual', 'preset', v)}
                          columns={4} minColPx={130} size="sm" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Texto id="estilo-visual" rotulo={visual.preset === 'nenhum' ? 'como são as imagens' : 'detalhes do visual (opcional)'}
                 max={400} valor={visual.descricao} aoMudar={(v) => mudarDe('visual', 'descricao', v)}
                 dica="Ex.: tons de azul e verde, cenário de floresta" />
          <Texto id="estilo-evitar" rotulo="o que nunca aparece (opcional)" max={200} valor={visual.evitar}
                 aoMudar={(v) => mudarDe('visual', 'evitar', v)} dica="Ex.: sangue, armas" />
        </div>
      </Secao>

      <Secao titulo="os personagens" icone={UsersRound}
             acoes={personagens.length < MAX_PERSONAGENS && (
               <button type="button" className="btn-ghost px-3 py-1.5 text-xs"
                       onClick={() => mudar('personagens', [...personagens, { nome: '', descricao: '' }])}>
                 <Plus size={13} /> personagem
               </button>
             )}>
        <p className="text-muted text-[13px] leading-snug">
          Cada personagem ganha uma imagem de referência, que vai em toda cena em que ele aparece: é o que mantém o
          personagem igual de um vídeo para o outro. Gere, olhe e, se não gostar, gere outra. Até {MAX_PERSONAGENS}.
        </p>
        {personagens.length === 0 && (
          <p className="text-sm text-ink2">Sem personagens fixos: o roteiro inventa quem aparece em cada vídeo.</p>
        )}
        <div className="space-y-2.5">
          {personagens.map((p, i) => (
            <PersonagemDoEstilo
              key={p.id || `novo-${i}`}
              personagem={p}
              indice={i}
              miniatura={p.id && p.imagem ? imagens[p.id] : null}
              ocupado={ocupado === i}
              aoMudar={(novo) => mudarPersonagem(i, novo)}
              aoRemover={() => mudar('personagens', personagens.filter((_, j) => j !== i))}
              aoGerar={() => gerar(i)}
              aoEnviar={(arquivo) => enviar(i, arquivo)}
            />
          ))}
        </div>
      </Secao>

      <Secao titulo="a voz e a legenda" icone={Play}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block min-w-0" htmlFor="estilo-voz">
            <span className="eyebrow">voz do narrador</span>
            <select id="estilo-voz" className="input-field mt-1.5" value={spec.voz?.nome || 'Kore'}
                    onChange={(e) => mudarDe('voz', 'nome', e.target.value)}>
              {vozes.map((v) => <option key={v.nome} value={v.nome}>{v.nome} · {v.jeito}</option>)}
            </select>
          </label>
          <Texto id="estilo-jeito" rotulo="jeito de falar (opcional)" max={200} valor={spec.voz?.instrucao}
                 dica="Ex.: conte como uma avó carinhosa" aoMudar={(v) => mudarDe('voz', 'instrucao', v)} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={ouvir} disabled={amostra.carregando}>
            {amostra.carregando ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />} ouvir
          </button>
          {amostra.url && (
            <button type="button" className="btn-quiet px-2.5 py-1.5 text-xs" onClick={() => audio.current?.pause()}>
              <Square size={12} /> parar
            </button>
          )}
          <span className="text-[12px] text-muted">A primeira amostra de cada voz usa uma narração da cota do dia.</span>
          {amostra.url && <audio ref={audio} src={amostra.url} className="hidden" />}
        </div>
        {amostra.erro && <p className="text-sm text-danger">{amostra.erro}</p>}
        <div>
          <p className="eyebrow mb-1.5">legenda</p>
          <SegmentedControl options={LEGENDAS.map((l) => ({ value: l.id, label: l.nome }))}
                            value={spec.legenda?.preset || 'karaoke_fill'}
                            onChange={(v) => mudarDe('legenda', 'preset', v)} columns={4} minColPx={120} size="sm" />
        </div>
      </Secao>

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0">{erro}</span>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={salvar} disabled={salvando || ocupado !== null}>
          {salvando ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} salvar o estilo
        </button>
        {tela.estilo && !sujo && <span className="text-[12px] text-muted">salvo</span>}
      </div>
    </div>
  );
}

export default function EstiloDoCanal({ canal }) {
  const [tela, setTela] = useState(null);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(async () => {
    const r = await lerEstilo(canal.id);
    if (!r.ok) {
      setErro(r);
      return;
    }
    setErro(null);
    setTela(r.data);
  }, [canal.id]);
  useEffect(() => { carregar(); }, [carregar]);

  if (erro) {
    return (
      <div className="card p-6 text-center space-y-2">
        <AlertTriangle size={22} className="mx-auto text-muted" />
        <p className="text-ink text-sm">{erro.motorAntigo ? 'O programa deste computador ainda não cria vídeos por IA.' : erro.erro}</p>
        {erro.motorAntigo && <p className="text-muted text-[13px]">Atualize o programa pelo aviso no topo da página.</p>}
      </div>
    );
  }
  if (tela === null) return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;

  // Gravar (ou gerar uma imagem) devolve o estilo novo; a cota e as chaves
  // vêm do recarregar, que é barato.
  const aoGravar = (dados) => {
    setTela((t) => ({ ...t, ...dados }));
    carregar();
  };
  return <Editor key={tela.estilo?.updated_at || 'novo'} canal={canal} tela={tela} aoGravar={aoGravar} />;
}
