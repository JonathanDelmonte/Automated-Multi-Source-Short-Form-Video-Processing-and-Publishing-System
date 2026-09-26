""""Conectar YouTube" pelo site: o consentimento do Google feito pelo motor (7.3).

Antes era `python youtube_oauth.py` no terminal -- o jeito certo para quem
programa e uma parede para quem nao. O fluxo e o mesmo, so que pedido pelo
botao do site:

1. o site pede ao motor (`POST /api/contas/{id}/conectar`) e recebe a URL de
   consentimento do Google;
2. a pessoa autoriza, e o Google a devolve **para a propria maquina**
   (`http://localhost:<porta>/`) -- e o que ele aceita para programa instalado,
   sem cadastrar endereco nenhum (cliente "App para computador", RFC 8252);
3. quem recebe e o motor (pela raiz, `GET /`) ou o painel do Docker, que manda
   o codigo ao motor (`POST /api/oauth/volta`); o motor troca o codigo pelo
   refresh token e o guarda no cofre local, e a conta passa a apontar para ele.

**Dois consentimentos, como o `youtube_oauth.py` sempre fez**: `publicar`
(`youtube.upload` e so ele) e `medir` (os dois escopos de leitura). Duas
credenciais pequenas em vez de uma grande: a que publica nao le, a que le nao
publica, e nenhuma das duas apaga (ha teste congelando os escopos).

- **A volta e sempre raiz, com barra** (`http://localhost:8000/`): e a forma
  que as bibliotecas do proprio Google usam para programa instalado, a mais
  garantida de o Google aceitar.
- **So localhost** (`localhost`, `127.0.0.1`, `[::1]`): e o que o Google aceita
  sem cadastro, e e o que garante que o codigo volte para ESTA maquina. O
  painel aberto de outro aparelho da rede nao conecta -- a tela diz para
  abrir neste computador.
- **O `state` e a senha do pedido**: aleatorio, de uso unico, vale 10 minutos,
  e e ele que liga a volta a conta e ao tenant de quem clicou. A rota de volta
  e publica (quem chega nela e o navegador vindo do Google, sem sessao), entao
  sem `state` valido ela nao faz nada.
- **PKCE** (S256), que o Google recomenda para programa instalado: o codigo
  sozinho, interceptado, nao vira token.
- **Em memoria**: um pedido que atravessa um reinicio do motor morre, e a tela
  manda clicar de novo. Guardar pedido pendente em disco seria guardar meio
  segredo por nada.
"""
from __future__ import annotations

import base64
import hashlib
import html
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode, urlsplit

AUTORIZACAO_GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_GOOGLE = "https://oauth2.googleapis.com/token"
REVOGAR_GOOGLE = "https://oauth2.googleapis.com/revoke"
AUTORIZACAO_TIKTOK = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_TIKTOK = "https://open.tiktokapis.com/v2/oauth/token/"

#: Os escopos de cada consentimento. Os mesmos do `youtube_oauth.py`, que o
#: teste compara: dois caminhos para a mesma credencial nao podem pedir coisas
#: diferentes.
ESCOPOS = {
    ("youtube", "publicar"): ("https://www.googleapis.com/auth/youtube.upload",),
    ("youtube", "medir"): ("https://www.googleapis.com/auth/youtube.readonly",
                           "https://www.googleapis.com/auth/yt-analytics.readonly"),
    # O TikTok (7.3c): o perfil basico e o Direct Post.
    ("tiktok", "publicar"): ("user.info.basic", "video.publish"),
    # E medir (7.4): o perfil basico e a lista de videos (API de exibicao).
    # Outra credencial, como no YouTube: a que posta nao le, a que le nao posta.
    ("tiktok", "medir"): ("user.info.basic", "video.list"),
}
TIPOS = ("publicar", "medir")
#: O que cada plataforma conecta pelo botao, e qual cadastro de aplicativo ela
#: usa. O Instagram mede por token COLADO (`metricas_instagram`), nao por botao:
#: a Meta so devolve o login para endereco HTTPS.
TIPOS_DE = {"youtube": ("publicar", "medir"), "tiktok": ("publicar", "medir")}

