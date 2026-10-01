"""Um aparelho da frota: ler o estado, pôr o video no app e tocar na tela --
etapa 7.9 (ADR-016).

Fala com o celular pelo servidor do adb (`adb_cliente`). Tudo aqui e uma acao
no aparelho ou a leitura do que ele respondeu; decidir QUANDO e POR QUE agir e
do `frota.py` (as regras da frota) e do driver (`publishers/aparelho.py`).

**As leituras sao funcoes puras sobre o texto que o Android devolve**
(`ler_estado`, `escolher_tela`, `ler_id_da_midia`...): o formato muda entre
versoes do Android, e e assim que o CI cobre cada variacao sem celular.

**O video entra no app como entra pelo "compartilhar" da galeria**: vai para
`Movies/Virtu Clips`, a galeria o indexa, e o app abre com ele pela intencao de
compartilhar. Qual tela do app recebe e perguntado ao aparelho, nunca escrito a
mao -- o nome muda de versao para versao do app.

**Nada aqui disfarça o aparelho**: nao muda identificador, rede, localizacao
nem configuracao do Android (ADR-016, "o que fica de fora"). As unicas mudancas
sao o teclado, trocado pelo ADBKeyBoard so enquanto a legenda e digitada e
devolvido logo depois, e os arquivos da pasta `Virtu Clips`.
"""
from __future__ import annotations

import base64
import re
import threading
import time
from contextlib import contextmanager
from typing import Optional
from urllib.parse import quote

import adb_cliente
import plataformas
from adb_cliente import AdbErro, aspas

#: Onde os cortes ficam no aparelho. `Movies` e uma pasta que toda galeria le.
PASTA_DOS_VIDEOS = "/sdcard/Movies/Virtu Clips"
#: Onde vai o `.txt` com a legenda, para a pessoa copiar no modo de entrega.
PASTA_DOS_TEXTOS = "/sdcard/Download/Virtu Clips"
#: Os arquivos da pasta com mais dias que isto saem. Nao antes: o app pode
#: ainda estar lendo o video de um post que acabou de sair.
DIAS_NA_PASTA = 3

#: O teclado que digita acento e emoji (ADBKeyBoard, GPL-2.0, instalado por
#: quem usa). O `input text` do Android nao escreve nenhum dos dois.
ADBKEYBOARD = "com.android.adbkeyboard/.AdbIME"
PACOTE_DO_ADBKEYBOARD = "com.android.adbkeyboard"

#: O `am broadcast` leva o texto em base64, em pedacos: o pedido ao adbd tem
#: teto (4 KiB nos Android antigos), e a legenda do Instagram vai a 2.200
#: caracteres.
BYTES_POR_PEDACO = 600

#: Onde o `uiautomator` grava a leitura da tela: fora do armazenamento
#: compartilhado, que e o que o shell do adb escreve sem permissao nenhuma.
ARQUIVO_DA_TELA = "/data/local/tmp/vc-tela.xml"

TECLAS = {
    "voltar": "KEYCODE_BACK",
    "inicio": "KEYCODE_HOME",
    "acordar": "KEYCODE_WAKEUP",
    "recentes": "KEYCODE_APP_SWITCH",
}

#: Todo pacote que o estado pergunta a versao: os apps das plataformas e o
#: teclado.
PACOTES_CONHECIDOS = tuple(app for p in plataformas.TODAS for app in p.apps) + (
    PACOTE_DO_ADBKEYBOARD,)


def _dormir(segundos: float) -> None:
    """As esperas pelo aparelho, num nome que o teste troca."""
    time.sleep(segundos)


class AparelhoErro(AdbErro):
    """O aparelho nao fez o que se pediu: a mensagem diz o que olhar nele."""


# --------------------------------------------------------------------------- #
# Uma coisa de cada vez por aparelho
# --------------------------------------------------------------------------- #

_TRAVAS: dict[str, threading.Lock] = {}
_TRAVA_DAS_TRAVAS = threading.Lock()
_OCUPADO_COM: dict[str, str] = {}


