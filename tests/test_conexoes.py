"""O cadastro do aplicativo e o "Conectar YouTube" pelo site (etapa 7.3).

O Google nao e alcancado daqui: a troca do codigo (`conexoes.trocar_codigo`) e a
conferencia do cadastro (`aplicativos.testar_google`) sao trocadas por
imitacoes, e o resto roda de verdade -- o motor, o banco, o cofre em disco e a
volta pela raiz. O que estes testes guardam:

- os escopos sao os do `youtube_oauth.py`, e a credencial de publicar nao le;
- a volta so aceita localhost, e o `state` e de uso unico e vence;
- o segredo do aplicativo nunca sai do motor;
- a conta passa a apontar para o cofre, e desconectar a devolve a fila manual.
"""
import asyncio
import base64
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")
aplicativos = pytest.importorskip("aplicativos")
conexoes = pytest.importorskip("conexoes")
metrics_collector = pytest.importorskip("metrics_collector")
vault = pytest.importorskip("vault")
youtube_oauth = pytest.importorskip("youtube_oauth")

CLIENT_ID = "123456789012-abcdefghijklmnopqrstuvwxyz012345.apps.googleusercontent.com"
SEGREDO = "GOCSPX-segredoDeMentira_1234567890ab"


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    for nome in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "saida"))
    monkeypatch.setattr(app_module, "APLICATIVOS",
                        aplicativos.Aplicativos(tmp_path / "dados", environ={}))
    monkeypatch.setattr(app_module, "PEDIDOS_DE_CONEXAO", conexoes.Pedidos())
    monkeypatch.setattr(aplicativos, "testar_google", lambda campos, **kw: "ok")
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield tmp_path
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None, cabecalhos=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo, headers=cabecalhos)
    return asyncio.run(_do())


def _com_aplicativo():
    r = _chama("POST", "/api/aplicativos", {"plataforma": "google",
                                            "client_id": CLIENT_ID,
                                            "client_secret": SEGREDO})
    assert r.status_code == 200, r.text


def _conta(plataforma="youtube", handle="@canalinfantil"):
    r = _chama("POST", "/api/contas", {"platform": plataforma, "handle": handle})
    assert r.status_code == 200, r.text
    return r.json()


def _estado_da_conta(conta_id):
    return next(c for c in _chama("GET", "/api/contas").json()["contas"] if c["id"] == conta_id)


def _state_de(url):
    return parse_qs(urlsplit(url).query)["state"][0]


# --------------------------------------------------------------------------- #
# O cadastro do aplicativo
# --------------------------------------------------------------------------- #

