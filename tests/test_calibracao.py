"""Cruzar a rubrica com o resultado -- Fase 5, bloco 5.2.

O proposito declarado da fase: "cruzar a rubrica que o LLM deu, ajustar os
pesos". As duas pontas ja existiam -- `clips.score` desde o bloco 3.3, `metrics`
desde o 5.1.

**O teste que mais importa aqui e `test_abaixo_do_minimo_nao_ha_coeficiente`.**
Com poucos cortes, um rho alto acontece por acaso com frequencia alta -- e uma
vez escrito num relatorio, vira a razao de alguem mexer nos pesos. E exatamente
o movimento que o ADR-006 recusou (nao virar um numero nao sabido em
constante), o pre-filtro recusou (cortar por orcamento e nao por qualidade) e o
`layout_picker` recusou (decisao entre opcoes fechadas, nao medida continua).
"""
import asyncio
import json
import random
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
calibracao = pytest.importorskip("calibracao")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")


def corre(coro_fn):
    return asyncio.run(coro_fn())


def _itens(n, acerta=True, semente=7):
    """`n` cortes. Com `acerta`, a retencao segue o score; sem, e aleatoria."""
    rng = random.Random(semente)
    scores = sorted((rng.uniform(40, 99) for _ in range(n)), reverse=True)
    return [{"score": round(s, 1),
             "retention_pct": round(s * 0.6 if acerta else rng.uniform(10, 70), 1),
             "views": int(s * 10)}
            for s in scores]


# --------------------------------------------------------------------------- #
# A regra que este modulo existe para respeitar
# --------------------------------------------------------------------------- #

class TestAmostra:

    @pytest.mark.parametrize("n", [0, 1, 3, 5, 9])
    def test_abaixo_do_minimo_nao_ha_coeficiente(self, n):
        """Um rho de 0,9 com n=5 acontece por acaso. Uma vez escrito, vira a
        razao de alguem mexer nos pesos."""
        r = calibracao.relatorio(_itens(n))
        assert r["rho_score_retencao"] is None

    def test_no_minimo_ja_ha(self):
        r = calibracao.relatorio(_itens(calibracao.MINIMO_PARA_CORRELACAO))
        assert r["rho_score_retencao"] is not None

    def test_abaixo_do_minimo_diz_quantos_faltam(self):
        r = calibracao.relatorio(_itens(4))
        assert any("Faltam 6" in o for o in r["observacoes"])

    def test_os_dados_crus_saem_de_qualquer_jeito(self):
        """Nao publicar coeficiente nao e nao mostrar nada: olhar e honesto."""
        r = calibracao.relatorio(_itens(4))
        assert r["clipes_medidos"] == 4
        assert sum(f["clipes"] for f in r["por_faixa"]) == 4

    def test_amostra_apertada_ganha_ressalva(self):
        r = calibracao.relatorio(_itens(12))
        assert any("apertada para decidir" in o for o in r["observacoes"])

    def test_amostra_confortavel_nao_ganha(self):
        r = calibracao.relatorio(_itens(40))
        assert not any("apertada para decidir" in o for o in r["observacoes"])

    def test_sem_nada_medido_diz_o_que_falta(self):
        r = calibracao.relatorio([])
        assert any("--leitura" in o for o in r["observacoes"])


# --------------------------------------------------------------------------- #
# A conta
# --------------------------------------------------------------------------- #

class TestSpearman:

    def test_ordem_perfeita_da_1(self):
        pares = [(i, i * 2) for i in range(12)]
        assert calibracao.spearman(pares) == 1.0

    def test_ordem_invertida_da_menos_1(self):
        pares = [(i, -i) for i in range(12)]
        assert calibracao.spearman(pares) == -1.0

    def test_mede_ORDEM_e_nao_reta(self):
        """A pergunta da fase e "o corte que o modelo achou melhor rendeu
        mais?". Um modelo que acerta o ranking inteiro mas comprime os scores
        entre 70 e 85 tem Pearson baixo e e exatamente o que queremos."""
        pares = [(i, i ** 3) for i in range(12)]
        assert calibracao.spearman(pares) == 1.0

    def test_empate_nao_vira_ordem_de_insercao(self):
        """Sem media nos empates, tres cortes com score 80 receberiam postos
        1, 2 e 3 numa ordem arbitraria -- e o coeficiente passaria a medir a
        ordem de insercao no banco."""
        pares = [(80, v) for v in range(12)]
        assert calibracao.spearman(pares) is None

    def test_sem_variacao_e_None_e_nao_zero(self):
        """Zero significaria "medimos e nao ha relacao", que e uma afirmacao.
        None significa "nao da para afirmar"."""
        assert calibracao.spearman([(5, 5)] * 12) is None

    def test_none_no_par_e_descartado(self):
        pares = [(i, i) for i in range(12)] + [(None, 5), (5, None)]
        assert calibracao.spearman(pares) == 1.0

    def test_modelo_que_acerta_x_modelo_que_chuta(self):
        """O relatorio precisa distinguir os dois casos -- e a pergunta
        inteira da fase."""
        acerta = calibracao.relatorio(_itens(30, acerta=True))
        chuta = calibracao.relatorio(_itens(30, acerta=False, semente=11))
        assert acerta["rho_score_retencao"] > 0.9
        assert abs(chuta["rho_score_retencao"]) < 0.6


