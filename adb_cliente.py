"""Cliente do servidor do adb, so com a biblioteca padrao -- etapa 7.9 (ADR-016).

O programa nao traz o adb: quem usa instala o do Google uma vez (`winget install
--id Google.PlatformTools`). Este modulo fala com o SERVIDOR dele, pela porta
5037, no protocolo de texto que o proprio adb documenta (`docs/dev/services.md`
e `docs/dev/sync.md` no codigo do adb):

- todo pedido e o tamanho em 4 digitos hexadecimais, seguido do texto;
- a resposta comeca por `OKAY` ou `FAIL` (no `FAIL`, 4 hex e a mensagem);
- `host:transport:<serial>` passa a conexao para o aparelho: o pedido seguinte
  vai para o adbd do celular;
- `exec:<comando>` roda pelo `sh` do aparelho sem terminal, entao os bytes saem
  intactos -- o que importa para o PNG do `screencap`;
- `sync:` e depois SEND/DATA/DONE mandam um arquivo.

**Uma conexao por pedido**, como o cliente do proprio adb faz: o servidor fecha
a conexao ao fim de cada servico, e reaproveitar uma so economizaria
milissegundos num caminho que gasta segundos esperando o celular.

**Nenhuma dependencia nova, e por isso nenhuma imagem a reconstruir**: o
`requirements.txt` mudar faria o botao "atualizar agora" mandar o `reconstruir`
de 40 minutos, e o adb cabe num socket.

Nada aqui guarda estado do aparelho nem decide nada sobre ele: ler o estado,
pôr o video na galeria e tocar na tela e do `frota_aparelho.py`.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import struct
import subprocess
import time
from typing import Callable, Optional

PORTA_PADRAO = 5037

#: O Docker Desktop encaminha este nome ao loopback do Windows, onde o servidor
#: do adb escuta (ADR-016). O adb nao precisa ficar aberto na rede.
HOST_DO_DOCKER = "host.docker.internal"

#: Teto de bytes lidos de um comando. O PNG de uma tela 4K passa de 10 MB; mais
#: que isto e um comando que despejou o que nao devia, e o motor nao o guarda.
MAX_SAIDA = 64 * 1024 * 1024

#: O pedaco do `sync:`. O protocolo recusa DATA maior que 64 KiB.
PEDACO = 64 * 1024

#: S_IFREG | 0644: arquivo comum, que todo app le. O modo vai em decimal.
MODO_DO_ARQUIVO = 0o100644

#: O marcador com que `executar_texto` separa a saida do codigo de retorno.
_MARCA_RC = "@@vc-rc="

#: Os estados do `host:devices-l`, com a palavra que a tela mostra.
ESTADOS = {
    "device": "no ar",
    "offline": "fora do ar",
    "unauthorized": "esperando autorizar",
    "authorizing": "autorizando",
    "connecting": "conectando",
    "no permissions": "sem permissão",
    "recovery": "em recuperação",
    "sideload": "em recuperação",
    "bootloader": "em bootloader",
    "host": "servidor",
}


class AdbErro(RuntimeError):
    """O servidor ou o aparelho recusou o pedido. A mensagem e a do adb, para o
    painel mostrar: "device unauthorized" diz mais que qualquer traducao."""


class AdbForaDoAr(AdbErro):
    """Nao ha servidor do adb no endereco. E o caso de quem ainda nao instalou o
    adb, ou de quem reiniciou o Windows e nao ligou de novo."""


# --------------------------------------------------------------------------- #
# Onde esta o servidor, e onde esta o adb
# --------------------------------------------------------------------------- #

def em_container() -> bool:
    """Se o motor roda dentro do Docker. O `/.dockerenv` e o marcador que o
    proprio Docker cria em todo container."""
    return os.path.exists("/.dockerenv")


def endereco_padrao() -> tuple[str, int]:
    """O servidor do adb que o motor usa: `ADB_SERVER` (`host:porta` ou so o
    host) manda; sem ele, o do Windows visto de dentro do Docker, ou o desta
    maquina."""
    bruto = (os.environ.get("ADB_SERVER") or "").strip()
    if bruto:
        host, sep, porta = bruto.rpartition(":")
        if not sep or not porta.isdigit() or "]" in porta:
            host, porta = bruto, ""
        host = host.strip("[]") or "127.0.0.1"
        numero = int(porta) if porta and 0 < int(porta) < 65536 else PORTA_PADRAO
        return host, numero
    return (HOST_DO_DOCKER if em_container() else "127.0.0.1"), PORTA_PADRAO


def _candidatos_do_adb() -> list[str]:
    nome = "adb.exe" if os.name == "nt" else "adb"
    caminhos = []
    if os.environ.get("ADB_PATH"):
        caminhos.append(os.environ["ADB_PATH"])
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or ""
        perfil = os.environ.get("USERPROFILE") or ""
        # O exe de verdade, ao lado das DLLs, antes do apelido do winget: o
        # apelido ja falhou em achar a AdbWinApi.dll (winget-pkgs#195087).
        caminhos += sorted(glob.glob(os.path.join(
            local, "Microsoft", "WinGet", "Packages", "Google.PlatformTools*",
            "platform-tools", nome)), reverse=True)
        caminhos += [
            os.path.join(local, "Android", "Sdk", "platform-tools", nome),
            os.path.join(perfil, "platform-tools", nome),
            os.path.join("C:\\", "platform-tools", nome),
            os.path.join(local, "Microsoft", "WinGet", "Links", nome),
        ]
    else:
        casa = os.path.expanduser("~")
        caminhos += [os.path.join(casa, "Android", "Sdk", "platform-tools", nome),
                     os.path.join(casa, "Library", "Android", "sdk", "platform-tools", nome)]
    achado = shutil.which(nome)
    if achado:
        caminhos.append(achado)
    return caminhos


def achar_adb() -> Optional[str]:
    """O executavel do adb nesta maquina, ou None."""
    for caminho in _candidatos_do_adb():
        if caminho and os.path.isfile(caminho):
            return caminho
    return None


def ligar_servidor(adb: Optional[str] = None, espera_s: float = 8.0) -> bool:
    """Liga o servidor do adb desta maquina com `adb start-server`.

    So serve fora do Docker: de dentro do container, o adb e o do Windows, e
    quem o liga e a pessoa (ou o `atalhos/celulares.bat`). Devolve se o servidor
    passou a responder."""
    adb = adb or achar_adb()
    if not adb or em_container():
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run([adb, "start-server"], capture_output=True, timeout=espera_s + 5,
                       creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return False
    return Cliente(timeout=2).no_ar()


# --------------------------------------------------------------------------- #
# Validacao do que vem do painel
# --------------------------------------------------------------------------- #

_SERIAL = re.compile(r"^[A-Za-z0-9._:@\-\[\]]{1,200}$")
_ENDERECO = re.compile(r"^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.\-]{1,253}):(\d{1,5})$")


def serial_valido(serial: str) -> bool:
    """O serial vai direto num pedido ao servidor: nada de espaco, quebra de
    linha ou caractere de controle. Cobre os do cabo (`R58M12ABCDE`), os da rede
    (`192.168.0.5:5555`) e os do pareamento por mDNS
    (`adb-R58M12ABCDE-AbCdEf._adb-tls-connect._tcp`)."""
    return bool(serial) and bool(_SERIAL.match(serial))


def endereco_valido(endereco: str) -> bool:
    """`host:porta`, com a porta de 1 a 65535."""
    m = _ENDERECO.match(endereco or "")
    return bool(m) and 0 < int(m.group(2)) < 65536


def codigo_valido(codigo: str) -> bool:
    """O codigo de pareamento do Android 11+: seis digitos."""
    return bool(re.fullmatch(r"\d{6}", codigo or ""))


def aspas(texto: str) -> str:
    """O texto como UM argumento do `sh` do aparelho, entre aspas simples.

    Todo pedaco variavel de um comando passa por aqui: um nome de arquivo com
    espaco quebraria o comando, e um com `;` rodaria outro."""
    return "'" + str(texto).replace("'", "'\\''") + "'"


# --------------------------------------------------------------------------- #
# O protocolo
# --------------------------------------------------------------------------- #

def _ler_exato(sock: socket.socket, n: int) -> bytes:
    partes, falta = [], n
    while falta > 0:
        bloco = sock.recv(min(falta, 65536))
        if not bloco:
            raise AdbErro("o servidor do adb fechou a conexão no meio da resposta")
        partes.append(bloco)
        falta -= len(bloco)
    return b"".join(partes)


def _ler_ate_o_fim(sock: socket.socket, maximo: int = MAX_SAIDA) -> bytes:
    partes, total = [], 0
    while True:
        bloco = sock.recv(65536)
        if not bloco:
            return b"".join(partes)
        total += len(bloco)
        if total > maximo:
            raise AdbErro(f"a saída do comando passou de {maximo // (1024 * 1024)} MB")
        partes.append(bloco)


def _pedido(texto: str) -> bytes:
    corpo = texto.encode("utf-8")
    if len(corpo) > 0xFFFF:
        raise AdbErro("pedido grande demais para o protocolo do adb")
    return f"{len(corpo):04x}".encode("ascii") + corpo


def _status(sock: socket.socket) -> None:
    """Le OKAY, ou levanta com a mensagem do FAIL."""
    status = _ler_exato(sock, 4)
    if status == b"OKAY":
        return
    if status == b"FAIL":
        raise AdbErro(_texto_com_tamanho(sock))
    raise AdbErro(f"resposta inesperada do servidor do adb: {status!r}")


def _texto_com_tamanho(sock: socket.socket) -> str:
    try:
        tamanho = int(_ler_exato(sock, 4).decode("ascii"), 16)
    except ValueError:
        raise AdbErro("tamanho ilegível na resposta do servidor do adb")
    return _ler_exato(sock, tamanho).decode("utf-8", "replace")


def ler_aparelhos(texto: str) -> list[dict]:
    """As linhas do `host:devices-l`, uma por aparelho:

        R58M12ABCDE   device usb:1-1 product:x model:SM_G973U device:y transport_id:1
        ZY22ABCDEF    unauthorized usb:1-2 transport_id:4
        0123          no permissions (user in plugdev group...); see [...]
    """
    saida = []
    for linha in (texto or "").splitlines():
        partes = linha.split()
        if len(partes) < 2:
            continue
        serial, estado, resto = partes[0], partes[1], partes[2:]
        if estado == "no" and resto and resto[0].startswith("permissions"):
            estado, resto = "no permissions", []
        extras = {}
        for parte in resto:
            chave, sep, valor = parte.partition(":")
            if sep and chave in ("usb", "product", "model", "device", "transport_id"):
                extras[chave] = valor
        saida.append({
            "serial": serial,
            "estado": estado,
            "no_ar": estado == "device",
            "rotulo": ESTADOS.get(estado, estado),
            "modelo": (extras.get("model") or "").replace("_", " ") or None,
            "usb": "usb" in extras,
            "transport_id": extras.get("transport_id"),
        })
    return saida


class Cliente:
    """O servidor do adb num endereco. Barato de criar: nao abre nada ate o
    primeiro pedido."""

    def __init__(self, host: Optional[str] = None, porta: Optional[int] = None,
                 timeout: float = 15.0):
        padrao_host, padrao_porta = endereco_padrao()
        self.host = host or padrao_host
        self.porta = int(porta or padrao_porta)
        self.timeout = timeout

    @property
    def endereco(self) -> str:
        return f"{self.host}:{self.porta}"

    # -- conexao ------------------------------------------------------------ #

    def _abrir(self, timeout: Optional[float] = None) -> socket.socket:
        try:
            sock = socket.create_connection((self.host, self.porta),
                                            timeout=timeout or self.timeout)
        except OSError as e:
            raise AdbForaDoAr(f"não há servidor do adb em {self.endereco} ({e})")
        sock.settimeout(timeout or self.timeout)
        return sock

    def _consulta(self, pedido: str, com_resposta: bool = True) -> str:
        with self._abrir() as sock:
            sock.sendall(_pedido(pedido))
            _status(sock)
            return _texto_com_tamanho(sock) if com_resposta else ""

    def _no_aparelho(self, serial: str, servico: str,
                     timeout: Optional[float] = None) -> socket.socket:
        """Uma conexao ja passada para o aparelho, com o servico aberto."""
        if not serial_valido(serial):
            raise AdbErro(f"serial inválido: {serial!r}")
        sock = self._abrir(timeout)
        try:
            sock.sendall(_pedido(f"host:transport:{serial}"))
            _status(sock)
            sock.sendall(_pedido(servico))
            _status(sock)
        except BaseException:
            sock.close()
            raise
        return sock

    # -- o servidor --------------------------------------------------------- #

    def no_ar(self) -> bool:
        try:
            self.versao()
            return True
        except AdbErro:
            return False

    def versao(self) -> int:
        """A versao interna do servidor (41 no adb 35+)."""
        try:
            return int(self._consulta("host:version"), 16)
        except ValueError:
            raise AdbErro("versão ilegível do servidor do adb")

    def aparelhos(self) -> list[dict]:
        return ler_aparelhos(self._consulta("host:devices-l"))

    def conectar(self, endereco: str) -> tuple[bool, str]:
        """`adb connect`: o servidor passa a falar com o aparelho na rede.

        O adb responde OKAY ate quando falha -- quem diz se deu certo e o texto
        ("connected to", "already connected to" ou "failed to connect...")."""
        if not endereco_valido(endereco):
            raise AdbErro(f"endereço inválido: {endereco!r} (use ip:porta)")
        texto = self._consulta(f"host:connect:{endereco}")
        ok = texto.startswith("connected to") or texto.startswith("already connected")
        return ok, texto.strip()

    def desconectar(self, endereco: str) -> str:
        if not endereco_valido(endereco):
            raise AdbErro(f"endereço inválido: {endereco!r}")
        return self._consulta(f"host:disconnect:{endereco}").strip()

    def parear(self, endereco: str, codigo: str) -> tuple[bool, str]:
        """O pareamento do Android 11+ ("Depuracao por Wi-Fi > Parear com codigo").
        A porta de parear NAO e a de conectar: a tela do celular mostra as duas."""
        if not endereco_valido(endereco):
            raise AdbErro(f"endereço inválido: {endereco!r} (use ip:porta)")
        if not codigo_valido(codigo):
            raise AdbErro("o código de pareamento tem seis dígitos")
        texto = self._consulta(f"host:pair:{codigo}:{endereco}")
        return texto.startswith("Successfully paired"), texto.strip()

    def estado(self, serial: str) -> str:
        if not serial_valido(serial):
            raise AdbErro(f"serial inválido: {serial!r}")
        return self._consulta(f"host-serial:{serial}:get-state").strip()

    # -- o aparelho --------------------------------------------------------- #

    def executar(self, serial: str, comando: str, timeout: Optional[float] = None,
                 maximo: int = MAX_SAIDA) -> bytes:
        """Roda `comando` no `sh` do aparelho e devolve tudo o que ele escreveu,
        em bytes, sem traducao de linha (`exec:` nao tem terminal)."""
        with self._no_aparelho(serial, f"exec:{comando}", timeout) as sock:
            return _ler_ate_o_fim(sock, maximo)

    def executar_texto(self, serial: str, comando: str,
                       timeout: Optional[float] = None) -> tuple[str, Optional[int]]:
        """Como `executar`, em texto, e com o codigo de retorno do comando.

        O `exec:` nao devolve o codigo; o marcador no fim da saida, sim, e
        funciona em todo Android -- o protocolo de shell v2 so existe do 7 em
        diante."""
        bruto = self.executar(serial, f"{comando}; echo \"{_MARCA_RC}$?\"", timeout)
        texto = bruto.decode("utf-8", "replace")
        posicao = texto.rfind(_MARCA_RC)
        if posicao < 0:
            return texto, None
        codigo = texto[posicao + len(_MARCA_RC):].strip()
        return texto[:posicao], int(codigo) if codigo.isdigit() else None

    def enviar(self, serial: str, origem: str, destino: str,
               progresso: Optional[Callable[[int, int], None]] = None,
               timeout: Optional[float] = None) -> int:
        """`adb push`: manda o arquivo `origem` para `destino` no aparelho e
        devolve quantos bytes foram."""
        with open(origem, "rb") as arquivo:
            return self._enviar(serial, arquivo, os.path.getsize(origem), destino,
                                progresso, timeout)

    def enviar_bytes(self, serial: str, dados: bytes, destino: str,
                     timeout: Optional[float] = None) -> int:
        """Como `enviar`, a partir de bytes na memoria -- a legenda em `.txt`,
        sem arquivo temporario no disco do motor."""
        import io
        return self._enviar(serial, io.BytesIO(dados), len(dados), destino, None, timeout)

    def _enviar(self, serial, leitor, total, destino, progresso, timeout) -> int:
        destino_e_modo = f"{destino},{MODO_DO_ARQUIVO}".encode("utf-8")
        enviados = 0
        with self._no_aparelho(serial, "sync:", timeout or max(self.timeout, 60)) as sock:
            sock.sendall(b"SEND" + struct.pack("<I", len(destino_e_modo)) + destino_e_modo)
            while True:
                bloco = leitor.read(PEDACO)
                if not bloco:
                    break
                sock.sendall(b"DATA" + struct.pack("<I", len(bloco)) + bloco)
                enviados += len(bloco)
                if progresso:
                    progresso(enviados, total)
            sock.sendall(b"DONE" + struct.pack("<I", int(time.time())))
            resposta = _ler_exato(sock, 8)
            ident, tamanho = resposta[:4], struct.unpack("<I", resposta[4:])[0]
            if ident == b"FAIL":
                raise AdbErro(_ler_exato(sock, tamanho).decode("utf-8", "replace"))
            if ident != b"OKAY":
                raise AdbErro(f"resposta inesperada ao enviar o arquivo: {ident!r}")
            try:
                sock.sendall(b"QUIT" + struct.pack("<I", 0))
            except OSError:
                pass
        return enviados
