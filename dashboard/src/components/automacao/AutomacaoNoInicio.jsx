import React, { useEffect, useState } from 'react';
import { ArrowRight, Bot, ShieldCheck } from 'lucide-react';
import AvatarDoCanal from '../ui/AvatarDoCanal';
import { lerAutomacao } from '../../lib/automacao';
import { usePainel } from '../../lib/painel';
import { hrefDe } from '../../lib/rota';

// A automação no Início (etapa 7.5): o que espera a sua aprovação e o que cada
// receita ligada está fazendo. Sem receita ligada e sem nada esperando, não
// ocupa lugar nenhum.
export default function AutomacaoNoInicio() {
  const { canais } = usePainel();
  const [dados, setDados] = useState(null);

  useEffect(() => {
    let vivo = true;
    lerAutomacao().then((r) => { if (vivo && r.ok) setDados(r.data); });
    return () => { vivo = false; };
  }, []);

  if (!dados) return null;
  const esperando = Object.entries(dados.esperando_aprovacao || {}).filter(([, n]) => n > 0);
  const ligadas = (dados.receitas || []).filter((r) => r.ativa);
  if (esperando.length === 0 && ligadas.length === 0) return null;

  return (
    <section className="space-y-3">
      <p className="eyebrow">automação</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {esperando.map(([canalId, n]) => {
          const canal = canais.porId[canalId];
          return (
            <a key={`aprovar-${canalId}`} href={hrefDe(`/canais/${canalId}/automacao`)}
               className="card p-4 flex items-center gap-3 group hover:border-rule2 transition-colors min-w-0">
              <span className="w-9 h-9 rounded-input bg-paper3 flex items-center justify-center shrink-0 text-brass">
                <ShieldCheck size={17} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink">
                  {n === 1 ? '1 corte esperando a sua aprovação' : `${n} cortes esperando a sua aprovação`}
                </span>
                <span className="block text-xs text-muted truncate">{canal?.name || 'canal'}</span>
              </span>
              <ArrowRight size={15} className="text-muted group-hover:text-ink shrink-0 transition-colors" />
            </a>
          );
        })}
        {ligadas.map((r) => {
          const canal = canais.porId[r.channel_id];
          if (!canal) return null;
          return (
            <a key={`receita-${r.channel_id}`} href={hrefDe(`/canais/${r.channel_id}/automacao`)}
               className="card p-4 flex items-center gap-3 group hover:border-rule2 transition-colors min-w-0">
              <AvatarDoCanal canal={canal} size={36} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm text-ink truncate">{canal.name}</span>
                <span className="block text-xs text-muted truncate">
                  <Bot size={12} className="inline -mt-0.5 mr-1" />
                  {r.situacao || 'receita ligada; esperando a primeira volta do motor'}
                </span>
              </span>
              <ArrowRight size={15} className="text-muted group-hover:text-ink shrink-0 transition-colors" />
            </a>
          );
        })}
      </div>
    </section>
  );
}
