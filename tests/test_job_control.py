"""Cancelar, listar e apagar um job -- e o progresso por estagio.

Nada disto existia. O handle do `Popen` so vivia como variavel local de
`run_job`, entao nenhum endpoint alcancava o processo: recarregar a pagina nao
parava nada, e matar o container tambem nao, porque o manifesto de resume
ressuscitava o job no proximo boot. Era o bug que o autor reportou em
13-set-2026, com o job continuando a processar depois de fechar o terminal e
apagar a pasta a mao.

O que os testes abaixo prendem, em ordem de importancia:

1. **cancelar apaga o manifesto.** E o unico passo cuja ausencia nao aparece na
   hora: o job morre, a tela diz "cancelado", e 30 segundos depois o scan de
   resume o re-enfileira. Sem este teste, a regressao so seria notada por
   alguem olhando o log meio minuto depois de desistir.
2. cancelado nao e falha -- um processo morto por sinal volta com codigo != 0,
   e sem tratamento vira "falhou" na cara de quem acabou de clicar em cancelar.
3. o marcador de estagio move a barra e **nao vaza para o log** do usuario.
"""
import asyncio
import io
import json
import os

import httpx
import pytest

import app as app_module
from app import app


def _client_call(metodo, caminho):
    async def _run():
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            return await c.request(metodo, caminho)
    return asyncio.run(_run())


class ProcessoFalso:
    """Um Popen que conta o que mandaram fazer com ele."""

    def __init__(self, morre_no_terminate=True):
        self.terminado = False
        self.morto = False
        self._morre_no_terminate = morre_no_terminate
        self._vivo = True

    def poll(self):
        return None if self._vivo else -15

    def terminate(self):
        self.terminado = True
        if self._morre_no_terminate:
            self._vivo = False

    def wait(self, timeout=None):
        if self._vivo:
            import subprocess
            raise subprocess.TimeoutExpired("falso", timeout)
        return -15

    def kill(self):
        self.morto = True
        self._vivo = False


@pytest.fixture(autouse=True)
def _limpa_estado():
    app_module.jobs.clear()
    app_module._job_processes.clear()
    app_module._cancelled_jobs.clear()
    yield
    app_module.jobs.clear()
    app_module._job_processes.clear()
    app_module._cancelled_jobs.clear()


def _job_rodando(job_id, tmp_path, com_manifesto=True):
    pasta = tmp_path / job_id
    pasta.mkdir(parents=True, exist_ok=True)
    if com_manifesto:
        (pasta / app_module._RESUME_FILE).write_text(json.dumps({"heartbeat": 0}))
    app_module.jobs[job_id] = {
        "status": "processing", "logs": [], "output_dir": str(pasta),
        "created_at": 1.0,
    }
    return pasta


