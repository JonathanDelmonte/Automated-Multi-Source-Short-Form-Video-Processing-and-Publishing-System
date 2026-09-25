import React, { useEffect, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw, X } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { maisNova, URL_DO_INSTALADOR, versaoPublicada } from '../lib/ajudante';

// "O motor deste computador está atrás do site" (Fase 6.2), com o botão que
// atualiza por aqui (25-set-2026).
//
// No Docker e no ajudante. O site é publicado a cada envio para a `main`, e o
// site novo falando com um motor velho é o tipo de defeito que parece bug e é
// versão. O aviso mandava rodar o `atalhos\atualizar.bat` na pasta do projeto,
// e só aparecia no Docker -- o ajudante se atualiza sozinho, mas pode levar
// até 6 horas. Agora os dois têm o botão (`POST /api/motor/atualizar`, ver
// atualizar_motor.py): o Docker baixa a `main` e reinicia o container; o
// ajudante troca de versão pelo caminho de sempre, com verificação e volta
// atrás. O motor rodado direto do código é de quem o está escrevendo, e ali o
// aviso seria ruído.
//
// Fechar vale até sair uma versão mais nova que a que foi dispensada: o aviso
// que volta a cada F5 vira paisagem, e o que nunca volta esconde o problema.
//
// **A resposta do clique tem de ser impossível de perder** (25-set-2026). O
// autor clicou num motor de antes do botão, que respondeu 404 em milésimos: a
// explicação apareceu como uma linha cinza e o botão continuou igual, e "não
// aconteceu nada". Agora o clique mostra "verificando…" por pelo menos meio
// segundo, a resposta vem numa caixa destacada (que reaparece a cada clique), e
// o botão só fica quando tentar de novo pode dar outro resultado.
const MINIMO_VERIFICANDO_MS = 600;
const CHAVE_FECHADO = 'cortes_aviso_motor_fechado';

const INTERVALO_MS = 3000;
// Quanto esperar o motor SAIR do ar. O Docker reinicia um segundo depois de
// responder; o ajudante confere o pedido a cada 10 s, baixa a versão nova e só
// troca com a fila vazia -- se não começou em 5 minutos, ou há vídeo na fila
// ou não havia o que trocar, e esperar mais seria girar à toa.
const SEM_COMECAR_MS = { docker: 60 * 1000, ajudante: 5 * 60 * 1000 };
// Quanto esperar o motor VOLTAR depois de sair. O Docker volta em segundos. O
// ajudante troca por outro processo, que pode reinstalar dependências e sobe a
// versão nova numa porta de teste antes de trocar: minutos, e bem mais quando
// as dependências mudam.
const PRAZO_MS = { docker: 3 * 60 * 1000, ajudante: 20 * 60 * 1000 };

const lerFechado = () => {
  try {
    return localStorage.getItem(CHAVE_FECHADO);
  } catch {
    return null;
  }
};

const Codigo = ({ children }) => <code className="text-ink2">{children}</code>;

const listar = (arquivos = [], total = arquivos.length) => {
  const nomes = arquivos.slice(0, 3).join(', ');
  const resto = Math.max(total, arquivos.length) - Math.min(arquivos.length, 3);
  return resto > 0 ? `${nomes} e mais ${resto}` : nomes;
};

