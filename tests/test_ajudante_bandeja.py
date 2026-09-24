"""A logica do ajudante (`ajudante/ajudante.py`), sem Windows (Fase 6.2).

A bandeja e o registro sao do Windows e ficam de fora; o que decide -- subir
ou nao o motor, com que variaveis, e o que fazer quando o Docker ja atende --
e stdlib pura, e e aqui que um erro custaria caro: subir um segundo motor por
cima do Docker do autor, ou o whisper pedindo a placa sem as DLLs dela.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ajudante"))

import ajudante as aj  # noqa: E402


# --- caminhos -----------------------------------------------------------------

def test_mora_no_localappdata_e_os_dados_ficam_fora_do_codigo(tmp_path):
    c = aj.caminhos_padrao({"LOCALAPPDATA": str(tmp_path)})
    assert c.base == tmp_path / "Cortes"
    # A atualizacao troca `motor/` inteira: os dados nao podem morar dentro.
    assert c.motor not in c.dados.parents and c.dados not in c.motor.parents
    assert aj.caminhos_padrao({"CORTES_BASE": str(tmp_path / "x")}).base == tmp_path / "x"


# --- placa --------------------------------------------------------------------

def _roda(returncode=0, stdout="", erro=None):
    def executar(*a, **kw):
        if erro:
            raise erro
        return SimpleNamespace(returncode=returncode, stdout=stdout)
    return executar


@pytest.mark.parametrize("executar, esperado", [
    (_roda(0, "GPU 0: NVIDIA GeForce RTX 3060 (UUID: GPU-x)"), True),
    (_roda(0, "No devices were found"), False),
    (_roda(9, ""), False),
    (_roda(erro=FileNotFoundError()), False),  # sem driver, sem nvidia-smi
])
def test_placa_pelo_nvidia_smi(executar, esperado):
    assert aj.tem_placa_nvidia(executar) is esperado


def _com_libs(c):
    for nome in ("cublas", "cudnn"):
        (c.venv / "Lib" / "site-packages" / "nvidia" / nome / "bin").mkdir(parents=True)


def test_com_placa_e_libs_o_whisper_vai_para_a_placa(tmp_path):
    c = aj.Caminhos(tmp_path)
    _com_libs(c)
    env = aj.ambiente_do_motor(c, True, {"PATH": "/sistema"})
    assert (env["WHISPER_DEVICE"], env["WHISPER_COMPUTE"]) == ("cuda", "float16")
    assert env["WHISPER_MODEL"] == "large-v3-turbo"
    assert env["FFMPEG_ENCODER"] == "auto"
    partes = env["PATH"].split(aj.os.pathsep)
    assert partes[0] == str(c.bin)
    assert any(p.endswith("cublas" + aj.os.sep + "bin") for p in partes)
    assert partes[-1] == "/sistema"


def test_com_placa_sem_libs_o_whisper_fica_na_cpu(tmp_path):
    """Pedir `cuda` sem as DLLs faria cada job tentar, falhar e so entao cair.
    O NVENC continua: ele so precisa do driver."""
    env = aj.ambiente_do_motor(aj.Caminhos(tmp_path), True, {})
    assert (env["WHISPER_DEVICE"], env["WHISPER_COMPUTE"]) == ("cpu", "int8")
    assert env["FFMPEG_ENCODER"] == "auto"


def test_sem_placa_tudo_na_cpu(tmp_path):
    env = aj.ambiente_do_motor(aj.Caminhos(tmp_path), False, {})
    assert (env["WHISPER_DEVICE"], env["WHISPER_MODEL"]) == ("cpu", "small")
    assert env["FFMPEG_ENCODER"] == "x264"


def test_as_pastas_de_trabalho_ficam_nos_dados(tmp_path):
    c = aj.Caminhos(tmp_path)
    env = aj.ambiente_do_motor(c, False, {})
    for chave in ("OUTPUT_DIR", "UPLOAD_DIR", "DATA_DIR", "HF_HOME"):
        assert Path(env[chave]).parent == c.dados, chave
    assert env["PYTHONUTF8"] == "1"


def test_o_env_da_pessoa_vence(tmp_path):
    c = aj.Caminhos(tmp_path)
    c.dados.mkdir(parents=True)
    (c.dados / ".env").write_text(
        "# comentario\nWHISPER_MODEL=medium\nGROQ_API_KEY=\"gsk_x\"\nlinha solta\n",
        encoding="utf-8")
    pessoa = aj.ler_env_da_pessoa(c)
    assert pessoa == {"WHISPER_MODEL": "medium", "GROQ_API_KEY": "gsk_x"}
    env = aj.ambiente_do_motor(c, False, {}, pessoa)
    assert env["WHISPER_MODEL"] == "medium"
    assert aj.ler_env_da_pessoa(aj.Caminhos(tmp_path / "nada")) == {}


# --- quem atende a porta -------------------------------------------------------

def _servidor(corpo: bytes, status=200):
    class T(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass
    s = ThreadingHTTPServer(("127.0.0.1", 0), T)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def test_quem_atende_a_porta():
    motor = _servidor(json.dumps({"billingEnabled": False, "authAtiva": False}).encode())
    outro = _servidor(b"<html>outro programa</html>")
    try:
        assert aj.quem_atende(motor.server_port) == aj.MOTOR
        assert aj.quem_atende(outro.server_port) == aj.OUTRO
    finally:
        for s in (motor, outro):
            s.shutdown()
            s.server_close()  # sem fechar, o socket ainda aceita conexao
    assert aj.quem_atende(motor.server_port) == aj.LIVRE


# --- a decisao -----------------------------------------------------------------

class _MotorFalso:
    def __init__(self):
        self.vivo_ = False
        self.subidas = 0

    def vivo(self):
        return self.vivo_

    def iniciar(self):
        self.subidas += 1
        self.vivo_ = True


class _Mundo:
    def __init__(self):
        self.porta = aj.LIVRE
        self.agora = 1000.0


def _ajudante():
    motor, mundo = _MotorFalso(), _Mundo()
    a = aj.Ajudante(motor, quem_atende_fn=lambda: mundo.porta, relogio=lambda: mundo.agora)
    return a, motor, mundo


def test_porta_livre_sobe_o_motor_e_fica_pronto():
    a, motor, mundo = _ajudante()
    assert a.passo() == aj.INICIANDO and motor.subidas == 1
    mundo.porta = aj.MOTOR  # o nosso respondeu
    assert a.passo() == aj.PRONTO
    assert motor.subidas == 1


def test_com_o_docker_atendendo_o_ajudante_nao_sobe_nada():
    a, motor, mundo = _ajudante()
    mundo.porta = aj.MOTOR
    for _ in range(5):
        assert a.passo() == aj.DOCKER
    assert motor.subidas == 0
    # O autor desliga o Docker: na volta seguinte, o ajudante assume.
    mundo.porta = aj.LIVRE
    assert a.passo() == aj.INICIANDO and motor.subidas == 1


def test_porta_ocupada_por_outro_programa():
    a, motor, mundo = _ajudante()
    mundo.porta = aj.OUTRO
    assert a.passo() == aj.OCUPADA and motor.subidas == 0


def test_motor_que_morre_volta_com_espera_crescente():
    a, motor, mundo = _ajudante()
    a.passo()
    motor.vivo_ = False                 # morreu
    assert a.passo() == aj.ERRO         # espera antes de tentar de novo
    assert motor.subidas == 1
    mundo.agora += aj.ESPERAS_APOS_FALHA_S[0] + 0.1
    assert a.passo() == aj.INICIANDO and motor.subidas == 2
    motor.vivo_ = False                 # morreu de novo: espera maior
    assert a.passo() == aj.ERRO
    mundo.agora += aj.ESPERAS_APOS_FALHA_S[0] + 0.1
    assert a.passo() == aj.ERRO
    mundo.agora += aj.ESPERAS_APOS_FALHA_S[1]
    assert a.passo() == aj.INICIANDO and motor.subidas == 3


def test_ficar_pronto_zera_as_falhas():
    a, motor, mundo = _ajudante()
    a.passo()
    motor.vivo_ = False
    a.passo()
    mundo.agora += 100
    a.passo()
    mundo.porta = aj.MOTOR
    assert a.passo() == aj.PRONTO and a.falhas == 0


# --- o resto ------------------------------------------------------------------

def test_log_grande_vira_o_anterior(tmp_path):
    log = tmp_path / "motor.log"
    log.write_bytes(b"x" * (aj.LOG_MAXIMO + 1))
    aj.girar_log(log)
    assert not log.exists() and (tmp_path / "motor.log.1").exists()
    log.write_text("pequeno")
    aj.girar_log(log)
    assert log.exists()


def test_o_motor_so_escuta_nesta_maquina():
    """127.0.0.1 e nunca 0.0.0.0: no computador de um amigo, o motor aberto
    para a rede seria o Cortes dele para qualquer um do Wi-Fi."""
    fonte = (RAIZ / "ajudante" / "ajudante.py").read_text(encoding="utf-8")
    assert '"--host", "127.0.0.1"' in fonte
    assert "0.0.0.0" not in fonte


def test_a_bandeja_so_importa_o_que_e_do_windows_na_hora():
    """O CI de Linux importa o modulo: pystray e winreg no topo o quebrariam."""
    fonte = (RAIZ / "ajudante" / "ajudante.py").read_text(encoding="utf-8")
    topo = fonte.split("\nclass ", 1)[0]
    assert "import pystray" not in topo and "import winreg" not in topo


# --- parar (o desinstalador) ----------------------------------------------------

def test_parar_deixa_a_marca_que_o_ajudante_consome(tmp_path):
    c = aj.Caminhos(tmp_path)
    consumida = []

    def ajudante_rodando():
        while not consumida:
            if aj.pedido_de_parar(c):
                consumida.append(True)
            aj.time.sleep(0.05)

    t = threading.Thread(target=ajudante_rodando, daemon=True)
    t.start()
    assert aj.pedir_para_parar(c, prazo_s=5, rodando=lambda: True) == 0
    t.join(2)
    assert consumida and not (c.dados / ".parar").exists()


def test_parar_sem_ajudante_rodando_sai_na_hora_e_sem_lixo(tmp_path):
    """Sem ninguem para consumir a marca, ela nao pode ficar (o proximo
    ajudante que subisse se desligaria sozinho), e nem vale esperar o prazo
    -- a desinstalacao inteira ficaria 40 s parada."""
    c = aj.Caminhos(tmp_path)
    inicio = aj.time.monotonic()
    assert aj.pedir_para_parar(c, prazo_s=30, rodando=lambda: False) == 0
    assert aj.time.monotonic() - inicio < 1
    assert not (c.dados / ".parar").exists()


def test_parar_quando_o_ajudante_some_sem_consumir(tmp_path):
    c = aj.Caminhos(tmp_path)
    assert aj.pedir_para_parar(c, prazo_s=0.2, rodando=lambda: True) == 0
    assert not (c.dados / ".parar").exists()