class TestCadastro:
    def test_limpa_os_jeitos_comuns_de_colar(self):
        assert aplicativos.limpar("google", "client_id", f"  '{CLIENT_ID}' ") == CLIENT_ID
        assert aplicativos.limpar("google", "client_id", f"YOUTUBE_CLIENT_ID={CLIENT_ID}") == CLIENT_ID
        with pytest.raises(aplicativos.AplicativoInvalido) as e:
            aplicativos.limpar("google", "client_id", "isso-nao-e-um-client-id")
        assert e.value.codigo == "formato"
        with pytest.raises(aplicativos.AplicativoInvalido) as e:
            aplicativos.limpar("google", "client_secret", "   ")
        assert e.value.codigo == "vazio"

    def test_o_json_baixado_do_google_serve(self):
        baixado = json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": SEGREDO,
                                            "redirect_uris": ["http://localhost"]}})
        assert aplicativos.limpar_pedido({"plataforma": "google", "client_id": baixado}) == \
            ("google", {"client_id": CLIENT_ID, "client_secret": SEGREDO})

    def test_cliente_da_web_e_o_tipo_errado(self):
        """Um "Aplicativo da Web" nao aceita a volta por localhost, e o erro so
        apareceria no meio do consentimento."""
        baixado = json.dumps({"web": {"client_id": CLIENT_ID, "client_secret": SEGREDO}})
        with pytest.raises(aplicativos.AplicativoInvalido) as e:
            aplicativos.limpar_pedido({"plataforma": "google", "client_id": baixado})
        assert e.value.codigo == "tipo"

    @pytest.mark.parametrize("status, corpo, resultado", [
        (400, '{"error": "invalid_grant", "error_description": "Malformed auth code."}', "ok"),
        (401, '{"error": "invalid_client", "error_description": "Unauthorized"}', "cliente"),
        (400, '{"error": "redirect_uri_mismatch"}', "tipo"),
        (503, "fora do ar", "incerto"),
    ])
    def test_a_conferencia_com_o_google(self, status, corpo, resultado):
        assert aplicativos.classificar_google(status, corpo) == resultado

    def test_a_conferencia_sem_rede_nao_derruba(self):
        class Quebra:
            def __enter__(self):
                raise httpx.ConnectError("sem internet")

            def __exit__(self, *a):
                return False
        assert aplicativos.testar_google({"client_id": CLIENT_ID, "client_secret": SEGREDO},
                                         cliente=Quebra) == "incerto"

    def test_o_env_vale_e_o_site_vence(self, tmp_path):
        env = {"YOUTUBE_CLIENT_ID": "do-env.apps.googleusercontent.com",
               "YOUTUBE_CLIENT_SECRET": "segredo-do-env-123456"}
        a = aplicativos.Aplicativos(tmp_path, environ=env)
        assert a.estado()["google"]["origem"] == "arquivo"
        a.trocar("google", {"client_id": CLIENT_ID, "client_secret": SEGREDO})
        assert a.credenciais("google") == {"client_id": CLIENT_ID, "client_secret": SEGREDO}
        assert a.estado()["google"]["origem"] == "site"
        a.trocar("google", None)
        assert a.credenciais("google")["client_secret"] == "segredo-do-env-123456"

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="permissao POSIX")
    def test_o_arquivo_nasce_0600(self, tmp_path):
        a = aplicativos.Aplicativos(tmp_path, environ={})
        a.trocar("google", {"client_id": CLIENT_ID, "client_secret": SEGREDO})
        assert stat.S_IMODE(os.stat(tmp_path / aplicativos.ARQUIVO).st_mode) == 0o600

    def test_pelo_motor_o_segredo_nunca_volta(self, ambiente):
        r = _chama("POST", "/api/aplicativos", {"plataforma": "google",
                                                "client_id": CLIENT_ID,
                                                "client_secret": SEGREDO})
        assert r.status_code == 200
        assert SEGREDO not in r.text
        estado = _chama("GET", "/api/aplicativos")
        assert SEGREDO not in estado.text
        assert estado.json()["aplicativos"]["google"] == {
            "configurado": True, "origem": "site", "client_id": CLIENT_ID}

    def test_o_google_recusando_nao_guarda(self, ambiente, monkeypatch):
        monkeypatch.setattr(aplicativos, "testar_google", lambda campos, **kw: "cliente")
        r = _chama("POST", "/api/aplicativos", {"plataforma": "google",
                                                "client_id": CLIENT_ID,
                                                "client_secret": SEGREDO})
        assert r.status_code == 422 and r.json()["detail"]["erro"] == "cliente"
        assert _chama("GET", "/api/aplicativos").json()["aplicativos"]["google"]["configurado"] is False

    def test_so_json(self, ambiente):
        r = _chama("POST", "/api/aplicativos", cabecalhos={"Content-Type": "text/plain"})
        assert r.status_code == 415


# --------------------------------------------------------------------------- #
# O que decide o consentimento -- sem rede
# --------------------------------------------------------------------------- #

