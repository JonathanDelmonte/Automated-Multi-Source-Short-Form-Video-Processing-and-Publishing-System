import React, { useState } from 'react';
import { CheckCircle2, FlaskConical, GraduationCap, Loader2, Trash2, XCircle } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import { Secao } from '../ui/Pagina';
import { apagarRoteiro, comecarEnsino, ensaiar } from '../../lib/frotaNoMotor';
import { descricaoDoPasso } from '../../lib/frota.js';
import { quando } from '../../lib/publicacoes.js';

// O roteiro de cada app neste aparelho (etapa 7.9): ensinado por você, e o
// último ensaio. O automático só liga com o ensaio passando, e só na versão do
// app em que ele passou -- o app atualizou, ensine e ensaie de novo.

function Ensaio({ roteiro, rodando }) {
  if (rodando) {
    return <span className="badge-warn"><Loader2 size={11} className="animate-spin" /> ensaiando</span>;
  }
  if (roteiro.ensaio_ok === true) return <span className="badge-ok"><CheckCircle2 size={11} /> ensaio passou</span>;
  if (roteiro.ensaio_ok === false) return <span className="badge-danger"><XCircle size={11} /> ensaio não passou</span>;
  return <span className="badge-warn">falta ensaiar</span>;
}

function LinhaDoApp({ aparelho, plataforma, app, aoEnsinar, aoMudar, ocupado }) {
  const roteiro = aparelho.roteiros?.[plataforma];
  const ensaio = aparelho.ensaio?.plataforma === plataforma ? aparelho.ensaio : null;
  const rodando = ensaio?.estado === 'rodando';
  const [trabalhando, setTrabalhando] = useState(false);
  const [erro, setErro] = useState(null);
  const [opcoes, setOpcoes] = useState(null);
  const [componente, setComponente] = useState('');

  const ensinar = async (escolhido) => {
    setTrabalhando(true);
    setErro(null);
    const r = await comecarEnsino(aparelho.id, plataforma, escolhido);
    setTrabalhando(false);
    if (r.ok) {
      setOpcoes(null);
      return aoEnsinar(plataforma, r.data);
    }
    if (r.opcoes?.length) setOpcoes(r.opcoes);
    return setErro(r.erro);
  };

  const fazerEnsaio = async () => {
    setTrabalhando(true);
    setErro(null);
    const r = await ensaiar(aparelho.id, plataforma);
    setTrabalhando(false);
    if (!r.ok) return setErro(r.erro);
    return aoMudar?.();
  };

  const apagar = async () => {
    const r = await apagarRoteiro(aparelho.id, plataforma);
    if (!r.ok) return setErro(r.erro);
    return aoMudar?.();
  };

  return (
    <li className="py-3 space-y-2" data-roteiro={plataforma}>
      <div className="flex flex-wrap items-center gap-2">
        <IconePlataforma platform={plataforma} size={16} />
        <span className="text-sm text-ink">{app?.versao ? `versão ${app.versao}` : 'app'}</span>
        {roteiro ? <Ensaio roteiro={roteiro} rodando={rodando} /> : <span className="readout">sem roteiro</span>}
        {roteiro && app?.versao && roteiro.versao && app.versao !== roteiro.versao && (
          <span className="badge-warn">o app mudou de versão: ensine de novo</span>
        )}
      </div>
      {roteiro && (
        <details>
          <summary className="text-[12px] text-muted cursor-pointer">
            {roteiro.passos.length} passos, ensinados {quando(roteiro.ensinado_em)}
          </summary>
          <ol className="list-decimal pl-5 mt-1.5 text-[13px] text-ink2 space-y-0.5">
            {roteiro.passos.map((p, i) => <li key={i}>{descricaoDoPasso(p)}</li>)}
          </ol>
        </details>
      )}
      {(ensaio?.detalhe || roteiro?.ensaio_detalhe) && !rodando && (
        <p className="text-[12px] text-ink2">{ensaio?.detalhe || roteiro.ensaio_detalhe}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-ghost px-3 py-1.5 text-xs" disabled={trabalhando || !!ocupado || rodando}
                onClick={() => ensinar(null)}>
          {trabalhando ? <Loader2 size={13} className="animate-spin" /> : <GraduationCap size={13} />}
          {roteiro ? 'ensinar de novo' : 'ensinar'}
        </button>
        {roteiro && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" disabled={trabalhando || !!ocupado || rodando}
                  onClick={fazerEnsaio}>
            <FlaskConical size={13} /> ensaiar
          </button>
        )}
        {roteiro && (
          <button type="button" className="btn-quiet px-3 py-1.5 text-xs" disabled={rodando} onClick={apagar}>
            <Trash2 size={13} /> apagar o roteiro
          </button>
        )}
      </div>
      {opcoes && (
        <div className="flex flex-wrap items-center gap-2">
          <select className="input-field py-1.5 text-xs min-w-0 flex-1" value={componente}
                  onChange={(e) => setComponente(e.target.value)} aria-label="tela do app que recebe o vídeo">
            <option value="">qual tela recebe o post?</option>
            {opcoes.map((o) => <option key={o} value={o}>{o.split('/')[1]}</option>)}
          </select>
          <button type="button" className="btn-primary px-3 py-1.5 text-xs" disabled={!componente || trabalhando}
                  onClick={() => ensinar(componente)}>ensinar por esta</button>
        </div>
      )}
      {erro && <p className="text-[12px] text-[color:var(--color-danger)]" role="alert">{erro}</p>}
    </li>
  );
}

export default function RoteirosDoAparelho({ aparelho, estado, plataformas, aoEnsinar, aoMudar }) {
  // Os apps que importam aqui: os instalados que a frota sabe abrir, os que já
  // têm roteiro e os das contas deste aparelho.
  const lista = (plataformas || []).filter((p) => estado?.apps?.[p] || aparelho.roteiros?.[p]
    || aparelho.contas.some((c) => c.platform === p));
  return (
    <Secao titulo="ensinar e ensaiar cada app" icone={GraduationCap}>
      <p className="text-[13px] text-muted leading-snug">
        Para o motor publicar sozinho, você ensina o caminho do post uma vez, pela tela do celular aqui no painel, e
        um ensaio refaz tudo com um vídeo de teste, parando antes de publicar. Sem ensaio passando, o vídeo só é
        entregue. Para o motor digitar a legenda (acento e emoji), o celular precisa do teclado{' '}
        <a href="https://github.com/senzhk/ADBKeyBoard" target="_blank" rel="noreferrer"
           className="underline underline-offset-2 text-ink2">ADBKeyBoard</a>.
      </p>
      <ul className="divide-y divide-[color:var(--color-rule)]">
        {lista.map((p) => (
          <LinhaDoApp key={p} aparelho={aparelho} plataforma={p} app={estado?.apps?.[p]}
                      aoEnsinar={aoEnsinar} aoMudar={aoMudar} ocupado={aparelho.ocupado} />
        ))}
        {!lista.length && (
          <li className="py-2 text-sm text-muted">
            {estado?.no_ar === false
              ? 'O aparelho está fora do ar: os apps aparecem quando ele voltar.'
              : 'Nenhum app de plataforma instalado neste aparelho.'}
          </li>
        )}
      </ul>
    </Secao>
  );
}
