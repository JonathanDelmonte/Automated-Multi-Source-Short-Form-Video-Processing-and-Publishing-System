// As regras puras da tela da frota (etapa 7.9, ADR-016), sem React e sem
// `window`: o teste as roda no `node` (tests/test_painel_da_frota.py). Quem
// fala com o motor é o `frotaNoMotor.js`.

// O padrão e o teto de posts por dia de cada conta, os mesmos do motor
// (`db_models.LIMITE_DIARIO_*`): 15 é o que a via oficial do TikTok, a mais
// apertada, aceita. A tela usa os que o motor manda; estes são a reserva.
export const LIMITE_PADRAO = 3;
export const LIMITE_MAXIMO = 15;

export const TIPOS = {
  cabo: 'pelo cabo',
  rede: 'pela rede de casa',
  nuvem: 'em nuvem',
};

// O comando que instala o adb do Google no Windows, uma vez.
export const INSTALAR_ADB = 'winget install --id Google.PlatformTools';

// O que fazer quando o motor não alcança o servidor do adb. No Docker, o adb é o
// do Windows (o container chega a ele pelo `host.docker.internal`); no
// ajudante, é o desta máquina, e o motor tenta ligá-lo sozinho.
export function ajudaDoAdb(adb) {
  if (!adb || adb.alcancado) return null;
  if (adb.docker) {
    return {
      titulo: 'O programa não alcançou o adb do Windows',
      passos: [
        `Instale o adb no Windows, uma vez, num terminal: ${INSTALAR_ADB}`,
        'Abra o atalho celulares.bat, na pasta atalhos do projeto: ele liga o adb e mostra os aparelhos.',
        'Volte aqui: a página pergunta de novo sozinha.',
      ],
    };
  }
  if (adb.adb_nesta_maquina) {
    return {
      titulo: 'O adb está instalado, mas não respondeu',
      passos: [
        'Feche e abra o ajudante (o ícone perto do relógio): ele liga o adb ao abrir a frota.',
        'Se continuar, abra um terminal e rode: adb start-server',
      ],
    };
  }
  return {
    titulo: 'Falta o adb, a ferramenta do Google que fala com o celular',
    passos: [
      `Instale, uma vez, num terminal do Windows: ${INSTALAR_ADB}`,
      'Feche e abra o ajudante: ele acha o adb sozinho.',
    ],
  };
}

// As etiquetas do estado ao vivo de um aparelho.
export function resumoDoEstado(estado) {
  if (!estado) return [];
  if (estado.no_ar === false) return [{ texto: 'fora do ar', tipo: 'erro' }];
  const saida = [];
  const bateria = estado.bateria || {};
  if (bateria.nivel != null) {
    const baixa = bateria.nivel < 20 && !bateria.carregando;
    saida.push({ texto: `${bateria.nivel}%${bateria.carregando ? ' carregando' : ''}`,
                 tipo: baixa ? 'aviso' : 'ok' });
  }
  if (estado.bloqueado === true) saida.push({ texto: 'tela bloqueada', tipo: 'aviso' });
  if (estado.espaco_livre_mb != null && estado.espaco_livre_mb < 500) {
    saida.push({ texto: 'pouco espaço', tipo: 'aviso' });
  }
  if (estado.adbkeyboard === false) saida.push({ texto: 'sem ADBKeyBoard', tipo: 'info' });
  return saida;
}

// Pode ligar o automático desta plataforma neste aparelho? As três travas do
// motor menos o consentimento, que é a pessoa quem dá na hora.
export function situacaoDoAutomatico(aparelho, plataforma) {
  const roteiro = aparelho?.roteiros?.[plataforma];
  if (!roteiro) return { pode: false, motivo: 'ensine o app neste aparelho primeiro' };
  if (roteiro.ensaio_ok !== true) {
    return { pode: false,
             motivo: roteiro.ensaio_ok === false
               ? 'o último ensaio não passou: ensine de novo ou ensaie outra vez'
               : 'ensaie o roteiro: o automático só liga com o ensaio passando' };
  }
  return { pode: true, motivo: '' };
}

export function textoDaConta(conta) {
  const quem = conta.modo === 'automatico' ? 'o motor publica' : 'você publica';
  return `${quem} · ${conta.hoje ?? 0} de ${conta.limite} hoje`;
}

export function descricaoDoPasso(passo) {
  if (passo.tipo === 'legenda') return 'tocar no campo da legenda, e o motor digita';
  if (passo.tipo === 'publicar') return `publicar em ${passo.descricao} (o ensaio para antes)`;
  return `tocar em ${passo.descricao}`;
}

// O ponto clicado na imagem da tela, em fração dela (0 a 1 nos dois eixos):
// é o que o motor converte para o tamanho real do aparelho.
export function pontoNaImagem(clientX, clientY, caixa) {
  const fx = (clientX - caixa.left) / Math.max(1, caixa.width);
  const fy = (clientY - caixa.top) / Math.max(1, caixa.height);
  const limitar = (v) => Math.min(1, Math.max(0, v));
  return { x: limitar(fx), y: limitar(fy) };
}

// As contas que podem ir para este aparelho: das plataformas que a frota sabe
// abrir, e que ainda não têm conta da mesma plataforma nele.
export function contasParaLigar(contas, plataformas, aparelho) {
  const ocupadas = new Set((aparelho?.contas || []).map((c) => c.platform));
  const daqui = new Set((aparelho?.contas || []).map((c) => c.account_id));
  return (contas || []).filter((c) => (plataformas || []).includes(c.platform)
    && !ocupadas.has(c.platform) && !daqui.has(c.id));
}

const SITUACOES = {
  entregue: { texto: 'entregue: esperando você publicar', tipo: 'ok' },
  publicado: { texto: 'publicado pelo aparelho', tipo: 'ok' },
  passou: { texto: 'o ensaio passou', tipo: 'ok' },
  parou: { texto: 'o automático parou', tipo: 'aviso' },
  duvida: { texto: 'confira no app se saiu', tipo: 'aviso' },
  falhou: { texto: 'não passou', tipo: 'erro' },
  'nao-saiu': { texto: 'não chegou ao aparelho', tipo: 'erro' },
};

export function situacaoDaExecucao(situacao) {
  return SITUACOES[situacao] || { texto: situacao || 'em andamento', tipo: 'info' };
}

export const TIPOS_DE_EXECUCAO = {
  entrega: 'entrega',
  automatico: 'post automático',
  ensaio: 'ensaio',
};
