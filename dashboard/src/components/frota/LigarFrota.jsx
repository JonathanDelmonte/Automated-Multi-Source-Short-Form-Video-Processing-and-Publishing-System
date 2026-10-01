import React, { useState } from 'react';
import { Loader2, Power, Smartphone } from 'lucide-react';
import IconePlataforma from '../ui/IconePlataforma';

// A frota nasce desligada (ADR-016): ligar é dizer que leu os limites. O
// botão só acende com a caixa marcada -- e o motor confere de novo.
export default function LigarFrota({ aoLigar }) {
  const [entendi, setEntendi] = useState(false);
  const [ligando, setLigando] = useState(false);
  const [erro, setErro] = useState(null);

  const ligar = async () => {
    setLigando(true);
    setErro(null);
    const r = await aoLigar();
    setLigando(false);
    if (!r.ok) setErro(r.erro);
  };

  return (
    <section className="card p-5 sm:p-6 space-y-4" data-ligar-frota>
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-paper3 grid place-items-center shrink-0">
          <Smartphone size={18} className="text-ink2" />
        </span>
        <div className="min-w-0 space-y-1.5">
          <h2 className="text-ink text-base font-medium">A frota está desligada</h2>
          <p className="text-muted text-sm leading-relaxed">
            Com ela ligada, celulares ligados a este computador (pelo cabo, pela rede de casa ou em nuvem) recebem os
            cortes das contas que moram neles, na hora da agenda. O Instagram é o que mais vai sair por aqui
            <IconePlataforma platform="instagram" size={14} className="inline-block align-text-bottom mx-1" />.
          </p>
          <p className="text-muted text-sm leading-relaxed">
            Antes de ligar, leia os limites logo abaixo: eles valem para todo aparelho e toda conta.
          </p>
        </div>
      </div>
      <label className="flex items-start gap-2.5 text-sm text-ink2 cursor-pointer">
        <input type="checkbox" className="mt-1 accent-[color:var(--color-accent)]" checked={entendi}
               onChange={(e) => setEntendi(e.target.checked)} data-entendi />
        <span>
          Li os limites. Sei que as plataformas podem punir a conta por publicação automatizada, e que o motor só
          publica sozinho numa conta em que eu der o consentimento.
        </span>
      </label>
      {erro && <p className="text-sm text-[color:var(--color-danger)]" role="alert">{erro}</p>}
      <button type="button" className="btn-primary px-4 py-2 text-sm" disabled={!entendi || ligando} onClick={ligar}>
        {ligando ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />} ligar a frota
      </button>
    </section>
  );
}
