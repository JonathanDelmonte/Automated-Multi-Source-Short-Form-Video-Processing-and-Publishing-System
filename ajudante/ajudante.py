"""O ajudante: o programa que roda o motor no computador de quem usa (Fase 6.2).

O site (https://virtu-clips.zirtuno.workers.dev) e so a tela. Quem baixa o
video, transcreve e corta e o motor -- o mesmo `app.py` do Docker --, e o
ajudante e quem o mantem de pe no Windows, sem Docker:

- sobe o motor em 127.0.0.1:8001, num console ESCONDIDO que os filhos herdam
  (sem ele, cada ffmpeg do job piscaria uma janela preta na tela);
- escolhe placa de video ou processador pelo `nvidia-smi`;
- CEDE ao Docker. A 8000 e do Docker, e o ajudante nunca a ocupa: no login os
  dois sobem juntos, o ajudante quase sempre primeiro, e na mesma porta o
  container do Docker morreria com "port is already allocated", em silencio.
  O site procura a 8000 e depois a 8001; quando o Docker atende, o ajudante
  para o motor dele (terminando antes o job que estiver rodando);
- mora perto do relogio: abrir o site, abrir a pasta dos cortes, ver o log,
  iniciar com o Windows e sair.

A logica (`Ajudante.passo`, `ambiente_do_motor`, `quem_atende`) e stdlib pura
e roda no CI de sempre; so a bandeja (`pystray`) e o registro (`winreg`) sao do
Windows, e ficam em funcoes que o teste nao chama.

Uso: pythonw.exe iniciar.py   (o instalador cria o atalho; o `iniciar.py`
acha a versao em uso e roda este arquivo -- ver atualizacao.py)
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

SITE = "https://virtu-clips.zirtuno.workers.dev"
PORTA = 8001            # a do ajudante
PORTA_DO_DOCKER = 8000  # a do Docker; o site procura esta primeiro
NOME = "Cortes"

NO_WINDOWS = os.name == "nt"
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
AQUI = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Caminhos:
    """Onde cada coisa mora. O codigo e TROCADO a cada atualizacao; os dados
    nunca -- por isso vivem em pastas irmas, e nao um dentro do outro.

    `motor` e a versao que roda ESTE arquivo (`versoes/<versao>/`, que e o
    que o `iniciar.py` escolheu), e nao uma pasta fixa: e assim que a
    verificacao de uma versao nova sobe o motor DELA, e nao o da atual.
    """
    base: Path
    codigo: Optional[Path] = None

    @property
    def motor(self) -> Path:        # o repositorio: app.py, main.py, fonts/...
        return self.codigo or AQUI.parent

    @property
    def versoes(self) -> Path:
        return self.base / "versoes"

    @property
    def dados(self) -> Path:        # projetos, banco, modelos, .env da pessoa
        return self.base / "dados"

    @property
    def bin(self) -> Path:          # ffmpeg, ffprobe, deno
        return self.base / "bin"

    @property
    def venv(self) -> Path:
        return self.base / "venv"

    @property
    def python(self) -> Path:
        return self.venv / ("Scripts/python.exe" if NO_WINDOWS else "bin/python")

    @property
    def logs(self) -> Path:
        return self.dados / "logs"


def caminhos_padrao(env: Mapping[str, str] = os.environ) -> Caminhos:
    """`%LOCALAPPDATA%\\Cortes`: por usuario, sem pedir administrador, e fora
    das pastas que o OneDrive sincroniza -- video de trabalho la dentro seria
    gigabyte subindo para a nuvem sem ninguem pedir."""
    if env.get("CORTES_BASE"):
        return Caminhos(Path(env["CORTES_BASE"]))
    raiz = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Caminhos(Path(raiz) / NOME)


# --- placa de video -----------------------------------------------------------

def tem_placa_nvidia(executar: Callable = subprocess.run) -> bool:
    """O driver da NVIDIA traz o `nvidia-smi`; sem ele, nao ha placa que o
    whisper ou o NVENC possam usar. `-L` so lista, e rapido."""
    try:
        r = executar(["nvidia-smi", "-L"], capture_output=True, text=True,
                     timeout=15, creationflags=_SEM_JANELA)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and "GPU" in (r.stdout or "")


def libs_da_placa(c: Caminhos) -> list:
    """As DLLs de CUDA que o instalador poe so em quem tem placa
    (requirements-windows-gpu.txt). O ctranslate2 as carrega pelo PATH."""
    raiz = c.venv / "Lib" / "site-packages" / "nvidia"
    return [p for p in (raiz / "cublas" / "bin", raiz / "cudnn" / "bin") if p.is_dir()]


def ler_env_da_pessoa(c: Caminhos) -> dict:
    """O `.env` da pasta de dados: chaves de IA e o que a pessoa quiser mudar.
    Fica fora do codigo para a atualizacao nao leva-lo junto."""
    caminho = c.dados / ".env"
    valores = {}
    try:
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    except OSError:
        return valores
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


# O que o `.env` da pessoa NAO muda: as pastas e o que o ajudante precisa
# para funcionar. O caminho natural de quem ja usa o Docker e copiar o `.env`
# do repositorio para `dados\.env` -- e la o `OUTPUT_DIR` pode ser `/app/...`,
# uma pasta do container que no Windows nao existe.
PROTEGIDAS = frozenset({
    "PATH", "OUTPUT_DIR", "UPLOAD_DIR", "DATA_DIR", "HF_HOME",
    "PYTHONUTF8", "PYTHONIOENCODING", "PROXY_DRAIN_SECONDS", "CORTES_ORIGEM_ESTRITA",
})


def ambiente_do_motor(c: Caminhos, placa: bool, base: Mapping[str, str],
                      da_pessoa: Optional[Mapping[str, str]] = None,
                      pastas_em: Optional[Path] = None) -> dict:
    """As variaveis com que o motor sobe. O `.env` da pessoa vence tudo menos
    `PROTEGIDAS` -- e as pastas de uma verificacao (`pastas_em`) nunca caem nos
    projetos de verdade.

    Com placa mas SEM as DLLs de CUDA (instalado antes de a placa existir, ou
    a instalacao delas falhou), o whisper vai para a CPU de proposito: pedir
    `cuda` ali faria cada job tentar a placa, falhar e so entao cair.
    """
    libs = libs_da_placa(c) if placa else []
    whisper_na_placa = placa and bool(libs)
    env = dict(base)
    caminho = [str(c.bin), *(str(p) for p in libs), env.get("PATH", "")]
    env.update({
        "PATH": os.pathsep.join(p for p in caminho if p),
        "OUTPUT_DIR": str(c.dados / "output"),
        "UPLOAD_DIR": str(c.dados / "uploads"),
        "DATA_DIR": str(c.dados / "data"),
        "HF_HOME": str(c.dados / "modelos"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "WHISPER_DEVICE": "cuda" if whisper_na_placa else "cpu",
        "WHISPER_COMPUTE": "float16" if whisper_na_placa else "int8",
        "WHISPER_MODEL": "large-v3-turbo" if whisper_na_placa else "small",
        # O NVENC so precisa do driver, nao das DLLs de CUDA.
        "FFMPEG_ENCODER": "auto" if placa else "x264",
        # Os 20 s em que o motor continua servindo depois de pedirem que pare
        # sao para o proxy do deploy em nuvem tira-lo de rotacao. Aqui nao ha
        # proxy nenhum -- so a pessoa esperando o motor reiniciar.
        "PROXY_DRAIN_SECONDS": "0",
        # Pedido que altera algo so de pagina autorizada (o site, localhost):
        # sem isto, qualquer site aberto no navegador poderia mandar o motor
        # desta maquina baixar e processar o que quisesse. Ver app.py.
        "CORTES_ORIGEM_ESTRITA": "1",
    })
    env.update({k: v for k, v in (da_pessoa or {}).items() if k not in PROTEGIDAS})
    if pastas_em is not None:
        env.update({"OUTPUT_DIR": str(pastas_em / "output"),
                    "UPLOAD_DIR": str(pastas_em / "uploads"),
                    "DATA_DIR": str(pastas_em / "data")})
    return env


# --- quem atende a porta ------------------------------------------------------

LIVRE, MOTOR, OUTRO = "livre", "motor", "outro"


def quem_atende(porta: int, timeout: float = 2.0) -> str:
    """`livre`, `motor` (um Cortes responde -- nosso ou o Docker) ou `outro`."""
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=timeout):
            pass
    except OSError:
        return LIVRE
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/config",
                                    timeout=timeout) as r:
            if r.status == 200 and "billingEnabled" in json.load(r):
                return MOTOR
    except Exception:
        pass
    return OUTRO


# --- o processo do motor --------------------------------------------------------

LOG_MAXIMO = 5 * 1024 * 1024


def girar_log(caminho: Path) -> None:
    """Um log por vez mais o anterior: o motor repete cada linha de todo job,
    e um arquivo que so cresce e disco que ninguem pediu para gastar."""
    try:
        if caminho.stat().st_size > LOG_MAXIMO:
            os.replace(caminho, caminho.with_name(caminho.name + ".1"))
    except OSError:
        pass


class Motor:
    """O `uvicorn app:app` em 127.0.0.1 -- so nesta maquina, nunca na rede."""

    def __init__(self, c: Caminhos, env_fn: Callable[[], dict], porta: int = PORTA,
                 log_nome: str = "motor.log"):
        self.c = c
        self.env_fn = env_fn
        self.porta = porta
        self.log_nome = log_nome
        self.proc: Optional[subprocess.Popen] = None

    def vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self) -> None:
        self.c.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.c.logs / self.log_nome
        girar_log(log_path)
        log = open(log_path, "a", encoding="utf-8")
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} motor subindo\n")
        log.flush()
        kw = {}
        if NO_WINDOWS:
            # Console NOVO e escondido, que o main.py e os ffmpeg herdam. Sem
            # console nenhum (CREATE_NO_WINDOW), cada filho abriria o SEU,
            # visivel -- uma janela preta piscando a cada corte.
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kw = {"startupinfo": si, "creationflags": subprocess.CREATE_NEW_CONSOLE}
        self.proc = subprocess.Popen(
            [str(self.c.python), "-m", "uvicorn", "app:app",
             "--host", "127.0.0.1", "--port", str(self.porta)],
            cwd=str(self.c.motor), env=self.env_fn(),
            stdout=log, stderr=subprocess.STDOUT, **kw)
        log.close()  # o filho tem a copia dele

    def parar(self) -> None:
        if not self.vivo():
            return
        if NO_WINDOWS:
            # A arvore inteira: o servidor, os jobs e os ffmpeg deles.
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=_SEM_JANELA)
        else:
            self.proc.terminate()
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


# --- a decisao ------------------------------------------------------------------

INICIANDO, PRONTO, DOCKER, OCUPADA, ERRO = (
    "iniciando", "pronto", "docker", "porta-ocupada", "erro")

TEXTO_DO_ESTADO = {
    INICIANDO: "iniciando o motor...",
    PRONTO: "pronto",
    DOCKER: "outro motor do Cortes (o Docker) ja esta atendendo",
    OCUPADA: f"a porta {PORTA} esta ocupada por outro programa",
    ERRO: "o motor nao subiu -- veja o log",
}

ESPERAS_APOS_FALHA_S = (5, 15, 60, 300)


class Ajudante:
    """A decisao de cada volta, separada da bandeja para o CI alcancar.

    Nunca derruba quem ja atende. Com um motor do Cortes na 8000 (o Docker),
    o nosso para -- depois de terminar o job que estiver rodando -- e fica
    parado ate ela liberar: o autor desliga o Docker e, na volta seguinte, o
    ajudante sobe. Um motor do Cortes que nao e o nosso na PROPRIA porta (o de
    um ajudante que caiu sem leva-lo junto) tambem e respeitado: ele atende o
    site do mesmo jeito.
    """

    def __init__(self, motor, quem_atende_fn: Callable[[], str] = lambda: quem_atende(PORTA),
                 docker_fn: Callable[[], str] = lambda: quem_atende(PORTA_DO_DOCKER),
                 ocupado_fn: Callable[[], bool] = lambda: False,
                 relogio: Callable[[], float] = time.monotonic):
        self.motor = motor
        self.quem_atende = quem_atende_fn
        self.docker = docker_fn
        self.ocupado = ocupado_fn
        self.relogio = relogio
        self.estado = INICIANDO
        self.falhas = 0
        self.proxima_tentativa = 0.0
        self._subiu_em: Optional[float] = None
        self.encerrado = False

    def encerrar(self) -> None:
        """Sair ou trocar de versao: nenhuma volta seguinte sobe o motor de
        novo, nem a que ja estava no meio quando o pedido chegou."""
        self.encerrado = True

    def passo(self) -> str:
        if self.encerrado:
            return self.estado
        agora = self.relogio()
        if self.docker() == MOTOR:
            # O site procura a 8000 primeiro: com o Docker de pe, o nosso motor
            # so disputaria placa e memoria.
            if self.motor.vivo():
                if self.ocupado():
                    self.estado = PRONTO  # termina o que comecou, depois cede
                    return self.estado
                self.motor.parar()
            self._subiu_em = None  # parar para ceder nao e falha
            self.estado = DOCKER
            return self.estado
        if self.motor.vivo():
            if self.quem_atende() == MOTOR:
                self.estado, self.falhas = PRONTO, 0
            else:
                self.estado = INICIANDO
            return self.estado
        if self._subiu_em is not None:
            # Estava de pe (ou subindo) e morreu: conta como falha.
            self._subiu_em = None
            self.falhas += 1
            espera = ESPERAS_APOS_FALHA_S[min(self.falhas, len(ESPERAS_APOS_FALHA_S)) - 1]
            self.proxima_tentativa = agora + espera
        dono = self.quem_atende()
        if dono == MOTOR:
            self.estado = DOCKER
            return self.estado
        if dono == OUTRO:
            self.estado = OCUPADA
            return self.estado
        if agora < self.proxima_tentativa:
            self.estado = ERRO
            return self.estado
        self.motor.iniciar()
        self._subiu_em = agora
        self.estado = INICIANDO
        return self.estado


# --- Windows: instancia unica, iniciar com o Windows, bandeja -------------------

_MUTEX = None  # o handle vive enquanto o processo vive; soltar libera o nome


def ja_existe_outro_ajudante() -> bool:
    """Mutex nomeado: um segundo clique no atalho so abre o site."""
    global _MUTEX
    if not NO_WINDOWS:
        return False
    import ctypes
    # `use_last_error`: o GetLastError chamado como outra funcao qualquer le o
    # erro da ULTIMA chamada ao Windows, que pode ja ser uma do proprio Python.
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _MUTEX = k32.CreateMutexW(None, False, "Local\\CortesAjudante")
    return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS


def ajudante_rodando() -> bool:
    """Ha um ajudante de pe? Pergunta pelo mutex sem cria-lo."""
    if not NO_WINDOWS:
        return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenMutexW(0x00100000, False, "Local\\CortesAjudante")  # SYNCHRONIZE
    if h:
        k32.CloseHandle(h)
        return True
    return False


_CHAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def comando_de_inicio(c: Caminhos) -> str:
    """O mesmo que o instalador grava: o `iniciar.py`, e nao este arquivo --
    este muda de pasta a cada versao."""
    return f'"{c.python.with_name("pythonw.exe")}" "{c.base / "iniciar.py"}"'


def inicia_com_o_windows() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN) as k:
            winreg.QueryValueEx(k, NOME)
            return True
    except OSError:
        return False


def iniciar_com_o_windows(ligar: bool, c: Caminhos) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando_de_inicio(c))
        else:
            try:
                winreg.DeleteValue(k, NOME)
            except OSError:
                pass


def abrir(caminho) -> None:
    if NO_WINDOWS:
        os.startfile(str(caminho))  # noqa: S606 -- pasta/arquivo local
    else:
        webbrowser.open(str(caminho))


def imagem_do_icone():
    """A inicial sobre o latao, como o cabecalho do painel."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(176, 141, 87, 255))
    fonte_path = Path(__file__).resolve().parent.parent / "fonts" / "Anton-Regular.ttf"
    try:
        fonte = ImageFont.truetype(str(fonte_path), 44)
    except OSError:
        fonte = ImageFont.load_default()
    d.text((32, 33), "C", font=fonte, fill=(20, 18, 16, 255), anchor="mm")
    return img


