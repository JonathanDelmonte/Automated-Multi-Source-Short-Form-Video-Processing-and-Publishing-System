"""Canais: a marca no centro da plataforma (Fase 7, etapa 7.1).

O que estes testes guardam:

**O banco de quem ja usa ganha as tabelas sozinho.** O motor cria o schema no
boot com `create_all`, que cria tabela que falta mas nunca acrescenta coluna.
Por isso as ligacoes moram em tabelas novas (`channel_accounts`,
`channel_jobs`) -- e o teste do banco antigo prova que o boot as cria sem
perder o que ja estava la.

**O canal do projeto mora na pasta dele** (`.canal`), porque a lista de
projetos vem do disco e o banco falha aberto. A linha de `channel_jobs`
acompanha, para as consultas do lado do banco.

**Apagar um canal e reorganizar**: contas e projetos ficam, soltos.

**Um tenant nao ve o canal do outro**, e a resposta e 404, como nos projetos.
"""
import asyncio
import base64
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
canais = pytest.importorskip("canais")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")

from sqlalchemy import inspect, text

#: Um PNG de 1x1 de verdade, em data URL.
PNG = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000100e527de2f0000000049454e44ae426082"
)).decode()


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    saida = tmp_path / "saida"
    saida.mkdir()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(app_module, "jobs", {})
    auth.esquecer_segredo()
    auth.limpar_tentativas()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    auth.esquecer_segredo()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(metodo, url, corpo=None, token=None, **extra):
    async def _do():
        cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
        cabecalhos.update(extra.pop("headers", {}))
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            if corpo is not None:
                extra["json"] = corpo
            return await client.request(metodo, url, headers=cabecalhos, **extra)
    return asyncio.run(_do())


def _canal(nome="Canal infantil", **campos):
    corpo = {"name": nome, "requires_approval": False, **campos}
    r = _chama("POST", "/api/canais", corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _projeto(raiz, canal_id=None, tenant_id=None):
    """Um projeto completo em disco, como o pipeline deixa."""
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    (pasta / "v_clip_1.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": [
        {"start": 0.0, "end": 30.0, "video_title_for_youtube_short": "Corte 1"}]}))
    (pasta / app_module.ARQUIVO_TENANT).write_text(tenant_id or db.SELF_HOST_TENANT_ID)
    if canal_id:
        (pasta / app_module.ARQUIVO_CANAL).write_text(canal_id)
    return job_id


def _linhas(modelo, *where):
    async def _t():
        async with db.tenant() as t:
            return await t.all(modelo, *where)
    return corre(_t)


# --------------------------------------------------------------------------- #
# Regras do pedido
# --------------------------------------------------------------------------- #

