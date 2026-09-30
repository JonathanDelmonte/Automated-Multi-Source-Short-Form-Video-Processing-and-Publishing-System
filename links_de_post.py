"""O link de um post, lido por plataforma (Fase 7, etapa 7.3).

O "ja publiquei" da fila manual passou a pedir o link do post. Sem ele, o que
se posta a mao nunca e medido: o coletor de metricas precisa do id do video, e
o id so existe do lado da plataforma.

Cada plataforma com os jeitos de copiar um link que existem de verdade -- o
botao "copiar link" do app nao da o mesmo endereco da barra do navegador:

- **YouTube**: `youtube.com/shorts/<id>`, `watch?v=<id>`, `youtu.be/<id>`,
  `/live/<id>`. O id tem 11 caracteres, e e o que a API de metricas le.
- **TikTok**: `tiktok.com/@<conta>/video/<id>` no navegador; no app, o
  "copiar link" da o **link curto** (`vm.tiktok.com/<codigo>`), que nao carrega
  o id -- so redireciona para o endereco completo. `resolver_link_curto` segue
  esse unico redirecionamento; sem rede, o link fica guardado e o id nao.
- **Instagram**: `instagram.com/reel/<codigo>/` (e `/p/`, `/tv/`, e o formato
  com a conta na frente). O codigo nao e o id da API -- a Fase 7.4 acha o id
  pela lista de posts da conta, casando pelo link.
- **As chinesas** (etapa 7.10): `douyin.com/video/<id>`, `kuaishou.com/short-video/<id>`,
  `bilibili.com/video/BV...` e `xiaohongshu.com/explore/<id>`, e o link curto
  de cada app (`v.douyin.com`, `v.kuaishou.com`, `b23.tv`, `xhslink.com`). O
  "compartilhar" desses apps copia um TEXTO com o link no meio ("7.94 复制打开抖音，
  看看... https://v.douyin.com/abc/ :9pm"): o link e tirado de dentro dele.

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
from urllib.parse import parse_qs, urlencode, urlsplit

import plataformas

PLATAFORMAS = plataformas.IDS
NOMES = plataformas.NOMES

_HOSTS = {
    "youtube": ("youtube.com", "youtu.be", "youtube-nocookie.com"),
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
    # A pagina de compartilhar do Douyin mora no iesdouyin.com.
    "douyin": ("douyin.com", "iesdouyin.com"),
    # O link do app do Kuaishou abre uma pagina no chenzhongtech.com ou no
    # gifshow.com (o nome antigo do app). O Kwai (kwai.com) e o app de fora da
    # China, outra plataforma: nao entra.
    "kuaishou": ("kuaishou.com", "chenzhongtech.com", "gifshow.com"),
    # O bilibili.tv e o Bilibili de fora da China, outra plataforma: nao entra.
    "bilibili": ("bilibili.com", "b23.tv", "bili2233.cn"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
}

_ID_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_ID_TIKTOK = re.compile(r"^\d{8,25}$")
_CODIGO_INSTAGRAM = re.compile(r"^[A-Za-z0-9_-]{5,64}$")
_ID_DOUYIN = _ID_TIKTOK
_ID_KUAISHOU = re.compile(r"^[A-Za-z0-9_-]{6,40}$")
_BV = re.compile(r"^[Bb][Vv]([0-9A-Za-z]{10})$")
_AV = re.compile(r"^[Aa][Vv](\d{1,20})$")
_ID_XIAOHONGSHU = re.compile(r"^[0-9a-f]{24}$")
_CODIGO_CURTO = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

#: Os hosts de link curto de cada app: nao carregam o id, so redirecionam para
#: o endereco completo (`resolver_link_curto`).
_CURTOS = {
    "tiktok": ("vm.tiktok.com", "vt.tiktok.com"),
    "douyin": ("v.douyin.com",),
    "kuaishou": ("v.kuaishou.com",),
    "bilibili": ("b23.tv", "bili2233.cn"),
    "xiaohongshu": ("xhslink.com",),
}
_TIKTOK_CURTOS = _CURTOS["tiktok"]

#: Um link dentro de um texto: so os caracteres de URL em ASCII, para parar na
#: pontuacao chinesa que os apps poem colada nele ("...abc/，复制本条信息").
_LINK_NO_TEXTO = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")


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


def extrair_link(texto: str) -> str:
    """O link de dentro do que a pessoa colou.

    Os apps chineses copiam um texto com o link no meio ("【标题-哔哩哔哩】
    https://b23.tv/abc", "...复制打开抖音 https://v.douyin.com/xyz/ :9pm"). Um
    texto sem espaco e sem letra fora do ASCII e o proprio link, como sempre foi
    -- inclusive sem `https://`. Com espaco ou com letra de fora, vale o primeiro
    `http(s)://` de dentro dele.
    """
    bruto = (texto or "").strip()
    if not bruto or (not re.search(r"\s", bruto) and bruto.isascii()):
        return bruto
    achado = _LINK_NO_TEXTO.search(bruto)
    if not achado:
        return bruto
    # Pontuacao ASCII colada no fim ("...abc/." ou "...abc/,") nao e do link.
    return achado.group(0).rstrip(".,;:!?)]'\"")


def _host(url: str) -> tuple:
    bruto = extrair_link(url)
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


def _do_host(host: str, hosts) -> bool:
    return any(host == h or host.endswith("." + h) for h in hosts)


def plataforma_de(url: str) -> Optional[str]:
    """A plataforma do link, ou None se nao for de nenhuma que o programa conhece."""
    try:
        _, host = _host(url)
    except LinkInvalido:
        return None
    for plataforma, hosts in _HOSTS.items():
        if _do_host(host, hosts):
            return plataforma
    return None


def _segmentos(caminho: str) -> list:
    return [s for s in caminho.split("/") if s]


def _curto(plataforma: str, partes, host: str, nome: str) -> Post:
    """O link curto de um app, guardado como veio: o id so vem seguindo-o. O
    caminho fica exatamente como o app o escreveu (com ou sem barra no fim):
    e o servidor dele que o le, e nem todo aceita a barra a mais."""
    segs = _segmentos(partes.path)
    codigo = segs[-1] if segs else ""
    if not _CODIGO_CURTO.match(codigo or ""):
        raise LinkInvalido(f"esse link curto do {nome} esta incompleto")
    return Post(plataforma, None, f"https://{host}{partes.path}", curto=True)


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


def _douyin(partes, host) -> Post:
    """`douyin.com/video/<id>` (e `/note/` para foto), a pagina de compartilhar
    do app (`iesdouyin.com/share/video/<id>/`) e o video aberto por cima de
    outra pagina no navegador (`?modal_id=<id>`)."""
    segs = _segmentos(partes.path)
    if host in _CURTOS["douyin"]:
        return _curto("douyin", partes, host, "Douyin")
    tipo = video = None
    for i, seg in enumerate(segs[:-1]):
        if seg in ("video", "note"):
            tipo, video = seg, segs[i + 1]
            break
    if not video:
        tipo, video = "video", (parse_qs(partes.query).get("modal_id") or [None])[0]
    if video and _ID_DOUYIN.match(video):
        return Post("douyin", video, f"https://www.douyin.com/{tipo}/{video}")
    raise LinkInvalido("esse link do Douyin nao e de um video; abra o video e "
                       "copie o link dele")


def _kuaishou(partes, host) -> Post:
    """`kuaishou.com/short-video/<id>`, a pagina que o link do app abre
    (`.../fw/photo/<id>`) e o endereco antigo com a conta (`/u/<conta>/<id>`).
    O `kuaishou.com/f/<codigo>` e link curto, como o `v.kuaishou.com`."""
    segs = _segmentos(partes.path)
    if host in _CURTOS["kuaishou"] or (segs and segs[0] == "f" and len(segs) > 1):
        return _curto("kuaishou", partes, host, "Kuaishou")
    video = None
    for i, seg in enumerate(segs[:-1]):
        if seg in ("short-video", "photo"):
            video = segs[i + 1]
            break
    if not video and len(segs) == 3 and segs[0] == "u":
        video = segs[2]
    if video and _ID_KUAISHOU.match(video):
        return Post("kuaishou", video, f"https://www.kuaishou.com/short-video/{video}")
    raise LinkInvalido("esse link do Kuaishou nao e de um video; abra o video e "
                       "copie o link dele")


def _bilibili(partes, host) -> Post:
    """`bilibili.com/video/BV.../` (e `m.bilibili.com`, e o numero antigo
    `av...`), o `?bvid=` das paginas de evento e o link curto do app (`b23.tv`)
    -- que as vezes ja traz o BV (`b23.tv/BV...`): ai o id sai sem rede."""
    segs = _segmentos(partes.path)
    video = None
    if host in _CURTOS["bilibili"]:
        if segs and _BV.match(segs[0]):
            video = segs[0]
        else:
            return _curto("bilibili", partes, host, "Bilibili")
    if not video:
        for i, seg in enumerate(segs[:-1]):
            if seg == "video":
                video = segs[i + 1]
                break
    if not video:
        video = (parse_qs(partes.query).get("bvid") or [None])[0]
    bv = _BV.match(video or "")
    if bv:
        video = "BV" + bv.group(1)
    else:
        av = _AV.match(video or "")
        video = f"av{av.group(1)}" if av else None
    if video:
        return Post("bilibili", video, f"https://www.bilibili.com/video/{video}/")
    raise LinkInvalido("esse link do Bilibili nao e de um video; abra o video e "
                       "copie o link dele")


def _xiaohongshu(partes, host) -> Post:
    """`xiaohongshu.com/explore/<id>` (e `/discovery/item/<id>` e a nota aberta
    no perfil, `/user/profile/<conta>/<id>`), e o link curto do app
    (`xhslink.com`). O `xsec_token` fica no link: sem ele a pagina da nota nao
    abre fora do app, entao ele nao e rastreador -- e a chave da porta."""
    segs = _segmentos(partes.path)
    if host in _CURTOS["xiaohongshu"]:
        return _curto("xiaohongshu", partes, host, "Xiaohongshu")
    nota = None
    if len(segs) >= 2 and segs[0] == "explore":
        nota = segs[1]
    elif len(segs) >= 3 and segs[:2] == ["discovery", "item"]:
        nota = segs[2]
    elif len(segs) >= 4 and segs[:2] == ["user", "profile"]:
        nota = segs[3]
    if nota and _ID_XIAOHONGSHU.match(nota):
        url = f"https://www.xiaohongshu.com/explore/{nota}"
        token = (parse_qs(partes.query).get("xsec_token") or [None])[0]
        if token:
            url += "?" + urlencode({"xsec_token": token})
        return Post("xiaohongshu", nota, url)
    raise LinkInvalido("esse link do Xiaohongshu nao e de uma nota; abra o video "
                       "e copie o link dele")


_LEITORES = {
    "youtube": _youtube, "tiktok": _tiktok, "instagram": _instagram,
    "douyin": _douyin, "kuaishou": _kuaishou, "bilibili": _bilibili,
    "xiaohongshu": _xiaohongshu,
}


def ler(url: str) -> Post:
    """O post que o link aponta. Levanta `LinkInvalido` com a frase da tela."""
    partes, host = _host(url)
    plataforma = plataforma_de(url)
    if plataforma in _LEITORES:
        return _LEITORES[plataforma](partes, host)
    raise LinkInvalido("esse link nao e de uma plataforma que o programa conhece ("
                       + ", ".join(NOMES[p] for p in PLATAFORMAS[:-1])
                       + f" ou {NOMES[PLATAFORMAS[-1]]})")


def ler_para(plataforma: str, url: str) -> Post:
    """`ler`, conferindo que o link e da plataforma do galho."""
    post = ler(url)
    if post.plataforma != plataforma:
        raise LinkInvalido(
            f"esse link e do {NOMES[post.plataforma]}, e esta publicacao e do "
            f"{NOMES.get(plataforma, plataforma)}")
    return post


def resolver_link_curto(url: str, timeout: float = 8.0) -> Optional[str]:
    """O endereco completo por tras de um link curto, ou None.

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


#: Quantos redirecionamentos um link curto pode dar ate o endereco do video.
#: Um e o normal; o segundo cobre o app que passa por uma pagina intermediaria.
SALTOS_DO_LINK_CURTO = 2


def ler_com_rede(plataforma: str, url: str) -> Post:
    """`ler_para`, seguindo o link curto quando ele vier.

    Fica com o link curto se a volta pela rede nao der um endereco de video:
    o que a pessoa colou nunca se perde por causa da rede.
    """
    post = ler_para(plataforma, url)
    atual = post
    for _ in range(SALTOS_DO_LINK_CURTO):
        if not atual.curto:
            break
        completo = resolver_link_curto(atual.url)
        if not completo:
            return post
        try:
            atual = ler_para(plataforma, completo)
        except LinkInvalido:
            return post
    return atual if atual.id else post
