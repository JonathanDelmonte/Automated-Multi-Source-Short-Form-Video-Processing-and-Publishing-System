"""Auth propria -- Fase 4, bloco 4.1.

A secao 7 adiou isto de proposito: "adicionar auth sobre um schema que ja tem
tenant e um sabado de trabalho". O que estes testes guardam:

**A auth nao tem flag: liga quando algum usuario ganha senha.** E o bootstrap
nao cria conta -- ele da senha ao `self-host@localhost` que o seed ja criou e
que ja e dono de tudo o que ha em disco. Criar um usuario novo ali deixaria os
jobs e templates de ontem pertencendo a uma conta em que ninguem entra.

**A tranca e middleware, nao decoracao por endpoint.** Uma rota nova nasce
protegida; quem quiser o contrario escreve o caminho em `ROTAS_PUBLICAS`. O
teste que importa mais aqui e `test_toda_rota_de_api_exige_sessao`, que varre a
lista de rotas do app em vez de conferir uma por uma.
"""
import asyncio
import os
import time

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")

SENHA = "uma-senha-boa-1"


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    """Banco e DATA_DIR proprios. O DATA_DIR importa: e onde moram o segredo de
    sessao e o marcador de auth ativa, e um teste nao pode herdar nem deixar
    nenhum dos dois para o seguinte."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    auth.esquecer_segredo()
    auth.limpar_tentativas()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield tmp_path
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None, token=None):
    async def _do():
        cabecalhos = {"Authorization": f"Bearer {token}"} if token else None
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo,
                                        headers=cabecalhos)
    return asyncio.run(_do())


def _bootstrap(email="eu@exemplo.com", senha=SENHA):
    r = _chama("POST", "/api/auth/bootstrap", {"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --------------------------------------------------------------------------- #
# Senha
# --------------------------------------------------------------------------- #

class TestSenha:

    def test_hash_nao_e_a_senha(self):
        h = auth.hash_de_senha(SENHA)
        assert SENHA not in h
        assert h.startswith("scrypt$")

    def test_duas_senhas_iguais_dao_hashes_diferentes(self):
        """Sal por senha: sem ele, duas contas com a mesma senha teriam o mesmo
        hash e quebrar uma quebraria todas."""
        assert auth.hash_de_senha(SENHA) != auth.hash_de_senha(SENHA)

    def test_confere_a_certa_e_recusa_a_errada(self):
        h = auth.hash_de_senha(SENHA)
        assert auth.senha_confere(SENHA, h) is True
        assert auth.senha_confere(SENHA + "x", h) is False
        assert auth.senha_confere("", h) is False

    def test_senha_curta_e_recusada(self):
        with pytest.raises(auth.AuthError):
            auth.hash_de_senha("curta")

    @pytest.mark.parametrize("guardado", [
        None, "", "nao-e-hash", "scrypt$", "scrypt$a$b$c$d$e",
        "bcrypt$1$1$1$AAAA$AAAA", "scrypt$16384$8$1$AAAA",
    ])
    def test_hash_corrompido_e_falso_e_nao_excecao(self, guardado):
        """Uma linha estragada no banco nao pode virar 500 no login -- nem,
        pior, virar um `except` que deixa entrar."""
        assert auth.senha_confere(SENHA, guardado) is False

    def test_parametros_ficam_no_hash(self):
        """Guardados junto para que endurecer o scrypt depois nao invalide as
        senhas ja gravadas: a verificacao le os que foram usados na hora."""
        h = auth.hash_de_senha(SENHA)
        assert h.split("$")[1:4] == [str(auth.SCRYPT_N), str(auth.SCRYPT_R),
                                     str(auth.SCRYPT_P)]
        endurecido = h.replace(f"scrypt${auth.SCRYPT_N}$", "scrypt$1024$", 1)
        assert auth.senha_confere(SENHA, endurecido) is False


# --------------------------------------------------------------------------- #
# Token
# --------------------------------------------------------------------------- #

class TestToken:

    def test_ida_e_volta(self):
        p = auth.ler_token(auth.gerar_token("u1", "t1", 7))
        assert p["u"] == "u1" and p["t"] == "t1" and p["v"] == 7

    def test_assinatura_adulterada_nao_passa(self):
        t = auth.gerar_token("u1", "t1")
        assert auth.ler_token(t[:-4] + "AAAA") is None

    def test_payload_trocado_nao_passa(self):
        """O ataque obvio: pegar o proprio token e trocar o tenant pelo do
        vizinho. Sem o segredo, a assinatura nao acompanha."""
        import base64
        import json
        corpo, _, assinatura = auth.gerar_token("u1", "t1").partition(".")
        payload = json.loads(auth._b64d(corpo))
        payload["t"] = "tenant-do-vizinho"
        novo = auth._b64e(json.dumps(payload, separators=(",", ":"),
                                     sort_keys=True).encode())
        assert auth.ler_token(f"{novo}.{assinatura}") is None
        assert base64  # noqa: usado acima via auth._b64*

    def test_token_expirado_nao_passa(self):
        assert auth.ler_token(auth.gerar_token("u1", "t1", ttl=-1)) is None

    @pytest.mark.parametrize("ruim", [
        None, "", "sem-ponto", ".", "a.b", "....", "nao.base64!!",
    ])
    def test_lixo_nao_derruba_o_leitor(self, ruim):
        assert auth.ler_token(ruim) is None

    def test_segredo_de_outra_instalacao_nao_serve(self, monkeypatch):
        t = auth.gerar_token("u1", "t1")
        monkeypatch.setenv("SESSION_SECRET", "outro-segredo-qualquer")
        auth.esquecer_segredo()
        assert auth.ler_token(t) is None

    def test_o_segredo_sobrevive_ao_restart(self, ambiente):
        """Um segredo sorteado na memoria deslogaria todo mundo a cada deploy."""
        t = auth.gerar_token("u1", "t1")
        auth.esquecer_segredo()          # como se o processo tivesse reiniciado
        assert auth.ler_token(t) is not None

    def test_o_arquivo_do_segredo_e_0600(self, ambiente):
        auth.segredo_de_sessao()
        caminho = os.path.join(str(ambiente / "dados"), auth.ARQUIVO_SEGREDO)
        assert oct(os.stat(caminho).st_mode & 0o777) == "0o600"

    def test_o_segredo_em_texto_preserva_os_32_bytes(self):
        """`decode("utf-8", "ignore")` sobre bytes aleatorios DESCARTA os que
        nao formam UTF-8 valido -- medido, sobram de 13 a 21 caracteres dos 32
        bytes, e sempre os mesmos tipos. A chave encolhe e envieza sem aviso.
        Foi assim que o token de midia do bloco 4.3 quase nasceu mais fraco."""
        import base64
        texto = auth.segredo_texto()
        assert texto.isascii()
        assert len(base64.urlsafe_b64decode(texto + "==")) == 32
        assert base64.urlsafe_b64decode(texto + "==") == auth.segredo_de_sessao()

    def test_bearer_do_header(self):
        assert auth.token_do_header("Bearer abc") == "abc"
        assert auth.token_do_header("bearer abc") == "abc"
        for ruim in (None, "", "abc", "Basic abc", "Bearer", "Bearer   "):
            assert auth.token_do_header(ruim) is None


class TestForcaBruta:

    def test_trava_depois_de_muitas_falhas(self):
        for _ in range(auth.MAX_TENTATIVAS):
            assert auth.esta_travado("x") is False
            auth.registrar_falha("x")
        assert auth.esta_travado("x") is True

    def test_a_trava_expira(self, monkeypatch):
        for _ in range(auth.MAX_TENTATIVAS):
            auth.registrar_falha("x")
        assert auth.esta_travado("x") is True
        # `auth.time` E o modulo `time` global, entao um lambda que chame
        # `time.time()` chamaria a si mesmo. O relogio real vai preso agora.
        agora = time.time()
        monkeypatch.setattr(auth.time, "time",
                            lambda: agora + auth.TRAVA_SEGUNDOS + 1)
        assert auth.esta_travado("x") is False

    def test_uma_chave_nao_trava_a_outra(self):
        for _ in range(auth.MAX_TENTATIVAS):
            auth.registrar_falha("a")
        assert auth.esta_travado("a") is True
        assert auth.esta_travado("b") is False


# --------------------------------------------------------------------------- #
# Bootstrap
# --------------------------------------------------------------------------- #

class TestBootstrap:

    def test_antes_do_bootstrap_a_api_esta_aberta(self):
        """O comportamento anterior a Fase 4, intacto: quem nunca quis auth
        continua sem ela."""
        assert _chama("GET", "/api/config").json()["authAtiva"] is False
        assert _chama("GET", "/api/templates").status_code == 200

    def test_nao_cria_conta_nova_e_aproveita_a_do_seed(self, ambiente):
        """O ponto inteiro do desenho: o dono do tenant fixo ja possui tudo o
        que ha em disco. Criar um usuario novo aqui deixaria os jobs e
        templates de ontem numa conta em que ninguem entra."""
        _bootstrap()

        async def _t():
            async with db.tenant() as t:
                return await t.all(db_models.User)
        usuarios = corre(_t)
        assert len(usuarios) == 1, "o bootstrap criou um usuario a mais"
        assert usuarios[0].email == "eu@exemplo.com"
        assert usuarios[0].tenant_id == db.SELF_HOST_TENANT_ID
        assert usuarios[0].role == "owner"

    def test_depois_do_bootstrap_a_api_exige_login(self):
        _bootstrap()
        assert _chama("GET", "/api/config").json()["authAtiva"] is True
        assert _chama("GET", "/api/templates").status_code == 401

    def test_o_token_do_bootstrap_ja_serve(self):
        token = _bootstrap()
        assert _chama("GET", "/api/templates", token=token).status_code == 200

    def test_bootstrap_uma_vez_so(self):
        _bootstrap()
        r = _chama("POST", "/api/auth/bootstrap",
                   {"email": "outro@exemplo.com", "senha": SENHA})
        assert r.status_code == 409
        assert "ja tem dono" in r.json()["detail"]

    def test_senha_curta_e_recusada_com_motivo(self):
        r = _chama("POST", "/api/auth/bootstrap",
                   {"email": "eu@exemplo.com", "senha": "abc"})
        assert r.status_code == 400
        assert str(auth.MIN_SENHA) in r.json()["detail"]

    def test_deixa_marcador_em_disco(self, ambiente):
        """O banco e a autoridade, mas a resposta precisa existir com ele fora
        do ar -- senao um container novo subindo com o banco em pe de guerra
        destrancaria a API."""
        _bootstrap()
        assert os.path.exists(os.path.join(str(ambiente / "dados"),
                                           app_module.ARQUIVO_AUTH_ATIVA))


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #

class TestLogin:

    def test_entra_com_a_senha_certa(self):
        _bootstrap()
        r = _chama("POST", "/api/auth/login",
                   {"email": "eu@exemplo.com", "senha": SENHA})
        assert r.status_code == 200
        assert _chama("GET", "/api/me", token=r.json()["token"]).json()["email"] \
            == "eu@exemplo.com"

    def test_senha_errada_e_401(self):
        _bootstrap()
        assert _chama("POST", "/api/auth/login",
                      {"email": "eu@exemplo.com", "senha": "outra-senha-1"}
                      ).status_code == 401

    def test_a_mensagem_nao_diz_se_o_email_existe(self):
        """Dizer "este e-mail nao existe" entrega a lista de usuarios a quem
        estiver tentando."""
        _bootstrap()
        errada = _chama("POST", "/api/auth/login",
                        {"email": "eu@exemplo.com", "senha": "outra-senha-1"})
        inexistente = _chama("POST", "/api/auth/login",
                             {"email": "ninguem@exemplo.com", "senha": SENHA})
        assert errada.status_code == inexistente.status_code == 401
        assert errada.json()["detail"] == inexistente.json()["detail"]

    def test_trava_depois_de_insistir(self):
        _bootstrap()
        for _ in range(auth.MAX_TENTATIVAS):
            _chama("POST", "/api/auth/login",
                   {"email": "eu@exemplo.com", "senha": "errada-mas-longa"})
        r = _chama("POST", "/api/auth/login",
                   {"email": "eu@exemplo.com", "senha": SENHA})
        assert r.status_code == 429

    def test_acertar_limpa_o_contador(self):
        _bootstrap()
        for _ in range(auth.MAX_TENTATIVAS - 1):
            _chama("POST", "/api/auth/login",
                   {"email": "eu@exemplo.com", "senha": "errada-mas-longa"})
        assert _chama("POST", "/api/auth/login",
                      {"email": "eu@exemplo.com", "senha": SENHA}).status_code == 200
        for _ in range(auth.MAX_TENTATIVAS - 1):
            _chama("POST", "/api/auth/login",
                   {"email": "eu@exemplo.com", "senha": "errada-mas-longa"})
        assert _chama("POST", "/api/auth/login",
                      {"email": "eu@exemplo.com", "senha": SENHA}).status_code == 200


# --------------------------------------------------------------------------- #
# A tranca
# --------------------------------------------------------------------------- #

class TestTranca:

    def test_toda_rota_de_api_exige_sessao(self):
        """Varre as rotas do app em vez de conferir uma por uma.

        Exigir sessao endpoint a endpoint significaria lembrar disso em ~60
        lugares, e a rota esquecida nao da erro -- so fica aberta. Este teste e
        o que transforma o esquecimento em vermelho: uma rota nova que responda
        sem token e sem estar em `ROTAS_PUBLICAS` quebra aqui.
        """
        _bootstrap()
        vistas = 0
        for rota in app_module.app.routes:
            caminho = getattr(rota, "path", "")
            if not caminho.startswith("/api/") or "{" in caminho:
                continue
            if app_module._rota_publica(caminho):
                continue
            for metodo in sorted(getattr(rota, "methods", set()) - {"HEAD", "OPTIONS"}):
                r = _chama(metodo, caminho, corpo={})
                assert r.status_code == 401, (
                    f"{metodo} {caminho} respondeu {r.status_code} sem sessao")
                vistas += 1
        assert vistas > 20, "a varredura nao encontrou rotas; o teste nao mede nada"

    def test_as_publicas_continuam_publicas(self):
        _bootstrap()
        assert _chama("GET", "/api/config").status_code == 200
        assert _chama("GET", "/health").status_code == 200

    def test_a_lista_de_publicas_e_curta_e_deliberada(self):
        """Se ela crescer, foi decisao de alguem -- e este teste obriga a
        escrever o porque no commit."""
        assert app_module.ROTAS_PUBLICAS == ("/api/config", "/api/auth/", "/health")

    def test_token_de_outro_segredo_nao_entra(self, monkeypatch):
        _bootstrap()
        monkeypatch.setenv("SESSION_SECRET", "segredo-de-outra-instalacao")
        auth.esquecer_segredo()
        forjado = auth.gerar_token("qualquer", db.SELF_HOST_TENANT_ID, 1)
        auth.esquecer_segredo()
        monkeypatch.delenv("SESSION_SECRET")
        auth.esquecer_segredo()
        assert _chama("GET", "/api/templates", token=forjado).status_code == 401

    def test_token_de_usuario_apagado_nao_entra(self):
        token = _bootstrap()

        async def _t():
            async with db.tenant() as t:
                for u in await t.all(db_models.User):
                    await t.session.delete(u)
                await t.commit()
        corre(_t)
        # Sem usuario com senha a instalacao volta a ser aberta -- mas o token
        # nao pode mais identificar ninguem.
        assert _chama("GET", "/api/me", token=token).json()["user_id"] is None


class TestRevogacao:

    def test_trocar_a_senha_invalida_os_tokens_antigos(self):
        """Trocar a senha porque ela pode ter vazado e deixar as sessoes antigas
        vivas resolve a metade que nao importa."""
        antigo = _bootstrap()
        r = _chama("POST", "/api/auth/senha",
                   {"senha_atual": SENHA, "senha_nova": "outra-senha-boa-2"},
                   token=antigo)
        assert r.status_code == 200
        assert _chama("GET", "/api/templates", token=antigo).status_code == 401
        assert _chama("GET", "/api/templates",
                      token=r.json()["token"]).status_code == 200

    def test_senha_atual_errada_nao_troca(self):
        token = _bootstrap()
        assert _chama("POST", "/api/auth/senha",
                      {"senha_atual": "chute-bem-longo", "senha_nova": "nova-senha-3"},
                      token=token).status_code == 401
        assert _chama("GET", "/api/templates", token=token).status_code == 200

    def test_senha_nova_curta_e_recusada(self):
        token = _bootstrap()
        assert _chama("POST", "/api/auth/senha",
                      {"senha_atual": SENHA, "senha_nova": "abc"},
                      token=token).status_code == 400

    def test_sair_de_tudo_derruba_o_proprio_token(self):
        token = _bootstrap()
        assert _chama("POST", "/api/auth/sair-de-tudo", token=token).status_code == 200
        assert _chama("GET", "/api/templates", token=token).status_code == 401


# --------------------------------------------------------------------------- #
# O criterio da fase
# --------------------------------------------------------------------------- #

class TestSegundaConta:

    def test_a_segunda_conta_nasce_num_tenant_proprio(self):
        """Um terco do criterio de pronto da Fase 4.

        Os outros dois estao nos blocos seguintes: os DADOS de cada tenant
        (4.2 -- hoje `/api/templates` ainda le o tenant fixo) e os ARQUIVOS
        (4.3). Aqui so se garante que a conta nasce num tenant proprio, que e o
        que torna os outros dois possiveis.
        """
        dono = _bootstrap()
        r = _chama("POST", "/api/usuarios",
                   {"email": "outra@exemplo.com", "senha": "senha-da-outra-1"},
                   token=dono)
        assert r.status_code == 200, r.text
        assert r.json()["tenant_id"] != db.SELF_HOST_TENANT_ID
        assert r.json()["role"] == "owner", "tenant novo nasce com dono"

    def test_a_segunda_conta_nao_ve_os_usuarios_da_primeira(self):
        dono = _bootstrap()
        _chama("POST", "/api/usuarios",
               {"email": "outra@exemplo.com", "senha": "senha-da-outra-1"},
               token=dono)
        outro = _chama("POST", "/api/auth/login",
                       {"email": "outra@exemplo.com", "senha": "senha-da-outra-1"}
                       ).json()["token"]
        emails = [u["email"] for u in
                  _chama("GET", "/api/usuarios", token=outro).json()["usuarios"]]
        assert emails == ["outra@exemplo.com"]

    def test_conta_no_mesmo_tenant_e_editor_e_ve_o_mesmo(self):
        dono = _bootstrap()
        r = _chama("POST", "/api/usuarios",
                   {"email": "ajudante@exemplo.com", "senha": "senha-ajudante-1",
                    "tenant": "mesmo"}, token=dono)
        assert r.json()["tenant_id"] == db.SELF_HOST_TENANT_ID
        assert r.json()["role"] == "editor"

    def test_so_o_dono_cria_conta(self):
        """Nao ha cadastro aberto: isto e ferramenta pessoal, nao SaaS."""
        dono = _bootstrap()
        _chama("POST", "/api/usuarios",
               {"email": "ajudante@exemplo.com", "senha": "senha-ajudante-1",
                "tenant": "mesmo"}, token=dono)
        ajudante = _chama("POST", "/api/auth/login",
                          {"email": "ajudante@exemplo.com",
                           "senha": "senha-ajudante-1"}).json()["token"]
        r = _chama("POST", "/api/usuarios",
                   {"email": "mais@exemplo.com", "senha": "senha-mais-1"},
                   token=ajudante)
        assert r.status_code == 403

    def test_email_repetido_no_mesmo_tenant_e_recusado(self):
        dono = _bootstrap()
        corpo = {"email": "x@exemplo.com", "senha": "senha-do-x-1", "tenant": "mesmo"}
        assert _chama("POST", "/api/usuarios", corpo, token=dono).status_code == 200
        assert _chama("POST", "/api/usuarios", corpo, token=dono).status_code == 409

    def test_role_e_tenant_invalidos_sao_recusados(self):
        dono = _bootstrap()
        assert _chama("POST", "/api/usuarios",
                      {"email": "a@b.com", "senha": "senha-boa-12",
                       "tenant": "outro"}, token=dono).status_code == 400
        assert _chama("POST", "/api/usuarios",
                      {"email": "a@b.com", "senha": "senha-boa-12",
                       "role": "admin"}, token=dono).status_code == 400