#: A permissao sem a qual cada consentimento do TikTok nao serve para nada. A
#: resposta dele lista o que a pessoa AUTORIZOU, que pode ser menos que o pedido.
ESCOPO_ESSENCIAL = {("tiktok", "publicar"): "video.publish",
                    ("tiktok", "medir"): "video.list"}
APLICATIVO_DE = {"youtube": "google", "tiktok": "tiktok"}

#: Quanto tempo um pedido espera a volta do Google.
VALIDADE_S = 600

_HOSTS_LOCAIS = ("localhost", "127.0.0.1", "::1")
_HOSTS_DO_TIKTOK = ("localhost", "127.0.0.1")


class ConexaoError(ValueError):
    """`codigo`: plataforma | tipo | volta | sem_aplicativo | expirou |
    recusada | troca | sem_refresh | escopo | escopo_medir."""

    def __init__(self, codigo: str, detalhe: str = ""):
        super().__init__(detalhe or codigo)
        self.codigo = codigo
        self.detalhe = detalhe


def volta_de(origem: str, plataforma: str = "youtube") -> str:
    """O endereco de volta, a partir da origem pela qual o NAVEGADOR fala com o
    motor (o site manda `http://localhost:8000`; o painel do Docker, a propria
    origem). So localhost; a volta e a raiz, com barra.

    **O TikTok e mais estreito que o Google** (Login Kit for Desktop): so
    `localhost` e `127.0.0.1` -- o `[::1]` nao --, e sempre com porta. A pessoa
    cadastra `http://localhost:*/` e `http://127.0.0.1:*/` no app dela (o `*` e
    qualquer porta), e uma volta fora disso seria recusada na tela do TikTok,
    depois do clique: aqui ela e recusada antes.
    """
    try:
        partes = urlsplit((origem or "").strip())
        host = (partes.hostname or "").lower()
        porta = partes.port
    except ValueError:
        raise ConexaoError("volta")
    if partes.scheme != "http" or host not in _HOSTS_LOCAIS:
        raise ConexaoError("volta")
    if partes.path not in ("", "/") or partes.query or partes.fragment:
        raise ConexaoError("volta")
    if plataforma == "tiktok" and (host not in _HOSTS_DO_TIKTOK or not porta):
        raise ConexaoError("volta")
    nome = f"[{host}]" if ":" in host else host
    return f"http://{nome}:{porta}/" if porta else f"http://{nome}/"


def par_pkce(hexadecimal: bool = False) -> tuple:
    """`(verifier, challenge)` do PKCE S256.

    O Google quer o desafio em base64url sem `=` (o RFC 7636). **O TikTok, em
    programa de computador, quer o SHA-256 em HEXADECIMAL** -- esta escrito na
    documentacao do Login Kit for Desktop, e e o erro que se comete copiando o
    PKCE de qualquer outro lugar."""
    verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    if hexadecimal:
        return verifier, digest.hex()
    return verifier, base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass
class Pedido:
    tenant_id: str
    account_id: str
    handle: str
    plataforma: str
    tipo: str
    volta: str
    verifier: str
    criado_em: float = field(default_factory=time.monotonic)


class Pedidos:
    """Os consentimentos em andamento, por `state`. Uso unico."""

    def __init__(self, validade_s: float = VALIDADE_S, relogio=time.monotonic):
        self._pedidos: dict = {}
        self._trava = threading.Lock()
        self._validade = validade_s
        self._relogio = relogio

    def _varrer(self) -> None:
        agora = self._relogio()
        for state in [s for s, p in self._pedidos.items()
                      if agora - p.criado_em > self._validade]:
            self._pedidos.pop(state, None)

    def novo(self, pedido: Pedido) -> str:
        with self._trava:
            self._varrer()
            pedido.criado_em = self._relogio()
            state = secrets.token_urlsafe(32)
            self._pedidos[state] = pedido
            return state

    def consumir(self, state: str) -> Optional[Pedido]:
        """O pedido deste `state`, tirado da lista -- ou None (nao existe,
        venceu, ou ja foi usado)."""
        if not isinstance(state, str) or not state:
            return None
        with self._trava:
            self._varrer()
            return self._pedidos.pop(state, None)

    def __len__(self) -> int:
        with self._trava:
            self._varrer()
            return len(self._pedidos)


def id_do_app(app: dict) -> str:
    return app.get("client_id") or app.get("client_key") or ""


