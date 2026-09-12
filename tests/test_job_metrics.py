"""Custo de um job por estagio (job_metrics) e sua exposicao no /api/status."""
import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import job_metrics


@pytest.fixture(autouse=True)
def zerado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job_metrics.reset(str(tmp_path), "video")
    return tmp_path


class TestTempoPorEstagio:
    def test_mede_o_tempo_de_parede(self):
        with job_metrics.stage("03_transcribe"):
            time.sleep(0.02)
        assert job_metrics.snapshot()["stages"]["03_transcribe"]["seconds"] >= 0.02

    def test_o_mesmo_estagio_acumula(self):
        # E o caso do laco de cortes: 05_06_render roda uma vez por corte.
        for _ in range(3):
            with job_metrics.stage("05_06_render"):
                time.sleep(0.01)
        s = job_metrics.snapshot()["stages"]["05_06_render"]
        assert s["seconds"] >= 0.03

    def test_excecao_ainda_registra_o_tempo(self):
        with pytest.raises(RuntimeError):
            with job_metrics.stage("04_detect"):
                time.sleep(0.01)
                raise RuntimeError("falhou no meio")
        assert job_metrics.snapshot()["stages"]["04_detect"]["seconds"] >= 0.01

    def test_estagios_aninhados_desempilham_na_ordem(self):
        with job_metrics.stage("externo"):
            with job_metrics.stage("interno"):
                assert job_metrics.current_stage() == "interno"
            assert job_metrics.current_stage() == "externo"
        assert job_metrics.current_stage() is None


class TestAtribuicaoDeTokens:
    def test_credita_a_chamada_ao_estagio_aberto(self):
        # A razao de o coletor manter pilha: instrumentar o LLM num lugar so.
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 900, "output_tokens": 100,
                                 "provider": "groq"})
        s = job_metrics.snapshot()["stages"]["04_detect"]
        assert (s["calls"], s["tokens_in"], s["tokens_out"]) == (1, 900, 100)
        assert s["providers"]["groq"] == {"calls": 1, "tokens": 1000}

    def test_soma_provedores_diferentes_no_mesmo_estagio(self):
        # Acontece quando a cascata cai do primario para o secundario.
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 100, "output_tokens": 0, "provider": "groq"})
            job_metrics.add_llm({"input_tokens": 200, "output_tokens": 0, "provider": "gemini"})
        s = job_metrics.snapshot()["stages"]["04_detect"]
        assert s["calls"] == 2
        assert set(s["providers"]) == {"groq", "gemini"}

    def test_chamada_fora_de_estagio_nao_se_perde(self):
        job_metrics.add_llm({"input_tokens": 5, "output_tokens": 1})
        assert job_metrics.snapshot()["stages"]["sem_estagio"]["calls"] == 1

    def test_cost_vazio_e_ignorado(self):
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm(None)
            job_metrics.add_llm({})
        assert job_metrics.snapshot()["stages"]["04_detect"]["calls"] == 0

    def test_usa_o_modelo_quando_nao_ha_provider(self):
        # O caminho antigo do Gemini devolve cost sem a chave "provider".
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 10, "model": "gemini-3.1-flash-lite"})
        s = job_metrics.snapshot()["stages"]["04_detect"]
        assert "gemini-3.1-flash-lite" in s["providers"]


class TestDuracaoFalada:
    def test_soma_os_segmentos_nao_a_duracao_do_arquivo(self):
        # A secao 4 do plano: o custo cresce com a duracao FALADA. Uma live de
        # 4h com metade de silencio custa metade.
        t = {"segments": [{"start": 0, "end": 10}, {"start": 100, "end": 130}]}
        assert job_metrics.spoken_seconds_from(t) == 40.0

    def test_transcricao_ausente_da_zero(self):
        assert job_metrics.spoken_seconds_from(None) == 0.0
        assert job_metrics.spoken_seconds_from({}) == 0.0

    def test_segmento_malformado_e_pulado(self):
        t = {"segments": [{"start": 0, "end": 5}, {"start": "x"}, {"end": 9}]}
        assert job_metrics.spoken_seconds_from(t) == 5.0

    def test_tokens_por_minuto_falado(self):
        # E o numero que a Fase 1 usa para calibrar o pre-filtro.
        job_metrics.fact("spoken_seconds", 600.0)   # 10 min
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 4_500, "output_tokens": 500})
        assert job_metrics.snapshot()["totals"]["tokens_per_spoken_minute"] == 500.0

    def test_sem_fala_nao_divide_por_zero(self):
        job_metrics.fact("spoken_seconds", 0.0)
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 10})
        assert "tokens_per_spoken_minute" not in job_metrics.snapshot()["totals"]


