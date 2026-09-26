"""O link de um post, lido por plataforma (Fase 7, etapa 7.3).

O "ja publiquei" da fila manual passou a pedir o link do post. Sem ele, o que
se posta a mao nunca e medido: o coletor de metricas precisa do id do video, e
o id so existe do lado da plataforma.

Tres plataformas, cada uma com os jeitos de copiar um link que existem de
verdade -- o botao "copiar link" do app nao da o mesmo endereco da barra do
navegador:

- **YouTube**: `youtube.com/shorts/<id>`, `watch?v=<id>`, `youtu.be/<id>`,
  `/live/<id>`. O id tem 11 caracteres, e e o que a API de metricas le.
- **TikTok**: `tiktok.com/@<conta>/video/<id>` no navegador; no app, o
  "copiar link" da o **link curto** (`vm.tiktok.com/<codigo>`), que nao carrega
  o id -- so redireciona para o endereco completo. `resolver_link_curto` segue
  esse unico redirecionamento; sem rede, o link fica guardado e o id nao.
- **Instagram**: `instagram.com/reel/<codigo>/` (e `/p/`, `/tv/`, e o formato
  com a conta na frente). O codigo nao e o id da API -- a Fase 7.4 acha o id
  pela lista de posts da conta, casando pelo link.

**O que decide e funcao pura** (`ler`), e o CI a exercita com os links como
eles chegam: com `?si=`, `?igsh=`, `m.`, barra no fim. A unica parte com rede e
`resolver_link_curto`, e ela nunca levanta.

**Link de outra plataforma e recusado**, com o nome das duas: colar o link do
TikTok no galho do YouTube faria o coletor medir o video errado, em silencio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlsplit

PLATAFORMAS = ("youtube", "tiktok", "instagram")
NOMES = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram"}

_HOSTS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
}

_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ID_TIKTOK = re.compile(r"^\d{8,25}$")
_CODIGO_INSTAGRAM = re.compile(r"^[A-Za-z0-9_-]{5,64}$")

#: Os hosts do link curto do app do TikTok: nao carregam o id.
_TIKTOK_CURTOS = ("vm.tiktok.com", "vt.tiktok.com")


class LinkInvalido(ValueError):
    """Um link que nao da para guardar. A mensagem vai para a tela."""


@dataclass(frozen=True)
class Post:
    plataforma: str
    #: O id que a plataforma entende. None num link curto do TikTok que nao
    #: deu para seguir: o link fica, a medicao espera.
    id: Optional[str]
    #: O link limpo (sem rastreador de compartilhamento), que o painel abre.
    url: str
    curto: bool = False


def _host(url: str) -> tuple:
    bruto = (url or "").strip()
    if not bruto:
        raise LinkInvalido("cole o link do post")
    esquema = re.match(r"^([a-z][a-z0-9+.-]*):", bruto, re.IGNORECASE)
    if esquema and "." not in esquema.group(1) and not bruto[esquema.end():].startswith("//"):
        raise LinkInvalido("isso nao parece um link")    # `javascript:`, `mailto:`...
    if not re.match(r"^[a-z][a-z0-9+.-]*://", bruto, re.IGNORECASE):
        bruto = "https://" + bruto
    partes = urlsplit(bruto)
    if partes.scheme.lower() not in ("http", "https") or not partes.hostname:
        raise LinkInvalido("isso nao parece um link")
    return partes, partes.hostname.lower()


def plataforma_de(url: str) -> Optional[str]:
    """A plataforma do link, ou None se nao for de nenhuma das tres."""
    try:
        _, host = _host(url)
    except LinkInvalido:
        return None
    for plataforma, hosts in _HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return plataforma
    return None


def _segmentos(caminho: str) -> list:
    return [s for s in caminho.split("/") if s]


def _youtube(partes, host) -> Post:
    segs = _segmentos(partes.path)
    video = None
    curto_de_shorts = False
    if host.endswith("youtu.be"):
        video = segs[0] if segs else None
    elif segs and segs[0] in ("shorts", "live", "embed", "v"):
        video = segs[1] if len(segs) > 1 else None
        curto_de_shorts = segs[0] == "shorts"
    elif segs and segs[0] == "watch":
        video = (parse_qs(partes.query).get("v") or [None])[0]
    if not video or not _ID_YOUTUBE.match(video):
        raise LinkInvalido("esse link do YouTube nao e de um video; abra o video "
                           "e copie o link dele")
    url = (f"https://www.youtube.com/shorts/{video}" if curto_de_shorts
           else f"https://www.youtube.com/watch?v={video}")
    return Post("youtube", video, url)


def _tiktok(partes, host) -> Post:
    segs = _segmentos(partes.path)
    if host in _TIKTOK_CURTOS or (segs and segs[0] == "t" and len(segs) > 1):
        codigo = segs[-1] if segs else ""
        if not re.match(r"^[A-Za-z0-9_-]{4,40}$", codigo or ""):
            raise LinkInvalido("esse link curto do TikTok esta incompleto")
        return Post("tiktok", None, f"https://{host}/{'/'.join(segs)}/", curto=True)
    # /@conta/video/<id>, /@conta/photo/<id>, /v/<id>.html, /embed/v2/<id>
    if len(segs) >= 3 and segs[0].startswith("@") and segs[1] in ("video", "photo"):
        conta, video = segs[0], segs[2]
        if _ID_TIKTOK.match(video):
            return Post("tiktok", video, f"https://www.tiktok.com/{conta}/{segs[1]}/{video}")
    for seg in reversed(segs):
        candidato = seg[:-5] if seg.endswith(".html") else seg
        if _ID_TIKTOK.match(candidato):
            # Sem a conta no link nao da para montar o endereco de sempre: fica
            # o que a pessoa colou, sem o rastreador de compartilhamento.
            return Post("tiktok", candidato, f"https://{host}{partes.path}")
    raise LinkInvalido("esse link do TikTok nao e de um video; abra o video e "
                       "copie o link dele")


def _instagram(partes, host) -> Post:
    segs = _segmentos(partes.path)
    for i, seg in enumerate(segs[:-1]):
        if seg in ("reel", "reels", "p", "tv"):
            codigo = segs[i + 1]
            if _CODIGO_INSTAGRAM.match(codigo):
                return Post("instagram", codigo,
                            f"https://www.instagram.com/reel/{codigo}/")
    raise LinkInvalido("esse link do Instagram nao e de um post; abra o reel e "
                       "copie o link dele")


def ler(url: str) -> Post:
    """O post que o link aponta. Levanta `LinkInvalido` com a frase da tela."""
    partes, host = _host(url)
    plataforma = plataforma_de(url)
    if plataforma == "youtube":
        return _youtube(partes, host)
    if plataforma == "tiktok":
        return _tiktok(partes, host)
    if plataforma == "instagram":
        return _instagram(partes, host)
    raise LinkInvalido("esse link nao e do YouTube, do TikTok nem do Instagram")


def ler_para(plataforma: str, url: str) -> Post:
    """`ler`, conferindo que o link e da plataforma do galho."""
    post = ler(url)
    if post.plataforma != plataforma:
        raise LinkInvalido(
            f"esse link e do {NOMES[post.plataforma]}, e esta publicacao e do "
            f"{NOMES.get(plataforma, plataforma)}")
    return post


def resolver_link_curto(url: str, timeout: float = 8.0) -> Optional[str]:
    """O endereco completo por tras de um link curto do TikTok, ou None.

    Segue UM redirecionamento, sem abrir a pagina de destino: o link curto
    responde 301 com o endereco completo, e e so isso que se quer dele. Nunca
    levanta -- sem rede, o link curto fica guardado como esta.
    """
    try:
        import httpx
        resposta = httpx.get(url, follow_redirects=False, timeout=timeout,
                             headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None
    destino = resposta.headers.get("location")
    if resposta.status_code in (301, 302, 303, 307, 308) and destino:
        return destino
    return None


def ler_com_rede(plataforma: str, url: str) -> Post:
    """`ler_para`, seguindo o link curto do TikTok quando ele vier.

    Fica com o link curto se a volta pela rede nao der um endereco de video:
    o que a pessoa colou nunca se perde por causa da rede.
    """
    post = ler_para(plataforma, url)
    if not post.curto:
        return post
    completo = resolver_link_curto(post.url)
    if not completo:
        return post
    try:
        resolvido = ler_para(plataforma, completo)
    except LinkInvalido:
        return post
    return resolvido if resolvido.id else post
