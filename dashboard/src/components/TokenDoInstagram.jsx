import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ExternalLink, KeyRound, Loader2, Unplug } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { mensagemDoToken } from '../lib/conexoes';

// "Medir" no Instagram (etapa 7.4): o token COLADO. A Meta só devolve o login
// para endereço HTTPS cadastrado, e o programa atende em http://localhost --
// então, em vez do botão de conectar, a pessoa gera o token no painel do app
// dela na Meta e cola aqui. O motor confere com o Instagram de quem é o token
// antes de guardar: de outra conta, é recusado.
//
// O token nunca volta do motor, e o campo é de senha: é uma credencial viva.

const PAINEL_DA_META = 'https://developers.facebook.com/apps/';

export default function TokenDoInstagram({ conta, aoMudar }) {
  const conexao = conta?.conexao || {};
  const [aberto, setAberto] = useState(false);
  const [guia, setGuia] = useState(false);
  const [token, setToken] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [confirmando, setConfirmando] = useState(false);

  const guardar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    setErro(null);
    try {
      const res = await apiFetch(`/api/contas/${conta.id}/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detalhe = data?.detail || {};
        setErro(mensagemDoToken(detalhe.erro, { conta: detalhe.conta, handle: conta.handle }));
        return;
      }
      setToken('');
      setAberto(false);
      await aoMudar();
    } catch {
      setErro('Não consegui falar com o programa.');
    } finally {
      setSalvando(false);
    }
  };

  const desconectar = async () => {
    setSalvando(true);
    try {
      await apiFetch(`/api/contas/${conta.id}/conexao?tipo=medir`, { method: 'DELETE' });
      setConfirmando(false);
      await aoMudar();
    } finally {
      setSalvando(false);
    }
  };

  if (conexao.medir && !aberto) {
    return confirmando ? (
      <span className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-rule2 text-[12px]">
        <button type="button" className="text-danger" disabled={salvando} onClick={desconectar}>tirar o token</button>
        <button type="button" className="text-muted" onClick={() => setConfirmando(false)}>não</button>
      </span>
    ) : (
      <button
        type="button"
        title="O programa lê as visualizações, curtidas, comentários, compartilhamentos e salvamentos dos reels. Não publica nada. Clique para tirar o token."
        onClick={() => setConfirmando(true)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-rule2 text-ok text-[12px] hover:border-[color:var(--color-danger)]"
      >
        <CheckCircle2 size={13} /> mede os números
      </button>
    );
  }

  return (
    <div className="space-y-1.5 text-[12px]">
      {conexao.medir_vencido && !aberto && (
        <p className="text-warn flex gap-1">
          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
          O token de medir venceu ou foi revogado. Cole um novo para voltar a medir.
        </p>
      )}
      {!aberto ? (
        <button
          type="button"
          onClick={() => setAberto(true)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-rule2 text-ink2 hover:text-ink hover:border-[color:var(--color-accent)]"
        >
          <KeyRound size={13} /> {conexao.medir_vencido ? 'colar um token novo' : 'colar o token para medir'}
        </button>
      ) : (
        <form onSubmit={guardar} className="space-y-2 p-2.5 rounded-input border border-rule2">
          <button type="button" onClick={() => setGuia((v) => !v)} aria-expanded={guia}
                  className="inline-flex items-center gap-1 text-ink2 hover:text-ink">
            <ChevronDown size={13} className={`transition-transform ${guia ? 'rotate-180' : ''}`} /> como gerar o token
          </button>
          {guia && (
            <ol className="list-decimal pl-4 space-y-1 text-muted leading-snug">
              <li>
                A conta precisa ser <span className="text-ink2">profissional</span> (criador de conteúdo ou empresa),
                no próprio app do Instagram.
              </li>
              <li>
                No{' '}
                <a href={PAINEL_DA_META} target="_blank" rel="noopener noreferrer" className="text-ink2 underline underline-offset-2">
                  painel de apps da Meta <ExternalLink size={10} className="inline" />
                </a>
                , crie um app com o caso de uso de gerenciar mensagens e conteúdo no Instagram.
              </li>
              <li>
                Em <span className="text-ink2">Instagram → configuração da API com login do Instagram</span>, deixe marcadas
                as permissões <code className="text-ink2 break-all">instagram_business_basic</code> e{' '}
                <code className="text-ink2 break-all">instagram_business_manage_insights</code>.
              </li>
              <li>
                Enquanto o app estiver em desenvolvimento, a conta entra como <span className="text-ink2">testadora</span>:
                em Funções do app, convide a conta, e aceite o convite no Instagram (Configurações → Apps e sites).
              </li>
              <li>
                Em <span className="text-ink2">gerar tokens de acesso</span>, adicione a conta {conta.handle}, clique em
                gerar token, copie e cole aqui.
              </li>
            </ol>
          )}
          <label className="block">
            <span className="sr-only">token do Instagram</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="cole o token aqui"
              className="w-full px-2.5 py-1.5 rounded-input bg-paper border border-rule2 text-ink placeholder:text-muted focus:border-[color:var(--color-accent)] outline-none"
            />
          </label>
          <p className="text-muted leading-snug">
            O token dura 60 dias, e o programa o renova sozinho uma vez por semana enquanto este computador ligar.
            Ele só lê os números da conta: não publica nada.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <button type="submit" className="btn-primary px-3 py-1.5 text-xs" disabled={salvando || token.trim().length < 20}>
              {salvando ? <Loader2 size={13} className="animate-spin" /> : <KeyRound size={13} />} guardar
            </button>
            <button type="button" className="btn-quiet px-3 py-1.5 text-xs" onClick={() => { setAberto(false); setErro(null); }}>
              cancelar
            </button>
          </div>
        </form>
      )}
      {erro && <p className="text-danger flex gap-1"><Unplug size={12} className="shrink-0 mt-0.5" /> {erro}</p>}
    </div>
  );
}
