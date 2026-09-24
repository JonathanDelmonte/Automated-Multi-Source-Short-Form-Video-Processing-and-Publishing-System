"""O ajudante: o programa que roda o motor no computador de quem usa (Fase 6.2).

O site (https://virtu-clips.zirtuno.workers.dev) e so a tela. Quem baixa o
video, transcreve e corta e o motor -- o mesmo `app.py` do Docker --, e o
ajudante e quem o mantem de pe no Windows, sem Docker:

- sobe o motor em 127.0.0.1:8000, num console ESCONDIDO que os filhos herdam
  (sem ele, cada ffmpeg do job piscaria uma janela preta na tela);
- escolhe placa de video ou processador pelo `nvidia-smi`;
- fica QUIETO quando outro motor ja atende a porta -- o Docker do autor. Subir
  por cima seria disputar o endereco, e o Windows deixaria os dois de pe, com o
  mais novo roubando os pedidos do outro;
- mora perto do relogio: abrir o site, abrir a pasta dos cortes, ver o log,
  iniciar com o Windows e sair.

A logica (`Ajudante.passo`, `ambiente_do_motor`, `quem_atende`) e stdlib pura
e roda no CI de sempre; so a bandeja (`pystray`) e o registro (`winreg`) sao do
Windows, e ficam em funcoes que o teste nao chama.

Uso: pythonw.exe ajudante.py   (o instalador cria o atalho)
"""
from __future__ import annotations

import json
import os
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
PORTA = 8000
NOME = "Cortes"

NO_WINDOWS = os.name == "nt"
_SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class Caminhos:
    """Onde cada coisa mora. O codigo e TROCADO a cada atualizacao; os dados
    nunca -- por isso vivem em pastas irmas, e nao um dentro do outro."""
    base: Path

    @property
    def motor(self) -> Path:        # o repositorio: app.py, main.py, fonts/...
        return self.base / "motor"

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


