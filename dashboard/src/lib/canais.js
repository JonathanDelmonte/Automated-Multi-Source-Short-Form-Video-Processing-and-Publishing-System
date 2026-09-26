import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from './api';

// Os canais no painel (Fase 7, etapa 7.1). O canal é a marca num nicho, com as
// contas de cada plataforma ligadas a ele; as regras moram no motor
// (`canais.py`), e aqui só se fala com ele.

// Um motor de antes dos canais não tem a rota, e responde 404: a tela diz para
// atualizar em vez de dizer "nenhum canal" -- que seria verdade só pela metade.
export async function listarCanais() {
  const res = await apiFetch('/api/canais');
  if (res.status === 404) return { canais: [], situacao: 'motor-antigo', detalhe: null };
  if (!res.ok) {
    const corpo = await res.json().catch(() => ({}));
    return { canais: [], situacao: 'erro', detalhe: typeof corpo.detail === 'string' ? corpo.detail : null };
  }
  const data = await res.json();
  return { canais: data.canais || [], situacao: 'ok', detalhe: null };
}

// A lista de canais do painel inteiro: carregada pelo App e recarregada por
// quem muda alguma coisa (criar, editar, apagar, mandar um vídeo para um canal
// -- a contagem de projetos vem junto).
//
// **Só com `ativo`**, que o App liga quando a sessão está pronta. O hook roda
// antes da tela de entrada (hooks não podem ficar depois de um `return`), e
// numa instalação com senha a primeira pergunta voltaria 401: a lista ficaria
// em erro depois do login, até alguém recarregar a página.
export function useListaDeCanais(ativo = true) {
  const [estado, setEstado] = useState({ canais: [], situacao: 'carregando', detalhe: null });
  const carregar = useCallback(async () => {
    try {
      setEstado(await listarCanais());
    } catch {
      setEstado((atual) => ({ ...atual, situacao: 'erro', detalhe: null }));
    }
  }, []);
  useEffect(() => { if (ativo) carregar(); }, [ativo, carregar]);
  const porId = useMemo(
    () => Object.fromEntries(estado.canais.map((c) => [c.id, c])), [estado.canais]);
  return useMemo(() => ({ ...estado, porId, carregar }), [estado, porId, carregar]);
}

async function pedir(caminho, metodo, corpo) {
  const res = await apiFetch(caminho, {
    method: metodo,
    headers: corpo === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detalhe = typeof data.detail === 'string' ? data.detail : null;
    return { ok: false, status: res.status, erro: detalhe || 'Não deu certo. Tente de novo.' };
  }
  return { ok: true, data };
}

// Criar (sem id) ou editar. O motor recusa com o motivo em texto, e é esse
// texto que a tela mostra.
export const salvarCanal = (id, dados) => (id
  ? pedir(`/api/canais/${id}`, 'PATCH', dados)
  : pedir('/api/canais', 'POST', dados));

export const apagarCanal = (id) => pedir(`/api/canais/${id}`, 'DELETE');

// Põe um projeto num canal, ou tira (`null`). Todo projeto de antes dos canais
// nasceu sem canal, e este é o caminho deles.
export const moverProjeto = (jobId, canalId) =>
  pedir(`/api/jobs/${jobId}/canal`, 'PUT', { channel_id: canalId || null });

// As iniciais do avatar "gerado": o canal sem imagem mostra as duas primeiras
// letras do nome sobre a cor dele.
export function iniciais(nome) {
  const palavras = String(nome || '').trim().split(/\s+/).filter(Boolean);
  if (!palavras.length) return '?';
  const letras = palavras.length === 1
    ? palavras[0].slice(0, 2)
    : palavras[0][0] + palavras[1][0];
  return letras.toUpperCase();
}

export const CORES_DO_CANAL = [
  '#e11d48', '#f97316', '#eab308', '#22c55e', '#14b8a6',
  '#3b82f6', '#8b5cf6', '#ec4899', '#a3a3a3',
];

// Os nichos que o autor citou, como sugestão -- o campo aceita qualquer um.
export const NICHOS_SUGERIDOS = [
  'infantil', 'filmes e séries', 'acidentes', 'fatos desconhecidos', 'finanças',
  'curiosidades', 'podcasts', 'games', 'esportes', 'humor',
];

export const IDIOMAS = [
  { id: 'pt-BR', nome: 'Português (Brasil)' },
  { id: 'pt-PT', nome: 'Português (Portugal)' },
  { id: 'en-US', nome: 'Inglês' },
  { id: 'es-ES', nome: 'Espanhol' },
];

// A imagem do canal é reduzida AQUI, a 256 px, antes de ir ao motor: ela viaja
// dentro da lista de canais, que o painel pede a cada tela, e uma foto de
// celular de 4 MB em cada resposta seria o painel inteiro lento. Recorta o
// centro (o avatar é redondo) e grava em webp; o navegador que não sabe
// escrever webp devolve png, e aí vale jpeg, que todos escrevem.
export async function reduzirImagem(arquivo, lado = 256) {
  const endereco = URL.createObjectURL(arquivo);
  try {
    const imagem = await new Promise((resolver, recusar) => {
      const i = new Image();
      i.onload = () => resolver(i);
      i.onerror = () => recusar(new Error('não consegui ler essa imagem'));
      i.src = endereco;
    });
    const tela = document.createElement('canvas');
    tela.width = lado;
    tela.height = lado;
    const ctx = tela.getContext('2d');
    const escala = Math.max(lado / imagem.width, lado / imagem.height);
    const w = imagem.width * escala;
    const h = imagem.height * escala;
    ctx.drawImage(imagem, (lado - w) / 2, (lado - h) / 2, w, h);
    const webp = tela.toDataURL('image/webp', 0.86);
    return webp.startsWith('data:image/webp') ? webp : tela.toDataURL('image/jpeg', 0.86);
  } finally {
    URL.revokeObjectURL(endereco);
  }
}
