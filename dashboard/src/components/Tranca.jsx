import React, { useState } from 'react';
import { Lock, Loader2, AlertTriangle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

// A porta de entrada (Fase 4, bloco 4.1).
//
// Uma tela só, com dois modos, porque são dois momentos da mesma instalação e
// nunca coexistem: enquanto ninguém tem senha, ela **define o dono**; depois,
// ela pede login. Quem decide qual é `authAtiva`, que vem do `/api/config` —
// e não uma escolha do usuário, que não tem como saber em qual estado está.
//
// **Definir o dono não cria conta.** O backend dá senha e e-mail ao usuário que
// o seed já criou e que já é dono de tudo em disco — jobs, templates, contas,
// publicações. Criar um usuário novo aqui deixaria o trabalho de ontem
// pertencendo a alguém em quem ninguém consegue entrar. A tela diz isso.
//
// Pequena de propósito, como o resto do que foi acrescentado ao painel: o
// frontend vai ser trocado, e o que é durável aqui é o contrato do backend.

export default function Tranca() {
  const { authAtiva, entrar, definirDono } = useAuth();
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState(null);
  const [ocupado, setOcupado] = useState(false);

  const primeiroAcesso = !authAtiva;

  const enviar = async (e) => {
    e.preventDefault();
    setOcupado(true);
    setErro(null);
    try {
      if (primeiroAcesso) await definirDono(email.trim(), senha);
      else await entrar(email.trim(), senha);
    } catch (err) {
      setErro(err?.detail || 'Não consegui entrar. Tente de novo.');
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="min-h-screen bg-paper flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center space-y-2">
          <img src="/virtu-clips.png" alt="" className="mx-auto h-24 w-auto" />
          <h1 className="sr-only">Virtu Clips</h1>
          <p className="text-muted text-[13px] leading-snug">
            {primeiroAcesso
              ? 'Esta instalação ainda não tem dono. Escolha um e-mail e uma senha — o projeto que já está aqui continua sendo seu.'
              : 'Entre para continuar.'}
          </p>
        </div>

        <form className="card p-4 space-y-3" onSubmit={enviar}>
          <label className="block space-y-1">
            <span className="text-muted text-xs">e-mail</span>
            <input
              className="input-field text-sm w-full"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label className="block space-y-1">
            <span className="text-muted text-xs">senha</span>
            <input
              className="input-field text-sm w-full"
              type="password"
              autoComplete={primeiroAcesso ? 'new-password' : 'current-password'}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
              minLength={primeiroAcesso ? 10 : undefined}
            />
            {primeiroAcesso && (
              <span className="text-muted text-[11px]">
                Pelo menos 10 caracteres. Depois desta tela, ela é a única coisa
                entre a internet e a sua ferramenta.
              </span>
            )}
          </label>

          {erro && (
            <p className="text-danger text-[13px] flex items-start gap-1.5">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" />
              <span>{erro}</span>
            </p>
          )}

          <button
            className="btn-primary text-sm w-full inline-flex items-center justify-center gap-2"
            type="submit"
            disabled={ocupado}
          >
            {ocupado ? <Loader2 size={14} className="animate-spin" />
                     : <Lock size={14} />}
            {primeiroAcesso ? 'definir dono' : 'entrar'}
          </button>
        </form>

        {primeiroAcesso && (
          <p className="text-muted text-[11px] text-center leading-snug">
            Enquanto ninguém tem senha, qualquer um na rede alcança esta
            ferramenta. Defina o dono antes de expô-la.
          </p>
        )}
      </div>
    </div>
  );
}
