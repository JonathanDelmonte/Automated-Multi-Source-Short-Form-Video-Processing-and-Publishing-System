import React, { useRef, useState } from 'react';
import { Check, Copy, Download, Loader2 } from 'lucide-react';
import { getApiUrl } from '../../config';
import { tempo } from '../../lib/compilacao.js';

// O vídeo longo na tela do projeto (etapa 7.8): o episódio de IA ou a
// compilação dos cortes. É horizontal, então não cabe no cartão em pé dos
// cortes (`ResultCard`), e as ferramentas dele -- reenquadrar, gancho -- são
// do vídeo vertical. Aqui: o player deitado, os capítulos (clicar pula para
// eles), a descrição do YouTube pronta para copiar e o baixar.

export default function VideoLongo({ clip, index = 0 }) {
  const video = useRef(null);
  const [copiado, setCopiado] = useState(false);
  const [baixando, setBaixando] = useState(null);
  const url = getApiUrl(clip.video_url);
  const capitulos = Array.isArray(clip.capitulos) ? clip.capitulos : [];
  const descricao = clip.video_description_for_youtube || '';
  const duracao = Math.max(0, (Number(clip.end) || 0) - (Number(clip.start) || 0));

  const pular = (segundos) => {
    const v = video.current;
    if (!v) return;
    v.currentTime = segundos;
    v.play?.().catch(() => {});
  };

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(descricao);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1500);
    } catch {
      /* sem permissão da área de transferência: o texto está na tela */
    }
  };

  // Como o do cartão de corte: com o progresso, porque um episódio tem
  // centenas de megabytes e o baixar mudo parece botão quebrado.
  const baixar = async () => {
    try {
      setBaixando(0);
      const resposta = await fetch(url);
      if (!resposta.ok) throw new Error('download');
      const total = Number(resposta.headers.get('content-length')) || 0;
      let blob;
      if (!resposta.body || !total) {
        blob = await resposta.blob();
      } else {
        const leitor = resposta.body.getReader();
        const pedacos = [];
        let recebido = 0;
        for (;;) {
          const { done, value } = await leitor.read();
          if (done) break;
          pedacos.push(value);
          recebido += value.length;
          setBaixando(Math.min(99, Math.round((recebido / total) * 100)));
        }
        blob = new Blob(pedacos, { type: 'video/mp4' });
      }
      const endereco = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = endereco;
      a.download = `video-longo-${index + 1}.mp4`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(endereco);
      document.body.removeChild(a);
    } catch {
      window.open(url, '_blank');
    } finally {
      setBaixando(null);
    }
  };

  return (
    <div className="card p-3 sm:p-4 space-y-3 min-w-0" data-video-longo>
      <video ref={video} src={url} controls preload="metadata"
             className="w-full aspect-video bg-black rounded-input" />
      <div className="flex flex-wrap items-start gap-2 min-w-0">
        <p className="text-ink font-medium min-w-0 flex-1 break-words">
          {clip.video_title_for_youtube_short || 'vídeo longo'}
        </p>
        <span className="readout normal-case shrink-0">{tempo(duracao)}</span>
      </div>
      <p className="text-[12px] text-muted leading-snug">
        Horizontal, para o YouTube: publicado no canal, ele abre só o galho do YouTube (TikTok e Instagram são
        a tela em pé).
      </p>

      {capitulos.length > 0 && (
        <div className="space-y-1" data-capitulos>
          <p className="eyebrow">capítulos</p>
          <ul className="space-y-0.5">
            {capitulos.map((c) => (
              <li key={`${c.inicio}-${c.titulo}`} className="flex items-baseline gap-2 text-sm min-w-0">
                <button type="button" onClick={() => pular(c.inicio)}
                        className="readout normal-case shrink-0 text-ink2 hover:text-ink underline underline-offset-2">
                  {tempo(c.inicio)}
                </button>
                <span className="min-w-0 truncate text-ink2">{c.titulo}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {descricao && (
        <details className="rounded-input border border-rule2 px-3 py-2">
          <summary className="text-sm text-ink2 cursor-pointer">descrição do YouTube</summary>
          <pre className="mt-2 whitespace-pre-wrap break-words text-[12px] text-ink2 font-sans">{descricao}</pre>
          <button type="button" onClick={copiar} className="btn-quiet px-2.5 py-1 text-xs mt-2">
            {copiado ? <Check size={13} className="text-ok" /> : <Copy size={13} />} {copiado ? 'copiada' : 'copiar'}
          </button>
        </details>
      )}

      <button type="button" onClick={baixar} disabled={baixando !== null} className="btn-ghost px-3 py-2 text-xs">
        {baixando !== null
          ? <><Loader2 size={14} className="animate-spin" /> baixando… {baixando}%</>
          : <><Download size={14} /> baixar o vídeo</>}
      </button>
    </div>
  );
}
