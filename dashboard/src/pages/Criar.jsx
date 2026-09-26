import React, { useState } from 'react';
import { AlertTriangle, ArrowLeft, Bot } from 'lucide-react';
import MediaInput from '../components/MediaInput';
import SeletorDeCanal from '../components/SeletorDeCanal';
import TiposDeCriacao from '../components/TiposDeCriacao';
import Modal from '../components/ui/Modal';
import Pagina, { CabecalhoDaPagina, EmBreve } from '../components/ui/Pagina';
import { enviarVideo, guardarMidia } from '../lib/processar';
import { usePainel } from '../lib/painel';
import { hrefDe, ir } from '../lib/rota';

// Criar (etapa 7.1): primeiro o canal, depois o que criar.
//
// `#/criar` mostra os tipos; `#/criar/cortes` é o fluxo de sempre (o antigo
// Clip Generator), agora com o canal escolhido no começo -- ou nenhum.
// `?canal=<id>` chega da página de um canal e já vem marcado.
//
// Enviado o vídeo, a tela vai para o projeto (`#/projetos/<id>`), que é onde o
// progresso e os cortes moram.

const OUTROS = {
  ia: { titulo: 'Vídeo criado por IA', etapa: '7.7' },
  serie: { titulo: 'Série em partes', etapa: '7.6' },
  longo: { titulo: 'Vídeo longo', etapa: '7.8' },
};

export default function Criar({ tipo = null, canalInicial = null }) {
  const { apiKey, keysMissing, pedirChave, canais } = usePainel();
  const [canalId, setCanalId] = useState(canalInicial);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [qualidade, setQualidade] = useState(null);

  // Um `?canal=` de um canal que não existe mais vale "sem canal", em vez de
  // mandar ao motor um id que ele recusaria.
  const canalValido = canalId && canais.porId[canalId] ? canalId : null;
  const canal = canalValido ? canais.porId[canalValido] : null;

  const processar = async (dados, forcar = false) => {
    if (keysMissing) {
      pedirChave();
      return;
    }
    setEnviando(true);
    setErro(null);
    setQualidade(null);
    try {
      const r = await enviarVideo(dados, { apiKey, forcarBaixaQualidade: forcar, canalId: canalValido });
      // A fonte tem resolução baixa: a pessoa decide antes de gastar minutos
      // num vídeo que vai sair ruim. Confirmando, o pedido volta forçado.
      if (r.needs_confirmation) {
        setQualidade({ info: r.quality_check, dados });
        return;
      }
      guardarMidia(r.job_id, dados);
      if (canalValido) canais.carregar();
      ir(`/projetos/${r.job_id}`);
    } catch (e) {
      setErro(`Não consegui começar: ${e.message}`);
    } finally {
      setEnviando(false);
    }
  };

  const escolhaDoCanal = (
    <div className="space-y-2">
      <p className="eyebrow">para qual canal?</p>
      <SeletorDeCanal valor={canalValido} aoEscolher={setCanalId} />
    </div>
  );

  if (!tipo) {
    return (
      <Pagina largura="media">
        <CabecalhoDaPagina
          rotulo="criar"
          titulo="O que vamos criar?"
          descricao="Escolha o canal (ou nenhum) e o tipo de vídeo."
        />
        {escolhaDoCanal}
        <TiposDeCriacao canalId={canalValido} />
      </Pagina>
    );
  }

  if (OUTROS[tipo]) {
    return (
      <Pagina largura="media">
        <a href={hrefDe('/criar')} className="btn-quiet px-3 py-1.5 text-xs w-fit">
          <ArrowLeft size={14} /> criar
        </a>
        <CabecalhoDaPagina rotulo="criar" titulo={OUTROS[tipo].titulo} />
        <EmBreve etapa={OUTROS[tipo].etapa} titulo="Ainda não dá para criar este tipo.">
          <p>O lugar dele já está aqui para você ver onde vai ficar. O que ele vai fazer está no cartão da tela anterior.</p>
        </EmBreve>
      </Pagina>
    );
  }

  return (
    <Pagina largura="estreita">
      <a href={hrefDe(`/criar${canalValido ? `?canal=${canalValido}` : ''}`)} className="btn-quiet px-3 py-1.5 text-xs w-fit">
        <ArrowLeft size={14} /> criar
      </a>
      <CabecalhoDaPagina
        rotulo={canal ? `criar · ${canal.name}` : 'criar'}
        titulo="Cortes de um vídeo"
        descricao="Envie um vídeo ou cole um link. A IA acha os melhores momentos e entrega cortes verticais, com legenda e gancho."
      />
      {escolhaDoCanal}

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0 break-words">{erro}</span>
        </p>
      )}

      <MediaInput onProcess={processar} isProcessing={enviando} />

      <p className="text-xs text-muted flex items-center gap-1.5">
        <Bot size={13} className="shrink-0" />
        Ou deixe um agente de IA fazer:{' '}
        <a href={hrefDe('/configuracoes/agente')} className="text-ink2 underline underline-offset-2 hover:text-brass transition-colors">
          conectar o Claude, o Cursor ou o n8n
        </a>
      </p>

      {qualidade && (
        <Modal isOpen onClose={() => setQualidade(null)} size="md" eyebrow="ATENÇÃO" title="vídeo em baixa qualidade">
          <div className="space-y-4">
            <p className="text-sm text-ink2">
              O YouTube só oferece <span className="text-brass font-semibold">{qualidade.info.max_height}p</span> para
              este vídeo (abaixo dos {qualidade.info.min_height}p recomendados). Dá para seguir, mas os cortes
              vão sair com menos qualidade.
            </p>
            {qualidade.info.cookies_invalid && (
              <p className="text-xs text-muted">
                Os cookies do YouTube parecem vencidos: exportar de novo, numa janela anônima, costuma liberar o HD.
              </p>
            )}
            <div className="flex gap-2 justify-end pt-2">
              <button onClick={() => setQualidade(null)} className="btn-ghost">cancelar</button>
              <button
                onClick={() => { const d = qualidade.dados; setQualidade(null); processar(d, true); }}
                className="btn-primary"
              >
                seguir assim mesmo
              </button>
            </div>
          </div>
        </Modal>
      )}
    </Pagina>
  );
}
