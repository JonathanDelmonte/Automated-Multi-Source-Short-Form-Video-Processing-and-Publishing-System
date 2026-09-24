// Mantém o modelo de transcrição carregado na placa enquanto o painel está
// aberto (24-set-2026).
//
// O modelo mora num processo do servidor (`asr_residente.py`) que se desliga
// sozinho depois de alguns minutos sem uso. Este aviso — ao abrir, ao voltar
// para a aba e a cada 2 minutos — é o "uso" que o segura. O modelo é do
// SERVIDOR, não da aba: várias abas ou várias pessoas mandando o aviso seguram
// o MESMO modelo.
//
// Falha em silêncio de propósito. Sem o aviso nada quebra: o vídeo ainda sai,
// só que o job carrega o modelo sozinho, como fazia antes.
import { useEffect } from 'react';
import { apiFetch } from './api';

const INTERVALO_MS = 2 * 60 * 1000;

function avisar() {
  apiFetch('/api/asr/aquecer', { method: 'POST' }).catch(() => {});
}

export function useAquecerTranscricao(ativo) {
  useEffect(() => {
    if (!ativo) return undefined;
    avisar();
    const id = setInterval(avisar, INTERVALO_MS);
    const aoVoltar = () => {
      if (document.visibilityState === 'visible') avisar();
    };
    document.addEventListener('visibilitychange', aoVoltar);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', aoVoltar);
    };
  }, [ativo]);
}
