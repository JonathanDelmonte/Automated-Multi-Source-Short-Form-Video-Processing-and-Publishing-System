"""O motor roda fora do Docker, no Windows do ajudante (Fase 6.2, 24-set-2026).

Ate aqui o servidor so rodava no container Linux, e tres coisas so funcionavam
la. Nenhuma quebrava ao subir -- quebravam no meio do uso, que e o pior lugar:

- **cancelar/apagar um projeto**: o `killpg` nao existe no Windows e o
  `signal.SIGKILL` tambem nao. O `main.py` morria sozinho e os ffmpeg ficavam
  orfaos, segurando o video aberto -- e arquivo aberto o Windows nao apaga;
- **a leitura do log**: um byte fora do UTF-8 encerrava a thread que esvazia o
  cano do job, e o job travava na escrita seguinte, "processando" para sempre;
- **as pastas**: `output/` e `uploads/` fixas, relativas ao codigo. O ajudante
  troca a pasta do codigo inteira a cada atualizacao, e os projetos iriam junto.

Os testes marcados para o Windows rodam no CI de lá (`windows.yml`); os outros
rodam aqui tambem, simulando o Windows onde da.
"""
import ast
import io
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

app_module = pytest.importorskip("app")
RAIZ = Path(__file__).resolve().parent.parent


# --- cancelar ---------------------------------------------------------------

def test_sigkill_nunca_e_lido_direto_do_modulo_signal():
    """`signal.SIGKILL` nao existe no Windows: lido no argumento de uma chamada,
    levanta antes de a funcao comecar -- e o `except` em volta engolia o erro
    com um aviso, deixando o processo vivo."""
    arvore = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    lidos = [no.lineno for no in ast.walk(arvore)
             if isinstance(no, ast.Attribute) and no.attr == "SIGKILL"
             and isinstance(no.value, ast.Name) and no.value.id == "signal"]
    assert lidos == [], f"use app._SIGKILL (linhas {lidos})"


class _ProcFalso:
    pid = 4242

    def __init__(self):
        self.vivo = True

    def poll(self):
        return None if self.vivo else 1

    def wait(self, timeout=None):
        return 1

    def terminate(self):
        raise AssertionError("terminate() antes do taskkill /T orfana os ffmpeg")

    def kill(self):
        raise AssertionError("o taskkill ja devia ter derrubado a arvore")


def test_no_windows_cancelar_derruba_a_arvore_inteira(monkeypatch):
    proc = _ProcFalso()
    comandos = []

    def run_falso(cmd, **kw):
        comandos.append(cmd)
        proc.vivo = False

    monkeypatch.setattr(app_module, "_NO_WINDOWS", True)
    monkeypatch.setattr(app_module.subprocess, "run", run_falso)
    app_module._terminar_processo(proc)
    assert comandos == [["taskkill", "/PID", "4242", "/T", "/F"]]


def _vivo_no_windows(pid):
    saida = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True).stdout
    return str(pid) in saida


@pytest.mark.skipif(os.name != "nt", reason="arvore de processos do Windows")
def test_no_windows_o_neto_morre_junto():
    # O processo do meio faz o papel do main.py; o neto, o do ffmpeg.
    codigo = ("import subprocess, sys, time; "
              "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
              "print(p.pid, flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", codigo],
                            stdout=subprocess.PIPE, text=True)
    neto = int(proc.stdout.readline())
    assert _vivo_no_windows(neto)

    app_module._terminar_processo(proc)

    prazo = time.time() + 10
    while _vivo_no_windows(neto) and time.time() < prazo:
        time.sleep(0.2)
    assert not _vivo_no_windows(neto), "o filho do job sobreviveu ao cancelamento"
    assert proc.poll() is not None


# --- log ----------------------------------------------------------------------

def test_byte_fora_do_utf8_nao_para_a_leitura_do_log():
    job = "teste-byte-quebrado"
    app_module.jobs[job] = {"logs": []}
    try:
        fluxo = io.BytesIO(b"antes\n" + b"caminho \xff\xfe torto\n" + b"depois\n")
        app_module.enqueue_output(fluxo, job)
        logs = list(app_module.jobs[job]["logs"])
    finally:
        app_module.jobs.pop(job, None)
    assert logs[0] == "antes"
    assert logs[-1] == "depois", "a leitura parou no byte quebrado"
    assert len(logs) == 3


# --- pastas -------------------------------------------------------------------

def test_as_pastas_de_trabalho_vem_do_ambiente(tmp_path):
    saida, envios = tmp_path / "saida", tmp_path / "envios"
    env = {**os.environ, "OUTPUT_DIR": str(saida), "UPLOAD_DIR": str(envios)}
    r = subprocess.run(
        [sys.executable, "-c",
         "import app; print('>>', app.OUTPUT_DIR); print('>>', app.UPLOAD_DIR);"
         "print('>>', app.THUMBNAILS_DIR)"],
        cwd=RAIZ, env=env, capture_output=True, text=True, timeout=180)
    linhas = [l[3:] for l in r.stdout.splitlines() if l.startswith(">> ")]
    assert linhas == [str(saida), str(envios), str(saida / "thumbnails")], r.stderr[-2000:]
    assert saida.is_dir() and envios.is_dir()


def test_sem_variavel_as_pastas_sao_as_de_sempre():
    """No Docker nada muda: relativas ao /app, como o compose monta."""
    fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
    assert 'UPLOAD_DIR = (os.environ.get("UPLOAD_DIR") or "").strip() or "uploads"' in fonte
    assert 'OUTPUT_DIR = (os.environ.get("OUTPUT_DIR") or "").strip() or "output"' in fonte


def test_a_miniatura_e_gravada_onde_o_servidor_a_procura(monkeypatch, tmp_path):
    thumbnail = pytest.importorskip("thumbnail")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    assert thumbnail._pasta_de_saida() == str(tmp_path)
    monkeypatch.delenv("OUTPUT_DIR")
    assert thumbnail._pasta_de_saida() == "output"
    fonte = (RAIZ / "thumbnail.py").read_text(encoding="utf-8")
    assert 'os.path.join("output"' not in fonte
