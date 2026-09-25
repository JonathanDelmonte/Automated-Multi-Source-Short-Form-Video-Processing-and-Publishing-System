import React, { useState, useCallback } from 'react';
import { Plug, Copy, Check } from 'lucide-react';
import { getApiUrl } from '../config';

// "Conectar um agente": como usar o Virtu Clips de dentro de um agente de IA
// (Claude Code, Claude Desktop, Cursor, n8n), pelo servidor MCP do motor
// (mcp_server.py). O cartao herdado era o do produto em nuvem do upstream: em
// ingles, prometendo "8 tools" com uma de publicar que saiu na Fase 0.3, e com
// a URL do servico pago deles. Este fork nao tem nuvem (ADR-001), entao o
// cartao so conhece o motor deste computador -- e diz, com todas as letras,
// que nada aqui le a conta de ninguem: foi a primeira pergunta do autor.

// O painel do Docker encaminha /api e /videos ao motor, mas nao /mcp (nem o
// proxy do Vite nem o nginx.conf): o agente fala com o motor direto. No site,
// o getApiUrl ja devolve o endereco absoluto do motor que respondeu (8000 no
// Docker, 8001 no ajudante); no painel do Docker, a porta do motor no mesmo
// host.
function enderecoDoMcp() {
  const u = getApiUrl('/mcp');
  if (u.startsWith('http')) return u;
  try { return `${window.location.protocol}//${window.location.hostname}:8000/mcp`; } catch { return 'http://localhost:8000/mcp'; }
}

// O que o agente ganha, na ordem do `mcp_server.TOOLS`. Um teste compara os
// nomes com os do motor, para o texto nao voltar a prometer o que nao existe.
const FERRAMENTAS = [
  ['process_video', 'processar um vídeo pelo link'],
  ['create_upload', 'receber um vídeo do computador'],
  ['get_job_status', 'acompanhar o processamento'],
  ['list_clips', 'listar os cortes'],
  ['get_quota', 'consultar o limite de uso'],
  ['add_subtitles', 'pôr legenda num corte'],
  ['recut_clip', 'recortar um corte'],
];

const emFrase = (itens) => (itens.length < 2 ? itens.join('')
  : `${itens.slice(0, -1).join(', ')} e ${itens[itens.length - 1]}`);

function clientes(url) {
  return [
    {
      id: 'claude-code', rotulo: 'Claude Code', tipo: 'codigo',
      texto: `claude mcp add --transport http virtu-clips ${url}`,
      nota: 'Rode uma vez no terminal. Depois é só pedir ao Claude Code, por exemplo: "corte este vídeo: <link>".',
    },
    {
      id: 'claude-desktop', rotulo: 'Claude Desktop', tipo: 'codigo',
      texto: `{\n  "mcpServers": {\n    "virtu-clips": {\n      "command": "npx",\n      "args": ["-y", "mcp-remote", "${url}"]\n    }\n  }\n}`,
      nota: 'Em Settings → Developer → Edit Config (o arquivo claude_desktop_config.json): cole isto e reinicie o Claude. Precisa do Node.js instalado.',
    },
    {
      id: 'cursor', rotulo: 'Cursor', tipo: 'codigo',
      texto: `{\n  "mcpServers": {\n    "virtu-clips": {\n      "url": "${url}"\n    }\n  }\n}`,
      nota: 'No arquivo de MCP do Cursor (~/.cursor/mcp.json).',
    },
    {
      id: 'n8n', rotulo: 'n8n', tipo: 'passos',
      passos: [
        'Ponha um nó "MCP Client Tool" no seu AI Agent.',
        `Endpoint: ${url}  ·  Transport: HTTP Streamable.`,
        'Authentication: none.',
      ],
      texto: url,
    },
    {
      id: 'curl', rotulo: 'curl', tipo: 'codigo',
      texto: `curl -X POST ${url} \\\n  -H "Content-Type: application/json" \\\n  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`,
      nota: 'Para conferir se o programa responde: devolve a lista de ferramentas.',
    },
  ];
}

export default function McpConnectCard() {
  const lista = clientes(enderecoDoMcp());
  const [ativo, setAtivo] = useState(lista[0].id);
  const [copiado, setCopiado] = useState(false);
  const atual = lista.find((c) => c.id === ativo) || lista[0];

  const copiar = useCallback(() => {
    navigator.clipboard?.writeText(atual.texto).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1600);
    }).catch(() => {});
  }, [atual]);

  return (
    <div className="card p-6" id="connect-agent">
      <h3 className="font-display uppercase tracking-wide text-lg text-ink mb-1 flex items-center gap-2">
        <Plug size={16} className="text-brass" /> Conectar um agente de IA
      </h3>
      <p className="text-muted text-sm mb-2">
        Opcional. Se você usa um agente de IA neste computador (Claude Code, Claude Desktop, Cursor ou
        n8n), ele pode usar o Virtu Clips direto da conversa. Copie o texto da aba do seu agente e cole
        nele: é o agente que passa a chamar este programa, e nada aqui lê a sua conta do Claude ou de
        outro serviço.
      </p>
      <p className="text-muted text-xs mb-4 leading-relaxed">
        O agente ganha {FERRAMENTAS.length} ferramentas: {emFrase(FERRAMENTAS.map(([, r]) => r))}. Ele
        precisa rodar neste computador, porque o endereço é o do programa daqui (o Claude do navegador
        não o alcança). Enquanto ninguém tiver senha neste programa, não precisa de chave.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4" role="tablist" aria-label="agente">
        {lista.map((c) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={c.id === ativo}
            onClick={() => { setAtivo(c.id); setCopiado(false); }}
            className={`px-3 py-1.5 rounded-input text-xs border transition-colors ${
              c.id === ativo ? 'border-brass text-ink bg-brass/10' : 'border-rule text-muted hover:text-ink'}`}
          >
            {c.rotulo}
          </button>
        ))}
      </div>

      {atual.tipo === 'passos' && (
        <ol className="list-decimal pl-5 space-y-1.5 text-sm text-ink2 mb-3">
          {atual.passos.map((s) => <li key={s}>{s}</li>)}
        </ol>
      )}

      <div className="relative">
        <pre className="font-mono text-ink2 whitespace-pre-wrap break-all rounded-card border border-rule bg-paper p-3 pr-24 text-xs leading-relaxed">
          {atual.texto}
        </pre>
        <button onClick={copiar} className="btn-ghost absolute top-2 right-2 px-2.5 py-1 text-xs" aria-label="copiar">
          {copiado ? <Check size={13} /> : <Copy size={13} />} {copiado ? 'copiado' : 'copiar'}
        </button>
      </div>
      {atual.nota && <p className="text-muted text-xs mt-2">{atual.nota}</p>}
    </div>
  );
}