def url_de_consentimento(client_id: str, volta: str, plataforma: str, tipo: str,
                         state: str, desafio: str) -> str:
    if (plataforma, tipo) not in ESCOPOS:
        raise ConexaoError("tipo")
    if plataforma == "tiktok":
        return AUTORIZACAO_TIKTOK + "?" + urlencode({
            "client_key": client_id,
            # O TikTok separa os escopos por VIRGULA.
            "scope": ",".join(ESCOPOS[(plataforma, tipo)]),
            "response_type": "code",
            "redirect_uri": volta,
            "state": state,
            "code_challenge": desafio,
            "code_challenge_method": "S256",
        })
    return AUTORIZACAO_GOOGLE + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": volta,
        "response_type": "code",
        "scope": " ".join(ESCOPOS[(plataforma, tipo)]),
        # `offline` e o que faz o Google devolver refresh_token; `consent`
        # forca a tela mesmo se a conta ja autorizou antes -- sem ele, a
        # segunda vez volta SEM refresh_token e o erro nao diz por que.
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": desafio,
        "code_challenge_method": "S256",
    })


def ref_do_cofre(plataforma: str, tipo: str, handle: str) -> str:
    """Onde a credencial mora: a de publicar, no endereco que o driver le; a de
    medir, no que o coletor de metricas procura."""
    if tipo not in TIPOS_DE.get(plataforma, ()):
        raise ConexaoError("tipo")
    pasta = plataforma if tipo == "publicar" else f"{plataforma}-metrics"
    return f"vault://local/{pasta}/{handle}"


def trocar_codigo(app: dict, codigo: str, pedido: Pedido,
                  cliente=None, timeout: float = 30.0) -> str:
    """O refresh token, trocando o codigo que o Google devolveu. Rede."""
    if cliente is None:
        import httpx

        def cliente():
            return httpx.Client(timeout=timeout)
    try:
        with cliente() as c:
            r = c.post(TOKEN_GOOGLE, data={
                "client_id": app["client_id"],
                "client_secret": app["client_secret"],
                "code": codigo,
                "code_verifier": pedido.verifier,
                "grant_type": "authorization_code",
                "redirect_uri": pedido.volta,
            })
    except Exception as e:
        raise ConexaoError("troca", f"sem resposta do Google ({type(e).__name__})")
    if r.status_code != 200:
        # A resposta de erro do OAuth traz o motivo (`invalid_grant`...), nunca
        # o segredo, entao pode ir para a tela.
        try:
            motivo = (r.json() or {}).get("error") or str(r.status_code)
        except ValueError:
            motivo = str(r.status_code)
        raise ConexaoError("troca", f"o Google recusou a troca ({motivo})")
    refresh = (r.json() or {}).get("refresh_token")
    if not refresh:
        raise ConexaoError("sem_refresh")
    return refresh


def trocar_codigo_tiktok(app: dict, codigo: str, pedido: Pedido,
                         cliente=None, timeout: float = 30.0) -> dict:
    """`{refresh_token, open_id}`, trocando o codigo que o TikTok devolveu. Rede.

    Confere que a permissao essencial veio: a resposta lista os escopos que a
    pessoa AUTORIZOU, que podem ser menos que os pedidos -- e sem
    `video.publish` a conexao "funciona" e nenhum post sai; sem `video.list`,
    nenhum numero volta."""
    if cliente is None:
        import httpx

        def cliente():
            return httpx.Client(timeout=timeout)
    try:
        with cliente() as c:
            r = c.post(TOKEN_TIKTOK, data={
                "client_key": app["client_key"],
                "client_secret": app["client_secret"],
                "code": codigo,
                "grant_type": "authorization_code",
                "redirect_uri": pedido.volta,
                "code_verifier": pedido.verifier,
            })
    except Exception as e:
        raise ConexaoError("troca", f"sem resposta do TikTok ({type(e).__name__})")
    try:
        dados = r.json() or {}
    except ValueError:
        dados = {}
    if r.status_code != 200 or dados.get("error"):
        raise ConexaoError("troca", f"o TikTok recusou a troca ({dados.get('error') or r.status_code})")
    if not dados.get("refresh_token"):
        raise ConexaoError("sem_refresh")
    escopos = {e.strip() for e in (dados.get("scope") or "").split(",") if e.strip()}
    essencial = ESCOPO_ESSENCIAL.get(("tiktok", pedido.tipo), "video.publish")
    if escopos and essencial not in escopos:
        if pedido.tipo == "publicar":
            raise ConexaoError("escopo")
        raise ConexaoError("escopo_medir")
    return {"refresh_token": dados["refresh_token"], "open_id": dados.get("open_id") or ""}


