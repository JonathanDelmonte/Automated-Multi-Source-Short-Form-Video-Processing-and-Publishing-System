import React, { useState, useEffect } from 'react';
import { Timer, Loader2, Info } from 'lucide-react';
import { apiFetch } from '../lib/api';

// "Onde vai o tempo" (Fase 5, bloco 5.3).
//
// O `job_metrics` mede por estágio desde a Fase 0.5 e o bloco 3.3 grava em
// `jobs.timings_json` — mas ninguém lia isso entre jobs: cada execução
// imprimia o próprio resumo no log e o número morria ali.
//
// **Mostra, não conserta.** A tentação diante de "está lento" é abrir o código
// e procurar o culpado. As observações que o backend devolve apontam para
// coisas verificáveis já escritas no repositório — nunca para uma conclusão
// que ninguém mediu.

const MINUTO = 60;

function duracao(segundos) {
  if (!segundos) return '—';
  if (segundos < MINUTO) return `${Math.round(segundos)}s`;
  const min = Math.floor(segundos / MINUTO);
  if (min < 60) return `${min}min`;
  return `${Math.floor(min / 60)}h${String(min % 60).padStart(2, '0')}`;
}

const NOMES = {
  '01_ingest': 'baixar',
  '02_probe': 'preparar áudio',
  '03_transcribe': 'transcrever',
  '04_detect': 'escolher momentos',
  '05_06_render': 'cortar e renderizar',
};

export default function OndeVaiOTempo() {
  const [dados, setDados] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch('/api/tempo');
        if (!res.ok) throw new Error('falhou');
        setDados(await res.json());
      } catch {
        setErro('Não consegui ler o relatório de tempo.');
      }
    })();
  }, []);

  if (erro) return <p className="text-danger text-[13px]">{erro}</p>;
  if (!dados) return <Loader2 size={16} className="animate-spin text-muted" />;
  if (!dados.jobs) {
    return (
      <p className="text-muted text-[13px]">
        Nenhum job medido ainda. O relatório aparece depois do primeiro vídeo.
      </p>
    );
  }

  const fator = dados.fator_tempo_real;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline gap-3 flex-wrap">
        {fator && (
          <span className="text-ink font-display text-2xl">{fator.toFixed(1)}×</span>
        )}
        <span className="text-muted text-[13px]">
          {fator
            ? 'de processamento para cada minuto de vídeo'
            : 'sem a duração da fonte não dá para calcular o fator'}
        </span>
        <span className="text-muted text-xs ml-auto">
          {dados.jobs} job{dados.jobs === 1 ? '' : 's'} · {duracao(dados.wall_seconds)} no total
        </span>
      </div>

      {/* Uma barra por estágio, na ordem em que acontecem — ler na ordem do
          pipeline é o que deixa ver onde ele engasga. */}
      <ul className="space-y-1.5">
        {dados.estagios.map((e) => (
          <li key={e.estagio} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2 text-[13px]">
              <span className="text-ink2">{NOMES[e.estagio] || e.estagio}</span>
              <span className="text-muted text-xs">
                {duracao(e.seconds)}
                {e.fatia != null && ` · ${Math.round(e.fatia * 100)}%`}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-paper3 overflow-hidden">
              <div
                className="h-full bg-brass"
                style={{ width: `${Math.round((e.fatia || 0) * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      {dados.observacoes?.length > 0 && (
        <ul className="space-y-1.5 pt-1">
          {dados.observacoes.map((o, i) => (
            <li key={i} className="text-muted text-[12px] leading-snug flex gap-1.5">
              <Info size={13} className="mt-0.5 shrink-0" />
              <span>{o}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CartaoDeTempo() {
  return (
    <section className="card p-4 space-y-3">
      <h3 className="text-ink text-sm font-medium inline-flex items-center gap-1.5">
        <Timer size={14} /> onde vai o tempo
      </h3>
      <OndeVaiOTempo />
    </section>
  );
}
