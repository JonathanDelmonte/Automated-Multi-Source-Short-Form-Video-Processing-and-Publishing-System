"""Monta o que o instalador do ajudante leva (Fase 6.2).

Roda no CI do Windows, antes do ISCC do Inno Setup:

    python ajudante/empacotar.py --versao 463 --bin <pasta com os .exe> --python <pasta do Python>

e deixa, dentro de `ajudante/` (ou onde `--pacote` e `--saida` mandarem):

- `pacote/motor/`: o codigo que o motor usa -- tudo o que o git rastreia,
  MENOS o que nao roda no computador de ninguem (painel, docs, testes,
  atalhos do Docker). Lista de exclusao e nao de inclusao, de proposito: um
  arquivo novo que o motor le em tempo de execucao entra sozinho; esquecido
  numa lista de inclusao, so faltaria no computador do amigo.
- `pacote/motor/VERSAO`: o que o ajudante compara com o GitHub para saber se
  ha atualizacao. A versao e a CONTAGEM de commits da `main` (`git rev-list
  --count HEAD`): so cresce, e o Docker consegue calcular a mesma coisa.
- `pacote/bin/`: uv, ffmpeg, ffprobe e deno, copiados de `--bin`.
- `pacote/python/`: o Python do motor, copiado de `--python` (um CPython
  standalone, que funciona de qualquer pasta). Vem no instalador desde
  24-set-2026: baixa-lo na instalacao, pelo `uv python install`, deu o erro
  448 no PC do autor (ver instalar.ps1).
- `pacote/virtu-clips.ico` e `pacote/assistente/`: o icone e as imagens do
  instalador, desenhados por `marca.py`.
- `saida/motor.zip` e `saida/versao.json`: o que a atualizacao sozinha baixa.
  O `conteudo` do versao.json e a impressao digital do motor SEM a versao: o
  CI so publica quando ela muda -- um commit so de documentacao ou do painel
  nao obriga ninguem a reiniciar o motor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))

from atualizacao import MARCA_COMPLETA, assinatura_das_dependencias  # noqa: E402,F401

# O que o git rastreia e o motor nunca le. As imagens do README do upstream
# sozinhas eram 74 MB -- o motor.zip de cada atualizacao ia de 8 para 82.
# `remotion/` e `render-service/` sao o renderizador em Node do Docker, que o
# ajudante nao roda.
FORA = (
    "dashboard/", "docs/", "tests/", "examples/", "ops/", ".github/",
    "atalhos/", ".claude/", "screenshots/", "remotion/", "render-service/",
    "cli/", "skills/", "ajudante/pacote/", "ajudante/saida/",
)
# `.md` tambem: o CLAUDE.md e o README mudam a toda hora e o motor nao le
# nenhum dos dois. Dentro do pacote, cada mudanca deles viraria uma versao
# nova -- e todo ajudante instalado reiniciaria o motor por causa de texto.
FORA_EXTENSOES = (".mp4", ".mov", ".gif", ".iss", ".md")
# Da raiz, o que so o Docker e o GitHub leem. LICENSE e NOTICE ficam: a
# licenca manda acompanhar o codigo que se distribui.
FORA_DA_RAIZ = (".dockerignore", ".env.example", ".gitignore", "Dockerfile",
                "docker-compose", "requirements.txt", "glama.json", "server.json")

BINARIOS = ("uv.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe")


def arquivos_do_motor(rastreados: list) -> list:
    return sorted(
        a for a in rastreados
        if not a.startswith(FORA) and not a.endswith(FORA_EXTENSOES)
        and not ("/" not in a and a.startswith(FORA_DA_RAIZ)))


def rastreados() -> list:
    saida = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True,
                           text=True, check=True).stdout
    return [linha for linha in saida.splitlines() if linha]


def impressao_do_conteudo(motor: Path) -> str:
    """O motor inteiro menos o que muda a cada empacotamento (a versao, a
    marca de completa): duas versoes com o mesmo codigo dao o mesmo numero."""
    h = hashlib.sha256()
    for arquivo in sorted(motor.rglob("*")):
        rel = arquivo.relative_to(motor).as_posix()
        if not arquivo.is_file() or rel in ("VERSAO", MARCA_COMPLETA):
            continue
        h.update(rel.encode() + b"\0" + hashlib.sha256(arquivo.read_bytes()).digest())
    return h.hexdigest()


def copiar_python(origem: Path, destino: Path) -> None:
    """O interpretador inteiro. Recusa o que nao e um: um `--python` errado
    so apareceria no fim da instalacao no computador de alguem."""
    if not (origem / "python.exe").is_file():
        raise SystemExit(f"--python: {origem} nao tem o python.exe")
    # `symlinks=True`: um atalho la dentro vira atalho, e nao a pasta para
    # onde ele aponta copiada duas vezes.
    shutil.copytree(origem, destino, symlinks=True)


def empacotar(versao: str, pasta_bin: Path, commit: str = "",
              pacote: Path = AQUI / "pacote", saida: Path = AQUI / "saida",
              imagens: bool = True, python: "Path | None" = None) -> dict:
    for p in (pacote, saida):
        shutil.rmtree(p, ignore_errors=True)
    motor, binarios = pacote / "motor", pacote / "bin"

    for rel in arquivos_do_motor(rastreados()):
        origem, destino = RAIZ / rel, motor / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
    (motor / "VERSAO").write_text(versao + "\n", encoding="utf-8")

    binarios.mkdir(parents=True)
    for nome in BINARIOS:
        shutil.copy2(pasta_bin / nome, binarios / nome)

    if python is not None:
        copiar_python(python, pacote / "python")

    if imagens:  # o .iss as procura em pacote/
        import marca
        marca.gravar_ico(pacote / "virtu-clips.ico")
        marca.gravar_imagens_do_assistente(pacote / "assistente")

    saida.mkdir(parents=True)
    with zipfile.ZipFile(saida / "motor.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in sorted(motor.rglob("*")):
            if arquivo.is_file():
                z.write(arquivo, arquivo.relative_to(motor).as_posix())
    # Depois do zip, de proposito: no instalador a pasta ja nasce completa; na
    # atualizacao quem poe a marca e a extracao, so quando ela termina.
    (motor / MARCA_COMPLETA).write_text(versao + "\n", encoding="utf-8")
    info = {
        "versao": versao,
        "tag": f"ajudante-{versao}",
        "commit": commit,
        "conteudo": impressao_do_conteudo(motor),
        "dependencias": assinatura_das_dependencias(motor),
        "motor_zip_sha256": hashlib.sha256((saida / "motor.zip").read_bytes()).hexdigest(),
    }
    (saida / "versao.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--versao", required=True)
    ap.add_argument("--bin", required=True, help="pasta com uv, ffmpeg, ffprobe e deno")
    ap.add_argument("--python", help="pasta do Python que vai no instalador")
    ap.add_argument("--commit", default="")
    ap.add_argument("--pacote", default=str(AQUI / "pacote"))
    ap.add_argument("--saida", default=str(AQUI / "saida"))
    ap.add_argument("--sem-icone", action="store_true",
                    help="sem icone nem imagens do instalador (pacotes so para testar a atualizacao)")
    args = ap.parse_args()
    info = empacotar(args.versao, Path(args.bin), args.commit,
                     Path(args.pacote), Path(args.saida), imagens=not args.sem_icone,
                     python=Path(args.python) if args.python else None)
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
