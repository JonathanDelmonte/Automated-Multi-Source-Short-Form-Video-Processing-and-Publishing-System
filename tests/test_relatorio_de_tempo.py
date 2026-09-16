"""Onde vai o tempo -- Fase 5, bloco 5.3.

O `job_metrics` mede por estagio desde a Fase 0.5 e o bloco 3.3 grava em
`jobs.timings_json`. Ninguem lia isso entre jobs: cada execucao imprimia o
proprio resumo no log e o numero morria ali.

**Estes testes cobrem uma ferramenta de MEDIR, nao de consertar.** A tentacao,
diante de "esta lento", e abrir o `main.py` e procurar o culpado. O que este
modulo entrega e o numero que diz onde olhar -- e as observacoes apontam para
coisas VERIFICAVEIS ja escritas no repositorio, nunca para uma conclusao que
ninguem mediu.

O numero central e `fator_tempo_real`: tempo de parede / duracao da fonte. E o
unico que responde "esta lento" sem depender de quao longo era o video.
"""
import asyncio
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
timings_report = pytest.importorskip("timings_report")


def corre(coro_fn):
    return asyncio.run(coro_fn())


def _timings(parede=2200.0, fonte=600.0, falada=540.0, tokens=31200,
             estagios=None):
    return {
        "facts": {"source_seconds": fonte, "spoken_seconds": falada},
        "stages": estagios if estagios is not None else {
            "01_ingest": {"seconds": 30},
            "03_transcribe": {"seconds": 1800},
            "04_detect": {"seconds": 40},
            "05_06_render": {"seconds": 330},
        },
        "totals": {"tokens": tokens, "calls": 6},
        "wall_seconds": parede,
    }


# --------------------------------------------------------------------------- #
# A conta
# --------------------------------------------------------------------------- #

class TestFatorTempoReal:

    def test_e_parede_sobre_fonte(self):
        """Um video de 10 min que leva 40 e 4,0x. E a unica grandeza que
        responde "esta lento" sem depender de quao longo era o video."""
        r = timings_report.agregar([_timings(parede=2400.0, fonte=600.0)])
        assert r["fator_tempo_real"] == 4.0

    def test_sem_duracao_da_fonte_e_None_e_nao_1(self):
        """Sem a duracao nao da para dizer se 40 minutos foi rapido ou lento.
        Inventar 1,0x seria pior que nao responder."""
        r = timings_report.agregar([_timings(fonte=0.0)])
        assert r["fator_tempo_real"] is None

    def test_soma_entre_jobs(self):
        r = timings_report.agregar([_timings(parede=600.0, fonte=600.0),
                                    _timings(parede=1800.0, fonte=600.0)])
        assert r["jobs"] == 2
        assert r["fator_tempo_real"] == 2.0     # 2400 / 1200


class TestEstagios:

    def test_a_fatia_de_cada_um(self):
        r = timings_report.agregar([_timings(parede=2200.0)])
        fatias = {e["estagio"]: e["fatia"] for e in r["estagios"]}
        assert fatias["03_transcribe"] == pytest.approx(0.818, abs=0.002)
        assert sum(fatias.values()) == pytest.approx(1.0, abs=0.01)

    def test_a_ordem_e_a_do_pipeline_e_nao_a_do_tamanho(self):
        """Ler na ordem em que acontece e o que deixa ver ONDE ele engasga."""
        r = timings_report.agregar([_timings()])
        assert [e["estagio"] for e in r["estagios"]] == [
            "01_ingest", "03_transcribe", "04_detect", "05_06_render"]

    def test_estagio_desconhecido_vai_para_o_fim(self):
        r = timings_report.agregar([_timings(estagios={
            "99_novo": {"seconds": 5}, "01_ingest": {"seconds": 10}})])
        assert [e["estagio"] for e in r["estagios"]] == ["01_ingest", "99_novo"]


