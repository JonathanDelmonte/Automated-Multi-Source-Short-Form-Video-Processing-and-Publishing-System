"""Aplicar o template a um clipe, e o preview de 3 s (Fase 2, bloco 2.2).

Dois contratos que o §5 trava e estes testes guardam:

- **o documento manda no estilo**, e não o contrário. Se os campos soltos do
  modal vencessem campo a campo, o template seria decorativo: o modal manda
  todos eles sempre, preenchidos com os próprios defaults.
- **preview não é entregável.** Apontar o `video_url` do clipe para um trecho
  de 3 s seria perder o clipe de vista.
"""
import asyncio
import json
import os

import httpx
import pytest

app_module = pytest.importorskip("app")


@pytest.fixture()
def job(tmp_path, monkeypatch):
    """Um job na forma que o endpoint espera: metadata, transcrição e um mp4."""
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out))
    jid = "j1"
    d = out / jid
    d.mkdir()

    palavras = [{"word": f" p{i}", "start": i * 0.5, "end": i * 0.5 + 0.4}
                for i in range(20)]
    data = {
        "transcript": {"language": "pt", "segments": [
            {"start": 0.0, "end": 10.0, "text": " ".join(w["word"] for w in palavras),
             "words": palavras}]},
        "shorts": [{"start": 0.0, "end": 10.0,
                    "video_url": f"/videos/{jid}/base_clip_1.mp4"}],
    }
    (d / "base_metadata.json").write_text(json.dumps(data))
    (d / "base_clip_1.mp4").write_bytes(b"\0" * 2048)

    app_module.jobs[jid] = {"status": "completed", "logs": [],
                            "result": {"clips": [{"video_url": f"/videos/{jid}/base_clip_1.mp4"}]}}
    yield jid, d
    app_module.jobs.pop(jid, None)


@pytest.fixture()
def espiao(monkeypatch):
    """Troca geração e queima por espiões: o que importa aqui são os argumentos."""
    visto = {}

    def _gera_ass(transcript, ini, fim, caminho, **kwargs):
        visto["ass_kwargs"] = kwargs
        open(caminho, "w").write("[Script Info]\n")
        return True

    def _queima(entrada, srt, saida, **kwargs):
        visto["burn_in"] = entrada
        visto["burn_out"] = saida
        open(saida, "wb").write(b"\0" * 512)

    def _corta(entrada, destino, ini, fim, n):
        visto["cut"] = (entrada, destino, ini, fim)
        open(destino, "wb").write(b"\0" * 256)

    monkeypatch.setattr(app_module, "generate_ass", _gera_ass)
    monkeypatch.setattr(app_module, "burn_subtitles", _queima)
    monkeypatch.setattr(app_module, "cut_clip", _corta)
    monkeypatch.setattr(app_module, "_archive_clip_edit_bg", lambda *a, **k: None)
    return visto


def _post(corpo):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.post("/api/subtitle", json=corpo,
                                     headers={"X-Gemini-Key": "k"})
    return asyncio.run(_do())


