// A sessão do painel: a config do motor (`/api/config`), quem está logado e a
// entrada pela auth própria (Fase 4: e-mail e senha, `auth.py`).
//
// O login do projeto original -- link mágico por e-mail e Google -- saiu na
// limpeza da 7.1 (26-set-2026): os endpoints que ele chamava moravam no módulo
// comercial, que saiu no ADR-001, e o código ficou aqui sem ter com quem falar.
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getApiUrl, setMediaToken, SERVIDORES, usarServidor } from '../config';
import { apiJson, getToken, setToken, clearToken } from '../lib/api';

const AuthContext = createContext(null);
// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [config, setConfig] = useState({ authAtiva: false });
  const [me, setMe] = useState(null);           // /api/me payload, or null when signed out
  const [loading, setLoading] = useState(true);
  // `/api/config` já respondeu pelo menos uma vez. Antes disso nada que a
  // config decide (auth, chave de LLM) pode ser afirmado -- nem negado.
  const [configCarregada, setConfigCarregada] = useState(false);

  const refreshMe = useCallback(async () => {
    if (!getToken()) { setMe(null); return null; }
    try {
      const data = await apiJson('/api/me');
      setMe(data);
      return data;
    } catch (e) {
      // Stale/invalid token: drop it and fall back to anonymous BYOK.
      clearToken();
      setMe(null);
      return null;
    }
  }, []);

  // O token curto das URLs de mídia. Sem ele, com a auth ligada, todo `<video>`
  // do painel volta 404 — o player não tem como mandar cabeçalho.
  //
  // **Declarado ANTES do efeito que o usa, e isso não é estilo.** Ele estava
  // 45 linhas abaixo, e o array de dependências do efeito (que o React avalia
  // durante o render, não depois) referenciava esta `const` enquanto ela ainda
  // estava na zona morta temporal. O resultado era
  // `ReferenceError: Cannot access 'pegarMediaToken' before initialization`
  // dentro do `AuthProvider`, que embrulha o app inteiro: o `#root` ficava
  // vazio e o painel abria em PRETO, sem mensagem nenhuma (17-set-2026).
  //
  // O `npm run build` não pega: o import resolve e a sintaxe está correta. O
  // ESLint também não, porque a regra que veria isso (`no-use-before-define`)
  // não está ligada. Quem pega é abrir a página.
  const pegarMediaToken = useCallback(async () => {
    try {
      const data = await apiJson('/api/media-token');
      setMediaToken(data.token);
    } catch {
      setMediaToken('');
    }
  }, []);

  useEffect(() => {
    let vivo = true;
    (async () => {
      // Tenta até o servidor responder. Era uma tentativa só, e a falha virava
      // "config padrão": sem `localLlm`, o painel concluía que não havia chave
      // de LLM e pedia uma (22-set-2026). É exatamente o que acontece logo
      // depois do `atualizar.bat`, quando o painel volta antes do backend -- e
      // um F5 "consertava", porque aí o backend já estava de pé.
      //
      // No site, a cada volta pergunta aos dois motores possiveis (Docker e
      // ajudante, ver config.js), na ordem, e fica com o primeiro que
      // responder.
      let cfg = null;
      for (let tentativa = 0; vivo && !cfg; tentativa += 1) {
        for (const base of SERVIDORES) {
          try {
            const res = await fetch(`${base}/api/config`);
            if (!res.ok) throw new Error(`config ${res.status}`);
            cfg = await res.json();
            usarServidor(base);
            break;
          } catch (_) { /* o proximo, ou a proxima volta */ }
        }
        if (!cfg) await new Promise((r) => setTimeout(r, Math.min(1000 * 2 ** tentativa, 5000)));
      }
      if (!vivo) return;
      setConfig(cfg);
      setConfigCarregada(true);
      try {
        // Com a auth ligada, quem tem token válido volta logado: sem o
        // `refreshMe` no boot, `me` ficava nulo e a pessoa caía na tela de
        // login para sempre (Fase 4).
        if (cfg.authAtiva) {
          await refreshMe();
          await pegarMediaToken();
        }
      } catch (_) { /* sessão inválida: o refreshMe já limpa o token */ }
      setLoading(false);
    })();
    return () => { vivo = false; };
  }, [refreshMe, pegarMediaToken]);

  const logout = useCallback(() => {
    clearToken();
    setMediaToken('');
    setMe(null);
  }, []);

  // --- Auth própria (Fase 4) -------------------------------------------------

  // Recarrega `authAtiva` do servidor. Chamado depois do bootstrap, quando a
  // resposta de `/api/config` de antes já está desatualizada por definição.
  const refreshConfig = useCallback(async () => {
    try {
      const res = await fetch(getApiUrl('/api/config'));
      if (!res.ok) return null;
      const cfg = await res.json();
      setConfig(cfg);
      setConfigCarregada(true);
      return cfg;
    } catch {
      return null;
    }
  }, []);

  const entrar = useCallback(async (email, senha) => {
    const data = await apiJson('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, senha }),
    });
    setToken(data.token);
    await refreshMe();
    await pegarMediaToken();
    return data;
  }, [refreshMe, pegarMediaToken]);

  // Só responde enquanto a instalação não tem dono. Não cria conta: dá senha e
  // e-mail ao usuário que o seed já criou e que já é dono de tudo em disco.
  const definirDono = useCallback(async (email, senha) => {
    const data = await apiJson('/api/auth/bootstrap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, senha }),
    });
    setToken(data.token);
    await refreshConfig();
    await refreshMe();
    await pegarMediaToken();
    return data;
  }, [refreshMe, refreshConfig, pegarMediaToken]);

  const value = {
    localLlm: config.localLlm || null,
    // O programa deste computador tem chave do Gemini (do .env ou colada nas
    // Configurações): o navegador não precisa ter a dele.
    geminiNoMotor: !!config.geminiNoMotor,
    // Versão e origem do motor (ajudante, docker, codigo): o AvisoDoMotor
    // compara com a publicada.
    motor: config.motor || null,
    configCarregada,
    jobRetentionSeconds: config.jobRetentionSeconds || null,
    loading,
    me,
    // `user_id` é o campo do `/api/me` da Fase 4.
    isSignedIn: !!me?.user_id,
    authAtiva: !!config.authAtiva,
    refreshMe,
    refreshConfig,
    entrar,
    definirDono,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
