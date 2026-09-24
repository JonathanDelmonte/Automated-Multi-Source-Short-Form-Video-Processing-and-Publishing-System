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


# --------------------------------------------------------------------------- #
# Parede x ocupado (16-set-2026)
# --------------------------------------------------------------------------- #

class _Relogio:
    """Relogio controlado, no lugar do modulo `time` DENTRO do job_metrics.

    Trocar `job_metrics.time` e nao `job_metrics.time.time`: o segundo e o
    modulo `time` global, e mexer nele afeta todo o processo (foi assim que um
    teste de auth entrou em recursao nesta mesma sessao). E sem relogio falso
    este teste dependeria de `sleep`, que e justamente o tipo de teste que
    falha uma vez em vinte no CI.
    """

    def __init__(self, inicio=1000.0):
        self.agora = inicio

    def time(self):
        return self.agora

    def avanca(self, segundos):
        self.agora += segundos


class TestParedeEOcupado:
    """O defeito: o laco de cortes roda em `ThreadPoolExecutor` e cada worker
    somava a propria duracao no MESMO estagio. Com `CLIP_WORKERS=3` um render
    de 200 s de parede gravava 600 s -- fatia de 1,0 sobre a parede do job,
    `fora_de_estagio` negativo (escondido por `max(0, ...)`) e, porque o
    relatorio acusa o primeiro estagio acima de 50% na ordem do pipeline, a
    transcricao levando a culpa do render."""

    def test_sobreposicao_conta_uma_vez_na_parede_e_duas_no_ocupado(self, monkeypatch):
        relogio = _Relogio()
        monkeypatch.setattr(job_metrics, "time", relogio)
        job_metrics.reset(".", "video")

        externo = job_metrics.stage("05_06_render")
        externo.__enter__()                      # worker A entra em t=0
        relogio.avanca(10)
        interno = job_metrics.stage("05_06_render")
        interno.__enter__()                      # worker B entra em t=10
        relogio.avanca(10)
        interno.__exit__(None, None, None)       # B sai em t=20 (ocupou 10)
        relogio.avanca(10)
        externo.__exit__(None, None, None)       # A sai em t=30 (ocupou 30)

        s = job_metrics.snapshot()["stages"]["05_06_render"]
        assert s["seconds"] == 40.0        # trabalho gasto: 30 + 10
        assert s["wall_seconds"] == 30.0   # o que a pessoa esperou: t=0 a t=30
        assert s["entries"] == 2

    def test_a_parede_de_um_estagio_nunca_passa_a_do_job(self):
        """A invariante que o defeito quebrava, e a unica que importa para o
        relatorio: se a soma dos estagios passa da parede do job, as fatias
        somam mais de 100% e a conta deixa de querer dizer alguma coisa."""
        from concurrent.futures import ThreadPoolExecutor

        job_metrics.reset(".", "video")
        comeco = time.time()

        def um_corte(_):
            with job_metrics.stage("05_06_render"):
                time.sleep(0.05)

        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(um_corte, range(6)))

        decorrido = time.time() - comeco
        s = job_metrics.snapshot()["stages"]["05_06_render"]
        assert s["entries"] == 6
        assert s["seconds"] >= 0.29                # o ocupado continua somando (6 x 50ms)
        assert s["wall_seconds"] <= decorrido + 0.05

    def test_a_pilha_e_por_thread(self):
        """Com a pilha global, a chamada de LLM de um worker era creditada ao
        estagio que outro worker tivesse deixado no topo -- e qual deles
        dependia do escalonador. O `hook_grounding` chama o Gemini de dentro
        deste laco, entao nao e hipotetico."""
        import threading

        visto = {}
        pronto = threading.Event()

        def outra_thread():
            visto["antes"] = job_metrics.current_stage()
            with job_metrics.stage("04_detect"):
                visto["dentro"] = job_metrics.current_stage()
            pronto.set()

        job_metrics.reset(".", "video")
        with job_metrics.stage("05_06_render"):
            t = threading.Thread(target=outra_thread)
            t.start()
            pronto.wait(5)
            t.join()
            assert job_metrics.current_stage() == "05_06_render"

        # A thread nova nao herda a pilha de quem a criou.
        assert visto["antes"] is None
        assert visto["dentro"] == "04_detect"