def trocar(app: dict, codigo: str, pedido: Pedido) -> dict:
    """O que guardar no cofre alem do cadastro do app, por plataforma."""
    if pedido.plataforma == "tiktok":
        return trocar_codigo_tiktok(app, codigo, pedido)
    return {"refresh_token": trocar_codigo(app, codigo, pedido)}


def revogar(token: str, timeout: float = 10.0) -> bool:
    """Avisa o Google que o token nao vale mais. Melhor esforco."""
    try:
        import httpx
        r = httpx.post(REVOGAR_GOOGLE, data={"token": token}, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


#: As frases da pagina de volta. `{empresa}` e quem mostrou a tela de
#: autorizacao: o Google (YouTube) ou o TikTok.
MENSAGENS = {
    "expirou": "Esse pedido de conexão venceu ou já foi usado. Volte ao Virtu Clips e clique em conectar de novo.",
    "recusada": "A conexão foi cancelada na tela do {empresa}. Nada mudou; dá para tentar de novo quando quiser.",
    "troca": "O {empresa} não aceitou o código de volta. Clique em conectar de novo.",
    "sem_refresh": "O Google respondeu sem a autorização permanente. Tire o acesso do Virtu Clips em myaccount.google.com/permissions e conecte de novo.",
    "sem_aplicativo": "O cadastro do aplicativo sumiu das Configurações. Cole de novo e conecte outra vez.",
    "escopo": "A permissão de postar não veio. Conecte de novo e deixe marcada a opção de publicar vídeos.",
    "escopo_medir": "A permissão de ver os vídeos não veio. Conecte de novo e deixe marcada a opção de ler os seus vídeos.",
}
#: O que muda no TikTok: a pagina de permissoes do Google nao serve para ele.
MENSAGENS_DO_TIKTOK = {
    "sem_refresh": "O TikTok respondeu sem a autorização permanente. Clique em conectar de novo.",
}
_EMPRESA = {"youtube": "Google", "tiktok": "TikTok"}


def mensagem(codigo: str, plataforma: str = "youtube") -> Optional[str]:
    """A frase de um codigo de erro, com o nome de quem mostrou a tela."""
    texto = (MENSAGENS_DO_TIKTOK.get(codigo) if plataforma == "tiktok" else None) \
        or MENSAGENS.get(codigo)
    return texto.format(empresa=_EMPRESA.get(plataforma, "Google")) if texto else None


_NOMES = {("youtube", "publicar"): "publicar no YouTube",
          ("youtube", "medir"): "medir as visualizações do YouTube",
          ("tiktok", "publicar"): "publicar no TikTok",
          ("tiktok", "medir"): "medir as visualizações do TikTok"}


def pagina_de_volta(ok: bool, *, plataforma: str = "youtube", tipo: str = "publicar",
                    handle: str = "", codigo: str = "", detalhe: str = "") -> str:
    """A pagina que a aba do consentimento mostra ao voltar. Tudo o que vem de
    fora passa por `html.escape`: o `error` da volta e texto de quem montou a
    URL."""
    if ok:
        titulo = "Conectado"
        texto = (f"A conta {handle} está conectada para "
                 f"{_NOMES.get((plataforma, tipo), tipo)}. Pode fechar esta aba e voltar ao Virtu Clips.")
    else:
        titulo = "Não conectou"
        texto = mensagem(codigo, plataforma) or "Não deu para conectar. Volte ao Virtu Clips e tente de novo."
        if detalhe:
            texto += f" ({detalhe})"
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(titulo)} · Virtu Clips</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0a0a0a; color: #f5f5f5; font: 16px/1.5 system-ui, sans-serif; }}
  main {{ max-width: 30rem; padding: 2rem 1.5rem; text-align: center; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .75rem; letter-spacing: .02em; }}
  p {{ color: #c7c7c7; margin: 0; }}
</style></head>
<body><main><h1>{html.escape(titulo)}</h1><p>{html.escape(texto)}</p></main></body></html>
"""