def _atualizacao():
    """O modulo da atualizacao, com ESTE arquivo registrado como `ajudante`.

    Rodado pelo `iniciar.py`, este arquivo e o `__main__`; sem o registro, o
    `import ajudante` de la leria o arquivo de novo e criaria um segundo
    modulo, com outras classes e outro `_MUTEX` -- o mesmo defeito que o
    CLAUDE.md descreve para o `main.py`."""
    if __name__ == "__main__":
        sys.modules.setdefault("ajudante", sys.modules[__name__])
    import atualizacao
    return atualizacao


def rodar_bandeja(c: Caminhos, aviso: Optional[str] = None) -> None:
    import pystray

    at = _atualizacao()
    placa = tem_placa_nvidia()
    motor = Motor(c, lambda: ambiente_do_motor(c, placa, os.environ, ler_env_da_pessoa(c)))
    ajudante = Ajudante(
        motor, ocupado_fn=lambda: (at.saude(PORTA) or {}).get("jobs_ativos", 0) > 0)
    parar = threading.Event()
    primeira_vez = not (c.dados / ".ja_abriu_o_site").exists()
    versao = at.versao_de(c.motor) or "de desenvolvimento"

    def titulo() -> str:
        extra = ""
        if ajudante.estado == PRONTO:
            extra = " (placa de video)" if placa else " (processador)"
        return f"{NOME}: {TEXTO_DO_ESTADO[ajudante.estado]}{extra}"

    def sair(icone, _item=None):
        parar.set()
        ajudante.encerrar()
        motor.parar()
        icone.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _i: titulo(), None, enabled=False),
        pystray.MenuItem(f"versao {versao}", None, enabled=False),
        pystray.MenuItem("Abrir o Cortes", lambda *_: webbrowser.open(SITE), default=True),
        pystray.MenuItem("Abrir a pasta dos cortes",
                         lambda *_: abrir(c.dados / "output")),
        pystray.MenuItem("Ver o log do motor", lambda *_: abrir(c.logs / "motor.log")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Iniciar com o Windows",
                         lambda *_: iniciar_com_o_windows(not inicia_com_o_windows(), c),
                         checked=lambda _i: inicia_com_o_windows()),
        pystray.MenuItem("Sair", sair),
    )
    icone = pystray.Icon(NOME, imagem_do_icone(), NOME, menu)

    def laco():
        nonlocal primeira_vez
        while not parar.is_set():
            if pedido_de_parar(c):
                # O desinstalador (ou um `--parar`) pediu: desliga tudo e sai.
                sair(icone)
                return
            anterior = ajudante.estado
            ajudante.passo()
            if ajudante.estado != anterior:
                icone.title = titulo()
                icone.update_menu()
            if primeira_vez and ajudante.estado in (PRONTO, DOCKER):
                # Depois de instalar, o site abre sozinho uma vez: e ali que o
                # Chrome pergunta a permissao, e e ali que a pessoa ve funcionar.
                primeira_vez = False
                webbrowser.open(SITE)
                try:
                    (c.dados / ".ja_abriu_o_site").touch()
                except OSError:
                    pass
            parar.wait(3 if ajudante.estado == INICIANDO else 15)

    def vigiar_atualizacoes():
        at.vigiar(c, lambda: ajudante.estado, parar, at.lancar_aplicacao,
                  lambda: sair(icone), at.registro(c))

    def ao_abrir(icone_):
        icone_.visible = True
        if aviso:
            try:
                icone_.notify(aviso, NOME)
            except Exception:
                pass

    threading.Thread(target=laco, daemon=True).start()
    if os.environ.get("CORTES_ATUALIZAR", "1") != "0":
        threading.Thread(target=vigiar_atualizacoes, daemon=True).start()
    icone.run(setup=ao_abrir)


