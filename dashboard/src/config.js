// Configuration for API endpoints
// If VITE_API_URL is set (e.g. in production), use it.
// Otherwise, default to empty string which means relative paths (proxied in dev).
//
// No site do Cloudflare (`build:site`) sao DOIS motores possiveis, na ordem em
// que sao procurados (`VITE_API_URLS`): o do Docker, na 8000, e o do ajudante,
// na 8001 (Fase 6.2). Portas diferentes de proposito: no login os dois sobem
// juntos, e na mesma porta o container do Docker morreria em silencio. Quem
// responder primeiro a `/api/config` vira o servidor desta aba
// (`usarServidor`, chamado pelo AuthContext); o `export let` e uma ligacao
// viva, entao todo `getApiUrl` passa a usar o escolhido.
const CANDIDATOS = (import.meta.env.VITE_API_URLS || import.meta.env.VITE_API_URL || '')
    .split(',')
    .map((u) => u.trim().replace(/\/+$/, ''))
    .filter(Boolean);

export const SERVIDORES = CANDIDATOS.length ? CANDIDATOS : [''];

export let API_BASE_URL = SERVIDORES[0];

export const usarServidor = (base) => { API_BASE_URL = base; };

// Token curto para as URLs de mídia (Fase 4, bloco 4.3).
//
// Um `<video src>` ou `<img src>` não manda cabeçalho `Authorization`, então o
// player nunca carregaria a sessão — e com a auth ligada os bytes do clipe
// respondem 404. O token vai na query, e é curto de propósito: se vazar pelo
// log de acesso ou pelo `Referer`, expira sozinho, ao contrário da sessão de
// 30 dias. Quem o busca é o `AuthContext`, uma vez por sessão.
//
// **Um lugar só.** Se cada componente montasse a própria URL de mídia, o que
// esquecesse o token simplesmente não tocaria o vídeo — e o bug pareceria "o
// clipe sumiu", não "faltou autorização".
let mediaToken = '';

export const setMediaToken = (t) => { mediaToken = t || ''; };

const PREFIXOS_DE_MIDIA = ['/videos/'];

export const getApiUrl = (path) => {
    if (path.startsWith('http')) return path;
    // Ensure path starts with / if not present
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    const url = `${API_BASE_URL}${normalizedPath}`;
    if (mediaToken && PREFIXOS_DE_MIDIA.some((p) => normalizedPath.startsWith(p))) {
        return url + (url.includes('?') ? '&' : '?') + `mt=${encodeURIComponent(mediaToken)}`;
    }
    return url;
};
