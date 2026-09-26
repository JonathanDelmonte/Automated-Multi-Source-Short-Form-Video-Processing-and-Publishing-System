import React, { useState, useEffect, useMemo } from 'react';
import {
  AlertTriangle, BarChart3, CalendarDays, Download, FolderOpen, Home, KeyRound, LifeBuoy,
  Loader2, Menu, Plus, Settings, Smartphone, Sparkles, Tv, Wrench, X,
} from 'lucide-react';
import Tranca from './components/Tranca';
import VoltaDoGoogle from './components/VoltaDoGoogle';
import AvisoDoMotor from './components/AvisoDoMotor';
import AvatarDoCanal from './components/ui/AvatarDoCanal';
import Modal from './components/ui/Modal';
import Inicio from './pages/Inicio';
import Canais, { NovoCanal } from './pages/Canais';
import Canal from './pages/Canal';
import Criar from './pages/Criar';
import Projetos from './pages/Projetos';
import Projeto from './pages/Projeto';
import Agenda from './pages/Agenda';
import Analises from './pages/Analises';
import Ferramentas from './pages/Ferramentas';
import Frota from './pages/Frota';
import Configuracoes from './pages/Configuracoes';
import Ajuda from './pages/Ajuda';
import { useAuth } from './contexts/AuthContext';
import { API_BASE_URL } from './config';
import { URL_DO_INSTALADOR } from './lib/ajudante';
import { useAquecerTranscricao } from './lib/aquecerTranscricao';
import { useListaDeCanais } from './lib/canais';
import { mandarFuso } from './lib/automacao';
import { ehVoltaDoGoogle } from './lib/conexoes';
import { PainelContext } from './lib/painel';
import { hrefDe, ir, useRota } from './lib/rota';

// O esqueleto do painel (Fase 7, etapa 7.1): a sessão, a navegação, os avisos
// do topo e qual página está aberta -- pelo endereço depois do `#`
// (`lib/rota.js`). As páginas moram em `pages/`; até a 7.1 tudo isto era um
// arquivo só de ~2.000 linhas, com a tela de cortes, a de projetos e as
// configurações misturadas no mesmo estado.

// Enquanto `/api/config` não responde. Era uma tela vazia -- e, com a config
// agora esperada até o servidor responder, "vazia" viraria "preta para
// sempre" se o backend não subir. Diz o que está acontecendo e, se demorar,
// o que fazer.
//
// No site do Cloudflare (`build:site`) há uma causa a mais, e a mais provável
// na primeira visita: o Chrome pergunta se o site pode falar com este
// computador, e um "Bloquear" por engano deixa esta tela girando para sempre
// sem erro nenhum. O servidor nunca fica sabendo -- só a tela pode dizer.
const ABERTO_PELO_SITE = /^https?:\/\//.test(API_BASE_URL);

