"""Coletor de `metrics` -- Fase 5.

A secao 7 chama `metrics` de "a tabela mais valiosa do projeto": e ela que
permite trocar a rubrica do LLM por retencao medida. Estava vazia desde a Fase
0.5 porque nada a escrevia.

Dois contratos que estes testes guardam:

**`metrics` e serie temporal, nao cache.** Cada coleta acrescenta linha. A
secao 7 poe `collected_at` na tabela e nao poe unicidade por publicacao
exatamente por isso -- retencao matura em dias, e sobrescrever jogaria fora a
unica dimensao que torna a tabela util.

**None nao e zero.** "Nao consegui perguntar" e "ninguem assistiu" sao coisas
diferentes, e confundi-las polui a media que a Fase 5 existe para calcular.
"""
import asyncio
import json
import os
import uuid
from datetime import date

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
metrics_collector = pytest.importorskip("metrics_collector")
metricas_tiktok = pytest.importorskip("metricas_tiktok")
metricas_instagram = pytest.importorskip("metricas_instagram")
publish_queue = pytest.importorskip("publish_queue")

import publishers
import vault


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "_avisou_sem_credencial", set())
    for nome in list(os.environ):
        if nome.startswith("YOUTUBE_"):
            monkeypatch.delenv(nome, raising=False)
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo)
    return asyncio.run(_do())


# --------------------------------------------------------------------------- #
# O escopo separado
# --------------------------------------------------------------------------- #

class TestEscopoDeLeitura:

    def test_os_escopos_de_leitura_nao_publicam_nem_apagam(self):
        """Duas credenciais pequenas em vez de uma grande: a que publica nao
        le, a que le nao publica, e nenhuma das duas apaga."""
        for escopo in metrics_collector.ESCOPOS_DE_LEITURA:
            assert escopo.endswith("readonly"), escopo

    def test_o_token_de_upload_continua_minimo(self):
        """A Fase 5 precisar de leitura NAO pode ter virado motivo para ampliar
        o token de publicacao -- era a decisao explicita do bloco 3.4."""
        import youtube_oauth
        assert youtube_oauth.ESCOPO == \
            "https://www.googleapis.com/auth/youtube.upload"

    def test_a_credencial_de_leitura_mora_noutro_endereco(self):
        """Confundi-la com a de publicacao seria o jeito mais facil de acabar
        com um token so, grande."""
        leitura = metrics_collector.ref_de_leitura("canal")
        assert "youtube-metrics" in leitura
        assert leitura != "vault://local/youtube/canal"

    def test_sem_credencial_o_coletor_diz_o_que_fazer(self, ambiente):
        """Desde a 7.3b o consentimento de leitura e um botao da conta; o
        `youtube_oauth.py --leitura` continua existindo, mas nao e mais o que
        se manda fazer."""
        with pytest.raises(publishers.PublisherError) as e:
            metrics_collector.medir("VIDEOID", "canal")
        assert "conectar para medir" in str(e.value)

    def test_o_token_de_publicacao_nao_serve_de_credencial_de_leitura(self, ambiente):
        """Tem de ser recusado mesmo existindo: o escopo dele nao le nada."""
        vault.gravar("vault://local/youtube/canal",
                     {"client_id": "i", "client_secret": "s",
                      "refresh_token": "r"})
        assert metrics_collector.credencial_de_leitura("canal") is None

    def test_com_a_credencial_de_leitura_ele_acha(self, ambiente):
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s",
                      "refresh_token": "r"})
        assert metrics_collector.credencial_de_leitura("canal")["client_id"] == "i"


# --------------------------------------------------------------------------- #
# Interpretacao das respostas
# --------------------------------------------------------------------------- #

