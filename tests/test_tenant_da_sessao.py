"""O tenant vem da sessao -- Fase 4, bloco 4.2.

Ate aqui `db.tenant()` sem argumento significava sempre o tenant fixo do
self-host. Agora significa **o tenant da requisicao em curso**, e os 22 sitios
de chamada espalhados por `app.py`, `publish_queue.py` e `job_registry.py` nao
mudaram uma linha -- que e exatamente o que o docstring de `db.tenant()` previa
desde a Fase 0.5.

O teste mais importante deste arquivo e
`test_o_contexto_atravessa_o_middleware`. **Toda a isolacao depende de um
detalhe de implementacao do Starlette**: um `ContextVar` posto no middleware
tem de continuar valendo dentro do endpoint. Se uma versao futura voltar a
rodar o `call_next` numa tarefa que nao herda o contexto, o default silencioso
vira o tenant errado -- sem erro, sem log, so dado do vizinho na tela. Este
teste e o que transforma isso em vermelho.
"""
import asyncio
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")

SENHA_A = "senha-do-primeiro-1"
SENHA_B = "senha-do-segundo-2"


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    auth.esquecer_segredo()
    auth.limpar_tentativas()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    auth.esquecer_segredo()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(metodo, url, corpo=None, token=None):
    async def _do():
        cabecalhos = {"Authorization": f"Bearer {token}"} if token else None
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo,
                                        headers=cabecalhos)
    return asyncio.run(_do())


@pytest.fixture()
def dois_donos():
    """O primeiro dono (tenant fixo) e um segundo, em tenant proprio."""
    a = _chama("POST", "/api/auth/bootstrap",
               {"email": "a@exemplo.com", "senha": SENHA_A}).json()["token"]
    r = _chama("POST", "/api/usuarios",
               {"email": "b@exemplo.com", "senha": SENHA_B}, token=a)
    assert r.status_code == 200, r.text
    b = _chama("POST", "/api/auth/login",
               {"email": "b@exemplo.com", "senha": SENHA_B}).json()["token"]
    return a, b, r.json()["tenant_id"]


# --------------------------------------------------------------------------- #
# A peca de que tudo depende
# --------------------------------------------------------------------------- #

class TestContexto:

    def test_o_contexto_atravessa_o_middleware(self, dois_donos):
        """Um `ContextVar` posto na tranca tem de valer dentro do endpoint.

        Se o Starlette voltar a rodar o `call_next` numa tarefa que nao herda o
        contexto, `db.tenant()` cai no default e passa a ler o tenant do
        self-host para todo mundo -- sem erro e sem log. Este teste e o alarme.
        """
        _, b, tenant_b = dois_donos
        eu = _chama("GET", "/api/me", token=b).json()
        assert eu["tenant_id"] == tenant_b
        # A prova de verdade: um endpoint que usa `db.tenant()` SEM argumento
        # tem de enxergar o tenant de quem chamou.
        _chama("POST", "/api/templates",
               {"name": "So do B", "spec": {"captions": {"preset": "limpo"}}},
               token=b)

        async def _t():
            async with db.tenant(tenant_b) as t:
                return [x.name for x in await t.all(db_models.Template)]
        assert "So do B" in corre(_t)

    def test_o_default_continua_sendo_o_self_host(self):
        """Instalacao sem auth, script de linha de comando, worker sem job: o
        fixo continua valendo quando ninguem preencheu."""
        assert db.tenant_atual() == db.SELF_HOST_TENANT_ID

    def test_usar_e_restaurar(self):
        token = db.usar_tenant("outro-tenant")
        assert db.tenant_atual() == "outro-tenant"
        db.restaurar_tenant(token)
        assert db.tenant_atual() == db.SELF_HOST_TENANT_ID

    def test_restaurar_token_de_outro_contexto_nao_levanta(self):
        """Guardar o token e usa-lo noutra tarefa e bug de quem chamou;
        levantar aqui esconderia o erro de verdade la atras."""
        async def _outra():
            return db.usar_tenant("x")
        token = asyncio.run(_outra())
        db.restaurar_tenant(token)          # nao pode explodir

    def test_id_vazio_cai_no_self_host(self):
        db.usar_tenant("")
        assert db.tenant_atual() == db.SELF_HOST_TENANT_ID