function EsperandoServidor() {
  // No site, quem chega pela primeira vez não tem motor nenhum: esperar os
  // 15 s do Docker para dizer o que fazer seria 15 s olhando um "conectando"
  // que nunca termina. Quem já tem o ajudante aberto não chega a ver isto --
  // a config responde antes.
  const [demorou, setDemorou] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDemorou(true), ABERTO_PELO_SITE ? 4000 : 15000);
    return () => clearTimeout(t);
  }, []);

  if (ABERTO_PELO_SITE) {
    return (
      <div className="min-h-screen bg-paper flex items-center justify-center p-6">
        <div className="max-w-md text-center space-y-4">
          {/* A primeira coisa que quem chega pelo site vê: a marca, antes de
              qualquer explicação. */}
          <img src="/virtu-clips.png" alt="Virtu Clips" className="mx-auto h-20 w-auto mb-2" />
          <p className="flex items-center justify-center gap-2 text-sm text-ink2">
            <Loader2 size={15} className="animate-spin text-brass" /> procurando o Virtu Clips neste computador…
          </p>
          {demorou && (
            <>
              <p className="text-sm text-ink2 leading-relaxed">
                Este site é só a tela. Quem baixa, transcreve e corta os vídeos é um
                programa no seu computador, que usa a placa de vídeo se houver.
              </p>
              <a href={URL_DO_INSTALADOR} className="btn-primary px-4 py-2 text-sm inline-flex">
                <Download size={15} /> Baixar o Virtu Clips para Windows
              </a>
              <p className="text-xs text-muted leading-relaxed">
                Abra o arquivo baixado: ele instala tudo sem pedir administrador (leva
                alguns minutos) e abre este site sozinho. Se o Windows disser que
                protegeu o computador, clique em “Mais informações” e depois em
                “Executar assim mesmo”.
              </p>
              <div className="text-xs text-muted leading-relaxed space-y-1.5 text-left border-t border-rule pt-3">
                <p>
                  <span className="text-ink2">Já instalou?</span> Abra o Virtu Clips pelo menu
                  Iniciar; o ícone dele fica perto do relógio.
                </p>
                <p>
                  <span className="text-ink2">O navegador perguntou</span> se este site pode
                  acessar apps e serviços deste dispositivo? A resposta é Permitir. Se
                  bloqueou, libere no ícone à esquerda do endereço e recarregue a página.
                </p>
                <p>
                  <span className="text-ink2">Usa o Docker?</span> Abra o Docker Desktop ou
                  rode atalhos\subir.bat.
                </p>
                <p>Mac e Linux ainda não têm o ajudante.</p>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-paper flex items-center justify-center p-6">
      <div className="max-w-sm text-center space-y-2">
        <p className="flex items-center justify-center gap-2 text-sm text-ink2">
          <Loader2 size={15} className="animate-spin text-brass" /> conectando ao servidor…
        </p>
        {demorou && (
          <p className="text-xs text-muted leading-relaxed">
            Logo depois de atualizar, o servidor leva alguns segundos para subir.
            Se passar de um minuto, confira se o Docker Desktop está aberto e rode
            atalhos\subir.bat.
          </p>
        )}
      </div>
    </div>
  );
}

// Uma definição de navegação alimenta as três superfícies: o trilho do
// computador, a gaveta do celular e a barra de baixo. `short` é o rótulo da
// barra, onde o completo quebraria em duas linhas num celular de 360 px, e
// `primary` diz quem mora nela. O `ord` é calculado pela posição, não escrito
// à mão: escrito à mão, a lista chegou a mostrar `01 03 05 07`, com os buracos
// das abas que saíram.
//
// O mapa é o do plano (`docs/PLANO-DA-PLATAFORMA.md`): o canal no centro, e
// cada parte que ainda não funciona com o lugar marcado.
const NAV = [
  { id: 'inicio', icon: Home, label: 'Início', short: 'início', primary: true },
  { id: 'canais', icon: Tv, label: 'Canais', short: 'canais', primary: true },
  { id: 'criar', icon: Sparkles, label: 'Criar', short: 'criar', primary: true },
  { id: 'projetos', icon: FolderOpen, label: 'Projetos', short: 'projetos', primary: true },
  { id: 'agenda', icon: CalendarDays, label: 'Agenda', short: 'agenda' },
  { id: 'analises', icon: BarChart3, label: 'Análises', short: 'análises' },
  { id: 'ferramentas', icon: Wrench, label: 'Ferramentas', short: 'ferramentas', separa: true },
  { id: 'frota', icon: Smartphone, label: 'Frota', short: 'frota' },
  { id: 'configuracoes', icon: Settings, label: 'Configurações', short: 'config', separa: true },
  { id: 'ajuda', icon: LifeBuoy, label: 'Ajuda', short: 'ajuda' },
].map((item, i) => ({ ...item, ord: String(i + 1).padStart(2, '0') }));

const SECOES = new Set(NAV.map((n) => n.id));

function App() {
  const { isSignedIn, localLlm, geminiNoMotor, configCarregada, authAtiva, motor, loading: authLoading } = useAuth();
  // Só depois da config, e só com sessão quando a instalação tem senha: antes
  // disso o servidor responderia 401 a tudo.
  const sessaoPronta = configCarregada && (!authAtiva || isSignedIn);
  // Segura o modelo de transcrição na placa enquanto esta aba estiver aberta.
  useAquecerTranscricao(sessaoPronta);
  // O fuso deste navegador vai para o motor (7.5): a agenda e a automação
  // valem no relógio de quem usa, e no Docker o motor roda em UTC.
  useEffect(() => { if (sessaoPronta) mandarFuso(); }, [sessaoPronta]);
  const rota = useRota();
  // A volta do "Conectar YouTube" no painel do Docker (7.3): o Google devolve
  // para a raiz do painel, com `?state=...&code=...` (ver VoltaDoGoogle).
  const [voltaDoGoogle] = useState(() => ehVoltaDoGoogle(window.location.search));
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem('gemini_key') || ''; } catch { return ''; }
  });
  const [showKeyModal, setShowKeyModal] = useState(false);
  // Mobile only: the full nav lives in a drawer behind the header's menu button.
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    // A chave do Gemini no NAVEGADOR é a de antes das chaves no programa
    // (ChavesDeIA): a tela a leva para lá e a esquece aqui -- e esquecer tem de
    // apagar, ou ela voltaria no próximo F5 e seguiria indo no `X-Gemini-Key`.
    try {
      if (apiKey) localStorage.setItem('gemini_key', apiKey);
      else localStorage.removeItem('gemini_key');
    } catch { /* localStorage bloqueado: vale só nesta aba */ }
  }, [apiKey]);

  // O projeto aberto morava no localStorage (`openshorts_session`, com os
  // cortes inteiros dentro) para voltar depois de um F5. Desde a 7.1 o
  // endereço é a memória (`#/projetos/<id>`), e a cópia velha só ocupa espaço.
  useEffect(() => {
    try { localStorage.removeItem('openshorts_session'); } catch { /* nada a limpar */ }
  }, []);

  // Fecha a gaveta ao trocar de tela; Esc também fecha.
  useEffect(() => { setNavOpen(false); }, [rota]);
  useEffect(() => {
    if (!navOpen) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') setNavOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [navOpen]);

  // A chave do navegador, um LLM local (LLM_BASE_URL) ou a do programa deste
  // computador bastam para o motor achar os momentos.
  // `geminiNoMotor`: a chave colada nas Configurações mora no programa deste
  // computador, e não no navegador (chaves_ia.py).
  const geminiOk = !!apiKey || !!localLlm || geminiNoMotor;
  // So com a config em mãos: antes dela, `localLlm` nulo quer dizer "ainda não
  // sei", não "não tem". Confundir os dois era o aviso de chave que aparecia
  // logo depois do atualizar.bat e sumia no F5.
  const keysMissing = configCarregada && !geminiOk;

  const canais = useListaDeCanais(sessaoPronta);
  const painel = useMemo(() => ({
    apiKey,
    setApiKey,
    geminiNoMotor,
    keysMissing,
    pedirChave: () => setShowKeyModal(true),
    canais,
  }), [apiKey, geminiNoMotor, keysMissing, canais]);

  // A tranca da Fase 4, antes de qualquer outra coisa. Com a auth ligada e sem
  // sessão, o painel inteiro dá lugar à tela de entrada — não adianta desenhar
  // abas cujas chamadas todas voltariam 401.
  //
  // `authLoading` importa: sem ele, a primeira renderização (antes de
  // `/api/config` responder) mostraria a tela de login por um instante para
  // quem já está logado, e pior, para quem nem tem auth ligada.
  // Antes da tranca: a volta vale pelo `state` do pedido, não pela sessão.
  if (voltaDoGoogle) {
    return <VoltaDoGoogle />;
  }
  if (authLoading) {
    return <EsperandoServidor />;
  }
  if (authAtiva && !isSignedIn) {
    return <Tranca />;
  }

  // O `#app` das versões antigas e qualquer endereço que não é tela caem no
  // início, em vez de numa tela vazia.
  const [secao, sub, extra, quarta] = rota.partes;
  const ativa = SECOES.has(secao) ? secao : 'inicio';
  const itemAtivo = NAV.find((n) => n.id === ativa);
  const canalDaRota = ativa === 'canais' && sub && sub !== 'novo' ? canais.porId[sub] : null;
  const tituloDoTopo = canalDaRota ? canalDaRota.name : itemAtivo?.label;

  let pagina;
  switch (ativa) {
    case 'canais':
      if (!sub) pagina = <Canais />;
      else if (sub === 'novo') pagina = <NovoCanal />;
      else pagina = <Canal key={sub} canalId={sub} aba={extra} subaba={quarta || null} />;
      break;
    case 'criar':
      pagina = <Criar key={`${sub || ''}-${rota.busca.get('canal') || ''}`} tipo={sub || null} canalInicial={rota.busca.get('canal')} />;
      break;
    case 'projetos':
      pagina = sub
        ? <Projeto key={sub} jobId={sub} />
        : <Projetos canal={rota.busca.get('canal')} />;
      break;
    case 'agenda': pagina = <Agenda />; break;
    case 'analises': pagina = <Analises aba={sub} />; break;
    case 'ferramentas': pagina = <Ferramentas ferramenta={sub} />; break;
    case 'frota': pagina = <Frota />; break;
    case 'configuracoes': pagina = <Configuracoes parte={sub} />; break;
    case 'ajuda': pagina = <Ajuda />; break;
    default: pagina = <Inicio />;
  }

  const Item = ({ item, rotulado, gaveta = false }) => {
    const NavIcon = item.icon;
    const isActive = ativa === item.id;
    return (
      <a
        href={hrefDe(item.id === 'inicio' ? '/' : `/${item.id}`)}
        title={item.label}
        aria-current={isActive ? 'page' : undefined}
        className={`relative w-full flex items-center gap-3 px-3 ${gaveta ? 'py-3' : 'py-2.5'} rounded-input transition-colors ${
          isActive ? 'bg-paper3 text-ink' : 'text-muted hover:text-ink2 hover:bg-paper3/50'}`}
      >
        {isActive && (
          <span className={`absolute left-0 ${gaveta ? 'top-2 bottom-2' : 'top-1.5 bottom-1.5'} w-0.5 bg-brass rounded-full`} aria-hidden="true" />
        )}
        <NavIcon size={18} className={`shrink-0 ${isActive ? 'text-brass' : ''}`} />
        <span className={`${gaveta ? 'text-[0.95rem]' : 'text-sm'} lowercase flex-1 text-left truncate ${rotulado ? '' : 'hidden lg:block'}`}>{item.label}</span>
        {!gaveta && <span className="readout hidden lg:block">{item.ord}</span>}
      </a>
    );
  };

  // Os canais no trilho: a cara de cada um, a um clique. No trilho estreito
  // (md) só o avatar; com rótulo (lg), o nome.
  const CanaisNoTrilho = ({ rotulado }) => {
    if (canais.situacao !== 'ok') return null;
    return (
      <div className="pt-3 mt-3 border-t border-rule space-y-1">
        <p className={`eyebrow px-3 pb-1 ${rotulado ? '' : 'hidden lg:block'}`}>seus canais</p>
        {canais.canais.slice(0, 6).map((c) => (
          <a
            key={c.id}
            href={hrefDe(`/canais/${c.id}`)}
            title={c.name}
            className={`flex items-center gap-2.5 px-3 py-1.5 rounded-input transition-colors ${
              canalDaRota?.id === c.id ? 'bg-paper3 text-ink' : 'text-muted hover:text-ink2 hover:bg-paper3/50'}`}
          >
            <AvatarDoCanal canal={c} size={22} />
            <span className={`text-sm truncate ${rotulado ? '' : 'hidden lg:block'}`}>{c.name}</span>
          </a>
        ))}
        <a
          href={hrefDe('/canais/novo')}
          title="novo canal"
          className="flex items-center gap-2.5 px-3 py-1.5 rounded-input text-muted hover:text-ink2 transition-colors"
        >
          <span className="w-[22px] h-[22px] rounded-full border border-dashed border-rule2 flex items-center justify-center shrink-0">
            <Plus size={12} />
          </span>
          <span className={`text-sm ${rotulado ? '' : 'hidden lg:block'}`}>novo canal</span>
        </a>
      </div>
    );
  };

  const LinkDoCodigo = ({ rotulado }) => (
    <a
      href="https://github.com/JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System"
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 text-xs lowercase text-muted hover:text-ink2 transition-colors"
    >
      <svg height="14" viewBox="0 0 16 16" version="1.1" width="14" aria-hidden="true" fill="currentColor" className="shrink-0"><path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>
      <span className={rotulado ? 'truncate' : 'hidden lg:block truncate'}>código aberto</span>
    </a>
  );

  return (
    <PainelContext.Provider value={painel}>
      {/* h-dvh where supported: on mobile Safari/Chrome `100vh` is the tallest
          the viewport ever gets, so a h-screen shell hides its own bottom bar
          behind the browser chrome until the user scrolls. */}
      <div className="flex h-screen supports-[height:100dvh]:h-[100dvh] bg-paper overflow-hidden">
        {/* Desktop rail: icon-only from md, labelled from lg. Below md it is
            gone entirely — an unlabelled 80px rail ate a fifth of a phone. */}
        <div className="hidden md:flex w-20 lg:w-64 bg-paper2 border-r border-rule flex-col h-full shrink-0 transition-all duration-300">
          {/* A marca: a logo inteira quando a barra tem rótulo (lg), e o V
              dela no trilho estreito (md), onde a logo seria um borrão. */}
          <a href={hrefDe('/')} className="p-6 pb-4 flex items-center" title="início">
            <img src="/favicon.png" alt="Virtu Clips" className="w-8 h-8 rounded-input shrink-0 lg:hidden" />
            <img src="/virtu-clips.png" alt="Virtu Clips" className="hidden lg:block h-12 w-auto" />
          </a>
          <nav className="flex-1 overflow-y-auto custom-scrollbar px-4 py-2 space-y-1">
            {NAV.map((item) => (
              <React.Fragment key={item.id}>
                {item.separa && <div className="my-2 border-t border-rule" aria-hidden="true" />}
                <Item item={item} />
              </React.Fragment>
            ))}
            <CanaisNoTrilho />
          </nav>
          <div className="p-4 border-t border-rule">
            <LinkDoCodigo />
          </div>
        </div>

        {navOpen && (
          <div className="md:hidden fixed inset-0 z-[90] flex" role="dialog" aria-modal="true" aria-label="Navegação">
            <div className="absolute inset-0 bg-black/60 animate-fade" onClick={() => setNavOpen(false)} aria-hidden="true" />
            <div className="relative w-[17rem] max-w-[82vw] h-full bg-paper2 border-r border-rule flex flex-col animate-slide-in-left">
              <div className="flex items-center justify-between px-5 h-14 border-b border-rule shrink-0">
                <a href={hrefDe('/')} className="flex items-center">
                  <img src="/virtu-clips.png" alt="Virtu Clips" className="h-8 w-auto" />
                </a>
                <button onClick={() => setNavOpen(false)} aria-label="fechar a navegação" className="p-2 -mr-2 text-muted hover:text-ink transition-colors">
                  <X size={18} />
                </button>
              </div>
              <nav className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3 space-y-1">
                {NAV.map((item) => (
                  <React.Fragment key={item.id}>
                    {item.separa && <div className="my-2 border-t border-rule" aria-hidden="true" />}
                    <Item item={item} rotulado gaveta />
                  </React.Fragment>
                ))}
                <CanaisNoTrilho rotulado />
              </nav>
              <div className="px-3 py-3 border-t border-rule safe-bottom shrink-0">
                <LinkDoCodigo rotulado />
              </div>
            </div>
          </div>
        )}

        <main className="flex-1 min-w-0 flex flex-col h-full overflow-hidden relative">
          <header className="h-14 border-b border-rule bg-paper flex items-center justify-between gap-2 px-3 sm:px-6 shrink-0 z-10">
            <div className="flex items-center gap-2 min-w-0">
              {/* Mobile: the drawer handle, and the section name the icon rail
                  used to carry. Without it a phone has no "where am I". */}
              <button
                onClick={() => setNavOpen(true)}
                aria-label="abrir a navegação"
                className="md:hidden -ml-1 p-2 rounded-input text-muted active:bg-paper3 transition-colors shrink-0"
              >
                <Menu size={20} />
              </button>
              <span className="font-display uppercase tracking-wide text-base text-ink truncate md:hidden">
                {tituloDoTopo || 'Virtu Clips'}
              </span>
              <span className="hidden md:inline readout truncate">
                {itemAtivo?.ord} · {itemAtivo?.label}{canalDaRota ? ` · ${canalDaRota.name}` : ''}
              </span>
            </div>

            <div className="flex items-center gap-2 sm:gap-3 shrink-0">
              {/* Hidden below sm: the standing banner underneath already says
                  the same thing, and two warnings in a 360px header is noise. */}
              {keysMissing && (
                <a
                  href={hrefDe('/configuracoes/chaves')}
                  className="badge-warn hover:brightness-125 transition-all hidden sm:inline-flex"
                  title="Colocar uma chave de IA"
                >
                  <AlertTriangle size={12} />
                  <span className="hidden md:inline">falta a chave de IA</span>
                  <span className="md:hidden">sem chave</span>
                </a>
              )}
              {ativa !== 'criar' && (
                <a href={hrefDe('/criar')} className="btn-primary px-3.5 py-1.5 text-xs hidden md:inline-flex">
                  <Sparkles size={13} /> criar
                </a>
              )}
            </div>
          </header>

          {/* A chave que falta, em toda tela menos na que resolve. */}
          {keysMissing && ativa !== 'configuracoes' && (
            <div className="mx-3 sm:mx-6 mt-3 px-3.5 sm:px-4 py-3 bg-paper2 border border-rule rounded-card flex flex-wrap items-center justify-between gap-2.5 sm:gap-4 shrink-0 animate-fade">
              <div className="flex items-start sm:items-center gap-2.5 sm:gap-3 text-sm text-ink2 min-w-0 flex-1">
                <KeyRound size={16} className="shrink-0 text-warn mt-0.5 sm:mt-0" />
                <div className="min-w-0">
                  <span className="font-medium text-ink">Falta uma chave de IA.</span>{' '}
                  <span className="text-muted">
                    O Virtu Clips usa IAs gratuitas para achar os melhores momentos. A chave é grátis e leva um minuto.
                  </span>
                </div>
              </div>
              <a href={hrefDe('/configuracoes/chaves')} className="btn-quiet px-3 py-1.5 text-xs shrink-0 w-full sm:w-auto">
                colocar a chave
              </a>
            </div>
          )}

          {/* O motor atrás do site, com o botão que o atualiza (Docker e ajudante). */}
          <AvisoDoMotor motor={motor} />

          <div className="flex-1 overflow-hidden relative">
            {pagina}
          </div>

          {/* Phone navigation: the four everyday places plus "mais". A flex
              sibling of the scrolling pane, not a fixed overlay, so content is
              never trapped behind it. */}
          <nav className="md:hidden shrink-0 border-t border-rule bg-paper2/95 backdrop-blur-sm safe-bottom" aria-label="navegação principal">
            <div className="flex items-stretch">
              {NAV.filter((n) => n.primary).map((item) => {
                const NavIcon = item.icon;
                const isActive = ativa === item.id;
                const destaque = item.id === 'criar';
                return (
                  <a
                    key={item.id}
                    href={hrefDe(item.id === 'inicio' ? '/' : `/${item.id}`)}
                    aria-current={isActive ? 'page' : undefined}
                    className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] transition-colors ${isActive ? 'text-ink' : 'text-muted active:text-ink2'}`}
                  >
                    {destaque ? (
                      <span className={`w-8 h-8 -my-1 rounded-full flex items-center justify-center ${isActive ? 'bg-brass text-brassink' : 'bg-paper3 text-ink'}`}>
                        <NavIcon size={17} />
                      </span>
                    ) : (
                      <NavIcon size={19} className={isActive ? 'text-brass' : ''} />
                    )}
                    <span className="text-[10.5px] lowercase leading-none truncate max-w-full px-0.5">{item.short}</span>
                  </a>
                );
              })}
              <button
                onClick={() => setNavOpen(true)}
                aria-label="mais seções"
                aria-expanded={navOpen}
                className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-1 py-2 min-h-[56px] transition-colors ${
                  !NAV.find((n) => n.id === ativa)?.primary ? 'text-ink' : 'text-muted active:text-ink2'}`}
              >
                <Menu size={19} className={!NAV.find((n) => n.id === ativa)?.primary ? 'text-brass' : ''} />
                <span className="text-[10.5px] lowercase leading-none">mais</span>
              </button>
            </div>
          </nav>
        </main>

        {/* Falta a chave de IA: o caminho é colar nas Configurações (ChavesDeIA). */}
        <Modal
          isOpen={showKeyModal}
          onClose={() => setShowKeyModal(false)}
          eyebrow="PRIMEIRO PASSO"
          title="Falta a chave de IA"
          footer={
            <div className="flex gap-3">
              <button onClick={() => setShowKeyModal(false)} className="btn-ghost flex-1 px-4 py-2 text-sm">
                agora não
              </button>
              <button
                onClick={() => { setShowKeyModal(false); ir('/configuracoes/chaves'); }}
                className="btn-primary flex-1 px-4 py-2 text-sm"
              >
                colocar a chave
              </button>
            </div>
          }
        >
          <div className="space-y-3 text-sm text-muted leading-relaxed">
            <p>
              O Virtu Clips usa IAs gratuitas para achar os melhores momentos do vídeo, e cada uma
              pede uma chave. É grátis e leva um minuto: nas Configurações, clique em
              <span className="text-ink2"> criar chave grátis</span>, copie e cole.
            </p>
            <p>
              As recomendadas são a do <span className="text-ink2">Google Gemini</span> e a do
              <span className="text-ink2"> Groq</span>. Uma só já basta para começar.
            </p>
          </div>
        </Modal>
      </div>
    </PainelContext.Provider>
  );
}

export default App;