class TestSubstage:
    def test_nao_anuncia_na_barra(self, capsys):
        """A barra do painel so conhece os cinco nomes de `PIPELINE_STAGES`:
        `_stage_view` devolve `stage_index` 0 para qualquer outro, ou seja, a
        barra volta ao inicio. Medicao fina nao pode custar isso."""
        job_metrics.reset(".", "video")
        with job_metrics.stage("05_06_render"):
            with job_metrics.substage("06_legenda"):
                pass
        saida = capsys.readouterr().out
        assert f"{job_metrics.STAGE_MARKER}BEGIN 05_06_render" in saida
        assert "06_legenda" not in saida

    def test_nao_soma_com_os_estagios(self):
        """Ele mede POR DENTRO de um estagio: somar os dois contaria o mesmo
        tempo duas vezes e deixaria `fora_de_estagio` negativo de novo."""
        relogio = _Relogio()
        job_metrics.reset(".", "video")
        s = job_metrics.snapshot()
        assert "substages" in s

        with job_metrics.stage("05_06_render"):
            with job_metrics.substage("06_legenda"):
                pass
        s = job_metrics.snapshot()
        assert "06_legenda" in s["substages"]
        assert "06_legenda" not in s["stages"]
        # `totals.seconds` soma so os estagios, e e o que o relatorio subtrai
        # da parede do job.
        assert s["totals"]["seconds"] == pytest.approx(
            s["stages"]["05_06_render"]["wall_seconds"], abs=0.01)
        assert relogio  # noqa: usado acima via _Relogio

    def test_os_tokens_vao_para_o_passe_que_os_gastou(self):
        """O `hook_grounding` e uma chamada de LLM por corte e ninguem a
        contava: nem o tempo (fora de estagio) nem os tokens."""
        job_metrics.reset(".", "video")
        with job_metrics.stage("05_06_render"):
            with job_metrics.substage("06_hook_grounding"):
                job_metrics.add_llm({"input_tokens": 3000, "output_tokens": 60,
                                     "provider": "gemini"})
        s = job_metrics.snapshot()
        assert s["substages"]["06_hook_grounding"]["tokens_in"] == 3000
        assert s["stages"]["05_06_render"]["calls"] == 0
        # Mas o total do job inclui: um token gasto e um token gasto.
        assert s["totals"]["tokens"] == 3060
        assert s["totals"]["calls"] == 1


def test_substage_filho_sai_recuado_debaixo_do_pai():
    """`pai/filho` e um pedaco dentro de outro substage (o reenquadramento,
    desde 22-set-2026): sai com o nome curto, recuado, logo abaixo do pai --
    e nao como mais uma linha do mesmo nivel, que convidaria a somar os dois."""
    job_metrics.reset()
    with job_metrics.stage("05_06_render"):
        with job_metrics.substage("06_reenquadra"):
            with job_metrics.substage("06_reenquadra/1_cenas"):
                pass
    linhas = job_metrics.summary_line().splitlines()
    i_pai = next(i for i, l in enumerate(linhas) if "└ 06_reenquadra" in l)
    assert "  └ 1_cenas" in linhas[i_pai + 1]
    assert "06_reenquadra/1_cenas" not in "\n".join(linhas)


class TestRetomar:
    """A espera pelo video que baixa em paralelo e ingest (24-set-2026).

    Com o `audio_primeiro`, o `01_ingest` termina quando o AUDIO chega. Se o
    video ainda nao chegou quando o corte precisa dele, esse tempo tambem e
    download -- mas anunciar o estagio de novo faria a barra voltar ao comeco.
    """

    def test_soma_no_mesmo_estagio(self, monkeypatch):
        relogio = _Relogio()
        monkeypatch.setattr(job_metrics, "time", relogio)
        job_metrics.reset(".", "video")
        with job_metrics.stage("01_ingest"):
            relogio.avanca(10)
        with job_metrics.stage("03_transcribe"):
            relogio.avanca(40)
        with job_metrics.retomar("01_ingest"):
            relogio.avanca(5)
        s = job_metrics.snapshot()["stages"]
        assert s["01_ingest"]["wall_seconds"] == 15.0
        assert s["01_ingest"]["seconds"] == 15.0
        assert s["03_transcribe"]["wall_seconds"] == 40.0

    def test_nao_move_a_barra(self, capsys):
        job_metrics.reset(".", "video")
        with job_metrics.stage("01_ingest"):
            pass
        capsys.readouterr()
        with job_metrics.retomar("01_ingest"):
            pass
        assert job_metrics.STAGE_MARKER not in capsys.readouterr().out
