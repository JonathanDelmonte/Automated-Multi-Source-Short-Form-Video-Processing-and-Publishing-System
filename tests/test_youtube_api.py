"""Driver `youtube-api`, contador de quota e cofre (Fase 3, bloco 3.4).

O numero que o plano manda respeitar: **1600 unidades por `videos.insert`
contra 10.000/dia = 6 uploads/dia**. O contador existe para que o 7o upload
CAIA NA FILA MANUAL em vez de virar um job vermelho -- que e o oposto do que a
cascata da secao 6 promete.

A parte de rede deste driver nao tem como ser exercitada aqui, e por isso ela
esta isolada em tres funcoes pequenas. O que da para testar -- o que decide -- e
o que estes testes cobrem: quota, credencial, o corpo do `videos.insert` e a
traducao dos erros.
"""
import json
import os
from datetime import datetime, timezone

import pytest

import publishers
import vault
from publishers import (Account, PostMeta, PublishOptions, PublisherError,
                        QuotaEsgotada, RenderedClip, quota)
from publishers.youtube_api import (YouTubeApiPublisher, corpo_do_video,
                                    erro_da_resposta, privacidade, ref_de)


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    for nome in list(os.environ):
        if nome.startswith("YOUTUBE_"):
            monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "saida"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    yield


@pytest.fixture()
def credenciado(monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id-de-cliente")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "segredo-de-cliente")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "token-de-renovacao")
    yield


def conta(**kw):
    base = dict(id="acc", platform="youtube", handle="canal")
    base.update(kw)
    return Account(**base)


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #

class TestQuota:

    def test_o_numero_do_plano(self):
        assert quota.CUSTO_INSERT == 1600
        assert quota.TETO_PADRAO == 10000
        assert quota.uploads_por_dia() == 6

    def test_a_conta_da_secao_1_fecha(self):
        """"3 videos/dia gastam 4.800 e sobra metade para listagem e
        reprocessamento"."""
        for _ in range(3):
            quota.registrar()
        assert quota.usadas() == 4800
        assert quota.restante() == 5200

    def test_o_setimo_upload_nao_cabe(self):
        for _ in range(6):
            assert quota.cabe()
            quota.registrar()
        assert quota.cabe() is False
        assert quota.estado()["uploads_hoje"] == 6

    def test_aumento_de_quota_muda_o_teto(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_QUOTA_DAILY", "50000")
        assert quota.uploads_por_dia() == 31

    def test_teto_invalido_cai_no_padrao(self, monkeypatch):
        for valor in ("zero", "-5", "0", ""):
            monkeypatch.setenv("YOUTUBE_QUOTA_DAILY", valor)
            assert quota.teto_diario() == quota.TETO_PADRAO

    def test_o_dia_e_o_do_pacifico_e_nao_o_nosso(self):
        """A quota zera a meia-noite no Pacifico. Contar em UTC daria 7-8 horas
        por dia em que o contador e a API discordam."""
        # 06:00 UTC de 16-set ainda e dia 15 no Pacifico.
        manha_utc = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)
        assert quota.dia_do_youtube(manha_utc) == "2026-09-15"
        assert quota.dia_do_youtube(
            datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)) == "2026-09-16"

    def test_o_contador_zera_na_virada(self, monkeypatch):
        quota.registrar()
        assert quota.usadas() == 1600
        monkeypatch.setattr(quota, "dia_do_youtube", lambda agora=None: "2099-01-01")
        assert quota.usadas() == 0

    def test_arquivo_corrompido_nao_derruba(self):
        os.makedirs(os.environ["OUTPUT_DIR"], exist_ok=True)
        with open(os.path.join(os.environ["OUTPUT_DIR"], quota.ARQUIVO), "w") as fh:
            fh.write("{isso nao e json")
        assert quota.usadas() == 0
        assert quota.cabe() is True

    def test_disco_somente_leitura_nao_derruba(self, monkeypatch):
        """O contador e melhor-esforco, como o orcamento de LLM: nunca quebra
        o que estava funcionando."""
        monkeypatch.setattr(quota, "_gravar", lambda dados: None)
        assert quota.registrar() >= 0

    def test_estado_explica_por_que_caiu_na_fila(self):
        for _ in range(6):
            quota.registrar()
        estado = quota.estado()
        assert estado["cabe_mais_um"] is False
        assert estado["uploads_hoje"] == 6
        assert estado["restante"] == 400


# --------------------------------------------------------------------------- #
# Cofre
# --------------------------------------------------------------------------- #

