import React from 'react';
import { ArrowRight, Film, ListVideo, Scissors, Wand2 } from 'lucide-react';
import { hrefDe } from '../lib/rota';

// O que dá para criar (etapa 7.1). Os cortes de vídeo real já funcionam; os
// outros três têm o lugar marcado e dizem o que vão fazer, cada um com a etapa
// do plano em que chega (`docs/PLANO-DA-PLATAFORMA.md`). Cortes de vídeo real e
// vídeo criado por IA são coisas separadas, e todo canal pode ter os dois
// (o autor, 26-set-2026).
const TIPOS = [
  {
    id: 'cortes',
    icone: Scissors,
    titulo: 'Cortes de um vídeo',
    texto: 'Cole um link ou envie um vídeo: a IA acha os melhores momentos e entrega cortes verticais com legenda e gancho.',
  },
  {
    id: 'ia',
    icone: Wand2,
    titulo: 'Vídeo criado por IA',
    texto: 'Roteiro, cenas e narração de uma história curta, no estilo que você salvar no canal. O estilo nunca é deduzido do nicho: quem configura é você.',
    etapa: '7.7',
  },
  {
    id: 'serie',
    icone: ListVideo,
    titulo: 'Série em partes',
    texto: 'Um vídeo longo sem direitos autorais, como uma live ou um filme antigo, vira parte 1, 2, 3, publicadas em sequência.',
    etapa: '7.6',
  },
  {
    id: 'longo',
    icone: Film,
    titulo: 'Vídeo longo',
    texto: 'Um vídeo horizontal longo, montado a partir dos cortes ou de um roteiro.',
    etapa: '7.8',
  },
];

export default function TiposDeCriacao({ canalId = null }) {
  const sufixo = canalId ? `?canal=${encodeURIComponent(canalId)}` : '';
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {TIPOS.map(({ id, icone, titulo, texto, etapa }) => {
        const Icone = icone;
        const pronto = !etapa;
        const miolo = (
          <>
            <div className="flex items-start justify-between gap-3">
              <span className={`w-10 h-10 rounded-input flex items-center justify-center shrink-0 ${pronto ? 'bg-brass text-brassink' : 'bg-paper3 text-muted'}`}>
                <Icone size={19} />
              </span>
              {pronto
                ? <ArrowRight size={17} className="text-muted group-hover:text-ink transition-colors" />
                : <span className="readout">em breve · {etapa}</span>}
            </div>
            <div>
              <p className={`font-medium ${pronto ? 'text-ink' : 'text-ink2'}`}>{titulo}</p>
              <p className="text-muted text-[13px] leading-snug mt-1">{texto}</p>
            </div>
          </>
        );
        return pronto ? (
          <a key={id} href={hrefDe(`/criar/${id}${sufixo}`)} className="card p-4 sm:p-5 flex flex-col gap-3 group hover:border-rule2 transition-colors">
            {miolo}
          </a>
        ) : (
          <div key={id} className="card p-4 sm:p-5 flex flex-col gap-3 opacity-80" aria-disabled="true">
            {miolo}
          </div>
        );
      })}
    </div>
  );
}