class TestValidar:

    def test_criar_exige_nome(self):
        with pytest.raises(canais.CanalError, match="name"):
            canais.validar({"requires_approval": False}, criando=True)
        with pytest.raises(canais.CanalError, match="vazio"):
            canais.validar({"name": "   ", "requires_approval": False}, criando=True)

    def test_criar_exige_a_escolha_da_aprovacao(self):
        """Decisao do autor (26-set-2026): quem escolhe e a pessoa, ao criar. Um
        padrao aqui decidiria por ela sem ninguem ver."""
        with pytest.raises(canais.CanalError, match="aprovacao"):
            canais.validar({"name": "x"}, criando=True)
        with pytest.raises(canais.CanalError, match="aprovacao"):
            canais.validar({"name": "x", "requires_approval": "sim"}, criando=True)

    def test_editar_e_parcial(self):
        assert canais.validar({"niche": "financas"}, criando=False) == {"niche": "financas"}
        assert canais.validar({}, criando=False) == {}

    def test_vazio_apaga_o_opcional(self):
        campos = canais.validar({"niche": "", "avatar": None, "color": "", "language": None},
                                criando=False)
        assert campos == {"niche": None, "avatar": None, "color": None, "language": None}

    def test_avatar_so_imagem_de_verdade_em_base64(self):
        assert canais.validar({"avatar": PNG}, criando=False)["avatar"] == PNG
        svg = "data:image/svg+xml;base64," + base64.b64encode(b"<svg onload=alert(1)/>").decode()
        for ruim in (svg, "https://exemplo.com/a.png", "data:image/png,cru", 42):
            with pytest.raises(canais.CanalError, match="avatar"):
                canais.validar({"avatar": ruim}, criando=False)

    def test_avatar_grande_demais_e_recusado_pelo_tamanho(self):
        grande = "data:image/png;base64," + "A" * canais.LIMITE_AVATAR
        with pytest.raises(canais.CanalError, match="grande"):
            canais.validar({"avatar": grande}, criando=False)

    def test_cor_e_idioma(self):
        assert canais.validar({"color": "#FF00aa"}, criando=False)["color"] == "#ff00aa"
        assert canais.validar({"language": "pt-BR"}, criando=False)["language"] == "pt-BR"
        with pytest.raises(canais.CanalError, match="color"):
            canais.validar({"color": "red"}, criando=False)
        with pytest.raises(canais.CanalError, match="language"):
            canais.validar({"language": "portugues"}, criando=False)

    def test_nome_com_caractere_de_controle(self):
        with pytest.raises(canais.CanalError, match="controle"):
            canais.validar({"name": "a\nb", "requires_approval": True}, criando=True)

    def test_contas_sao_ids(self):
        conta = str(uuid.uuid4())
        assert canais.validar({"contas": [conta, conta]}, criando=False) == {"contas": [conta]}
        assert canais.validar({"contas": None}, criando=False) == {"contas": []}
        with pytest.raises(canais.CanalError, match="contas"):
            canais.validar({"contas": ["../x"]}, criando=False)

    def test_conta_nova_segue_as_regras_da_fila(self):
        """As mesmas regras de `POST /api/contas`, pelo mesmo codigo."""
        with pytest.raises(canais.CanalError, match="plataforma desconhecida"):
            canais.validar({"novas_contas": [{"platform": "orkut", "handle": "@a"}]},
                           criando=False)


# --------------------------------------------------------------------------- #
# Criar, listar, editar, apagar
# --------------------------------------------------------------------------- #

