import React, { useRef } from 'react';
import { ImageUp, Loader2, Trash2, UserRound, Wand2 } from 'lucide-react';

// Um personagem do estilo (etapa 7.7): nome, como ele é e a imagem de
// referência. A imagem vai para o modelo em toda cena em que ele aparece -- é
// ela que faz o segundo vídeo sair com o MESMO personagem (ADR-013). Por isso a
// pessoa gera, olha e, se não gostar, gera outra; ou manda um desenho dela.

export default function PersonagemDoEstilo({
  personagem, indice, miniatura, ocupado, aoMudar, aoRemover, aoGerar, aoEnviar,
}) {
  const arquivo = useRef(null);
  const id = `personagem-${indice}`;
  const temImagem = Boolean(miniatura);
  const semDescricao = !String(personagem.descricao || '').trim();

  return (
    <div className="rounded-input border border-rule2 p-3 flex flex-col sm:flex-row gap-3" data-personagem={personagem.nome || indice}>
      <div className="shrink-0 flex sm:flex-col items-center gap-2">
        <div className="w-24 h-24 rounded-input bg-paper3 border border-rule overflow-hidden flex items-center justify-center">
          {ocupado
            ? <Loader2 size={20} className="animate-spin text-muted" aria-label="fazendo a imagem" />
            : temImagem
              ? <img src={miniatura} alt={`imagem de referência de ${personagem.nome || 'personagem'}`}
                     className="w-full h-full object-cover" />
              : <UserRound size={28} className="text-muted" aria-hidden="true" />}
        </div>
        <span className={`text-[11px] ${temImagem ? 'text-muted' : 'text-danger'}`}>
          {temImagem ? 'imagem aprovada' : 'sem imagem'}
        </span>
      </div>

      <div className="min-w-0 flex-1 space-y-2">
        <label className="block" htmlFor={`${id}-nome`}>
          <span className="eyebrow">nome</span>
          <input id={`${id}-nome`} className="input-field mt-1.5" maxLength={40} value={personagem.nome || ''}
                 onChange={(e) => aoMudar({ ...personagem, nome: e.target.value })} placeholder="Ex.: Lulu" />
        </label>
        <label className="block" htmlFor={`${id}-descricao`}>
          <span className="eyebrow">como é</span>
          <textarea id={`${id}-descricao`} className="input-field mt-1.5 min-h-[4.5rem]" maxLength={400}
                    value={personagem.descricao || ''}
                    onChange={(e) => aoMudar({ ...personagem, descricao: e.target.value })}
                    placeholder="Ex.: coelhinha branca, orelhas compridas, laço vermelho na orelha esquerda, olhos grandes" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={aoGerar}
                  disabled={ocupado || semDescricao || !String(personagem.nome || '').trim()}
                  title={semDescricao ? 'Descreva o personagem antes' : 'Usa uma imagem da cota grátis do dia'}>
            <Wand2 size={13} /> {temImagem ? 'gerar outra' : 'gerar a imagem'}
          </button>
          <button type="button" className="btn-quiet px-3 py-1.5 text-xs" onClick={() => arquivo.current?.click()}
                  disabled={ocupado || !String(personagem.nome || '').trim()}>
            <ImageUp size={13} /> enviar uma imagem
          </button>
          <input ref={arquivo} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                 onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) aoEnviar(f); }} />
          <button type="button" className="btn-quiet px-2.5 py-1.5 text-xs ml-auto text-muted hover:text-danger"
                  onClick={aoRemover} disabled={ocupado} aria-label={`tirar ${personagem.nome || 'o personagem'}`}>
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}
