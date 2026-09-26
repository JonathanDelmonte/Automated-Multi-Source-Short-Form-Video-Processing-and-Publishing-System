import React, { useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, Link2, Loader2, Unplug } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { API_BASE_URL } from '../config';
import { hrefDe } from '../lib/rota';
import { mensagemDe, origemDoMotor, voltaPossivel } from '../lib/conexoes';

// "Conectar YouTube" numa conta (etapa 7.3). Dois consentimentos, como o
// `youtube_oauth.py` sempre fez: um para PUBLICAR (sobe o vídeo, não lê) e
// outro para MEDIR (lê views e retenção, não publica). Duas credenciais
// pequenas em vez de uma grande.
//
// O clique abre a aba do Google ANTES de perguntar ao motor: aberta depois de
// um `await`, o bloqueador de pop-up a trataria como propaganda. Sem aba
// (bloqueada mesmo assim), o link aparece para clicar.
//
// Depois do consentimento, quem recebe a volta é o motor (ou o painel do
// Docker), não esta aba: por isso ela pergunta ao motor de 3 em 3 segundos se
// a conta já está conectada, por até 10 minutos.

const TIPOS = [
  { id: 'publicar', ligado: 'publica sozinho', botao: 'conectar para publicar',
    dica: 'O programa sobe os cortes sozinho, na hora marcada. Não lê nem apaga nada.' },
  { id: 'medir', ligado: 'mede as visualizações', botao: 'conectar para medir',
    dica: 'O programa lê as visualizações e a retenção dos cortes. Não publica nada.' },
];

const ESPERA_MAXIMA_MS = 10 * 60 * 1000;

export default function ConexaoDaConta({ conta, aplicativoPronto, aoMudar }) {
  const [esperando, setEsperando] = useState(null);
  const [erro, setErro] = useState(null);
  const [linkManual, setLinkManual] = useState(null);
  const [confirmando, setConfirmando] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  const conexao = conta?.conexao;
  const conectadoAgora = esperando && conexao?.[esperando];

  // Enquanto espera a volta do Google, pergunta ao motor.
  useEffect(() => {
    if (!esperando || conectadoAgora) return undefined;
    const inicio = Date.now();
    const t = setInterval(() => {
      if (Date.now() - inicio > ESPERA_MAXIMA_MS) {
        setEsperando(null);
        return;
      }
      aoMudar();
    }, 3000);
    return () => clearInterval(t);
  }, [esperando, conectadoAgora, aoMudar]);

  useEffect(() => {
    if (conectadoAgora) { setEsperando(null); setLinkManual(null); }
  }, [conectadoAgora]);

  // Motor de antes da 7.3 não diz o estado da conexão; conta de outra
  // plataforma ainda não conecta por aqui (TikTok vem na 7.3c).
  if (!conexao || conta.platform !== 'youtube') return null;

  const origem = origemDoMotor(API_BASE_URL, window.location.origin);
  const podeVoltar = voltaPossivel(origem);

  const conectar = async (tipo) => {
    setErro(null);
    setLinkManual(null);
    const aba = window.open('', '_blank');
    try {
      const res = await apiFetch(`/api/contas/${conta.id}/conectar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo, volta: origem }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (aba) aba.close();
        setErro(mensagemDe(data?.detail?.erro));
        return;
      }
      if (aba) {
        aba.opener = null;
        aba.location.href = data.url;
      } else {
        setLinkManual(data.url);
      }
      setEsperando(tipo);
    } catch {
      if (aba) aba.close();
      setErro('Não consegui falar com o programa.');
    }
  };

  const desconectar = async (tipo) => {
    setOcupado(true);
    setErro(null);
    try {
      const res = await apiFetch(`/api/contas/${conta.id}/conexao?tipo=${tipo}`, { method: 'DELETE' });
      if (!res.ok) setErro('Não deu para desconectar.');
      setConfirmando(null);
      await aoMudar();
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="space-y-1.5 text-[12px]">
      <div className="flex flex-wrap gap-1.5">
        {TIPOS.map((t) => {
          if (conexao[t.id]) {
            return confirmando === t.id ? (
              <span key={t.id} className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-rule2">
                <button type="button" className="text-danger" disabled={ocupado} onClick={() => desconectar(t.id)}>
                  desconectar
                </button>
                <button type="button" className="text-muted" onClick={() => setConfirmando(null)}>não</button>
              </span>
            ) : (
              <button
                key={t.id}
                type="button"
                title={`${t.dica} Clique para desconectar.`}
                onClick={() => setConfirmando(t.id)}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-rule2 text-ok hover:border-[color:var(--color-danger)]"
              >
                <CheckCircle2 size={13} /> {t.ligado}
              </button>
            );
          }
          if (!aplicativoPronto || !podeVoltar) return null;
          return (
            <button
              key={t.id}
              type="button"
              title={t.dica}
              onClick={() => conectar(t.id)}
              disabled={esperando === t.id}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-rule2 text-ink2 hover:text-ink hover:border-[color:var(--color-accent)]"
            >
              {esperando === t.id ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
              {esperando === t.id ? 'esperando o Google…' : t.botao}
            </button>
          );
        })}
      </div>
      {!aplicativoPronto && !(conexao.publicar && conexao.medir) && (
        <p className="text-muted">
          Para conectar, primeiro{' '}
          <a href={hrefDe('/configuracoes/aplicativos')} className="text-ink2 underline underline-offset-2">
            cadastre o aplicativo do Google
          </a>.
        </p>
      )}
      {aplicativoPronto && !podeVoltar && !(conexao.publicar && conexao.medir) && (
        <p className="text-muted">
          Para conectar, abra o painel neste computador (em localhost): o Google só devolve a conexão para ele.
        </p>
      )}
      {esperando && (
        <p className="text-muted">
          Autorize na aba do Google. Esta tela percebe sozinha quando terminar.
        </p>
      )}
      {linkManual && (
        <a href={linkManual} target="_blank" rel="noopener noreferrer"
           className="inline-flex items-center gap-1 text-ink2 underline underline-offset-2">
          <ExternalLink size={12} /> abrir a tela do Google
        </a>
      )}
      {erro && <p className="text-danger flex items-center gap-1"><Unplug size={12} /> {erro}</p>}
    </div>
  );
}