class TestCofre:

    def test_o_endereco_do_schema_e_o_que_ele_le(self):
        import db_models
        ref = db_models.vault_ref("local", "youtube", "canal-principal")
        assert vault.partes(ref) == ("local", "youtube", "canal-principal")

    @pytest.mark.parametrize("ref", [
        "", None, "youtube/canal", "vault://local/youtube",
        "vault://local/youtube/canal/extra", "vault://nuvem/youtube/canal",
        "vault://local//canal",
    ])
    def test_endereco_invalido_e_recusado(self, ref):
        with pytest.raises(vault.VaultError):
            vault.partes(ref)

    def test_env_da_conta_padrao(self, credenciado):
        segredo = vault.resolve("vault://env/youtube/canal", vault.CAMPOS)
        assert segredo["client_id"] == "id-de-cliente"

    def test_env_com_handle_vence_o_generico(self, credenciado, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CANAL_CLIENT_ID", "id-do-canal")
        segredo = vault.resolve("vault://env/youtube/canal")
        assert segredo["client_id"] == "id-do-canal"

    def test_arquivo_local_nasce_com_0600(self):
        """Um segredo legivel por todo mundo no container e um segredo."""
        caminho = vault.gravar("vault://local/youtube/canal",
                               {"refresh_token": "abc"})
        assert oct(os.stat(caminho).st_mode & 0o777) == "0o600"
        assert vault.resolve("vault://local/youtube/canal")["refresh_token"] == "abc"

    def test_backend_env_nao_e_gravavel(self):
        """Escrever variavel de ambiente de dentro do processo nao sobrevive ao
        restart, e mexer no `.env` de quem o mantem e pior que nao gravar."""
        with pytest.raises(vault.VaultError):
            vault.gravar("vault://env/youtube/canal", {"refresh_token": "a"})

    def test_a_falta_e_dita_por_nome_de_campo(self):
        vault.gravar("vault://local/youtube/canal", {"client_id": "so-esse"})
        with pytest.raises(vault.VaultError) as e:
            vault.resolve("vault://local/youtube/canal", vault.CAMPOS)
        assert "client_secret" in str(e.value)
        assert "refresh_token" in str(e.value)

    def test_nenhuma_mensagem_carrega_o_segredo(self, credenciado):
        """Um token no log de um job e um token vazado: o log aparece no painel
        e vai para o WhatsApp quando alguem pede ajuda."""
        vault.gravar("vault://local/youtube/outro", {"client_id": "id-de-cliente"})
        mensagens = []
        for ref in ("vault://local/youtube/outro", "vault://nuvem/x/y", "",
                    "vault://local/youtube/nao-existe"):
            try:
                vault.resolve(ref, vault.CAMPOS)
            except vault.VaultError as e:
                mensagens.append(str(e))
        juntas = " ".join(mensagens)
        for segredo in ("id-de-cliente", "segredo-de-cliente", "token-de-renovacao"):
            assert segredo not in juntas

    @pytest.mark.parametrize("ref", [
        "vault://local/../canal",
        "vault://local/./canal",
        "vault://local/youtube/..",
        "vault://local/youtube/.",
        "vault://local/....../canal",
    ])
    def test_nenhum_endereco_escreve_fora_da_pasta_do_cofre(self, ref):
        """O endereco vem do corpo de `POST /api/contas`.

        `vault://local/../canal` dava `<DATA_DIR>/vault/../canal.json` -- um
        arquivo FORA do cofre, escolhido por quem mandou a requisicao. Nenhuma
        plataforma nem handle de verdade precisa de ponto-ponto.
        """
        _, plataforma, handle = vault.partes(ref)
        caminho = os.path.abspath(vault.caminho_local(plataforma, handle))
        raiz = os.path.abspath(os.path.join(os.environ["DATA_DIR"], "vault"))
        assert caminho.startswith(raiz + os.sep)

    def test_endereco_com_barra_a_mais_e_recusado_antes(self):
        """Duas barras extras nao viram nome sanitizado: nao sao um endereco."""
        with pytest.raises(vault.VaultError):
            vault.partes("vault://local/youtube/../../x")

    def test_o_nome_util_sobrevive_a_limpeza(self):
        """A defesa nao pode estragar o caso normal."""
        assert vault.caminho_local("youtube", "canal-principal").endswith(
            os.path.join("youtube", "canal-principal.json"))

    def test_existe_nao_levanta(self):
        assert vault.existe(None) is False
        assert vault.existe("lixo") is False
        assert vault.existe("vault://env/youtube/canal", vault.CAMPOS) is False

    def test_arquivo_ilegivel_e_ausencia_e_nao_erro(self, tmp_path):
        caminho = vault.caminho_local("youtube", "canal")
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w") as fh:
            fh.write("[1,2,3]")
        assert vault.resolve("vault://local/youtube/canal") == {}


# --------------------------------------------------------------------------- #
# O corpo do videos.insert
# --------------------------------------------------------------------------- #

class TestCorpoDoVideo:

    def test_privacidade_desconhecida_cai_no_mais_fechado(self):
        """Um erro de digitacao num campo de visibilidade nao pode ser o que
        publica um corte para o mundo."""
        assert privacidade("publico") == "private"
        assert privacidade("") == "private"
        assert privacidade(None) == "private"
        assert privacidade("PUBLIC") == "public"
        assert privacidade("unlisted") == "unlisted"

    def test_titulo_perde_as_setas(self):
        """A API recusa `<` e `>`, e a recusa vem DEPOIS do upload: 1600
        unidades gastas porque um hook trazia uma seta."""
        corpo = corpo_do_video(PostMeta(title="Olha isso <aqui>"),
                               PublishOptions())
        assert corpo["snippet"]["title"] == "Olha isso aqui"

    def test_titulo_cabe_em_100_chars(self):
        corpo = corpo_do_video(PostMeta(title="a" * 200), PublishOptions())
        assert len(corpo["snippet"]["title"]) == 100

    def test_titulo_vazio_ainda_e_valido(self):
        """A API recusa video sem titulo, e um corte sem titulo ainda e um
        corte."""
        assert corpo_do_video(PostMeta(), PublishOptions())["snippet"]["title"] == "Corte"

    def test_descricao_cabe_em_5000(self):
        meta = PostMeta(descriptions={"youtube": "x" * 9000})
        corpo = corpo_do_video(meta, PublishOptions())
        assert len(corpo["snippet"]["description"]) == 5000

    def test_hashtags_viram_tags_sem_cerquilha(self):
        meta = PostMeta(hashtags=("#corte", "shorts", "  ", "#viral"))
        assert corpo_do_video(meta, PublishOptions())["snippet"]["tags"] == \
            ["corte", "shorts", "viral"]

    def test_tags_respeitam_o_teto_de_500_chars(self):
        """O teto e da soma, e estourar faz a API recusar o video inteiro."""
        meta = PostMeta(hashtags=tuple(f"tag{'x' * 40}{i}" for i in range(30)))
        tags = corpo_do_video(meta, PublishOptions())["snippet"]["tags"]
        assert sum(len(t) for t in tags) <= 500
        assert len(tags) < 30

    def test_declara_que_nao_e_para_criancas(self):
        """Deixar o campo fora faz a API assumir o pior."""
        corpo = corpo_do_video(PostMeta(), PublishOptions())
        assert corpo["status"]["selfDeclaredMadeForKids"] is False

    def test_agendamento_so_em_video_privado(self):
        """`publishAt` num video ja publico e erro 400."""
        quando = "2026-09-20T12:00:00Z"
        privado = corpo_do_video(PostMeta(),
                                 PublishOptions(visibility="private",
                                                scheduled_at=quando))
        publico = corpo_do_video(PostMeta(),
                                 PublishOptions(visibility="public",
                                                scheduled_at=quando))
        assert privado["status"]["publishAt"] == quando
        assert "publishAt" not in publico["status"]

    def test_idioma_entra_quando_conhecido(self):
        corpo = corpo_do_video(PostMeta(language="pt"), PublishOptions())
        assert corpo["snippet"]["defaultLanguage"] == "pt"
        assert "defaultLanguage" not in corpo_do_video(PostMeta(),
                                                       PublishOptions())["snippet"]

    def test_categoria_configuravel(self, monkeypatch):
        assert corpo_do_video(PostMeta(), PublishOptions())["snippet"]["categoryId"] == "22"
        monkeypatch.setenv("YOUTUBE_CATEGORY_ID", "28")
        assert corpo_do_video(PostMeta(), PublishOptions())["snippet"]["categoryId"] == "28"


class TestTraducaoDeErro:

    @pytest.mark.parametrize("razao", ["quotaExceeded", "dailyLimitExceeded",
                                       "rateLimitExceeded"])
    def test_quota_vira_quota_esgotada(self, razao):
        """Quota estourada nao e falha do corte: e o sinal de que os proximos
        vao para a fila manual."""
        corpo = json.dumps({"error": {"message": "sem quota",
                                      "errors": [{"reason": razao}]}})
        assert isinstance(erro_da_resposta(403, corpo), QuotaEsgotada)

    def test_outro_erro_e_erro_de_driver(self):
        corpo = json.dumps({"error": {"message": "titulo invalido",
                                      "errors": [{"reason": "invalidTitle"}]}})
        erro = erro_da_resposta(400, corpo)
        assert isinstance(erro, PublisherError)
        assert not isinstance(erro, QuotaEsgotada)
        assert "titulo invalido" in str(erro)

    def test_resposta_que_nao_e_json_nao_derruba(self):
        erro = erro_da_resposta(502, "<html>Bad Gateway</html>")
        assert isinstance(erro, PublisherError)
        assert "502" in str(erro)

    def test_resposta_vazia(self):
        assert isinstance(erro_da_resposta(500, ""), PublisherError)


# --------------------------------------------------------------------------- #
# O driver na cascata
# --------------------------------------------------------------------------- #

class TestDriverNaCascata:

    def test_a_ordem_e_a_da_secao_6(self):
        ids = publishers.driver_ids()
        assert ids.index("youtube-api") < ids.index("aggregator") < ids.index("manual")

    def test_sem_credencial_cai_na_fila_manual(self):
        assert publishers.resolve("youtube", conta()).id == "manual"

    def test_com_credencial_e_quota_ele_atende(self, credenciado):
        assert publishers.resolve("youtube", conta()).id == "youtube-api"

    def test_quota_acabada_devolve_o_corte_para_a_fila(self, credenciado):
        """O comportamento inteiro do bloco em uma linha: o 7o upload do dia
        cai na fila manual em vez de virar um job vermelho."""
        for _ in range(6):
            quota.registrar()
        assert publishers.resolve("youtube", conta()).id == "manual"

    def test_a_conta_pode_pedir_a_fila_manual(self, credenciado):
        assert publishers.resolve(
            "youtube", conta(driver_pref="manual")).id == "manual"

    def test_custo_em_unidades_de_quota(self):
        custo = YouTubeApiPublisher().cost(3)
        assert custo.quota_units == 4800
        assert custo.usd == 0.0
        assert custo.risk_score == 0.0

    def test_e_de_risco_zero_como_o_manual(self):
        """"Seu canal do YouTube" -- e a API oficial, com o token do dono."""
        assert publishers.entra_na_cascata(YouTubeApiPublisher()) is True

    def test_capability_diz_por_que_nao_atende(self, credenciado):
        driver = YouTubeApiPublisher()
        assert driver.capability(conta()) == "public"
        for _ in range(6):
            quota.registrar()
        assert driver.capability(conta()) == "none"

    def test_app_nao_verificado_e_private_only(self, credenciado, monkeypatch):
        monkeypatch.setenv("YOUTUBE_APP_UNVERIFIED", "1")
        assert YouTubeApiPublisher().capability(conta()) == "private_only"

    def test_outra_plataforma_nao_e_com_ele(self, credenciado):
        assert YouTubeApiPublisher().capability(
            conta(platform="tiktok")) == "none"

    def test_ref_padrao_quando_a_conta_nao_tem(self):
        assert ref_de(conta()) == "vault://env/youtube/canal"
        assert ref_de(conta(credentials_ref="vault://local/youtube/x")) == \
            "vault://local/youtube/x"


class TestPublish:

    def test_arquivo_ausente_e_falha_e_nao_excecao(self, credenciado, tmp_path):
        r = YouTubeApiPublisher().publish(
            RenderedClip(path=str(tmp_path / "nao-existe.mp4"), job_id="j", index=0),
            PostMeta(), PublishOptions(), conta())
        assert r.ok is False and r.status == "failed"

    def test_sem_quota_levanta_quota_esgotada(self, credenciado, tmp_path):
        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x")
        for _ in range(6):
            quota.registrar()
        with pytest.raises(QuotaEsgotada) as e:
            YouTubeApiPublisher().publish(
                RenderedClip(path=str(arquivo), job_id="j", index=0),
                PostMeta(), PublishOptions(), conta())
        assert "fila manual" in str(e.value)

    def test_dry_run_nao_gasta_quota_nem_toca_a_rede(self, credenciado, tmp_path):
        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x")
        r = YouTubeApiPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(title="T"), PublishOptions(dry_run=True), conta())
        assert r.ok is True
        assert quota.usadas() == 0
        assert '"title": "T"' in r.detail

    def test_debita_a_quota_antes_de_chamar(self, credenciado, tmp_path,
                                            monkeypatch):
        """O YouTube cobra quando aceita a requisicao: um upload que morre no
        meio ja gastou as 1600. Contar so no sucesso deixaria o contador abaixo
        da verdade justamente no dia ruim."""
        from publishers import youtube_api

        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x" * 10)

        def explode(*a, **kw):
            raise PublisherError("a rede caiu no meio")

        monkeypatch.setattr(youtube_api, "_token_de_acesso", explode)
        with pytest.raises(PublisherError):
            YouTubeApiPublisher().publish(
                RenderedClip(path=str(arquivo), job_id="j", index=0),
                PostMeta(title="T"), PublishOptions(), conta())
        assert quota.usadas() == 1600

    def test_caminho_feliz_com_a_rede_dublada(self, credenciado, tmp_path,
                                              monkeypatch):
        from publishers import youtube_api

        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x" * 10)
        monkeypatch.setattr(youtube_api, "_token_de_acesso", lambda s: "tok")
        monkeypatch.setattr(youtube_api, "_abrir_sessao",
                            lambda t, c, n: "https://upload/sessao")
        monkeypatch.setattr(youtube_api, "_enviar_arquivo", lambda d, c: {
            "id": "VIDEOID123", "status": {"privacyStatus": "private"}})
        r = YouTubeApiPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(title="T"), PublishOptions(visibility="private"), conta())
        assert r.ok is True
        assert r.status == "published"
        assert r.remote_id == "VIDEOID123"
        assert r.url == "https://www.youtube.com/watch?v=VIDEOID123"
        assert "restam 8400" in r.detail

    def test_avisa_quando_o_youtube_rebaixa_a_privacidade(self, credenciado,
                                                          tmp_path, monkeypatch):
        """Pedir `public` e receber `private` e a diferenca entre "publiquei" e
        "subiu, mas ninguem ve"."""
        from publishers import youtube_api

        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x" * 10)
        monkeypatch.setattr(youtube_api, "_token_de_acesso", lambda s: "tok")
        monkeypatch.setattr(youtube_api, "_abrir_sessao", lambda t, c, n: "u")
        monkeypatch.setattr(youtube_api, "_enviar_arquivo", lambda d, c: {
            "id": "V", "status": {"privacyStatus": "private"}})
        r = YouTubeApiPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(title="T"), PublishOptions(visibility="public"), conta())
        assert "pedimos public" in r.detail
        assert "verificado" in r.detail

    def test_status_devolvido_cabe_no_check_do_banco(self, credenciado,
                                                     tmp_path, monkeypatch):
        import db_models
        from publishers import youtube_api

        arquivo = tmp_path / "c.mp4"
        arquivo.write_bytes(b"x")
        monkeypatch.setattr(youtube_api, "_token_de_acesso", lambda s: "tok")
        monkeypatch.setattr(youtube_api, "_abrir_sessao", lambda t, c, n: "u")
        monkeypatch.setattr(youtube_api, "_enviar_arquivo",
                            lambda d, c: {"id": "V"})
        r = YouTubeApiPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(), PublishOptions(), conta())
        assert r.status in db_models.PUB_STATUSES