class TestParse:

    def test_views(self):
        assert metrics_collector.parse_views(
            {"items": [{"statistics": {"viewCount": "1234"}}]}) == 1234

    @pytest.mark.parametrize("payload", [
        {}, {"items": []}, {"items": [{}]},
        {"items": [{"statistics": {}}]},
        {"items": [{"statistics": {"viewCount": "muitas"}}]},
        {"items": "nao e lista"},
    ])
    def test_views_ausente_e_none_e_nao_zero(self, payload):
        """Zero e um numero que a Fase 5 vai cruzar com a rubrica. "Nao medido"
        nao pode entrar na media como "ninguem assistiu"."""
        assert metrics_collector.parse_views(payload) is None

    def test_retencao_le_pelo_NOME_da_coluna(self):
        """A API devolve `columnHeaders` junto das linhas porque a ordem muda
        com a lista de metricas pedida. Ler pela posicao nao daria erro -- so
        gravaria o numero de views no campo de retencao."""
        payload = {"columnHeaders": [{"name": "views"},
                                     {"name": "averageViewPercentage"}],
                   "rows": [[999, 62.317]]}
        assert metrics_collector.parse_retencao(payload) == 62.32

    def test_retencao_com_a_ordem_invertida(self):
        payload = {"columnHeaders": [{"name": "averageViewPercentage"},
                                     {"name": "views"}],
                   "rows": [[62.317, 999]]}
        assert metrics_collector.parse_retencao(payload) == 62.32

    @pytest.mark.parametrize("payload", [
        {}, {"rows": []}, {"columnHeaders": [{"name": "views"}], "rows": [[1]]},
        {"columnHeaders": [{"name": "averageViewPercentage"}], "rows": [[]]},
        {"columnHeaders": None, "rows": None},
    ])
    def test_retencao_ausente_e_none(self, payload):
        assert metrics_collector.parse_retencao(payload) is None

    @pytest.mark.parametrize("bruto,esperado", [(-5, 0.0), (150.0, 100.0)])
    def test_retencao_fora_da_faixa_e_presa(self, bruto, esperado):
        """O CHECK da coluna recusa fora de 0..100, e um valor estranho da API
        derrubaria a gravacao das OUTRAS publicacoes da rodada."""
        payload = {"columnHeaders": [{"name": "averageViewPercentage"}],
                   "rows": [[bruto]]}
        assert metrics_collector.parse_retencao(payload) == esperado

    def test_estatisticas_trazem_curtidas_e_comentarios(self):
        """Do mesmo `statistics` de onde sempre saiu o `viewCount`: pedir as
        curtidas nao custa uma unidade a mais."""
        payload = {"items": [{"statistics": {"viewCount": "1234", "likeCount": "56",
                                             "commentCount": "7", "favoriteCount": "0"}}]}
        assert metrics_collector.parse_estatisticas(payload) == {
            "views": 1234, "likes": 56, "comments": 7}

    def test_curtidas_escondidas_sao_none(self):
        """O dono pode esconder as curtidas; "escondido" nao e "zero"."""
        payload = {"items": [{"statistics": {"viewCount": "10"}}]}
        assert metrics_collector.parse_estatisticas(payload) == {
            "views": 10, "likes": None, "comments": None}

    def test_o_relatorio_le_cada_numero_pelo_nome(self):
        payload = {"columnHeaders": [{"name": "shares"}, {"name": "averageViewDuration"},
                                     {"name": "averageViewPercentage"}],
                   "rows": [[4, 17.8, 61.2]]}
        assert metrics_collector.parse_relatorio(payload) == {
            "retention_pct": 61.2, "avg_watch_s": 17.8, "shares": 4}

    def test_o_relatorio_so_com_a_retencao(self):
        """O relatorio de antes (so a retencao) continua lido."""
        payload = {"columnHeaders": [{"name": "averageViewPercentage"}], "rows": [[40]]}
        assert metrics_collector.parse_relatorio(payload) == {
            "retention_pct": 40.0, "avg_watch_s": None, "shares": None}

    def test_relatorio_recusado_volta_a_pedir_so_a_retencao(self, monkeypatch):
        """Um numero a mais nunca pode custar o que ja era medido."""
        pedidos = []

        class R:
            def __init__(self, status, corpo):
                self.status_code, self._corpo, self.text = status, corpo, ""

            def json(self):
                return self._corpo

        def _pedir(token, video_id, metricas):
            pedidos.append(metricas)
            if "," in metricas:
                return R(400, {})
            return R(200, {"columnHeaders": [{"name": "averageViewPercentage"}],
                           "rows": [[33.3]]})
        monkeypatch.setattr(metrics_collector, "_pedir_relatorio", _pedir)
        assert metrics_collector._buscar_relatorio("T", "V")["retention_pct"] == 33.3
        assert pedidos == ["averageViewPercentage,averageViewDuration,shares",
                           "averageViewPercentage"]

    def test_o_token_de_leitura_vale_para_a_rodada(self, monkeypatch):
        """Uma rodada mede um video por vez; sem guardar o token, cada video
        pediria um novo ao Google."""
        metrics_collector._TOKENS.clear()
        pedidos = []

        class R:
            status_code = 200

            def json(self):
                return {"access_token": "AT", "expires_in": 3599}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: pedidos.append(1) or R())
        segredo = {"client_id": "i", "client_secret": "s", "refresh_token": "r"}
        assert metrics_collector._token_de_leitura(segredo) == "AT"
        assert metrics_collector._token_de_leitura(segredo) == "AT"
        assert len(pedidos) == 1
        metrics_collector._TOKENS.clear()

    def test_a_janela_olha_para_tras(self):
        inicio, fim = metrics_collector.janela(date(2026, 9, 16))
        assert fim == "2026-09-16"
        assert inicio == "2026-06-18"


