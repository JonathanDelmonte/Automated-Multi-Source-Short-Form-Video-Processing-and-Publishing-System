"""Teto de upload: o §4 mira 10GB (Fase 1, metade do bloco 1.6).

A outra metade do requisito — *"upload grande gravado em disco por streaming e
nunca em memória"* — **já estava satisfeita**, herdada do upstream: o endpoint
lê em pedaços de 1MB e escreve direto no arquivo. O que limitava a 2GB era o
número, não a arquitetura.

Estes testes fixam as duas coisas que importam: o teto é configurável (disco é
restrição da máquina, não do projeto) e o arquivo parcial não fica para trás
quando o upload estoura.
"""
import asyncio
import importlib

import httpx
import pytest

app_module = pytest.importorskip("app")


class TestTeto:
    def test_padrao_e_o_alvo_do_plano(self):
        assert app_module.MAX_FILE_SIZE_MB == 10240, "10 GB, o alvo do §4"

    def test_env_manda(self, monkeypatch):
        monkeypatch.setenv("MAX_FILE_SIZE_MB", "512")
        recarregado = importlib.reload(app_module)
        try:
            assert recarregado.MAX_FILE_SIZE_MB == 512
        finally:
            monkeypatch.delenv("MAX_FILE_SIZE_MB", raising=False)
            importlib.reload(app_module)

    def test_convive_com_o_teto_do_diretorio(self):
        # Um upload de 10GB tem que caber em UPLOADS_MAX_GB, senão o arquivo
        # entra e a varredura o apaga em seguida.
        assert app_module.MAX_FILE_SIZE_MB / 1024 <= app_module.UPLOADS_MAX_GB


class TestArquivoGrandeDemais:
    def _post(self, tmp_path, monkeypatch, tamanho_mb, teto_mb):
        monkeypatch.setattr(app_module, "MAX_FILE_SIZE_MB", teto_mb)
        up = tmp_path / "uploads"
        out = tmp_path / "output"
        up.mkdir(); out.mkdir()
        monkeypatch.setattr(app_module, "UPLOAD_DIR", str(up))
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out))

        async def _do():
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://testserver") as client:
                return await client.post(
                    "/api/process",
                    files={"file": ("grande.mp4", b"\0" * (tamanho_mb * 1024 * 1024),
                                    "video/mp4")},
                    data={"acknowledged": "true"},
                    headers={"X-Gemini-Key": "k"})
        return asyncio.run(_do()), up, out

    def test_acima_do_teto_e_413(self, tmp_path, monkeypatch):
        resp, _, _ = self._post(tmp_path, monkeypatch, tamanho_mb=3, teto_mb=1)
        assert resp.status_code == 413
        assert "1MB" in resp.json()["detail"]

    def test_nao_deixa_o_arquivo_parcial_para_tras(self, tmp_path, monkeypatch):
        # Sem isto, um upload recusado ainda ocupa disco até a varredura passar
        # — e num teto de 10GB o parcial é grande.
        resp, up, out = self._post(tmp_path, monkeypatch, tamanho_mb=3, teto_mb=1)
        assert resp.status_code == 413
        assert list(up.iterdir()) == []
        assert list(out.iterdir()) == []