class TestObservacoes:

    def test_aponta_o_estagio_dominante(self):
        r = timings_report.agregar([_timings()])
        assert any("03_transcribe" in o and "81%" in o for o in r["observacoes"])

    def test_a_transcricao_dominante_manda_conferir_a_GPU(self):
        """Aponta para algo VERIFICAVEL que ja esta escrito no repositorio --
        sem a placa no container, `WHISPER_DEVICE=cuda` cai para CPU em
        silencio. Nao para uma conclusao que ninguem mediu."""
        r = timings_report.agregar([_timings()])
        juntas = " ".join(r["observacoes"])
        assert "WHISPER_DEVICE" in juntas and "silencio" in juntas

    def test_o_render_dominante_manda_olhar_o_numero_de_cortes(self):
        r = timings_report.agregar([_timings(parede=1000.0, estagios={
            "03_transcribe": {"seconds": 10}, "05_06_render": {"seconds": 990}})])
        assert any("cortes" in o for o in r["observacoes"])

    def test_tempo_fora_de_estagio_e_o_assunto_quando_e_grande(self):
        """Espera na fila, subida do subprocesso, ou um pedaco sem
        instrumentacao. Sem esta linha ele seria invisivel: cada estagio
        pareceria pequeno sem que nada explicasse por que."""
        r = timings_report.agregar([_timings(parede=2000.0, estagios={
            "03_transcribe": {"seconds": 200}})])
        assert r["fora_de_estagio_seconds"] == 1800.0
        assert any("nao esta em estagio nenhum" in o for o in r["observacoes"])

    def test_com_tudo_medido_nao_reclama_de_tempo_fora(self):
        r = timings_report.agregar([_timings(parede=2200.0)])
        assert r["fora_de_estagio_seconds"] == 0.0
        assert not any("estagio nenhum" in o for o in r["observacoes"])

    def test_sem_estagio_dominante_nao_inventa_culpado(self):
        """Quatro estagios parecidos nao tem culpado, e dizer que tem seria
        exatamente o palpite que este modulo existe para nao dar."""
        r = timings_report.agregar([_timings(parede=400.0, estagios={
            "01_ingest": {"seconds": 100}, "03_transcribe": {"seconds": 100},
            "04_detect": {"seconds": 100}, "05_06_render": {"seconds": 100}})])
        assert not any("% do tempo de parede" in o for o in r["observacoes"])

    def test_diz_quando_a_amostra_e_pequena(self):
        """Um job aponta onde olhar; nao calibra."""
        r = timings_report.agregar([_timings()])
        assert any("Amostra de 1" in o for o in r["observacoes"])
        muitos = timings_report.agregar([_timings() for _ in range(5)])
        assert not any("Amostra de" in o for o in muitos["observacoes"])

    def test_tokens_por_minuto_falado_e_comparado_com_o_ADR_004(self):
        r = timings_report.agregar([_timings()])
        assert r["tokens_por_minuto_falado"] == pytest.approx(3466.7, abs=0.1)
        assert any("ADR-004" in o for o in r["observacoes"])


class TestEntradaTorta:

    @pytest.mark.parametrize("ruim", [
        None, {}, [], "texto", 42, {"stages": "nao e dict"},
        {"facts": None, "stages": None, "totals": None},
    ])
    def test_nao_derruba_o_relatorio(self, ruim):
        """Um job que morreu no meio gravou o que deu. O pedaco medido continua
        valendo, e o relatorio nao pode explodir por causa do resto."""
        assert timings_report.agregar([ruim]) is not None

    def test_job_interrompido_soma_os_estagios_que_deu(self):
        """Sem `wall_seconds` -- o job nem chegou ao fim -- a soma dos estagios
        e o que ha, e e melhor que zero."""
        r = timings_report.agregar([{
            "facts": {"source_seconds": 600.0},
            "stages": {"01_ingest": {"seconds": 30},
                       "03_transcribe": {"seconds": 570}}}])
        assert r["wall_seconds"] == 600.0

    def test_lista_vazia_responde_em_vez_de_quebrar(self):
        r = timings_report.agregar([])
        assert r["jobs"] == 0 and r["fator_tempo_real"] is None

    def test_numero_absurdo_nao_vira_infinito(self):
        r = timings_report.agregar([_timings(parede=float("inf"))])
        assert r["wall_seconds"] >= 0


