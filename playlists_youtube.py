"""Uma playlist por serie no YouTube (Fase 7, etapa 7.6).

"No YouTube, uma playlist por serie": quando a primeira parte de uma serie vai
ao ar numa conta do YouTube, a playlist nasce com o nome da serie, e cada parte
publicada entra nela, na ordem das partes.

**E uma terceira conexao, e opcional.** O token de publicar e so
`youtube.upload`, de proposito (se vazar, a diferenca e entre um video
indesejado e um canal vazio), e o de medir e so leitura. Mexer em playlist pede
o escopo `youtube` inteiro -- o Google nao tem um escopo so de playlist
(`playlists.insert` e `playlistItems.insert` aceitam `youtube`,
`youtube.force-ssl` ou `youtubepartner`). Entao a playlist e um consentimento a
parte, "organizar", guardado noutro endereco do cofre
(`vault://local/youtube-playlists/<conta>`), usado so aqui. Sem ele, a serie
sai igual, sem playlist -- e a pessoa monta a playlist no YouTube Studio, se
quiser.

**Cota**: `playlists.insert` e `playlistItems.insert` custam 50 unidades cada,
das 10.000 do dia (as que o coletor de metricas tambem usa). Uma serie de 60
partes gasta 3.050 unidades, e o que nao cabe hoje entra amanha: a playlist se
completa sozinha, na ordem.

Mesmo desenho do driver `youtube-api`: HTTP direto com `httpx`, a rede isolada
em duas funcoes, o resto puro.
"""
from __future__ import annotations

import json
import os
from typing import Optional

URL_PLAYLISTS = "https://www.googleapis.com/youtube/v3/playlists?part=snippet,status"
URL_ITENS = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
URL_DA_PLAYLIST = "https://www.youtube.com/playlist?list="

#: O custo de cada chamada, em unidades da cota do dia (Quota Calculator).
CUSTO_PLAYLIST = 50
CUSTO_ITEM = 50

#: Limites do proprio YouTube para a playlist.
MAX_TITULO = 150
MAX_DESCRICAO = 5000

CAMPOS = ("client_id", "client_secret", "refresh_token")

_DESCRICAO = {
    "pt": "Todas as partes de “{nome}”, na ordem.",
    "en": "Every part of “{nome}”, in order.",
    "es": "Todas las partes de “{nome}”, en orden.",
}


class PlaylistSumiu(RuntimeError):
    """A playlist foi apagada no YouTube: a proxima volta cria outra."""


def ref_de(handle: str) -> str:
    import conexoes
    return conexoes.ref_do_cofre("youtube", "organizar", handle)


def credencial(handle: str) -> Optional[dict]:
    """O segredo de "organizar" desta conta, ou None: sem ele, nao ha playlist."""
    import vault
    try:
        return vault.resolve(ref_de(handle), exigir=CAMPOS)
    except vault.VaultError:
        return None


def privacidade() -> str:
    """A visibilidade da playlist. Publica por padrao, e nao privada como o
    envio agendado: a playlist e so o conteiner, e um video privado dentro de
    uma playlist publica continua invisivel para os outros -- o que ela mostra
    e o que ja e publico. `YOUTUBE_PLAYLIST_PRIVACY` troca; valor torto vira
    privado (`youtube_api.privacidade`)."""
    from publishers import youtube_api
    return youtube_api.privacidade(os.environ.get("YOUTUBE_PLAYLIST_PRIVACY") or "public")


def corpo_da_playlist(nome: str, idioma: Optional[str] = None) -> dict:
    lingua = (idioma or "pt").split("-")[0].lower()
    nome = " ".join((nome or "").split()) or "Série"
    return {
        "snippet": {"title": nome[:MAX_TITULO],
                    "description": _DESCRICAO.get(lingua, _DESCRICAO["pt"]).format(nome=nome)[:MAX_DESCRICAO]},
        "status": {"privacyStatus": privacidade()},
    }


def corpo_do_item(playlist_id: str, video_id: str) -> dict:
    return {"snippet": {"playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}


def _erro(status: int, texto: str) -> Exception:
    from publishers import youtube_api
    try:
        erros = ((json.loads(texto or "{}").get("error") or {}).get("errors") or [])
        razao = erros[0].get("reason") if erros and isinstance(erros[0], dict) else ""
    except (ValueError, AttributeError):
        razao = ""
    if razao == "playlistNotFound":
        return PlaylistSumiu("a playlist foi apagada no YouTube")
    return youtube_api.erro_da_resposta(status, texto)


# --------------------------------------------------------------------------- #
# Rede -- as duas funcoes que o CI nao alcanca
# --------------------------------------------------------------------------- #

def criar(token: str, corpo: dict) -> str:
    """Cria a playlist e devolve o id dela."""
    import httpx
    r = httpx.post(URL_PLAYLISTS, json=corpo, timeout=30.0,
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code not in (200, 201):
        raise _erro(r.status_code, r.text)
    playlist_id = (r.json() or {}).get("id")
    if not playlist_id:
        from publishers.base import PublisherError
        raise PublisherError("o YouTube criou a playlist e nao mandou o id")
    return playlist_id


def inserir(token: str, corpo: dict) -> str:
    """Poe o video no fim da playlist e devolve o id do item."""
    import httpx
    r = httpx.post(URL_ITENS, json=corpo, timeout=30.0,
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code not in (200, 201):
        raise _erro(r.status_code, r.text)
    return (r.json() or {}).get("id") or ""


def token_de_acesso(segredo: dict) -> str:
    from publishers import youtube_api
    return youtube_api._token_de_acesso(segredo)