# --------------------------------------------------------------------------- #
# A tabela
# --------------------------------------------------------------------------- #

def _publicacao(ambiente, status="published", remote_id="VIDEO1",
                driver="youtube-api"):
    """Uma publicacao completa: job, corte, conta e a linha."""
    job_id = str(uuid.uuid4())
    pasta = ambiente / job_id
    pasta.mkdir()
    shorts = [{"start": 0.0, "end": 30.0, "predicted_score": 80,
               "video_title_for_youtube_short": "Corte 1",
               "video_description_for_tiktok": "d"}]
    (pasta / "v_clip_1.mp4").write_bytes(b"\x00" * 32)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
        async with db.tenant() as t:
            # Uma conta so, reaproveitada: `accounts` tem unicidade por
            # (tenant, plataforma, handle), e o caso real e um canal com varias
            # publicacoes -- nao um canal por publicacao.
            existentes = await t.all(db_models.Account,
                                     db_models.Account.handle == "canal")
            conta = existentes[0] if existentes else t.add(
                db_models.Account(platform="youtube", handle="canal"))
            await t.flush()
            corte = [c for c in await t.all(db_models.Clip)
                     if c.job_id == job_id][0]
            pub = t.add(db_models.Publication(
                clip_id=corte.id, account_id=conta.id, driver=driver,
                status=status, remote_id=remote_id))
            await t.commit()
            return pub.id
    return corre(_t)


