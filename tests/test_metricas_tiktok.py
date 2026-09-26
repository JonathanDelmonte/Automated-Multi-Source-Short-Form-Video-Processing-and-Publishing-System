"""Medir o TikTok pela API de exibicao -- etapa 7.4.

A rede do TikTok nao e alcancavel daqui: `_consultar` e `tiktok_api.renovar`
sao trocados por imitacoes que respondem como a documentacao descreve
(`data.videos[]`, `error.code`). O que decide -- lotes, leitura da resposta,
frases de erro, o refresh token que muda -- roda de verdade.
"""
import pytest

import metricas_tiktok
import vault
from publishers import tiktok_api
from publishers.base import PublisherError

CREDENCIAL = {"client_key": "awABCdef12345678", "client_secret": "s",
              "refresh_token": "R-1"}


@pytest.fixture()
def cofre(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    return tmp_path


def _id(n: int) -> str:
    return str(7400000000000000000 + n)


class TestLotes:

    def test_vinte_por_consulta(self):
        """O limite da API: `video_ids` aceita ate 20."""
        grupos = metricas_tiktok.lotes([_id(i) for i in range(45)])
        assert [len(g) for g in grupos] == [20, 20, 5]

    def test_sem_repetir_e_so_id_de_video(self):
        """Um id torto derrubaria a consulta do lote inteiro."""
        grupos = metricas_tiktok.lotes([_id(1), _id(1), "abc", "", None, " " + _id(2) + " ", "123"])
        assert grupos == [[_id(1), _id(2)]]

    def test_nada_a_medir(self):
        assert metricas_tiktok.lotes([]) == []


class TestLeitura:

    def test_os_quatro_numeros(self):
        payload = {"data": {"videos": [
            {"id": _id(1), "view_count": 1200, "like_count": 88,
             "comment_count": 5, "share_count": 3},
        ]}, "error": {"code": "ok"}}
        assert metricas_tiktok.parse_videos(payload) == {
            _id(1): {"views": 1200, "likes": 88, "comments": 5, "shares": 3}}

    def test_campo_ausente_e_none_e_nao_zero(self):
        """Sem retencao e sem o que nao veio: None nao entra na media como
        "ninguem assistiu"."""
        payload = {"data": {"videos": [{"id": _id(2), "view_count": 10}]}}
        assert metricas_tiktok.parse_videos(payload)[_id(2)] == {
            "views": 10, "likes": None, "comments": None, "shares": None}

    @pytest.mark.parametrize("payload", [
        {}, None, {"data": None}, {"data": {"videos": "nao e lista"}},
        {"data": {"videos": [{"view_count": 1}]}},        # sem id
    ])
    def test_resposta_estranha_nao_mede_nada(self, payload):
        assert metricas_tiktok.parse_videos(payload) == {}

    def test_numero_negativo_ou_torto_vira_none(self):
        payload = {"data": {"videos": [{"id": _id(3), "view_count": -1,
                                        "like_count": "muitos", "share_count": True}]}}
        numeros = metricas_tiktok.parse_videos(payload)[_id(3)]
        assert numeros["views"] is None and numeros["likes"] is None
        assert numeros["shares"] is None

    def test_o_id_volta_como_texto(self):
        """A resposta pode trazer o id como numero; a publicacao guarda texto."""
        payload = {"data": {"videos": [{"id": 7400000000000000001, "view_count": 1}]}}
        assert list(metricas_tiktok.parse_videos(payload)) == ["7400000000000000001"]


class TestFrases:

    def test_sem_permissao_de_ver_os_videos(self):
        """A frase do driver fala em POSTAR; aqui a conexao e a de medir."""
        erro = metricas_tiktok.erro_da_consulta(
            401, {"error": {"code": "scope_not_authorized", "message": "x"}})
        assert "video.list" in str(erro) and "postar" not in str(erro)

    def test_conexao_vencida(self):
        erro = metricas_tiktok.erro_da_consulta(401, {"error": {"code": "access_token_invalid"}})
        assert "conecte para medir" in str(erro).lower()

    def test_erro_desconhecido_cai_na_frase_do_driver(self):
        erro = metricas_tiktok.erro_da_consulta(500, {"error": {"code": "internal_error",
                                                                "message": "falhou"}})
        assert "internal_error" in str(erro)


class TestMedir:

    def _imitar(self, monkeypatch, respostas=None, novo_refresh=None):
        chamadas = []

        def _renovar(segredo):
            chamadas.append(("renovar", segredo["refresh_token"]))
            dados = {"access_token": "A-1"}
            if novo_refresh:
                dados["refresh_token"] = novo_refresh
            return dados

        def _consultar(token, ids):
            chamadas.append(("consultar", token, list(ids)))
            videos = [{"id": i, "view_count": 100 + n, "like_count": n}
                      for n, i in enumerate(ids) if i in (respostas or ids)]
            return {"data": {"videos": videos}, "error": {"code": "ok"}}

        monkeypatch.setattr(tiktok_api, "renovar", _renovar)
        monkeypatch.setattr(metricas_tiktok, "_consultar", _consultar)
        return chamadas

    def test_sem_a_conexao_de_medir(self, cofre):
        """A de POSTAR nao serve: outra credencial, de proposito."""
        vault.gravar("vault://local/tiktok/@canal", CREDENCIAL)
        with pytest.raises(PublisherError) as e:
            metricas_tiktok.medir("@canal", [_id(1)])
        assert "conectar para medir" in str(e.value)

    def test_um_token_para_a_conta_inteira(self, cofre, monkeypatch):
        vault.gravar(metricas_tiktok.ref_de("@canal"), CREDENCIAL)
        chamadas = self._imitar(monkeypatch)
        numeros = metricas_tiktok.medir("@canal", [_id(i) for i in range(25)])
        assert len(numeros) == 25
        assert [c[0] for c in chamadas] == ["renovar", "consultar", "consultar"]
        assert numeros[_id(0)] == {"views": 100, "likes": 0, "comments": None, "shares": None}

    def test_video_que_nao_veio_fica_sem_numero(self, cofre, monkeypatch):
        """Um id de outra conta (ou um post privado) volta vazio: fica de fora,
        e nao vira zero."""
        vault.gravar(metricas_tiktok.ref_de("@canal"), CREDENCIAL)
        self._imitar(monkeypatch, respostas=[_id(1)])
        assert set(metricas_tiktok.medir("@canal", [_id(1), _id(2)])) == {_id(1)}

    def test_o_refresh_token_novo_e_gravado(self, cofre, monkeypatch):
        """O TikTok pode trocar o refresh token a cada renovacao, e o velho
        deixa de valer: perder o novo seria perder a conexao em silencio."""
        vault.gravar(metricas_tiktok.ref_de("@canal"), CREDENCIAL)
        self._imitar(monkeypatch, novo_refresh="R-2")
        metricas_tiktok.medir("@canal", [_id(1)])
        guardado = metricas_tiktok.credencial("@canal")
        assert guardado["refresh_token"] == "R-2"
        assert guardado["client_key"] == CREDENCIAL["client_key"]

    def test_renovacao_recusada_manda_conectar_de_novo(self, cofre, monkeypatch):
        vault.gravar(metricas_tiktok.ref_de("@canal"), CREDENCIAL)

        def _recusa(segredo):
            raise PublisherError("o TikTok respondeu 400: invalid_grant")
        monkeypatch.setattr(tiktok_api, "renovar", _recusa)
        with pytest.raises(PublisherError) as e:
            metricas_tiktok.medir("@canal", [_id(1)])
        assert "conecte para medir" in str(e.value).lower()

    def test_sem_id_valido_nem_pergunta(self, cofre, monkeypatch):
        """O link curto que nao deu para seguir nao tem id: nao gasta pedido."""
        chamadas = self._imitar(monkeypatch)
        assert metricas_tiktok.medir("@canal", ["curto", None]) == {}
        assert chamadas == []

    def test_a_consulta_pede_os_campos_certos(self):
        """`id` volta para casar a resposta com a publicacao."""
        assert metricas_tiktok.CAMPOS_DO_VIDEO[0] == "id"
        assert set(metricas_tiktok.CAMPOS_DO_VIDEO) == {
            "id", "view_count", "like_count", "comment_count", "share_count"}
