"""Um servidor do adb de mentira, para os testes da frota (etapa 7.9).

Fala o mesmo protocolo que o servidor de verdade (4 hex de tamanho, OKAY/FAIL,
`host:transport`, `exec:` e `sync:`), numa porta de 127.0.0.1, e por tras dele ha
aparelhos imitados: cada um responde aos comandos por expressoes regulares e
guarda os arquivos que recebe. Assim o cliente e o driver sao exercitados pelo
socket de verdade, sem celular e sem o adb do Google.
"""
from __future__ import annotations

import re
import socketserver
import struct
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional, Union

MARCA_RC = "; echo \"@@vc-rc=$?\""

Resposta = Union[bytes, str, tuple]


@dataclass
class AparelhoFalso:
    serial: str
    estado: str = "device"
    modelo: str = "Pixel_7"
    usb: bool = True
    #: (expressao, resposta): a resposta e bytes/str, (saida, codigo) ou uma
    #: funcao que recebe o comando e o `match` e devolve um desses.
    comandos: list = field(default_factory=list)
    arquivos: dict = field(default_factory=dict)
    executados: list = field(default_factory=list)

    def responder(self, expressao: str, resposta) -> "AparelhoFalso":
        self.comandos.insert(0, (re.compile(expressao, re.S), resposta))
        return self

    def rodar(self, comando: str) -> tuple[bytes, int]:
        self.executados.append(comando)
        for expressao, resposta in self.comandos:
            m = expressao.search(comando)
            if not m:
                continue
            if callable(resposta):
                resposta = resposta(comando, m)
            if isinstance(resposta, tuple):
                saida, codigo = resposta
            else:
                saida, codigo = resposta, 0
            if isinstance(saida, str):
                saida = saida.encode("utf-8")
            return saida, codigo
        return b"", 0


class ServidorFalso:
    """`with ServidorFalso() as s:` -- `s.porta` e a porta, `s.aparelhos` os
    aparelhos (por serial). `pareamento` e o codigo que o `host:pair` aceita."""

    def __init__(self, versao: int = 41):
        self.versao = versao
        self.aparelhos: dict[str, AparelhoFalso] = {}
        self.pedidos: list[str] = []
        self.pareamento = "123456"
        self.conectaveis: dict[str, AparelhoFalso] = {}
        self._srv: Optional[socketserver.ThreadingTCPServer] = None

    def acrescentar(self, aparelho: AparelhoFalso) -> AparelhoFalso:
        self.aparelhos[aparelho.serial] = aparelho
        return aparelho

    @property
    def porta(self) -> int:
        return self._srv.server_address[1]

    def __enter__(self):
        dono = self

        class Tratador(socketserver.BaseRequestHandler):
            def handle(self):
                dono._atender(self.request)

        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self._srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Tratador)
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, kwargs={"poll_interval": 0.02},
                         daemon=True).start()
        return self

    def __exit__(self, *exc):
        self._srv.shutdown()
        self._srv.server_close()

    # -- protocolo ---------------------------------------------------------- #

    @staticmethod
    def _ler(sock, n):
        dados = b""
        while len(dados) < n:
            bloco = sock.recv(n - len(dados))
            if not bloco:
                raise EOFError
            dados += bloco
        return dados

    def _pedido(self, sock) -> str:
        tamanho = int(self._ler(sock, 4).decode("ascii"), 16)
        return self._ler(sock, tamanho).decode("utf-8")

    @staticmethod
    def _ok(sock, texto: Optional[str] = None):
        sock.sendall(b"OKAY")
        if texto is not None:
            corpo = texto.encode("utf-8")
            sock.sendall(f"{len(corpo):04x}".encode() + corpo)

    @staticmethod
    def _falha(sock, texto: str):
        corpo = texto.encode("utf-8")
        sock.sendall(b"FAIL" + f"{len(corpo):04x}".encode() + corpo)

    def _linhas_de_aparelhos(self) -> str:
        linhas = []
        for a in self.aparelhos.values():
            # Como o adb de verdade: o modelo so aparece de aparelho autorizado
            # (o `unauthorized` ainda nao contou nada ao computador).
            modelo = f" product:x model:{a.modelo} device:y" if a.estado == "device" else ""
            extras = (" usb:1-1" if a.usb else "") + modelo + " transport_id:1"
            linhas.append(f"{a.serial:<22} {a.estado}{extras}")
        return "".join(l + "\n" for l in linhas)

    def _atender(self, sock):
        try:
            pedido = self._pedido(sock)
        except (EOFError, ValueError):
            return
        self.pedidos.append(pedido)
        if pedido == "host:version":
            return self._ok(sock, f"{self.versao:04x}")
        if pedido == "host:devices-l":
            return self._ok(sock, self._linhas_de_aparelhos())
        if pedido.startswith("host:connect:"):
            endereco = pedido[len("host:connect:"):]
            if endereco in self.aparelhos:
                return self._ok(sock, f"already connected to {endereco}")
            if endereco in self.conectaveis:
                self.aparelhos[endereco] = self.conectaveis.pop(endereco)
                return self._ok(sock, f"connected to {endereco}")
            return self._ok(sock, f"failed to connect to '{endereco}': Connection refused")
        if pedido.startswith("host:disconnect:"):
            endereco = pedido[len("host:disconnect:"):]
            self.aparelhos.pop(endereco, None)
            return self._ok(sock, f"disconnected {endereco}")
        if pedido.startswith("host:pair:"):
            _, _, resto = pedido.partition("host:pair:")
            codigo, _, endereco = resto.partition(":")
            if codigo == self.pareamento:
                return self._ok(sock, f"Successfully paired to {endereco} [guid=adb-falso]")
            return self._ok(sock, "Failed: Wrong password or connection was dropped.")
        m = re.match(r"host-serial:(.+):get-state$", pedido)
        if m:
            a = self.aparelhos.get(m.group(1))
            if a is None:
                return self._falha(sock, f"device '{m.group(1)}' not found")
            return self._ok(sock, a.estado)
        if pedido.startswith("host:transport:"):
            serial = pedido[len("host:transport:"):]
            a = self.aparelhos.get(serial)
            if a is None:
                return self._falha(sock, f"device '{serial}' not found")
            if a.estado != "device":
                return self._falha(sock, f"device {a.estado}")
            self._ok(sock)
            return self._servico(sock, a)
        return self._falha(sock, f"unknown host service {pedido}")

    def _servico(self, sock, aparelho: AparelhoFalso):
        servico = self._pedido(sock)
        self.pedidos.append(servico)
        if servico.startswith("exec:"):
            comando = servico[len("exec:"):]
            com_rc = comando.endswith(MARCA_RC)
            if com_rc:
                comando = comando[: -len(MARCA_RC)]
            saida, codigo = aparelho.rodar(comando)
            self._ok(sock)
            sock.sendall(saida)
            if com_rc:
                sock.sendall(f"@@vc-rc={codigo}\n".encode())
            return
        if servico == "sync:":
            self._ok(sock)
            return self._sync(sock, aparelho)
        self._falha(sock, f"unknown service {servico}")

    def _sync(self, sock, aparelho: AparelhoFalso):
        while True:
            try:
                cabeca = self._ler(sock, 8)
            except EOFError:
                return
            ident, tamanho = cabeca[:4], struct.unpack("<I", cabeca[4:])[0]
            if ident == b"QUIT":
                return
            if ident != b"SEND":
                return
            destino, _, _modo = self._ler(sock, tamanho).decode("utf-8").rpartition(",")
            dados = b""
            while True:
                cabeca = self._ler(sock, 8)
                ident, tamanho = cabeca[:4], struct.unpack("<I", cabeca[4:])[0]
                if ident == b"DATA":
                    dados += self._ler(sock, tamanho)
                    continue
                if ident == b"DONE":
                    break
                return
            if destino.startswith("/proibido"):
                corpo = b"Permission denied"
                sock.sendall(b"FAIL" + struct.pack("<I", len(corpo)) + corpo)
                return
            aparelho.arquivos[destino] = dados
            sock.sendall(b"OKAY" + struct.pack("<I", 0))


