import React, { useEffect, useState } from 'react';
import { Bot, Gauge, Info, KeyRound, Shield, Timer, Users } from 'lucide-react';
import ChavesDeIA from '../components/ChavesDeIA';
import McpConnectCard from '../components/McpConnectCard';
import OndeVaiOTempo from '../components/OndeVaiOTempo';
import PublicacoesTab from '../components/PublicacoesTab';
import Versoes from '../components/Versoes';
import Pagina, { CabecalhoDaPagina, EmBreve, Secao } from '../components/ui/Pagina';
import { apiFetch } from '../lib/api';
import { usePainel } from '../lib/painel';
import { hrefDe } from '../lib/rota';

// Configurações (etapa 7.1). Cada parte tem endereço (`#/configuracoes/contas`)
// e os atalhos no topo levam até ela: é o que deixa o resto do painel mandar a
// pessoa direto ao lugar certo ("colocar a chave", "conectar um agente").
//
// As contas vieram da antiga aba Publicação, e "onde vai o tempo" também -- ele
// morava lá "porque é onde o autor já olha", e o autor não entendeu o que os
// números queriam dizer (26-set-2026): aqui eles ganharam uma legenda.

const PARTES = [
  { id: 'chaves', rotulo: 'chaves de IA', icone: KeyRound },
  { id: 'contas', rotulo: 'contas', icone: Users },
  { id: 'uso', rotulo: 'uso e limites', icone: Gauge },
  { id: 'desempenho', rotulo: 'desempenho', icone: Timer },
  { id: 'agente', rotulo: 'agente de IA', icone: Bot },
  { id: 'versoes', rotulo: 'versões', icone: Info },
];

function UsoELimites() {
  const [quota, setQuota] = useState(undefined);
  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await apiFetch('/api/contas');
        const data = res.ok ? await res.json() : {};
        if (vivo) setQuota(data.quota_youtube || null);
      } catch {
        if (vivo) setQuota(null);
      }
    })();
    return () => { vivo = false; };
  }, []);

  return (
    <>
      {quota && (
        <p className="text-sm text-ink2">
          YouTube: <span className="text-ink">{quota.uploads_hoje}</span> de {quota.uploads_por_dia} envios hoje pela API.
          <span className="text-muted"> A cota do Google recomeça à meia-noite do horário do Pacífico.</span>
        </p>
      )}
      <EmBreve
        etapa="7.3"
        itens={[
          'Quanto do limite diário de cada IA gratuita já foi usado hoje.',
          'A cota de envios de cada conta do YouTube.',
          'Quanto os projetos ocupam no disco deste computador.',
        ]}
      />
    </>
  );
}

export default function Configuracoes({ parte = null }) {
  const { apiKey, setApiKey } = usePainel();

  // Chegar por `#/configuracoes/contas` leva até a parte; sem ela, o topo.
  useEffect(() => {
    if (!parte) return;
    const alvo = document.getElementById(parte);
    if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [parte]);

  return (
    <Pagina largura="estreita">
      <CabecalhoDaPagina rotulo="configurações" titulo="Configurações">
        <p className="flex items-center gap-2 text-xs text-muted mt-2">
          <Shield size={12} className="text-ok shrink-0" /> As chaves ficam no programa deste computador, não no site.
        </p>
      </CabecalhoDaPagina>

      <nav aria-label="partes das configurações" className="flex flex-wrap gap-1.5">
        {PARTES.map(({ id, rotulo, icone: Icone }) => (
          <a
            key={id}
            href={hrefDe(`/configuracoes/${id}`)}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs transition-colors ${
              parte === id ? 'border-[color:var(--color-accent)] text-ink bg-paper3' : 'border-rule2 text-muted hover:text-ink2'}`}
          >
            {Icone && <Icone size={13} />} {rotulo}
          </a>
        ))}
      </nav>

      {/* As chaves primeiro: sem elas nada processa. */}
      <div id="chaves" className="scroll-mt-4">
        <ChavesDeIA chaveDoNavegador={apiKey} esquecerChaveDoNavegador={() => setApiKey('')} />
      </div>

      <div id="contas" className="scroll-mt-4 space-y-2">
        <p className="text-muted text-[13px] leading-snug">
          Todas as contas de plataforma, de todos os canais. Para ligar uma conta a um canal, use os
          ajustes do canal.
        </p>
        <PublicacoesTab secoes={['contas']} />
      </div>

      <Secao id="uso" titulo="uso e limites" icone={Gauge}>
        <UsoELimites />
      </Secao>

      <Secao id="desempenho" titulo="desempenho: onde vai o tempo" icone={Timer}>
        <p className="text-muted text-[13px] leading-snug">
          O número grande é quantos minutos o programa leva para cada minuto de vídeo (2× quer dizer que
          um vídeo de 10 minutos leva 20). À direita, quantos vídeos entraram na conta e o tempo de todos
          somados. As barras mostram quanto cada etapa pesa, na ordem em que acontecem.
        </p>
        <OndeVaiOTempo />
      </Secao>

      <div id="agente" className="scroll-mt-4">
        <McpConnectCard />
      </div>

      {/* Por ultimo: e o que se copia para pedir ajuda, nao o que se usa. */}
      <div id="versoes" className="scroll-mt-4">
        <Versoes />
      </div>
    </Pagina>
  );
}
