"""Qual versao do motor esta rodando (Fase 6.2).

O site do Cloudflare e publicado a cada envio para a `main`; o motor, nao. No
ajudante ele se atualiza sozinho; no Docker, so com o `atalhos\\atualizar.bat`.
Para o site poder dizer "o motor deste computador esta atras do site", o motor
diz a versao dele no `/api/config`.

A versao e a mesma conta nos dois lados: a CONTAGEM de commits da `main`, que
so cresce. O ajudante a recebe pronta, no arquivo `VERSAO` que o
`ajudante/empacotar.py` poe no pacote. O Docker a calcula pelo git -- que esta
na imagem -- sobre o repositorio montado em `/app`, uma vez, ao subir: e o
codigo que subiu que importa, e nao o que um `git pull` sem reinicio deixou no
disco.

Sem como saber (sem `.git`, clone raso, git quebrado), a versao e `None`, e o
site nao avisa nada: dizer "desatualizado" sem saber seria pior que o silencio.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

RAIZ = Path(__file__).resolve().parent


def descobrir(raiz: Path = RAIZ, executar: Callable = subprocess.run,
              no_docker: Optional[bool] = None) -> dict:
    try:
        versao = (raiz / "VERSAO").read_text(encoding="utf-8").strip()
    except OSError:
        versao = ""
    if versao:
        return {"versao": versao, "origem": "ajudante"}

    if no_docker is None:
        no_docker = os.path.exists("/.dockerenv")
    origem = "docker" if no_docker else "codigo"
    git = raiz / ".git"
    # Clone raso conta so os commits que baixou: um checkout do CI diria "1".
    if not git.exists() or (git / "shallow").exists():
        return {"versao": None, "origem": origem}
    try:
        # `safe.directory`: no Docker a pasta montada e de outro dono, e sem
        # isto o git se recusa a ler o repositorio.
        r = executar(["git", "-c", "safe.directory=*", "-C", str(raiz),
                      "rev-list", "--count", "HEAD"],
                     capture_output=True, text=True, timeout=10)
        contagem = (r.stdout or "").strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        contagem = ""
    return {"versao": contagem if contagem.isdigit() else None, "origem": origem}
