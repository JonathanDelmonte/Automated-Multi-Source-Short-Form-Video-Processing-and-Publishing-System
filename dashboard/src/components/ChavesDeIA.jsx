import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Check, ChevronDown, ExternalLink, Eye, EyeOff, KeyRound, Loader2, Trash2,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { apiFetch } from '../lib/api';
import { PROVEDORES } from '../lib/provedoresDeIA';

// As chaves de IA nas Configurações (25-set-2026, chaves_ia.py).
//
// Um bloco por IA gratuita, com o botão que abre a página onde se cria a chave.
// A chave é guardada no programa deste computador -- vale para todo navegador
// daqui e para os vídeos que ele processa --, e ele a confere com a IA antes de
// guardar: a que ela recusa não entra. A tela nunca recebe a chave de volta, só
// os 4 últimos caracteres.
//
// A chave do Gemini que ficava no NAVEGADOR (o `X-Gemini-Key` de antes) vai
// para o programa sozinha na primeira vez que esta tela abre, se ele ainda não
// tiver uma.

const ERROS = {
  curta: 'Curta demais para ser uma chave. Ela foi copiada inteira?',
  longa: 'Longa demais. Copie só a chave, sem o resto da página.',
  caracteres: 'Tem espaço ou um caractere que chave não tem. Copie só a chave.',
  desconhecida: 'O programa deste computador não conhece esta chave. Ele está atualizado?',
  texto: 'A chave tem de ser texto.',
  vazio: 'Cole a chave antes de salvar.',
  gravar: 'O programa deste computador não conseguiu guardar a chave no disco.',
};

const maiuscula = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const pelo = (p) => (p.artigo === 'a' ? 'pela' : 'pelo');

function textoDoTeste(p, t) {
  switch (t?.resultado) {
    case 'ok':
      return { tipo: 'ok', texto: `Funcionou: a chave foi aceita ${pelo(p)} ${p.nome}.` };
    case 'ocupado':
      return { tipo: 'ok', texto: `Guardada. A chave foi aceita ${pelo(p)} ${p.nome}, que pediu para esperar um pouco antes do próximo pedido.` };
    case 'incompleto':
      return { tipo: 'aviso', texto: 'Guardada, mas ainda falta o ID da conta para funcionar.' };
    case 'incerto':
      return { tipo: 'aviso', texto: `Guardada. ${maiuscula(p.artigo)} ${p.nome} respondeu ${t.status}: não recusou a chave, mas também não deu para confirmar.` };
    case 'sem_resposta':
      return { tipo: 'aviso', texto: `Guardada, mas sem conferir: não deu para falar com ${p.artigo} ${p.nome} agora.` };
    default:
      return { tipo: 'ok', texto: 'Guardada.' };
  }
}

function textoDoErro(p, status, d) {
  if (status === 404 || status === 405) {
    return 'O programa deste computador é de antes desta tela. Atualize-o pelo aviso no topo da página e tente de novo.';
  }
  if (status === 401) return 'Entre de novo na sua conta e tente outra vez.';
  if (status === 403) return typeof d === 'string' && d ? d : 'Só o dono da instalação pode trocar as chaves.';
  if (d?.erro === 'recusada') {
    return `${maiuscula(p.artigo)} ${p.nome} recusou esta chave. Confira se ela foi copiada inteira.`;
  }
  if (d?.erro && ERROS[d.erro]) return ERROS[d.erro];
  return `O programa deste computador respondeu ${status}.`;
}

const COR = { ok: 'text-ok', aviso: 'text-warn', erro: 'text-danger' };

function Mensagem({ m }) {
  if (!m) return null;
  const Icone = m.tipo === 'ok' ? Check : AlertTriangle;
  return (
    <p className={`text-xs flex items-start gap-1.5 animate-fade ${COR[m.tipo]}`}>
      <Icone size={13} className="shrink-0 mt-px" />
      <span>{m.texto}</span>
    </p>
  );
}

function Situacao({ p, estado }) {
  const estados = p.campos.map((c) => estado?.[c.variavel]);
  const algum = estados.some((e) => e?.configurada);
  if (!algum) return <span className="text-xs text-muted">sem chave</span>;
  if (!estados.every((e) => e?.configurada)) return <span className="badge-warn">incompleta</span>;
  const doSite = estados.some((e) => e?.origem === 'site');
  const final = estados[0]?.final;
  return (
    <span className="badge-ok">
      <Check size={11} /> {doSite ? 'guardada' : 'no arquivo .env'}
      {/* O selo é em maiúsculas; o final da chave não pode ser, ou "x1Yz"
          vira "X1YZ" e não bate com a chave que a pessoa tem na mão. */}
      {final && <> · termina em <span className="normal-case">{final}</span></>}
    </span>
  );
}

