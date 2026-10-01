import React, { useState } from 'react';
import { AlertTriangle, Check, Copy } from 'lucide-react';
import { INSTALAR_ADB, ajudaDoAdb } from '../../lib/frota.js';

// Quando o motor não alcança o servidor do adb: o que fazer, conforme ele roda
// no Docker (o adb é o do Windows) ou no ajudante (o desta máquina).
export default function AjudaDoAdb({ adb }) {
  const [copiado, setCopiado] = useState(false);
  const ajuda = ajudaDoAdb(adb);
  if (!ajuda) return null;

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(INSTALAR_ADB);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1800);
    } catch {
      // Sem área de transferência: o comando está escrito na tela.
    }
  };

  return (
    <section className="card p-4 sm:p-5 space-y-3 border-[color:var(--color-warn)]" data-ajuda-do-adb>
      <p className="text-ink text-sm font-medium flex items-center gap-2">
        <AlertTriangle size={15} className="text-[color:var(--color-warn)] shrink-0" /> {ajuda.titulo}
      </p>
      <ol className="list-decimal pl-5 space-y-1.5 text-sm text-ink2">
        {ajuda.passos.map((passo) => <li key={passo}>{passo}</li>)}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <code className="readout bg-paper3 rounded-input px-2.5 py-1.5 break-all">{INSTALAR_ADB}</code>
        <button type="button" className="btn-ghost px-2.5 py-1 text-xs" onClick={copiar}>
          {copiado ? <Check size={13} /> : <Copy size={13} />} {copiado ? 'copiado' : 'copiar'}
        </button>
      </div>
      {adb?.erro && <p className="text-[11px] text-muted break-all">o motor tentou {adb.endereco}: {adb.erro}</p>}
    </section>
  );
}
