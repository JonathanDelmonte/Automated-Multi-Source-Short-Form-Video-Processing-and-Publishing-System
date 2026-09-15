"""CRUD de templates (Fase 2, bloco 2.3).

Primeiro uso do banco por um caminho do pipeline: até aqui só os testes de
schema chamavam `db.tenant()`.

O contrato que estes testes guardam é o da §5: **salvar cria uma versão, nunca
sobrescreve**. Sobrescrever perderia a única coisa que a versão serve para dar
— poder voltar ao estilo de antes depois de mexer.
"""
import asyncio

import httpx
import pytest

app_module = pytest.importorskip("app")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")
db_models = pytest.importorskip("db_models")


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield
    db.reset_engine()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo)
    return asyncio.run(_do())


class TestListar:
    def test_o_seed_ja_deixa_um_template(self, banco):
        r = _chama("GET", "/api/templates")
        assert r.status_code == 200, r.text
        nomes = [t["name"] for t in r.json()["templates"]]
        assert "Padrao Cortes" in nomes

    def test_manda_os_presets_junto(self, banco):
        # Duas chamadas para pintar um seletor seriam uma a mais.
        corpo = _chama("GET", "/api/templates").json()
        assert len(corpo["presets"]) == 6
        assert "karaoke_fill" in corpo["presets"]
        assert corpo["padrao"]["safeArea"]["bottomPct"] == 18

    def test_so_a_ultima_versao_de_cada_nome(self, banco):
        for _ in range(3):
            _chama("POST", "/api/templates",
                   {"name": "Meu", "spec": {"captions": {"preset": "limpo"}}})
        lista = [t for t in _chama("GET", "/api/templates").json()["templates"]
                 if t["name"] == "Meu"]
        assert len(lista) == 1
        assert lista[0]["version"] == 3


class TestSalvar:
    def test_cria_a_versao_1(self, banco):
        r = _chama("POST", "/api/templates",
                   {"name": "Novo", "spec": {"captions": {"preset": "centro"}}})
        assert r.status_code == 200, r.text
        assert r.json()["version"] == 1
        assert r.json()["spec"]["captions"]["preset"] == "centro"

    def test_salvar_de_novo_versiona_em_vez_de_sobrescrever(self, banco):
        _chama("POST", "/api/templates", {"name": "X", "spec": {"captions": {"preset": "limpo"}}})
        r2 = _chama("POST", "/api/templates", {"name": "X", "spec": {"captions": {"preset": "centro"}}})
        assert r2.json()["version"] == 2

        async def _conta():
            async with db.tenant() as t:
                return await t.all(db_models.Template, db_models.Template.name == "X")
        assert len(asyncio.run(_conta())) == 2, "a versão anterior tem que continuar lá"

    def test_completa_o_spec_com_os_defaults(self, banco):
        r = _chama("POST", "/api/templates", {"name": "Curto", "spec": {}})
        spec = r.json()["spec"]
        assert spec["safeArea"] == {"topPct": 12, "bottomPct": 18}
        assert spec["captions"]["preset"] == "karaoke_fill"

    def test_nome_do_corpo_vence_o_do_spec(self, banco):
        r = _chama("POST", "/api/templates",
                   {"name": "DeFora", "spec": {"name": "DeDentro"}})
        assert r.json()["name"] == "DeFora"

    def test_spec_invalido_e_400_com_a_razao(self, banco):
        r = _chama("POST", "/api/templates",
                   {"name": "Ruim", "spec": {"captions": {"preset": "nao_existe"}}})
        assert r.status_code == 400
        assert "karaoke_fill" in r.json()["detail"]

    def test_nada_e_gravado_quando_o_spec_e_invalido(self, banco):
        _chama("POST", "/api/templates",
               {"name": "Ruim", "spec": {"safeArea": {"topPct": 90}}})
        nomes = [t["name"] for t in _chama("GET", "/api/templates").json()["templates"]]
        assert "Ruim" not in nomes


class TestApagar:
    def test_leva_todas_as_versoes(self, banco):
        # Apagar só uma versão deixaria o template vivo com o estilo antigo,
        # que não é o que alguém quer dizer com "apagar este template".
        _chama("POST", "/api/templates", {"name": "Y", "spec": {"captions": {"preset": "limpo"}}})
        r2 = _chama("POST", "/api/templates", {"name": "Y", "spec": {"captions": {"preset": "centro"}}})
        r = _chama("DELETE", f"/api/templates/{r2.json()['id']}")
        assert r.status_code == 200
        assert r.json()["versoes_apagadas"] == 2
        nomes = [t["name"] for t in _chama("GET", "/api/templates").json()["templates"]]
        assert "Y" not in nomes

    def test_apagar_por_uma_versao_antiga_tambem_leva_tudo(self, banco):
        r1 = _chama("POST", "/api/templates", {"name": "Z", "spec": {}})
        _chama("POST", "/api/templates", {"name": "Z", "spec": {"captions": {"preset": "centro"}}})
        r = _chama("DELETE", f"/api/templates/{r1.json()['id']}")
        assert r.json()["versoes_apagadas"] == 2

    def test_id_inexistente_e_404(self, banco):
        assert _chama("DELETE", "/api/templates/nao-existe").status_code == 404

    def test_nao_derruba_os_outros(self, banco):
        r = _chama("POST", "/api/templates", {"name": "A", "spec": {}})
        _chama("POST", "/api/templates", {"name": "B", "spec": {}})
        _chama("DELETE", f"/api/templates/{r.json()['id']}")
        nomes = [t["name"] for t in _chama("GET", "/api/templates").json()["templates"]]
        assert "B" in nomes and "A" not in nomes


class TestBancoIndisponivel:
    def test_diz_o_que_rodar(self, monkeypatch, tmp_path):
        # Uma instalação que nunca rodou o seed não pode receber "no such table".
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/vazio.db")
        db.reset_engine()
        try:
            r = _chama("GET", "/api/templates")
            assert r.status_code == 503
            assert "db_seed" in r.json()["detail"]
        finally:
            db.reset_engine()