class TestRegras:
    def test_os_escopos_sao_os_do_youtube_oauth(self):
        """Dois caminhos para a mesma credencial nao podem pedir coisas
        diferentes -- e o de publicar continua sem ler nem apagar."""
        assert conexoes.ESCOPOS[("youtube", "publicar")] == (youtube_oauth.ESCOPO,)
        assert conexoes.ESCOPOS[("youtube", "medir")] == youtube_oauth.ESCOPOS_DE_LEITURA
        assert conexoes.ESCOPOS[("youtube", "medir")] == metrics_collector.ESCOPOS_DE_LEITURA

    @pytest.mark.parametrize("origem, volta", [
        ("http://localhost:8000", "http://localhost:8000/"),
        ("http://127.0.0.1:5175/", "http://127.0.0.1:5175/"),
        ("http://[::1]:8001", "http://[::1]:8001/"),
    ])
    def test_a_volta_e_a_raiz_de_localhost(self, origem, volta):
        assert conexoes.volta_de(origem) == volta

    @pytest.mark.parametrize("origem", [
        "https://virtu-clips.zirtuno.workers.dev",
        "http://192.168.0.10:5175",
        "http://localhost.evil.com:8000",
        "http://localhost:8000/outra/coisa",
        "http://localhost:8000/?x=1",
        "javascript:alert(1)",
        "",
    ])
    def test_a_volta_recusa_o_que_nao_e_esta_maquina(self, origem):
        with pytest.raises(conexoes.ConexaoError) as e:
            conexoes.volta_de(origem)
        assert e.value.codigo == "volta"

    def test_pkce_no_formato_do_google(self):
        verifier, desafio = conexoes.par_pkce()
        assert 43 <= len(verifier) <= 128
        assert re.fullmatch(r"[A-Za-z0-9._~-]+", verifier)
        esperado = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert desafio == esperado

    def test_a_url_de_consentimento(self):
        url = conexoes.url_de_consentimento(CLIENT_ID, "http://localhost:8000/",
                                            "youtube", "publicar", "ESTADO", "DESAFIO")
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        assert url.startswith(conexoes.AUTORIZACAO_GOOGLE)
        assert q == {"client_id": CLIENT_ID, "redirect_uri": "http://localhost:8000/",
                     "response_type": "code",
                     "scope": "https://www.googleapis.com/auth/youtube.upload",
                     "access_type": "offline", "prompt": "consent", "state": "ESTADO",
                     "code_challenge": "DESAFIO", "code_challenge_method": "S256"}

    def test_o_pedido_e_de_uso_unico_e_vence(self):
        relogio = [0.0]
        pedidos = conexoes.Pedidos(validade_s=600, relogio=lambda: relogio[0])
        pedido = conexoes.Pedido("t", "a", "h", "youtube", "publicar", "v", "x")
        state = pedidos.novo(pedido)
        assert pedidos.consumir(state) is pedido
        assert pedidos.consumir(state) is None
        vencido = pedidos.novo(conexoes.Pedido("t", "a", "h", "youtube", "publicar", "v", "x"))
        relogio[0] = 601
        assert pedidos.consumir(vencido) is None
        assert pedidos.consumir("") is None and pedidos.consumir(None) is None

    def test_os_enderecos_do_cofre_sao_os_que_os_leitores_procuram(self):
        assert conexoes.ref_do_cofre("youtube", "publicar", "@c") == "vault://local/youtube/@c"
        assert conexoes.ref_do_cofre("youtube", "medir", "@c") == \
            metrics_collector.ref_de_leitura("@c", "local")

    def test_a_troca_manda_o_verifier_e_a_mesma_volta(self):
        enviados = {}

        class Resposta:
            status_code = 200

            def json(self):
                return {"access_token": "a", "refresh_token": "R-123"}

        class Cliente:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, data):
                enviados.update(data)
                return Resposta()
        pedido = conexoes.Pedido("t", "a", "h", "youtube", "publicar",
                                 "http://localhost:8000/", "VERIFIER")
        assert conexoes.trocar_codigo({"client_id": CLIENT_ID, "client_secret": SEGREDO},
                                      "CODIGO", pedido, cliente=Cliente) == "R-123"
        assert enviados["code_verifier"] == "VERIFIER"
        assert enviados["redirect_uri"] == "http://localhost:8000/"
        assert enviados["grant_type"] == "authorization_code"

    def test_sem_refresh_token_diz_o_que_fazer(self):
        class Resposta:
            status_code = 200

            def json(self):
                return {"access_token": "a"}

        class Cliente:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, data):
                return Resposta()
        pedido = conexoes.Pedido("t", "a", "h", "youtube", "publicar", "v", "x")
        with pytest.raises(conexoes.ConexaoError) as e:
            conexoes.trocar_codigo({"client_id": CLIENT_ID, "client_secret": SEGREDO},
                                   "C", pedido, cliente=Cliente)
        assert e.value.codigo == "sem_refresh"
        assert "myaccount.google.com/permissions" in conexoes.MENSAGENS["sem_refresh"]

    def test_a_pagina_de_volta_escapa_o_que_vem_de_fora(self):
        pagina = conexoes.pagina_de_volta(False, codigo="troca",
                                          detalhe="<script>alert(1)</script>")
        assert "<script>alert" not in pagina and "&lt;script&gt;" in pagina


