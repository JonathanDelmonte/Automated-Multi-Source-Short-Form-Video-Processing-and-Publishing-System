"""HTTP: /api/process recusa no submit a fonte que ainda nao sabe buscar.

O `main.py` tambem recusa, e recusar aqui e o que faz a diferenca aparecer: no
formulario, na hora, em vez de virar um job vermelho no historico dez segundos
depois. Tambem poupa o probe de qualidade, que para uma live nao responde nada
util.
"""
import asyncio

import httpx
import pytest

app_module = pytest.importorskip("app")


def _post(json_body):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.post("/api/process", json=json_body,
                                     headers={"X-Gemini-Key": "test-key"})
    return asyncio.run(_do())


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    out_root = tmp_path / "output"
    up_root = tmp_path / "uploads"
    out_root.mkdir(); up_root.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out_root))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(up_root))
    return out_root, up_root


@pytest.fixture()
def probe_nunca_chamado(monkeypatch):
    """O probe nao pode nem ser tentado numa fonte que sera recusada."""
    chamadas = []

    async def _probe(url):
        chamadas.append(url)
        return {"max_height": 1080, "duration": 3600}

    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    return chamadas


class TestLiveDaTwitch:
    def test_canal_ao_vivo_e_recusado(self, dirs, probe_nunca_chamado):
        resp = _post({"url": "https://www.twitch.tv/gaules", "acknowledged": True})
        assert resp.status_code == 400
        detalhe = resp.json()["detail"]
        assert "1.5" in detalhe and "/videos/" in detalhe, detalhe

    def test_lista_de_videos_do_canal_e_recusada(self, dirs, probe_nunca_chamado):
        resp = _post({"url": "https://www.twitch.tv/gaules/videos", "acknowledged": True})
        assert resp.status_code == 400
        assert "lista de videos" in resp.json()["detail"]

    def test_nao_gasta_probe_numa_fonte_recusada(self, dirs, probe_nunca_chamado):
        _post({"url": "https://www.twitch.tv/gaules", "acknowledged": True})
        assert probe_nunca_chamado == [], (
            "a recusa tem que vir antes do probe: numa live ele nao responde "
            "duracao nenhuma e, em modo cloud, custa banda paga")

    def test_nenhum_job_e_criado(self, dirs, probe_nunca_chamado):
        antes = dict(app_module.jobs)
        _post({"url": "https://www.twitch.tv/gaules", "acknowledged": True})
        assert dict(app_module.jobs) == antes


class TestFontesQuePassam:
    """O portao recusa a live e nao pode recusar mais nada."""

    @pytest.mark.parametrize("url", [
        "https://www.twitch.tv/videos/123456789",
        "https://clips.twitch.tv/AlgumSlug",
        "https://www.youtube.com/watch?v=abc",
        "https://cdn.exemplo.com/video.mp4",
    ])
    def test_passa_do_portao(self, dirs, monkeypatch, url):
        # Curto de proposito: o 400 que interessa aqui e o do portao de duracao,
        # que so e alcancavel DEPOIS do portao de fonte. Se a fonte tivesse sido
        # recusada, a mensagem seria outra.
        async def _probe(_url):
            return {"max_height": 1080, "duration": 5}
        monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)

        resp = _post({"url": url, "acknowledged": True})
        assert resp.status_code == 400
        assert "5s long" in resp.json()["detail"], (
            "chegou ao portao de duracao, ou seja, passou pelo de fonte")