// O que dizer quando o botão não resolveu. `d` é o `detail` do motor.
function textoDaRecusa(status, d, origem) {
  if (status === 404 || status === 405) {
    return origem === 'ajudante' ? (
      <>
        Este ajudante é de antes do botão. Ele se atualiza sozinho em até 6 horas, quando
        nenhum vídeo estiver sendo processado — ou{' '}
        <a href={URL_DO_INSTALADOR} className="underline text-ink2 hover:text-ink">baixe o instalador</a>{' '}
        e escolha <span className="text-ink2">Reinstalar</span>.
      </>
    ) : (
      <>
        Este motor é de antes do botão: rode <Codigo>atalhos\atualizar.bat</Codigo> uma vez
        na pasta do projeto. Daí em diante, é por aqui.
      </>
    );
  }
  if (status === 401) return 'Entre de novo na sua conta e tente outra vez.';
  if (status === 403) return typeof d === 'string' && d ? d : 'Só o dono da instalação pode atualizar o motor.';
  if (!d || typeof d !== 'object') return typeof d === 'string' && d ? d : `O motor respondeu ${status}.`;

  if (d.situacao === 'precisa_do_atalho') {
    return d.reconstruir ? (
      <>
        Esta versão muda o que fica dentro da imagem do Docker ({listar(d.arquivos, d.total)}), e
        isso o botão não troca. Na pasta do projeto, rode <Codigo>atalhos\atualizar.bat</Codigo> e
        depois <Codigo>atalhos\reconstruir.bat</Codigo> — a reconstrução leva de 15 a 40 minutos.
      </>
    ) : (
      <>
        Esta versão muda a configuração dos containers ({listar(d.arquivos, d.total)}), e isso o
        botão não troca. Rode <Codigo>atalhos\atualizar.bat</Codigo> na pasta do projeto.
      </>
    );
  }
  switch (d.causa) {
    case 'jobs':
      return 'Há vídeo sendo processado agora. Espere terminar e clique de novo.';
    case 'atualizando':
      return 'O motor já está se atualizando (por outra aba?). Espere um pouco.';
    case 'ramo':
      return `A pasta do projeto está na branch ${d.ramo}, e o botão só atualiza a main. Volte para a main pelo GitHub Desktop.`;
    case 'divergiu':
      return 'A pasta do projeto tem commits que a main publicada não tem. O botão só avança, nunca mistura: resolva pelo GitHub Desktop.';
    case 'mudancas_locais':
      return `Há mudanças feitas à mão em arquivos que a versão nova troca (${listar(d.arquivos)}). Desfaça-as ou guarde-as pelo GitHub Desktop e clique de novo.`;
    case 'arquivos_soltos':
      return `Há arquivos na pasta do projeto, fora do git, com o nome de arquivos que a versão nova traz (${listar(d.arquivos)}). Mova-os de lá e clique de novo.`;
    case 'git_ocupado':
      return 'Outro programa está usando o git desta pasta agora (o GitHub Desktop?). Clique de novo em alguns segundos.';
    case 'sem_rede':
      return `Não consegui baixar a versão nova do GitHub${d.linha ? ` (${d.linha})` : ''}.`;
    case 'fora_do_compose':
      return (
        <>
          Este motor não foi aberto pelos atalhos do projeto, e o botão não sabe reiniciá-lo.
          Rode <Codigo>atalhos\atualizar.bat</Codigo> na pasta do projeto.
        </>
      );
    default:
      return `Não deu para atualizar por aqui: ${d.motivo || d.linha || d.causa || d.situacao}.`;
  }
}

// Clicar de novo muda alguma coisa? Não, quando o motor é de antes do botão,
// quando a versão pede o atalho ou quando o motor não é dos atalhos: ali o
// botão continuar na tela é o convite para o clique que "não faz nada".
const SEM_VOLTA = new Set(['fora_do_compose', 'codigo', 'sem_bandeja', 'ramo', 'divergiu']);
function valeTentarDeNovo(status, d) {
  if (status === 404 || status === 405 || status === 401 || status === 403) return false;
  if (d && typeof d === 'object') {
    if (d.situacao === 'precisa_do_atalho') return false;
    if (SEM_VOLTA.has(d.causa)) return false;
  }
  return true;
}

function textoDoPrazo(origem, saiu) {
  if (origem === 'ajudante') {
    return saiu
      ? 'O motor não voltou em 20 minutos. Abra o Virtu Clips pelo menu Iniciar; se ele não subir, baixe o instalador e escolha Reinstalar.'
      : 'O ajudante não começou a troca. Se há vídeo sendo processado, ele espera terminar e troca sozinho; se não, feche o Virtu Clips pelo ícone perto do relógio e abra de novo pelo menu Iniciar.';
  }
  return saiu
    ? 'O motor não voltou em 3 minutos. No Docker Desktop, confira o container virtu-clips-backend — ou rode atalhos\\atualizar.bat na pasta do projeto.'
    : 'O motor não reiniciou sozinho. Rode atalhos\\atualizar.bat na pasta do projeto.';
}

