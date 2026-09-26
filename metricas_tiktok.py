"""Medir o TikTok -- a API de exibicao (Display API), etapa 7.4.

O que o TikTok da de um video da propria conta: visualizacoes, curtidas,
comentarios e compartilhamentos (`video/query`). **Retencao, nao**: a
documentacao da API de exibicao nao tem, e este modulo nao inventa -- o campo
fica None, e a calibracao sabe que None nao e zero.

### Uma conexao so de LER, separada da de postar

A mesma regra do YouTube (`metrics_collector.py`): duas credenciais pequenas em
vez de uma grande. A de postar (`video.publish`, 7.3c) nao le; a de medir
(`user.info.basic` + `video.list`) nao posta. Cada uma mora no seu endereco do
cofre -- `vault://local/tiktok/<conta>` e `vault://local/tiktok-metrics/<conta>`
--, e a pessoa conecta cada uma pelo seu botao.

### O que so da para medir

- **Post publico.** Antes da auditoria do TikTok, o que sai pela API e
  `SELF_ONLY`, e o TikTok nao devolve o id de um post privado: sem id, nada a
  perguntar. O post feito a mao, com o link colado no "ja publiquei", tem o id
  no proprio link.
- **Video da conta conectada.** A consulta so responde pelos videos de quem
  autorizou; um id de outra conta volta vazio, e vazio aqui e None.

### O refresh token muda a cada renovacao

Como no driver de postar: o TikTok pode devolver outro refresh token, e o
velho deixa de valer. O novo e gravado ANTES de seguir -- perde-lo seria perder
a conexao em silencio na coleta seguinte.

Rede isolada (`_consultar`), decisao pura (`lotes`, `parse_videos`,
`erro_da_consulta`) -- a mesma divisao dos outros coletores.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from publishers.base import PublisherError

CONSULTA = "https://open.tiktokapis.com/v2/video/query/"

#: Os campos pedidos. `id` volta para casar a resposta com a publicacao: a
#: ordem da resposta nao e a do pedido.
CAMPOS_DO_VIDEO = ("id", "view_count", "like_count", "comment_count", "share_count")

#: Quantos ids por consulta. E o limite da API (`video_ids`, ate 20).
LOTE = 20

#: O que a credencial de medir precisa ter. O cadastro do app vai junto do
#: token, como na de postar: o refresh token so vale com o app que o emitiu.
CAMPOS = ("client_key", "client_secret", "refresh_token")

REF = "vault://local/tiktok-metrics/{handle}"

_ID = re.compile(r"^\d{8,25}$")


def ref_de(handle: str) -> str:
    return REF.format(handle=handle or "conta")


def credencial(handle: str) -> Optional[dict]:
    """O segredo de medir desta conta, ou None se ainda nao foi conectada."""
    import vault
    try:
        return vault.resolve(ref_de(handle), exigir=CAMPOS)
    except vault.VaultError:
        return None


# --------------------------------------------------------------------------- #
# Decisao -- puro
# --------------------------------------------------------------------------- #

def lotes(ids: Iterable[str]) -> list:
    """Os ids em lotes de `LOTE`, sem repetir e so os que sao id de video.

    Um id torto (o link curto que nao deu para seguir nunca vira id, mas um
    `remote_id` escrito a mao poderia) derrubaria a consulta do lote inteiro.
    """
    vistos, validos = set(), []
    for bruto in ids:
        vid = str(bruto or "").strip()
        if _ID.match(vid) and vid not in vistos:
            vistos.add(vid)
            validos.append(vid)
    return [validos[i:i + LOTE] for i in range(0, len(validos), LOTE)]


def _inteiro(bruto) -> Optional[int]:
    if bruto is None or isinstance(bruto, bool):
        return None
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return None
    return valor if valor >= 0 else None


def parse_videos(payload: dict) -> dict:
    """`{id: {views, likes, comments, shares}}` da resposta de `video/query`.

    Video que nao veio na resposta fica de fora (a publicacao nao e medida
    nesta volta), e campo que nao veio e None -- nunca zero.
    """
    try:
        videos = ((payload or {}).get("data") or {}).get("videos") or []
    except AttributeError:
        return {}
    saida = {}
    for video in videos if isinstance(videos, list) else []:
        if not isinstance(video, dict) or video.get("id") is None:
            continue
        saida[str(video["id"])] = {
            "views": _inteiro(video.get("view_count")),
            "likes": _inteiro(video.get("like_count")),
            "comments": _inteiro(video.get("comment_count")),
            "shares": _inteiro(video.get("share_count")),
        }
    return saida


_FRASES = {
    "scope_not_authorized":
        "A conexao de medir do TikTok nao tem permissao de ver os videos (video.list). "
        "Confira se o app tem a Display API e conecte para medir de novo.",
    "access_token_invalid":
        "A conexao de medir do TikTok venceu. Conecte para medir de novo.",
    "rate_limit_exceeded":
        "Muitos pedidos ao TikTok agora; a proxima coleta tenta de novo.",
}


def erro_da_consulta(status: int, dados: dict) -> PublisherError:
    """A recusa do TikTok numa frase de MEDIR -- a do driver fala em postar."""
    erro = (dados or {}).get("error") if isinstance(dados, dict) else None
    codigo = erro.get("code") if isinstance(erro, dict) else (erro or "")
    if codigo in _FRASES:
        return PublisherError(_FRASES[codigo])
    from publishers import tiktok_api
    return tiktok_api.erro_do_tiktok(status, dados)


# --------------------------------------------------------------------------- #
# Rede -- o que o CI nao alcanca
# --------------------------------------------------------------------------- #

def _consultar(token: str, ids: list) -> dict:
    import httpx

    from publishers import tiktok_api
    r = httpx.post(CONSULTA, params={"fields": ",".join(CAMPOS_DO_VIDEO)},
                   json={"filters": {"video_ids": ids}}, timeout=30.0,
                   headers={"Authorization": f"Bearer {token}",
                            "Content-Type": "application/json; charset=UTF-8"})
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    if r.status_code != 200 or not tiktok_api._ok(dados):
        raise erro_da_consulta(r.status_code, dados)
    return dados


def _token(handle: str, segredo: dict) -> str:
    """Um access token, gravando o refresh token novo se o TikTok trocou."""
    import vault

    from publishers import tiktok_api
    try:
        tokens = tiktok_api.renovar(segredo)
    except PublisherError as e:
        raise PublisherError(f"a conexao de medir do TikTok nao renovou ({e}). "
                             "Conecte para medir de novo.")
    novo = tokens.get("refresh_token")
    if novo and novo != segredo["refresh_token"]:
        vault.gravar(ref_de(handle), {**segredo, "refresh_token": novo})
    return tokens["access_token"]


def medir(handle: str, ids: Iterable[str]) -> dict:
    """`{id: numeros}` dos videos desta conta. Levanta `PublisherError`.

    Um token por coleta, e nao por video: sao ate 20 ids por consulta.
    """
    grupos = lotes(ids)
    if not grupos:
        return {}
    segredo = credencial(handle)
    if segredo is None:
        raise PublisherError(
            f"a conta {handle} do TikTok ainda nao esta conectada para MEDIR. "
            "Conecte pelo botao \"conectar para medir\" da conta.")
    token = _token(handle, segredo)
    saida = {}
    for grupo in grupos:
        saida.update(parse_videos(_consultar(token, grupo)))
    return saida