# --- modos de linha de comando ---------------------------------------------

def pedido_de_parar(c: Caminhos) -> bool:
    marca = c.dados / ".parar"
    if not marca.exists():
        return False
    try:
        marca.unlink()
    except OSError:
        pass
    return True


def pedir_para_parar(c: Caminhos, prazo_s: float = 40,
                     rodando: Callable[[], bool] = ajudante_rodando) -> int:
    """`--parar`: o desinstalador nao pode apagar o que o ajudante tem aberto.
    Deixa a marca e espera o ajudante que esta rodando a consumir. Sem
    ajudante de pe, sai na hora -- esperar o prazo inteiro por ninguem
    atrasaria toda desinstalacao."""
    if not rodando():
        return 0
    c.dados.mkdir(parents=True, exist_ok=True)
    marca = c.dados / ".parar"
    marca.touch()
    fim = time.monotonic() + prazo_s
    while marca.exists() and time.monotonic() < fim:
        time.sleep(0.5)
    if marca.exists():  # nenhum ajudante rodando: nada a parar
        marca.unlink()
    return 0


def fim_do_log(c: Caminhos, nome: str = "motor.log", linhas: int = 80) -> str:
    try:
        texto = (c.logs / nome).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(sem log do motor)"
    return "\n".join(texto.splitlines()[-linhas:])