class TestTabela:

    def test_cada_coleta_acrescenta_linha(self, ambiente):
        """Serie temporal, nao cache: retencao matura em dias, e o valor de
        24 h depois e outra informacao."""
        pub_id = _publicacao(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=10,
                                                   retention_pct=40.0))
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=95,
                                                   retention_pct=52.5))
        leituras = corre(lambda: publish_queue.historico(pub_id))
        assert len(leituras) == 2
        assert sorted(m["views"] for m in leituras) == [10, 95]

    def test_leitura_sem_numero_nenhum_nao_vira_linha(self, ambiente):
        """Ela nao diz nada e sujaria a media com uma amostra vazia."""
        pub_id = _publicacao(ambiente)
        assert corre(lambda: publish_queue.gravar_metrica(pub_id)) is None
        assert corre(lambda: publish_queue.historico(pub_id)) == []

    def test_so_views_ja_vale_linha(self, ambiente):
        """Retencao exige o escopo de Analytics; views nao. Perder a linha
        inteira por falta da metade cara seria jogar fora o que deu para medir."""
        pub_id = _publicacao(ambiente)
        assert corre(lambda: publish_queue.gravar_metrica(pub_id, views=7))
        leitura = corre(lambda: publish_queue.historico(pub_id))[0]
        assert leitura["views"] == 7 and leitura["retention_pct"] is None

    def test_os_detalhes_vao_na_mesma_leitura(self, ambiente):
        """Curtidas, comentarios, compartilhamentos, salvamentos e tempo medio
        moram em `metric_details`, 1:1 com a leitura (7.4)."""
        pub_id = _publicacao(ambiente)
        corre(lambda: publish_queue.gravar_metrica(
            pub_id, views=100, retention_pct=None, likes=9, comments=2, shares=1,
            saves=3, avg_watch_s=12.5))
        leitura = corre(lambda: publish_queue.historico(pub_id))[0]
        assert (leitura["views"], leitura["likes"], leitura["comments"], leitura["shares"],
                leitura["saves"], leitura["avg_watch_s"]) == (100, 9, 2, 1, 3, 12.5)

        async def _contar():
            async with db.tenant() as t:
                return len(await t.all(db_models.MetricDetail))
        assert corre(_contar) == 1

    def test_so_curtidas_ja_vale_linha(self, ambiente):
        """Post do Instagram sem insights: a lista da curtidas e comentarios, e
        isso ja e uma leitura."""
        pub_id = _publicacao(ambiente)
        assert corre(lambda: publish_queue.gravar_metrica(pub_id, likes=4))
        leitura = corre(lambda: publish_queue.historico(pub_id))[0]
        assert leitura["views"] is None and leitura["likes"] == 4

    def test_sem_detalhe_nao_ha_linha_de_detalhe(self, ambiente):
        pub_id = _publicacao(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=5, likes=None))

        async def _contar():
            async with db.tenant() as t:
                return len(await t.all(db_models.MetricDetail))
        assert corre(_contar) == 0

    def test_numero_negativo_vira_none_e_nao_derruba(self, ambiente):
        """O CHECK recusaria, e a resposta estranha de uma plataforma
        derrubaria a gravacao."""
        pub_id = _publicacao(ambiente)
        assert corre(lambda: publish_queue.gravar_metrica(pub_id, views=-3, likes=-1,
                                                          retention_pct=180.0))
        leitura = corre(lambda: publish_queue.historico(pub_id))[0]
        assert leitura["views"] is None and leitura["likes"] is None
        assert leitura["retention_pct"] == 100.0

    def test_detalhe_desconhecido_levanta(self, ambiente):
        """Um numero que o coletor mede e ninguem guarda e um bug."""
        pub_id = _publicacao(ambiente)
        with pytest.raises(TypeError):
            corre(lambda: publish_queue.gravar_metrica(pub_id, views=1, dislikes=2))

    def test_apagar_a_leitura_leva_o_detalhe(self, ambiente):
        pub_id = _publicacao(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=1, likes=1))

        async def _apagar_e_contar():
            async with db.tenant() as t:
                for m in await t.all(db_models.Metric):
                    await t.session.delete(m)
                await t.commit()
            async with db.tenant() as t:
                return len(await t.all(db_models.MetricDetail))
        assert corre(_apagar_e_contar) == 0

    def test_a_lista_traz_o_arroba_e_a_duracao(self, ambiente):
        """O `@` diz qual credencial usar; a duracao faz do tempo medio do
        Instagram uma retencao."""
        _publicacao(ambiente)
        pub = corre(publish_queue.publicadas_com_remote_id)[0]
        assert pub["handle"] == "canal" and pub["duracao_s"] == 30.0

    def test_so_as_publicadas_com_remote_id_sao_medidas(self, ambiente):
        """Uma linha na fila manual nao tem video do outro lado. Medi-la
        registraria zero views como se fosse resultado."""
        _publicacao(ambiente, status="scheduled", remote_id=None, driver="manual")
        assert corre(publish_queue.publicadas_com_remote_id) == []
        _publicacao(ambiente, status="published", remote_id="V2")
        assert len(corre(publish_queue.publicadas_com_remote_id)) == 1

    def test_publicada_sem_remote_id_nao_entra(self, ambiente):
        _publicacao(ambiente, status="published", remote_id=None)
        assert corre(publish_queue.publicadas_com_remote_id) == []

    def test_a_lista_traz_o_tenant_junto(self, ambiente):
        """O coletor atravessa tenants e precisa devolver cada linha ao dela
        antes de gravar."""
        _publicacao(ambiente)
        assert corre(publish_queue.publicadas_com_remote_id)[0]["tenant_id"] == \
            db.SELF_HOST_TENANT_ID


