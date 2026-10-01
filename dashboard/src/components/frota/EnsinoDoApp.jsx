import React, { useRef, useState } from 'react';
import { ArrowLeft, Check, GraduationCap, Home, Loader2, MousePointerClick, Send, Undo2, X } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';
import { acaoNoEnsino, cancelarEnsino } from '../../lib/frotaNoMotor';
import { descricaoDoPasso, pontoNaImagem } from '../../lib/frota.js';

// Ensinar o caminho do post a um app (etapa 7.9, ADR-016). O motor não adivinha
// a tela do Instagram: você mostra uma vez. A tela do celular aparece com o que
// dá para tocar contornado; clique no que você tocaria e o motor toca no
// aparelho e anota. No campo da legenda ele digita um texto de teste. No botão
// de publicar, troque para "marcar o botão de publicar" e clique nele: o motor
// anota SEM tocar -- o vídeo de teste nunca sai.

export default function EnsinoDoApp({ aparelhoId, plataforma, estado: inicial, aoTerminar }) {
  const [estado, setEstado] = useState(inicial);
  const [modo, setModo] = useState('tocar');
  const [trabalhando, setTrabalhando] = useState(false);
  const [erro, setErro] = useState(null);
  const imagem = useRef(null);

  const responder = (r) => {
    if (r.ok) {
      setEstado(r.data);
      setErro(null);
    } else {
      setErro(r.erro);
    }
    return r;
  };

  const clicar = async (evento) => {
    if (!imagem.current || trabalhando || estado.pronto) return;
    const ponto = pontoNaImagem(evento.clientX, evento.clientY, imagem.current.getBoundingClientRect());
    setTrabalhando(true);
    const r = responder(await acaoNoEnsino(aparelhoId, modo === 'publicar' ? 'publicar' : 'tocar', ponto));
    setTrabalhando(false);
    if (r.ok && modo === 'publicar') setModo('tocar');
  };

  const fazer = async (acao, corpo) => {
    setTrabalhando(true);
    const r = responder(await acaoNoEnsino(aparelhoId, acao, corpo));
    setTrabalhando(false);
    return r;
  };

  const salvar = async () => {
    setTrabalhando(true);
    const r = await acaoNoEnsino(aparelhoId, 'salvar', {});
    setTrabalhando(false);
    if (!r.ok) return setErro(r.erro);
    return aoTerminar?.(r.data);
  };

  const cancelar = async () => {
    setTrabalhando(true);
    await cancelarEnsino(aparelhoId);
    setTrabalhando(false);
    aoTerminar?.(null);
  };

  return (
    <section className="card p-4 sm:p-5 space-y-4" data-ensino>
      <div className="flex flex-wrap items-center gap-2">
        <GraduationCap size={16} className="text-ink2" />
        <h2 className="text-ink text-sm font-medium flex items-center gap-1.5">
          ensinando o <IconePlataforma platform={plataforma} size={15} /> {estado.versao ? `(versão ${estado.versao})` : ''}
        </h2>
      </div>
      <ol className="list-decimal pl-5 text-[13px] text-ink2 space-y-1">
        <li>Clique, na imagem, no que você tocaria para postar o vídeo de teste: o motor toca no celular.</li>
        <li>No campo da legenda, clique nele: {estado.digita
          ? 'o motor digita um texto de teste.'
          : 'falta o ADBKeyBoard no celular, então ele só toca (o ensaio vai pedir o teclado).'}</li>
        <li>No botão de publicar, troque para <strong>marcar o botão de publicar</strong> e clique nele. O motor
          anota sem tocar.</li>
      </ol>
      <div className="grid gap-4 md:grid-cols-[minmax(0,16rem)_1fr] items-start">
        <div className="space-y-2">
          <div className="relative mx-auto w-full max-w-[16rem] rounded-[18px] border border-rule bg-paper3 overflow-hidden"
               style={{ aspectRatio: `${estado.largura} / ${estado.altura}` }}>
            <img ref={imagem} src={estado.imagem} alt="tela do celular no ensino"
                 className={`w-full h-full object-fill ${estado.pronto ? '' : 'cursor-crosshair'}`} onClick={clicar} />
            {!estado.pronto && estado.elementos.map((e, i) => (
              <span key={i} aria-hidden="true"
                    className={`pointer-events-none absolute rounded-[3px] border ${
                      e.tipo === 'campo' ? 'border-[color:var(--color-ok)]' : 'border-[color:var(--color-accent)]/70'}`}
                    style={{ left: `${e.x * 100}%`, top: `${e.y * 100}%`, width: `${e.w * 100}%`, height: `${e.h * 100}%` }} />
            ))}
            {trabalhando && (
              <div className="absolute inset-0 grid place-items-center bg-black/30">
                <Loader2 size={18} className="animate-spin text-ink" />
              </div>
            )}
          </div>
          <div className="flex flex-wrap justify-center gap-1.5">
            <button type="button" className="btn-ghost px-2.5 py-1 text-xs" disabled={trabalhando}
                    onClick={() => fazer('tecla', { tecla: 'voltar' })}><ArrowLeft size={13} /> voltar</button>
            <button type="button" className="btn-ghost px-2.5 py-1 text-xs" disabled={trabalhando}
                    onClick={() => fazer('tecla', { tecla: 'inicio' })}><Home size={13} /> início</button>
          </div>
          <p className="text-[11px] text-muted text-center">As teclas não entram no roteiro.</p>
        </div>
        <div className="space-y-3 min-w-0">
          {!estado.pronto && (
            <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="o que o clique faz">
              <button type="button" role="radio" aria-checked={modo === 'tocar'}
                      className={`${modo === 'tocar' ? 'btn-primary' : 'btn-ghost'} px-3 py-1.5 text-xs`}
                      onClick={() => setModo('tocar')}>
                <MousePointerClick size={13} /> tocar
              </button>
              <button type="button" role="radio" aria-checked={modo === 'publicar'}
                      className={`${modo === 'publicar' ? 'btn-primary' : 'btn-ghost'} px-3 py-1.5 text-xs`}
                      onClick={() => setModo('publicar')} data-marcar-publicar>
                <Send size={13} /> marcar o botão de publicar
              </button>
            </div>
          )}
          <div className="space-y-1.5">
            <p className="eyebrow">o roteiro até aqui</p>
            {estado.passos.length ? (
              <ol className="list-decimal pl-5 text-sm text-ink2 space-y-1" data-passos>
                {estado.passos.map((p, i) => <li key={i}>{descricaoDoPasso(p)}</li>)}
              </ol>
            ) : <p className="text-sm text-muted">Nenhum passo ainda.</p>}
          </div>
          {erro && <p className="text-[13px] text-[color:var(--color-danger)]" role="alert">{erro}</p>}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ghost px-3 py-1.5 text-xs" disabled={trabalhando || !estado.passos.length}
                    onClick={() => fazer('desfazer')}><Undo2 size={13} /> desfazer o último</button>
            <button type="button" className="btn-primary px-3 py-1.5 text-xs" disabled={trabalhando || !estado.pronto}
                    onClick={salvar}><Check size={13} /> salvar o roteiro</button>
            <button type="button" className="btn-quiet px-3 py-1.5 text-xs" disabled={trabalhando}
                    onClick={cancelar}><X size={13} /> cancelar</button>
          </div>
          {estado.pronto && (
            <p className="text-[13px] text-ink2">
              Pronto. Salve, e depois ensaie: o ensaio refaz tudo com outro vídeo de teste e para antes de publicar.
              O app ficou na última tela com o vídeo de teste: saia dele sem publicar (descartar).
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