def importar_o_pipeline(c: Caminhos, env: dict) -> tuple:
    """`import main`: o servidor responder prova o `app.py`, e o pipeline mora
    no `main.py`, que so roda quando um video chega. E ele que carrega torch,
    mediapipe e o resto -- uma dependencia quebrada so apareceria ali."""
    try:
        r = subprocess.run([str(c.python), "-c", "import main"], cwd=str(c.motor), env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300, creationflags=_SEM_JANELA)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def verificar(c: Caminhos, porta: int = PORTA, temporario: bool = False,
              prazo_s: float = 300) -> int:
    """`--verificar`: sobe o motor como a bandeja subiria, espera ele responder,
    confere que o pipeline importa e desliga. O CI roda isto depois de
    instalar o .exe de verdade; a atualizacao, antes de trocar de versao.

    `--temporario` poe projetos, uploads e banco numa pasta que e apagada no
    fim: verificar uma versao nova nao pode retomar a fila nem migrar o banco
    de verdade. Na falha, imprime o fim do log -- e o que o CI e o registro da
    atualizacao guardam sem pedir."""
    placa = tem_placa_nvidia()
    pastas = c.dados / "verificacao" / str(os.getpid()) if temporario else None
    log_nome = "verificacao.log" if temporario else "motor.log"

    def env() -> dict:
        return ambiente_do_motor(c, placa, os.environ, ler_env_da_pessoa(c), pastas)

    motor = Motor(c, env, porta=porta, log_nome=log_nome)
    if quem_atende(porta) != LIVRE:
        print(f"a porta {porta} ja esta em uso; nada a verificar")
        return 2
    print(f"verificando a versao {c.motor.name} em 127.0.0.1:{porta}", flush=True)
    motor.iniciar()
    fim = time.monotonic() + prazo_s
    try:
        while time.monotonic() < fim:
            if not motor.vivo():
                print("o motor morreu ao subir:\n" + fim_do_log(c, log_nome))
                return 1
            if quem_atende(porta) == MOTOR:
                break
            time.sleep(2)
        else:
            print("o motor nao respondeu a tempo:\n" + fim_do_log(c, log_nome))
            return 1
        ok, saida = importar_o_pipeline(c, env())
        if not ok:
            print("o servidor subiu, mas o pipeline (main.py) nao importa:\n" + saida)
            return 1
        print(f"motor pronto ({'placa de video' if placa else 'processador'})", flush=True)
        return 0
    finally:
        motor.parar()
        if pastas is not None:
            shutil.rmtree(pastas, ignore_errors=True)


