// Auth + billing session state for cloud mode.
// - Reads /api/config to learn whether billing is enabled at all.
// - Handles the magic-link and Google OAuth redirect hashes.
// - Exposes the current user, plan and minute balance to the app.
// When billingEnabled is false the provider is inert and the app behaves as the
// classic BYOK dashboard.
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getApiUrl } from '../config';
import { apiFetch, apiJson, getToken, setToken, clearToken } from '../lib/api';
import { track, identify, reset as resetAnalytics } from '../lib/analytics';
import { report as reportAttribution } from '../lib/attribution';

const AuthContext = createContext(null);
// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [config, setConfig] = useState({ billingEnabled: false, googleAuthEnabled: false, authAtiva: false });
  const [me, setMe] = useState(null);           // /api/me payload, or null when signed out
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);

  const refreshMe = useCallback(async () => {
    if (!getToken()) { setMe(null); return null; }
    try {
      const data = await apiJson('/api/me');
      setMe(data);
      // Same profileId (user uuid) the server-side events use.
      identify(data?.user, { plan: data?.plan || 'free' });
      return data;
    } catch (e) {
      // Stale/invalid token: drop it and fall back to anonymous BYOK.
      clearToken();
      setMe(null);
      return null;
    }
  }, []);

  // Handle auth redirect hashes: #/auth/verify?ml=... and #/auth/callback?token=...
  const handleAuthHash = useCallback(async () => {
    const hash = window.location.hash || '';
    const match = hash.match(/^#\/auth\/(verify|callback)\??(.*)$/);
    if (!match) return false;
    const [, kind, query] = match;
    const params = new URLSearchParams(query);

    setSigningIn(true);
    let destination = '#app';
    try {
      if (kind === 'callback') {
        const token = params.get('token');
        if (token) {
          setToken(token);
          // Scrub the token from the URL immediately (replaceState, no new
          // history entry) so the bearer token isn't left reachable via Back.
          try {
            window.history.replaceState(null, document.title,
              window.location.pathname + window.location.search);
          } catch (_) { /* ignore */ }
        }
      } else if (kind === 'verify') {
        const ml = params.get('ml');
        if (ml) {
          const data = await apiJson('/api/auth/magic-link/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: ml }),
          });
          if (data.token) setToken(data.token);
        }
      }
      const signedInMe = await refreshMe();
      // This handler only runs on the auth redirect, so a resolved user here is
      // a fresh sign-in / sign-up — the top of the conversion funnel.
      if (signedInMe?.user) {
        track('Signup', { props: { method: kind === 'verify' ? 'magic_link' : 'google' } });
        // Server-side twin of the Signup event: the one place we learn which
        // channel produced an account. Awaited but never allowed to throw.
        await reportAttribution(apiJson);
      }
      // Everyone lands in the app. First-time (unpaid) sign-in gets the Clip
      // Generator tutorial, not a pricing dump — they need one successful job
      // before the rest of the tools unlock. os_welcomed keeps this once-only
      // even if they skip the tutorial.
      const paid = ['starter', 'creator', 'pro'].includes(signedInMe?.plan);
      let welcomed = false;
      try { welcomed = localStorage.getItem('os_welcomed') === '1'; } catch (_) { /* ignore */ }
      if (signedInMe?.user && !paid && !welcomed) {
        try {
          localStorage.setItem('os_show_clip_tutorial', '1');
          localStorage.setItem('os_welcomed', '1');
        } catch (_) { /* ignore */ }
      }
    } catch (e) {
      // fall through — user lands signed-out
    } finally {
      setSigningIn(false);
      // Clear the sensitive hash, land wherever we resolved above.
      window.location.hash = destination;
    }
    return true;
  }, [refreshMe]);

  useEffect(() => {
    (async () => {
      try {
        const cfg = await (await fetch(getApiUrl('/api/config'))).json();
        setConfig(cfg);
        // `authAtiva` entrou aqui na Fase 4, e não é detalhe: `billingEnabled`
        // é sempre falso neste fork (ADR-001), então sem esta segunda condição
        // o `refreshMe` nunca rodava no boot — e quem tinha token válido caía
        // na tela de login para sempre, porque `me` ficava nulo.
        if (cfg.billingEnabled || cfg.authAtiva) {
          const handled = cfg.billingEnabled ? await handleAuthHash() : false;
          if (!handled) await refreshMe();
        }
      } catch (_) { /* config fetch failed — stay in BYOK */ }
      setLoading(false);
    })();
  }, [handleAuthHash, refreshMe]);

  const requestMagicLink = useCallback(async (email) => {
    const res = await apiFetch('/api/auth/magic-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (res.status === 429) throw new Error('Too many attempts. Try again in a few minutes.');
    if (!res.ok) throw new Error('Could not send sign-in link.');
    return true;
  }, []);

  const loginWithGoogle = useCallback(() => {
    window.location.href = getApiUrl('/api/auth/google');
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setMe(null);
    resetAnalytics();
  }, []);

  // --- Auth própria (Fase 4) -------------------------------------------------
  // O magic-link e o Google acima morreram com o `cloud/` (ADR-001): os
  // endpoints que eles chamam não existem mais neste fork. Ficam no arquivo
  // porque o frontend inteiro vai ser trocado e apagá-los agora seria mexer em
  // código marcado para sair. O que funciona é isto.

  // Recarrega `authAtiva` do servidor. Chamado depois do bootstrap, quando a
  // resposta de `/api/config` de antes já está desatualizada por definição.
  const refreshConfig = useCallback(async () => {
    try {
      const cfg = await (await fetch(getApiUrl('/api/config'))).json();
      setConfig(cfg);
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
    return data;
  }, [refreshMe]);

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
    return data;
  }, [refreshMe, refreshConfig]);

  const value = {
    billingEnabled: config.billingEnabled,
    localLlm: config.localLlm || null,
    googleAuthEnabled: config.googleAuthEnabled,
    jobRetentionSeconds: config.jobRetentionSeconds || null,
    loading,
    signingIn,
    user: me?.user || null,
    me,
    plan: me?.plan || null,
    entitled: !!me?.entitled,
    minutes: me?.minutes || null,
    // `user_id` é o campo do `/api/me` desta fase; `user` era o do cloud.
    isSignedIn: !!(me?.user_id || me?.user),
    authAtiva: !!config.authAtiva,
    // Managed = signed-in AND entitled (active plan or top-up credit).
    isManaged: !!(config.billingEnabled && me?.entitled),
    refreshMe,
    refreshConfig,
    entrar,
    definirDono,
    requestMagicLink,
    loginWithGoogle,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
