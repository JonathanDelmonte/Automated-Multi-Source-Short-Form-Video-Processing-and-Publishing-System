/* global __VERSAO_DO_SITE__ */
import React, { useEffect, useState } from 'react';
import { Check, Copy, Info } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { maisNova, versaoPublicada } from '../lib/ajudante';
import { lerNavegador } from '../lib/navegador';

// Configurações → Versões (25-set-2026). Pedido do autor: "um pequeno espaço
// para colocar essas versões". São três coisas que mudam em ritmos diferentes,
// e cada uma responde uma pergunta diferente quando algo dá errado:
//
// - o PROGRAMA deste computador (o motor, no Docker ou no ajudante), que diz a
//   versão dele pelo `/api/config`;
// - o SITE, que o Cloudflare publica a cada envio para a `main`, com a versão
//   gravada no build (`versao-do-site.js`);
// - o NAVEGADOR, a primeira pergunta de todo "no meu computador não abre".
//
// O site muda mais vezes que o programa -- um commit só de tela não gera
// versão nova do programa --, então um número maior no site é o normal, e o
// cartão diz isso. Quem avisa que o programa ficou para trás é o AvisoDoMotor,
// no topo da página; aqui só se mostra.

const SITE = typeof __VERSAO_DO_SITE__ !== 'undefined' ? __VERSAO_DO_SITE__ : null;

const ORIGEM = {
  docker: 'Docker',
  ajudante: 'ajudante, instalado pelo site',
  codigo: 'rodando direto do código',
};

function dataCurta(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return null;
  }
}

function linhaDoSite() {
  // No painel do Docker o Vite roda em modo de desenvolvimento, sem git no
  // container: não há build, então não há número -- e a tela é servida da
  // pasta do projeto, que é de onde o programa também roda.
  if (import.meta.env.DEV) return 'o da pasta do projeto (painel do Docker): acompanha o código da pasta, sem número próprio';
  if (!SITE) return 'não informado';
  const partes = [SITE.versao ? `versão ${SITE.versao}` : 'versão não informada'];
  if (SITE.commit) partes.push(`commit ${SITE.commit}`);
  const quando = dataCurta(SITE.publicadoEm);
  if (quando) partes.push(`publicado em ${quando}`);
  return partes.join(' · ');
}

function Linha({ rotulo, children }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-0.5 sm:gap-3 py-2 border-b border-rule last:border-b-0">
      <dt className="text-muted text-xs sm:w-44 shrink-0">{rotulo}</dt>
      <dd className="text-sm text-ink2 break-words min-w-0">{children}</dd>
    </div>
  );
}

export default function Versoes() {
  const { motor } = useAuth();
  // undefined = perguntando; null = não deu para saber
  const [publicada, setPublicada] = useState(undefined);
  const [navegador, setNavegador] = useState(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    let vivo = true;
    versaoPublicada().then((v) => { if (vivo) setPublicada(v); });
    lerNavegador().then((n) => { if (vivo) setNavegador(n); });
    return () => { vivo = false; };
  }, []);

  const versao = motor?.versao || null;
  const origem = ORIGEM[motor?.origem] || null;
  const programa = motor
    ? [versao ? `versão ${versao}` : 'sem número de versão', origem].filter(Boolean).join(' · ')
    : 'não informado';

  let situacao = null;
  if (publicada && versao) {
    situacao = maisNova(publicada, versao)
      ? { ok: false, texto: 'há versão nova: use o aviso no topo da página' }
      : { ok: true, texto: 'em dia' };
  }
  const textoPublicada = publicada === undefined ? 'perguntando…'
    : publicada ? `versão ${publicada}` : 'não deu para consultar agora';

  const nomeDoSite = import.meta.env.MODE === 'site' ? 'Este site' : 'Este painel';
  const linhas = [
    ['Programa deste computador', programa],
    ['Mais nova publicada', situacao ? `${textoPublicada} (${situacao.texto})` : textoPublicada],
    [nomeDoSite, linhaDoSite()],
    ['Navegador', navegador || '…'],
  ];

  const copiar = () => {
    const texto = linhas.map(([r, v]) => `${r}: ${v}`).join('\n');
    navigator.clipboard?.writeText(texto).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1600);
    }).catch(() => {});
  };

  return (
    <div className="card p-6 mb-6" id="versoes">
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 className="font-display uppercase tracking-wide text-lg text-ink flex items-center gap-2">
          <Info size={16} className="text-brass" /> Versões
        </h3>
        <button onClick={copiar} className="btn-ghost px-2.5 py-1 text-xs shrink-0" aria-label="copiar as versões">
          {copiado ? <Check size={13} /> : <Copy size={13} />} {copiado ? 'copiado' : 'copiar'}
        </button>
      </div>
      <dl className="mb-3">
        <Linha rotulo="Programa deste computador">{programa}</Linha>
        <Linha rotulo="Mais nova publicada">
          {textoPublicada}
          {situacao && (
            <span className={`ml-2 text-xs ${situacao.ok ? 'text-ok' : 'text-warn'}`}>{situacao.texto}</span>
          )}
        </Linha>
        <Linha rotulo={nomeDoSite}>{linhaDoSite()}</Linha>
        <Linha rotulo="Navegador">{navegador || '…'}</Linha>
      </dl>
      <p className="text-muted text-xs leading-relaxed">
        O site muda mais vezes que o programa: mudança só de tela não gera versão nova do programa,
        então o número do site ser maior é o normal. Quando o programa precisar de atualização, o
        aviso aparece no topo da página. Para pedir ajuda, use <span className="text-ink2">copiar</span>{' '}
        e cole na conversa.
      </p>
    </div>
  );
}