def atualizar_agora(c: Caminhos) -> int:
    """`--atualizar-agora`: confere, prepara e troca, tudo nesta chamada. E o
    que o CI usa para provar a troca e a volta; a bandeja faz o mesmo sozinha,
    de 6 em 6 horas."""
    at = _atualizacao()
    log = at.registro(c)
    if ajudante_rodando():
        print("o ajudante esta aberto: ele se atualiza sozinho quando o motor estiver livre")
        return 2
    try:
        nova = at.preparar_se_houver(c, log)
    except Exception as e:
        log(f"conferir atualizacao: {e!r}")
        return 1
    if nova is None:
        log(f"nada a trocar (versao {at.versao_de(c.motor) or 'sem versao'})")
        return 0
    return 0 if at.aplicar(c, nova, log) else 1


def esperar_o_anterior_sair(prazo_s: float = 60) -> None:
    """`--reinicio`: a troca de versao abre o ajudante novo logo depois de o
    antigo sair; sem esperar, o mutex dele ainda poderia estar de pe, e o novo
    concluiria que ja ha um ajudante e so abriria o site."""
    fim = time.monotonic() + prazo_s
    while ajudante_rodando() and time.monotonic() < fim:
        time.sleep(0.5)


def _valor(argv: list, nome: str, padrao=None):
    if nome in argv and argv.index(nome) + 1 < len(argv):
        return argv[argv.index(nome) + 1]
    return padrao


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    c = caminhos_padrao()
    if "--parar" in argv:
        return pedir_para_parar(c)
    if "--verificar" in argv:
        return verificar(c, porta=int(_valor(argv, "--porta", PORTA)),
                         temporario="--temporario" in argv)
    if "--atualizar-agora" in argv:
        return atualizar_agora(c)
    if "--reinicio" in argv:
        esperar_o_anterior_sair()
    if ja_existe_outro_ajudante():
        webbrowser.open(SITE)
        return 0
    c.dados.mkdir(parents=True, exist_ok=True)
    aviso = None
    if "--atualizado" in argv:
        aviso = f"Atualizado para a versao {_valor(argv, '--atualizado', '')}."
    elif "--atualizacao-falhou" in argv:
        aviso = (f"A versao {_valor(argv, '--atualizacao-falhou', '')} nao passou na "
                 "verificacao; o Cortes continua na anterior.")
    rodar_bandeja(c, aviso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
