"""A atualizacao sozinha do ajudante (Fase 6.2).

O CI do Windows publica no GitHub Releases, a cada mudanca no motor que passa
pela instalacao de verdade, tres arquivos: o instalador, o `motor.zip` e o
`versao.json`. O ajudante confere de 6 em 6 horas e, quando ha versao nova,
prepara-a sem parar nada; so troca quando o motor esta livre.

**Cada versao mora na sua pasta** (`versoes/<versao>/`), e a que vale e a que
o `atual.txt` nomeia. Trocar de versao e reescrever esse arquivo -- um
`os.replace`, atomico no NTFS --, e nao renomear a pasta do motor: no Windows
um rename de pasta falha com qualquer arquivo aberto la dentro (o antivirus
examinando o que acabou de ser extraido, por exemplo), e uma troca que cai no
meio de dois renames deixaria o atalho apontando para o nada.

A troca e feita por OUTRO processo (`--aplicar`), depois que o ajudante sai:

1. se as dependencias mudaram, o `instalar.ps1 -SoDependencias` da versao
   nova. O ajudante tem o Pillow e o pystray carregados, e o Windows nao deixa
   o uv trocar uma DLL em uso -- por isso ele sai antes;
2. a verificacao: o motor NOVO sobe numa porta de teste, com pastas
   temporarias, e responde. Sem isso uma versao quebrada so apareceria quando
   a pessoa colasse um link;
3. passou: o `atual.txt` passa a nomea-la. Nao passou: volta tudo (inclusive
   as dependencias, que sao pinos exatos -- reinstalar a lista da versao
   anterior as devolve), e a versao fica marcada para nao ser tentada de novo;
4. o ajudante e aberto de novo, e avisa o que aconteceu.

Stdlib pura: roda com o Python do ajudante sem carregar nada do venv que a
troca de dependencias possa estar substituindo.

Uso (o ajudante chama sozinho; a mao, so para testar):
    python atualizacao.py --aplicar <pasta da versao nova> [--reabrir]
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import ajudante as aj  # noqa: E402 -- stdlib no topo; pystray so dentro da bandeja

REPO = "JonathanDelmonte/Automated-Multi-Source-Short-Form-Video-Processing-and-Publishing-System"
RELEASES = f"https://github.com/{REPO}/releases"

INTERVALO_S = 6 * 3600
PRIMEIRA_CONFERENCIA_S = 120
# Ninguem mexendo no painel ha 5 minutos. Uma legenda sendo queimada e um
# pedido sincrono, que nao aparece como job: e o ocioso que a protege.
OCIOSO_MINIMO_S = 300
PORTA_DA_VERIFICACAO = 8128
PRAZO_DA_VERIFICACAO_S = 420
PRAZO_DAS_DEPENDENCIAS_S = 3600
TAMANHO_MAXIMO = 200 * 1024 * 1024
MARCA_COMPLETA = ".completo"
VERSOES_GUARDADAS = 2  # a atual e a anterior, para voltar a mao se preciso


# --- versoes -------------------------------------------------------------------

def chave(versao: str) -> tuple:
    """"463" < "463.1" < "464". Parte que nao e numero vale -1: a versao de
    desenvolvimento ("0.0.0-local") perde para qualquer publicada."""
    return tuple(int(p) if p.isdigit() else -1 for p in versao.strip().split("."))


def mais_nova(remota: str, local: str) -> bool:
    return bool(remota) and chave(remota) > chave(local or "0")


def versao_de(pasta: Path) -> str:
    try:
        return (pasta / "VERSAO").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def completa(pasta: Path) -> bool:
    return (pasta / MARCA_COMPLETA).is_file() and (pasta / "ajudante" / "ajudante.py").is_file()


def gravar_atual(c: "aj.Caminhos", nome: str) -> None:
    """Atomico: um `atual.txt` pela metade seria um atalho que nao abre nada."""
    tmp = c.base / "atual.txt.tmp"
    tmp.write_text(nome + "\n", encoding="utf-8")
    os.replace(tmp, c.base / "atual.txt")


def podar(c: "aj.Caminhos", manter: set) -> None:
    """Apaga as versoes fora de `manter`. Falha ao apagar nao e erro: sobra
    uma pasta, que a proxima poda leva."""
    if not c.versoes.is_dir():
        return
    for pasta in c.versoes.iterdir():
        if pasta.is_dir() and pasta.name not in manter:
            shutil.rmtree(pasta, ignore_errors=True)


# --- as dependencias ---------------------------------------------------------------

def assinatura_das_dependencias(motor: Path) -> str:
    """Muda quando uma lista de dependencias muda: e o que decide se a troca
    precisa rodar o `instalar.ps1 -SoDependencias`."""
    h = hashlib.sha256()
    for nome in ("requirements-windows.txt", "requirements-windows-gpu.txt"):
        caminho = motor / "ajudante" / nome
        h.update(nome.encode())
        h.update(caminho.read_bytes() if caminho.exists() else b"")
    return h.hexdigest()


# --- estado (dados/atualizacao.json) ----------------------------------------------

def _arquivo_de_estado(c) -> Path:
    return c.dados / "atualizacao.json"


def ler_estado(c) -> dict:
    try:
        estado = json.loads(_arquivo_de_estado(c).read_text(encoding="utf-8"))
        return estado if isinstance(estado, dict) else {}
    except (OSError, ValueError):
        return {}


def gravar_estado(c, estado: dict) -> None:
    c.dados.mkdir(parents=True, exist_ok=True)
    tmp = _arquivo_de_estado(c).with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, _arquivo_de_estado(c))


def registrar(c, versao: str, resultado: str) -> None:
    estado = ler_estado(c)
    if resultado != "aplicada":
        falhas = [v for v in estado.get("falhou", []) if v != versao]
        estado["falhou"] = (falhas + [versao])[-20:]
    estado["ultima"] = {"versao": versao, "resultado": resultado,
                        "quando": time.strftime("%Y-%m-%d %H:%M:%S")}
    gravar_estado(c, estado)


def registro(c) -> Callable[[str], None]:
    """Uma linha com hora em `dados/logs/atualizacao.log` (e no console, se
    houver: o `--aplicar` roda sem nenhum)."""
    def log(msg: str) -> None:
        linha = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        try:
            c.logs.mkdir(parents=True, exist_ok=True)
            caminho = c.logs / "atualizacao.log"
            aj.girar_log(caminho)
            with open(caminho, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass
        if sys.stdout is not None:
            print(linha, flush=True)
    return log


# --- rede ----------------------------------------------------------------------------

def url_das_versoes(env=os.environ) -> str:
    """`CORTES_ATUALIZACAO_URL` troca o GitHub por outro servidor com o mesmo
    formato -- e o que o CI usa para testar a troca sem publicar nada."""
    return (env.get("CORTES_ATUALIZACAO_URL") or RELEASES).rstrip("/")


def _abrir(url: str, timeout: float):
    pedido = urllib.request.Request(url, headers={"User-Agent": "VirtuClips-ajudante"})
    return urllib.request.urlopen(pedido, timeout=timeout)  # noqa: S310 -- https fixo ou o do teste


def buscar(base_url: str, abrir=_abrir) -> dict:
    """O `versao.json` da versao mais nova publicada."""
    with abrir(f"{base_url}/latest/download/versao.json", 20) as r:
        info = json.loads(r.read(1024 * 1024).decode("utf-8"))
    if not isinstance(info, dict) or not info.get("versao") or not info.get("motor_zip_sha256"):
        raise ValueError(f"versao.json sem os campos esperados: {info!r}"[:300])
    return info


def url_do_zip(base_url: str, info: dict) -> str:
    # Pela TAG, e nao por `latest`: uma versao publicada entre a leitura do
    # versao.json e o download traria o zip de outra versao.
    tag = info.get("tag")
    if tag:
        return f"{base_url}/download/{tag}/motor.zip"
    return f"{base_url}/latest/download/motor.zip"


def baixar(url: str, destino: Path, sha256: str, abrir=_abrir) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    h, total = hashlib.sha256(), 0
    try:
        with abrir(url, 60) as r, open(parcial, "wb") as f:
            while bloco := r.read(1024 * 1024):
                total += len(bloco)
                if total > TAMANHO_MAXIMO:
                    raise ValueError("o motor.zip passou do tamanho maximo")
                h.update(bloco)
                f.write(bloco)
        if h.hexdigest() != sha256.lower():
            raise ValueError("o motor.zip baixado nao confere com o versao.json")
        os.replace(parcial, destino)
    finally:
        if parcial.exists():
            parcial.unlink()


def extrair(arquivo_zip: Path, destino: Path, versao: str) -> None:
    """Extrai e SO ENTAO poe a marca de completa: a pasta sem a marca e lixo de
    uma extracao que caiu, e ninguem a usa."""
    if destino.exists():
        shutil.rmtree(destino)
    raiz = destino.resolve()
    with zipfile.ZipFile(arquivo_zip) as z:
        for membro in z.namelist():
            alvo = (raiz / membro).resolve()
            if raiz != alvo and raiz not in alvo.parents:
                raise ValueError(f"caminho fora da pasta no zip: {membro!r}")
        z.extractall(raiz)
    if versao_de(destino) != versao:
        raise ValueError(f"o zip diz ser a versao {versao_de(destino)!r}, e nao {versao!r}")
    (destino / MARCA_COMPLETA).write_text(versao + "\n", encoding="utf-8")


def preparar_se_houver(c, log: Callable[[str], None], base_url: Optional[str] = None,
                       buscar_fn=buscar, baixar_fn=baixar) -> Optional[Path]:
    """Baixa e extrai a versao nova, SEM tocar no que esta rodando. Devolve a
    pasta dela, ou None se nao ha o que fazer."""
    base_url = base_url or url_das_versoes()
    info = buscar_fn(base_url)
    remota, local = str(info["versao"]), versao_de(c.motor)
    if not mais_nova(remota, local):
        return None
    if remota in ler_estado(c).get("falhou", []):
        log(f"a versao {remota} ja falhou na verificacao aqui; esperando a proxima")
        return None
    destino = c.versoes / remota
    if completa(destino):
        return destino
    log(f"versao nova: {remota} (esta e a {local or 'sem versao'}); baixando")
    arquivo = c.dados / "atualizacao" / f"motor-{remota}.zip"
    baixar_fn(url_do_zip(base_url, info), arquivo, str(info["motor_zip_sha256"]))
    try:
        extrair(arquivo, destino, remota)
    finally:
        arquivo.unlink(missing_ok=True)
    log(f"versao {remota} pronta em {destino}")
    return destino


# --- quando trocar -------------------------------------------------------------------

def saude(porta: int = aj.PORTA) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/health", timeout=5) as r:  # noqa: S310
            return json.load(r)
    except Exception:
        return None


def pode_trocar_agora(estado_do_ajudante: str, saude_fn: Callable[[], Optional[dict]] = saude) -> bool:
    """So com o NOSSO motor de pe ha o que proteger. Com o Docker atendendo,
    o motor parado ou quebrado, a troca nao interrompe ninguem -- e pode ser
    justamente o conserto."""
    if estado_do_ajudante != aj.PRONTO:
        return True
    s = saude_fn()
    if not s or "jobs_ativos" not in s:
        return True  # motor sem resposta: reiniciar nao tira nada de ninguem
    return s.get("jobs_ativos", 0) == 0 and s.get("ocioso_s", 0) >= OCIOSO_MINIMO_S


def vigiar(c, estado_fn: Callable[[], str], parar, lancar_fn, sair_fn, log,
           preparar_fn=preparar_se_houver, pode_fn=pode_trocar_agora,
           primeira_s: float = PRIMEIRA_CONFERENCIA_S, intervalo_s: float = INTERVALO_S,
           espera_s: float = 60) -> None:
    """O laco da bandeja: prepara a versao nova sem parar nada, espera o motor
    ficar livre, e so entao entrega a troca a outro processo e sai.

    A troca e de OUTRO processo porque este tem o Pillow e o pystray
    carregados, e o Windows nao deixaria o uv substitui-los se a versao nova
    mudar as dependencias. Se esse processo nao conseguir nem comecar, o
    ajudante FICA -- sair ali deixaria a pessoa sem ajudante nenhum.
    """
    if parar.wait(primeira_s):
        return
    while not parar.is_set():
        try:
            nova = preparar_fn(c, log)
        except Exception as e:  # sem internet, GitHub fora do ar: tenta depois
            log(f"conferir atualizacao: {e!r}")
            nova = None
        if nova is not None:
            while not parar.is_set() and not pode_fn(estado_fn()):
                parar.wait(espera_s)
            if parar.is_set():
                return
            log(f"trocando para a versao {nova.name}: o ajudante sai e volta")
            try:
                lancar_fn(c, nova)
            except OSError as e:
                log(f"a troca nao conseguiu comecar: {e!r}")
            else:
                sair_fn()
                return
        parar.wait(intervalo_s)


# --- a troca (o processo `--aplicar`) ---------------------------------------------------

def _sem_janela() -> dict:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def verificar_versao(c, pasta: Path, log) -> bool:
    """O motor da versao nova sobe numa porta de teste, com pastas
    temporarias -- nem a fila nem o banco de verdade sao tocados."""
    cmd = [str(c.python), str(pasta / "ajudante" / "ajudante.py"),
           "--verificar", "--porta", str(PORTA_DA_VERIFICACAO), "--temporario"]
    try:
        r = subprocess.run(cmd, cwd=str(c.base), capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=PRAZO_DA_VERIFICACAO_S, **_sem_janela())
    except (OSError, subprocess.SubprocessError) as e:
        log(f"a verificacao nao rodou: {e}")
        return False
    for linha in (r.stdout + r.stderr).strip().splitlines()[-40:]:
        log(f"  | {linha}")
    return r.returncode == 0


def instalar_dependencias(c, pasta: Path, log) -> bool:
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           str(pasta / "ajudante" / "instalar.ps1"), "-Base", str(c.base),
           "-SoDependencias", "-SemPausa"]
    log(f"dependencias mudaram: instalando as da versao {pasta.name}")
    try:
        r = subprocess.run(cmd, cwd=str(c.base), capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=PRAZO_DAS_DEPENDENCIAS_S, **_sem_janela())
    except (OSError, subprocess.SubprocessError) as e:
        log(f"o instalar.ps1 nao rodou: {e}")
        return False
    if r.returncode != 0:
        log("o instalar.ps1 falhou; o registro completo esta em dados/logs/instalacao.log")
    return r.returncode == 0


def atualizar_ytdlp(c, log) -> None:
    """O YouTube muda toda semana e o yt-dlp acompanha. A troca de versao e o
    unico momento em que o motor esta parado com certeza, entao ele vem junto
    -- e falhar aqui nao impede nada."""
    uv = c.bin / ("uv.exe" if aj.NO_WINDOWS else "uv")
    if not uv.exists():
        return
    # Nunca baixar Python: o do ajudante veio no instalador (ver instalar.ps1).
    env = dict(os.environ, UV_CACHE_DIR=str(c.base / "cache-uv"), UV_PYTHON_DOWNLOADS="never")
    try:
        r = subprocess.run([str(uv), "pip", "install", "--python", str(c.python),
                            "--upgrade", "yt-dlp[default]"], env=env, capture_output=True,
                           text=True, errors="replace", timeout=600, **_sem_janela())
        log("yt-dlp atualizado" if r.returncode == 0 else f"yt-dlp: {r.stderr.strip()[-300:]}")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"yt-dlp: {e}")
    finally:
        shutil.rmtree(c.base / "cache-uv", ignore_errors=True)


def falta_a_placa(c) -> bool:
    """Placa NVIDIA sem as DLLs de CUDA: o whisper roda no processador. Foi o
    que o instalador deixou ate a versao 538, quando abria o PowerShell de 32
    bits -- que nao ve o nvidia-smi -- e decidia que nao havia placa."""
    return aj.tem_placa_nvidia() and not aj.libs_da_placa(c)


def aplicar(c, nova: Path, log, verificar_fn=verificar_versao,
            dependencias_fn=instalar_dependencias, ytdlp_fn=atualizar_ytdlp,
            falta_a_placa_fn=falta_a_placa) -> bool:
    """Troca para `nova` se ela passar na verificacao; senao, deixa tudo como
    estava. `c.motor` e a versao que roda este codigo -- a atual."""
    atual, versao = c.motor, versao_de(nova)
    if not completa(nova):
        log(f"{nova} nao esta completa; nada a fazer")
        return False
    mudaram = assinatura_das_dependencias(nova) != assinatura_das_dependencias(atual)
    ok = True
    if mudaram:
        ok = dependencias_fn(c, nova, log)
    elif falta_a_placa_fn(c):
        # A troca e o momento em que o motor esta parado com certeza. O
        # instalar.ps1 poe as bibliotecas quando acha a placa -- e o resultado
        # nao decide a troca: sem elas, o motor continua no processador.
        log("placa NVIDIA sem as bibliotecas de CUDA: instalando junto com esta versao")
        dependencias_fn(c, nova, log)
    else:
        ytdlp_fn(c, log)
    if ok:
        log(f"verificando a versao {versao}")
        ok = verificar_fn(c, nova, log)
    if not ok:
        log(f"a versao {versao} NAO passou; o {aj.NOME} continua na {versao_de(atual)}")
        if mudaram and not dependencias_fn(c, atual, log):
            log(f"as dependencias da versao anterior nao voltaram; reinstale o {aj.NOME}")
        shutil.rmtree(nova, ignore_errors=True)
        registrar(c, versao, "revertida")
        return False
    gravar_atual(c, nova.name)
    podar(c, {nova.name, atual.name} if atual.parent == c.versoes else {nova.name})
    registrar(c, versao, "aplicada")
    log(f"versao {versao} em uso")
    return True


def esperar_o_ajudante_sair(prazo_s: float = 60, rodando=None) -> bool:
    rodando = rodando or aj.ajudante_rodando
    fim = time.monotonic() + prazo_s
    while rodando() and time.monotonic() < fim:
        time.sleep(0.5)
    return not rodando()


def reabrir_o_ajudante(c, *argumentos: str) -> None:
    pythonw = c.python.with_name("pythonw.exe") if aj.NO_WINDOWS else c.python
    flags = 0
    if aj.NO_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(pythonw), str(c.base / "iniciar.py"), "--reinicio", *argumentos],
                     cwd=str(c.base), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def lancar_aplicacao(c, nova: Path) -> None:
    """Chamado pela bandeja, que sai logo depois: a troca continua sozinha."""
    pythonw = c.python.with_name("pythonw.exe") if aj.NO_WINDOWS else c.python
    flags = 0
    if aj.NO_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(pythonw), str(Path(__file__).resolve()), "--aplicar", str(nova),
                      "--reabrir"],
                     cwd=str(c.base), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--aplicar" not in argv:
        print(__doc__)
        return 2
    nova = Path(argv[argv.index("--aplicar") + 1]).resolve()
    c = aj.caminhos_padrao()
    log = registro(c)
    if not esperar_o_ajudante_sair():
        log("o ajudante nao saiu a tempo; a troca fica para a proxima")
        ok = None
    else:
        try:
            ok = aplicar(c, nova, log)
        except Exception as e:  # nunca deixar a pessoa sem o ajudante
            log(f"a troca caiu: {e!r}")
            ok = False
    if "--reabrir" in argv:
        extra = [] if ok is None else (["--atualizado", versao_de(nova)] if ok
                                       else ["--atualizacao-falhou", nova.name])
        reabrir_o_ajudante(c, *extra)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
