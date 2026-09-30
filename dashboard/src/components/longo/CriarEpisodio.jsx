import React, { useEffect, useState } from 'react';
import { AlertTriangle, BookOpen, Loader2, Palette, Wand2 } from 'lucide-react';
import {
  DURACAO_LONGA, HISTORIA_MAX, cenasDoLongo, chaveDaHistoria, corpoDoEpisodio,
  fraseDaCotaDoEpisodio, fraseDaHistoria, nomeDaHistoria, resumoDoEstilo,
} from '../../lib/criacao.js';
import { criarVideo, lerEstilo, lerHistorias } from '../../lib/criacaoNoMotor';
import { hrefDe, ir } from '../../lib/rota';

// O episódio longo por IA (etapa 7.8): a mesma máquina do vídeo curto, deitada,
// de 2 a 10 minutos, no estilo salvo no canal. A história é opcional: com ela,
// o episódio novo lê o resumo dos anteriores e continua de onde o último parou.
// A cota do dia é conferida pela DURAÇÃO escolhida, antes do clique.

const AVULSO = '';
const NOVA = '__nova__';

export default function CriarEpisodio({ canalId, aoCriar }) {
  const [tela, setTela] = useState(null);
  const [historias, setHistorias] = useState([]);
  const [erro, setErro] = useState(null);
  const [minutos, setMinutos] = useState(3);
  const [escolha, setEscolha] = useState(AVULSO);
  const [nomeNovo, setNomeNovo] = useState('');
  const [ideia, setIdeia] = useState('');
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    let vivo = true;
    setTela(null);
    setErro(null);
    if (!canalId) return undefined;
    Promise.all([lerEstilo(canalId), lerHistorias(canalId)]).then(([estilo, lista]) => {
      if (!vivo) return;
      if (!estilo.ok) {
        setErro(estilo.erro);
        return;
      }
      setTela(estilo.data);
      setHistorias(lista.ok ? lista.data.historias || [] : []);
    });
    return () => { vivo = false; };
  }, [canalId]);

  if (!canalId) {
    return <p className="text-sm text-ink2">Escolha o canal: o episódio sai no estilo que está salvo nele.</p>;
  }
  if (tela === null && !erro) return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;

  const spec = tela?.estilo?.spec;
  const nome = escolha === NOVA ? nomeDaHistoria(nomeNovo) : (escolha || '');
  // Um nome "novo" igual ao de uma história que existe continua aquela: é o
  // que o motor faz, e a tela diz antes do clique.
  const jaExiste = escolha === NOVA && nome
    ? historias.find((h) => chaveDaHistoria(h.nome) === chaveDaHistoria(nome)) : null;
  const historia = jaExiste
    || (escolha && escolha !== NOVA ? historias.find((h) => h.nome === escolha) : null);
  const cota = tela ? fraseDaCotaDoEpisodio(tela.cota, minutos) : null;
  const esperando = historia && historia.ultimo && !historia.ultimo.pronto;
  const bloqueio = tela?.pode_criar_episodio
    || (cota && !cota.ok ? cota.texto : null)
    || (esperando ? fraseDaHistoria(historia) : null)
    || (escolha === NOVA && !nome ? 'Dê um nome à história nova.' : null);

  const criar = async () => {
    setEnviando(true);
    setErro(null);
    const r = await criarVideo(corpoDoEpisodio({ canalId, ideia, minutos, historia: nome }));
    setEnviando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    if (aoCriar) aoCriar(r.data.job_id);
    ir(`/projetos/${r.data.job_id}`);
  };

  return (
    <div className="space-y-4" data-criar-episodio>
      {tela && (
        <p className="flex items-start gap-2 text-sm text-ink2 min-w-0">
          <Palette size={15} className="shrink-0 mt-0.5 text-muted" />
          <span className="min-w-0">
            {spec ? resumoDoEstilo(spec, { duracao: false }) : 'Este canal ainda não tem estilo.'}{' '}
            <a href={hrefDe(`/canais/${canalId}/criar`)} className="text-muted underline underline-offset-2 hover:text-ink2">
              {spec ? 'mudar o estilo' : 'configurar o estilo'}
            </a>
          </span>
        </p>
      )}

      <label className="block" htmlFor="episodio-minutos">
        <span className="eyebrow">duração: {minutos} minutos ({cenasDoLongo(minutos * 60)} cenas)</span>
        <input id="episodio-minutos" type="range" className="w-full mt-2 accent-[color:var(--color-accent)]"
               min={DURACAO_LONGA.min / 60} max={DURACAO_LONGA.max / 60} step={1} value={minutos}
               onChange={(e) => setMinutos(Number(e.target.value))} />
      </label>

      <div className="space-y-2">
        <label className="block" htmlFor="episodio-historia">
          <span className="eyebrow">história</span>
          <select id="episodio-historia" className="input-field mt-1.5" value={escolha}
                  onChange={(e) => setEscolha(e.target.value)}>
            <option value={AVULSO}>episódio avulso</option>
            {historias.map((h) => (
              <option key={h.nome} value={h.nome}>
                {h.nome} — {h.episodios} episódio{h.episodios === 1 ? '' : 's'}
              </option>
            ))}
            <option value={NOVA}>começar uma história nova…</option>
          </select>
        </label>
        {escolha === NOVA && (
          <input className="input-field" maxLength={HISTORIA_MAX} value={nomeNovo} aria-label="nome da história nova"
                 onChange={(e) => setNomeNovo(e.target.value)} placeholder="Ex.: A Lulu na floresta" />
        )}
        <p className="flex items-start gap-2 text-[12px] text-muted leading-snug">
          <BookOpen size={13} className="shrink-0 mt-0.5" />
          <span>
            {jaExiste
              ? `Essa história já existe. ${fraseDaHistoria(jaExiste)}`
              : escolha === NOVA
                ? (nome ? `Este será o episódio 1 de “${nome}”.` : 'O episódio 1 apresenta o mundo e os personagens.')
                : fraseDaHistoria(historia)}
          </span>
        </p>
      </div>

      <label className="block" htmlFor="episodio-ideia">
        <span className="eyebrow">sobre o que é este episódio? (opcional)</span>
        <textarea id="episodio-ideia" className="input-field mt-1.5 min-h-[4.5rem]" maxLength={500} value={ideia}
                  onChange={(e) => setIdeia(e.target.value)}
                  placeholder={historia ? 'Sem ideia, a história continua de onde parou.' : 'Ex.: a Lulu se perde na floresta e faz um amigo'} />
      </label>

      {cota && (
        <p className={`text-[12px] leading-snug ${cota.ok ? 'text-muted' : 'text-danger'}`} data-cota-do-episodio>
          {cota.texto}
        </p>
      )}
      {bloqueio && (!cota || cota.ok || bloqueio !== cota.texto) && (
        <p className="flex items-start gap-2 text-sm text-danger" data-bloqueio-do-episodio>
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0">{bloqueio}</span>
        </p>
      )}
      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0 break-words">{erro}</span>
        </p>
      )}

      <button type="button" className="btn-primary px-4 py-2.5 text-sm w-full sm:w-auto" onClick={criar}
              disabled={!tela || Boolean(bloqueio) || enviando}>
        {enviando ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />} criar o episódio
      </button>
      <p className="text-[12px] text-muted leading-snug">
        Horizontal, com capítulos na descrição: ele vai só para o YouTube. A narração sai em blocos de uns
        dois minutos e meio, cada um uma chamada da cota de voz do dia. Um episódio de 5 minutos leva uns
        15 a 30 minutos neste computador.
      </p>
    </div>
  );
}
