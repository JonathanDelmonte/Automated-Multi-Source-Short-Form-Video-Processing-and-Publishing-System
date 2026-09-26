"""Driver `tiktok-api` (etapa 7.3): o Direct Post do Content Posting API.

A rede do TikTok nao e alcancada daqui: `_pedir`, `_enviar_pedaco` e `renovar`
sao trocadas por imitacoes que respondem como a documentacao diz. O que decide
-- os pedacos do envio, a privacidade, a legenda, o corpo do `init` e as frases
de erro -- roda de verdade.
"""
import os

import pytest

import publishers
import vault
from publishers import Account, PostMeta, PublishOptions, PublisherError, RenderedClip
from publishers import tiktok_api as T

MB = 1024 * 1024


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "saida"))
    monkeypatch.delenv("TIKTOK_APP_AUDITADO", raising=False)
    monkeypatch.setattr(T, "INTERVALO_DO_STATUS_S", 0)
    yield tmp_path


def conta(**kw):
    base = dict(id="acc", platform="tiktok", handle="@canalinfantil",
                credentials_ref="vault://local/tiktok/@canalinfantil")
    base.update(kw)
    return Account(**base)


def _conectada():
    vault.gravar("vault://local/tiktok/@canalinfantil", {
        "client_key": "sbawabcdef123456", "client_secret": "segredo-do-app-123",
        "refresh_token": "R-1", "open_id": "O"})


def _corte(tmp_path, tamanho=2 * MB, duracao=30.0):
    arquivo = tmp_path / "v_clip_1.mp4"
    arquivo.write_bytes(b"\x00" * tamanho)
    return RenderedClip(path=str(arquivo), job_id="j", index=0, duration_s=duracao)


# --------------------------------------------------------------------------- #
# Os pedacos do envio (Media Transfer Guide)
# --------------------------------------------------------------------------- #

class TestPedacos:
    @pytest.mark.parametrize("tamanho", [1, 3 * MB, 5 * MB, 40 * MB, 64 * MB])
    def test_ate_64_mb_vai_inteiro(self, tamanho):
        assert T.plano_de_pedacos(tamanho) == (tamanho, 1)
        assert T.pedacos(tamanho) == [(0, tamanho - 1)]

    @pytest.mark.parametrize("tamanho", [64 * MB + 1, 95 * MB + 7, 500 * MB + 123])
    def test_acima_disso_em_pedacos_que_cobrem_tudo(self, tamanho):
        passo, total = T.plano_de_pedacos(tamanho)
        assert T.PEDACO_MINIMO <= passo <= T.PEDACO_MAXIMO
        # Arredondado para BAIXO: para cima daria um ultimo pedaco abaixo de
        # 5 MB, que o TikTok recusa.
        assert total == tamanho // passo
        partes = T.pedacos(tamanho)
        assert len(partes) == total
        assert partes[0][0] == 0 and partes[-1][1] == tamanho - 1
        assert all(b[0] == a[1] + 1 for a, b in zip(partes, partes[1:]))
        ultimo = partes[-1][1] - partes[-1][0] + 1
        assert passo <= ultimo <= 128 * MB

    def test_arquivo_vazio(self):
        with pytest.raises(PublisherError):
            T.plano_de_pedacos(0)


# --------------------------------------------------------------------------- #
# O que decide
# --------------------------------------------------------------------------- #