class TestAjudanteDeOAuth:
    """O script que emite o refresh token. Sem ele o driver e inutilizavel: a
    API exige um token que so nasce de um consentimento no navegador."""

    def test_o_escopo_e_so_o_de_upload(self):
        """`youtube` completo daria a este token o poder de APAGAR videos do
        canal. Se ele vazar, a diferenca entre os dois escopos e a diferenca
        entre um video indesejado e um canal vazio."""
        import youtube_oauth
        assert youtube_oauth.ESCOPO.endswith("/youtube.upload")

    def test_pede_offline_e_consent(self):
        """`access_type=offline` e o que faz o Google devolver refresh_token;
        sem `prompt=consent` a segunda execucao volta SEM ele, e o erro nao diz
        por que."""
        import inspect

        import youtube_oauth
        fonte = inspect.getsource(youtube_oauth.main)
        assert '"access_type": "offline"' in fonte
        assert '"prompt": "consent"' in fonte

    def test_grava_no_mesmo_endereco_que_o_driver_le(self, tmp_path,
                                                     monkeypatch):
        """O script e o driver tem de concordar sobre onde o segredo mora."""
        import youtube_oauth
        from publishers.youtube_api import ref_de

        ref = f"vault://local/youtube/{'canal'}"
        vault.gravar(ref, {"client_id": "i", "client_secret": "s",
                           "refresh_token": "r"})
        assert vault.existe(ref, vault.CAMPOS)
        assert ref_de(conta(credentials_ref=ref)) == ref
        assert youtube_oauth.ESCOPO  # o modulo carrega sem rede

    def test_sem_client_id_sai_com_erro_em_vez_de_travar(self, monkeypatch,
                                                         capsys):
        import youtube_oauth
        monkeypatch.setattr("builtins.input", lambda *a: "")
        assert youtube_oauth.main(["--handle", "x"]) == 2
        assert "Client ID" in capsys.readouterr().err
