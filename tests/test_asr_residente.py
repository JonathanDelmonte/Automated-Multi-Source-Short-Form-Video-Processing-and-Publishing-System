"""O modelo de transcricao segurado na placa por um processo proprio (24-set-2026).

A regra que mais importa aqui e a da queda: qualquer duvida devolve `None`, e o
job carrega o modelo sozinho como sempre fez. Os testes do servidor rodam a
classe numa thread, com carga e decodificacao falsas; um teste final sobe o
PROCESSO de verdade, com um `faster_whisper` falso no caminho, porque um erro
de import no ponto de entrada so aparece ali.
"""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import asr_residente as ar
import transcribe_backends as tb

RAIZ = Path(__file__).resolve().parent.parent
CHAVE = ("large-v3-turbo", "cuda", "float16")

pytestmark = pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or os.name != "posix",
                                reason="socket de arquivo so existe em POSIX")


def _transcricao(n=1):
    return {"text": "ola", "language": "pt",
            "segments": [{"start": float(i), "end": i + 1.0, "text": " ola",
                          "words": [{"word": " ola", "start": float(i), "end": i + 0.5}]}
                         for i in range(n)]}


def _carregar_ok():
    return object(), "cuda", CHAVE, 0.01


def _decodificar_ok(modelo, dispositivo, arquivo, params, progresso):
    p = progresso(4.0)
    for pos in (1.0, 2.0, 3.0, 4.0):
        p.update(pos)
    return _transcricao(4)


@pytest.fixture
def residente(tmp_path, monkeypatch):
    """Sobe um `Servidor` numa thread; devolve (servidor, resultado do laco)."""
    caminho = str(tmp_path / "s" / "asr.sock")
    monkeypatch.setenv("ASR_RESIDENTE_SOCKET", caminho)
    subidos = []

    def subir(**kw):
        kw.setdefault("carregar", _carregar_ok)
        kw.setdefault("decodificar", _decodificar_ok)
        kw.setdefault("batida", 0.05)
        ocioso = kw.pop("ocioso", 60)
        s = ar.Servidor(caminho, ocioso, **kw)
        s.abrir()
        saida = []
        t = threading.Thread(target=lambda: saida.append(s.laco()), daemon=True)
        t.start()
        subidos.append((s, t))
        return s, t, saida

    yield subir
    for s, t in subidos:
        s.estado = "falhou"      # faz o laco sair na proxima volta
        t.join(3)
        s.fechar("fim do teste")


def _esperar(condicao, limite=3.0):
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return False


class TestLigado:
    @pytest.mark.parametrize("amb,esperado", [
        ({"WHISPER_DEVICE": "cuda"}, True),
        ({"WHISPER_DEVICE": "cuda:0"}, True),
        ({"WHISPER_DEVICE": "cpu"}, False),
        ({"WHISPER_DEVICE": "cuda", "TRANSCRIBE_BACKEND": "parakeet"}, False),
        ({"WHISPER_DEVICE": "cuda", "ASR_RESIDENTE": "0"}, False),
        ({"WHISPER_DEVICE": "cpu", "ASR_RESIDENTE": "1"}, True),
    ])
    def test_auto_so_com_whisper_na_placa(self, monkeypatch, amb, esperado):
        for k in ("WHISPER_DEVICE", "TRANSCRIBE_BACKEND", "ASR_RESIDENTE"):
            monkeypatch.delenv(k, raising=False)
        for k, v in amb.items():
            monkeypatch.setenv(k, v)
        assert ar.ativo() is esperado

    @pytest.mark.parametrize("valor,esperado", [("10", 600), ("0", 60), ("x", 600)])
    def test_ocioso_tem_piso_de_um_minuto(self, monkeypatch, valor, esperado):
        monkeypatch.setenv("ASR_RESIDENTE_OCIOSO_MIN", valor)
        assert ar.ocioso_s() == esperado


