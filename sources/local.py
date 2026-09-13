"""Arquivo que ja esta em disco: o upload do painel, ou `-i` na linha de comando.

`fetch` nao copia nem move nada -- o arquivo ja esta onde vai ser lido, e copiar
um MOV de 10GB para "ingerir" seria pagar o dobro de disco por nada. O titulo e
o nome do arquivo sem extensao, que e literalmente o que o bloco `__main__`
calculava antes desta camada existir.

O upload em streaming com alvo de 10GB (§4) e trabalho do `app.py`, nao daqui:
quando ele chegar, este adapter continua recebendo um caminho pronto.
"""
from __future__ import annotations

import os

from .base import Fetched, SourceAdapter, is_http_url


class LocalFileAdapter(SourceAdapter):
    id = "upload"
    label = "arquivo local"

    @classmethod
    def matches(cls, raw: str) -> bool:
        return bool(raw) and not is_http_url(raw)

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        return Fetched(
            path=raw,
            title=os.path.splitext(os.path.basename(raw))[0],
            kind=self.id,
        )
