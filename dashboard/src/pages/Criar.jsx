import React, { useState } from 'react';
import { AlertTriangle, ArrowLeft, Bot } from 'lucide-react';
import MediaInput from '../components/MediaInput';
import CriarVideoDeIA from '../components/criacao/CriarVideoDeIA';
import CriarVideoLongo from '../components/longo/CriarVideoLongo';
import SerieInput from '../components/SerieInput';
import SeletorDeCanal from '../components/SeletorDeCanal';
import TiposDeCriacao from '../components/TiposDeCriacao';
import Modal from '../components/ui/Modal';
import Pagina, { CabecalhoDaPagina } from '../components/ui/Pagina';
import { enviarVideo, guardarMidia } from '../lib/processar';
import { usePainel } from '../lib/painel';
import { useAuth } from '../contexts/AuthContext';
import { hrefDe, ir } from '../lib/rota';

// Criar (etapa 7.1): primeiro o canal, depois o que criar.
//
// `#/criar` mostra os tipos; `#/criar/cortes` é o fluxo de sempre (o antigo
// Clip Generator), agora com o canal escolhido no começo -- ou nenhum.
// `?canal=<id>` chega da página de um canal e já vem marcado.
//
// Enviado o vídeo, a tela vai para o projeto (`#/projetos/<id>`), que é onde o
// progresso e os cortes moram.
//
// `#/criar/serie` (7.6) é a série em partes: o mesmo envio, com o documento da
// série junto. Nenhuma IA escolhe trecho, então ela não pede chave de IA.
//
// `#/criar/ia` (7.7) é o vídeo criado por IA: sem envio nenhum, no estilo
// salvo no canal. Sem canal não há estilo, então o canal é obrigatório ali.
//
// `#/criar/longo` (7.8) é o vídeo horizontal longo: o episódio de IA ou a
// compilação dos cortes (`?modo=cortes`, e `?projeto=<id>` chega da tela de um
// projeto com os cortes dele já escolhidos).

export default function Criar({ tipo = null, canalInicial = null, modoInicial = null, projetoInicial = null }) {
  const { apiKey, keysMissing, pedirChave, canais } = usePainel();
  const { configCarregada, seriesNoMotor } = useAuth();
  const [canalId, setCanalId] = useState(canalInicial);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [qualidade, setQualidade] = useState(null);

  // Um `?canal=` de um canal que não existe mais vale "sem canal", em vez de
  // mandar ao motor um id que ele recusaria.
  const canalValido = canalId && canais.porId[canalId] ? canalId : null;
  const canal = canalValido ? canais.porId[canalValido] : null;

  const processar = async (dados, forcar = false) => {
    // A série não usa IA para escolher trecho: sem chave, ela anda igual.
    if (keysMissing && !dados.serie) {
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

  if (tipo === 'longo') {
    return (
      <Pagina largura="estreita">
        <a href={hrefDe(`/criar${canalValido ? `?canal=${canalValido}` : ''}`)} className="btn-quiet px-3 py-1.5 text-xs w-fit">
          <ArrowLeft size={14} /> criar
        </a>
        <CabecalhoDaPagina
          rotulo={canal ? `criar · ${canal.name}` : 'criar'}
          titulo="Vídeo longo"
          descricao="Um vídeo horizontal de vários minutos para o YouTube: um episódio criado por IA no estilo do canal, que pode continuar uma história, ou uma compilação dos cortes que você já tem."
        />
        {escolhaDoCanal}
        <CriarVideoLongo canalId={canalValido} modoInicial={modoInicial} projetoInicial={projetoInicial}
                         aoCriar={() => canais.carregar()} />
      </Pagina>
    );
  }

  if (tipo === 'ia') {
    return (
      <Pagina largura="estreita">
        <a href={hrefDe(`/criar${canalValido ? `?canal=${canalValido}` : ''}`)} className="btn-quiet px-3 py-1.5 text-xs w-fit">
          <ArrowLeft size={14} /> criar
        </a>
        <CabecalhoDaPagina
          rotulo={canal ? `criar · ${canal.name}` : 'criar'}
          titulo="Vídeo criado por IA"
          descricao="Roteiro, imagens, narração e legenda de um vídeo curto, no estilo que está salvo no canal. Nada é pago: tudo sai das cotas grátis das suas chaves."
        />
        {escolhaDoCanal}
        <CriarVideoDeIA canalId={canalValido} aoCriar={() => canais.carregar()} />
      </Pagina>
    );
  }

  const ehSerie = tipo === 'serie';

  return (
    <Pagina largura="estreita">
      <a href={hrefDe(`/criar${canalValido ? `?canal=${canalValido}` : ''}`)} className="btn-quiet px-3 py-1.5 text-xs w-fit">
        <ArrowLeft size={14} /> criar
      </a>
      <CabecalhoDaPagina
        rotulo={canal ? `criar · ${canal.name}` : 'criar'}
        titulo={ehSerie ? 'Série em partes' : 'Cortes de um vídeo'}
        descricao={ehSerie
          ? 'Cole o link de uma live ou de um vídeo longo sem direitos autorais. Ele vira Parte 1, 2, 3…, com o número no vídeo e no título, e vai para a agenda na ordem.'
          : 'Envie um vídeo ou cole um link. A IA acha os melhores momentos e entrega cortes verticais, com legenda e gancho.'}
      />
      {escolhaDoCanal}

      {erro && (
        <p className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" /> <span className="min-w-0 break-words">{erro}</span>
        </p>
      )}

      {ehSerie
        ? <SerieInput onProcess={processar} isProcessing={enviando} canalId={canalValido} canalNome={canal?.name}
                      motorAntigo={configCarregada && !seriesNoMotor} />
        : <MediaInput onProcess={processar} isProcessing={enviando} />}

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