def _trava(serial: str) -> threading.Lock:
    with _TRAVA_DAS_TRAVAS:
        return _TRAVAS.setdefault(serial, threading.Lock())


class Ocupado(AparelhoErro):
    """O aparelho ja esta fazendo outra coisa (publicando, ensinando, ensaiando)."""


def reservar(serial: str, motivo: str, espera_s: float = 0.0) -> None:
    """Toma o aparelho para uma tarefa que atravessa varios pedidos do painel
    (o ensino). Quem reserva libera (`liberar`)."""
    trava = _trava(serial)
    pegou = trava.acquire(timeout=espera_s) if espera_s > 0 else trava.acquire(blocking=False)
    if not pegou:
        raise Ocupado(f"o aparelho está ocupado: {_OCUPADO_COM.get(serial, 'outra tarefa')}")
    _OCUPADO_COM[serial] = motivo


def liberar(serial: str) -> None:
    _OCUPADO_COM.pop(serial, None)
    try:
        _trava(serial).release()
    except RuntimeError:
        pass


@contextmanager
def ocupar(serial: str, motivo: str, espera_s: float = 0.0):
    """Um aparelho faz uma coisa de cada vez (ADR-016): um post no meio de um
    ensino tocaria na tela do outro."""
    reservar(serial, motivo, espera_s)
    try:
        yield
    finally:
        liberar(serial)


def ocupado_com(serial: str) -> Optional[str]:
    return _OCUPADO_COM.get(serial)


# --------------------------------------------------------------------------- #
# As leituras (puras)
# --------------------------------------------------------------------------- #

def _secoes(texto: str) -> dict[str, str]:
    """Divide a saida do script de estado pelos marcadores `@@nome`."""
    secoes, atual, linhas = {}, None, []
    for linha in (texto or "").splitlines():
        if linha.startswith("@@") and " " not in linha.strip():
            if atual:
                secoes[atual] = "\n".join(linhas)
            atual, linhas = linha.strip()[2:], []
        else:
            linhas.append(linha)
    if atual:
        secoes[atual] = "\n".join(linhas)
    return secoes


def ler_bateria(texto: str) -> dict:
    nivel = re.search(r"^\s*level:\s*(\d+)", texto or "", re.M)
    status = re.search(r"^\s*status:\s*(\d+)", texto or "", re.M)
    na_tomada = any(re.search(rf"^\s*{fonte} powered:\s*true", texto or "", re.M)
                    for fonte in ("AC", "USB", "Wireless", "Dock"))
    return {
        "nivel": int(nivel.group(1)) if nivel else None,
        # 2 = carregando, 5 = cheia (BatteryManager.BATTERY_STATUS_*).
        "carregando": (status.group(1) in ("2", "5")) if status else na_tomada,
        "na_tomada": na_tomada,
    }


def ler_tela_ligada(texto: str) -> Optional[bool]:
    m = re.search(r"mWakefulness=(\w+)", texto or "")
    if m:
        return m.group(1) == "Awake"
    m = re.search(r"Display Power: state=(\w+)", texto or "")
    if m:
        return m.group(1).upper() == "ON"
    return None


def ler_bloqueio(texto: str) -> Optional[bool]:
    """A tela de bloqueio esta na frente? As chaves mudam entre versoes do
    Android, e nenhuma resposta e "nao sei" -- nunca "desbloqueado"."""
    achados = re.findall(r"(mKeyguardShowing|mShowingLockscreen|isKeyguardShowing|"
                         r"mDreamingLockscreen)=(true|false)", texto or "", re.I)
    if not achados:
        return None
    return any(valor.lower() == "true" for _chave, valor in achados)


def ler_espaco_livre_mb(linha: str) -> Optional[int]:
    """A ultima linha do `df -k /sdcard`: o quarto campo e o livre, em KiB."""
    partes = (linha or "").split()
    if len(partes) >= 4 and partes[3].isdigit():
        return int(partes[3]) // 1024
    return None