# --------------------------------------------------------------------------- #
# O motor de ponta a ponta
# --------------------------------------------------------------------------- #

class TestConectar:
    def _conectar(self, conta_id, tipo="publicar", volta="http://localhost:8000"):
        return _chama("POST", f"/api/contas/{conta_id}/conectar", {"tipo": tipo, "volta": volta})

    def test_sem_o_cadastro_do_aplicativo_diz_qual_falta(self, ambiente):
        conta = _conta()
        r = self._conectar(conta["id"])
        assert r.status_code == 409 and r.json()["detail"]["erro"] == "sem_aplicativo"

    def test_so_youtube_por_enquanto(self, ambiente):
        _com_aplicativo()
        conta = _conta("tiktok", "@c")
        assert self._conectar(conta["id"]).json()["detail"]["erro"] == "plataforma"

    def test_o_painel_de_outro_aparelho_nao_conecta(self, ambiente):
        _com_aplicativo()
        conta = _conta()
        r = self._conectar(conta["id"], volta="http://192.168.0.10:5175")
        assert r.status_code == 400 and r.json()["detail"]["erro"] == "volta"

    def test_conta_que_nao_existe(self, ambiente):
        _com_aplicativo()
        assert self._conectar(str(uuid.uuid4())).status_code == 404

    def test_publicar_de_ponta_a_ponta(self, ambiente, monkeypatch):
        _com_aplicativo()
        conta = _conta()
        antes = _estado_da_conta(conta["id"])
        assert antes["conexao"] == {"publicar": False, "medir": False}
        assert antes["driver_agora"] == "manual"

        r = self._conectar(conta["id"])
        assert r.status_code == 200, r.text
        state = _state_de(r.json()["url"])
        vistos = []

        def troca(app, codigo, pedido, **kw):
            vistos.append((app["client_id"], codigo, pedido.volta, pedido.tipo))
            return "REFRESH-DO-CANAL"
        monkeypatch.setattr(conexoes, "trocar_codigo", troca)

        volta = _chama("GET", f"/?state={state}&code=CODIGO&scope=x")
        assert volta.status_code == 200
        assert "Conectado" in volta.text and "@canalinfantil" in volta.text
        assert vistos == [(CLIENT_ID, "CODIGO", "http://localhost:8000/", "publicar")]

        segredo = vault.resolve("vault://local/youtube/@canalinfantil", vault.CAMPOS)
        assert segredo == {"client_id": CLIENT_ID, "client_secret": SEGREDO,
                           "refresh_token": "REFRESH-DO-CANAL"}
        depois = _estado_da_conta(conta["id"])
        assert depois["credentials_ref"] == "vault://local/youtube/@canalinfantil"
        assert depois["conexao"] == {"publicar": True, "medir": False}
        # Com a credencial e a cota, a cascata passa a escolher a API.
        assert depois["driver_agora"] == "youtube-api"
        # O segredo nao aparece em lugar nenhum da resposta.
        assert "REFRESH-DO-CANAL" not in _chama("GET", "/api/contas").text

    def test_o_state_nao_vale_duas_vezes(self, ambiente, monkeypatch):
        _com_aplicativo()
        conta = _conta()
        state = _state_de(self._conectar(conta["id"]).json()["url"])
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: "R")
        assert _chama("GET", f"/?state={state}&code=C").status_code == 200
        segunda = _chama("GET", f"/?state={state}&code=C")
        assert segunda.status_code == 400 and "venceu" in segunda.text

    def test_state_inventado_nao_faz_nada(self, ambiente, monkeypatch):
        chamou = []
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: chamou.append(a) or "R")
        r = _chama("GET", "/?state=inventado&code=C")
        assert r.status_code == 400 and chamou == []

    def test_cancelar_no_google_nao_muda_nada(self, ambiente):
        _com_aplicativo()
        conta = _conta()
        state = _state_de(self._conectar(conta["id"]).json()["url"])
        r = _chama("GET", f"/?state={state}&error=access_denied")
        assert r.status_code == 400 and "cancelada" in r.text
        assert _estado_da_conta(conta["id"])["conexao"]["publicar"] is False

    def test_a_raiz_sem_state_continua_404(self, ambiente):
        assert _chama("GET", "/").status_code == 404

    def test_medir_guarda_onde_o_coletor_procura(self, ambiente, monkeypatch):
        _com_aplicativo()
        conta = _conta()
        state = _state_de(self._conectar(conta["id"], "medir").json()["url"])
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: "R-LEITURA")
        assert _chama("GET", f"/?state={state}&code=C").status_code == 200
        assert metrics_collector.credencial_de_leitura("@canalinfantil")["refresh_token"] == "R-LEITURA"
        depois = _estado_da_conta(conta["id"])
        assert depois["conexao"] == {"publicar": False, "medir": True}
        # A de medir nao vira a credencial de publicar da conta.
        assert depois["credentials_ref"].startswith("vault://env/")

    def test_a_volta_pelo_painel_do_docker(self, ambiente, monkeypatch):
        """No painel do Docker quem recebe a volta e o Vite (5175): o painel
        manda o codigo para o motor."""
        _com_aplicativo()
        conta = _conta()
        r = self._conectar(conta["id"], volta="http://localhost:5175")
        assert parse_qs(urlsplit(r.json()["url"]).query)["redirect_uri"] == ["http://localhost:5175/"]
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: "R")
        v = _chama("POST", "/api/oauth/volta", {"state": _state_de(r.json()["url"]), "code": "C"})
        assert v.status_code == 200
        assert v.json() == {"ok": True, "plataforma": "youtube", "tipo": "publicar",
                            "handle": "@canalinfantil"}

    def test_desconectar_volta_para_a_fila_manual(self, ambiente, monkeypatch):
        _com_aplicativo()
        conta = _conta()
        state = _state_de(self._conectar(conta["id"]).json()["url"])
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: "R-X")
        _chama("GET", f"/?state={state}&code=C")
        revogados = []
        monkeypatch.setattr(conexoes, "revogar", lambda token, **kw: revogados.append(token) or True)
        r = _chama("DELETE", f"/api/contas/{conta['id']}/conexao?tipo=publicar")
        assert r.status_code == 200 and r.json()["havia"] is True
        assert revogados == ["R-X"]
        depois = _estado_da_conta(conta["id"])
        assert depois["conexao"]["publicar"] is False
        assert depois["driver_agora"] == "manual"
        assert depois["credentials_ref"] == "vault://env/youtube/@canalinfantil"


