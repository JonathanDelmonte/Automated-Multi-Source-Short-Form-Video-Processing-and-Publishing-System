"""Atualizar o motor pelo botao do site (25-set-2026).

O aviso "o motor deste computador esta atras do site" mandava rodar o
`atalhos\\atualizar.bat` na pasta do projeto -- e o ajudante, que se atualiza
sozinho, nem mostrava o aviso: podia ficar ate 6 horas para tras. O autor pediu,
para ele e para o amigo, um botao que atualize "pelo proprio navegador". Este
modulo e a metade do motor; o botao e o `AvisoDoMotor.jsx`.

**No Docker** o repositorio esta montado em `/app` e o git esta na imagem (o
`versao_do_motor.py` ja o usa). O botao faz o que o `atualizar.bat` faz para
mudanca de CODIGO: baixa a `main`, avanca o checkout -- so fast-forward, nunca
mistura -- e reinicia. O reinicio e o do proprio container: o motor pede ao
processo 1 (o uvicorn do docker-compose.yml) que pare, e o `restart:
unless-stopped` o sobe de novo com o codigo novo. O `--reload` do uvicorn nao
serve: o bind mount do Docker Desktop nao repassa os eventos de arquivo
(docs/COMO-EXECUTAR.md). Para o painel, fica uma marca que o dev server do Vite
vigia (`dashboard/vite.config.js`): e o `restart frontend` do atalho.

**O que mora DENTRO da imagem o botao recusa**, e diz qual arquivo e: as
dependencias (requirements.txt e os package.json, instalados no build), os
Dockerfile, o renderizador (render-service/ e remotion/ vao inteiros para a
imagem dele), o mapa de fontes (vai para o sistema da imagem) e o compose (a
configuracao dos containers). Avancar o codigo sem
elas subiria um motor importando o que a imagem nao tem. Ali continua valendo
o atalho, que sabe mandar reconstruir.

**A distancia e medida do commit com que o motor SUBIU**, e nao do disco: um
`git pull` pelo GitHub Desktop sem reinicio deixa o disco em dia e o motor para
tras -- e, se aquele pull trouxe uma dependencia, reiniciar sem reconstruir
seria o mesmo erro por outro caminho.

**No ajudante** quem troca de versao e a bandeja (ajudante/atualizacao.py), com
verificacao e volta atras: o motor so deixa o pedido num arquivo, que ela le em
ate 10 s. Duas maneiras de trocar de versao seriam duas maneiras de errar.

Stdlib pura: a regra roda no CI sem subir a API.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

RAMO = "main"

#: O que o dev server do painel vigia (dashboard/vite.config.js).
MARCA_DO_PAINEL = Path("dashboard") / ".reiniciar-painel"

# A imagem do backend instala so o requirements.txt da RAIZ (Dockerfile), e
# copia o mapa de fontes para o fontconfig do sistema. As fontes em si nao: a
# legenda as le da pasta montada (`fontsdir` em subtitles.py) e o gancho, pelo
# caminho. As imagens do painel e do renderizador instalam o package.json e o
# lock de cada um.
_NA_RAIZ = frozenset({"requirements.txt", "fonts/openshorts-fontmap.conf"})
_EM_QUALQUER_PASTA = frozenset({"package.json", "package-lock.json", ".dockerignore"})
# Copiadas inteiras para a imagem do renderizador, que nao monta o repositorio.
_PASTAS_NA_IMAGEM = ("render-service/", "remotion/")


def fica_na_imagem(caminho: str) -> bool:
    """Se trocar este arquivo exige reconstruir alguma imagem."""
    p = PurePosixPath(caminho)
    if str(p) in _NA_RAIZ or p.name in _EM_QUALQUER_PASTA:
        return True
    return p.name.startswith("Dockerfile") or str(p).startswith(_PASTAS_NA_IMAGEM)


def e_do_compose(caminho: str) -> bool:
    """A configuracao dos containers, que so um `docker compose up` aplica."""
    p = PurePosixPath(caminho)
    return (len(p.parts) == 1 and p.name.startswith("docker-compose")
            and p.suffix in (".yml", ".yaml"))


# --- o git do container -------------------------------------------------------------

def _fins_de_linha(raiz: Path) -> str:
    """`true` quando o checkout veio do Windows com CRLF.

    O git para Windows guarda o `core.autocrlf=true` na configuracao do
    SISTEMA dele, que o git do container nao le. Sem repetir a regra aqui, o
    merge gravaria os arquivos que troca com LF no meio de um checkout CRLF --
    e um `.bat` so com LF e conhecido por fazer o cmd.exe errar o `goto`.
    """
    for nome in ("app.py", "main.py", "README.md"):
        try:
            with open(raiz / nome, "rb") as f:
                if b"\r\n" in f.read(1 << 16):
                    return "true"
        except OSError:
            continue
    return "false"


def _git(raiz: Path, *args: str, fins: str = "false", timeout: float = 60,
         executar: Callable = subprocess.run) -> subprocess.CompletedProcess:
    comando = [
        "git",
        # A pasta montada e de outro dono (ver versao_do_motor.py).
        "-c", "safe.directory=*",
        # O NTFS nao guarda o bit de execucao: montado no Linux, todo arquivo
        # parece executavel, e o git contaria isso como mudanca local.
        "-c", "core.filemode=false",
        "-c", f"core.autocrlf={fins}",
        "-c", "core.fsmonitor=false",
        "-c", "core.quotepath=false",
        # Ninguem para digitar senha: credencial pedida e erro, nao espera.
        "-c", "credential.helper=",
        "-C", str(raiz), *args,
    ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return executar(comando, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=timeout, env=env)


def _linha(r: subprocess.CompletedProcess) -> str:
    """A linha do git que explica a falha (`error:`/`fatal:`), ou a ultima."""
    linhas = [l.strip() for l in ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines()
              if l.strip()]
    for l in linhas:
        if l.startswith(("error:", "fatal:")):
            return l
    return linhas[-1] if linhas else f"o git saiu com o codigo {r.returncode}"


def _arquivos_citados(r: subprocess.CompletedProcess) -> list:
    """Os arquivos que o git lista, recuados, numa recusa de merge."""
    return [l.strip() for l in (r.stderr or "").splitlines() if l.startswith("\t")]


def _recusa(causa: str, motivo: str, **extra) -> dict:
    return {"situacao": "recusado", "causa": causa, "motivo": motivo, **extra}


def _recusa_do_merge(r: subprocess.CompletedProcess) -> dict:
    linha, arquivos = _linha(r), _arquivos_citados(r)[:10]
    if "untracked working tree files" in linha:
        return _recusa("arquivos_soltos", "ha arquivos fora do git com o nome de arquivos "
                       "que a versao nova traz", arquivos=arquivos, linha=linha)
    if "would be overwritten" in linha:
        return _recusa("mudancas_locais", "ha mudancas locais em arquivos que a versao nova "
                       "troca", arquivos=arquivos, linha=linha)
    if "index.lock" in linha:
        return _recusa("git_ocupado", "outro programa esta usando o git desta pasta",
                       linha=linha)
    return _recusa("git", "o git recusou avancar o checkout", linha=linha)


def commit_de(raiz: Path, executar: Callable = subprocess.run) -> Optional[str]:
    """O commit do checkout, ou None. O `app.py` o chama uma vez, ao subir."""
    try:
        r = _git(raiz, "rev-parse", "HEAD", fins=_fins_de_linha(raiz), timeout=10,
                 executar=executar)
    except (OSError, subprocess.SubprocessError):
        return None
    sha = (r.stdout or "").strip()
    return sha if r.returncode == 0 and len(sha) >= 40 else None


def atualizar_docker(raiz: Path, subiu_em: Optional[str] = None,
                     executar: Callable = subprocess.run) -> dict:
    """Baixa a `main` e avanca o checkout, ou diz por que nao. Nunca levanta.

    `situacao`:
      - `atualizado`: o motor ja roda o que a `main` tem;
      - `atualizou`: o checkout esta na `main` e o motor subiu antes dela --
        falta reiniciar (`de`/`para` sao as versoes, `painel` diz se a marca
        do dev server foi gravada);
      - `precisa_do_atalho`: a diferenca inclui o que mora na imagem
        (`reconstruir`) ou no compose; o checkout NAO e tocado;
      - `recusado`: com `causa` e `motivo`.
    """
    fins = _fins_de_linha(raiz)

    def git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        return _git(raiz, *args, fins=fins, timeout=timeout, executar=executar)

    try:
        r = git("rev-parse", "--abbrev-ref", "HEAD")
        if r.returncode != 0:
            return _recusa("sem_repositorio", "a pasta do motor nao e um repositorio git",
                           linha=_linha(r))
        ramo = r.stdout.strip()
        if ramo != RAMO:
            return _recusa("ramo", f"o checkout esta na branch {ramo}, e o botao so "
                           f"atualiza a {RAMO}", ramo=ramo)

        r = git("fetch", "--quiet", "origin", RAMO, timeout=180)
        if r.returncode != 0:
            return _recusa("sem_rede", "nao consegui baixar a main do GitHub",
                           linha=_linha(r))
        head = git("rev-parse", "HEAD").stdout.strip()
        alvo = git("rev-parse", "FETCH_HEAD").stdout.strip()
        if not head or not alvo:
            return _recusa("git", "o git nao disse em que commit esta")

        if head != alvo:
            r = git("merge-base", "--is-ancestor", head, alvo)
            if r.returncode == 1:
                return _recusa("divergiu", "o checkout tem commits que a main publicada "
                               "nao tem")
            if r.returncode != 0:
                return _recusa("git", "o git nao comparou os commits", linha=_linha(r))

        # Do commit com que o motor SUBIU; se ele sumiu (historia reescrita),
        # do disco.
        base = subiu_em or head
        r = git("diff", "--name-only", base, alvo)
        if r.returncode != 0 and base != head:
            base = head
            r = git("diff", "--name-only", base, alvo)
        if r.returncode != 0:
            return _recusa("git", "o git nao listou o que mudou", linha=_linha(r))
        mudou = [l.strip() for l in r.stdout.splitlines() if l.strip()]

        na_imagem = [a for a in mudou if fica_na_imagem(a)]
        do_compose = [a for a in mudou if e_do_compose(a)]
        if na_imagem or do_compose:
            return {"situacao": "precisa_do_atalho", "reconstruir": bool(na_imagem),
                    "arquivos": (na_imagem + do_compose)[:12],
                    "total": len(na_imagem) + len(do_compose)}

        if head != alvo:
            r = git("merge", "--ff-only", "--quiet", alvo, timeout=120)
            if r.returncode != 0:
                return _recusa_do_merge(r)

        if base == alvo:
            return {"situacao": "atualizado"}

        painel = any(a.startswith("dashboard/") for a in mudou)
        if painel:
            try:
                (raiz / MARCA_DO_PAINEL).write_text(alvo + "\n", encoding="utf-8")
            except OSError:
                painel = False
        return {"situacao": "atualizou", "de": _contagem(git, base),
                "para": _contagem(git, alvo), "painel": painel}
    except (OSError, subprocess.SubprocessError) as e:
        return _recusa("git", "o git nao respondeu", linha=str(e))


def _contagem(git: Callable, commit: str) -> Optional[str]:
    r = git("rev-list", "--count", commit)
    contagem = (r.stdout or "").strip()
    return contagem if r.returncode == 0 and contagem.isdigit() else None


# --- quem pode reiniciar ---------------------------------------------------------------

def subiu_pelo_compose(cmdline: Path = Path("/proc/1/cmdline")) -> bool:
    """Se o processo 1 do container e o uvicorn do docker-compose.yml deste
    repositorio.

    E o `--reload` que o identifica (o CMD do Dockerfile, de producao, nao o
    tem), e aquele servico e o que tem `restart: unless-stopped` -- sem essa
    politica, pedir ao processo 1 que pare seria DESLIGAR o motor. De dentro do
    container nao ha como perguntar a politica ao Docker; na duvida, o botao
    recusa e o atalho continua valendo.
    """
    try:
        partes = cmdline.read_bytes().split(b"\0")
    except OSError:
        return False
    return any(p.endswith(b"uvicorn") for p in partes) and b"--reload" in partes


def pedir_ao_ajudante(caminho: str) -> None:
    """Deixa o pedido para a bandeja, que o le em ate 10 s. Levanta OSError."""
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{int(time.time())}\n", encoding="utf-8")
