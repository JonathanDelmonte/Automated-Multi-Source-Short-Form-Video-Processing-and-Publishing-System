"""O cliente do servidor do adb (etapa 7.9, ADR-016), contra um servidor falso
que fala o mesmo protocolo pelo socket de verdade."""
import os

import pytest

import adb_cliente
from adb_cliente import AdbErro, AdbForaDoAr, Cliente
from adb_falso import AparelhoFalso, ServidorFalso


@pytest.fixture
def servidor():
    with ServidorFalso() as s:
        yield s


def cliente(s):
    return Cliente("127.0.0.1", s.porta, timeout=5)


def test_versao_e_lista_de_aparelhos(servidor):
    servidor.acrescentar(AparelhoFalso("R58M12ABCDE", modelo="SM_G973U"))
    servidor.acrescentar(AparelhoFalso("192.168.0.5:5555", usb=False))
    servidor.acrescentar(AparelhoFalso("ZY22ABCDEF", estado="unauthorized"))
    c = cliente(servidor)
    assert c.versao() == 41
    lista = {a["serial"]: a for a in c.aparelhos()}
    assert lista["R58M12ABCDE"]["no_ar"] and lista["R58M12ABCDE"]["usb"]
    assert lista["R58M12ABCDE"]["modelo"] == "SM G973U"
    assert lista["192.168.0.5:5555"]["usb"] is False
    assert lista["ZY22ABCDEF"]["no_ar"] is False
    assert lista["ZY22ABCDEF"]["rotulo"] == "esperando autorizar"


def test_sem_servidor_e_fora_do_ar():
    c = Cliente("127.0.0.1", 1, timeout=1)
    with pytest.raises(AdbForaDoAr):
        c.versao()
    assert c.no_ar() is False


def test_estado_sem_permissao_tem_espacos():
    linhas = ("0123456789ABCDEF       no permissions (user in plugdev group; are your "
              "udev rules wrong?); see [http://developer.android.com/tools/device.html]\n")
    a = adb_cliente.ler_aparelhos(linhas)[0]
    assert a["estado"] == "no permissions" and a["rotulo"] == "sem permissão"


def test_executar_texto_devolve_o_codigo(servidor):
    servidor.acrescentar(AparelhoFalso("X1")).responder(
        r"^getprop ro\.product\.model$", ("Pixel 7\n", 0)).responder(
        r"^false$", ("", 1))
    c = cliente(servidor)
    assert c.executar_texto("X1", "getprop ro.product.model") == ("Pixel 7\n", 0)
    assert c.executar_texto("X1", "false")[1] == 1


def test_executar_devolve_bytes_intactos(servidor):
    png = bytes(range(256)) * 40 + b"\r\n\x00"
    servidor.acrescentar(AparelhoFalso("X1")).responder(r"^screencap -p$", png)
    assert cliente(servidor).executar("X1", "screencap -p") == png


def test_aparelho_desconhecido_e_erro_do_adb(servidor):
    with pytest.raises(AdbErro, match="not found"):
        cliente(servidor).executar("NAO-EXISTE", "true")


def test_aparelho_sem_autorizar_recusa_comando(servidor):
    servidor.acrescentar(AparelhoFalso("X1", estado="unauthorized"))
    with pytest.raises(AdbErro, match="unauthorized"):
        cliente(servidor).executar("X1", "true")


def test_enviar_arquivo(servidor, tmp_path):
    aparelho = servidor.acrescentar(AparelhoFalso("X1"))
    origem = tmp_path / "corte.mp4"
    conteudo = os.urandom(adb_cliente.PEDACO * 2 + 123)
    origem.write_bytes(conteudo)
    vistos = []
    n = cliente(servidor).enviar("X1", str(origem), "/sdcard/Movies/Virtu Clips/a.mp4",
                                 progresso=lambda feito, total: vistos.append((feito, total)))
    assert n == len(conteudo)
    assert aparelho.arquivos["/sdcard/Movies/Virtu Clips/a.mp4"] == conteudo
    assert vistos[-1] == (len(conteudo), len(conteudo))
    assert len(vistos) == 3  # tres pedacos: o protocolo recusa DATA acima de 64 KiB


def test_enviar_recusado_diz_o_motivo(servidor, tmp_path):
    servidor.acrescentar(AparelhoFalso("X1"))
    origem = tmp_path / "a.mp4"
    origem.write_bytes(b"x")
    with pytest.raises(AdbErro, match="Permission denied"):
        cliente(servidor).enviar("X1", str(origem), "/proibido/a.mp4")