class TestRegras:
    @pytest.mark.parametrize("pedida, opcoes, esperada", [
        ("private", ["SELF_ONLY"], "SELF_ONLY"),
        ("public", ["SELF_ONLY"], "SELF_ONLY"),
        ("public", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "PUBLIC_TO_EVERYONE"),
        ("private", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "SELF_ONLY"),
        ("PUBLICO", ["PUBLIC_TO_EVERYONE", "SELF_ONLY"], "SELF_ONLY"),
        ("public", ["MUTUAL_FOLLOW_FRIENDS"], "MUTUAL_FOLLOW_FRIENDS"),
    ])
    def test_auditado_a_privacidade_e_a_mais_fechada_na_duvida(self, pedida, opcoes, esperada):
        assert T.escolher_privacidade(pedida, opcoes, auditado=True) == esperada

    @pytest.mark.parametrize("pedida", ["public", "private", "", None])
    def test_antes_da_auditoria_e_sempre_so_para_voce(self, pedida):
        """A conta pode oferecer publico (o creator_info fala da CONTA, nao do
        app): antes da auditoria, pedir publico so trocaria o post por um erro."""
        opcoes = ["PUBLIC_TO_EVERYONE", "FOLLOWER_OF_CREATOR", "SELF_ONLY"]
        assert T.escolher_privacidade(pedida, opcoes) == "SELF_ONLY"

    def test_antes_da_auditoria_sem_o_privado_nao_inventa_outro(self):
        with pytest.raises(PublisherError, match="so aceita post privado"):
            T.escolher_privacidade("private", ["PUBLIC_TO_EVERYONE", "FOLLOWER_OF_CREATOR"])

    @pytest.mark.parametrize("auditado", [True, False])
    def test_sem_opcao_nenhuma(self, auditado):
        with pytest.raises(PublisherError):
            T.escolher_privacidade("private", [], auditado=auditado)

    def test_a_legenda_e_a_do_tiktok_com_as_hashtags_que_faltam(self):
        meta = PostMeta(title="A girafa", descriptions={"tiktok": "Olha isso #animais"},
                        hashtags=["animais", "#fyp"])
        assert T.legenda(meta) == "Olha isso #animais #fyp"

    def test_sem_descricao_vai_o_titulo_e_nunca_passa_do_limite(self):
        assert T.legenda(PostMeta(title="Só o título")) == "Só o título"
        longa = PostMeta(descriptions={"tiktok": "x" * 5000})
        assert len(T.legenda(longa)) == T.MAX_LEGENDA

    def test_o_corpo_respeita_o_que_o_criador_desligou(self):
        corpo = T.corpo_do_post(PostMeta(title="t"), "SELF_ONLY",
                                {"comment_disabled": True, "duet_disabled": False,
                                 "stitch_disabled": True}, 3 * MB)
        assert corpo["post_info"]["disable_comment"] is True
        assert corpo["post_info"]["disable_stitch"] is True
        assert corpo["post_info"]["disable_duet"] is False
        assert corpo["source_info"] == {"source": "FILE_UPLOAD", "video_size": 3 * MB,
                                        "chunk_size": 3 * MB, "total_chunk_count": 1}

    def test_a_conta_publica_antes_da_auditoria_diz_o_que_fazer(self):
        erro = T.erro_do_tiktok(403, {"error": {
            "code": "unaudited_client_can_only_post_to_private_accounts", "message": "x"}})
        assert "PRIVADA no app" in str(erro) and "pacote do dia" in str(erro)

    def test_erro_desconhecido_sai_cru(self):
        erro = T.erro_do_tiktok(400, {"error": {"code": "algo_novo", "message": "explicacao"}})
        assert "algo_novo" in str(erro) and "explicacao" in str(erro)

    def test_o_endereco_do_cofre(self):
        assert T.ref_de(conta()) == "vault://local/tiktok/@canalinfantil"
        assert T.ref_de(conta(credentials_ref="vault://local/tiktok/outra")) == \
            "vault://local/tiktok/outra"

    @pytest.mark.parametrize("ref", ["vault://env/tiktok/@canalinfantil",
                                     "vault://local/youtube/@canalinfantil", None])
    def test_a_credencial_do_tiktok_mora_so_no_cofre_local(self, ref):
        """O TikTok pode trocar o refresh token a cada renovacao, e o `env` nao
        e gravavel: la, a conexao morreria na primeira troca. A conta nasce
        apontando para o `env` (o padrao de toda conta), e o driver usa o
        endereco local, onde o "conectar" grava."""
        assert T.ref_de(conta(credentials_ref=ref)) == "vault://local/tiktok/@canalinfantil"

    def test_o_ambiente_nao_conecta_a_conta(self, monkeypatch):
        for campo, valor in (("CLIENT_KEY", "sbawabcdef123456"), ("CLIENT_SECRET", "s" * 20),
                             ("REFRESH_TOKEN", "R")):
            monkeypatch.setenv(f"TIKTOK_{campo}", valor)
        c = conta(credentials_ref="vault://env/tiktok/@canalinfantil")
        assert T.TikTokApiPublisher().disponivel(c) is False
        assert publishers.resolve("tiktok", c).id == "manual"
        assert T.ref_de(conta(credentials_ref=None, handle="@y")) == "vault://local/tiktok/@y"


