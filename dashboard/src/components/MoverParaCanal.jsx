import React, { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { moverProjeto } from '../lib/canais';
import { usePainel } from '../lib/painel';

// Troca o canal de um projeto: todo projeto de antes dos canais nasceu sem
// nenhum, e é por aqui que ele entra num. Um `<select>` e não um menu
// desenhado à mão: é o controle que o celular já sabe abrir bem.
export default function MoverParaCanal({ jobId, canalId, aoMover, className = '' }) {
  const { canais } = usePainel();
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  if (canais.situacao !== 'ok') return null;

  const trocar = async (e) => {
    const novo = e.target.value || null;
    setSalvando(true);
    setErro(null);
    const r = await moverProjeto(jobId, novo);
    setSalvando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    canais.carregar();
    if (aoMover) aoMover(novo);
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 min-w-0 ${className}`}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <select
        value={canalId || ''}
        onChange={trocar}
        disabled={salvando}
        aria-label="canal do projeto"
        title={erro || 'canal do projeto'}
        className={`bg-transparent text-xs max-w-[11rem] truncate border border-rule2 rounded-full pl-2 pr-6 py-0.5 cursor-pointer hover:border-[color:var(--color-accent)] transition-colors ${erro ? 'text-danger' : 'text-muted'}`}
      >
        <option value="">sem canal</option>
        {canais.canais.map((c) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>
      {salvando && <Loader2 size={12} className="animate-spin text-muted shrink-0" />}
    </span>
  );
}