function BlocoDoProvedor({ p, estado, trocar, nota = null, mensagemInicial = null }) {
  const [valores, setValores] = useState({});
  const [mostrar, setMostrar] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [mensagem, setMensagem] = useState(mensagemInicial);
  const doSite = p.campos.some((c) => estado?.[c.variavel]?.origem === 'site');
  const digitado = p.campos.some((c) => (valores[c.variavel] || '').trim());

  useEffect(() => { if (mensagemInicial) setMensagem(mensagemInicial); }, [mensagemInicial]);

  const enviar = async (chaves, sucesso) => {
    setOcupado(true);
    setMensagem(null);
    try {
      const r = await trocar(chaves);
      if (r.ok) {
        setValores({});
        setMensagem(sucesso(r.corpo));
      } else {
        setMensagem({ tipo: 'erro', texto: textoDoErro(p, r.status, r.corpo?.detail ?? r.corpo) });
      }
    } catch {
      setMensagem({ tipo: 'erro', texto: 'Não consegui falar com o programa deste computador. Ele está ligado?' });
    } finally {
      setOcupado(false);
    }
  };

  const salvar = () => {
    const chaves = {};
    for (const c of p.campos) {
      const v = (valores[c.variavel] || '').trim();
      if (v) chaves[c.variavel] = v;
    }
    if (!Object.keys(chaves).length || ocupado) return;
    enviar(chaves, (corpo) => {
      const testes = corpo?.testes || {};
      return textoDoTeste(p, testes[Object.keys(testes)[0]]);
    });
  };

  const remover = () => {
    const chaves = {};
    for (const c of p.campos) {
      if (estado?.[c.variavel]?.origem === 'site') chaves[c.variavel] = null;
    }
    enviar(chaves, (corpo) => {
      const volta = p.campos.some((c) => corpo?.variaveis?.[c.variavel]?.origem === 'arquivo');
      return { tipo: 'ok', texto: volta ? 'Removida. Vale de novo a chave do arquivo .env.' : 'Removida.' };
    });
  };

  return (
    <div className="rounded-input border border-rule p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-ink">{p.nome}</span>
          {p.recomendado && (
            <span className="text-[10px] uppercase tracking-wide text-muted border border-rule rounded px-1.5 py-0.5">
              recomendada
            </span>
          )}
        </div>
        <Situacao p={p} estado={estado} />
      </div>
      <p className="text-xs text-muted leading-relaxed">{p.paraQue}</p>
      <a
        href={p.link}
        target="_blank"
        rel="noopener noreferrer"
        className="btn-ghost px-3 py-1.5 text-xs"
      >
        criar chave grátis <ExternalLink size={12} />
      </a>
      {p.campos.map((c) => {
        const tem = estado?.[c.variavel]?.configurada;
        return (
          <div key={c.variavel}>
            {p.campos.length > 1 && <label className="block text-xs text-muted mb-1">{c.rotulo}</label>}
            <div className="relative">
              <input
                type={mostrar ? 'text' : 'password'}
                value={valores[c.variavel] || ''}
                onChange={(e) => setValores((v) => ({ ...v, [c.variavel]: e.target.value }))}
                onKeyDown={(e) => { if (e.key === 'Enter') salvar(); }}
                placeholder={tem ? 'cole outra para trocar' : (c.exemplo ? `cole aqui (${c.exemplo})` : 'cole aqui')}
                aria-label={`${c.rotulo || 'chave'} ${p.nome}`}
                autoComplete="off"
                spellCheck={false}
                className="input-field pr-10 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setMostrar((m) => !m)}
                aria-label={mostrar ? 'Esconder a chave' : 'Mostrar a chave'}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink transition-colors"
              >
                {mostrar ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>
        );
      })}
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={salvar} disabled={!digitado || ocupado} className="btn-primary px-4 py-2 text-xs">
          {ocupado && <Loader2 size={14} className="animate-spin" />}
          {ocupado ? 'conferindo…' : 'salvar'}
        </button>
        {doSite && (
          <button onClick={remover} disabled={ocupado} className="btn-quiet px-3 py-2 text-xs">
            <Trash2 size={12} /> remover
          </button>
        )}
      </div>
      <Mensagem m={mensagem} />
      {nota}
      {p.treina && (
        <p className="text-[11px] text-muted leading-relaxed">
          No plano grátis, {p.artigo} {p.nome} pode usar o que você manda para treinar a IA.
        </p>
      )}
    </div>
  );
}

export default function ChavesDeIA({ chaveDoNavegador, esquecerChaveDoNavegador }) {
  const { refreshConfig } = useAuth();
  const [estado, setEstado] = useState(null);
  // 'antigo' (programa de antes desta tela) | 'sem_motor' (não respondeu)
  const [problema, setProblema] = useState(null);
  const [maisAberto, setMaisAberto] = useState(null);
  const [migracao, setMigracao] = useState(null);
  const migrou = useRef(false);

  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/chaves', { cache: 'no-store' });
      if (res.status === 404 || res.status === 405) { setProblema('antigo'); return; }
      if (!res.ok) { setProblema('sem_motor'); return; }
      setEstado((await res.json()).variaveis || {});
      setProblema(null);
    } catch {
      setProblema('sem_motor');
    }
  }, []);

  const trocar = useCallback(async (chaves) => {
    const res = await apiFetch('/api/chaves', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chaves }),
    });
    let corpo = null;
    try { corpo = await res.json(); } catch { /* sem corpo */ }
    if (res.ok && corpo?.variaveis) {
      setEstado(corpo.variaveis);
      // O painel decide "falta chave?" pela config: sem isto o aviso ficaria
      // na tela até o próximo F5.
      refreshConfig();
    }
    return { ok: res.ok, status: res.status, corpo };
  }, [refreshConfig]);

  useEffect(() => { carregar(); }, [carregar]);

  // A chave do Gemini guardada neste navegador vai para o programa, uma vez.
  useEffect(() => {
    if (!estado || migrou.current || !chaveDoNavegador) return;
    if (estado.GEMINI_API_KEY?.configurada) return;
    migrou.current = true;
    (async () => {
      try {
        const r = await trocar({ GEMINI_API_KEY: chaveDoNavegador });
        if (r.ok) {
          esquecerChaveDoNavegador();
          setMigracao({ tipo: 'ok', texto: 'A chave do Gemini que estava guardada neste navegador foi para o programa deste computador.' });
        }
      } catch { /* fica como estava: o navegador continua mandando a dele */ }
    })();
  }, [estado, chaveDoNavegador, trocar, esquecerChaveDoNavegador]);

  const recomendados = PROVEDORES.filter((p) => p.recomendado);
  const reserva = PROVEDORES.filter((p) => !p.recomendado);
  const reservaComChave = reserva.filter((p) => p.campos.some((c) => estado?.[c.variavel]?.configurada)).length;
  const abertas = maisAberto ?? reservaComChave > 0;

  const notaDoGemini = chaveDoNavegador && estado?.GEMINI_API_KEY?.configurada && !migracao && (
    <div className="text-xs text-muted flex flex-wrap items-center gap-2">
      <span>Este navegador também guarda uma chave do Gemini, que vale no lugar desta nos pedidos feitos daqui.</span>
      <button onClick={esquecerChaveDoNavegador} className="btn-quiet px-2 py-1 text-xs">
        usar só a do programa
      </button>
    </div>
  );

  return (
    <div className="card p-4 sm:p-6 mb-6 animate-fade">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 bg-paper3 rounded-input text-brass">
          <KeyRound size={18} />
        </div>
        <h2 className="font-display uppercase tracking-wide text-lg text-ink">Chaves de IA</h2>
      </div>
      <p className="text-sm text-muted leading-relaxed mb-2">
        O Virtu Clips usa IAs gratuitas para achar os melhores momentos dos seus vídeos. Cada chave é
        grátis e leva um minuto: clique em <span className="text-ink2">criar chave grátis</span>, entre
        com a sua conta, copie a chave e cole aqui.
      </p>
      <p className="text-xs text-muted leading-relaxed mb-5">
        Com mais de uma, se uma IA estiver fora do ar ou sem cota, o programa passa para a próxima
        sozinho. As chaves ficam guardadas no programa deste computador, e não no site.
      </p>

      {problema === 'antigo' && (
        <p className="text-sm text-warn flex items-start gap-2">
          <AlertTriangle size={15} className="shrink-0 mt-0.5" />
          O programa deste computador é de antes desta tela. Atualize-o pelo aviso no topo da página e
          volte aqui.
        </p>
      )}
      {problema === 'sem_motor' && (
        <div className="text-sm text-warn flex flex-wrap items-center gap-2">
          <AlertTriangle size={15} className="shrink-0" />
          Não consegui falar com o programa deste computador.
          <button onClick={carregar} className="btn-quiet px-2 py-1 text-xs">tentar de novo</button>
        </div>
      )}
      {!estado && !problema && (
        <p className="text-sm text-muted flex items-center gap-2">
          <Loader2 size={14} className="animate-spin" /> perguntando ao programa deste computador…
        </p>
      )}

      {estado && (
        <div className="space-y-3">
          {recomendados.map((p) => (
            <BlocoDoProvedor
              key={p.id}
              p={p}
              estado={estado}
              trocar={trocar}
              nota={p.id === 'gemini' ? notaDoGemini : null}
              mensagemInicial={p.id === 'gemini' ? migracao : null}
            />
          ))}
          <button
            onClick={() => setMaisAberto(!abertas)}
            className="btn-quiet px-3 py-2 text-xs"
            aria-expanded={abertas}
          >
            <ChevronDown size={14} className={`transition-transform ${abertas ? 'rotate-180' : ''}`} />
            mais IAs gratuitas, de reserva
            {reservaComChave > 0 && ` (${reservaComChave} com chave)`}
          </button>
          {abertas && reserva.map((p) => (
            <BlocoDoProvedor key={p.id} p={p} estado={estado} trocar={trocar} />
          ))}
        </div>
      )}
    </div>
  );
}