class TestFaixas:

    def test_agrupa_por_score(self):
        r = calibracao.relatorio([
            {"score": 90, "retention_pct": 50.0, "views": 100},
            {"score": 85, "retention_pct": 46.0, "views": 90},
            {"score": 70, "retention_pct": 30.0, "views": 40},
            {"score": 40, "retention_pct": 20.0, "views": 10},
        ])
        por = {f["faixa"]: f for f in r["por_faixa"]}
        assert por["alto"]["clipes"] == 2
        assert por["alto"]["retencao_media"] == 48.0
        assert por["medio"]["clipes"] == 1
        assert por["baixo"]["clipes"] == 1

    def test_faixa_vazia_nao_inventa_media(self):
        r = calibracao.relatorio([{"score": 90, "retention_pct": 50.0}])
        por = {f["faixa"]: f for f in r["por_faixa"]}
        assert por["baixo"]["retencao_media"] is None

    def test_o_contraste_entre_faixas_aponta_para_o_ADR_006(self):
        r = calibracao.relatorio([
            {"score": 90, "retention_pct": 55.0},
            {"score": 45, "retention_pct": 18.0},
        ])
        assert any("ADR-006" in o for o in r["observacoes"])

    def test_score_ausente_nao_entra_em_faixa(self):
        r = calibracao.relatorio([{"score": None, "retention_pct": 50.0}])
        assert sum(f["clipes"] for f in r["por_faixa"]) == 0


# --------------------------------------------------------------------------- #
# O cruzamento no banco
# --------------------------------------------------------------------------- #

@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


def _chama(url):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.get(url)
    return asyncio.run(_do())


def _publicar(ambiente, score=88, titulo="Corte bom"):
    job_id = str(uuid.uuid4())
    pasta = ambiente / job_id
    pasta.mkdir()
    shorts = [{"start": 0.0, "end": 30.0, "predicted_score": score,
               "video_title_for_youtube_short": titulo,
               "video_description_for_tiktok": "d"}]
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
        async with db.tenant() as t:
            existentes = await t.all(db_models.Account,
                                     db_models.Account.handle == "canal")
            conta = existentes[0] if existentes else t.add(
                db_models.Account(platform="youtube", handle="canal"))
            await t.flush()
            corte = [c for c in await t.all(db_models.Clip)
                     if c.job_id == job_id][0]
            pub = t.add(db_models.Publication(
                clip_id=corte.id, account_id=conta.id, driver="youtube-api",
                status="published", remote_id="V" + job_id[:6]))
            await t.commit()
            return pub.id
    return corre(_t)


class TestCruzamentoNoBanco:

    def test_junta_score_e_medida(self, ambiente):
        pub_id = _publicar(ambiente, score=88, titulo="O bom")
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=120,
                                                   retention_pct=57.5))
        itens = corre(publish_queue.cruzamento)
        assert len(itens) == 1
        assert itens[0]["score"] == 88.0
        assert itens[0]["retention_pct"] == 57.5
        assert itens[0]["titulo"] == "O bom"

    def test_vale_a_leitura_MAIS_RECENTE(self, ambiente):
        """`metrics` e serie temporal: somar todas contaria o mesmo video uma
        vez por coleta e daria peso maior ao publicado ha mais tempo."""
        pub_id = _publicar(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=10,
                                                   retention_pct=30.0))
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=300,
                                                   retention_pct=61.0))
        itens = corre(publish_queue.cruzamento)
        assert len(itens) == 1
        assert itens[0]["views"] == 300

    def test_publicacao_sem_medida_aparece_com_None(self, ambiente):
        """Ela existe e ainda nao foi medida -- some-la do relatorio esconderia
        que ha o que coletar."""
        _publicar(ambiente)
        itens = corre(publish_queue.cruzamento)
        assert len(itens) == 1
        assert itens[0]["retention_pct"] is None

    def test_o_endpoint_responde_com_as_ressalvas(self, ambiente):
        pub_id = _publicar(ambiente)
        corre(lambda: publish_queue.gravar_metrica(pub_id, views=5,
                                                   retention_pct=40.0))
        corpo = _chama("/api/calibracao").json()
        assert corpo["clipes_medidos"] == 1
        assert corpo["rho_score_retencao"] is None
        assert corpo["minimo_para_correlacao"] == calibracao.MINIMO_PARA_CORRELACAO
        assert len(corpo["clipes"]) == 1

    def test_sem_publicacao_nenhuma_o_endpoint_responde(self, ambiente):
        corpo = _chama("/api/calibracao").json()
        assert corpo["clipes_publicados"] == 0
        assert any("--leitura" in o for o in corpo["observacoes"])
