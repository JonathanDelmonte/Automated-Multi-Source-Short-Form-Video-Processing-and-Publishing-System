"""Os projetos ficam no disco de quem usa ate essa pessoa apaga-los.

O autor perguntou onde os projetos estavam salvos (22-set-2026) e pediu que
ficassem "a todo momento" no computador da pessoa. Ja ficavam -- `output/` e a
pasta do repositorio, montada no container --, mas duas coisas os apagavam
sozinhas: a varredura por idade (24h no self-host) e o teto de 25 GB, que o
upstream justificava com um arquivo no R2 que este fork nao tem.

O que estes testes prendem:

1. o padrao do self-host e NUNCA (0) nos dois;
2. o 0 quer dizer nunca DE VERDADE. Sem guarda, `now - mtime > 0` vale para
   todo arquivo, e o valor que devia desligar a limpeza apagaria tudo na
   primeira volta -- inclusive o upload do job que esta rodando;
3. quem poe um numero no `.env` continua tendo a varredura;
4. apagar o projeto leva o video ENVIADO junto, porque agora nada mais o tira.
"""
import asyncio
import os
import time

import httpx
import pytest

app_module = pytest.importorskip("app")

UM_ANO = 365 * 86400


def _envelhecer(caminho, segundos):
    antes = time.time() - segundos
    os.utime(caminho, (antes, antes))


@pytest.fixture()
def disco(tmp_path, monkeypatch):
    """Um `output/` com um projeto de um ano atras e um `uploads/` idem."""
    saida = tmp_path / "output"
    envios = tmp_path / "uploads"
    saida.mkdir()
    envios.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(envios))

    projeto = saida / "projeto-velho"
    projeto.mkdir()
    (projeto / "video_clip_1.mp4").write_bytes(b"corte")
    _envelhecer(projeto, UM_ANO)

    enviado = envios / "projeto-velho_video.mp4"
    enviado.write_bytes(b"fonte")
    _envelhecer(enviado, UM_ANO)
    return saida, envios


class TestPadrao:

    def test_self_host_nunca_apaga_por_idade(self):
        if "JOB_RETENTION_SECONDS" in os.environ:
            pytest.skip("o ambiente definiu JOB_RETENTION_SECONDS")
        assert app_module.JOB_RETENTION_SECONDS == 0

    def test_self_host_nunca_apaga_por_tamanho(self):
        if "OUTPUT_MAX_GB" in os.environ:
            pytest.skip("o ambiente definiu OUTPUT_MAX_GB")
        assert app_module.OUTPUT_MAX_GB == 0


class TestZeroEhNunca:

    def test_projeto_de_um_ano_continua_la(self, disco, monkeypatch):
        saida, envios = disco
        monkeypatch.setattr(app_module, "JOB_RETENTION_SECONDS", 0)
        monkeypatch.setattr(app_module, "SOURCE_RETENTION_SECONDS", 0)
        monkeypatch.setattr(app_module, "OUTPUT_MAX_GB", 0)

        app_module._limpar_uma_vez(time.time())

        assert (saida / "projeto-velho" / "video_clip_1.mp4").exists()
        assert (envios / "projeto-velho_video.mp4").exists()

    def test_nem_o_upload_de_agora_some(self, disco, monkeypatch):
        """O caso que a guarda existe para impedir: com 0 e sem guarda, o
        arquivo recem-enviado de um job em andamento tambem 'passou de 0s'."""
        _saida, envios = disco
        monkeypatch.setattr(app_module, "JOB_RETENTION_SECONDS", 0)
        agora = envios / "job-rodando_video.mp4"
        agora.write_bytes(b"fonte")

        app_module._limpar_uma_vez(time.time() + 5)

        assert agora.exists()

    def test_teto_zero_nao_apaga_nada(self, disco, monkeypatch):
        saida, _envios = disco
        monkeypatch.setattr(app_module, "OUTPUT_MAX_GB", 0)
        app_module._enforce_output_size_cap()
        assert (saida / "projeto-velho").exists()


class TestQuemPedeContinuaTendo:

    def test_um_numero_no_env_religa_a_varredura(self, disco, monkeypatch):
        saida, envios = disco
        monkeypatch.setattr(app_module, "JOB_RETENTION_SECONDS", 86400)
        monkeypatch.setattr(app_module, "SOURCE_RETENTION_SECONDS", 86400)
        novo = saida / "projeto-de-hoje"
        novo.mkdir()

        app_module._limpar_uma_vez(time.time())

        assert not (saida / "projeto-velho").exists()
        assert not (envios / "projeto-velho_video.mp4").exists()
        assert novo.exists()

    def test_fonte_retida_sai_mesmo_com_o_projeto_para_sempre(self, disco, monkeypatch):
        """SOURCE_RETENTION_SECONDS pedido de proposito tem de valer com o
        relogio do job em 0 -- comparar so os numeros diria que qualquer valor
        e 'maior ou igual' a 0 e nunca varreria."""
        saida, _envios = disco
        projeto = saida / "projeto-velho"
        (projeto / "x_metadata.json").write_text('{"source_video": "fonte.mp4"}')
        fonte = projeto / "fonte.mp4"
        fonte.write_bytes(b"download")
        _envelhecer(fonte, UM_ANO)
        monkeypatch.setattr(app_module, "JOB_RETENTION_SECONDS", 0)
        monkeypatch.setattr(app_module, "SOURCE_RETENTION_SECONDS", 3600)

        assert list(app_module._sweep_retained_sources()) == ["projeto-velho"]
        assert not fonte.exists()
        assert (projeto / "video_clip_1.mp4").exists()


def test_apagar_o_projeto_leva_o_video_enviado(disco, monkeypatch):
    saida, envios = disco
    vizinho = envios / "outro-projeto_video.mp4"
    vizinho.write_bytes(b"fonte do vizinho")

    async def _apagar():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            return await c.delete("/api/jobs/projeto-velho")

    r = asyncio.run(_apagar())

    assert r.status_code == 200
    assert not (saida / "projeto-velho").exists()
    assert not (envios / "projeto-velho_video.mp4").exists()
    assert vizinho.exists()
