"""Gravar a live da Twitch em blocos (Fase 1, bloco 1.5).

**Um job = um bloco, e essa e a decisao inteira.** O §4 descreve a live como
"worker de longa duracao", e o fatiamento em blocos que ele manda fazer e
exatamente o que evita precisar de um. Nao da para baixar o que ainda nao
aconteceu: gravar uma live de 4h por inteiro seria um job de 4 horas, e o
sistema em volta assume job limitado --

- a fila tem semaforo: um job de 4h segura uma vaga a tarde toda;
- o manifesto de resume espera batimento a cada 10s e re-enfileira o que ficar
  60s mudo, o que nao combina com um processo que so grava;
- todo push redeploya o container, e o drain espera os jobs terminarem ate
  `DRAIN_TIMEOUT_SECONDS` (840s). Uma gravacao de 4h nao cabe la;
- e a barra do painel diria "recebendo o video" pela tarde inteira.

Entao cada job grava **um bloco** (`TWITCH_LIVE_BLOCK_MINUTES`, 15 por padrao)
e o processa como qualquer upload. Uma live de 4h vira N jobs de 15 minutos em
vez de um de 4 horas, e os cortes vao aparecendo enquanto ela acontece. Quem
quiser cobrir a live inteira reenvia -- e o agendador da Fase 4 e quem vai
fazer isso sozinho.

**Por que ffmpeg e nao o downloader do yt-dlp.** O yt-dlp grava live ate a
transmissao acabar; nao ha "grave 15 minutos". Ele entra aqui so para o que
sabe fazer melhor: dizer se o canal esta no ar e resolver a URL do stream.
Quem grava e o ffmpeg com `-t`, que fecha o arquivo direito no tempo pedido.
"""
from __future__ import annotations

import os
import subprocess

#: Margem sobre a duracao do bloco antes de considerar o ffmpeg travado. Uma
#: live com queda de conexao pode demorar mais que `-t` para fechar o arquivo.
MARGEM_SEGUNDOS = 120

PADRAO_MINUTOS = 15


class LiveOffline(RuntimeError):
    """O canal existe e nao esta transmitindo agora."""


def block_seconds() -> int:
    """Duracao de um bloco, em segundos.

    Curto demais nao rende corte (o proprio `MIN_SOURCE_SECONDS` recusa abaixo
    de 45s); longo demais volta ao problema que o fatiamento resolve. O teto de
    2h nao e arbitrario: acima disso o job passa a nao caber no drain de um
    deploy, que e um dos motivos de o fatiamento existir.
    """
    bruto = (os.environ.get("TWITCH_LIVE_BLOCK_MINUTES") or "").strip()
    try:
        minutos = int(bruto) if bruto else PADRAO_MINUTOS
    except ValueError:
        minutos = PADRAO_MINUTOS
    minutos = max(1, min(minutos, 120))
    return minutos * 60


def pick_stream_url(info: dict) -> str | None:
    """A URL do stream dentro do que o yt-dlp devolveu. Pura.

    O yt-dlp poe `url` no topo quando ja escolheu um formato, e so a lista
    `formats` quando nao. As duas formas aparecem conforme a versao e o
    extrator, entao as duas sao tratadas.
    """
    if not isinstance(info, dict):
        return None
    direto = info.get("url")
    if direto:
        return direto
    formatos = [f for f in (info.get("formats") or []) if isinstance(f, dict) and f.get("url")]
    if not formatos:
        return None
    # O ultimo da lista e o de melhor qualidade na convencao do yt-dlp.
    return formatos[-1]["url"]


def record_cmd(stream_url: str, dest: str, seconds: int) -> list[str]:
    """ffmpeg gravando um bloco. Pura, e testada literalmente.

    `-t` **depois** do `-i` limita a saida: e o que fecha o arquivo no tempo
    pedido em vez de gravar ate a live acabar. `-c copy` nao recodifica --
    numa live de 1080p60 recodificar custaria mais CPU que o resto do pipeline
    inteiro, e o bloco vai ser recortado depois de qualquer jeito.
    """
    return ["ffmpeg", "-y", "-loglevel", "error",
            "-i", stream_url,
            "-t", str(int(seconds)),
            "-c", "copy",
            "-movflags", "+faststart",
            dest]


def resolve_live(url: str, cookiefile: str | None = None, ydl=None) -> dict:
    """`{"title", "stream_url"}` de um canal no ar. `ydl` e injetavel para teste.

    Levanta `LiveOffline` quando o canal existe e nao esta transmitindo -- que e
    a resposta util, e nao um download que falha tres minutos depois.
    """
    if ydl is None:
        import yt_dlp

        opcoes = {"quiet": True, "no_warnings": True, "skip_download": True}
        if cookiefile and os.path.exists(cookiefile):
            opcoes["cookiefile"] = cookiefile

        def ydl(alvo):
            with yt_dlp.YoutubeDL(opcoes) as cliente:
                return cliente.extract_info(alvo, download=False)

    info = ydl(url) or {}
    if not info.get("is_live"):
        raise LiveOffline(
            f"{url} nao esta transmitindo agora. Gravar so funciona com o canal no ar; "
            "para material passado, use a URL do VOD (termina em /videos/<numero>).")
    stream_url = pick_stream_url(info)
    if not stream_url:
        raise LiveOffline(
            f"{url} esta no ar mas nao consegui resolver a URL do stream. "
            "Se for um canal de sub-only, configure TWITCH_COOKIES.")
    return {"title": info.get("title") or "live", "stream_url": stream_url}


def record_block(stream_url: str, dest: str, seconds: int, log=print) -> str:
    """Grava o bloco e devolve o caminho. Levanta em qualquer falha.

    Aqui **nao** se falha aberto, ao contrario do estagio 02: sem o arquivo nao
    ha o que processar, e um job que segue sem fonte so falharia mais adiante,
    com uma mensagem pior.
    """
    log(f"   🔴 Gravando {seconds // 60} min da transmissao ao vivo. "
        f"O job so comeca a cortar depois disso.")
    try:
        proc = subprocess.run(record_cmd(stream_url, dest, seconds),
                              capture_output=True,
                              timeout=seconds + MARGEM_SEGUNDOS)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"a gravacao passou de {seconds + MARGEM_SEGUNDOS}s sem fechar o arquivo "
            "-- a transmissao pode ter caido no meio.") from e
    if proc.returncode != 0:
        erro = proc.stderr.decode(errors="replace").strip()[:300]
        raise RuntimeError(f"ffmpeg falhou ao gravar a live: {erro}")
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError("a gravacao saiu vazia -- a transmissao pode ter acabado "
                           "no instante em que o job comecou.")
    return dest