def test_conectar_e_parear(servidor):
    servidor.conectaveis["192.168.0.9:5555"] = AparelhoFalso("192.168.0.9:5555", usb=False)
    c = cliente(servidor)
    assert c.conectar("192.168.0.9:5555") == (True, "connected to 192.168.0.9:5555")
    assert c.conectar("192.168.0.9:5555")[0] is True  # "already connected"
    ok, texto = c.conectar("10.0.0.1:5555")
    assert ok is False and "failed to connect" in texto
    assert c.parear("192.168.0.9:37123", "123456")[0] is True
    assert c.parear("192.168.0.9:37123", "654321")[0] is False
    assert "host:pair:123456:192.168.0.9:37123" in servidor.pedidos


@pytest.mark.parametrize("serial", ["R58M12ABCDE", "192.168.0.5:5555", "emulator-5554",
                                    "adb-R58M12ABCDE-AbCdEf._adb-tls-connect._tcp"])
def test_seriais_validos(serial):
    assert adb_cliente.serial_valido(serial)


@pytest.mark.parametrize("serial", ["", "a b", "x\nhost:kill", "a;rm", "a" * 300])
def test_seriais_invalidos_nunca_chegam_ao_servidor(serial, servidor):
    assert not adb_cliente.serial_valido(serial)
    with pytest.raises(AdbErro, match="serial inválido"):
        cliente(servidor).executar(serial, "true")
    assert servidor.pedidos == []


@pytest.mark.parametrize("endereco,ok", [
    ("192.168.0.5:5555", True), ("celular.local:37000", True), ("[fe80::1]:5555", True),
    ("192.168.0.5", False), ("192.168.0.5:0", False), ("192.168.0.5:70000", False),
    ("a b:5555", False), ("x:5555;host:kill", False),
])
def test_enderecos(endereco, ok):
    assert adb_cliente.endereco_valido(endereco) is ok


def test_codigo_de_pareamento():
    assert adb_cliente.codigo_valido("123456")
    for ruim in ("12345", "1234567", "abcdef", "12 456", ""):
        assert not adb_cliente.codigo_valido(ruim)


def test_aspas_e_um_argumento_so():
    assert adb_cliente.aspas("Virtu Clips") == "'Virtu Clips'"
    assert adb_cliente.aspas("a'b; rm -rf /") == "'a'\\''b; rm -rf /'"


@pytest.mark.parametrize("valor,esperado", [
    ("", None),
    ("host.docker.internal:5037", ("host.docker.internal", 5037)),
    ("192.168.0.10", ("192.168.0.10", 5037)),
    ("localhost:5038", ("localhost", 5038)),
    ("[::1]:5037", ("::1", 5037)),
    ("maquina:porta", ("maquina:porta", 5037)),
])
def test_endereco_do_servidor(valor, esperado, monkeypatch):
    if valor:
        monkeypatch.setenv("ADB_SERVER", valor)
    else:
        monkeypatch.delenv("ADB_SERVER", raising=False)
        monkeypatch.setattr(adb_cliente, "em_container", lambda: False)
        esperado = ("127.0.0.1", 5037)
    assert adb_cliente.endereco_padrao() == esperado


def test_no_docker_o_servidor_e_o_do_windows(monkeypatch):
    """O container fala com o adb do Windows pelo nome que o Docker Desktop
    encaminha ao loopback dele (ADR-016): o adb nao precisa abrir na rede."""
    monkeypatch.delenv("ADB_SERVER", raising=False)
    monkeypatch.setattr(adb_cliente, "em_container", lambda: True)
    assert adb_cliente.endereco_padrao() == ("host.docker.internal", 5037)


def test_no_docker_nao_tenta_ligar_o_adb(monkeypatch, tmp_path):
    adb = tmp_path / "adb"
    adb.write_text("")
    monkeypatch.setattr(adb_cliente, "em_container", lambda: True)
    assert adb_cliente.ligar_servidor(str(adb)) is False


def test_achar_adb_pela_variavel(monkeypatch, tmp_path):
    adb = tmp_path / ("adb.exe" if os.name == "nt" else "adb")
    adb.write_text("")
    monkeypatch.setenv("ADB_PATH", str(adb))
    assert adb_cliente.achar_adb() == str(adb)


def test_pedido_grande_demais_e_recusado():
    with pytest.raises(AdbErro, match="grande demais"):
        adb_cliente._pedido("x" * 70000)


def test_enviar_bytes(servidor):
    aparelho = servidor.acrescentar(AparelhoFalso("X1"))
    texto = "Legenda com acento e emoji 🎬\n#corte".encode("utf-8")
    assert cliente(servidor).enviar_bytes("X1", texto, "/sdcard/Download/a.txt") == len(texto)
    assert aparelho.arquivos["/sdcard/Download/a.txt"] == texto