# --------------------------------------------------------------------------- #
# O criterio da fase, pelo lado dos DADOS
# --------------------------------------------------------------------------- #

class TestIsolamentoDeDados:

    def test_templates_nao_atravessam(self, dois_donos):
        a, b, _ = dois_donos
        _chama("POST", "/api/templates",
               {"name": "Meu estilo", "spec": {"captions": {"preset": "limpo"}}},
               token=a)
        meus = [t["name"] for t in
                _chama("GET", "/api/templates", token=a).json()["templates"]]
        dele = [t["name"] for t in
                _chama("GET", "/api/templates", token=b).json()["templates"]]
        assert "Meu estilo" in meus
        assert "Meu estilo" not in dele

    def test_o_segundo_tenant_tem_o_proprio_template_padrao(self, dois_donos):
        """O seed so semeia o tenant fixo. Um tenant novo comeca sem template
        salvo -- e a lista ainda responde, com os presets e o padrao de
        fabrica, em vez de quebrar."""
        _, b, _ = dois_donos
        corpo = _chama("GET", "/api/templates", token=b).json()
        assert corpo["templates"] == []
        assert len(corpo["presets"]) == 6
        assert corpo["padrao"]["safeArea"]["bottomPct"] == 18

    def test_apagar_template_do_vizinho_nao_alcanca(self, dois_donos):
        a, b, _ = dois_donos
        criado = _chama("POST", "/api/templates",
                        {"name": "Meu", "spec": {"captions": {"preset": "limpo"}}},
                        token=a).json()
        r = _chama("DELETE", f"/api/templates/{criado['id']}", token=b)
        assert r.status_code == 404
        nomes = [t["name"] for t in
                 _chama("GET", "/api/templates", token=a).json()["templates"]]
        assert "Meu" in nomes

    def test_contas_de_publicacao_nao_atravessam(self, dois_donos):
        a, b, _ = dois_donos
        _chama("POST", "/api/contas", {"platform": "youtube", "handle": "meu-canal"},
               token=a)
        assert [c["handle"] for c in
                _chama("GET", "/api/contas", token=a).json()["contas"]] == ["meu-canal"]
        assert _chama("GET", "/api/contas", token=b).json()["contas"] == []

    def test_publicacoes_nao_atravessam(self, dois_donos):
        a, b, _ = dois_donos
        _chama("POST", "/api/contas", {"platform": "youtube", "handle": "canal"},
               token=a)
        assert _chama("GET", "/api/publicacoes", token=b).json()["publicacoes"] == []

    def test_o_mesmo_handle_cabe_nos_dois_tenants(self, dois_donos):
        """A unicidade de `accounts` e por tenant, nao global: dois donos podem
        ter um canal com o mesmo nome."""
        a, b, _ = dois_donos
        corpo = {"platform": "youtube", "handle": "cortes"}
        assert _chama("POST", "/api/contas", corpo, token=a).status_code == 200
        assert _chama("POST", "/api/contas", corpo, token=b).status_code == 200


# --------------------------------------------------------------------------- #
# O worker, que nao herda contexto nenhum
# --------------------------------------------------------------------------- #

