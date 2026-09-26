"""Cada linha do log carrega a hora em que NASCEU, nao a de quem olha.

O painel escrevia `new Date().toLocaleTimeString()` ao desenhar cada linha, e
todas saiam com a mesma hora -- a do momento em que a tela era redesenhada
(22-set-2026: "a contagem de minutos nao passa, a de segundos passa"). A hora
certa so existe no servidor, quando a linha chega do subprocesso; estes testes
prendem que ela e guardada ali, que chega alinhada ao painel e que o painel a usa.
"""
import ast
import asyncio
import copy
import io
import pickle
from pathlib import Path

import httpx
import pytest

app_module = pytest.importorskip("app")

RAIZ = Path(__file__).resolve().parent.parent


def _status(job_id):
    async def _run():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            return await c.get(f"/api/status/{job_id}")
    return asyncio.run(_run())


@pytest.fixture()
def job(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    linhas = app_module.LinhasDoLog()
    app_module.jobs["log-com-hora"] = {"status": "processing", "logs": linhas}
    yield linhas
    app_module.jobs.pop("log-com-hora", None)


class TestLinhasDoLog:

    def test_cada_append_guarda_a_propria_hora(self, monkeypatch):
        linhas = app_module.LinhasDoLog()
        # Relogio falso so no `app`: trocar `time.time` trocaria o do processo.
        relogio = iter([100.0, 160.0, 220.5])
        monkeypatch.setattr(app_module, "time",
                            type("RelogioFalso", (), {"time": staticmethod(lambda: next(relogio))}))
        linhas.append("baixando")
        linhas.append("transcrevendo")
        linhas += ["renderizando"]
        assert linhas == ["baixando", "transcrevendo", "renderizando"]
        assert linhas.tempos == [100.0, 160.0, 220.5]

    def test_continua_sendo_lista_de_texto_para_quem_ja_le(self):
        linhas = app_module.LinhasDoLog(["a", "b"])
        assert isinstance(linhas, list)
        assert linhas[-1:] == ["b"]
        assert app_module._job_error_text(linhas) is not None

    @pytest.mark.parametrize("copiar", [copy.copy, copy.deepcopy,
                                        lambda x: pickle.loads(pickle.dumps(x))])
    def test_copia_nao_dobra_as_horas_nem_mexe_na_original(self, copiar):
        original = app_module.LinhasDoLog(["a", "b"])
        original.tempos = [1.0, 2.0]
        copia = copiar(original)
        assert copia == ["a", "b"] and copia.tempos == [1.0, 2.0]
        assert original.tempos == [1.0, 2.0]
        copia.append("c")
        assert original.tempos == [1.0, 2.0]


class TestStatus:

    def test_devolve_as_horas_alinhadas_com_as_linhas(self, job):
        job.extend(["baixando", "transcrevendo"])
        job.tempos = [1758550000.04, 1758550093.26]

        corpo = _status("log-com-hora").json()

        assert corpo["logs"] == ["baixando", "transcrevendo"]
        assert corpo["log_times"] == [1758550000.0, 1758550093.3]

    def test_poll_no_meio_do_append_manda_a_ultima_sem_hora(self, job):
        """O texto entra antes da hora. Um poll que caia entre os dois passos
        nao pode deslocar as horas das linhas de cima."""
        job.extend(["a", "b"])
        job.tempos = [10.0, 20.0]
        list.append(job, "c")  # o texto entrou; a hora ainda nao

        corpo = _status("log-com-hora").json()

        assert corpo["logs"] == ["a", "b", "c"]
        assert corpo["log_times"] == [10.0, 20.0, None]

    def test_lista_comum_manda_sem_hora_e_nao_com_hora_errada(self, job):
        app_module.jobs["log-com-hora"]["logs"] = ["linha antiga"]
        corpo = _status("log-com-hora").json()
        assert corpo["logs"] == ["linha antiga"]
        assert corpo["log_times"] is None


def test_a_saida_do_subprocesso_ganha_hora(job):
    """O caminho de verdade: o que o main.py imprime passa pelo enqueue_output."""
    fluxo = io.BytesIO("🎙️ transcrevendo\n__STAGE__BEGIN 04_detect\n✂️ cortando\n"
                       .encode("utf-8"))
    app_module.enqueue_output(fluxo, "log-com-hora")
    assert list(job) == ["🎙️ transcrevendo", "✂️ cortando"]
    assert len(job.tempos) == 2


def test_todo_job_nasce_com_o_log_que_guarda_hora():
    """Um `'logs': [...]` cru num job novo tiraria a hora daquele job inteiro,
    sem erro nenhum -- a tela so voltaria a mostrar linha sem hora."""
    arvore = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    crus = [
        no.lineno
        for no in ast.walk(arvore) if isinstance(no, ast.Dict)
        for chave, valor in zip(no.keys, no.values)
        if isinstance(chave, ast.Constant) and chave.value == "logs"
        and isinstance(valor, ast.List)
    ]
    assert crus == [], f"job criado com lista crua de log nas linhas {crus}"


def test_o_painel_nao_inventa_mais_a_hora():
    # O log mora na pagina do projeto desde a 7.1 (`pages/Projeto.jsx`), e o
    # App.jsx nao pode voltar a desenhar log nenhum com a hora de quem olha.
    src = RAIZ / "dashboard" / "src"
    projeto = (src / "pages" / "Projeto.jsx").read_text(encoding="utf-8")
    assert "new Date().toLocaleTimeString()" not in projeto
    assert "log_times" in projeto
    assert "new Date().toLocaleTimeString()" not in (src / "App.jsx").read_text(encoding="utf-8")