# --------------------------------------------------------------------------- #
# Um celular com telas: o fluxo de post de um app, pelo adb
# --------------------------------------------------------------------------- #

import base64
import io
from xml.sax.saxutils import quoteattr

ADBKEYBOARD = "com.android.adbkeyboard/.AdbIME"
GBOARD = "com.google.android.inputmethod.latin/.LatinIME"

COMPONENTES_DO_INSTAGRAM = (
    "com.instagram.android/com.instagram.share.handleractivity.ShareHandlerActivity\n"
    "com.instagram.android/com.instagram.share.handleractivity.ClipsShareHandlerActivity\n"
    "com.instagram.android/com.instagram.share.handleractivity.StoryShareHandlerActivity\n")


def png(largura=1080, altura=2400) -> bytes:
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (largura, altura), (22, 22, 26)).save(saida, "PNG")
    return saida.getvalue()


def no(rid="", texto="", desc="", classe="android.widget.Button", clicavel=True,
       caixa=(0, 0, 10, 10), filhos=()):
    return {"rid": rid, "texto": texto, "desc": desc, "classe": classe,
            "clicavel": clicavel, "caixa": caixa, "filhos": list(filhos)}


def tela_xml(nos, raiz=(0, 0, 1080, 2400), pacote="com.instagram.android"):
    def um(n):
        x1, y1, x2, y2 = n["caixa"]
        attrs = (f'text={quoteattr(n["texto"])} resource-id={quoteattr(n["rid"])} '
                 f'class={quoteattr(n["classe"])} package="{pacote}" '
                 f'content-desc={quoteattr(n["desc"])} clickable="{str(n["clicavel"]).lower()}" '
                 f'long-clickable="false" bounds="[{x1},{y1}][{x2},{y2}]"')
        return f"<node {attrs}>{''.join(um(f) for f in n['filhos'])}</node>"
    x1, y1, x2, y2 = raiz
    return (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
            f'<node text="" resource-id="" class="android.widget.FrameLayout" package="{pacote}" '
            f'content-desc="" clickable="false" long-clickable="false" '
            f'bounds="[{x1},{y1}][{x2},{y2}]">{"".join(um(n) for n in nos)}</node></hierarchy>')


