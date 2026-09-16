"""Fila e arquivos isolados por tenant -- Fase 4, bloco 4.3.

Este arquivo guarda o **criterio de pronto da Fase 4**: "uma segunda conta usa
o sistema sem ver nada da primeira". O bloco 4.2 cuidou dos dados (templates,
contas, publicacoes); aqui e o que sobra e o que mais aparece na tela -- os
projetos, os arquivos e os bytes dos clipes.

A guarda mora num lugar so, `_assert_job_owner`, que ja era chamada por
`/api/status`, cancelar, apagar, baixar tudo e por todos os endpoints de
edicao. Somar a checagem la protege os nove de uma vez e faz o endpoint novo
nascer protegido -- e `test_todo_endpoint_de_job_recusa_o_vizinho` e o que
cobra isso de todos eles.
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
db_seed = pytest.importorskip("db_seed")
media_auth = pytest.importorskip("media_auth")

SENHA_A = "senha-do-primeiro-1"
SENHA_B = "senha-do-segundo-2"


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
    # O mount de `/videos` guarda o diretorio no IMPORT, entao trocar
    # `app.OUTPUT_DIR` nao o alcanca -- e sem isto os testes de bytes mediriam
    # um 404 de arquivo ausente achando que mediam a tranca.
    montagem = [r for r in app_module.app.routes
                if getattr(r, "name", "") == "videos"][0].app
    monkeypatch.setattr(montagem, "directory", str(saida))
    monkeypatch.setattr(montagem, "all_directories", [str(saida)])
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
    a = _chama("POST", "/api/auth/bootstrap",
               {"email": "a@exemplo.com", "senha": SENHA_A}).json()["token"]
    r = _chama("POST", "/api/usuarios",
               {"email": "b@exemplo.com", "senha": SENHA_B}, token=a)
    b = _chama("POST", "/api/auth/login",
               {"email": "b@exemplo.com", "senha": SENHA_B}).json()["token"]
    return a, b, r.json()["tenant_id"]


def _job_de(raiz, tenant_id, quantos=1):
    """Um projeto completo em disco, carimbado com o tenant."""
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = []
    for i in range(quantos):
        shorts.append({"start": 0.0, "end": 30.0,
                       "video_title_for_youtube_short": f"Corte {i + 1}",
                       "video_description_for_tiktok": "d"})
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))
    (pasta / app_module.ARQUIVO_TENANT).write_text(tenant_id)
    return job_id


# --------------------------------------------------------------------------- #
# Projetos
# --------------------------------------------------------------------------- #

class TestListaDeProjetos:

    def test_cada_um_ve_so_os_seus(self, dois_donos, ambiente):
        a, b, tenant_b = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        dele = _job_de(ambiente, tenant_b)
        assert [j["job_id"] for j in
                _chama("GET", "/api/jobs", token=a).json()["jobs"]] == [meu]
        assert [j["job_id"] for j in
                _chama("GET", "/api/jobs", token=b).json()["jobs"]] == [dele]

    def test_projeto_sem_carimbo_e_do_self_host(self, dois_donos, ambiente):
        """Uma pasta anterior a Fase 4 e do unico tenant que existia entao."""
        a, b, _ = dois_donos
        job_id = str(uuid.uuid4())
        pasta = ambiente / job_id
        pasta.mkdir()
        (pasta / "v_metadata.json").write_text(json.dumps({"shorts": []}))
        assert [j["job_id"] for j in
                _chama("GET", "/api/jobs", token=a).json()["jobs"]] == [job_id]
        assert _chama("GET", "/api/jobs", token=b).json()["jobs"] == []

    def test_sem_auth_a_lista_e_a_de_sempre(self, ambiente):
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert [j["job_id"] for j in
                _chama("GET", "/api/jobs").json()["jobs"]] == [meu]


class TestEndpointsDeJob:

    def test_todo_endpoint_de_job_recusa_o_vizinho(self, dois_donos, ambiente):
        """A guarda esta em `_assert_job_owner`, que estes nove ja chamavam.

        Conferir um por um aqui e o que garante que ela continua sendo chamada
        -- um endpoint que pare de faze-lo nao da erro, so passa a responder
        para todo mundo.
        """
        _, b, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        casos = [
            ("GET", f"/api/status/{meu}"),
            ("GET", f"/api/jobs/{meu}/download-all"),
            ("POST", f"/api/jobs/{meu}/cancel"),
            ("DELETE", f"/api/jobs/{meu}"),
        ]
        for metodo, url in casos:
            r = _chama(metodo, url, corpo={}, token=b)
            assert r.status_code == 404, f"{metodo} {url} respondeu {r.status_code}"

    def test_o_dono_continua_alcancando(self, dois_donos, ambiente):
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", f"/api/status/{meu}", token=a).status_code == 200

    def test_recusa_com_404_e_nao_403(self, dois_donos, ambiente):
        """403 confirma que o id existe, e quem sonda ids alheios ja ganhou
        metade da resposta com isso."""
        _, b, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        inexistente = str(uuid.uuid4())
        assert _chama("GET", f"/api/status/{meu}", token=b).status_code == \
            _chama("GET", f"/api/status/{inexistente}", token=b).status_code == 404

    def test_apagar_o_do_vizinho_nao_apaga_nada(self, dois_donos, ambiente):
        _, b, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        _chama("DELETE", f"/api/jobs/{meu}", token=b)
        assert (ambiente / meu / "v_metadata.json").exists()


class TestPacoteDoDia:

    def test_o_pacote_so_leva_os_seus_cortes(self, dois_donos, ambiente):
        a, b, tenant_b = dois_donos
        _job_de(ambiente, db.SELF_HOST_TENANT_ID, quantos=2)
        _job_de(ambiente, tenant_b, quantos=3)
        assert _chama("GET", "/api/publicacoes/dias",
                      token=a).json()["dias"][0]["cortes"] == 2
        assert _chama("GET", "/api/publicacoes/dias",
                      token=b).json()["dias"][0]["cortes"] == 3

    def test_sem_corte_proprio_o_pacote_e_404(self, dois_donos, ambiente):
        _, b, _ = dois_donos
        _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", "/api/publicacoes/pacote", token=b).status_code == 404


# --------------------------------------------------------------------------- #
# Os bytes
# --------------------------------------------------------------------------- #

class TestBytesDosClipes:

    def _url(self, job_id):
        return f"/videos/{job_id}/v_clip_1.mp4"

    def test_o_dono_baixa_com_a_sessao(self, dois_donos, ambiente):
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", self._url(meu), token=a).status_code == 200

    def test_o_vizinho_nao_baixa_nem_com_o_id_certo(self, dois_donos, ambiente):
        """O id do job NAO e a fechadura. Ele vaza em log, em webhook e na
        URL que a pessoa manda para alguem."""
        _, b, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", self._url(meu), token=b).status_code == 404

    def test_sem_sessao_nenhuma_nao_baixa(self, dois_donos, ambiente):
        _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", self._url(meu)).status_code == 404

    def test_o_token_de_midia_abre_para_o_dono(self, dois_donos, ambiente):
        """Um `<video src>` nao manda cabecalho: sem esta porta, o player do
        painel voltaria 404 em toda instalacao com auth."""
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        mt = _chama("GET", "/api/media-token", token=a).json()["token"]
        assert _chama("GET", f"{self._url(meu)}?mt={mt}").status_code == 200

    def test_o_token_do_vizinho_nao_abre(self, dois_donos, ambiente):
        _, b, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        mt = _chama("GET", "/api/media-token", token=b).json()["token"]
        assert _chama("GET", f"{self._url(meu)}?mt={mt}").status_code == 404

    def test_token_adulterado_nao_abre(self, dois_donos, ambiente):
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        mt = _chama("GET", "/api/media-token", token=a).json()["token"]
        uid, exp, _sig = mt.split(".")
        assert _chama("GET", f"{self._url(meu)}?mt={uid}.{exp}.0000").status_code == 404

    def test_token_expirado_nao_abre(self, dois_donos, ambiente):
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        segredo = auth.segredo_texto()
        vencido = media_auth.mint_user_token(db.SELF_HOST_TENANT_ID, segredo,
                                             ttl=-10)
        assert _chama("GET", f"{self._url(meu)}?mt={vencido}").status_code == 404

    def test_o_token_carrega_o_tenant_e_nao_o_usuario(self, dois_donos):
        """O dono do arquivo e o tenant. Com o id do usuario, trocar de conta
        dentro da mesma instalacao obrigaria a remintar sem necessidade."""
        a, _, _ = dois_donos
        mt = _chama("GET", "/api/media-token", token=a).json()["token"]
        segredo = auth.segredo_texto()
        assert media_auth.verify_user_token(mt, segredo) == db.SELF_HOST_TENANT_ID

    def test_sem_auth_os_bytes_respondem_como_sempre(self, ambiente):
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        assert _chama("GET", self._url(meu)).status_code == 200

    @pytest.mark.parametrize("arquivo", [
        ".instance", ".llm_budget.json", ".youtube_quota.json",
    ])
    def test_o_que_mora_na_raiz_do_output_nao_e_servido(self, dois_donos,
                                                        ambiente, arquivo):
        """`/videos` serve o OUTPUT_DIR inteiro, e na raiz dele moram o marcador
        de instancia, o orcamento de LLM e o contador de quota.

        A tranca por tenant nao os cobre -- o primeiro pedaco do caminho nao e
        um id de job. Quem os recusa e a lista de extensoes entregaveis do
        `media_auth`, e este teste e o que garante que ela continua sendo o
        piso mesmo agora que existe uma segunda porta.
        """
        a, _, _ = dois_donos
        (ambiente / arquivo).write_text("segredo")
        assert _chama("GET", f"/videos/{arquivo}", token=a).status_code == 404

    def test_o_guard_de_arquivo_continua_valendo(self, dois_donos, ambiente):
        """A tranca por tenant nao substituiu a lista de extensoes entregaveis:
        o `.tenant`, o `.owner` e o metadata continuam fora do alcance mesmo
        para o proprio dono."""
        a, _, _ = dois_donos
        meu = _job_de(ambiente, db.SELF_HOST_TENANT_ID)
        for arquivo in (app_module.ARQUIVO_TENANT, "v_metadata.json"):
            r = _chama("GET", f"/videos/{meu}/{arquivo}", token=a)
            assert r.status_code == 404, f"{arquivo} foi servido"
