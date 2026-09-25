// O ajudante e a versão publicada do motor (Fase 6.2).
//
// O site é só a tela; quem processa é o motor no computador de quem usa. Quem
// ainda não tem o motor baixa o ajudante daqui, e quem já tem fica sabendo
// quando o motor ficou para trás do site, com o botão que o atualiza
// (AvisoDoMotor.jsx) -- o ajudante também se atualiza sozinho, em até 6 horas.
//
// A versão publicada vem do GitHub Releases, o mesmo lugar de onde o ajudante
// se atualiza. É a contagem de commits da `main` (ver versao_do_motor.py), e
// só muda quando o MOTOR muda: um commit do painel não gera aviso.

const REPO = 'JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System';

export const URL_DO_INSTALADOR = `https://github.com/${REPO}/releases/latest/download/Instalar-Virtu-Clips.exe`;

const CHAVE = 'cortes_versao_publicada';
// Uma hora: a API do GitHub sem login atende 60 pedidos por hora por IP, e a
// versão nova não precisa aparecer no minuto em que sai.
const VALIDADE_MS = 60 * 60 * 1000;

// "463" < "463.1" < "464". Parte que não é número vale -1, como no
// ajudante/atualizacao.py.
const chave = (v) => String(v).trim().split('.').map((p) => (/^\d+$/.test(p) ? Number(p) : -1));

export const maisNova = (a, b) => {
  if (!a || !b) return false;
  const x = chave(a);
  const y = chave(b);
  for (let i = 0; i < Math.max(x.length, y.length); i += 1) {
    const d = (x[i] ?? -Infinity) - (y[i] ?? -Infinity);
    if (d !== 0) return d > 0;
  }
  return false;
};

// A versão mais nova publicada, ou null se não deu para saber (sem internet,
// GitHub fora, nenhuma publicada ainda). Nunca lança.
export async function versaoPublicada() {
  try {
    const salvo = JSON.parse(localStorage.getItem(CHAVE) || 'null');
    if (salvo && Date.now() - salvo.em < VALIDADE_MS) return salvo.versao;
  } catch { /* localStorage bloqueado: pergunta de novo */ }
  try {
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`, {
      headers: { Accept: 'application/vnd.github+json' },
    });
    if (!res.ok) return null;
    const tag = (await res.json()).tag_name || '';
    const versao = tag.startsWith('ajudante-') ? tag.slice('ajudante-'.length) : null;
    try {
      localStorage.setItem(CHAVE, JSON.stringify({ versao, em: Date.now() }));
    } catch { /* sem cache: tudo bem */ }
    return versao;
  } catch {
    return null;
  }
}
