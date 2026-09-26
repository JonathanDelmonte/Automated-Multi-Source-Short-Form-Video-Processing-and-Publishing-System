import React, { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Unplug } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { dadosDaVolta, mensagemDe } from '../lib/conexoes';
import { PLATAFORMAS } from '../lib/plataformas';

// A volta do consentimento no painel do Docker (etapa 7.3): a do Google
// (YouTube) e, desde a 7.3c, a do TikTok, que volta do mesmo jeito.
//
// No painel do Docker a API é relativa, e a volta chega à raiz do PAINEL (o
// Vite), com `?state=...&code=...`. Esta tela manda o código ao
// motor (`POST /api/oauth/volta`) e diz o resultado. No site do Cloudflare
// ela não aparece: lá quem recebe a volta é o próprio motor.
//
// Uma vez só por `state`: o StrictMode roda o efeito duas vezes no
// desenvolvimento, e o segundo envio voltaria "venceu", apagando da tela o
// "conectado" do primeiro.
const enviados = new Map();

function enviarUmaVez(dados) {
  if (!enviados.has(dados.state)) {
    enviados.set(dados.state, (async () => {
      const res = await apiFetch('/api/oauth/volta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(dados),
      });
      return res.json().catch(() => ({ ok: false }));
    })());
  }
  return enviados.get(dados.state);
}

export default function VoltaDoGoogle() {
  const [resultado, setResultado] = useState(null);

  useEffect(() => {
    let vivo = true;
    enviarUmaVez(dadosDaVolta(window.location.search))
      .then((r) => { if (vivo) setResultado(r); })
      .catch(() => { if (vivo) setResultado({ ok: false, codigo: null }); });
    return () => { vivo = false; };
  }, []);

  // Voltar ao painel TIRA a query: com ela, cada F5 reenviaria o código.
  const voltar = () => {
    window.location.replace(`${window.location.pathname}#/configuracoes/contas`);
  };

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center p-6">
      <div className="card p-8 max-w-md w-full text-center space-y-4">
        {resultado === null ? (
          <>
            <Loader2 size={26} className="mx-auto animate-spin text-muted" />
            <p className="text-ink">Terminando a conexão…</p>
          </>
        ) : resultado.ok ? (
          <>
            <CheckCircle2 size={28} className="mx-auto text-ok" />
            <p className="text-ink">
              {resultado.handle} está conectada para{' '}
              {resultado.tipo === 'medir' ? 'medir as visualizações' : 'publicar sozinha'}
              {PLATAFORMAS[resultado.plataforma] ? ` no ${PLATAFORMAS[resultado.plataforma].nome}` : ''}.
            </p>
          </>
        ) : (
          <>
            <Unplug size={26} className="mx-auto text-danger" />
            <p className="text-ink">Não conectou.</p>
            <p className="text-muted text-sm">{mensagemDe(resultado.codigo, { plataforma: resultado.plataforma })}</p>
          </>
        )}
        {resultado !== null && (
          <button type="button" className="btn-primary px-4 py-2 text-sm" onClick={voltar}>
            voltar ao Virtu Clips
          </button>
        )}
      </div>
    </div>
  );
}
