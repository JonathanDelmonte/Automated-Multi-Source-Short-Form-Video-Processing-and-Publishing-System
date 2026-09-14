"""Camada de ingestao: uma fonte, uma classe (§4 do Plano Tecnico, Fase 1).

Antes disto a decisao de origem morava em tres lugares que nao sabiam um do
outro: `main.is_youtube_url` (roteamento por host), `main.plan_download_attempts`
(que rotas de rede tentar) e o bloco `__main__` do `main.py` (URL ou arquivo
local). Nenhum deles era o dono da pergunta "que tipo de fonte e esta?", e cada
fonte nova -- Twitch, live, Drive -- multiplicava os tres.

Aqui cada fonte e uma classe com `matches` / `probe` / `fetch`, e o pipeline
recebe sempre a mesma coisa: um arquivo em disco e um titulo. O `main.py` deixa
de saber de onde veio, que e a condicao para a Fase 1 acrescentar fontes sem
mexer no meio do pipeline.

**Os adapters chamam o codigo que ja existe; nao o movem.** Ver o comentario em
`youtube.py`: e o que mantem o `git fetch upstream` viavel.

**O import do `main` e tardio, dentro do `fetch`.** Alem de evitar o ciclo
(o `main` importa este pacote), isso deixa o pacote inteiro importavel so com a
biblioteca padrao -- entao os testes de roteamento rodam no CI, que
deliberadamente nao instala torch, mediapipe nem scenedetect.
"""
from __future__ import annotations

from .base import (  # noqa: F401  (reexportados: e esta a superficie publica)
    Fetched,
    SourceAdapter,
    SourceInfo,
    SourceNotReady,
    UnknownSource,
    host_of,
    is_http_url,
)
from .direct import DirectUrlAdapter
from .gdrive import GoogleDriveAdapter
from .local import LocalFileAdapter
from .twitch import TwitchLiveAdapter, TwitchVodAdapter
from .youtube import YouTubeAdapter

# A ordem E o desempate, do host mais especifico para o mais generico:
# `DirectUrlAdapter.matches` aceita qualquer http(s), entao qualquer plataforma
# nova entra ANTES dele ou nunca sera alcancada. O arquivo local pode ficar em
# qualquer posicao (so ele responde ao que nao e URL), e esta por ultimo para
# que a lista se leia como "as fontes de rede, e o resto".
REGISTRY: tuple[type[SourceAdapter], ...] = (
    YouTubeAdapter,
    TwitchVodAdapter,
    TwitchLiveAdapter,
    GoogleDriveAdapter,
    DirectUrlAdapter,
    LocalFileAdapter,
)


def resolve(raw: str) -> SourceAdapter:
    """O adapter que sabe buscar `raw`.

    Levanta `UnknownSource` em entrada vazia. Hoje nenhuma outra entrada chega
    ate aqui sem dono -- `LocalFileAdapter` aceita tudo que nao e URL --, mas a
    excecao existe para quando o registro tiver fontes que nao se reconhecem
    por host (um id de arquivo do Drive, por exemplo).
    """
    if not raw or not str(raw).strip():
        raise UnknownSource("fonte vazia: informe uma URL ou o caminho de um arquivo")
    for adapter in REGISTRY:
        if adapter.matches(raw):
            return adapter()
    raise UnknownSource(f"nenhuma fonte reconhece esta entrada: {raw[:120]}")


def label_for(raw: str) -> str:
    """Nome legivel da fonte, para log e mensagem de erro. Nunca levanta.

    O `main.download_youtube_video` anunciava "Downloading video from YouTube"
    para qualquer origem, e ao falhar imprimia um banner dizendo "YOUTUBE
    DOWNLOAD FAILED" -- mesmo quando a URL era de um CDN, o que acontece desde
    o upstream. Nomear a plataforma errada manda quem le procurar no lugar
    errado.
    """
    try:
        return resolve(raw).label
    except Exception:
        return "fonte desconhecida"


def cookie_jar_for(raw: str) -> tuple[str, str]:
    """(variavel de ambiente, arquivo) com os cookies desta fonte.

    Errar aqui e **silencioso**: o download falha como se a conta nao estivesse
    logada, e um VOD sub-only vira "video unavailable" sem dizer por que.
    """
    try:
        adapter = resolve(raw)
    except Exception:
        return (SourceAdapter.cookie_env, SourceAdapter.cookie_file)
    return (adapter.cookie_env, adapter.cookie_file)


def adapter_ids() -> tuple[str, ...]:
    """Ids registrados, na ordem de resolucao. Para log e para teste."""
    return tuple(a.id for a in REGISTRY)