class TestODocumentoManda:
    def test_preset_chega_ao_gerador(self, job, espiao):
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0,
                   "template": {"captions": {"preset": "limpo"}}})
        assert r.status_code == 200, r.text
        assert espiao["ass_kwargs"]["font_name"] == "Verdana"

    def test_vence_os_campos_soltos_do_modal(self, job, espiao):
        # O modal manda todos os campos sempre; se eles vencessem, o template
        # nunca teria efeito nenhum.
        jid, _ = job
        _post({"job_id": jid, "clip_index": 0,
               "font_name": "Comic Sans", "font_size": 9, "style": "classic",
               "template": {"captions": {"preset": "karaoke_fill"}}})
        assert espiao["ass_kwargs"]["font_name"] == "Anton"
        assert espiao["ass_kwargs"]["fontsize"] == 44

    def test_safe_area_vira_margem(self, job, espiao):
        import template as t
        jid, _ = job
        _post({"job_id": jid, "clip_index": 0,
               "template": {"safeArea": {"bottomPct": 25}}})
        assert espiao["ass_kwargs"]["margin_v"] == t.margem_vertical(
            {"safeArea": {"bottomPct": 25}})

    def test_sempre_pelo_caminho_ass(self, job, espiao):
        # Só o ASS aceita realce por palavra, efeito, base apagada e a legenda
        # na costura de um SPLIT. E o `burn_subtitles` não aplica force_style
        # sobre `.ass`, então os estilos do documento chegam intactos.
        jid, _ = job
        _post({"job_id": jid, "clip_index": 0, "style": "classic",
               "template": {"captions": {"preset": "limpo"}}})
        assert "ass_kwargs" in espiao, "o caminho SRT ignoraria o documento"

    def test_template_invalido_e_400_com_a_razao(self, job, espiao):
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0,
                   "template": {"captions": {"preset": "nao_existe"}}})
        assert r.status_code == 400
        assert "karaoke_fill" in r.json()["detail"]

    def test_sem_template_nada_muda(self, job, espiao):
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0, "style": "karaoke",
                   "font_name": "Comic Sans"})
        assert r.status_code == 200
        assert espiao["ass_kwargs"]["font_name"] == "Comic Sans"
        assert "margin_v" not in espiao["ass_kwargs"]


class TestPreview:
    def test_corta_a_entrada_nao_a_legenda(self, job, espiao):
        # O ASS cobre o clipe inteiro; os eventos além do corte nunca aparecem.
        # Remapear timestamps aqui seria trabalho para o mesmo resultado.
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0, "preview_seconds": 3,
                   "template": {"captions": {"preset": "limpo"}}})
        assert r.status_code == 200, r.text
        entrada, destino, ini, fim = espiao["cut"]
        assert (ini, fim) == (0.0, 3.0)
        assert espiao["burn_in"] == destino, "a queima tem que usar o trecho cortado"

    def test_nao_mexe_no_clipe_entregavel(self, job, espiao):
        jid, d = job
        antes = json.loads((d / "base_metadata.json").read_text())["shorts"][0]["video_url"]
        r = _post({"job_id": jid, "clip_index": 0, "preview_seconds": 3})
        assert r.json()["preview"] is True
        depois = json.loads((d / "base_metadata.json").read_text())["shorts"][0]["video_url"]
        assert depois == antes, "preview não pode virar o vídeo do clipe"
        assert app_module.jobs[jid]["result"]["clips"][0]["video_url"] == antes

    def test_o_arquivo_do_preview_tem_nome_proprio(self, job, espiao):
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0, "preview_seconds": 3})
        assert "/preview_" in r.json()["new_video_url"]

    def test_limpa_o_trecho_intermediario(self, job, espiao):
        jid, d = job
        _post({"job_id": jid, "clip_index": 0, "preview_seconds": 3})
        assert not list(d.glob("previewsrc_*.mp4")), (
            "o corte intermediário não serve para nada depois da queima")

    @pytest.mark.parametrize("pedido,esperado", [
        (0.1, 0.5),      # piso: menos que isso não mostra nada
        (999, 30.0),     # teto: preview longo deixa de ser preview
        (3, 3.0),
    ])
    def test_duracao_e_limitada(self, job, espiao, pedido, esperado):
        jid, _ = job
        r = _post({"job_id": jid, "clip_index": 0, "preview_seconds": pedido})
        assert r.json()["seconds"] == esperado
        assert espiao["cut"][3] == esperado

    def test_sem_preview_o_clipe_e_atualizado_como_sempre(self, job, espiao):
        jid, d = job
        r = _post({"job_id": jid, "clip_index": 0, "style": "karaoke"})
        assert r.json().get("preview") is None
        novo = json.loads((d / "base_metadata.json").read_text())["shorts"][0]["video_url"]
        assert "/subtitled_" in novo
