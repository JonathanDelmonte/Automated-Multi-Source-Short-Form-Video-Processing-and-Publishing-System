"""Apagar um projeto apaga tudo -- e diz quando nao conseguiu.

O autor apagou um projeto na aba Projetos, voltou ao Clip Generator e o projeto
continuava la; e "parece que mesmo excluindo, fica salvo os videos" (22-set-2026).
Havia tres buracos, e cada teste abaixo prende um:

1. o `rmtree(ignore_errors=True)` engolia arquivo preso (no Docker Desktop a
   pasta e do Windows, que nao apaga arquivo aberto) e a resposta era
   "apagado" com o video ainda no disco;
2. cancelar matava o `main.py` e deixava os ffmpeg filhos vivos, gravando na
   pasta que ia ser apagada;
3. o painel nao soltava o projeto aberto (esse e JS; o guarda aqui le a fonte).
"""
import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

app_module = pytest.importorskip("app")

RAIZ = Path(__file__).resolve().parent.parent


def _apagar(job_id):
    async def _run():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            return await c.delete(f"/api/jobs/{job_id}")
    return asyncio.run(_run())


@pytest.fixture()
def projeto(tmp_path, monkeypatch):
    saida = tmp_path / "output"
    envios = tmp_path / "uploads"
    saida.mkdir()
    envios.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(envios))
    monkeypatch.setattr(app_module, "_ESPERAS_PARA_APAGAR", (0.0, 0.0))
    pasta = saida / "projeto-x"
    pasta.mkdir()
    (pasta / "Video_clip_1.mp4").write_bytes(b"corte")
    (pasta / "Video_metadata.json").write_text('{"shorts": []}')
    (envios / "projeto-x_original.mp4").write_bytes(b"fonte")
    yield pasta, envios
    app_module.jobs.pop("projeto-x", None)


class TestNaoDizApagadoComArquivoNoDisco:

    def test_apaga_a_pasta_e_o_video_enviado(self, projeto):
        pasta, envios = projeto
        r = _apagar("projeto-x")
        assert r.status_code == 200
        assert not pasta.exists()
        assert list(envios.iterdir()) == []

    def test_arquivo_preso_vira_409_com_o_nome_dele(self, projeto, monkeypatch):
        pasta, _ = projeto
        # O Windows recusando: o rmtree "passa" e o arquivo continua la.
        monkeypatch.setattr(app_module.shutil, "rmtree", lambda *a, **k: None)
        r = _apagar("projeto-x")
        assert r.status_code == 409
        assert "Video_clip_1.mp4" in r.json()["detail"] or \
            "Video_metadata.json" in r.json()["detail"]
        assert (pasta / "Video_clip_1.mp4").exists()

    def test_tenta_de_novo_antes_de_desistir(self, projeto, monkeypatch):
        """Meio segundo costuma bastar: o ffmpeg termina de morrer, o antivirus
        solta o arquivo. A primeira recusa nao pode virar erro na tela."""
        pasta, _ = projeto
        verdadeiro = app_module.shutil.rmtree
        tentativas = []

        def rmtree_teimoso(caminho, *a, **k):
            tentativas.append(caminho)
            if len(tentativas) > 1:
                verdadeiro(caminho, *a, **k)

        monkeypatch.setattr(app_module.shutil, "rmtree", rmtree_teimoso)
        r = _apagar("projeto-x")
        assert r.status_code == 200
        assert len(tentativas) == 2
        assert not pasta.exists()

    def test_o_que_sobrou_de_antes_sai_na_proxima_vez(self, projeto):
        """Pasta sem metadata e sem manifesto: o endpoint nao acha o job, e
        mesmo assim tem de levar o que sobrou de uma tentativa anterior."""
        pasta, _ = projeto
        (pasta / "Video_metadata.json").unlink()
        r = _apagar("projeto-x")
        assert r.status_code == 200
        assert not pasta.exists()


def _vivo(pid):
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return estado != "Z"


@pytest.mark.skipif(not hasattr(os, "killpg") or not Path("/proc").exists(),
                    reason="grupo de processos e coisa de Linux (o container)")
class TestCancelarLevaOsFilhos:

    def test_o_ffmpeg_filho_morre_junto_com_o_main(self):
        # O `sh` faz o papel do main.py; o `sleep` em segundo plano, o do ffmpeg.
        proc = subprocess.Popen(
            ["sh", "-c", "sleep 30 & echo $!; wait"],
            stdout=subprocess.PIPE, text=True, start_new_session=True)
        neto = int(proc.stdout.readline())
        assert _vivo(neto)

        app_module._terminar_processo(proc)

        prazo = time.time() + 5
        while _vivo(neto) and time.time() < prazo:
            time.sleep(0.05)
        assert not _vivo(neto), "o filho do job sobreviveu ao cancelamento"

    def test_processo_sem_grupo_proprio_nunca_leva_o_servidor_junto(self):
        """Sem `start_new_session`, o grupo do processo e o do SERVIDOR: um
        killpg ali derrubaria o uvicorn. Este teste esta vivo para contar."""
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        assert os.getpgid(proc.pid) == os.getpgrp()
        app_module._terminar_processo(proc)
        assert proc.wait(timeout=5) is not None


def test_todo_job_nasce_em_grupo_proprio():
    fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
    assert "start_new_session=True" in fonte
    assert "os.killpg(" in fonte


class TestPainelSoltaOProjetoApagado:
    """JS nao roda no CI; o guarda le a fonte, como o de `test_log_com_hora`."""

    def test_as_duas_listas_avisam_o_app(self):
        for nome in ("ProjectsGrid.jsx", "ProjectsList.jsx"):
            fonte = (RAIZ / "dashboard" / "src" / "components" / nome).read_text(encoding="utf-8")
            assert "onApagado(jobId)" in fonte, nome
            # `apiFetch` nao falha em 409; so o `apiJson` leva o erro a tela.
            assert "apiJson(`/api/jobs/${jobId}`, { method: 'DELETE' })" in fonte, nome

    def test_o_app_fecha_o_projeto_aberto(self):
        fonte = (RAIZ / "dashboard" / "src" / "App.jsx").read_text(encoding="utf-8")
        assert "if (id === jobId) handleReset();" in fonte
        assert fonte.count("onApagado={handleProjetoApagado}") == 2
