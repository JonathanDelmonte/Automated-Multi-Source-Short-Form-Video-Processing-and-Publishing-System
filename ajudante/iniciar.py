"""O ponto de entrada do ajudante: o atalho, o menu Iniciar e o inicio com o
Windows chamam ESTE arquivo (Fase 6.2).

Ele mora em `%LOCALAPPDATA%\\Cortes\\iniciar.py`, fora das versoes, e a
atualizacao sozinha nunca o troca -- por isso e pequeno e so faz uma coisa:
achar a versao em uso (`atual.txt` -> `versoes/<versao>/`) e rodar o
`ajudante.py` dela. Se o `atual.txt` apontar para uma pasta que nao existe ou
nao terminou de ser extraida, cai na versao completa mais nova, em vez de o
icone nao abrir nada.

Stdlib pura, e sem nada que possa quebrar numa versao futura do motor.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import Optional

MARCA_COMPLETA = ".completo"  # a mesma de atualizacao.py


def _chave(versao: str) -> tuple:
    return tuple(int(p) if p.isdigit() else -1 for p in versao.strip().split("."))


def _utilizavel(pasta: Path) -> bool:
    return (pasta / MARCA_COMPLETA).is_file() and (pasta / "ajudante" / "ajudante.py").is_file()


def versao_em_uso(base: Path) -> Optional[Path]:
    versoes = base / "versoes"
    try:
        nome = (base / "atual.txt").read_text(encoding="utf-8").strip()
    except OSError:
        nome = ""
    if nome and _utilizavel(versoes / nome):
        return versoes / nome
    try:
        candidatas = [p for p in versoes.iterdir() if p.is_dir() and _utilizavel(p)]
    except OSError:
        candidatas = []
    if candidatas:
        return max(candidatas, key=lambda p: _chave(p.name))
    # Rodando de dentro do repositorio (desenvolvimento): o ajudante.py do lado.
    if (base / "ajudante.py").is_file():
        return base.parent
    return None


def _avisar(texto: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, texto, "Cortes", 0x10)
    else:
        print(texto, file=sys.stderr)


def main() -> int:
    base = Path(__file__).resolve().parent
    pasta = versao_em_uso(base)
    if pasta is None:
        _avisar("O motor do Cortes nao foi encontrado nesta pasta.\n\n"
                "Instale de novo pelo site: o instalador guarda os seus projetos.")
        return 1
    script = pasta / "ajudante" / "ajudante.py"
    sys.path.insert(0, str(script.parent))
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
