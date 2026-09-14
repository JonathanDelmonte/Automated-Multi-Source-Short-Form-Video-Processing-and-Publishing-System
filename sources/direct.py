"""URL que nao e de uma plataforma conhecida.

Um mp4 num CDN, um link de tmpfiles/catbox que um agente subiu, um arquivo no
R2. Vai pela mesma funcao do YouTube porque **ela ja separa os dois casos por
dentro**: `plan_download_attempts(..., youtube=False)` devolve um plano sem
cascata de proxy e sem cookies, baixando do IP do proprio servidor -- que e 5 a
10x mais rapido quando nao ha banimento de IP a desviar.

Este adapter existe, entao, para dar nome ao caso, nao para mudar o caminho. O
ganho e o log dizer "URL direta" em vez de "Downloading video from YouTube...".
"""
from __future__ import annotations

from .base import Fetched, SourceAdapter, is_http_url, modulo_main


class DirectUrlAdapter(SourceAdapter):
    id = "direct"
    label = "URL direta"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return is_http_url(raw)

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        path, title = modulo_main().download_youtube_video(raw, output_dir)
        return Fetched(path=path, title=title, kind=self.id)