def ler_pacotes(texto: str) -> set[str]:
    return {linha.strip()[len("package:"):] for linha in (texto or "").splitlines()
            if linha.strip().startswith("package:")}


def ler_versoes(texto: str) -> dict[str, str]:
    """Linhas `@@v <pacote> versionName=1.2.3`."""
    versoes = {}
    for linha in (texto or "").splitlines():
        m = re.match(r"^\s*(\S+)\s+versionName=(\S+)", linha)
        if m:
            versoes[m.group(1)] = m.group(2)
    return versoes


def ler_tamanho(texto: str) -> Optional[tuple[int, int]]:
    """`wm size`: o tamanho em uso (o "Override", quando alguem mudou)."""
    m = (re.search(r"Override size:\s*(\d+)x(\d+)", texto or "")
         or re.search(r"Physical size:\s*(\d+)x(\d+)", texto or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def ler_estado(texto: str) -> dict:
    """A saida do `SCRIPT_DO_ESTADO`, lida."""
    s = _secoes(texto)
    props = (s.get("props") or "").splitlines() + [""] * 5
    fabricante, modelo, versao, sdk, serie = (p.strip() for p in props[:5])
    pacotes = ler_pacotes(s.get("pacotes", ""))
    versoes = ler_versoes(s.get("versoes", ""))
    apps = {}
    for p in plataformas.TODAS:
        instalado = next((app for app in p.apps if app in pacotes), None)
        if instalado:
            apps[p.id] = {"pacote": instalado, "versao": versoes.get(instalado)}
    teclado = (s.get("teclado") or "").strip()
    return {
        "fabricante": fabricante or None,
        "modelo": modelo or None,
        "android": versao or None,
        "sdk": int(sdk) if sdk.isdigit() else None,
        "numero_de_serie": serie or None,
        "bateria": ler_bateria(s.get("bateria", "")),
        "tela_ligada": ler_tela_ligada(s.get("energia", "")),
        "bloqueado": ler_bloqueio(s.get("bloqueio", "")),
        "espaco_livre_mb": ler_espaco_livre_mb((s.get("espaco") or "").strip()),
        "apps": apps,
        "adbkeyboard": PACOTE_DO_ADBKEYBOARD in pacotes,
        "teclado": teclado if teclado and teclado != "null" else None,
        "tela": ler_tamanho(s.get("tamanho", "")),
    }


def ler_telas_de_compartilhar(texto: str, pacote: str) -> list[str]:
    """Os componentes (`pacote/classe`) que o `query-activities` listou."""
    achados = []
    for linha in (texto or "").splitlines():
        m = re.search(rf"\b({re.escape(pacote)}/[\w.$]+)", linha)
        if m and m.group(1) not in achados:
            achados.append(m.group(1))
    return achados


def escolher_tela(componentes: list[str], plataforma: str) -> Optional[str]:
    """Qual tela do app recebe o corte. A preferida da plataforma (os Reels do
    Instagram); senao, a unica que sobra depois de tirar as que nunca servem
    (Stories, Direct). Mais de uma sobrando: None, e o Android pergunta -- quem
    esta na frente do aparelho escolhe, e o automatico nao chuta."""
    regra = plataformas.de(plataforma)
    if regra is None or not componentes:
        return None
    classe = lambda c: c.split("/", 1)[1]
    if regra.tela_preferida:
        for c in componentes:
            if re.search(regra.tela_preferida, classe(c), re.I):
                return c
    sobram = [c for c in componentes
              if not (regra.telas_evitadas and re.search(regra.telas_evitadas, classe(c), re.I))]
    return sobram[0] if len(sobram) == 1 else None


def ler_id_da_midia(texto: str) -> Optional[str]:
    """`content query`: "Row: 0 _id=1234"."""
    m = re.search(r"\b_id=(\d+)", texto or "")
    return m.group(1) if m else None


def ler_app_em_frente(texto: str) -> Optional[str]:
    """O pacote da tela em uso, pelo `dumpsys activity activities`."""
    m = re.search(r"(?:mResumedActivity|topResumedActivity|ResumedActivity)[:=]\s*"
                  r"ActivityRecord\{\S+\s+\S+\s+([\w.]+)/", texto or "")
    return m.group(1) if m else None


def pedacos_do_texto(texto: str, maximo: int = BYTES_POR_PEDACO) -> list[str]:
    """O texto em pedacos de ate `maximo` bytes de UTF-8, sem partir um
    caractere no meio, ja em base64 -- o que o ADBKeyBoard recebe."""
    pedacos, atual = [], ""
    for ch in texto or "":
        if len((atual + ch).encode("utf-8")) > maximo:
            pedacos.append(atual)
            atual = ""
        atual += ch
    if atual:
        pedacos.append(atual)
    return [base64.b64encode(p.encode("utf-8")).decode("ascii") for p in pedacos]


def nome_no_aparelho(base: str, sufixo: str) -> str:
    """Um nome so com letra, numero e hifen: vai para o shell do aparelho e para
    a consulta da galeria, e nenhum dos dois precisa de aspas assim."""
    limpo = re.sub(r"[^a-z0-9-]+", "-", (base or "").lower()).strip("-")[:40] or "corte"
    return f"vc-{limpo}{sufixo}"


# --------------------------------------------------------------------------- #
# O aparelho
# --------------------------------------------------------------------------- #

def _script_do_estado() -> str:
    pacotes = " ".join(PACOTES_CONHECIDOS)
    return (
        'echo "@@props"; getprop ro.product.manufacturer; getprop ro.product.model; '
        'getprop ro.build.version.release; getprop ro.build.version.sdk; getprop ro.serialno; '
        'echo "@@bateria"; dumpsys battery 2>/dev/null; '
        'echo "@@energia"; dumpsys power 2>/dev/null | grep -E "mWakefulness=|Display Power: state="; '
        'echo "@@bloqueio"; dumpsys window 2>/dev/null | grep -iE '
        '"mKeyguardShowing|mShowingLockscreen|isKeyguardShowing|mDreamingLockscreen"; '
        'echo "@@espaco"; df -k /sdcard 2>/dev/null | tail -n 1; '
        'echo "@@pacotes"; INST=$(pm list packages 2>/dev/null); echo "$INST"; '
        f'echo "@@versoes"; for p in {pacotes}; do '
        'if echo "$INST" | grep -qx "package:$p"; then '
        'echo "$p $(dumpsys package $p 2>/dev/null | grep -m1 versionName)"; fi; done; '
        'echo "@@teclado"; settings get secure default_input_method 2>/dev/null; '
        'echo "@@tamanho"; wm size 2>/dev/null; '
        'echo "@@fim"'
    )


class Aparelho:
    """Um celular, pelo serial que o servidor do adb da a ele."""

    def __init__(self, serial: str, cliente: Optional[adb_cliente.Cliente] = None):
        if not adb_cliente.serial_valido(serial):
            raise AparelhoErro(f"serial inválido: {serial!r}")
        self.serial = serial
        self.adb = cliente or adb_cliente.Cliente()

    # -- comandos ----------------------------------------------------------- #

    def sh(self, comando: str, timeout: float = 30) -> str:
        return self.adb.executar(self.serial, comando, timeout).decode("utf-8", "replace")

    def sh_ok(self, comando: str, timeout: float = 30) -> str:
        saida, codigo = self.adb.executar_texto(self.serial, comando, timeout)
        if codigo not in (0, None):
            raise AparelhoErro(f"o aparelho recusou ({codigo}): {saida.strip()[-200:]}")
        return saida

    # -- estado ------------------------------------------------------------- #

    def estado(self) -> dict:
        return ler_estado(self.sh(_script_do_estado(), timeout=45))

    def tela_png(self) -> bytes:
        dados = self.adb.executar(self.serial, "screencap -p", timeout=30)
        if not dados.startswith(b"\x89PNG"):
            raise AparelhoErro("o aparelho não devolveu a imagem da tela")
        return dados

    def ler_tela(self) -> str:
        """O XML do `uiautomator dump`. O `--compressed` primeiro: sem ele o
        dump espera a tela parar, e com um video tocando no editor ela nunca
        para (mobile-next/mobilewright#117)."""
        for extra in ("--compressed ", ""):
            xml = self.sh(f"uiautomator dump {extra}{ARQUIVO_DA_TELA} >/dev/null 2>&1; "
                          f"cat {ARQUIVO_DA_TELA} 2>/dev/null; rm -f {ARQUIVO_DA_TELA}",
                          timeout=40)
            inicio = xml.find("<?xml")
            if inicio >= 0 and "</hierarchy>" in xml:
                return xml[inicio:xml.rindex("</hierarchy>") + len("</hierarchy>")]
        raise AparelhoErro("não consegui ler a tela do aparelho (uiautomator)")

    def app_em_frente(self) -> Optional[str]:
        return ler_app_em_frente(self.sh(
            "dumpsys activity activities 2>/dev/null | grep -E "
            "'mResumedActivity|topResumedActivity|ResumedActivity' | head -n 3"))

    def versao_do_app(self, pacote: str) -> Optional[str]:
        m = re.search(r"versionName=(\S+)", self.sh(
            f"dumpsys package {aspas(pacote)} 2>/dev/null | grep -m1 versionName"))
        return m.group(1) if m else None

    # -- tela --------------------------------------------------------------- #

    def tocar(self, x: int, y: int) -> None:
        self.sh_ok(f"input tap {int(x)} {int(y)}")

    def tecla(self, nome: str) -> None:
        if nome not in TECLAS:
            raise AparelhoErro(f"tecla desconhecida: {nome}")
        self.sh_ok(f"input keyevent {TECLAS[nome]}")

    def acordar(self) -> Optional[bool]:
        """Acende a tela e diz se a tela de bloqueio ficou na frente. Com senha,
        o motor nao desbloqueia: nao e para isso que ele existe."""
        self.tecla("acordar")
        self.sh("wm dismiss-keyguard >/dev/null 2>&1")
        _dormir(0.6)
        return ler_bloqueio(self.sh(
            "dumpsys window 2>/dev/null | grep -iE "
            "'mKeyguardShowing|mShowingLockscreen|isKeyguardShowing|mDreamingLockscreen'"))

    # -- o video no app ----------------------------------------------------- #

    def por_na_galeria(self, origem: str, nome: str, espera_s: float = 15.0) -> str:
        """Manda o video para `Movies/Virtu Clips` e devolve o endereco dele na
        galeria (`content://media/...`), que e o que o app sabe abrir."""
        self.sh_ok(f"mkdir -p {aspas(PASTA_DOS_VIDEOS)}")
        destino = f"{PASTA_DOS_VIDEOS}/{nome}"
        self.adb.enviar(self.serial, origem, destino, timeout=600)
        # Do Android 11 em diante, a galeria indexa sozinha o que chega pelo
        # armazenamento compartilhado; o aviso abaixo e para os de antes.
        uri_do_arquivo = "file://" + quote(destino)
        self.sh(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
                f"-d {aspas(uri_do_arquivo)} >/dev/null 2>&1")
        onde = f"_display_name='{nome}'"
        consulta = (f"content query --uri content://media/external/video/media "
                    f"--projection _id --where {aspas(onde)}")
        limite = time.monotonic() + espera_s
        while True:
            midia = ler_id_da_midia(self.sh(consulta))
            if midia:
                return f"content://media/external/video/media/{midia}"
            if time.monotonic() >= limite:
                raise AparelhoErro("o vídeo chegou ao aparelho, mas a galeria não o "
                                   "mostrou (a pasta Movies/Virtu Clips existe?)")
            _dormir(1.0)

    def escrever_texto(self, nome: str, texto: str) -> str:
        """O `.txt` com a legenda, em `Download/Virtu Clips`, para copiar."""
        self.sh_ok(f"mkdir -p {aspas(PASTA_DOS_TEXTOS)}")
        destino = f"{PASTA_DOS_TEXTOS}/{nome}"
        self.adb.enviar_bytes(self.serial, (texto or "").encode("utf-8"), destino)
        return destino

    def telas_de_compartilhar(self, pacote: str) -> list[str]:
        return ler_telas_de_compartilhar(self.sh(
            f"cmd package query-activities --brief -a android.intent.action.SEND "
            f"-t video/mp4 {aspas(pacote)} 2>/dev/null"), pacote)

    def abrir_no_app(self, uri: str, pacote: str, componente: Optional[str]) -> None:
        """O app abre com o video, como pelo "compartilhar" da galeria. A tarefa
        dele e recomecada (`--activity-clear-task`): um post que parou no meio
        da ultima vez nao pode ser a tela em que este comeca. O app em si nao e
        parado -- um envio de antes pode estar subindo."""
        alvo = f"-n {aspas(componente)}" if componente else f"-p {aspas(pacote)}"
        saida = self.sh_ok(
            f"am start -a android.intent.action.SEND -t video/mp4 "
            f"--eu android.intent.extra.STREAM {aspas(uri)} --grant-read-uri-permission "
            f"--activity-clear-task {alvo}")
        if "Error" in saida:
            raise AparelhoErro(f"o app não abriu: {saida.strip()[-200:]}")

    def limpar_pasta(self) -> None:
        """Tira da pasta os videos e textos com mais de `DIAS_NA_PASTA` dias."""
        for pasta in (PASTA_DOS_VIDEOS, PASTA_DOS_TEXTOS):
            self.sh(f"find {aspas(pasta)} -type f -mtime +{DIAS_NA_PASTA} "
                    f"-exec rm -f {{}} + 2>/dev/null")

    def apagar(self, caminho: str) -> None:
        if not caminho.startswith((PASTA_DOS_VIDEOS + "/", PASTA_DOS_TEXTOS + "/")):
            raise AparelhoErro("o motor só apaga o que ele mesmo pôs no aparelho")
        self.sh(f"rm -f {aspas(caminho)}")

    # -- teclado ------------------------------------------------------------ #

    def teclado_atual(self) -> Optional[str]:
        valor = self.sh("settings get secure default_input_method 2>/dev/null").strip()
        return valor if valor and valor != "null" else None

    def tem_adbkeyboard(self) -> bool:
        return f"package:{PACOTE_DO_ADBKEYBOARD}" in self.sh(
            f"pm list packages {PACOTE_DO_ADBKEYBOARD} 2>/dev/null")

    def usar_teclado(self, ime: str) -> None:
        self.sh(f"ime enable {aspas(ime)} >/dev/null 2>&1")
        self.sh_ok(f"ime set {aspas(ime)}")

    def digitar(self, texto: str) -> None:
        """Digita pelo ADBKeyBoard, que tem de estar em uso (`usar_teclado`)."""
        for pedaco in pedacos_do_texto(texto):
            self.sh_ok(f"am broadcast -a ADB_INPUT_B64 --es msg {aspas(pedaco)} >/dev/null")

    def limpar_campo(self) -> None:
        self.sh_ok("am broadcast -a ADB_CLEAR_TEXT >/dev/null")


@contextmanager
def com_adbkeyboard(aparelho: Aparelho):
    """Usa o ADBKeyBoard so dentro do bloco, e devolve o teclado de antes
    aconteca o que acontecer: a pessoa nao pode achar o celular dela com um
    teclado sem teclas."""
    antes = aparelho.teclado_atual()
    aparelho.usar_teclado(ADBKEYBOARD)
    try:
        yield
    finally:
        if antes and antes != ADBKEYBOARD:
            try:
                aparelho.usar_teclado(antes)
            except AdbErro:
                pass
