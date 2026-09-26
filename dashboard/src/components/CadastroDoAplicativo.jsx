import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, ExternalLink, Loader2, Trash2 } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { API_BASE_URL } from '../config';
import IconePlataforma from './ui/IconePlataforma';
import { mensagemDoCadastro, origemDoMotor } from '../lib/conexoes';

// O cadastro de aplicativo de quem usa (etapa 7.3). Decisão do autor
// (26-set-2026): cada pessoa usa o próprio -- o projeto dela no Google Cloud, o
// app dela no TikTok --, como já faz com as chaves de IA. É o que deixa o
// "conectar" de cada conta funcionar sem terminal.
//
// Os passos são os de verdade, na ordem em que cada console pede, e dizem as
// pegadinhas que custam caro depois: no Google, o tipo do cliente ("App para
// computador") e a tela de consentimento "Em produção"; no TikTok, o endereço
// de volta cadastrado e o que a API faz antes da auditoria.

const volta = () => `${origemDoMotor(API_BASE_URL, window.location.origin)}/`;

const APPS = [
  {
    plataforma: 'google',
    icone: 'youtube',
    titulo: 'Google (YouTube)',
    campos: [
      { nome: 'client_id', rotulo: 'ID do cliente do Google', placeholder: 'ID do cliente (…apps.googleusercontent.com), ou o JSON baixado' },
      { nome: 'client_secret', rotulo: 'chave secreta do cliente do Google', placeholder: 'chave secreta do cliente (GOCSPX-…)', secreto: true },
    ],
    aceitaJson: true,
    passos: () => [
      {
        texto: 'Entre no Google Cloud com a conta Google do canal e crie um projeto (qualquer nome, por exemplo "Virtu Clips").',
        links: [['https://console.cloud.google.com/projectcreate', 'criar o projeto']],
      },
      {
        texto: 'Ative a YouTube Data API v3 (para publicar) e a YouTube Analytics API (para medir).',
        links: [['https://console.cloud.google.com/apis/library/youtube.googleapis.com', 'ativar a Data API'],
                ['https://console.cloud.google.com/apis/library/youtubeanalytics.googleapis.com', 'ativar a Analytics API']],
      },
      {
        texto: 'Configure a tela de consentimento: público "Externo", o nome do app e o seu e-mail. Depois, em "Público-alvo", coloque o app "Em produção" — em "Teste", a conexão expira a cada 7 dias. Na hora de conectar, o Google avisa que o app não foi verificado: para uso próprio, é só seguir em "Avançado".',
        links: [['https://console.cloud.google.com/auth/overview', 'tela de consentimento']],
      },
      {
        texto: 'Em "Clientes", crie um cliente OAuth do tipo "App para computador" (não "Aplicativo da Web"). Copie o ID do cliente e a chave secreta — ou baixe o JSON e cole ele inteiro no primeiro campo.',
        links: [['https://console.cloud.google.com/auth/clients', 'criar o cliente']],
      },
      { texto: 'Cole aqui e salve. Depois, em cada conta do YouTube (na visão geral do canal ou em Configurações → contas), clique em "conectar".' },
    ],
    nota: 'Até o Google aprovar a auditoria do seu projeto, os vídeos que o programa envia sobem como privados — você os deixa públicos no YouTube Studio, ou posta pelo pacote do dia.',
  },
  {
    plataforma: 'tiktok',
    icone: 'tiktok',
    titulo: 'TikTok',
    campos: [
      { nome: 'client_key', rotulo: 'client key do TikTok', placeholder: 'client key (aw… ou sbaw… no sandbox)' },
      { nome: 'client_secret', rotulo: 'client secret do TikTok', placeholder: 'client secret', secreto: true },
    ],
    passos: () => [
      {
        texto: 'Entre no TikTok for Developers com a sua conta do TikTok e crie um app.',
        links: [['https://developers.tiktok.com/apps/', 'meus apps']],
      },
      { texto: 'Em "Products", adicione o Login Kit, o Content Posting API (para publicar; nele, ligue o "Direct Post") e a Display API (para medir as visualizações).' },
      {
        texto: `No Login Kit, escolha a plataforma "Desktop" e cadastre os dois endereços de volta: http://localhost:*/ e http://127.0.0.1:*/ — o * vale qualquer porta, e cobre o site, o painel do Docker e o ajudante. (Este computador volta por ${volta()}.)`,
      },
      { texto: 'Confira em "Scopes" que o app tem o user.info.basic, o video.publish (publicar) e o video.list (medir).' },
      { texto: 'Para usar sem esperar a revisão do app, crie um Sandbox e adicione a sua conta do TikTok como usuário de teste ("Target users").' },
      { texto: 'Copie o client key e o client secret (os do Sandbox, se for o caso), cole aqui e salve. Depois, conecte a conta do TikTok na visão geral do canal.' },
    ],
    aviso: 'Antes da auditoria do TikTok, o envio pela API sai só para você (privado), a conta precisa estar PRIVADA no app na hora do post, e no máximo 5 contas por dia postam pelo seu app. Serve para testar; para postar público, use o pacote do dia até a auditoria.',
  },
];