# --------------------------------------------------------------------------- #
# O driver, com a rede imitada
# --------------------------------------------------------------------------- #

class Rede:
    """Responde como a documentacao do Direct Post diz."""

    def __init__(self, opcoes=("SELF_ONLY",), status=("PROCESSING_UPLOAD", "PUBLISH_COMPLETE"),
                 novo_refresh="R-1", maximo=600, ids=()):
        self.opcoes = list(opcoes)
        self.status = list(status)
        self.novo_refresh = novo_refresh
        self.maximo = maximo
        self.ids = list(ids)
        self.corpo_do_init = None
        self.pedacos = []

    def renovar(self, segredo):
        return {"access_token": "A", "refresh_token": self.novo_refresh}

    def pedir(self, url, *, token=None, json=None, data=None, timeout=60.0):
        assert token == "A"
        if url == T.CREATOR_INFO:
            return {"data": {"privacy_level_options": self.opcoes, "creator_username": "canalinfantil",
                             "max_video_post_duration_sec": self.maximo}}
        if url == T.INICIAR:
            self.corpo_do_init = json
            return {"data": {"publish_id": "PUB-1", "upload_url": "https://upload.tiktok/x"}}
        if url == T.STATUS:
            situacao = self.status.pop(0) if len(self.status) > 1 else self.status[0]
            dados = {"status": situacao}
            if situacao == "FAILED":
                dados["fail_reason"] = "video_too_short"
            if situacao == "PUBLISH_COMPLETE" and self.ids:
                dados["publicaly_available_post_id"] = self.ids
            return {"data": dados}
        raise AssertionError(url)

    def enviar(self, url, caminho, inicio, fim, total):
        self.pedacos.append((inicio, fim, total))


@pytest.fixture()
def rede(monkeypatch):
    r = Rede()
    monkeypatch.setattr(T, "renovar", r.renovar)
    monkeypatch.setattr(T, "_pedir", r.pedir)
    monkeypatch.setattr(T, "_enviar_pedaco", r.enviar)
    return r


