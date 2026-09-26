"""Medir o Instagram pela API de conta profissional -- etapa 7.4.

A rede da Meta nao e alcancavel daqui: `_get` e trocado por uma imitacao que
responde como a API (`data`, `paging.next`, `error.code`). O que decide -- o
token colado, a conta certa, a cadeia de metricas, o tempo em milissegundos, a
retencao derivada, o token que vence -- roda de verdade.
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import metricas_instagram as mi
import vault
from publishers.base import PublisherError

TOKEN = "IGAAT" + "x" * 60


@pytest.fixture()
def cofre(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    return tmp_path


def _erro(status, codigo, mensagem="x"):
    return mi.erro_do_instagram(status, {"error": {"code": codigo, "message": mensagem}})


class ApiFalsa:
    """Responde `_get` como a Meta: `me`, `me/media` (paginada) e insights."""

    def __init__(self, midias=(), por_pagina=2, insights=None, aceitos=None,
                 me=None, erro_em=None):
        self.midias = list(midias)
        self.por_pagina = por_pagina
        self.insights = insights or {}
        # Os conjuntos de metricas que a "API" aceita; os outros dao 400/100.
        self.aceitos = aceitos
        self.me = me or {"user_id": "1789", "username": "canal"}
        self.erro_em = erro_em or {}
        self.pedidos = []

    def __call__(self, caminho, token, params=None, timeout=30.0):
        self.pedidos.append((caminho, dict(params or {})))
        for chave, erro in self.erro_em.items():
            if chave in caminho:
                raise erro
        if caminho == "me":
            return dict(self.me)
        if caminho == "refresh_access_token":
            return {"access_token": "IGAAT-renovado" + "y" * 40, "expires_in": 5184000}
        if caminho == "me/media" or caminho.startswith("https://"):
            pagina = 0 if caminho == "me/media" else int(caminho.rsplit("=", 1)[1])
            fatia = self.midias[pagina * self.por_pagina:(pagina + 1) * self.por_pagina]
            dados = {"data": fatia}
            if (pagina + 1) * self.por_pagina < len(self.midias):
                dados["paging"] = {"next": f"{mi.GRAPH}/v24.0/1789/media?after={pagina + 1}"}
            return dados
        if caminho.endswith("/insights"):
            pedidas = tuple(params["metric"].split(","))
            if self.aceitos is not None and pedidas not in self.aceitos:
                raise _erro(400, 100, "(#100) metric[4] must be one of the following values")
            valores = self.insights.get(caminho.split("/")[0], {})
            return {"data": [{"name": n, "period": "lifetime", "values": [{"value": valores[n]}]}
                             for n in pedidas if n in valores]}
        raise AssertionError(f"caminho inesperado: {caminho}")


def _midia(n, codigo=None, **extra):
    return {"id": f"1790{n}", "shortcode": codigo or f"COD{n}xyz",
            "media_product_type": "REELS", "like_count": 10 + n, "comments_count": n, **extra}


class TestTokenColado:

    @pytest.mark.parametrize("colado", [
        TOKEN, f"  {TOKEN}\n", f'"{TOKEN}"', f"access_token={TOKEN}", f"Bearer {TOKEN}",
    ])
    def test_limpa_o_que_vem_junto(self, colado):
        assert mi.limpar_token(colado) == TOKEN

    @pytest.mark.parametrize("colado", ["", "curto", "tem espaco no meio " + "x" * 40,
                                        "<script>" + "x" * 40, "IGAA\n" + "x" * 40])
    def test_o_que_nao_parece_token(self, colado):
        with pytest.raises(mi.TokenRecusado) as e:
            mi.limpar_token(colado)
        assert e.value.codigo == "formato"

    def test_a_conta_certa(self, monkeypatch):
        monkeypatch.setattr(mi, "_get", ApiFalsa(me={"user_id": "1789", "username": "Canal"}))
        segredo = mi.conferir(TOKEN, "@canal")
        assert segredo["access_token"] == TOKEN and segredo["user_id"] == "1789"
        assert segredo["username"] == "Canal"
        assert datetime.fromisoformat(segredo["renovado_em"]).tzinfo is not None

    def test_token_de_outra_conta_e_recusado(self, monkeypatch):
        """Medir a conta errada seria pior que nao medir: os numeros entrariam
        na calibracao como se fossem destes cortes."""
        monkeypatch.setattr(mi, "_get", ApiFalsa(me={"user_id": "9", "username": "outra"}))
        with pytest.raises(mi.TokenRecusado) as e:
            mi.conferir(TOKEN, "@canal")
        assert e.value.codigo == "outra_conta" and e.value.detalhe == "outra"

    @pytest.mark.parametrize("erro, codigo", [
        (_erro(400, 190, "Invalid OAuth access token"), "recusado"),
        (_erro(403, 10, "Application does not have permission"), "permissao"),
        (_erro(500, 2, "Service temporarily unavailable"), "sem_resposta"),
        (_erro(400, 4, "Application request limit reached"), "sem_resposta"),
        (httpx.ConnectError("sem rede"), "sem_resposta"),
    ])
    def test_o_que_o_instagram_responde(self, monkeypatch, erro, codigo):
        monkeypatch.setattr(mi, "_get", ApiFalsa(erro_em={"me": erro}))
        with pytest.raises(mi.TokenRecusado) as e:
            mi.conferir(TOKEN, "@canal")
        assert e.value.codigo == codigo

    def test_sem_o_campo_user_id_pergunta_pelo_id(self, monkeypatch):
        """`user_id` e o campo da conta profissional; se a versao da API nao o
        conhecer, o `id` responde pela mesma conta."""
        chamadas = []

        def _get(caminho, token, params=None, timeout=30.0):
            chamadas.append(params["fields"])
            if "user_id" in params["fields"]:
                raise _erro(400, 100, "(#100) Tried accessing nonexisting field (user_id)")
            return {"id": "55", "username": "canal"}
        monkeypatch.setattr(mi, "_get", _get)
        assert mi.conferir(TOKEN, "canal")["user_id"] == "55"
        assert chamadas == ["user_id,username", "id,username"]

    def test_erro_de_rede_nao_carrega_o_endereco_com_o_token(self, monkeypatch):
        """O token vai no endereco da consulta; a excecao do httpx pode
        repetir o endereco, e ela chegaria ao log do coletor (e ao painel)."""
        def _falha(url, params=None, timeout=None):
            raise httpx.ConnectError(f"falhou em {url}?access_token={params['access_token']}")
        monkeypatch.setattr(httpx, "get", _falha)
        with pytest.raises(mi.ErroDoInstagram) as e:
            mi._get("me", TOKEN, {"fields": "username"})
        assert TOKEN not in str(e.value) and e.value.__cause__ is None
        assert "ConnectError" in str(e.value)

    def test_a_frase_de_erro_nunca_repete_o_token(self):
        erro = mi.erro_do_instagram(400, {"error": {"code": 1, "message": "falhou"}})
        assert TOKEN not in str(erro)


class TestLeitura:

    def test_o_codigo_do_post_pelo_campo_ou_pelo_link(self):
        assert mi.codigo_do_link({"shortcode": "ABC123xy"}) == "ABC123xy"
        assert mi.codigo_do_link({"permalink": "https://www.instagram.com/reel/DEF456zz/"}) == "DEF456zz"
        assert mi.codigo_do_link({"permalink": "https://www.instagram.com/p/GHI789ww/?igsh=1"}) == "GHI789ww"
        assert mi.codigo_do_link({"permalink": "https://exemplo.com/x"}) is None
        assert mi.codigo_do_link({}) is None

    def test_os_insights_nas_duas_formas(self):
        """`values` e a forma de sempre; `total_value`, a das metricas novas."""
        payload = {"data": [
            {"name": "views", "values": [{"value": 1500}]},
            {"name": "reach", "total_value": {"value": 900}},
            {"name": "saved", "values": []},
            {"name": "shares", "values": [{"value": True}]},
        ]}
        assert mi.parse_insights(payload) == {"views": 1500, "reach": 900}

    def test_o_tempo_medio_chega_em_milissegundos(self):
        numeros = mi.numeros({"like_count": 40, "comments_count": 3},
                             {"views": 2000, "saved": 7, "shares": 5,
                              "ig_reels_avg_watch_time": 12500}, duracao_s=25.0)
        assert numeros == {"views": 2000, "likes": 40, "comments": 3, "shares": 5,
                           "saves": 7, "avg_watch_s": 12.5, "retention_pct": 50.0}

    def test_a_retencao_tem_teto(self):
        """Reel repete: a media pode passar da duracao, e 180% nao quer dizer
        nada."""
        assert mi.retencao(45.0, 25.0) == 100.0

    @pytest.mark.parametrize("medio, duracao", [(None, 30), (12.0, None), (12.0, 0), (0, 30)])
    def test_sem_duracao_ou_sem_tempo_nao_ha_retencao(self, medio, duracao):
        assert mi.retencao(medio, duracao) is None

    def test_numero_que_nao_veio_e_none(self):
        numeros = mi.numeros({}, {})
        assert set(numeros.values()) == {None}


class TestRenovar:

    def test_uma_vez_por_semana(self):
        agora = datetime(2026, 9, 26, tzinfo=timezone.utc)
        recente = {"renovado_em": (agora - timedelta(days=2)).isoformat()}
        antigo = {"renovado_em": (agora - timedelta(days=8)).isoformat()}
        assert not mi.precisa_renovar(recente, agora)
        assert mi.precisa_renovar(antigo, agora)
        assert mi.precisa_renovar({}, agora)

    def test_a_medicao_renova_e_guarda(self, cofre, monkeypatch):
        antigo = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        vault.gravar(mi.ref_de("@canal"), {"access_token": TOKEN, "user_id": "1789",
                                           "renovado_em": antigo})
        api = ApiFalsa(midias=[_midia(1)])
        monkeypatch.setattr(mi, "_get", api)
        mi.medir("@canal", [{"id": "COD1xyz"}])
        guardado = mi.credencial("@canal")
        assert guardado["access_token"].startswith("IGAAT-renovado")
        assert guardado["renovado_em"] != antigo
        assert any(c == "refresh_access_token" for c, _ in api.pedidos)


class TestMedir:

    def _conectar(self):
        vault.gravar(mi.ref_de("@canal"), {
            "access_token": TOKEN, "user_id": "1789", "username": "canal",
            "renovado_em": datetime.now(timezone.utc).isoformat()})

    def test_casa_pelo_codigo_do_link_lendo_as_paginas(self, cofre, monkeypatch):
        """O "ja publiquei" guarda o codigo do link, que nao e o id da API."""
        self._conectar()
        api = ApiFalsa(midias=[_midia(n) for n in range(5)], por_pagina=2,
                       insights={"17904": {"views": 321, "saved": 2, "shares": 1,
                                           "reach": 300, "ig_reels_avg_watch_time": 9000}})
        monkeypatch.setattr(mi, "_get", api)
        numeros = mi.medir("@canal", [{"id": "COD4xyz", "duracao_s": 30.0}])
        assert numeros == {"COD4xyz": {"views": 321, "likes": 14, "comments": 4, "shares": 1,
                                       "saves": 2, "avg_watch_s": 9.0, "retention_pct": 30.0}}
        paginas = [c for c, _ in api.pedidos if c == "me/media" or c.startswith("https://")]
        assert len(paginas) == 3

    def test_para_de_ler_quando_achou(self, cofre, monkeypatch):
        self._conectar()
        api = ApiFalsa(midias=[_midia(n) for n in range(8)], por_pagina=2)
        monkeypatch.setattr(mi, "_get", api)
        mi.medir("@canal", [{"id": "COD1xyz"}])
        assert [c for c, _ in api.pedidos if c == "me/media" or c.startswith("https://")] == ["me/media"]

    def test_post_que_nao_e_da_conta_fica_sem_numero(self, cofre, monkeypatch):
        self._conectar()
        monkeypatch.setattr(mi, "_get", ApiFalsa(midias=[_midia(1)]))
        assert mi.medir("@canal", [{"id": "DEOUTRAxy"}]) == {}

    def test_metrica_recusada_passa_ao_conjunto_seguinte(self, cofre, monkeypatch):
        """A Meta renomeia metricas (plays e impressions sairam em 2025): um
        nome recusado nunca custa os outros numeros."""
        self._conectar()
        api = ApiFalsa(midias=[_midia(1)], aceitos=[mi.CONJUNTOS_DE_METRICAS[1]],
                       insights={"17901": {"views": 50, "reach": 40, "saved": 1, "shares": 0}})
        monkeypatch.setattr(mi, "_get", api)
        numeros = mi.medir("@canal", [{"id": "COD1xyz", "duracao_s": 20}])["COD1xyz"]
        assert numeros["views"] == 50 and numeros["shares"] == 0
        assert numeros["avg_watch_s"] is None and numeros["retention_pct"] is None
        insights = [p["metric"] for c, p in api.pedidos if c.endswith("/insights")]
        assert len(insights) == 2

    def test_sem_insights_ficam_curtidas_e_comentarios(self, cofre, monkeypatch):
        """Post de antes da conta virar profissional nao tem insights: a lista
        ja deu curtidas e comentarios."""
        self._conectar()
        monkeypatch.setattr(mi, "_get", ApiFalsa(midias=[_midia(1)], aceitos=[]))
        numeros = mi.medir("@canal", [{"id": "COD1xyz"}])["COD1xyz"]
        assert (numeros["likes"], numeros["comments"], numeros["views"]) == (11, 1, None)

    def test_muitos_pedidos_para_a_conta(self, cofre, monkeypatch):
        """Com limite atingido, insistir nos outros conjuntos so gasta mais."""
        self._conectar()
        api = ApiFalsa(midias=[_midia(1)], erro_em={"/insights": _erro(400, 4)})
        monkeypatch.setattr(mi, "_get", api)
        with pytest.raises(mi.ErroDoInstagram):
            mi.medir("@canal", [{"id": "COD1xyz"}])
        assert len([c for c, _ in api.pedidos if c.endswith("/insights")]) == 1

    def test_token_vencido_marca_a_conexao(self, cofre, monkeypatch):
        """Vencido, so um token novo resolve: a tela pede outro, e a coleta
        para de tentar."""
        self._conectar()
        monkeypatch.setattr(mi, "_get", ApiFalsa(erro_em={"me/media": _erro(400, 190)}))
        with pytest.raises(mi.TokenInvalido):
            mi.medir("@canal", [{"id": "COD1xyz"}])
        assert mi.situacao("@canal") == "vencido"
        assert mi.credencial("@canal") is None

    def test_sem_token(self, cofre):
        with pytest.raises(PublisherError) as e:
            mi.medir("@canal", [{"id": "COD1xyz"}])
        assert "cole o token" in str(e.value).lower()

    def test_a_pagina_seguinte_de_outro_endereco_nao_e_seguida(self, cofre, monkeypatch):
        """O endereco da pagina seguinte carrega o token."""
        self._conectar()

        def _get(caminho, token, params=None, timeout=30.0):
            assert not caminho.startswith("https://evil"), "seguiu o endereco estranho"
            return {"data": [_midia(1)], "paging": {"next": "https://evil.example/x?after=1"}}
        monkeypatch.setattr(mi, "_get", _get)
        assert mi.medir("@canal", [{"id": "OUTROxyz"}]) == {}


# --------------------------------------------------------------------------- #
# O endpoint de colar o token e o estado da conta
# --------------------------------------------------------------------------- #

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(metodo, url, json=corpo)
    return asyncio.run(_do())


def _conta(plataforma="instagram", handle="@canal"):
    r = _chama("POST", "/api/contas", {"platform": plataforma, "handle": handle})
    assert r.status_code == 200, r.text
    return r.json()


def _conexao(conta_id):
    contas = _chama("GET", "/api/contas").json()["contas"]
    return next(c for c in contas if c["id"] == conta_id)["conexao"]


class TestEndpoint:

    def test_colar_e_desconectar(self, ambiente, monkeypatch, capsys):
        conta = _conta()
        assert _conexao(conta["id"]) == {"publicar": False, "medir": False,
                                         "medir_vencido": False, "tipos": [], "token": True}
        monkeypatch.setattr(mi, "_get", ApiFalsa(me={"user_id": "1789", "username": "canal"}))
        r = _chama("POST", f"/api/contas/{conta['id']}/token", {"token": f" {TOKEN} "})
        assert r.status_code == 200, r.text
        assert r.json() == {"success": True, "conta": "canal"}
        assert TOKEN not in r.text and TOKEN not in capsys.readouterr().out
        assert mi.credencial("@canal")["access_token"] == TOKEN
        assert _conexao(conta["id"])["medir"] is True
        # O arquivo do cofre nasce 0600, como todo segredo.
        if os.name == "posix":
            caminho = vault.caminho_local("instagram-metrics", "@canal")
            assert oct(os.stat(caminho).st_mode & 0o777) == "0o600"
        r = _chama("DELETE", f"/api/contas/{conta['id']}/conexao?tipo=medir")
        assert r.status_code == 200 and r.json()["havia"] is True
        assert _conexao(conta["id"])["medir"] is False

    def test_token_de_outra_conta_diz_de_quem_e(self, ambiente, monkeypatch):
        conta = _conta()
        monkeypatch.setattr(mi, "_get", ApiFalsa(me={"user_id": "9", "username": "outra"}))
        r = _chama("POST", f"/api/contas/{conta['id']}/token", {"token": TOKEN})
        assert r.status_code == 422
        assert r.json()["detail"] == {"erro": "outra_conta", "conta": "outra"}
        assert mi.credencial("@canal") is None

    def test_so_o_instagram_cola_token(self, ambiente):
        conta = _conta("tiktok", "@canal")
        r = _chama("POST", f"/api/contas/{conta['id']}/token", {"token": TOKEN})
        assert r.status_code == 400 and r.json()["detail"]["erro"] == "plataforma"

    def test_token_torto_nem_pergunta_ao_instagram(self, ambiente, monkeypatch):
        conta = _conta()
        api = ApiFalsa()
        monkeypatch.setattr(mi, "_get", api)
        r = _chama("POST", f"/api/contas/{conta['id']}/token", {"token": "curto"})
        assert r.status_code == 422 and r.json()["detail"]["erro"] == "formato"
        assert api.pedidos == []

    def test_conta_que_nao_existe(self, ambiente):
        r = _chama("POST", f"/api/contas/{uuid.uuid4()}/token", {"token": TOKEN})
        assert r.status_code == 404

    def test_o_vencido_aparece_na_conta(self, ambiente):
        conta = _conta()
        vault.gravar(mi.ref_de("@canal"), {"access_token": TOKEN, "user_id": "1",
                                           "vencido": "1"})
        assert _conexao(conta["id"]) == {"publicar": False, "medir": False,
                                         "medir_vencido": True, "tipos": [], "token": True}

    def test_so_json(self, ambiente):
        """Formulario de outro site nao cola token: sem JSON, sem pedido."""
        conta = _conta()

        async def _do():
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.post(f"/api/contas/{conta['id']}/token",
                                    content=f'{{"token": "{TOKEN}"}}',
                                    headers={"Content-Type": "text/plain"})
        assert asyncio.run(_do()).status_code in (415, 422)
