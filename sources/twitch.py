"""Twitch: VOD, clip e -- ainda nao -- a live.

O §9 manda comecar a Fase 1 pela Twitch porque live longa e o pior caso, e
testar o pior caso cedo evita retrabalho. Este bloco entrega as duas formas
que ja da para baixar como arquivo (VOD e clip) e, tao importante quanto,
**reconhece a live para recusa-la com clareza**.

Sem esse reconhecimento a URL de um canal cairia no adapter generico, que
chamaria o yt-dlp -- e o yt-dlp *aceita* gravar live da Twitch: ele ficaria
baixando ate a transmissao acabar. Um job que nao termina e pior que um job que
falha, porque ninguem sabe que ele esta errado. Ate o bloco 1.5, e um erro
imediato e explicado.

Nada aqui passa pela cascata de proxy do YouTube: `download_youtube_video` ja
separa os dois casos por dentro (`plan_download_attempts(..., youtube=False)`),
entao Twitch baixa do IP do proprio servidor, sem cookie de YouTube e sem
nunca tocar o proxy por GB.
"""
from __future__ import annotations

import os
import re

from .base import (Fetched, SourceAdapter, SourceInfo, SourceNotReady,
                   host_of, is_http_url)


def _is_twitch_host(raw: str) -> bool:
    """Host da Twitch, com o ponto no lugar certo.

    `host.endswith("twitch.tv")` daria True para `nottwitch.tv`. Aqui isso nao
    seria um vazamento de cookie (o formato Netscape e escopado por dominio),
    mas mandaria o download pelo plano de rede errado -- e o log nomearia a
    plataforma errada, que e como se procura problema no lugar errado.

    `main.is_youtube_url` tem a forma solta e fica como esta de proposito: o
    `download_youtube_video` a chama outra vez por dentro para montar o plano,
    entao endurecer so o adapter faria o rotulo discordar da rota. Um log que
    mente e pior que um roteamento subotimo de um host que ninguem tem.
    """
    host = host_of(raw)
    return host == "twitch.tv" or host.endswith(".twitch.tv")


def _path_parts(raw: str) -> list[str]:
    from urllib.parse import urlparse

    try:
        return [p for p in (urlparse(raw).path or "").split("/") if p]
    except Exception:
        return []


# `/videos/<id>` (atual) e `/<canal>/v/<id>` (legado, ainda circula em link
# antigo). O id e numerico nos dois.
_VOD_ID = re.compile(r"^\d+$")


def classify(raw: str) -> str | None:
    """`vod` | `clip` | `live` | `channel-list`, ou None se nao for Twitch.

    Funcao pura, sem rede: e o que separa "da para baixar agora" de "isso e uma
    transmissao acontecendo". Testada diretamente porque o custo de errar aqui
    e um job que nunca termina.
    """
    if not is_http_url(raw) or not _is_twitch_host(raw):
        return None
    host = host_of(raw)
    parts = _path_parts(raw)

    if host == "clips.twitch.tv":
        return "clip" if parts else None
    if not parts:
        return None                                   # twitch.tv/ pelado
    if parts[0] == "videos" and len(parts) >= 2 and _VOD_ID.match(parts[1]):
        return "vod"
    if len(parts) >= 3 and parts[1] == "v" and _VOD_ID.match(parts[2]):
        return "vod"                                  # /<canal>/v/<id>, legado
    if len(parts) >= 3 and parts[1] == "clip":
        return "clip"                                 # /<canal>/clip/<slug>
    if len(parts) == 2 and parts[1] == "videos":
        return "channel-list"                         # /<canal>/videos
    if len(parts) == 1:
        return "live"                                 # /<canal>
    return None


class TwitchVodAdapter(SourceAdapter):
    id = "twitch-vod"
    label = "Twitch (VOD/clip)"
    # O do YouTube fica em /app/cookies.txt porque o `quality_probe.py`
    # procura esse caminho pelo nome; este e novo, entao pode ter o seu.
    cookie_env = "TWITCH_COOKIES"
    cookie_file = "/app/cookies-twitch.txt"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return classify(raw) in ("vod", "clip")

    def probe(self, raw: str) -> SourceInfo:
        # O aviso de expiracao nao e enfeite: o §4 registra que VOD da Twitch
        # some em 7 a 60 dias conforme o plano do canal, e o plano lista isso
        # como risco a monitorar ("nao tratar VOD como armazenamento"). Quem le
        # o log tem que saber que a fonte e peniveis antes de decidir reprocessar
        # daqui a um mes.
        notas = ["VOD da Twitch expira em 7 a 60 dias: ingira cedo, nao trate a fonte como arquivo"]
        if classify(raw) == "vod":
            notas.append("VOD de sub-only precisa de cookie de conta inscrita (TWITCH_COOKIES)")
        return SourceInfo(kind=self.id, label=self.label, notes=tuple(notas))

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        import main

        path, title = main.download_youtube_video(raw, output_dir)
        return Fetched(path=path, title=title, kind=self.id)


class TwitchLiveAdapter(SourceAdapter):
    id = "twitch-live"
    label = "Twitch (ao vivo)"
    # O do YouTube fica em /app/cookies.txt porque o `quality_probe.py`
    # procura esse caminho pelo nome; este e novo, entao pode ter o seu.
    cookie_env = "TWITCH_COOKIES"
    cookie_file = "/app/cookies-twitch.txt"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return classify(raw) in ("live", "channel-list")

    def probe(self, raw: str) -> SourceInfo:
        from . import twitch_live

        if classify(raw) == "channel-list":
            return SourceInfo(kind=self.id, label="Twitch (lista do canal)", is_live=False)
        minutos = twitch_live.block_seconds() // 60
        return SourceInfo(
            kind=self.id, label=self.label, is_live=True,
            notes=(f"transmissao ao vivo: o job grava um bloco de {minutos} min e corta "
                   f"esse bloco (TWITCH_LIVE_BLOCK_MINUTES muda a duracao)",),
        )

    def assert_fetchable(self, raw: str) -> None:
        # A live passa desde o bloco 1.5. A lista de videos do canal continua
        # recusada: nao e um video, e o yt-dlp a trataria como playlist e
        # baixaria o canal inteiro.
        if classify(raw) == "channel-list":
            raise SourceNotReady(
                f"{raw} e a lista de videos do canal, nao um video. "
                "Abra o VOD que voce quer e use a URL dele (termina em /videos/<numero>).")

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        from . import twitch_live

        self.assert_fetchable(raw)
        segundos = twitch_live.block_seconds()
        _, cookiefile = self.cookie_env, self.cookie_file
        vivo = twitch_live.resolve_live(raw, cookiefile=cookiefile)

        # Import tardio, mesma razao dos outros adapters (evita o ciclo com o
        # `main`) -- aqui so para higienizar o nome do arquivo.
        import main

        base = main.sanitize_filename(f"{vivo['title']}_bloco")
        destino = os.path.join(output_dir or ".", f"{base}.mp4")
        twitch_live.record_block(vivo["stream_url"], destino, segundos)
        return Fetched(path=destino, title=base, kind=self.id,
                       meta={"live": True, "block_seconds": segundos})