def ambiente_do_motor(c: Caminhos, placa: bool, base: Mapping[str, str],
                      da_pessoa: Optional[Mapping[str, str]] = None) -> dict:
    """As variaveis com que o motor sobe. O `.env` da pessoa vence tudo.

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
    })
    env.update(da_pessoa or {})
    return env


# --- quem atende a porta ------------------------------------------------------

LIVRE, MOTOR, OUTRO = "livre", "motor", "outro"


def quem_atende(porta: int = PORTA, timeout: float = 2.0) -> str:
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

    def __init__(self, c: Caminhos, env_fn: Callable[[], dict]):
        self.c = c
        self.env_fn = env_fn
        self.proc: Optional[subprocess.Popen] = None

    def vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self) -> None:
        self.c.logs.mkdir(parents=True, exist_ok=True)
        log_path = self.c.logs / "motor.log"
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
             "--host", "127.0.0.1", "--port", str(PORTA)],
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
    DOCKER: "o Docker ja esta atendendo",
    OCUPADA: "a porta 8000 esta ocupada por outro programa",
    ERRO: "o motor nao subiu -- veja o log",
}

ESPERAS_APOS_FALHA_S = (5, 15, 60, 300)


class Ajudante:
    """A decisao de cada volta, separada da bandeja para o CI alcancar.

    Nunca derruba quem ja atende: se a porta responde e nao e o nosso
    processo, e o Docker (ou outro ajudante), e ficamos parados ate ela
    liberar -- o autor desliga o Docker e, na volta seguinte, o ajudante sobe.
    """

    def __init__(self, motor, quem_atende_fn: Callable[[], str] = quem_atende,
                 relogio: Callable[[], float] = time.monotonic):
        self.motor = motor
        self.quem_atende = quem_atende_fn
        self.relogio = relogio
        self.estado = INICIANDO
        self.falhas = 0
        self.proxima_tentativa = 0.0
        self._subiu_em: Optional[float] = None

    def passo(self) -> str:
        agora = self.relogio()
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


def comando_de_inicio() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve()}"'


def inicia_com_o_windows() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN) as k:
            winreg.QueryValueEx(k, NOME)
            return True
    except OSError:
        return False


def iniciar_com_o_windows(ligar: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CHAVE_RUN, 0, winreg.KEY_SET_VALUE) as k:
        if ligar:
            winreg.SetValueEx(k, NOME, 0, winreg.REG_SZ, comando_de_inicio())
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


def rodar_bandeja(c: Caminhos) -> None:
    import pystray

    placa = tem_placa_nvidia()
    motor = Motor(c, lambda: ambiente_do_motor(c, placa, os.environ, ler_env_da_pessoa(c)))
    ajudante = Ajudante(motor)
    parar = threading.Event()
    primeira_vez = not (c.dados / ".ja_abriu_o_site").exists()

    def titulo() -> str:
        extra = ""
        if ajudante.estado == PRONTO:
            extra = " (placa de video)" if placa else " (processador)"
        return f"{NOME}: {TEXTO_DO_ESTADO[ajudante.estado]}{extra}"

    def sair(icone, _item):
        parar.set()
        motor.parar()
        icone.stop()

    menu = pystray.Menu(
        pystray.MenuItem(lambda _i: titulo(), None, enabled=False),
        pystray.MenuItem("Abrir o Cortes", lambda *_: webbrowser.open(SITE), default=True),
        pystray.MenuItem("Abrir a pasta dos cortes",
                         lambda *_: abrir(c.dados / "output")),
        pystray.MenuItem("Ver o log do motor", lambda *_: abrir(c.logs / "motor.log")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Iniciar com o Windows",
                         lambda *_: iniciar_com_o_windows(not inicia_com_o_windows()),
                         checked=lambda _i: inicia_com_o_windows()),
        pystray.MenuItem("Sair", sair),
    )
    icone = pystray.Icon(NOME, imagem_do_icone(), NOME, menu)

    def laco():
        nonlocal primeira_vez
        while not parar.is_set():
            if pedido_de_parar(c):
                # O desinstalador (ou um `--parar`) pediu: desliga tudo e sai.
                sair(icone, None)
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

    threading.Thread(target=laco, daemon=True).start()
    icone.run()


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


def fim_do_log(c: Caminhos, linhas: int = 80) -> str:
    try:
        texto = (c.logs / "motor.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(sem log do motor)"
    return "\n".join(texto.splitlines()[-linhas:])


def verificar(c: Caminhos, prazo_s: float = 300) -> int:
    """`--verificar`: sobe o motor como a bandeja subiria, espera ele responder
    e desliga. E o que o CI roda depois de instalar o .exe de verdade -- prova a
    instalacao (venv, pastas, ffmpeg no PATH) sem precisar de tela. Na falha,
    imprime o fim do log: e a unica coisa que o CI guarda sem pedir."""
    placa = tem_placa_nvidia()
    motor = Motor(c, lambda: ambiente_do_motor(c, placa, os.environ, ler_env_da_pessoa(c)))
    if quem_atende() != LIVRE:
        print("a porta 8000 ja esta em uso; nada a verificar")
        return 2
    motor.iniciar()
    fim = time.monotonic() + prazo_s
    try:
        while time.monotonic() < fim:
            if not motor.vivo():
                print("o motor morreu ao subir:\n" + fim_do_log(c))
                return 1
            if quem_atende() == MOTOR:
                print(f"motor pronto ({'placa de video' if placa else 'processador'})")
                return 0
            time.sleep(2)
        print("o motor nao respondeu a tempo:\n" + fim_do_log(c))
        return 1
    finally:
        motor.parar()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    c = caminhos_padrao()
    if "--parar" in argv:
        return pedir_para_parar(c)
    if "--verificar" in argv:
        return verificar(c)
    if ja_existe_outro_ajudante():
        webbrowser.open(SITE)
        return 0
    c.dados.mkdir(parents=True, exist_ok=True)
    rodar_bandeja(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
