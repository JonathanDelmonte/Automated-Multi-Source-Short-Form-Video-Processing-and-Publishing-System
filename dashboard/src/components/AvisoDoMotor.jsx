import React, { useEffect, useState } from 'react';
import { RefreshCw, X } from 'lucide-react';
import { maisNova, versaoPublicada } from '../lib/ajudante';

// "O motor deste computador está atrás do site" (Fase 6.2).
//
// Só no Docker. O site é publicado a cada envio para a `main`; o motor do
// Docker só muda com o `atalhos\atualizar.bat`, e o site novo falando com um
// motor velho é o tipo de defeito que parece bug e é versão. O ajudante se
// atualiza sozinho, e o motor rodado direto do código é de quem o está
// escrevendo -- nos dois o aviso seria ruído.
//
// Fechar vale até sair uma versão mais nova que a que foi dispensada: o aviso
// que volta a cada F5 vira paisagem, e o que nunca volta esconde o problema.
const CHAVE_FECHADO = 'cortes_aviso_motor_fechado';

const lerFechado = () => {
  try {
    return localStorage.getItem(CHAVE_FECHADO);
  } catch {
    return null;
  }
};

export default function AvisoDoMotor({ motor }) {
  const [publicada, setPublicada] = useState(null);
  const [fechado, setFechado] = useState(lerFechado);
  const noDocker = motor?.origem === 'docker' && !!motor?.versao;

  useEffect(() => {
    if (!noDocker) return undefined;
    let vivo = true;
    versaoPublicada().then((v) => { if (vivo) setPublicada(v); });
    return () => { vivo = false; };
  }, [noDocker]);

  if (!noDocker || !maisNova(publicada, motor.versao)) return null;
  if (fechado && !maisNova(publicada, fechado)) return null;

  const fechar = () => {
    try {
      localStorage.setItem(CHAVE_FECHADO, publicada);
    } catch { /* fecha só nesta aba */ }
    setFechado(publicada);
  };

  return (
    <div className="mx-3 sm:mx-6 mt-3 px-3.5 sm:px-4 py-3 bg-paper2 border border-rule rounded-card flex items-start justify-between gap-3 shrink-0 animate-fade">
      <div className="flex items-start gap-2.5 text-sm text-ink2 min-w-0">
        <RefreshCw size={16} className="shrink-0 text-brass mt-0.5" />
        <div className="min-w-0">
          <span className="font-medium text-ink">O motor deste computador está atrás do site.</span>{' '}
          <span className="text-muted">
            Ele está na versão {motor.versao}, e a mais nova é a {publicada}. Para atualizar,
            rode <code className="text-ink2">atalhos\atualizar.bat</code> na pasta do projeto.
          </span>
        </div>
      </div>
      <button
        onClick={fechar}
        aria-label="Dispensar o aviso"
        className="p-1 rounded-input text-muted hover:text-ink transition-colors shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}