class TestCancelamento:

    def test_cancelar_mata_o_processo_e_marca_cancelado(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        _job_rodando("job-a", tmp_path)
        proc = ProcessoFalso()
        app_module._job_processes["job-a"] = proc

        r = _client_call("POST", "/api/jobs/job-a/cancel")

        assert r.status_code == 200
        assert r.json()["cancelled"] is True
        assert proc.terminado is True
        assert app_module.jobs["job-a"]["status"] == "cancelled"

    def test_cancelar_apaga_o_manifesto_de_resume(self, tmp_path, monkeypatch):
        """O passo que, se faltar, faz o job cancelado voltar sozinho em 30s."""
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        pasta = _job_rodando("job-b", tmp_path)
        manifesto = pasta / app_module._RESUME_FILE
        assert manifesto.exists()
        app_module._job_processes["job-b"] = ProcessoFalso()

        _client_call("POST", "/api/jobs/job-b/cancel")

        assert not manifesto.exists()

    def test_scan_de_resume_nao_ressuscita_cancelado(self, tmp_path, monkeypatch):
        """Cinto e suspensorio: mesmo com o manifesto de volta, nao re-enfileira."""
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        pasta = _job_rodando("job-c", tmp_path)
        app_module._cancelled_jobs.add("job-c")
        (pasta / app_module._RESUME_FILE).write_text(json.dumps({"heartbeat": 0}))

        app_module._resume_interrupted_jobs()

        assert not (pasta / app_module._RESUME_FILE).exists()

    def test_processo_teimoso_leva_kill(self, tmp_path):
        proc = ProcessoFalso(morre_no_terminate=False)
        app_module._terminar_processo(proc)
        assert proc.terminado is True
        assert proc.morto is True

    def test_cancelar_job_ja_terminado_nao_e_erro(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["job-d"] = {"status": "completed", "logs": [], "created_at": 1.0}
        r = _client_call("POST", "/api/jobs/job-d/cancel")
        assert r.status_code == 200
        assert r.json()["cancelled"] is False

    def test_cancelar_job_inexistente_da_404(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        assert _client_call("POST", "/api/jobs/nao-existe/cancel").status_code == 404


class TestApagar:

    def test_apagar_remove_a_pasta_e_o_registro(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        pasta = _job_rodando("job-e", tmp_path)
        app_module._job_processes["job-e"] = ProcessoFalso()

        r = _client_call("DELETE", "/api/jobs/job-e")

        assert r.status_code == 200
        assert not pasta.exists()
        assert "job-e" not in app_module.jobs

    def test_apagar_cancela_antes_de_remover(self, tmp_path, monkeypatch):
        """Apagar a pasta debaixo de um main.py vivo deixa um processo orfao
        escrevendo num diretorio que ja nao existe."""
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        _job_rodando("job-f", tmp_path)
        proc = ProcessoFalso()
        app_module._job_processes["job-f"] = proc

        _client_call("DELETE", "/api/jobs/job-f")

        assert proc.terminado is True

    def test_apagar_o_que_ja_nao_existe_e_sucesso(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        r = _client_call("DELETE", "/api/jobs/fantasma")
        assert r.status_code == 200
        assert r.json()["deleted"] is True


class TestListagem:

    def test_lista_vem_do_mais_novo_para_o_mais_velho(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["velho"] = {"status": "completed", "logs": [], "created_at": 10.0}
        app_module.jobs["novo"] = {"status": "completed", "logs": [], "created_at": 99.0}

        ids = [j["job_id"] for j in _client_call("GET", "/api/jobs").json()["jobs"]]

        assert ids == ["novo", "velho"]

    def test_resumo_traz_titulo_e_contagem_sem_o_log(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["j"] = {
            "status": "completed", "created_at": 1.0,
            "logs": ["linha " * 5000],
            "result": {"clips": [{"video_title_for_youtube_short": "Um título"}, {}]},
        }
        linha = _client_call("GET", "/api/jobs").json()["jobs"][0]
        assert linha["title"] == "Um título"
        assert linha["clip_count"] == 2
        assert "logs" not in linha

    def test_resumo_traz_a_capa_do_primeiro_clipe(self, tmp_path, monkeypatch):
        """E o proprio clipe: o cartao usa <video preload=metadata>."""
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["j"] = {
            "status": "completed", "created_at": 1.0, "logs": [],
            "result": {"clips": [{"video_url": "/videos/j/corte_1.mp4"}]},
        }
        linha = _client_call("GET", "/api/jobs").json()["jobs"][0]
        assert linha["first_clip_url"] == "/videos/j/corte_1.mp4"

    def test_sem_clipes_a_capa_e_nula(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["j"] = {"status": "processing", "created_at": 1.0, "logs": []}
        linha = _client_call("GET", "/api/jobs").json()["jobs"][0]
        assert linha["first_clip_url"] is None


class TestProgressoPorEstagio:

    def _alimenta(self, job_id, *linhas):
        fluxo = io.BytesIO(b"".join(l.encode("utf-8") + b"\n" for l in linhas))
        app_module.enqueue_output(fluxo, job_id)

    def test_marcador_move_o_estagio(self):
        app_module.jobs["j"] = {"status": "processing", "logs": []}
        self._alimenta("j", "__STAGE__BEGIN 03_transcribe")
        assert app_module.jobs["j"]["stage"] == "03_transcribe"

    def test_marcador_nao_vaza_para_o_log_do_usuario(self):
        app_module.jobs["j"] = {"status": "processing", "logs": []}
        self._alimenta("j", "__STAGE__BEGIN 01_ingest", "Baixando vídeo...")
        assert app_module.jobs["j"]["logs"] == ["Baixando vídeo..."]

    def test_indice_e_rotulo_do_estagio(self):
        # O indice vem da POSICAO em PIPELINE_STAGES, nao de um numero repetido
        # aqui: a versao anterior deste teste fixava 3 de 4 e quebrou no dia em
        # que o estagio 02 nasceu, sem que nada estivesse errado.
        esperado = [n for n, _ in app_module.PIPELINE_STAGES].index("04_detect") + 1
        v = app_module._stage_view({"stage": "04_detect"})
        assert v["stage_index"] == esperado
        assert v["stage_total"] == len(app_module.PIPELINE_STAGES)
        assert v["stage_label"] == "escolhendo os melhores momentos"

    def test_estagios_estao_na_ordem_em_que_o_pipeline_os_emite(self):
        """O indice so quer dizer alguma coisa se a lista estiver na ordem certa.

        Os nomes sao ordenaveis por prefixo justamente para isto (`01_`, `02_`),
        entao a checagem e direta -- e pega o caso de alguem acrescentar um
        estagio no fim da lista em vez de no lugar dele."""
        nomes = [n for n, _ in app_module.PIPELINE_STAGES]
        assert nomes == sorted(nomes)

    def test_todo_estagio_tem_rotulo_em_portugues(self):
        for nome, rotulo in app_module.PIPELINE_STAGES:
            assert rotulo and rotulo != nome, nome

    def test_sem_estagio_o_indice_e_zero(self):
        v = app_module._stage_view({})
        assert v["stage_index"] == 0
        assert v["stage"] is None

    def test_estagio_desconhecido_nao_quebra(self):
        """Um estagio novo no main.py que ninguem cadastrou aqui deve deixar a
        barra parada, nao derrubar o /api/status."""
        v = app_module._stage_view({"stage": "99_inventado"})
        assert v["stage_index"] == 0
        assert v["stage_label"] == "99_inventado"

    def test_status_carrega_o_estagio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        app_module.jobs["j"] = {"status": "processing", "logs": [], "stage": "03_transcribe"}
        corpo = _client_call("GET", "/api/status/j").json()
        assert corpo["stage_label"] == "transcrevendo"
        assert corpo["stage_index"] == (
            [n for n, _ in app_module.PIPELINE_STAGES].index("03_transcribe") + 1)