class TestDriver:
    def test_sem_conectar_nao_atende(self):
        driver = T.TikTokApiPublisher()
        assert driver.disponivel(conta()) is False
        assert driver.capability(conta()) == "none"
        assert publishers.resolve("tiktok", conta()).id == "manual"

    def test_conectada_a_cascata_escolhe_a_api(self):
        _conectada()
        assert publishers.resolve("tiktok", conta()).id == "tiktok-api"
        assert T.TikTokApiPublisher().capability(conta()) == "private_only"

    def test_auditado_diz_publico(self, monkeypatch):
        _conectada()
        monkeypatch.setenv("TIKTOK_APP_AUDITADO", "1")
        assert T.TikTokApiPublisher().capability(conta()) == "public"

    def test_e_de_risco_zero(self):
        assert publishers.entra_na_cascata(T.TikTokApiPublisher())

    def test_nao_pega_conta_de_outra_plataforma(self):
        _conectada()
        assert T.TikTokApiPublisher().disponivel(conta(platform="youtube")) is False

    def test_publica_privado_de_ponta_a_ponta(self, ambiente, rede):
        _conectada()
        clip = _corte(ambiente)
        meta = PostMeta(title="A girafa", descriptions={"tiktok": "Olha #animais"})
        r = T.TikTokApiPublisher().publish(clip, meta, PublishOptions(visibility="public"), conta())
        assert r.ok and r.status == "published"
        assert "so para voce" in r.detail
        assert rede.corpo_do_init["post_info"]["privacy_level"] == "SELF_ONLY"
        assert rede.corpo_do_init["post_info"]["title"] == "Olha #animais"
        assert rede.pedacos == [(0, 2 * MB - 1, 2 * MB)]
        # Privado nao tem endereco publico.
        assert r.remote_id is None and r.url is None

    def test_publico_depois_da_auditoria_devolve_o_link(self, ambiente, monkeypatch):
        _conectada()
        monkeypatch.setenv("TIKTOK_APP_AUDITADO", "1")
        rede = Rede(opcoes=["PUBLIC_TO_EVERYONE", "SELF_ONLY"], ids=["7412345678901234567"])
        monkeypatch.setattr(T, "renovar", rede.renovar)
        monkeypatch.setattr(T, "_pedir", rede.pedir)
        monkeypatch.setattr(T, "_enviar_pedaco", rede.enviar)
        r = T.TikTokApiPublisher().publish(_corte(ambiente), PostMeta(title="t"),
                                           PublishOptions(visibility="public"), conta())
        assert r.remote_id == "7412345678901234567"
        assert r.url == "https://www.tiktok.com/@canalinfantil/video/7412345678901234567"

    def test_antes_da_auditoria_a_conta_que_aceita_publico_recebe_privado(self, ambiente, monkeypatch):
        _conectada()
        rede = Rede(opcoes=["PUBLIC_TO_EVERYONE", "SELF_ONLY"], ids=["7412345678901234567"])
        monkeypatch.setattr(T, "renovar", rede.renovar)
        monkeypatch.setattr(T, "_pedir", rede.pedir)
        monkeypatch.setattr(T, "_enviar_pedaco", rede.enviar)
        r = T.TikTokApiPublisher().publish(_corte(ambiente), PostMeta(title="t"),
                                           PublishOptions(visibility="public"), conta())
        assert rede.corpo_do_init["post_info"]["privacy_level"] == "SELF_ONLY"
        assert "so para voce" in r.detail

    def test_o_refresh_token_novo_e_guardado(self, ambiente, monkeypatch, rede):
        """O TikTok pode trocar o refresh token na renovacao: guardar o velho
        seria perder a conexao em silencio na proxima publicacao."""
        _conectada()
        rede.novo_refresh = "R-2"
        T.TikTokApiPublisher().publish(_corte(ambiente), PostMeta(title="t"), PublishOptions(), conta())
        segredo = vault.resolve("vault://local/tiktok/@canalinfantil")
        assert segredo["refresh_token"] == "R-2"
        assert segredo["client_key"] == "sbawabcdef123456"

    def test_corte_mais_longo_que_a_conta_aceita(self, ambiente, rede):
        _conectada()
        rede.maximo = 20
        with pytest.raises(PublisherError, match="aceita ate 20 s"):
            T.TikTokApiPublisher().publish(_corte(ambiente, duracao=30.0), PostMeta(title="t"),
                                           PublishOptions(), conta())
        assert rede.corpo_do_init is None

    def test_o_tiktok_falhando_no_processamento(self, ambiente, rede):
        _conectada()
        rede.status = ["FAILED"]
        with pytest.raises(PublisherError, match="video_too_short"):
            T.TikTokApiPublisher().publish(_corte(ambiente), PostMeta(title="t"), PublishOptions(), conta())

    def test_dry_run_nao_toca_a_rede(self, ambiente, monkeypatch):
        def explode(*a, **kw):
            raise AssertionError("foi a rede")
        monkeypatch.setattr(T, "renovar", explode)
        r = T.TikTokApiPublisher().publish(_corte(ambiente), PostMeta(title="t"),
                                           PublishOptions(dry_run=True), conta())
        assert r.ok and r.status == "scheduled"

    def test_arquivo_sumido(self, ambiente):
        r = T.TikTokApiPublisher().publish(
            RenderedClip(path=str(ambiente / "nada.mp4"), job_id="j", index=0),
            PostMeta(), PublishOptions(), conta())
        assert r.ok is False and r.status == "failed"
