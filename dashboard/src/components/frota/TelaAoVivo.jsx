import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, Home, Loader2, Pause, Play, Sun } from 'lucide-react';
import { apertarTecla, lerTela, tocarNaTela } from '../../lib/frotaNoMotor';
import { pontoNaImagem } from '../../lib/frota.js';

// A tela do celular ao vivo, e o controle remoto dele (etapa 7.9): uma imagem
// a cada poucos segundos enquanto a aba está à vista, e um toque na imagem vira
// um toque no aparelho. É você mexendo no seu celular de longe -- o que serve,
// sobretudo, ao celular em nuvem, que não dá para pegar na mão. Enquanto o
// aparelho publica, aprende ou ensaia, o motor recusa o toque.

const RECARGA_MS = 3_000;

export default function TelaAoVivo({ aparelhoId, ocupado }) {
  const [tela, setTela] = useState(null);
  const [erro, setErro] = useState(null);
  const [pausada, setPausada] = useState(false);
  const [mexendo, setMexendo] = useState(false);
  const imagem = useRef(null);

  const carregar = useCallback(async () => {
    const r = await lerTela(aparelhoId);
    if (r.ok) {
      setTela(r.data);
      setErro(null);
    } else {
      setErro(r.erro);
    }
  }, [aparelhoId]);

  useEffect(() => {
    if (pausada) return undefined;
    carregar();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') carregar();
    }, RECARGA_MS);
    return () => clearInterval(id);
  }, [carregar, pausada]);

  const responder = (r) => {
    if (r.ok) {
      setTela(r.data);
      setErro(null);
    } else {
      setErro(r.erro);
    }
  };

  const tocar = async (evento) => {
    if (!imagem.current || mexendo) return;
    const { x, y } = pontoNaImagem(evento.clientX, evento.clientY, imagem.current.getBoundingClientRect());
    setMexendo(true);
    responder(await tocarNaTela(aparelhoId, x, y));
    setMexendo(false);
  };

  const tecla = async (nome) => {
    setMexendo(true);
    responder(await apertarTecla(aparelhoId, nome));
    setMexendo(false);
  };

  return (
    <div className="space-y-2" data-tela-ao-vivo>
      <div className="relative mx-auto w-full max-w-[16rem] aspect-[9/19] rounded-[18px] border border-rule bg-paper3 overflow-hidden">
        {tela ? (
          <img ref={imagem} src={tela.imagem} alt="tela do celular agora"
               className={`w-full h-full object-contain ${ocupado ? 'cursor-not-allowed' : 'cursor-crosshair'}`}
               onClick={ocupado ? undefined : tocar} />
        ) : (
          <div className="absolute inset-0 grid place-items-center text-muted text-xs px-4 text-center">
            {erro || <Loader2 size={16} className="animate-spin" />}
          </div>
        )}
        {mexendo && (
          <div className="absolute inset-0 grid place-items-center bg-black/30">
            <Loader2 size={18} className="animate-spin text-ink" />
          </div>
        )}
      </div>
      <div className="flex flex-wrap justify-center gap-1.5">
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => tecla('voltar')}
                disabled={mexendo || !!ocupado} title="voltar"><ArrowLeft size={13} /> voltar</button>
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => tecla('inicio')}
                disabled={mexendo || !!ocupado} title="início"><Home size={13} /> início</button>
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => tecla('acordar')}
                disabled={mexendo || !!ocupado} title="acender a tela"><Sun size={13} /> acender</button>
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={() => setPausada(!pausada)}
                title={pausada ? 'voltar a atualizar' : 'parar de atualizar'}>
          {pausada ? <Play size={13} /> : <Pause size={13} />} {pausada ? 'ao vivo' : 'pausar'}
        </button>
      </div>
      <p className="text-[11px] text-muted text-center">
        {ocupado ? `O aparelho está ${ocupado}: o toque espera.` : 'Toque na imagem para tocar no celular.'}
        {tela && erro ? ` ${erro}` : ''}
      </p>
    </div>
  );
}
