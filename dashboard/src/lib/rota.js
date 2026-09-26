import { useEffect, useState } from 'react';
import { hrefDe, lerRota } from './endereco';

// O endereço de cada tela (Fase 7, etapa 7.1): `#/canais/<id>/agenda`.
//
// Antes, a aba aberta só existia na memória da página: voltar, recarregar ou
// mandar o link de uma tela caía sempre no começo. Com canais, cada um com sete
// abas, isso deixou de ser detalhe.
//
// **Depois do `#`** porque o site é estático no Cloudflare: um caminho de
// verdade (`/canais/x`) pediria ao servidor uma página que não existe. E **feito
// à mão, sem biblioteca**: toda dependência nova do painel muda o
// `package.json`, e o botão "atualizar agora" do Docker recusa essa mudança
// (reconstruir a imagem, 40 minutos). O que se precisa aqui cabe em trinta
// linhas.

export { lerRota, hrefDe };

export function ir(caminho) {
  const destino = hrefDe(caminho);
  if (window.location.hash !== destino) window.location.hash = destino;
}

export function useRota() {
  const [rota, setRota] = useState(() => lerRota(window.location.hash));
  useEffect(() => {
    const aoMudar = () => setRota(lerRota(window.location.hash));
    window.addEventListener('hashchange', aoMudar);
    return () => window.removeEventListener('hashchange', aoMudar);
  }, []);
  return rota;
}
