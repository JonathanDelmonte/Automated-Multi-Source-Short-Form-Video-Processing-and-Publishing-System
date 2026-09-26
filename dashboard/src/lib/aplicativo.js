import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from './api';

// Quais cadastros de aplicativo existem no programa deste computador (etapa
// 7.3): `{ google: true, tiktok: false }`. É o que decide se o botão
// "conectar" de cada conta aparece, ou o link para cadastrar. `null` enquanto
// não se sabe -- e num motor de antes da 7.3, que não tem a rota. Para uma
// conta, `situacaoDoAplicativo(prontos, conta.platform)` (lib/conexoes.js).
export function useAplicativos() {
  const [prontos, setProntos] = useState(null);
  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/aplicativos');
      if (!res.ok) { setProntos(null); return; }
      const data = await res.json();
      const cadastros = data.aplicativos || {};
      setProntos(Object.fromEntries(
        Object.entries(cadastros).map(([plataforma, estado]) => [plataforma, !!estado?.configurado]),
      ));
    } catch {
      setProntos(null);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);
  return { prontos, carregar };
}