class TestLaco:

    def test_sem_credencial_nao_derruba_nada(self, ambiente, capsys):
        _publicacao(ambiente)
        r = corre(app_module.coletar_metricas)
        assert r["medidas"] == 0
        assert r.get("sem_credencial") == ["youtube/canal"]
        assert "conectar para medir" in capsys.readouterr().out

    def test_avisa_uma_vez_so(self, ambiente, capsys):
        """A cada seis horas o laco roda de novo; repetir o aviso encheria o
        log de quem escolheu nao coletar."""
        _publicacao(ambiente)
        corre(app_module.coletar_metricas)
        capsys.readouterr()
        corre(app_module.coletar_metricas)
        assert "conectar para medir" not in capsys.readouterr().out

    def test_mede_e_grava(self, ambiente, monkeypatch):
        pub_id = _publicacao(ambiente)
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s",
                      "refresh_token": "r"})
        monkeypatch.setattr(metrics_collector, "medir",
                            lambda vid, handle: {"views": 42,
                                                 "retention_pct": 61.5})
        assert corre(app_module.coletar_metricas)["medidas"] == 1
        leitura = corre(lambda: publish_queue.historico(pub_id))[0]
        assert (leitura["views"], leitura["retention_pct"]) == (42, 61.5)

    def test_um_video_que_falha_nao_derruba_os_outros(self, ambiente, monkeypatch):
        _publicacao(ambiente, remote_id="BOM1")
        _publicacao(ambiente, remote_id="RUIM")
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s",
                      "refresh_token": "r"})

        def _medir(vid, handle):
            if vid == "RUIM":
                raise publishers.PublisherError("videos.list respondeu 404")
            return {"views": 5, "retention_pct": None}

        monkeypatch.setattr(metrics_collector, "medir", _medir)
        r = corre(app_module.coletar_metricas)
        assert r["medidas"] == 1 and r["erros"] == 1

    def test_o_post_feito_a_mao_no_youtube_e_medido(self, ambiente, monkeypatch):
        """Etapa 7.3: o "ja publiquei" guarda o link, e dele sai o id do video.
        Quem diz de onde medir e a PLATAFORMA da conta, nao o driver -- o
        video postado a mao e um video do canal como qualquer outro."""
        _publicacao(ambiente, driver="manual", remote_id="COLADO")
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s",
                      "refresh_token": "r"})
        chamou = []
        monkeypatch.setattr(metrics_collector, "medir",
                            lambda *a: chamou.append(a) or {"views": 1})
        assert corre(app_module.coletar_metricas)["medidas"] == 1
        assert chamou == [("COLADO", "canal")]

    def test_conta_do_tiktok_sem_a_conexao_de_medir_e_pulada(self, ambiente, monkeypatch):
        """Desde a 7.4 o TikTok tem de onde medir -- mas so com a conexao de
        MEDIR, que e outra credencial: a de postar nao le."""
        pub_id = _publicacao(ambiente, driver="manual", remote_id="7412345678901234567")

        async def _para_o_tiktok():
            async with db.tenant() as t:
                pub = await t.get(db_models.Publication, pub_id)
                conta = t.add(db_models.Account(platform="tiktok", handle="canal"))
                await t.flush()
                pub.account_id = conta.id
                await t.commit()
        corre(_para_o_tiktok)
        # A de POSTAR existe; a de medir, nao.
        vault.gravar("vault://local/tiktok/canal",
                     {"client_key": "k", "client_secret": "s", "refresh_token": "r"})
        chamou = []
        monkeypatch.setattr(metricas_tiktok, "medir",
                            lambda *a: chamou.append(a) or {})
        r = corre(app_module.coletar_metricas)
        assert r["medidas"] == 0 and chamou == []
        assert r["sem_credencial"] == ["tiktok/canal"]

    def _mover_para(self, pub_id, plataforma, handle="canal"):
        async def _mover():
            async with db.tenant() as t:
                pub = await t.get(db_models.Publication, pub_id)
                existentes = await t.all(db_models.Account,
                                         db_models.Account.platform == plataforma)
                conta = existentes[0] if existentes else t.add(
                    db_models.Account(platform=plataforma, handle=handle))
                await t.flush()
                pub.account_id = conta.id
                await t.commit()
        corre(_mover)

    def test_as_tres_plataformas_numa_rodada(self, ambiente, monkeypatch):
        """Cada conta mede pela sua API, com os seus numeros; o TikTok nao tem
        retencao, e o Instagram a tem pela duracao do corte."""
        yt = _publicacao(ambiente, remote_id="YTVIDEO0001")
        tt = _publicacao(ambiente, driver="manual", remote_id="7412345678901234567")
        ig = _publicacao(ambiente, driver="manual", remote_id="DAbc123xy")
        self._mover_para(tt, "tiktok")
        self._mover_para(ig, "instagram")
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s", "refresh_token": "r"})
        vault.gravar(metricas_tiktok.ref_de("canal"),
                     {"client_key": "k", "client_secret": "s", "refresh_token": "r"})
        vault.gravar(metricas_instagram.ref_de("canal"),
                     {"access_token": "IG" + "x" * 40, "user_id": "1"})
        monkeypatch.setattr(metrics_collector, "medir", lambda vid, h: {
            "views": 500, "retention_pct": 48.0, "likes": 20, "comments": 2,
            "shares": 1, "avg_watch_s": 14.4})
        monkeypatch.setattr(metricas_tiktok, "medir", lambda h, ids: {
            i: {"views": 900, "likes": 70, "comments": 4, "shares": 6} for i in ids})
        pedidos_ig = []
        monkeypatch.setattr(metricas_instagram, "medir", lambda h, pedidos: pedidos_ig.extend(pedidos) or {
            p["id"]: metricas_instagram.numeros(
                {"like_count": 30, "comments_count": 3},
                {"views": 700, "saved": 5, "shares": 2, "ig_reels_avg_watch_time": 15000},
                p["duracao_s"]) for p in pedidos})
        r = corre(app_module.coletar_metricas)
        assert r == {"medidas": 3, "erros": 0}
        assert pedidos_ig == [{"id": "DAbc123xy", "duracao_s": 30.0}]
        por_pub = {m["publication_id"]: m for m in corre(lambda: publish_queue.historico())}
        assert (por_pub[yt]["views"], por_pub[yt]["retention_pct"], por_pub[yt]["likes"]) == (500, 48.0, 20)
        assert (por_pub[tt]["views"], por_pub[tt]["shares"], por_pub[tt]["retention_pct"]) == (900, 6, None)
        assert (por_pub[ig]["views"], por_pub[ig]["saves"], por_pub[ig]["retention_pct"]) == (700, 5, 50.0)

    def test_conta_sem_conexao_nao_para_as_outras(self, ambiente, monkeypatch):
        """Ate a 7.4 a primeira conta sem credencial encerrava a rodada."""
        sem = _publicacao(ambiente, remote_id="YTVIDEO0001")
        com = _publicacao(ambiente, driver="manual", remote_id="7412345678901234567")
        self._mover_para(com, "tiktok")
        vault.gravar(metricas_tiktok.ref_de("canal"),
                     {"client_key": "k", "client_secret": "s", "refresh_token": "r"})
        monkeypatch.setattr(metricas_tiktok, "medir", lambda h, ids: {i: {"views": 1} for i in ids})
        r = corre(app_module.coletar_metricas)
        assert r["medidas"] == 1 and r["sem_credencial"] == ["youtube/canal"]
        assert corre(lambda: publish_queue.historico(sem)) == []

    def test_erro_da_conta_conta_uma_vez(self, ambiente, monkeypatch):
        """TikTok e Instagram medem a conta de uma vez: a recusa e da conta."""
        for vid in ("7412345678901234567", "7412345678901234568"):
            self._mover_para(_publicacao(ambiente, driver="manual", remote_id=vid), "tiktok")
        vault.gravar(metricas_tiktok.ref_de("canal"),
                     {"client_key": "k", "client_secret": "s", "refresh_token": "r"})

        def _recusa(h, ids):
            raise publishers.PublisherError("A conexao de medir do TikTok venceu.")
        monkeypatch.setattr(metricas_tiktok, "medir", _recusa)
        assert corre(app_module.coletar_metricas) == {"medidas": 0, "erros": 1}

    def test_o_token_vencido_do_instagram_pede_outro(self, ambiente, capsys):
        ig = _publicacao(ambiente, driver="manual", remote_id="DAbc123xy")
        self._mover_para(ig, "instagram")
        vault.gravar(metricas_instagram.ref_de("canal"),
                     {"access_token": "IG" + "x" * 40, "user_id": "1", "vencido": "1"})
        r = corre(app_module.coletar_metricas)
        assert r["sem_credencial"] == ["instagram/canal"]
        assert "venceu" in capsys.readouterr().out

    def test_o_endpoint_diz_se_alguma_conta_mede(self, ambiente):
        _publicacao(ambiente)
        assert _chama("GET", "/api/metricas").json()["tem_credencial_de_leitura"] is False
        vault.gravar(metrics_collector.ref_de_leitura("canal"),
                     {"client_id": "i", "client_secret": "s", "refresh_token": "r"})
        assert _chama("GET", "/api/metricas").json()["tem_credencial_de_leitura"] is True

    def test_o_endpoint_forca_uma_rodada(self, ambiente):
        """Descobrir se a credencial esta certa nao pode custar seis horas."""
        _publicacao(ambiente)
        r = _chama("POST", "/api/metricas/coletar")
        assert r.status_code == 200
        assert r.json()["medidas"] == 0

    def test_o_endpoint_lista_o_historico(self, ambiente):
        pub_id = _publicacao(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=3))
        corpo = _chama("GET", "/api/metricas").json()
        assert len(corpo["metricas"]) == 1
        assert corpo["tem_credencial_de_leitura"] is False


class TestQuota:

    def test_o_list_debita_das_unidades(self):
        """Uma unidade das 10.000 do dia, que desde jun-2026 sao so das
        chamadas que nao sao envio. Barato, mas debitado: um contador que
        ignora o barato deixa de ser o contador."""
        assert metrics_collector.CUSTO_LIST == 1

    def test_medir_nao_conta_como_upload(self, tmp_path, monkeypatch):
        """Debitar a unidade e certo; contar como envio faria o painel dizer
        que restam 99 envios quando restam 100."""
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        from publishers import quota
        antes = quota.estado()["uploads_hoje"]
        quota.registrar_unidades(metrics_collector.CUSTO_LIST)
        estado = quota.estado()
        assert estado["uploads_hoje"] == antes
        assert estado["usadas"] == 1

    def test_o_coletor_debita_pelas_unidades(self):
        fonte = open(metrics_collector.__file__, encoding="utf-8").read()
        assert "quota.registrar_unidades(CUSTO_LIST)" in fonte