class TestCrud:

    def test_criar_com_as_contas_novas_na_mesma_gravacao(self):
        canal = _canal("Financas em 1 minuto", niche="financas", avatar=PNG,
                       color="#112233", language="pt-BR", requires_approval=True,
                       novas_contas=[{"platform": "tiktok", "handle": "@fin"},
                                     {"platform": "youtube", "handle": "@fin"}])
        assert canal["requires_approval"] is True
        assert canal["avatar"] == PNG
        assert canal["projetos"] == 0
        # Na ordem das plataformas, que e a ordem dos icones na tela.
        assert [c["platform"] for c in canal["contas"]] == ["youtube", "tiktok"]
        contas = _chama("GET", "/api/contas").json()["contas"]
        assert {c["channel_id"] for c in contas} == {canal["id"]}

    def test_conta_nova_repetida_desfaz_tudo(self):
        """O canal e as contas nascem na mesma gravacao: uma conta recusada nao
        pode deixar o canal criado pela metade."""
        _chama("POST", "/api/contas", {"platform": "youtube", "handle": "@ja"})
        r = _chama("POST", "/api/canais", {
            "name": "Meio", "requires_approval": False,
            "novas_contas": [{"platform": "tiktok", "handle": "@novo"},
                             {"platform": "youtube", "handle": "@ja"}]})
        assert r.status_code == 400
        assert _chama("GET", "/api/canais").json()["canais"] == []
        assert [c["handle"] for c in _chama("GET", "/api/contas").json()["contas"]] == ["@ja"]

    def test_nome_repetido_sem_diferenca_de_maiuscula(self):
        _canal("Canal Infantil")
        r = _chama("POST", "/api/canais", {"name": "  canal infantil ", "requires_approval": True})
        assert r.status_code == 409
        assert "nome" in r.json()["detail"]

    def test_lista_em_ordem_de_nome(self):
        for nome in ("zebra", "Acidentes", "fatos"):
            _canal(nome)
        assert [c["name"] for c in _chama("GET", "/api/canais").json()["canais"]] == \
            ["Acidentes", "fatos", "zebra"]

    def test_editar_mexe_so_no_que_veio(self):
        canal = _canal("Antes", niche="filmes", color="#000000")
        r = _chama("PATCH", f"/api/canais/{canal['id']}", {"name": "Depois"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Depois"
        assert r.json()["niche"] == "filmes" and r.json()["color"] == "#000000"

    def test_renomear_para_o_nome_de_outro(self):
        _canal("Um")
        dois = _canal("Dois")
        r = _chama("PATCH", f"/api/canais/{dois['id']}", {"name": "UM"})
        assert r.status_code == 409
        # Renomear para o proprio nome, com outra caixa, nao e conflito.
        assert _chama("PATCH", f"/api/canais/{dois['id']}", {"name": "DOIS"}).status_code == 200

    def test_contas_e_a_lista_inteira(self):
        canal = _canal("A", novas_contas=[{"platform": "youtube", "handle": "@a"},
                                          {"platform": "tiktok", "handle": "@a"}])
        youtube = canal["contas"][0]["id"]
        r = _chama("PATCH", f"/api/canais/{canal['id']}", {"contas": [youtube]})
        assert [c["id"] for c in r.json()["contas"]] == [youtube]
        # A que saiu ficou solta, e nao apagada.
        contas = {c["handle"] + c["platform"]: c for c in
                  _chama("GET", "/api/contas").json()["contas"]}
        assert contas["@atiktok"]["channel_id"] is None

    def test_conta_de_outro_canal_muda_de_canal(self):
        """Uma conta pertence a um canal so; pedi-la aqui a MOVE."""
        a = _canal("A", novas_contas=[{"platform": "youtube", "handle": "@x"}])
        b = _canal("B")
        conta = a["contas"][0]["id"]
        r = _chama("PATCH", f"/api/canais/{b['id']}", {"contas": [conta]})
        assert r.status_code == 200, r.text
        assert [c["id"] for c in r.json()["contas"]] == [conta]
        assert _chama("GET", f"/api/canais/{a['id']}").json()["contas"] == []
        assert len(_linhas(db_models.ChannelAccount)) == 1

    def test_conta_inexistente(self):
        canal = _canal("A")
        r = _chama("PATCH", f"/api/canais/{canal['id']}", {"contas": [str(uuid.uuid4())]})
        assert r.status_code == 400
        assert "conta nao encontrada" in r.json()["detail"]

    def test_apagar_solta_contas_e_projetos(self, ambiente):
        canal = _canal("A", novas_contas=[{"platform": "youtube", "handle": "@a"}])
        job_id = _projeto(ambiente, canal["id"])
        r = _chama("DELETE", f"/api/canais/{canal['id']}")
        assert r.status_code == 200, r.text
        assert r.json()["contas_desligadas"] == 1
        assert r.json()["projetos_desligados"] == 1
        assert [c["handle"] for c in _chama("GET", "/api/contas").json()["contas"]] == ["@a"]
        assert _linhas(db_models.ChannelAccount) == []
        assert (ambiente / job_id / "v_metadata.json").exists()
        assert not (ambiente / job_id / app_module.ARQUIVO_CANAL).exists()
        [projeto] = _chama("GET", "/api/jobs").json()["jobs"]
        assert projeto["channel_id"] is None

    def test_apagar_a_conta_solta_ela_do_canal(self):
        """A ligacao sai pela cascata do schema -- no SQLite, so com o
        `PRAGMA foreign_keys=ON` do `db.py`."""
        canal = _canal("A", novas_contas=[{"platform": "youtube", "handle": "@a"}])
        assert _chama("DELETE", f"/api/contas/{canal['contas'][0]['id']}").status_code == 200
        assert _chama("GET", f"/api/canais/{canal['id']}").json()["contas"] == []
        assert _linhas(db_models.ChannelAccount) == []

    def test_canal_inexistente_e_404(self):
        outro = str(uuid.uuid4())
        assert _chama("GET", f"/api/canais/{outro}").status_code == 404
        assert _chama("PATCH", f"/api/canais/{outro}", {"name": "x"}).status_code == 404
        assert _chama("DELETE", f"/api/canais/{outro}").status_code == 404
        assert _chama("GET", "/api/canais/nao-e-id").status_code == 404

    def test_so_json(self):
        """Pedido JSON de outra origem exige o preflight do CORS; formulario nao."""
        r = _chama("POST", "/api/canais", data={"name": "x", "requires_approval": "false"})
        assert r.status_code == 415
        canal = _canal("A")
        r = _chama("PATCH", f"/api/canais/{canal['id']}", content=b'{"name":"b"}',
                   headers={"Content-Type": "text/plain"})
        assert r.status_code == 415

    def test_banco_fora_do_ar_e_503(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/nao-existe/x.db")
        db.reset_engine()
        assert _chama("GET", "/api/canais").status_code == 503
        assert _chama("POST", "/api/canais", {"name": "a", "requires_approval": False}).status_code == 503


# --------------------------------------------------------------------------- #
# O banco de quem ja usa
# --------------------------------------------------------------------------- #

class TestBancoAntigo:

    def test_o_boot_cria_as_tabelas_novas_sem_perder_nada(self):
        """O banco do autor nasceu antes dos canais. O boot (`db_seed.seed`, com
        `create_all`) tem de criar as tres tabelas e deixar o resto intacto --
        e e por isso que o canal nao e coluna de `accounts` nem de `jobs`."""
        _chama("POST", "/api/contas", {"platform": "youtube", "handle": "@antiga"})

        async def _derrubar():
            async with db.engine().begin() as conn:
                for tabela in ("channel_jobs", "channel_accounts", "channels"):
                    await conn.execute(text(f"DROP TABLE {tabela}"))
        corre(_derrubar)

        async def _tabelas():
            async with db.engine().connect() as conn:
                return await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        assert "channels" not in corre(_tabelas)

        asyncio.run(db_seed.seed())
        assert {"channels", "channel_accounts", "channel_jobs"} <= corre(_tabelas)
        conta = _chama("GET", "/api/contas").json()["contas"][0]
        canal = _canal("Novo", contas=[conta["id"]])
        assert [c["handle"] for c in canal["contas"]] == ["@antiga"]


# --------------------------------------------------------------------------- #
# O projeto e o canal
# --------------------------------------------------------------------------- #

class TestProjetoNoCanal:

    def _submeter(self, **dados):
        return _chama("POST", "/api/process",
                      files={"file": ("v.mp4", b"\0" * 2048, "video/mp4")},
                      data={"acknowledged": "true", **dados},
                      headers={"X-Gemini-Key": "k"})

    def test_o_submit_grava_o_canal_na_pasta_e_no_banco(self, ambiente):
        canal = _canal("A")
        r = self._submeter(channel_id=canal["id"])
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert (ambiente / job_id / app_module.ARQUIVO_CANAL).read_text() == canal["id"]
        assert [l.job_id for l in _linhas(db_models.ChannelJob)] == [job_id]
        [projeto] = _chama("GET", "/api/jobs").json()["jobs"]
        assert projeto["channel_id"] == canal["id"]
        assert _chama("GET", "/api/canais").json()["canais"][0]["projetos"] == 1

    def test_o_submit_por_json_tambem(self, ambiente):
        """O MCP e os agentes mandam JSON; o canal vem no mesmo corpo."""
        canal = _canal("A")
        r = _chama("POST", "/api/process",
                   {"url": "https://exemplo.com/video.mp4", "acknowledged": True,
                    "channel_id": canal["id"]},
                   headers={"X-Gemini-Key": "k"})
        assert r.status_code == 200, r.text
        assert app_module.jobs[r.json()["job_id"]]["channel_id"] == canal["id"]

    def test_canal_errado_para_antes_do_trabalho(self, ambiente):
        assert self._submeter(channel_id="nao-e-id").status_code == 400
        r = self._submeter(channel_id=str(uuid.uuid4()))
        assert r.status_code == 400
        assert "Canal" in r.json()["detail"]
        assert app_module.jobs == {}
        assert list(ambiente.iterdir()) == []

    def test_sem_canal_continua_como_antes(self, ambiente):
        r = self._submeter()
        assert r.status_code == 200, r.text
        assert not (ambiente / r.json()["job_id"] / app_module.ARQUIVO_CANAL).exists()
        assert _linhas(db_models.ChannelJob) == []

    def test_banco_fora_do_ar_nao_impede_o_video(self, ambiente, tmp_path, monkeypatch):
        """O pipeline nunca dependeu do banco; o canal fica gravado na pasta."""
        canal_id = str(uuid.uuid4())
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/nao-existe/x.db")
        db.reset_engine()
        r = self._submeter(channel_id=canal_id)
        assert r.status_code == 200, r.text
        assert (ambiente / r.json()["job_id"] / app_module.ARQUIVO_CANAL).read_text() == canal_id

    def test_a_lista_filtra_pelo_canal(self, ambiente):
        a, b = _canal("A"), _canal("B")
        do_a = _projeto(ambiente, a["id"])
        _projeto(ambiente, b["id"])
        _projeto(ambiente)
        assert [j["job_id"] for j in
                _chama("GET", f"/api/jobs?canal={a['id']}").json()["jobs"]] == [do_a]
        assert len(_chama("GET", "/api/jobs").json()["jobs"]) == 3

    def test_o_projeto_recuperado_do_disco_lembra_o_canal(self, ambiente):
        canal = _canal("A")
        job_id = _projeto(ambiente, canal["id"])
        app_module._recover_jobs_from_disk()
        assert app_module.jobs[job_id]["channel_id"] == canal["id"]

    def test_marcador_estragado_vale_sem_canal(self, ambiente):
        job_id = _projeto(ambiente)
        (ambiente / job_id / app_module.ARQUIVO_CANAL).write_text("../../etc")
        [projeto] = _chama("GET", "/api/jobs").json()["jobs"]
        assert projeto["channel_id"] is None


class TestMoverProjeto:

    def _projeto_registrado(self, raiz):
        """Projeto em disco E no banco, como o submit deixa."""
        job_id = _projeto(raiz)

        async def _t():
            fonte = await job_registry.registrar_fonte("youtube", "https://y/x")
            await job_registry.registrar_job(job_id, fonte)
        corre(_t)
        return job_id

    def test_por_e_tirar_do_canal(self, ambiente):
        canal = _canal("A")
        job_id = self._projeto_registrado(ambiente)
        r = _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": canal["id"]})
        assert r.status_code == 200, r.text
        assert (ambiente / job_id / app_module.ARQUIVO_CANAL).read_text() == canal["id"]
        assert [l.channel_id for l in _linhas(db_models.ChannelJob)] == [canal["id"]]
        assert _chama("GET", "/api/jobs").json()["jobs"][0]["channel_id"] == canal["id"]

        r = _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": None})
        assert r.status_code == 200, r.text
        assert not (ambiente / job_id / app_module.ARQUIVO_CANAL).exists()
        assert _linhas(db_models.ChannelJob) == []
        assert _chama("GET", "/api/jobs").json()["jobs"][0]["channel_id"] is None

    def test_trocar_de_canal_deixa_uma_ligacao_so(self, ambiente):
        a, b = _canal("A"), _canal("B")
        job_id = self._projeto_registrado(ambiente)
        _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": a["id"]})
        _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": b["id"]})
        assert [l.channel_id for l in _linhas(db_models.ChannelJob)] == [b["id"]]

    def test_projeto_antigo_sem_linha_no_banco_muda_mesmo_assim(self, ambiente):
        """Projeto anterior ao bloco 3.3 nao tem linha em `jobs`: a FK recusa a
        ligacao, e isso e so um aviso -- a pasta e quem manda na lista."""
        canal = _canal("A")
        job_id = _projeto(ambiente)
        r = _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": canal["id"]})
        assert r.status_code == 200, r.text
        assert _chama("GET", "/api/jobs").json()["jobs"][0]["channel_id"] == canal["id"]

    def test_recusas(self, ambiente):
        job_id = _projeto(ambiente)
        assert _chama("PUT", f"/api/jobs/{job_id}/canal",
                      {"channel_id": str(uuid.uuid4())}).status_code == 404
        assert _chama("PUT", f"/api/jobs/{job_id}/canal", {}).status_code == 400
        assert _chama("PUT", f"/api/jobs/{uuid.uuid4()}/canal",
                      {"channel_id": None}).status_code == 404
        r = _chama("PUT", f"/api/jobs/{job_id}/canal", content=b'{"channel_id":null}',
                   headers={"Content-Type": "text/plain"})
        assert r.status_code == 415

    def test_apagar_o_projeto_leva_a_ligacao(self, ambiente):
        canal = _canal("A")
        job_id = self._projeto_registrado(ambiente)
        _chama("PUT", f"/api/jobs/{job_id}/canal", {"channel_id": canal["id"]})
        assert _chama("DELETE", f"/api/jobs/{job_id}").status_code == 200
        assert _linhas(db_models.ChannelJob) == []
        assert _chama("GET", "/api/canais").json()["canais"][0]["projetos"] == 0


# --------------------------------------------------------------------------- #
# Um tenant nao ve o canal do outro
# --------------------------------------------------------------------------- #

SENHA_A = "senha-do-primeiro-1"
SENHA_B = "senha-do-segundo-2"


class TestIsolamento:

    @pytest.fixture()
    def dois_donos(self):
        a = _chama("POST", "/api/auth/bootstrap",
                   {"email": "a@exemplo.com", "senha": SENHA_A}).json()["token"]
        r = _chama("POST", "/api/usuarios",
                   {"email": "b@exemplo.com", "senha": SENHA_B}, token=a)
        b = _chama("POST", "/api/auth/login",
                   {"email": "b@exemplo.com", "senha": SENHA_B}).json()["token"]
        return a, b, r.json()["tenant_id"]

    def test_cada_um_ve_so_os_seus(self, dois_donos):
        a, b, _ = dois_donos
        r = _chama("POST", "/api/canais", {"name": "Meu", "requires_approval": False}, token=a)
        assert r.status_code == 200, r.text
        meu = r.json()["id"]
        assert _chama("GET", "/api/canais", token=b).json()["canais"] == []
        for metodo, corpo in (("GET", None), ("PATCH", {"name": "roubado"}), ("DELETE", None)):
            assert _chama(metodo, f"/api/canais/{meu}", corpo, token=b).status_code == 404
        assert _chama("GET", f"/api/canais/{meu}", token=a).json()["name"] == "Meu"

    def test_o_mesmo_nome_em_tenants_diferentes(self, dois_donos):
        a, b, _ = dois_donos
        for token in (a, b):
            r = _chama("POST", "/api/canais", {"name": "Infantil", "requires_approval": True},
                       token=token)
            assert r.status_code == 200, r.text

    def test_nao_liga_conta_do_vizinho(self, dois_donos):
        a, b, _ = dois_donos
        conta = _chama("POST", "/api/contas", {"platform": "youtube", "handle": "@a"},
                       token=a).json()["id"]
        r = _chama("POST", "/api/canais", {"name": "B", "requires_approval": False,
                                           "contas": [conta]}, token=b)
        assert r.status_code == 400
        assert "conta nao encontrada" in r.json()["detail"]

    def test_nao_poe_projeto_no_canal_do_vizinho(self, dois_donos, ambiente):
        a, b, tenant_b = dois_donos
        do_a = _chama("POST", "/api/canais", {"name": "A", "requires_approval": False},
                      token=a).json()["id"]
        job_de_b = _projeto(ambiente, tenant_id=tenant_b)
        r = _chama("PUT", f"/api/jobs/{job_de_b}/canal", {"channel_id": do_a}, token=b)
        assert r.status_code == 404
        assert not (ambiente / job_de_b / app_module.ARQUIVO_CANAL).exists()