# --------------------------------------------------------------------------- #
# O endpoint
# --------------------------------------------------------------------------- #

@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(url):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.get(url)
    return asyncio.run(_do())


def _job_no_banco(timings):
    job_id = str(uuid.uuid4())

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.marcar_job(job_id, status="completed", timings=timings)
    corre(_t)
    return job_id


def _sidecar(raiz, job_id, timings, tenant=None):
    pasta = raiz / job_id
    pasta.mkdir(exist_ok=True)
    (pasta / app_module.ARQUIVO_TENANT).write_text(
        tenant or db.SELF_HOST_TENANT_ID)
    (pasta / "v.timings.json").write_text(json.dumps(timings))


class TestEndpoint:

    def test_le_o_banco(self, ambiente):
        _job_no_banco(_timings(parede=1200.0, fonte=600.0))
        corpo = _chama("/api/tempo").json()
        assert corpo["jobs"] == 1
        assert corpo["fator_tempo_real"] == 2.0
        assert corpo["fonte"] == {"banco": 1, "disco": 0}

    def test_le_o_sidecar_de_job_que_o_banco_nao_tem(self, ambiente):
        """O sidecar existe desde a Fase 0.5; a linha no banco so desde o bloco
        3.3. So os dois juntos cobrem as PRIMEIRAS execucoes -- que sao
        justamente as que ninguem mediu."""
        _sidecar(ambiente, str(uuid.uuid4()), _timings(parede=900.0, fonte=300.0))
        corpo = _chama("/api/tempo").json()
        assert corpo["jobs"] == 1
        assert corpo["fonte"] == {"banco": 0, "disco": 1}

    def test_nao_conta_o_mesmo_job_duas_vezes(self, ambiente):
        """Somado duas vezes, o tempo de parede dobra e o fator cai pela
        metade -- uma media que mente para os dois lados ao mesmo tempo."""
        job_id = _job_no_banco(_timings(parede=1200.0, fonte=600.0))
        _sidecar(ambiente, job_id, _timings(parede=1200.0, fonte=600.0))
        corpo = _chama("/api/tempo").json()
        assert corpo["jobs"] == 1
        assert corpo["fator_tempo_real"] == 2.0

    def test_junta_banco_e_disco_quando_sao_jobs_diferentes(self, ambiente):
        _job_no_banco(_timings(parede=600.0, fonte=600.0))
        _sidecar(ambiente, str(uuid.uuid4()), _timings(parede=1800.0, fonte=600.0))
        corpo = _chama("/api/tempo").json()
        assert corpo["jobs"] == 2
        assert corpo["fator_tempo_real"] == 2.0

    def test_sidecar_de_outro_tenant_nao_entra(self, ambiente):
        _sidecar(ambiente, str(uuid.uuid4()), _timings(), tenant="outro-tenant")
        assert _chama("/api/tempo").json()["jobs"] == 0

    def test_sem_job_nenhum_responde(self, ambiente):
        corpo = _chama("/api/tempo").json()
        assert corpo["jobs"] == 0 and corpo["observacoes"] == []

    def test_sidecar_corrompido_e_pulado(self, ambiente):
        job_id = str(uuid.uuid4())
        pasta = ambiente / job_id
        pasta.mkdir()
        (pasta / app_module.ARQUIVO_TENANT).write_text(db.SELF_HOST_TENANT_ID)
        (pasta / "v.timings.json").write_text("{nao e json")
        assert _chama("/api/tempo").json()["jobs"] == 0

    def test_o_limite_corta(self, ambiente):
        for _ in range(4):
            _job_no_banco(_timings())
        assert _chama("/api/tempo?limite=2").json()["jobs"] == 2
