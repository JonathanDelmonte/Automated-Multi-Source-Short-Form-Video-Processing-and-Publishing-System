"""YouTube: o caminho que o fork ja tinha, agora com nome e endereco."""
from __future__ import annotations

from .base import Fetched, SourceAdapter, host_of, is_http_url, modulo_main

# Os mesmos hosts de `main.is_youtube_url`, repetidos de proposito em vez de
# importados: este modulo precisa abrir sem o `main` (e sem torch). A lista e
# curta e estavel, e `tests/test_sources.py` compara as duas sempre que o
# `main` esta disponivel -- entao elas nao divergem em silencio.
HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "googlevideo.com")


class YouTubeAdapter(SourceAdapter):
    id = "youtube"
    label = "YouTube"
    # O nome com que as extensoes de exportar cookies salvam o arquivo. Aceitar
    # os dois evita o passo "agora renomeie", que e um passo a mais para errar.
    cookie_file_alt = ("www.youtube.com_cookies.txt",)

    @classmethod
    def matches(cls, raw: str) -> bool:
        return is_http_url(raw) and host_of(raw).endswith(HOSTS)

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        # Import tardio: o `main` importa este pacote, e importa-lo de volta no
        # topo fecharia o ciclo.
        #
        # **Chama, nao move.** `download_youtube_video` sao ~240 linhas do
        # upstream: cascata de proxy, lista de clients do yt-dlp, contabilidade
        # de bytes pagos, PROXY_ROUTE. Traze-la para ca daria conflito em todo
        # `git fetch upstream` -- exatamente o que as interfaces do §4 existem
        # para evitar (ver "Fluxo de git" no CLAUDE.md). O adapter e fino.
        path, title = modulo_main().download_youtube_video(raw, output_dir)
        return Fetched(path=path, title=title, kind=self.id)
