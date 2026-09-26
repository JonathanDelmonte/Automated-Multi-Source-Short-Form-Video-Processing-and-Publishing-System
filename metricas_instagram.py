"""Medir o Instagram -- a API de contas profissionais, etapa 7.4.

O Instagram publica pelo pacote do dia nesta versao (7.3d, o porque esta no
plano), mas MEDIR e outra conversa: ler numeros nao envia video, e a API oficial
de conta profissional (Instagram API com login do Instagram) le os posts da
propria conta.

### O token e colado, e nao conectado por botao

Ao contrario do Google e do TikTok, a Meta exige endereco de volta **HTTPS**
cadastrado para o login -- e o programa atende em `http://localhost`. O caminho
que sobra, e que a Meta oferece para isso, e o painel do app dela: "Gerar
token", que da um token de 60 dias da conta que a pessoa entrar. Colado em
Configuracoes, ele e conferido na hora (`conferir`):

- **e da conta certa?** O `@` que o Instagram devolve tem de ser o da conta no
  programa. Medir a conta errada seria pior que nao medir -- os numeros
  entrariam na calibracao como se fossem destes cortes;
- **o Instagram aceita?** Token recusado nao entra.

### O token dura 60 dias, e o programa o renova

`refresh_access_token` da mais 60 dias a um token que tenha pelo menos 24 h e
ainda valha. O coletor renova quando a ultima renovacao passou de
`RENOVAR_APOS` (uma semana): com a maquina ligada de vez em quando, o token
nunca vence. Se vencer (a maquina ficou dois meses desligada), o Instagram
responde o codigo 190, a conexao fica marcada como vencida, e a tela pede um
token novo.

### O que da para medir, e o que e conta

- **O link do post e o endereco.** O "ja publiquei" guarda o codigo do link
  (`/reel/<codigo>/`), que nao e o id da API: o coletor le a lista de posts da
  conta e casa pelo codigo. Post que nao esta na lista nao e desta conta, e
  fica sem numero.
- **Curtidas e comentarios** vem da propria lista; **visualizacoes, alcance,
  salvamentos, compartilhamentos e tempo medio assistido** vem dos insights de
  cada post. O nome das metricas ja mudou duas vezes em 2025 (`plays` e
  `impressions` sairam, entrou `views`), entao os insights sao pedidos por uma
  cadeia de conjuntos: um nome recusado nunca custa os outros numeros.
- **A retencao e DERIVADA**: tempo medio assistido / duracao do corte, com teto
  de 100% (reel repete, e a media pode passar da duracao). O Instagram nao da
  porcentagem; o YouTube da. Sem a duracao do corte, fica None.
- O tempo medio vem em **milissegundos**; aqui vira segundos, como o do YouTube.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from publishers.base import PublisherError

#: A API do Instagram com login do Instagram. Sem versao no caminho: a Meta
#: responde pela versao corrente do app, e uma versao fixa aqui venceria.
GRAPH = (os.environ.get("INSTAGRAM_GRAPH_URL") or "https://graph.instagram.com").rstrip("/")

REF = "vault://local/instagram-metrics/{handle}"
#: O que a credencial precisa ter para medir.
CAMPOS = ("access_token", "user_id")

#: De quanto em quanto tempo renovar o token (ele dura 60 dias).
RENOVAR_APOS = timedelta(days=7)

#: A lista de posts, em paginas. Para de ler assim que achou todos os codigos
#: procurados; o teto existe para uma conta enorme nao virar um laco longo.
POR_PAGINA = 50
PAGINAS_MAXIMAS = 20
CAMPOS_DA_MIDIA = ("id", "shortcode", "permalink", "media_product_type",
                   "like_count", "comments_count", "timestamp")

#: Os insights, do conjunto mais completo ao menor. Um nome recusado (a Meta
#: renomeia metricas; post antigo ou de feed nao tem as de reel) passa ao
#: seguinte, e nunca derruba os outros numeros.
CONJUNTOS_DE_METRICAS = (
    ("views", "reach", "saved", "shares", "ig_reels_avg_watch_time"),
    ("views", "reach", "saved", "shares"),
    ("reach", "saved"),
)

_TOKEN = re.compile(r"^[A-Za-z0-9._|%-]{30,2048}$")

#: Os codigos de "muitos pedidos" da Meta: parar e tentar na proxima coleta.
_LIMITE = (4, 17, 32, 613)


class ErroDoInstagram(PublisherError):
    """Uma recusa da Meta, com o status HTTP e o codigo dela."""

    def __init__(self, texto: str, status: int = 0, codigo=None):
        super().__init__(texto)
        self.status = status
        self.codigo = codigo


class TokenInvalido(ErroDoInstagram):
    """O Instagram recusou o token (codigo 190): venceu, foi revogado ou a
    senha da conta mudou. So um token novo resolve."""


class SemPermissao(ErroDoInstagram):
    """O token vale, mas sem a permissao de ler os numeros."""


class TokenRecusado(ValueError):
    """O token colado nao entra. `codigo`: formato | recusado | outra_conta |
    sem_resposta | permissao."""

    def __init__(self, codigo: str, detalhe: str = ""):
        super().__init__(detalhe or codigo)
        self.codigo = codigo
        self.detalhe = detalhe


def ref_de(handle: str) -> str:
    return REF.format(handle=handle or "conta")


def credencial(handle: str) -> Optional[dict]:
    """O token de medir desta conta, ou None se nao ha -- ou se venceu."""
    import vault
    try:
        segredo = vault.resolve(ref_de(handle), exigir=CAMPOS)
    except vault.VaultError:
        return None
    return None if segredo.get("vencido") else segredo


def situacao(handle: str) -> str:
    """`conectado`, `vencido` ou `nao` -- sem rede, para a tela."""
    import vault
    try:
        segredo = vault.resolve(ref_de(handle), exigir=CAMPOS)
    except vault.VaultError:
        return "nao"
    return "vencido" if segredo.get("vencido") else "conectado"


# --------------------------------------------------------------------------- #
# Decisao -- puro
# --------------------------------------------------------------------------- #

def limpar_token(texto: str) -> str:
    """O token como a pessoa o colou, sem o que costuma vir junto por engano:
    aspas, `access_token=`, `Bearer ` e espacos nas pontas. Levanta
    `TokenRecusado("formato")` se ainda nao parecer um token."""
    limpo = (texto or "").strip().strip("\"'").strip()
    for prefixo in ("access_token=", "Bearer ", "bearer "):
        if limpo.startswith(prefixo):
            limpo = limpo[len(prefixo):].strip()
    if not _TOKEN.match(limpo):
        raise TokenRecusado("formato")
    return limpo


def arroba(texto: str) -> str:
    """O `@` comparavel: sem o `@`, sem espacos, minusculo."""
    return (texto or "").strip().lstrip("@").strip().lower()


def parse_me(payload: dict) -> dict:
    """`{user_id, username}` de `GET /me`. Levanta `TokenRecusado` se faltar."""
    if not isinstance(payload, dict):
        raise TokenRecusado("recusado")
    user_id = str(payload.get("user_id") or payload.get("id") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not user_id or not username:
        raise TokenRecusado("recusado")
    return {"user_id": user_id, "username": username}


def codigo_do_link(midia: dict) -> Optional[str]:
    """O codigo do post (o do link `/reel/<codigo>/`), pelo campo ou pelo link."""
    codigo = str((midia or {}).get("shortcode") or "").strip()
    if codigo:
        return codigo
    link = (midia or {}).get("permalink")
    if not link:
        return None
    import links_de_post
    try:
        return links_de_post.ler_para("instagram", link).id
    except links_de_post.LinkInvalido:
        return None


def indice_de_midias(midias: Iterable[dict]) -> dict:
    """`{codigo: midia}` da lista de posts da conta."""
    indice = {}
    for midia in midias or []:
        if not isinstance(midia, dict) or not midia.get("id"):
            continue
        codigo = codigo_do_link(midia)
        if codigo:
            indice[codigo] = midia
    return indice


def _numero(bruto, tipo=int):
    if bruto is None or isinstance(bruto, bool):
        return None
    try:
        valor = tipo(bruto)
    except (TypeError, ValueError):
        return None
    return valor if valor >= 0 else None


def parse_insights(payload: dict) -> dict:
    """`{nome: valor}` da resposta de `/<midia>/insights`.

    A resposta traz `values: [{"value": ...}]` (a forma de sempre) ou
    `total_value: {"value": ...}` (a das metricas novas): as duas valem.
    """
    saida = {}
    for item in ((payload or {}).get("data") or []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        valor = None
        valores = item.get("values")
        if isinstance(valores, list) and valores and isinstance(valores[0], dict):
            valor = valores[0].get("value")
        if valor is None and isinstance(item.get("total_value"), dict):
            valor = item["total_value"].get("value")
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            saida[item["name"]] = valor
    return saida


def retencao(avg_watch_s: Optional[float], duracao_s: Optional[float]) -> Optional[float]:
    """Tempo medio assistido / duracao do corte, em %, com teto de 100.

    O teto e porque reel repete: a media de quem assistiu duas vezes passa da
    duracao, e 180% de retencao seria um numero que nao quer dizer nada."""
    if not avg_watch_s or not duracao_s or duracao_s <= 0:
        return None
    return round(min(100.0, 100.0 * avg_watch_s / duracao_s), 2)


def numeros(midia: dict, insights: dict, duracao_s: Optional[float] = None) -> dict:
    """Os numeros de um post: a lista da as curtidas e os comentarios, os
    insights dao o resto. O tempo medio chega em MILISSEGUNDOS."""
    medio_ms = _numero(insights.get("ig_reels_avg_watch_time"), float)
    avg_watch_s = round(medio_ms / 1000.0, 2) if medio_ms is not None else None
    return {
        "views": _numero(insights.get("views")),
        "likes": _numero((midia or {}).get("like_count")),
        "comments": _numero((midia or {}).get("comments_count")),
        "shares": _numero(insights.get("shares")),
        "saves": _numero(insights.get("saved")),
        "avg_watch_s": avg_watch_s,
        "retention_pct": retencao(avg_watch_s, duracao_s),
    }


def precisa_renovar(segredo: dict, agora: Optional[datetime] = None) -> bool:
    """Se a ultima renovacao (ou a colagem) passou de `RENOVAR_APOS`."""
    agora = agora or datetime.now(timezone.utc)
    try:
        ultima = datetime.fromisoformat(segredo.get("renovado_em") or "")
    except ValueError:
        return True
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    return agora - ultima >= RENOVAR_APOS


def erro_do_instagram(status: int, dados: dict) -> ErroDoInstagram:
    """A resposta de erro da Meta numa frase que diz o que fazer.

    Nunca repete o token: a mensagem de erro da Meta nao o traz, e a frase
    daqui so usa o codigo e a mensagem."""
    erro = (dados or {}).get("error") if isinstance(dados, dict) else None
    erro = erro if isinstance(erro, dict) else {}
    codigo = erro.get("code")
    mensagem = str(erro.get("message") or "")[:200]
    if codigo == 190:
        return TokenInvalido("o token do Instagram venceu ou foi revogado. "
                             "Cole um novo nas contas.", status, codigo)
    if codigo in (10, 200) or "permission" in mensagem.lower():
        return SemPermissao("o token do Instagram nao tem a permissao de ler os "
                            "numeros (instagram_business_manage_insights). Gere "
                            "outro com ela marcada.", status, codigo)
    if codigo in _LIMITE:
        return ErroDoInstagram("muitos pedidos ao Instagram agora; a proxima "
                               "coleta tenta de novo.", status, codigo)
    return ErroDoInstagram(f"o Instagram respondeu {status}: {mensagem or 'erro'}",
                           status, codigo)


# --------------------------------------------------------------------------- #
# Rede -- o que o CI nao alcanca
# --------------------------------------------------------------------------- #

def _get(caminho: str, token: Optional[str], params: Optional[dict] = None,
         timeout: float = 30.0) -> dict:
    """Um GET na API. `caminho` pode ser o endereco inteiro da pagina seguinte
    (`paging.next`), que ja traz o token: ai `token` e None."""
    import httpx

    url = caminho if caminho.startswith("https://") else f"{GRAPH}/{caminho.lstrip('/')}"
    parametros = dict(params or {})
    if token:
        parametros["access_token"] = token
    try:
        r = httpx.get(url, params=parametros or None, timeout=timeout)
    except httpx.HTTPError as e:
        # O token vai no ENDERECO (e a convencao da API, e a pagina seguinte ja
        # o traz), e a mensagem de uma excecao de rede pode repetir o
        # endereco: ela chegaria ao log do coletor, que aparece no painel. So
        # o tipo sai daqui.
        raise ErroDoInstagram(f"sem resposta do Instagram ({type(e).__name__})") from None
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    if r.status_code != 200 or (isinstance(dados, dict) and dados.get("error")):
        raise erro_do_instagram(r.status_code, dados)
    return dados if isinstance(dados, dict) else {}


def conferir(texto: str, handle: str) -> dict:
    """O que guardar, depois de conferir o token colado com o Instagram.

    Levanta `TokenRecusado`: `formato`, `recusado` (o Instagram nao aceitou),
    `outra_conta` (o token e de outro @) ou `sem_resposta`."""
    token = limpar_token(texto)
    try:
        try:
            me = parse_me(_get("me", token, {"fields": "user_id,username"}))
        except ErroDoInstagram as e:
            # `user_id` e o campo da conta profissional; se a versao da API
            # nao o conhecer (codigo 100), o `id` responde pela mesma conta.
            if e.codigo != 100:
                raise
            me = parse_me(_get("me", token, {"fields": "id,username"}))
    except TokenInvalido:
        raise TokenRecusado("recusado")
    except SemPermissao:
        raise TokenRecusado("permissao")
    except ErroDoInstagram as e:
        # 4xx e recusa do token; o resto (5xx, limite) e o Instagram fora do ar.
        raise TokenRecusado("recusado" if 400 <= e.status < 500 and e.codigo not in _LIMITE
                            else "sem_resposta")
    except TokenRecusado:
        raise
    except Exception as e:
        raise TokenRecusado("sem_resposta", type(e).__name__)
    if arroba(me["username"]) != arroba(handle):
        raise TokenRecusado("outra_conta", me["username"])
    return {"access_token": token, "user_id": me["user_id"],
            "username": me["username"],
            "renovado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def renovar(segredo: dict) -> Optional[dict]:
    """O segredo com o token renovado por mais 60 dias, ou None se o Instagram
    nao renovou agora (o token ainda vale; a proxima coleta tenta de novo)."""
    try:
        dados = _get("refresh_access_token", segredo["access_token"],
                     {"grant_type": "ig_refresh_token"})
    except TokenInvalido:
        raise
    except Exception:
        return None
    novo = dados.get("access_token")
    if not novo:
        return None
    return {**segredo, "access_token": novo,
            "renovado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _midias(token: str, procurados: set) -> dict:
    """`{codigo: midia}` dos posts da conta, lendo ate achar os procurados."""
    achados: dict = {}
    proxima = None
    for _ in range(PAGINAS_MAXIMAS):
        if proxima:
            dados = _get(proxima, None)
        else:
            dados = _get("me/media", token, {"fields": ",".join(CAMPOS_DA_MIDIA),
                                             "limit": POR_PAGINA})
        achados.update(indice_de_midias(dados.get("data") or []))
        if procurados <= set(achados):
            break
        proxima = ((dados.get("paging") or {}).get("next"))
        if not proxima or not _mesmo_host(proxima):
            # A pagina seguinte carrega o token no endereco: so se segue a que
            # aponta para a propria API.
            break
    return achados


def _mesmo_host(url: str) -> bool:
    from urllib.parse import urlsplit
    try:
        return urlsplit(url).scheme == "https" and \
            urlsplit(url).hostname == urlsplit(GRAPH).hostname
    except ValueError:
        return False


def _insights(token: str, midia_id: str) -> dict:
    """Os insights do post, pelo primeiro conjunto de metricas que o Instagram
    aceitar. Nenhum aceito (post de antes da conta virar profissional, por
    exemplo) devolve vazio: a lista ja deu curtidas e comentarios."""
    for conjunto in CONJUNTOS_DE_METRICAS:
        try:
            return parse_insights(_get(f"{midia_id}/insights", token,
                                       {"metric": ",".join(conjunto)}))
        except (TokenInvalido, SemPermissao):
            raise
        except ErroDoInstagram as e:
            if e.codigo in _LIMITE:
                raise
            continue
    return {}


def _marcar_vencido(handle: str, segredo: dict) -> None:
    import vault
    try:
        vault.gravar(ref_de(handle), {**segredo, "vencido": "1"})
    except Exception:
        pass


def medir(handle: str, pedidos: Iterable[dict]) -> dict:
    """`{codigo: numeros}` dos posts pedidos desta conta.

    `pedidos`: `[{"id": <codigo do link>, "duracao_s": <segundos ou None>}]`.
    Levanta `PublisherError` (e `TokenInvalido`, que marca a conexao como
    vencida para a tela pedir outro token).
    """
    import vault

    pedidos = [p for p in pedidos or [] if p.get("id")]
    if not pedidos:
        return {}
    segredo = credencial(handle)
    if segredo is None:
        raise PublisherError(
            f"a conta {handle} do Instagram ainda nao tem o token de medir. "
            "Cole o token nas contas.")
    try:
        if precisa_renovar(segredo):
            renovado = renovar(segredo)
            if renovado:
                vault.gravar(ref_de(handle), renovado)
                segredo = renovado
        token = segredo["access_token"]
        indice = _midias(token, {p["id"] for p in pedidos})
        saida = {}
        for pedido in pedidos:
            midia = indice.get(pedido["id"])
            if midia is None:
                continue
            saida[pedido["id"]] = numeros(midia, _insights(token, str(midia["id"])),
                                          pedido.get("duracao_s"))
        return saida
    except TokenInvalido:
        _marcar_vencido(handle, segredo)
        raise