export default function AvisoDoMotor({ motor }) {
  const [publicada, setPublicada] = useState(null);
  const [fechado, setFechado] = useState(lerFechado);
  // null | 'pedindo' | 'esperando' (o motor reinicia ou o ajudante troca)
  const [fase, setFase] = useState(null);
  // { texto, deNovo, n }: `deNovo` diz se clicar de novo pode mudar alguma
  // coisa; `n` refaz a animação a cada clique, mesmo com o mesmo texto.
  const [problema, setProblemaCru] = useState(null);
  const setProblema = (texto, deNovo = true) => setProblemaCru(
    texto ? { texto, deNovo, n: Date.now() } : null);
  const origem = motor?.origem;
  const versao = motor?.versao;
  const atualizavel = (origem === 'docker' || origem === 'ajudante') && !!versao;

  useEffect(() => {
    if (!atualizavel) return undefined;
    let vivo = true;
    versaoPublicada().then((v) => { if (vivo) setPublicada(v); });
    return () => { vivo = false; };
  }, [atualizavel]);

  // Pergunta a versão ao motor até ela mudar, e aí recarrega: o painel inteiro
  // passa a falar com o motor novo. Enquanto ele reinicia, a pergunta falha, e
  // isso é o esperado.
  useEffect(() => {
    if (fase !== 'esperando') return undefined;
    let vivo = true;
    let timer = null;
    let saiu = false;
    const inicio = Date.now();
    const olhar = async () => {
      let nova = null;
      try {
        const res = await apiFetch('/api/config', { cache: 'no-store' });
        if (res.ok) nova = (await res.json())?.motor?.versao ?? null;
        else saiu = true;
      } catch {
        saiu = true;  // reiniciando: é o esperado
      }
      if (!vivo) return;
      if (nova && nova !== versao) {
        window.location.reload();
        return;
      }
      const prazo = (saiu ? PRAZO_MS : SEM_COMECAR_MS)[origem] || PRAZO_MS.docker;
      if (Date.now() - inicio > prazo) {
        setFase(null);
        setProblema(textoDoPrazo(origem, saiu), true);
        return;
      }
      timer = setTimeout(olhar, INTERVALO_MS);
    };
    timer = setTimeout(olhar, INTERVALO_MS);
    return () => { vivo = false; clearTimeout(timer); };
  }, [fase, origem, versao]);

  if (!atualizavel || !maisNova(publicada, versao)) return null;
  if (!fase && fechado && !maisNova(publicada, fechado)) return null;

  const fechar = () => {
    try {
      localStorage.setItem(CHAVE_FECHADO, publicada);
    } catch { /* fecha só nesta aba */ }
    setFechado(publicada);
    setProblema(null);
  };

  const atualizar = async () => {
    setFase('pedindo');
    setProblema(null);
    const inicio = Date.now();
    const esperarOMinimo = () => new Promise((r) => {
      setTimeout(r, Math.max(0, MINIMO_VERIFICANDO_MS - (Date.now() - inicio)));
    });
    try {
      const res = await apiFetch('/api/motor/atualizar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      let corpo = null;
      try { corpo = await res.json(); } catch { /* sem corpo */ }
      await esperarOMinimo();
      if (res.status === 202) {
        setFase('esperando');
        return;
      }
      setFase(null);
      if (res.ok && corpo?.situacao === 'atualizado') {
        setProblema('O código desta pasta já é o mais novo da main, e o motor já roda ele. Dê um Ctrl+F5 nesta aba.', false);
        return;
      }
      const d = corpo?.detail ?? corpo;
      setProblema(textoDaRecusa(res.status, d, origem), valeTentarDeNovo(res.status, d));
    } catch {
      await esperarOMinimo();
      setFase(null);
      setProblema('Não consegui falar com o motor deste computador. Ele está ligado?', true);
    }
  };

  const ocupado = fase !== null;
  const andamento = fase === 'esperando' && (origem === 'ajudante'
    ? 'O ajudante está trocando de versão: o motor para por alguns minutos e volta sozinho, e esta página recarrega quando ele voltar. Se há vídeo sendo processado, ele espera terminar.'
    : 'Atualizando: o motor reinicia, e esta página recarrega sozinha quando ele voltar.');

  return (
    <div className="mx-3 sm:mx-6 mt-3 px-3.5 sm:px-4 py-3 bg-paper2 border border-rule rounded-card flex items-start justify-between gap-3 shrink-0 animate-fade">
      <div className="flex items-start gap-2.5 text-sm text-ink2 min-w-0">
        <RefreshCw size={16} className={`shrink-0 text-brass mt-0.5 ${fase === 'esperando' ? 'animate-spin' : ''}`} />
        <div className="min-w-0 space-y-2">
          <div>
            <span className="font-medium text-ink">O motor deste computador está atrás do site.</span>{' '}
            <span className="text-muted">
              Ele está na versão {versao}, e a mais nova é a {publicada}.
            </span>
          </div>
          {andamento && <p className="text-muted">{andamento}</p>}
          {problema && (
            <div
              key={problema.n}
              className="flex items-start gap-2 rounded-input border border-warn/40 bg-warn/10 px-3 py-2 text-ink2 animate-fade"
            >
              <AlertTriangle size={14} className="text-warn shrink-0 mt-0.5" />
              <div className="min-w-0">{problema.texto}</div>
            </div>
          )}
          {fase !== 'esperando' && (!problema || problema.deNovo) && (
            <button
              onClick={atualizar}
              disabled={ocupado}
              className="btn-primary px-4 py-2 text-xs"
            >
              {fase === 'pedindo' && <Loader2 size={14} className="animate-spin" />}
              {fase === 'pedindo' ? 'verificando…' : (problema ? 'tentar de novo' : 'atualizar agora')}
            </button>
          )}
        </div>
      </div>
      {!ocupado && (
        <button
          onClick={fechar}
          aria-label="Dispensar o aviso"
          className="p-1 rounded-input text-muted hover:text-ink transition-colors shrink-0"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}