class TestSidecar:
    def test_grava_com_o_nome_base_do_video(self, tmp_path):
        with job_metrics.stage("01_ingest"):
            pass
        caminho = job_metrics.write()
        assert caminho and caminho.endswith("video.timings.json")
        d = json.loads(open(caminho, encoding="utf-8").read())
        assert "01_ingest" in d["stages"]

    def test_set_destination_nao_apaga_o_que_ja_foi_medido(self, tmp_path):
        # O estagio 01 e medido antes de output_dir e titulo existirem.
        with job_metrics.stage("01_ingest"):
            time.sleep(0.01)
        destino = tmp_path / "job-abc"
        destino.mkdir()
        job_metrics.set_destination(str(destino), "outro_titulo")
        caminho = job_metrics.write()
        assert caminho == str(destino / "outro_titulo.timings.json")
        assert "01_ingest" in json.loads(open(caminho, encoding="utf-8").read())["stages"]

    def test_diretorio_inexistente_nao_quebra_o_job(self):
        job_metrics.set_destination("/nao/existe/em/lugar/nenhum", "video")
        assert job_metrics.write() is None      # medicao e melhor-esforco

    def test_snapshot_vazio_quando_nao_houve_reset(self, monkeypatch):
        monkeypatch.setattr(job_metrics, "_job", {})
        assert job_metrics.snapshot() == {}
        assert job_metrics.summary_line() == ""
        assert job_metrics.write() is None


class TestResumo:
    def test_uma_linha_por_estagio_com_numeros(self):
        job_metrics.fact("spoken_seconds", 120.0)
        with job_metrics.stage("03_transcribe"):
            time.sleep(0.01)
        with job_metrics.stage("04_detect"):
            job_metrics.add_llm({"input_tokens": 1_000, "output_tokens": 200,
                                 "provider": "groq"})
        texto = job_metrics.summary_line()
        assert "03_transcribe" in texto
        assert "04_detect" in texto
        assert "1200 tokens" in texto.replace("  ", " ").replace("  ", " ") or "1200" in texto
        assert "groq" in texto
        assert "TOTAL" in texto
        assert "tokens/min falado" in texto


class TestExposicaoNaApi:
    def test_status_le_o_sidecar(self, tmp_path, monkeypatch):
        """`_job_timings` usa `_JOB_ID_RE`, que e definido depois dele no
        app.py -- resolve em tempo de chamada, mas vale confirmar."""
        app = pytest.importorskip("app")
        job_id = "0123abcd-4567-89ab-cdef-0123456789ab"
        d = tmp_path / "saida" / job_id
        d.mkdir(parents=True)
        (d / "video.timings.json").write_text(
            json.dumps({"totals": {"tokens": 4_242}}), encoding="utf-8")
        monkeypatch.setattr(app, "OUTPUT_DIR", str(tmp_path / "saida"))
        assert app._job_timings(job_id)["totals"]["tokens"] == 4_242

    def test_status_ignora_id_malformado(self, monkeypatch):
        app = pytest.importorskip("app")
        assert app._job_timings("../../etc/passwd") is None

    def test_sem_sidecar_devolve_none(self, tmp_path, monkeypatch):
        app = pytest.importorskip("app")
        job_id = "0123abcd-4567-89ab-cdef-0123456789ab"
        (tmp_path / "saida" / job_id).mkdir(parents=True)
        monkeypatch.setattr(app, "OUTPUT_DIR", str(tmp_path / "saida"))
        assert app._job_timings(job_id) is None
