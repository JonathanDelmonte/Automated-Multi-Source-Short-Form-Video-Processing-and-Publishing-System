import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from './api';

// Se o cadastro do aplicativo do Google existe no programa deste computador
// (etapa 7.3). É o que decide se o botão "conectar" de cada conta do YouTube
// aparece, ou o link para cadastrar. `null` enquanto não se sabe -- e num
// motor de antes da 7.3, que não tem a rota.
export function useAplicativoDoGoogle() {
  const [pronto, setPronto] = useState(null);
  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/aplicativos');
      if (!res.ok) { setPronto(null); return; }
      const data = await res.json();
      setPronto(!!data.aplicativos?.google?.configurado);
    } catch {
      setPronto(null);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);
  return { pronto, carregar };
}