class TestConversa:
    def test_sem_residente_devolve_none_calado(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", str(tmp_path / "ninguem.sock"))
        assert ar.pingar() is None
        assert ar.transcrever("a.wav", CHAVE, {}) is None
        assert capsys.readouterr().out == ""

    def test_ping_diz_o_estado(self, residente):
        s, _t, _ = residente()
        assert _esperar(lambda: s.estado == "pronto")
        r = ar.pingar()
        assert r["estado"] == "pronto" and r["chave"] == list(CHAVE)

    def test_transcreve_e_o_log_do_job_ganha_as_linhas(self, residente, capsys):
        residente()
        t = ar.transcrever("a.wav", CHAVE, {"beam_size": 5},
                           linha_do_whisper="🎙️ [ASR] whisper large-v3-turbo em cuda (float16)",
                           progresso=tb._TranscribeProgress)
        assert t == _transcricao(4)
        out = capsys.readouterr().out
        assert "🎙️ [ASR] whisper large-v3-turbo em cuda (float16)" in out
        assert "modelo ja na placa (processo residente)" in out
        # As MESMAS linhas de progresso que o job imprimia sozinho.
        assert "Transcribing… 25%" in out and "Transcribing… 100%" in out

    def test_os_parametros_chegam_inteiros(self, residente):
        recebidos = {}

        def decodificar(modelo, dispositivo, arquivo, params, progresso):
            recebidos.update(arquivo=arquivo, params=params)
            return _transcricao()

        residente(decodificar=decodificar)
        ar.transcrever("x/a.wav", CHAVE, {"beam_size": 5, "vad_filter": True})
        assert recebidos["arquivo"] == os.path.abspath("x/a.wav")
        assert recebidos["params"] == {"beam_size": 5, "vad_filter": True}

    def test_outra_configuracao_e_recusada(self, residente, capsys):
        residente()
        assert ar.transcrever("a.wav", ("small", "cpu", "int8"), {}) is None
        assert "carregando o modelo neste job" in capsys.readouterr().out

    def test_carga_que_falha_recusa_e_o_residente_sai(self, residente, capsys):
        def carregar():
            raise RuntimeError("CUDA failed with error out of memory")

        s, t, saida = residente(carregar=carregar)
        assert ar.transcrever("a.wav", CHAVE, {}) is None
        t.join(3)
        assert saida and "a carga do modelo falhou" in saida[0]

    def test_erro_na_placa_no_meio_devolve_none_e_encerra(self, residente):
        def decodificar(*a):
            raise RuntimeError("CUDA error: an illegal memory access")

        s, t, saida = residente(decodificar=decodificar)
        assert ar.transcrever("a.wav", CHAVE, {}) is None
        t.join(3)
        assert saida and "CUDA" in saida[0]

    def test_erro_comum_devolve_none_e_o_residente_continua(self, residente):
        chamadas = []

        def decodificar(modelo, dispositivo, arquivo, params, progresso):
            chamadas.append(arquivo)
            if len(chamadas) == 1:
                raise ValueError("arquivo estranho")
            return _transcricao()

        s, _t, _ = residente(decodificar=decodificar)
        assert ar.transcrever("a.wav", CHAVE, {}) is None
        assert ar.transcrever("b.wav", CHAVE, {}) == _transcricao()
        assert s.estado == "pronto"


class TestEsperaECarga:
    def test_espera_a_carga_terminar(self, residente, capsys):
        def carregar():
            time.sleep(0.3)
            return _carregar_ok()

        residente(carregar=carregar)
        assert ar.transcrever("a.wav", CHAVE, {}) == _transcricao(4)
        out = capsys.readouterr().out
        assert "ainda esta subindo na placa" in out
        assert "esperei" in out or "nenhuma carga" in out

    def test_carga_lenta_demais_o_job_segue_sozinho(self, residente, capsys):
        liberar = threading.Event()

        def carregar():
            liberar.wait(5)
            return _carregar_ok()

        residente(carregar=carregar)
        try:
            assert ar.transcrever("a.wav", CHAVE, {}, espera_carga_max_s=0.2) is None
            assert "nao terminou de carregar" in capsys.readouterr().out
        finally:
            liberar.set()

    def test_um_de_cada_vez_na_ordem(self, residente):
        ordem, trava = [], threading.Lock()

        def decodificar(modelo, dispositivo, arquivo, params, progresso):
            with trava:
                ordem.append(("comeca", arquivo))
            time.sleep(0.1)
            with trava:
                ordem.append(("acaba", arquivo))
            return _transcricao()

        residente(decodificar=decodificar)
        ts = [threading.Thread(target=ar.transcrever, args=(f"{n}.wav", CHAVE, {}))
              for n in range(3)]
        for t in ts:
            t.start()
            time.sleep(0.02)
        for t in ts:
            t.join(5)
        # Nunca duas transcricoes ao mesmo tempo na placa.
        abertas = 0
        for evento, _ in ordem:
            abertas += 1 if evento == "comeca" else -1
            assert abertas <= 1
        assert len(ordem) == 6


class TestFimDaVida:
    def test_job_que_vai_embora_para_a_decodificacao(self, residente):
        passos = []
        segue = threading.Event()

        def decodificar(modelo, dispositivo, arquivo, params, progresso):
            p = progresso(100.0)
            for pos in range(1, 101):
                passos.append(pos)
                p.update(float(pos))
                if pos == 1:
                    segue.wait(2)
                time.sleep(0.01)
            return _transcricao()

        residente(decodificar=decodificar)
        c = ar._conectar(2.0)
        ar._enviar(c, {"tipo": "transcrever", "arquivo": "a.wav",
                       "chave": list(CHAVE), "params": {}})
        while ar._receber(c).get("tipo") != "progresso":
            pass
        c.close()                      # o job foi cancelado
        segue.set()
        assert _esperar(lambda: len(passos) >= 2)
        time.sleep(0.3)
        assert len(passos) < 100, "o residente continuou gastando a placa"

    def test_sem_uso_solta_a_placa(self, residente):
        _s, t, saida = residente(ocioso=0.3)
        t.join(3)
        assert saida and "sem uso" in saida[0]

    def test_o_ping_do_painel_segura_o_modelo(self, residente):
        _s, t, saida = residente(ocioso=0.4)
        fim = time.monotonic() + 1.0
        while time.monotonic() < fim:
            assert ar.pingar() is not None
            time.sleep(0.1)
        assert not saida, "saiu com o painel aberto"
        t.join(3)
        assert saida and "sem uso" in saida[0]

    def test_nao_sai_por_ociosidade_no_meio_da_carga(self, residente):
        """A primeira carga numa instalacao nova inclui baixar o modelo."""
        s, t, saida = residente(ocioso=0.1, carregar=lambda: (time.sleep(0.5), _carregar_ok())[1])
        time.sleep(0.3)
        assert not saida and s.estado == "carregando"
        t.join(3)
        assert saida and "sem uso" in saida[0]

    def test_travou_no_meio_o_laco_manda_sair(self, residente):
        """Quem encerra de fato e o `os._exit` do `servir()`; aqui, numa thread,
        basta o laco devolver o motivo."""
        liberar = threading.Event()

        def decodificar(modelo, dispositivo, arquivo, params, progresso):
            progresso(10.0).update(1.0)
            liberar.wait(5)              # a placa parou de responder
            return _transcricao()

        _s, t, saida = residente(decodificar=decodificar, travado=0.3)
        cliente = threading.Thread(target=ar.transcrever, args=("a.wav", CHAVE, {}))
        cliente.start()
        try:
            t.join(3)
            assert saida and "parou de andar" in saida[0]
        finally:
            liberar.set()
            cliente.join(3)

    def test_residente_que_morre_no_meio_o_job_segue_sozinho(self, tmp_path,
                                                              monkeypatch, capsys):
        caminho = str(tmp_path / "m.sock")
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", caminho)
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(caminho)
        srv.listen(1)

        def morrer():
            conn, _ = srv.accept()
            ar._receber(conn)
            ar._enviar(conn, {"tipo": "inicio"})
            ar._enviar(conn, {"tipo": "progresso", "pos": 1.0, "total": 10.0})
            conn.close()                 # o `os._exit` de um residente travado

        t = threading.Thread(target=morrer)
        t.start()
        try:
            assert ar.transcrever("a.wav", CHAVE, {}) is None
        finally:
            t.join(3)
            srv.close()
        assert "parou de responder" in capsys.readouterr().out

    def test_um_residente_so_por_endereco(self, residente, tmp_path):
        s, _t, _ = residente()
        outro = ar.Servidor(s.caminho, 60)
        with pytest.raises(ar.JaExiste):
            outro.abrir()


class TestDono:
    def test_desligado_nao_sobe_nada(self, monkeypatch):
        monkeypatch.setenv("ASR_RESIDENTE", "0")
        monkeypatch.setattr(ar.subprocess, "Popen", lambda *a, **k: pytest.fail("subiu"))
        assert ar.garantir("teste") == "desligado"

    def test_sobe_uma_vez_e_nao_duplica(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ASR_RESIDENTE", "1")
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", str(tmp_path / "x.sock"))
        monkeypatch.setattr(ar, "_processo", None)
        monkeypatch.setattr(ar, "_falhou_em", None)
        subidos = []

        class Proc:
            def __init__(self, cmd, **kw):
                subidos.append((cmd, kw))

            def poll(self):
                return None

        monkeypatch.setattr(ar.subprocess, "Popen", Proc)
        assert ar.garantir("painel") == "iniciando"
        assert ar.garantir("video") == "iniciando"
        assert len(subidos) == 1
        cmd, kw = subidos[0]
        assert cmd[-2:] == [str(RAIZ / "asr_residente.py"), "--servir"]
        # Sessao propria: cancelar um job mata o grupo dele, nao o residente.
        assert kw.get("start_new_session") is True

    def test_nao_subir_nao_derruba_quem_chamou(self, monkeypatch, tmp_path, capsys):
        """O `run_job` chama isto logo antes de subir o video."""
        monkeypatch.setenv("ASR_RESIDENTE", "1")
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", str(tmp_path / "x.sock"))
        monkeypatch.setattr(ar, "_processo", None)

        def falha(*a, **k):
            raise OSError("Resource temporarily unavailable")

        monkeypatch.setattr(ar.subprocess, "Popen", falha)
        assert ar.garantir("video") == "falhou"
        assert "carrega o modelo sozinho" in capsys.readouterr().out

    def test_depois_de_uma_falha_da_placa_espera_antes_de_tentar(self, monkeypatch, tmp_path):
        """Sem a espera, uma instalacao com a placa fora do container subiria e
        derrubaria o residente a cada aviso do painel."""
        monkeypatch.setenv("ASR_RESIDENTE", "1")
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", str(tmp_path / "x.sock"))
        monkeypatch.setattr(ar, "_processo", None)
        monkeypatch.setattr(ar, "_falhou_em", None)
        subidos = []

        class Proc:
            codigo = ar.SAIDA_FALHOU

            def __init__(self, cmd, **kw):
                subidos.append(cmd)

            def poll(self):
                return Proc.codigo

        monkeypatch.setattr(ar.subprocess, "Popen", Proc)
        assert ar.garantir("painel") == "iniciando"
        assert ar.garantir("painel") == "falhou"      # saiu com a placa falhando
        assert len(subidos) == 1
        # Passado o prazo, tenta de novo.
        monkeypatch.setattr(ar, "_falhou_em", ar.time.monotonic() - ar.ESPERA_APOS_FALHA_S - 1)
        assert ar.garantir("painel") == "iniciando"
        assert len(subidos) == 2

    def test_saida_por_ociosidade_sobe_de_novo_na_hora(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ASR_RESIDENTE", "1")
        monkeypatch.setenv("ASR_RESIDENTE_SOCKET", str(tmp_path / "x.sock"))
        monkeypatch.setattr(ar, "_processo", None)
        monkeypatch.setattr(ar, "_falhou_em", None)
        subidos = []

        class Proc:
            def __init__(self, cmd, **kw):
                subidos.append(cmd)

            def poll(self):
                return 0

        monkeypatch.setattr(ar.subprocess, "Popen", Proc)
        ar.garantir("painel")
        assert ar.garantir("video") == "iniciando"
        assert len(subidos) == 2

    def test_de_pe_so_pinga(self, monkeypatch, residente):
        monkeypatch.setenv("ASR_RESIDENTE", "1")
        s, _t, _ = residente()
        assert _esperar(lambda: s.estado == "pronto")
        monkeypatch.setattr(ar.subprocess, "Popen", lambda *a, **k: pytest.fail("subiu outro"))
        assert ar.garantir("painel") == "pronto"


class TestNoTranscribeBackends:
    """O job pergunta ao residente primeiro, e so carrega se ele nao servir."""

    @pytest.fixture
    def sem_modelo_local(self, monkeypatch):
        monkeypatch.setattr(tb, "_whisper_force_cpu", False)
        monkeypatch.setattr(tb, "run_whisper_transcription",
                            lambda *a, **k: pytest.fail("carregou o modelo local"))

    def test_residente_serve_e_o_job_nao_carrega_nada(self, monkeypatch, sem_modelo_local):
        monkeypatch.setattr(ar, "ativo", lambda: True)
        monkeypatch.setattr(ar, "transcrever", lambda *a, **k: _transcricao(2))
        assert tb._transcribe_with_whisper("a.wav") == _transcricao(2)

    def test_residente_falha_e_o_job_carrega_como_antes(self, monkeypatch):
        monkeypatch.setattr(ar, "ativo", lambda: True)
        monkeypatch.setattr(ar, "transcrever", lambda *a, **k: None)
        seg = SimpleNamespace(start=0.0, end=1.0, text=" oi",
                              words=[SimpleNamespace(word=" oi", start=0.0, end=0.5)])
        monkeypatch.setattr(tb, "run_whisper_transcription",
                            lambda *a, **k: ([seg], SimpleNamespace(language="pt")))
        t = tb._transcribe_with_whisper("a.wav")
        assert t["segments"][0]["text"] == " oi" and t["language"] == "pt"

    def test_desligado_nem_tenta(self, monkeypatch):
        monkeypatch.setattr(ar, "ativo", lambda: False)
        monkeypatch.setattr(ar, "transcrever", lambda *a, **k: pytest.fail("tentou"))
        monkeypatch.setattr(tb, "run_whisper_transcription",
                            lambda *a, **k: ([], SimpleNamespace(language="pt")))
        assert tb._transcribe_with_whisper("a.wav")["segments"] == []

    def test_manda_a_chave_do_ambiente_do_job(self, monkeypatch, sem_modelo_local):
        monkeypatch.setenv("WHISPER_MODEL", "large-v3-turbo")
        monkeypatch.setenv("WHISPER_DEVICE", "cuda")
        monkeypatch.setenv("WHISPER_COMPUTE", "float16")
        monkeypatch.setattr(ar, "ativo", lambda: True)
        visto = {}

        def transcrever(media, chave, params, **kw):
            visto.update(chave=chave, params=params)
            return _transcricao()

        monkeypatch.setattr(ar, "transcrever", transcrever)
        tb._transcribe_with_whisper("a.wav")
        assert visto["chave"] == CHAVE
        assert visto["params"]["word_timestamps"] is True


# --------------------------------------------------------------------------- #
# O processo de verdade, com um faster_whisper falso no caminho
# --------------------------------------------------------------------------- #

_FASTER_WHISPER_FALSO = '''
from types import SimpleNamespace

class WhisperModel:
    def __init__(self, model_size, device=None, compute_type=None, **kw):
        self.chave = (model_size, device, compute_type)

    def transcribe(self, path, **params):
        palavras = [SimpleNamespace(word=" residente", start=0.0, end=0.4)]
        segs = iter([SimpleNamespace(start=0.0, end=1.0, text=" residente",
                                     words=palavras)])
        return segs, SimpleNamespace(language="pt", duration=1.0)
'''


def test_o_processo_de_verdade_sobe_atende_e_sai(tmp_path):
    falso = tmp_path / "falso" / "faster_whisper"
    falso.mkdir(parents=True)
    (falso / "__init__.py").write_text(_FASTER_WHISPER_FALSO, encoding="utf-8")
    caminho = str(tmp_path / "s" / "asr.sock")
    amb = dict(os.environ,
               PYTHONPATH=os.pathsep.join([str(falso.parent), str(RAIZ)]),
               ASR_RESIDENTE_SOCKET=caminho, WHISPER_MODEL="large-v3-turbo",
               WHISPER_DEVICE="cuda", WHISPER_COMPUTE="float16",
               WHISPER_BATCH_SIZE="0")
    proc = subprocess.Popen([sys.executable, "-u", str(RAIZ / "asr_residente.py"), "--servir"],
                            cwd=str(RAIZ), env=amb, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        velho = os.environ.get("ASR_RESIDENTE_SOCKET")
        os.environ["ASR_RESIDENTE_SOCKET"] = caminho
        try:
            assert _esperar(lambda: (ar.pingar() or {}).get("estado") == "pronto", 20), \
                "o residente nao subiu"
            t = ar.transcrever(str(tmp_path / "a.wav"), CHAVE, {"beam_size": 5})
        finally:
            if velho is None:
                os.environ.pop("ASR_RESIDENTE_SOCKET", None)
            else:
                os.environ["ASR_RESIDENTE_SOCKET"] = velho
        assert t["segments"][0]["text"] == " residente"
        assert t["segments"][0]["words"][0]["word"] == " residente"
    finally:
        proc.terminate()
        saida = proc.communicate(timeout=10)[0]
    assert "pronto na placa" in saida, saida


# --------------------------------------------------------------------------- #
# O servidor HTTP: quem aquece
# --------------------------------------------------------------------------- #

class TestNoServidorHttp:
    def test_a_rota_do_painel_devolve_o_estado(self, monkeypatch):
        import asyncio

        import httpx

        import app as app_module

        pedidos = []
        monkeypatch.setattr(ar, "garantir", lambda motivo="": pedidos.append(motivo) or "pronto")

        async def _post():
            transporte = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
                return await c.post("/api/asr/aquecer")

        r = asyncio.run(_post())
        assert r.status_code == 200 and r.json() == {"estado": "pronto"}
        assert pedidos == ["painel aberto"]

    def test_o_job_aquece_antes_de_subir_o_main(self):
        """Antes do `Popen`: o modelo carrega enquanto o job ainda baixa o
        video. E no `run_job`, e nao no `/api/process`, para valer tambem para
        o job retomado depois de um restart."""
        import ast

        arvore = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
        run_job = next(n for n in ast.walk(arvore)
                       if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_job")
        linhas = {}
        for n in ast.walk(run_job):
            if isinstance(n, ast.Call):
                texto = ast.unparse(n)
                if "asr_residente.garantir" in texto:
                    linhas.setdefault("aquece", n.lineno)
                if texto.startswith("subprocess.Popen("):
                    linhas.setdefault("popen", n.lineno)
        assert "aquece" in linhas, "o run_job parou de aquecer o residente"
        assert linhas["aquece"] < linhas["popen"]
