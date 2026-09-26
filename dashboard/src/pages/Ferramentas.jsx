import React, { useState } from 'react';
import { AlertTriangle, ArrowLeft, ArrowRight, Image, Search, Wand2 } from 'lucide-react';
import ThumbnailStudio from '../components/ThumbnailStudio';
import Pagina, { CabecalhoDaPagina, EmBreve } from '../components/ui/Pagina';
import { enviarVideo } from '../lib/processar';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// Ferramentas (etapa 7.1): o que se usa de vez em quando, fora do fluxo de um
// canal. Hoje, o YouTube Studio (títulos e miniaturas), que o autor pediu para
// manter; o resto tem o lugar marcado.

function Studio() {
  const { apiKey, geminiNoMotor, keysMissing, pedirChave } = usePainel();
  const [erro, setErro] = useState(null);

  // "Criar cortes deste vídeo": o vídeo e a transcrição já estão no motor, pela
  // sessão do Studio, e o projeto nasce sem mandar nada de novo.
  const criarCortes = async (sessao) => {
    if (keysMissing) {
      pedirChave();
      return;
    }
    setErro(null);
    try {
      // O Studio só recebe o vídeo da própria pessoa, publicado no próprio
      // canal: o envio carrega esse mesmo atestado.
      const r = await enviarVideo({ type: 'thumbnail_session', payload: sessao, acknowledged: true }, { apiKey });
      ir(`/projetos/${r.job_id}`);
    } catch (e) {
      setErro(`Não consegui começar: ${e.message}`);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="shrink-0 px-3 sm:px-4 pt-3 flex flex-wrap items-center gap-2">
        <a href={hrefDe('/ferramentas')} className="btn-quiet px-3 py-1.5 text-xs">
          <ArrowLeft size={14} /> ferramentas
        </a>
        {erro && (
          <span className="flex items-center gap-1.5 text-xs text-danger min-w-0">
            <AlertTriangle size={13} className="shrink-0" /> <span className="truncate">{erro}</span>
          </span>
        )}
      </div>
      <div className="flex-1 min-h-0 relative">
        <ThumbnailStudio geminiApiKey={apiKey} geminiNoMotor={geminiNoMotor} onCreateClips={criarCortes} />
      </div>
    </div>
  );
}

export default function Ferramentas({ ferramenta = null }) {
  if (ferramenta === 'studio') return <Studio />;

  return (
    <Pagina largura="media">
      <CabecalhoDaPagina
        rotulo="ferramentas"
        titulo="Ferramentas"
        descricao="O que se usa de vez em quando, fora do fluxo de um canal."
      />

      <a href={hrefDe('/ferramentas/studio')} className="card p-5 flex items-center gap-4 group hover:border-rule2 transition-colors">
        <span className="w-11 h-11 rounded-input bg-brass text-brassink flex items-center justify-center shrink-0">
          <Image size={20} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-ink font-medium">YouTube Studio</span>
          <span className="block text-muted text-[13px] leading-snug mt-0.5">
            Títulos e miniaturas para um vídeo longo: a IA lê o vídeo, propõe títulos e desenha as
            miniaturas com o seu rosto.
          </span>
        </span>
        <ArrowRight size={17} className="text-muted group-hover:text-ink shrink-0 transition-colors" />
      </a>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <EmBreve etapa="7.5" titulo="Busca de vídeos sem direitos">
          <p className="flex gap-2"><Search size={15} className="shrink-0 mt-0.5" />
            Achar vídeos de domínio público ou com licença livre no nicho de um canal, guardando a
            licença e o crédito de cada um.</p>
        </EmBreve>
        <EmBreve etapa="7.7" titulo="Estilos de criação">
          <p className="flex gap-2"><Wand2 size={15} className="shrink-0 mt-0.5" />
            Montar e salvar o estilo dos vídeos de IA de um canal: traço, cores, voz e ritmo.</p>
        </EmBreve>
      </div>
    </Pagina>
  );
}
