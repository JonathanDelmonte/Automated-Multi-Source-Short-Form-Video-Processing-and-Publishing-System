import React, { useState } from 'react';
import { AlertTriangle, Loader2, Scissors, Wand2 } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { situacaoDoVideoLongo } from '../../lib/criacao.js';
import CompilarCortes from './CompilarCortes';
import CriarEpisodio from './CriarEpisodio';

// Criar → Vídeo longo (etapa 7.8): "um vídeo horizontal longo, montado a partir
// dos cortes ou de um roteiro". Dois caminhos na mesma tela: o episódio criado
// por IA (a máquina da 7.7, deitada e mais longa, com a história que continua)
// e a compilação dos cortes que já existem. Os dois vão só para o YouTube e,
// desde a 7.10, para o Bilibili.

const MODOS = [
  { id: 'episodio', icone: Wand2, rotulo: 'episódio criado por IA' },
  { id: 'cortes', icone: Scissors, rotulo: 'compilação dos cortes' },
];

export default function CriarVideoLongo({ canalId, modoInicial = null, projetoInicial = null, aoCriar }) {
  const { configCarregada, videoLongoNoMotor } = useAuth();
  const situacao = situacaoDoVideoLongo({ configCarregada, videoLongoNoMotor });
  const [modo, setModo] = useState(modoInicial === 'cortes' || projetoInicial ? 'cortes' : 'episodio');

  if (situacao === 'carregando') return <Loader2 size={18} className="animate-spin text-muted" aria-label="carregando" />;
  if (situacao === 'motor-antigo') {
    return (
      <p className="flex items-start gap-2 text-sm text-ink2" data-aviso-video-longo-motor>
        <AlertTriangle size={15} className="shrink-0 mt-0.5 text-muted" />
        <span>O programa deste computador ainda não faz vídeo longo. Atualize-o pelo aviso no topo da página.</span>
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div role="tablist" aria-label="como fazer o vídeo longo" className="flex flex-wrap gap-2">
        {MODOS.map(({ id, icone, rotulo }) => {
          const Icone = icone;
          return (
            <button key={id} type="button" role="tab" aria-selected={modo === id} onClick={() => setModo(id)}
                    className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-full border text-sm transition-colors ${
                      modo === id ? 'border-[color:var(--color-accent)] bg-paper3 text-ink' : 'border-rule2 text-muted hover:text-ink2'}`}>
              <Icone size={15} /> {rotulo}
            </button>
          );
        })}
      </div>
      {modo === 'episodio'
        ? <CriarEpisodio canalId={canalId} aoCriar={aoCriar} />
        : <CompilarCortes key={canalId || 'todos'} canalId={canalId} projetoInicial={projetoInicial} aoCriar={aoCriar} />}
    </div>
  );
}
