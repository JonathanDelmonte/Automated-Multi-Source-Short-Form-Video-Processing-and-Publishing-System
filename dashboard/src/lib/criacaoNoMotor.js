import { apiFetch } from './api';

// O vídeo criado por IA falando com o motor (etapa 7.7): o estilo do canal, a
// imagem de cada personagem, a amostra da voz e o pedido do vídeo. As frases
// de recusa vêm do motor (`app.py`, `criacoes.py`), já em português.
//
// Um motor de antes da 7.7 não tem as rotas: responde o 404 genérico do FastAPI
// ("Not Found") ou 405, e a tela diz para atualizar.

async function pedir(caminho, metodo = 'GET', corpo) {
  let res;
  try {
    res = await apiFetch(caminho, {
      method: metodo,
      headers: corpo === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    return { ok: false, status: 0, erro: 'Não consegui falar com o programa neste computador.' };
  }
  const data = await res.json().catch(() => ({}));
  if ((res.status === 404 && data.detail === 'Not Found') || res.status === 405) {
    return { ok: false, status: res.status, motorAntigo: true,
             erro: 'Atualize o programa para criar vídeos por IA.' };
  }
  if (!res.ok) {
    const detalhe = typeof data.detail === 'string' ? data.detail : null;
    return { ok: false, status: res.status, erro: detalhe || 'Não deu certo. Tente de novo.' };
  }
  return { ok: true, data };
}

const doEstilo = (canalId, resto = '') => `/api/canais/${canalId}/estilo${resto}`;

export const lerEstilo = (canalId) => pedir(doEstilo(canalId));

export const salvarEstilo = (canalId, spec) => pedir(doEstilo(canalId), 'PUT', { spec });

export const gerarPersonagem = (canalId, personagemId) =>
  pedir(doEstilo(canalId, `/personagens/${personagemId}/gerar`), 'POST', {});

export const enviarPersonagem = (canalId, personagemId, dataUrl) =>
  pedir(doEstilo(canalId, `/personagens/${personagemId}/imagem`), 'POST', { imagem: dataUrl });

export const criarVideo = (corpo) => pedir('/api/criacoes', 'POST', corpo);

export const continuarCriacao = (jobId) => pedir(`/api/criacoes/${jobId}/continuar`, 'POST', {});

// A amostra da voz vem em WAV: devolve um endereço que o <audio> toca.
export async function ouvirVoz(canalId, voz, instrucao) {
  let res;
  try {
    res = await apiFetch(doEstilo(canalId, '/ouvir'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voz, instrucao }),
    });
  } catch {
    return { ok: false, erro: 'Não consegui falar com o programa neste computador.' };
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { ok: false, erro: typeof data.detail === 'string' ? data.detail : 'A amostra não saiu.' };
  }
  return { ok: true, url: URL.createObjectURL(await res.blob()) };
}

// A imagem que a pessoa escolheu, reduzida AQUI a no máximo 1024 px de lado,
// sem cortar: o motor a reduz de novo a 512 para o modelo, e mandar a foto de
// celular inteira seria esperar o envio à toa. PNG guarda o fundo transparente
// (o motor o põe sobre branco); o resto vai em JPEG.
export async function reduzirSemCortar(arquivo, lado = 1024) {
  const endereco = URL.createObjectURL(arquivo);
  try {
    const imagem = await new Promise((resolver, recusar) => {
      const i = new Image();
      i.onload = () => resolver(i);
      i.onerror = () => recusar(new Error('não consegui ler essa imagem'));
      i.src = endereco;
    });
    const escala = Math.min(1, lado / Math.max(imagem.width, imagem.height));
    const tela = document.createElement('canvas');
    tela.width = Math.max(1, Math.round(imagem.width * escala));
    tela.height = Math.max(1, Math.round(imagem.height * escala));
    tela.getContext('2d').drawImage(imagem, 0, 0, tela.width, tela.height);
    return arquivo.type === 'image/png' ? tela.toDataURL('image/png') : tela.toDataURL('image/jpeg', 0.9);
  } finally {
    URL.revokeObjectURL(endereco);
  }
}