class TestTenantDoJob:

    def _submeter(self, token):
        async def _do():
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://testserver") as client:
                return await client.post(
                    "/api/process",
                    files={"file": ("v.mp4", b"\0" * 2048, "video/mp4")},
                    data={"acknowledged": "true"},
                    headers={"X-Gemini-Key": "k",
                             "Authorization": f"Bearer {token}"})
        return asyncio.run(_do())

    def test_a_fonte_nasce_no_tenant_de_quem_submeteu(self, dois_donos, ambiente):
        a, b, tenant_b = dois_donos
        r = self._submeter(b)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        async def _t():
            async with db.tenant(tenant_b) as t:
                return await t.get(db_models.Job, job_id), await t.all(db_models.Source)
        job, fontes = corre(_t)
        assert job is not None, "o job foi parar no tenant errado"
        assert len(fontes) == 1

        async def _do_primeiro():
            async with db.tenant(db.SELF_HOST_TENANT_ID) as t:
                return await t.all(db_models.Source)
        assert corre(_do_primeiro) == [], "a fonte vazou para o primeiro tenant"

    def test_o_job_carrega_o_tenant_para_o_worker(self, dois_donos, ambiente):
        """O worker roda depois da resposta, numa tarefa que nao herda o
        contexto -- entao o tenant tem de viajar dentro do proprio job."""
        _, b, tenant_b = dois_donos
        job_id = self._submeter(b).json()["job_id"]
        assert app_module.jobs[job_id]["tenant_id"] == tenant_b

    def test_o_manifesto_de_resume_carrega_o_tenant(self, dois_donos, ambiente):
        """Sem isto, um job retomado depois de um deploy gravaria os cortes no
        tenant do self-host -- e a linha no tenant errado nao volta sozinha."""
        _, b, tenant_b = dois_donos
        job_id = self._submeter(b).json()["job_id"]
        caminho = os.path.join(str(ambiente), job_id, app_module._RESUME_FILE)
        with open(caminho, encoding="utf-8") as fh:
            assert json.load(fh)["tenant_id"] == tenant_b

    def test_a_pasta_do_job_carrega_o_tenant(self, dois_donos, ambiente):
        """O manifesto some quando o job termina. Um projeto COMPLETO
        recuperado do disco depois de um restart precisa continuar sabendo de
        quem e -- mesmo papel do `.owner`."""
        _, b, tenant_b = dois_donos
        job_id = self._submeter(b).json()["job_id"]
        caminho = os.path.join(str(ambiente), job_id, app_module.ARQUIVO_TENANT)
        with open(caminho, encoding="utf-8") as fh:
            assert fh.read().strip() == tenant_b

    def test_job_recuperado_do_disco_volta_com_o_tenant(self, ambiente):
        job_id = str(uuid.uuid4())
        pasta = ambiente / job_id
        pasta.mkdir()
        (pasta / "v_metadata.json").write_text(json.dumps({"shorts": []}))
        (pasta / app_module.ARQUIVO_TENANT).write_text("tenant-de-alguem")
        app_module._recover_jobs_from_disk()
        assert app_module.jobs[job_id]["tenant_id"] == "tenant-de-alguem"

    def test_job_anterior_ao_bloco_cai_no_self_host(self, ambiente):
        """Uma pasta sem o arquivo e de antes desta fase, quando so havia um
        tenant. Chutar qualquer outro seria inventar dono."""
        job_id = str(uuid.uuid4())
        pasta = ambiente / job_id
        pasta.mkdir()
        (pasta / "v_metadata.json").write_text(json.dumps({"shorts": []}))
        app_module._recover_jobs_from_disk()
        assert app_module.jobs[job_id]["tenant_id"] == db.SELF_HOST_TENANT_ID


class TestSemAuthNadaMuda:
    """Instalacao que nunca ligou auth continua exatamente como era."""

    def test_tudo_continua_no_tenant_fixo(self, ambiente):
        assert _chama("GET", "/api/config").json()["authAtiva"] is False
        _chama("POST", "/api/templates",
               {"name": "Sem auth", "spec": {"captions": {"preset": "limpo"}}})

        async def _t():
            async with db.tenant(db.SELF_HOST_TENANT_ID) as t:
                return [x.name for x in await t.all(db_models.Template)]
        assert "Sem auth" in corre(_t)
