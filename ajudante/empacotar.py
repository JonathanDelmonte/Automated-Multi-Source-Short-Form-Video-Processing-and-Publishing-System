"""Monta o que o instalador do ajudante leva (Fase 6.2).

Roda no CI do Windows, antes do ISCC do Inno Setup:

    python ajudante/empacotar.py --versao 463 --bin <pasta com os .exe>

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
- `cortes.ico`: o icone, desenhado pela mesma funcao da bandeja.
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
    "ajudante/pacote/", "ajudante/saida/",
)
FORA_EXTENSOES = (".mp4", ".mov", ".gif", ".iss")

BINARIOS = ("uv.exe", "ffmpeg.exe", "ffprobe.exe", "deno.exe")


def arquivos_do_motor(rastreados: list) -> list:
    return sorted(
        a for a in rastreados
        if not a.startswith(FORA) and not a.endswith(FORA_EXTENSOES))


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


def gravar_icone(destino: Path) -> None:
    import ajudante
    img = ajudante.imagem_do_icone().resize((256, 256))
    img.save(destino, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])


def empacotar(versao: str, pasta_bin: Path, commit: str = "",
              pacote: Path = AQUI / "pacote", saida: Path = AQUI / "saida",
              icone: "Path | None" = AQUI / "cortes.ico") -> dict:
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

    if icone is not None:  # o .iss o procura ao lado dele
        gravar_icone(icone)

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
    ap.add_argument("--commit", default="")
    ap.add_argument("--pacote", default=str(AQUI / "pacote"))
    ap.add_argument("--saida", default=str(AQUI / "saida"))
    ap.add_argument("--sem-icone", action="store_true",
                    help="nao redesenhar o cortes.ico (pacotes so para testar a atualizacao)")
    args = ap.parse_args()
    info = empacotar(args.versao, Path(args.bin), args.commit,
                     Path(args.pacote), Path(args.saida),
                     icone=None if args.sem_icone else AQUI / "cortes.ico")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