class TestComSenha:
    def test_conectar_exige_sessao_e_a_volta_nao(self, ambiente, monkeypatch):
        _com_aplicativo()
        conta = _conta()
        r = _chama("POST", "/api/auth/bootstrap", {"email": "eu@exemplo.com",
                                                   "senha": "uma-senha-longa-9"})
        assert r.status_code == 200, r.text
        token = r.json()["token"]
        sem = _chama("POST", f"/api/contas/{conta['id']}/conectar",
                     {"tipo": "publicar", "volta": "http://localhost:8000"})
        assert sem.status_code == 401
        com = _chama("POST", f"/api/contas/{conta['id']}/conectar",
                     {"tipo": "publicar", "volta": "http://localhost:8000"},
                     cabecalhos={"Authorization": f"Bearer {token}"})
        assert com.status_code == 200
        monkeypatch.setattr(conexoes, "trocar_codigo", lambda *a, **kw: "R")
        # A volta chega do Google, sem sessao: vale pelo `state`.
        v = _chama("POST", "/api/oauth/volta", {"state": _state_de(com.json()["url"]),
                                                 "code": "C"})
        assert v.status_code == 200
        assert _chama("POST", "/api/oauth/volta", {"state": "inventado",
                                                   "code": "C"}).status_code == 400
