import React, { useCallback, useEffect, useState } from 'react';
import { Loader2, Power, Smartphone } from 'lucide-react';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import AdicionarAparelho from '../components/frota/AdicionarAparelho';
import AjudaDoAdb from '../components/frota/AjudaDoAdb';
import CartaoDoAparelho from '../components/frota/CartaoDoAparelho';
import DetalheDoAparelho from '../components/frota/DetalheDoAparelho';
import LigarFrota from '../components/frota/LigarFrota';
import LimitesDaFrota from '../components/frota/LimitesDaFrota';
import { lerFrota, ligarFrota } from '../lib/frotaNoMotor';

// A frota de aparelhos (etapa 7.9, ADR-016): celulares ligados a este
// computador, pelo cabo, pela rede de casa ou em nuvem, cada um com as contas
// que moram nele. O padrão é entregar -- o vídeo abre no app e a pessoa toca em
// publicar --, e o motor só toca no botão numa conta que consentiu, depois de
// a pessoa ensinar o caminho e um ensaio passar. O Instagram é o que mais vai
// sair por aqui (o autor, 26-set-2026).

const RECARGA_MS = 10_000;

export default function Frota({ aparelho }) {
  const [frota, setFrota] = useState(null);
  const [erro, setErro] = useState(null);
  const [desligando, setDesligando] = useState(false);

  const carregar = useCallback(async () => {
    const r = await lerFrota();
    if (!r.ok) return setErro(r);
    setErro(null);
    return setFrota(r.data);
  }, []);

  useEffect(() => {
    carregar();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') carregar();
    }, RECARGA_MS);
    return () => clearInterval(id);
  }, [carregar]);

  if (aparelho) return <DetalheDoAparelho key={aparelho} id={aparelho} frota={frota} aoMudar={carregar} />;

  const ligar = async () => {
    const r = await ligarFrota(true, true);
    if (r.ok) await carregar();
    return r;
  };

  const desligar = async () => {
    if (!window.confirm('Desligar a frota? Os aparelhos e as contas ficam guardados, mas nada sai por eles até ligar de novo.')) return;
    setDesligando(true);
    await ligarFrota(false);
    setDesligando(false);
    carregar();
  };

  const ligada = frota?.ligada;
  const online = (frota?.aparelhos || []).length;

  return (
    <Pagina largura="larga">
      <CabecalhoDaPagina
        rotulo="frota"
        titulo="Frota de aparelhos"
        descricao="Celulares, físicos ou em nuvem, cada um postando pelos aplicativos das contas que moram nele."
        acoes={ligada ? (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={desligar} disabled={desligando}>
            {desligando ? <Loader2 size={13} className="animate-spin" /> : <Power size={13} />} desligar a frota
          </button>
        ) : null}
      />

      {erro && (
        <section className="card p-5 text-sm text-ink2" role="alert">
          {erro.motorAntigo
            ? 'O programa deste computador é de antes da frota. Atualize-o pelo aviso no topo da página.'
            : erro.erro}
        </section>
      )}

      {!frota && !erro && (
        <div className="grid place-items-center py-16 text-muted"><Loader2 size={18} className="animate-spin" /></div>
      )}

      {frota && !ligada && <LigarFrota aoLigar={ligar} />}

      {frota && ligada && (
        <>
          <AjudaDoAdb adb={frota.adb} />
          <section className="space-y-3">
            <p className="eyebrow flex items-center gap-1.5">
              <Smartphone size={12} /> {online ? `${online} ${online === 1 ? 'aparelho' : 'aparelhos'} na frota` : 'nenhum aparelho ainda'}
            </p>
            {online > 0 && (
              <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,17rem),1fr))]" data-grade-da-frota>
                {frota.aparelhos.map((a) => <CartaoDoAparelho key={a.id} aparelho={a} />)}
              </div>
            )}
          </section>
          {frota.adb?.alcancado && <AdicionarAparelho vistos={frota.vistos || []} aoMudar={carregar} />}
        </>
      )}

      {frota && <LimitesDaFrota limite={frota.limite?.maximo} />}
    </Pagina>
  );
}