IG = "com.instagram.android"
AVANCAR = no(rid=f"{IG}:id/next_button", classe="android.widget.FrameLayout",
             caixa=(880, 100, 1060, 180),
             filhos=[no(texto="Avançar", classe="android.widget.TextView", clicavel=False,
                        caixa=(900, 110, 1040, 170))])
LEGENDA = no(rid=f"{IG}:id/caption_input", texto="Escreva uma legenda...",
             classe="android.widget.EditText", caixa=(40, 300, 1040, 500))
COMPARTILHAR = no(rid=f"{IG}:id/share_button", texto="Compartilhar",
                  caixa=(40, 2200, 1040, 2320))
FEED = no(rid=f"{IG}:id/feed_tab", desc="Página inicial", caixa=(0, 2300, 200, 2400))


class CelularComTelas:
    """O fluxo de post de um app como o Instagram, por tras do adb falso: o
    `am start` abre o editor, cada `input tap` segue as transicoes, o
    ADBKeyBoard digita no campo, e a galeria responde o id do video."""

    def __init__(self, aparelho: AparelhoFalso, adbkeyboard: bool = True,
                 versao: str = "312.0.0.39.120", bloqueado: bool = False):
        self.ap = aparelho
        self.telas = {"editor": [AVANCAR], "legenda": [LEGENDA, COMPARTILHAR], "feed": [FEED],
                      "inicio": [no(rid="com.android.launcher:id/x", desc="Apps",
                                    caixa=(400, 2200, 680, 2300))]}
        self.transicoes = {("editor", AVANCAR["rid"]): "legenda",
                           ("legenda", COMPARTILHAR["rid"]): "feed"}
        self.atual = "inicio"
        self.digitado = ""
        self.teclado = GBOARD
        self.tocados = []
        self.aberturas = []
        self.adbkeyboard = adbkeyboard
        self.versao = versao
        self.bloqueado = bloqueado
        self._png = png()
        a = aparelho
        a.responder(r"^uiautomator dump", lambda c, m: self.xml())
        a.responder(r"^screencap -p$", lambda c, m: self._png)
        a.responder(r"^input tap (\d+) (\d+)$", self._tocar)
        a.responder(r"^input keyevent (\S+)$", self._tecla)
        a.responder(r"^dumpsys window", lambda c, m: f"    mKeyguardShowing={'true' if self.bloqueado else 'false'}\n")
        a.responder(r"^pm list packages", lambda c, m: self._pacotes())
        a.responder(r"^dumpsys package (\S+)", lambda c, m: f"    versionName={self.versao}\n")
        a.responder(r"^cmd package query-activities", COMPONENTES_DO_INSTAGRAM)
        a.responder(r"^content query", "Row: 0 _id=77\n")
        a.responder(r"^am start -a android\.intent\.action\.SEND", self._abrir)
        a.responder(r"^settings get secure default_input_method", lambda c, m: self.teclado + "\n")
        a.responder(r"^ime set '([^']+)'", self._ime)
        a.responder(r"^am broadcast -a ADB_INPUT_B64 --es msg '([^']+)'", self._digitar)
        a.responder(r"^am broadcast -a ADB_CLEAR_TEXT", self._limpar)

    def _pacotes(self):
        pacotes = ["com.android.chrome", IG] + (["com.android.adbkeyboard"] if self.adbkeyboard else [])
        return "".join(f"package:{p}\n" for p in pacotes)

    def xml(self):
        nos = []
        for n in self.telas[self.atual]:
            n = dict(n)
            if n["classe"].endswith("EditText") and self.digitado:
                n["texto"] = self.digitado
            nos.append(n)
        return tela_xml(nos)

    def _abrir(self, comando, m):
        self.aberturas.append(comando)
        self.atual = "editor"
        self.digitado = ""
        return "Starting: Intent { act=android.intent.action.SEND }\n"

    def _tocar(self, comando, m):
        import frota_roteiro
        tela = frota_roteiro.ler(self.xml())
        alvo = frota_roteiro.no_no_ponto(tela, int(m.group(1)), int(m.group(2)))
        if alvo is None:
            return ""
        self.tocados.append(alvo.rid or alvo.rotulo)
        self.atual = self.transicoes.get((self.atual, alvo.rid), self.atual)
        return ""

    def _tecla(self, comando, m):
        if m.group(1) == "KEYCODE_BACK" and self.atual == "legenda":
            self.atual = "editor"
        if m.group(1) == "KEYCODE_HOME":
            self.atual = "inicio"
        return ""

    def _ime(self, comando, m):
        self.teclado = m.group(1)
        return ""

    def _digitar(self, comando, m):
        if self.teclado == ADBKEYBOARD:
            self.digitado += base64.b64decode(m.group(1)).decode("utf-8")
        return ""

    def _limpar(self, comando, m):
        if self.teclado == ADBKEYBOARD:
            self.digitado = ""
        return ""
