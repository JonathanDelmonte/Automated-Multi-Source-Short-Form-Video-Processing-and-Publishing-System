import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, Loader2, Trash2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import IconePlataforma from './ui/IconePlataforma';
import { MENSAGENS_DO_CADASTRO } from '../lib/conexoes';

// O cadastro do aplicativo do Google (etapa 7.3). Decisão do autor
// (26-set-2026): cada pessoa usa o próprio cadastro -- o projeto dela no
// Google Cloud --, como já faz com as chaves de IA. É o que deixa o "conectar"
// de cada conta do YouTube funcionar sem terminal.
//
// O passo a passo é o de verdade, na ordem em que o console do Google pede, e
// diz as duas pegadinhas que custam caro depois: o tipo do cliente ("App para
// computador") e a tela de consentimento "Em produção" (em "Teste", a conexão
// expira a cada 7 dias).

const PASSOS = [
  {
    texto: 'Entre no Google Cloud com a conta Google do canal e crie um projeto (qualquer nome, por exemplo "Virtu Clips").',
    link: 'https://console.cloud.google.com/projectcreate',
    rotulo: 'criar o projeto',
  },
  {
    texto: 'Ative a YouTube Data API v3 (para publicar) e a YouTube Analytics API (para medir).',
    link: 'https://console.cloud.google.com/apis/library/youtube.googleapis.com',
    rotulo: 'ativar a Data API',
    link2: 'https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com',
    rotulo2: 'ativar a Analytics API',
  },
  {
    texto: 'Configure a tela de consentimento: público "Externo", o nome do app e o seu e-mail. Depois, em "Público-alvo", coloque o app "Em produção" — em "Teste", a conexão expira a cada 7 dias. Na hora de conectar, o Google avisa que o app não foi verificado: para uso próprio, é só seguir em "Avançado".',
    link: 'https://console.cloud.google.com/auth/overview',
    rotulo: 'tela de consentimento',
  },
  {
    texto: 'Em "Clientes", crie um cliente OAuth do tipo "App para computador" (não "Aplicativo da Web"). Copie o ID do cliente e a chave secreta — ou baixe o JSON e cole ele inteiro no primeiro campo.',
    link: 'https://console.cloud.google.com/auth/clients',
    rotulo: 'criar o cliente',
  },
  {
    texto: 'Cole aqui e salve. Depois, em cada conta do YouTube (nos ajustes do canal ou em Configurações → contas), clique em "conectar".',
  },
];

export default function CadastroDoAplicativo() {
  const [estado, setEstado] = useState(undefined);
  const [clientId, setClientId] = useState('');
  const [segredo, setSegredo] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/aplicativos');
      if (res.status === 404) { setEstado(null); return; }  // motor de antes da 7.3
      const data = res.ok ? await res.json() : {};
      setEstado(data.aplicativos?.google || null);
    } catch {
      setEstado(null);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const enviar = async (corpo) => {
    setSalvando(true);
    setErro(null);
    setAviso(null);
    try {
      const res = await apiFetch('/api/aplicativos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plataforma: 'google', ...corpo }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro(MENSAGENS_DO_CADASTRO[data?.detail?.erro] || 'Não deu para salvar.');
        return;
      }
      setEstado(data.aplicativos?.google || null);
      setClientId('');
      setSegredo('');
      if (data.teste === 'incerto') {
        setAviso('Salvo. Não deu para conferir com o Google agora (sem internet?): se estiver errado, o conectar vai dizer.');
      }
    } catch {
      setErro('Não consegui falar com o programa.');
    } finally {
      setSalvando(false);
    }
  };

  // O JSON baixado do Google traz os dois campos: colado no primeiro, o
  // segundo não é preciso.
  const colouJson = clientId.trim().startsWith('{');
  const podeSalvar = !salvando && (colouJson || (clientId.trim() && segredo.trim()));

  if (estado === undefined) {
    return <Loader2 size={16} className="animate-spin text-muted" />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2.5">
        <IconePlataforma platform="youtube" size={20} />
        <h3 className="text-ink text-sm font-medium">Google (YouTube)</h3>
        {estado?.configurado && (
          <span className="ml-auto inline-flex items-center gap-1 text-xs text-ok">
            <CheckCircle2 size={13} /> cadastrado{estado.origem === 'arquivo' ? ' pelo arquivo .env' : ''}
          </span>
        )}
      </div>

      {estado === null && (
        <p className="text-muted text-[13px]">
          O programa deste computador ainda não sabe guardar o cadastro do aplicativo. Atualize o programa
          (o aviso no topo do site tem o botão).
        </p>
      )}

      {estado?.configurado && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-muted">ID do cliente:</span>
          <code className="text-ink2 break-all">{estado.client_id}</code>
          {estado.origem === 'site' && (
            <button type="button" className="text-muted hover:text-danger inline-flex items-center gap-1 text-xs ml-auto"
                    onClick={() => enviar({ remover: true })} disabled={salvando}>
              <Trash2 size={13} /> tirar
            </button>
          )}
        </div>
      )}

      {estado !== null && (
        <>
          <ol className="space-y-2.5 text-[13px] text-ink2 list-decimal pl-5">
            {PASSOS.map((p) => (
              <li key={p.texto} className="leading-snug">
                {p.texto}
                {p.link && (
                  <span className="block mt-1 space-x-3">
                    <a href={p.link} target="_blank" rel="noopener noreferrer"
                       className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink2 underline underline-offset-2">
                      <ExternalLink size={11} /> {p.rotulo}
                    </a>
                    {p.link2 && (
                      <a href={p.link2} target="_blank" rel="noopener noreferrer"
                         className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink2 underline underline-offset-2">
                        <ExternalLink size={11} /> {p.rotulo2}
                      </a>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ol>

          <form className="space-y-2" onSubmit={(e) => {
            e.preventDefault();
            if (podeSalvar) enviar(colouJson ? { client_id: clientId } : { client_id: clientId, client_secret: segredo });
          }}>
            <input
              className="input-field text-sm py-1.5 w-full"
              placeholder="ID do cliente (…apps.googleusercontent.com), ou o JSON baixado"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              aria-label="ID do cliente do Google"
            />
            {!colouJson && (
              <input
                className="input-field text-sm py-1.5 w-full"
                placeholder="chave secreta do cliente (GOCSPX-…)"
                value={segredo}
                onChange={(e) => setSegredo(e.target.value)}
                type="password"
                autoComplete="off"
                aria-label="chave secreta do cliente do Google"
              />
            )}
            <button type="submit" className="btn-primary text-sm" disabled={!podeSalvar}>
              {salvando ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              {estado?.configurado ? 'trocar o cadastro' : 'salvar'}
            </button>
          </form>
          <p className="text-muted text-[12px] leading-snug">
            O cadastro fica no programa deste computador, e a chave secreta nunca volta para o site. Até o
            Google aprovar a auditoria do seu projeto, os vídeos que o programa envia sobem como privados —
            você os deixa públicos no YouTube Studio, ou posta pelo pacote do dia.
          </p>
        </>
      )}
      {erro && <p className="text-danger text-[13px]">{erro}</p>}
      {aviso && <p className="text-brass text-[13px]">{aviso}</p>}
    </div>
  );
}