function CartaoDoApp({ app, estado, aoSalvar }) {
  const [valores, setValores] = useState({});
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);
  const [aviso, setAviso] = useState(null);

  const enviar = async (corpo) => {
    setSalvando(true);
    setErro(null);
    setAviso(null);
    try {
      const res = await apiFetch('/api/aplicativos', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plataforma: app.plataforma, ...corpo }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro(mensagemDoCadastro(data?.detail?.erro, { plataforma: app.plataforma, campo: data?.detail?.campo }));
        return;
      }
      setValores({});
      if (data.teste === 'incerto') {
        setAviso('Salvo. Não deu para conferir com o Google agora (sem internet?): se estiver errado, o conectar vai dizer.');
      }
      aoSalvar(data.aplicativos || {});
    } catch {
      setErro('Não consegui falar com o programa.');
    } finally {
      setSalvando(false);
    }
  };

  const primeiro = app.campos[0].nome;
  const colouJson = app.aceitaJson && (valores[primeiro] || '').trim().startsWith('{');
  const preenchido = colouJson || app.campos.every((c) => (valores[c.nome] || '').trim());
  const configurado = estado?.configurado;

  return (
    <div className="space-y-3 border-t border-rule pt-4 first:border-0 first:pt-0" data-app={app.plataforma}>
      <div className="flex items-center gap-2.5">
        <IconePlataforma platform={app.icone} size={20} />
        <h3 className="text-ink text-sm font-medium">{app.titulo}</h3>
        {configurado && (
          <span className="ml-auto inline-flex items-center gap-1 text-xs text-ok">
            <CheckCircle2 size={13} /> cadastrado{estado.origem === 'arquivo' ? ' pelo arquivo .env' : ''}
          </span>
        )}
      </div>

      {configurado && (
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-muted">{app.plataforma === 'google' ? 'ID do cliente:' : 'client key:'}</span>
          <code className="text-ink2 break-all">{estado.client_id}</code>
          {estado.origem === 'site' && (
            <button type="button" className="text-muted hover:text-danger inline-flex items-center gap-1 text-xs ml-auto"
                    onClick={() => enviar({ remover: true })} disabled={salvando}>
              <Trash2 size={13} /> tirar
            </button>
          )}
        </div>
      )}

      <ol className="space-y-2.5 text-[13px] text-ink2 list-decimal pl-5">
        {app.passos().map((p) => (
          <li key={p.texto} className="leading-snug">
            {p.texto}
            {p.links && (
              <span className="block mt-1 space-x-3">
                {p.links.map(([href, rotulo]) => (
                  <a key={href} href={href} target="_blank" rel="noopener noreferrer"
                     className="inline-flex items-center gap-1 text-xs text-muted hover:text-ink2 underline underline-offset-2">
                    <ExternalLink size={11} /> {rotulo}
                  </a>
                ))}
              </span>
            )}
          </li>
        ))}
      </ol>

      <form className="space-y-2" onSubmit={(e) => {
        e.preventDefault();
        if (!preenchido || salvando) return;
        enviar(colouJson ? { [primeiro]: valores[primeiro] } : valores);
      }}>
        {app.campos.map((c) => (c.nome !== primeiro && colouJson ? null : (
          <input
            key={c.nome}
            className="input-field text-sm py-1.5 w-full"
            placeholder={c.placeholder}
            value={valores[c.nome] || ''}
            onChange={(e) => setValores({ ...valores, [c.nome]: e.target.value })}
            type={c.secreto ? 'password' : 'text'}
            autoComplete="off"
            spellCheck={false}
            aria-label={c.rotulo}
          />
        )))}
        <button type="submit" className="btn-primary text-sm" disabled={!preenchido || salvando}>
          {salvando ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
          {configurado ? 'trocar o cadastro' : 'salvar'}
        </button>
      </form>
      {app.aviso && (
        <p className="text-[12px] leading-snug text-brass flex gap-1.5">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {app.aviso}
        </p>
      )}
      {app.nota && <p className="text-muted text-[12px] leading-snug">{app.nota}</p>}
      {erro && <p className="text-danger text-[13px]">{erro}</p>}
      {aviso && <p className="text-brass text-[13px]">{aviso}</p>}
    </div>
  );
}

export default function CadastroDoAplicativo() {
  const [estados, setEstados] = useState(undefined);

  const carregar = useCallback(async () => {
    try {
      const res = await apiFetch('/api/aplicativos');
      if (res.status === 404) { setEstados(null); return; }  // motor de antes da 7.3
      const data = res.ok ? await res.json() : {};
      setEstados(data.aplicativos || {});
    } catch {
      setEstados(null);
    }
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  if (estados === undefined) {
    return <Loader2 size={16} className="animate-spin text-muted" />;
  }
  if (estados === null) {
    return (
      <p className="text-muted text-[13px]">
        O programa deste computador ainda não sabe guardar o cadastro do aplicativo. Atualize o programa
        (o aviso no topo do site tem o botão).
      </p>
    );
  }
  return (
    <div className="space-y-4">
      <p className="text-muted text-[12px] leading-snug">
        O cadastro fica no programa deste computador, e a chave secreta nunca volta para o site.
      </p>
      {APPS.map((app) => (
        // O site é publicado antes de o programa de quem usa ser atualizado:
        // um programa que não conhece a plataforma não guarda o cadastro dela.
        estados[app.plataforma] === undefined ? (
          <p key={app.plataforma} className="text-muted text-[13px] border-t border-rule pt-4" data-app={app.plataforma}>
            {app.titulo}: o cadastro chega com a versão nova do programa deste computador. Atualize o
            programa (o aviso no topo do site tem o botão).
          </p>
        ) : (
          <CartaoDoApp key={app.plataforma} app={app} estado={estados[app.plataforma]}
                       aoSalvar={(novos) => setEstados(novos)} />
        )
      ))}
    </div>
  );
}
