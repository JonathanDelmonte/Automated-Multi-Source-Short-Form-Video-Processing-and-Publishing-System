"""Analises por canal -- etapa 7.4.

A conta e pura (`analises.py`): os testes montam galhos com leituras em horas
escolhidas e um `agora` fixo, sem banco e sem relogio. No fim, os endpoints com
o banco de verdade, para garantir que o que o banco devolve e o que a conta le.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import analises

AGORA = datetime(2026, 9, 26, 15, 0, tzinfo=timezone.utc)


def _h(horas_atras: float) -> str:
    return (AGORA - timedelta(hours=horas_atras)).isoformat()


def _galho(pid="p1", plataforma="youtube", canal="c1", postado_ha=72.0, leituras=(), **extra):
    return {"publication_id": pid, "platform": plataforma, "channel_id": canal,
            "handle": "@canal", "titulo": f"Corte {pid}", "posted_at": _h(postado_ha),
            "leituras": [{"collected_at": _h(h), **numeros} for h, numeros in leituras],
            **extra}


class TestUmaPublicacao:

    def test_vale_o_ultimo_numero_conhecido_de_cada_campo(self):
        """A leitura de hoje sem retencao (o Analytics recusou nesta volta) nao
        apaga a de ontem."""
        g = _galho(leituras=[(30, {"views": 100, "retention_pct": 55.0}),
                             (2, {"views": 180, "retention_pct": None})])
        u = analises.ultimo(g)
        assert (u["views"], u["retention_pct"]) == (180, 55.0)
        assert u["medido_em"] == AGORA - timedelta(hours=2)

    def test_as_leituras_fora_de_ordem(self):
        g = _galho(leituras=[(2, {"views": 180}), (30, {"views": 100})])
        assert analises.ultimo(g)["views"] == 180

    def test_ganho_com_base(self):
        g = _galho(leituras=[(30, {"views": 100}), (20, {"views": 130}), (1, {"views": 250})])
        assert analises.ganho_no_periodo(g, "views", AGORA - timedelta(hours=24), AGORA) == 150

    def test_post_novo_tem_base_zero(self):
        g = _galho(postado_ha=5, leituras=[(1, {"views": 40})])
        assert analises.ganho_no_periodo(g, "views", AGORA - timedelta(hours=24), AGORA) == 40

    def test_post_antigo_medido_pela_primeira_vez_nao_ganha_a_vida_inteira(self):
        """Um pico falso no dia em que alguem conectou a conta seria pior que
        a falta do numero."""
        g = _galho(postado_ha=24 * 30, leituras=[(3, {"views": 90000})])
        assert analises.ganho_no_periodo(g, "views", AGORA - timedelta(hours=24), AGORA) is None

    def test_views_do_primeiro_dia(self):
        """A leitura mais perto de 24 h depois do post, entre 18 h e 36 h."""
        g = _galho(postado_ha=60, leituras=[(50, {"views": 30}), (37, {"views": 80}),
                                            (34, {"views": 95}), (10, {"views": 400})])
        # postado ha 60 h: 24 h depois = ha 36 h; a de 37 h esta a 1 h, a de
        # 34 h a 2 h.
        assert analises.views_no_primeiro_dia(g) == 80

    def test_sem_leitura_no_primeiro_dia(self):
        g = _galho(postado_ha=100, leituras=[(95, {"views": 10}), (1, {"views": 900})])
        assert analises.views_no_primeiro_dia(g) is None


class TestSomas:

    def test_totais_somam_so_quem_tem_o_numero(self):
        galhos = [_galho("a", leituras=[(1, {"views": 100, "likes": 10, "retention_pct": 40.0})]),
                  _galho("b", leituras=[(1, {"views": 50, "retention_pct": 60.0})]),
                  _galho("c")]
        t = analises.totais(galhos)
        assert (t["publicados"], t["medidos"], t["views"], t["likes"]) == (3, 2, 150, 10)
        assert t["retencao_media"] == 50.0 and t["com_retencao"] == 2
        assert t["comments"] is None, "ninguem mediu comentarios: None, e nao zero"

    def test_ganho_de_24h_so_de_quem_tem_base(self):
        galhos = [_galho("a", leituras=[(30, {"views": 100}), (1, {"views": 160})]),
                  _galho("b", postado_ha=24 * 20, leituras=[(2, {"views": 5000})])]
        g = analises.ganho(galhos, AGORA)
        assert g["views"] == 60 and g["medidos"] == 1

    def test_por_plataforma_na_ordem_das_telas(self):
        galhos = [_galho("a", plataforma="tiktok", leituras=[(1, {"views": 10})]),
                  _galho("b", plataforma="youtube", leituras=[(1, {"views": 20})])]
        linhas = analises.por_plataforma(galhos)
        assert [l["plataforma"] for l in linhas] == ["youtube", "tiktok"]
        assert linhas[1]["views"] == 10

    def test_filtrar_por_canal_e_plataforma(self):
        galhos = [_galho("a", canal="c1"), _galho("b", canal="c2", plataforma="tiktok"),
                  _galho("c", canal=None)]
        assert [g["publication_id"] for g in analises.filtrar(galhos, "c1")] == ["a"]
        assert [g["publication_id"] for g in analises.filtrar(galhos, "sem")] == ["c"]
        assert [g["publication_id"] for g in analises.filtrar(galhos, None, "tiktok")] == ["b"]

    def test_melhores_pelo_ultimo_numero(self):
        galhos = [_galho("a", leituras=[(1, {"views": 10})]),
                  _galho("b", leituras=[(1, {"views": 900})]),
                  _galho("c")]
        assert [m["publication_id"] for m in analises.melhores(galhos)] == ["b", "a"]


class TestSerie:

    def test_views_ganhas_por_dia_local(self):
        """O dia e o de quem olha: com o fuso de Brasilia (-180), 26-set 01:00
        UTC ainda e 25-set."""
        g = _galho(postado_ha=24 * 10, leituras=[
            (50, {"views": 100}),      # 24-set 13:00 UTC = 24-set 10:00 local
            (38, {"views": 150}),      # 25-set 01:00 UTC = 24-set 22:00 local
            (14, {"views": 400}),      # 26-set 01:00 UTC = 25-set 22:00 local
            (1, {"views": 450}),       # 26-set 14:00 UTC = 26-set 11:00 local
        ])
        serie = analises.serie([g], AGORA, dias=3, fuso_min=-180)
        assert [d["dia"] for d in serie] == ["2026-09-24", "2026-09-25", "2026-09-26"]
        # 24-set: a primeira leitura e do meio do dia, e o post e antigo: sem
        # base, o dia fica sem numero -- e nao com as 100 views da vida dele.
        assert serie[0]["views"] is None
        assert serie[1]["views"] == 250 and serie[2]["views"] == 50
        assert serie[2]["por_plataforma"] == {"youtube": 50}

    def test_leitura_na_virada_do_dia_serve_de_base(self):
        g = _galho(postado_ha=24 * 10, leituras=[(60, {"views": 100}), (38, {"views": 150})])
        # 60 h atras = 24-set 03:00 UTC = 24-set 00:00 em Brasilia, exatamente.
        assert analises.serie([g], AGORA, dias=3, fuso_min=-180)[0]["views"] == 50

    def test_o_post_do_dia_conta_do_zero(self):
        g = _galho(postado_ha=5, leituras=[(1, {"views": 70})])
        assert analises.serie([g], AGORA, dias=1)[0]["views"] == 70


class TestHorario:

    def _post(self, pid, hora_utc, views_24h):
        # Postado ha 3 dias, na hora pedida; a leitura de 24 h depois.
        postado = datetime(2026, 9, 23, hora_utc, 0, tzinfo=timezone.utc)
        return {"publication_id": pid, "platform": "youtube", "posted_at": postado.isoformat(),
                "leituras": [{"collected_at": (postado + timedelta(hours=24)).isoformat(),
                              "views": views_24h}]}

    def test_a_faixa_e_a_hora_local(self):
        """14:00 UTC e 11:00 em Brasilia: manha, e nao tarde."""
        r = analises.por_horario([self._post("a", 14, 100)], fuso_min=-180)
        manha = next(f for f in r["faixas"] if f["faixa"] == "manha")
        assert manha["posts"] == 1 and manha["views_do_primeiro_dia_mediana"] == 100

    def test_sem_amostra_nao_ha_conclusao(self):
        """Os numeros saem; a frase de qual faixa rende mais, nao."""
        posts = [self._post(f"m{i}", 14, 1000) for i in range(3)] + \
                [self._post(f"t{i}", 20, 10) for i in range(3)]
        r = analises.por_horario(posts, fuso_min=-180)
        assert r["melhor"] is None
        assert all(not f["amostra_suficiente"] for f in r["faixas"])

    def test_com_amostra_aponta_a_faixa(self):
        posts = [self._post(f"m{i}", 14, 1000 + i) for i in range(5)] + \
                [self._post(f"t{i}", 20, 10 + i) for i in range(5)]
        r = analises.por_horario(posts, fuso_min=-180)
        assert r["melhor"] == "manha"
        assert r["minimo"] == analises.MINIMO_POR_HORARIO

    def test_empate_nao_escolhe(self):
        posts = [self._post(f"m{i}", 14, 100) for i in range(5)] + \
                [self._post(f"t{i}", 20, 100) for i in range(5)]
        r = analises.por_horario(posts, fuso_min=-180)
        assert r["melhor"] is None and r["parecidas"] is True

    def test_diferenca_pequena_nao_e_vencedor(self):
        """2.036 contra 2.020 (o que o demo da 7.4 mostrou) nao e "a tarde
        rende mais": a melhor faixa tem de passar a segunda pela margem."""
        posts = [self._post(f"m{i}", 14, 2036) for i in range(5)] + \
                [self._post(f"t{i}", 20, 2020) for i in range(5)]
        r = analises.por_horario(posts, fuso_min=-180)
        assert r["melhor"] is None and r["parecidas"] is True
        posts = [self._post(f"m{i}", 14, 1300) for i in range(5)] + \
                [self._post(f"t{i}", 20, 1000) for i in range(5)]
        assert analises.por_horario(posts, fuso_min=-180)["melhor"] == "manha"


class TestTelas:

    def test_resumo_tem_tudo_o_que_a_tela_desenha(self):
        r = analises.resumo([_galho(leituras=[(1, {"views": 5})])], AGORA)
        assert set(r) == {"totais", "ganho_24h", "por_plataforma", "serie",
                          "melhores", "por_horario"}
        assert len(r["serie"]) == 28

    def test_lado_a_lado_com_o_grupo_sem_canal(self):
        galhos = [_galho("a", canal="c1", leituras=[(1, {"views": 10})]),
                  _galho("b", canal=None, leituras=[(1, {"views": 7})])]
        linhas = analises.lado_a_lado([{"id": "c1", "name": "Infantil"},
                                       {"id": "c2", "name": "Vazio"}], galhos, AGORA)
        assert [l["canal"] and l["canal"]["id"] for l in linhas] == ["c1", "c2", None]
        assert linhas[0]["totais"]["views"] == 10 and linhas[1]["totais"]["views"] is None
        assert linhas[2]["totais"]["views"] == 7

    def test_hoje(self):
        galhos = [_galho("a", canal="c1", postado_ha=3, leituras=[(1, {"views": 40})]),
                  _galho("b", canal="c1", postado_ha=48,
                         leituras=[(30, {"views": 100}), (1, {"views": 400})])]
        r = analises.hoje([{"id": "c1", "name": "Infantil"}], galhos, AGORA, fuso_min=-180)
        assert r["ganho_24h"]["views"] == 340
        assert r["publicados_hoje"] == 1
        assert r["destaque"]["publication_id"] == "b" and r["destaque"]["ganho_views"] == 300
        assert r["por_canal"][0]["ganho_24h"]["views"] == 340

    @pytest.mark.parametrize("bruto, esperado", [(None, 0), ("x", 0), (-180, -180),
                                                 (99999, 14 * 60)])
    def test_o_fuso_torto_nao_derruba(self, bruto, esperado):
        assert analises.fuso(bruto).utcoffset(None) == timedelta(minutes=esperado)


# --------------------------------------------------------------------------- #
# Os endpoints, com o banco de verdade
# --------------------------------------------------------------------------- #

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")


def corre(fn):
    return asyncio.run(fn())


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
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


def _canal(nome, contas):
    r = _chama("POST", "/api/canais", {"name": nome, "requires_approval": False,
                                       "novas_contas": contas})
    assert r.status_code == 200, r.text
    return r.json()


def _publicado(ambiente, conta_id, score=80, status="published", titulo="Corte"):
    job_id = str(uuid.uuid4())
    shorts = [{"start": 0.0, "end": 20.0, "predicted_score": score,
               "video_title_for_youtube_short": titulo}]
    (ambiente / job_id).mkdir()
    (ambiente / job_id / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
        async with db.tenant() as t:
            corte = [c for c in await t.all(db_models.Clip) if c.job_id == job_id][0]
            pub = t.add(db_models.Publication(clip_id=corte.id, account_id=conta_id,
                                              driver="manual", status=status,
                                              remote_id="R" + job_id[:8]))
            await t.flush()
            if status == "published":
                t.add(db_models.PublicationPost(publication_id=pub.id))
            await t.commit()
            return pub.id
    return corre(_t)


class TestEndpoints:

    def test_o_canal_ligado_mostra_as_tres_telas(self, ambiente):
        """O "pronto quando" da 7.4: um canal ligado mostra os numeros de cada
        plataforma, e o relatorio de calibracao conta os cortes medidos."""
        canal = _canal("Infantil", [{"platform": "youtube", "handle": "@inf"},
                                    {"platform": "tiktok", "handle": "@inf"}])
        yt = next(c["id"] for c in canal["contas"] if c["platform"] == "youtube")
        tt = next(c["id"] for c in canal["contas"] if c["platform"] == "tiktok")
        p1 = _publicado(ambiente, yt, score=90)
        p2 = _publicado(ambiente, tt, score=70)
        _publicado(ambiente, yt, status="scheduled")
        corre(lambda: publish_queue.gravar_metrica(p1, views=500, retention_pct=62.0, likes=40))
        corre(lambda: publish_queue.gravar_metrica(p2, views=1200, likes=90, shares=12))

        geral = _chama("GET", f"/api/analises?canal={canal['id']}&fuso_min=-180").json()
        assert geral["totais"]["publicados"] == 2, "o agendado nao foi ao ar"
        assert geral["totais"]["views"] == 1700 and geral["totais"]["likes"] == 130
        assert [p["plataforma"] for p in geral["por_plataforma"]] == ["youtube", "tiktok"]
        assert geral["ganho_24h"]["views"] == 1700, "os dois foram ao ar hoje: base zero"
        assert {c["platform"] for c in geral["contas"]} == {"youtube", "tiktok"}
        assert all(c["medir"] is False for c in geral["contas"])

        youtube = _chama("GET", f"/api/analises?canal={canal['id']}&plataforma=youtube").json()
        assert youtube["totais"]["views"] == 500 and youtube["totais"]["retencao_media"] == 62.0
        tiktok = _chama("GET", f"/api/analises?canal={canal['id']}&plataforma=tiktok").json()
        assert tiktok["totais"]["shares"] == 12 and tiktok["totais"]["retencao_media"] is None

        cal = _chama("GET", f"/api/calibracao?canal={canal['id']}").json()
        assert cal["clipes_medidos"] == 2 and cal["clipes_publicados"] == 2
        assert [p["plataforma"] for p in cal["por_plataforma"]] == ["youtube", "tiktok"]
        assert _chama("GET", "/api/calibracao?plataforma=tiktok").json()["clipes_medidos"] == 1

    def test_lado_a_lado_e_hoje(self, ambiente):
        a = _canal("Infantil", [{"platform": "youtube", "handle": "@inf"}])
        _canal("Financas", [{"platform": "youtube", "handle": "@fin"}])
        solta = _chama("POST", "/api/contas", {"platform": "tiktok", "handle": "@solta"}).json()
        pa = _publicado(ambiente, a["contas"][0]["id"])
        ps = _publicado(ambiente, solta["id"])
        corre(lambda: publish_queue.gravar_metrica(pa, views=30))
        corre(lambda: publish_queue.gravar_metrica(ps, views=4))

        lado = _chama("GET", "/api/analises/canais").json()["canais"]
        assert [l["canal"]["name"] if l["canal"] else None for l in lado] == \
            ["Financas", "Infantil", None]
        assert "avatar" not in lado[0]["canal"]
        assert lado[1]["totais"]["views"] == 30 and lado[2]["totais"]["views"] == 4
        assert len(lado[1]["serie"]) == 14

        hoje = _chama("GET", "/api/analises/hoje?fuso_min=-180").json()
        assert hoje["ganho_24h"]["views"] == 34
        assert hoje["publicados_hoje"] == 2
        assert hoje["destaque"]["ganho_views"] == 30

    def test_sem_nada_publicado(self, ambiente):
        r = _chama("GET", "/api/analises").json()
        assert r["totais"]["publicados"] == 0 and r["totais"]["views"] is None
        assert _chama("GET", "/api/analises/hoje").json()["destaque"] is None

    @pytest.mark.parametrize("url", ["/api/analises?canal=../x", "/api/analises?plataforma=orkut"])
    def test_recorte_torto(self, ambiente, url):
        assert _chama("GET", url).status_code == 400

    def test_dias_fora_da_faixa(self, ambiente):
        assert len(_chama("GET", "/api/analises?dias=0").json()["serie"]) == 1
        assert len(_chama("GET", "/api/analises?dias=99999").json()["serie"]) == \
            app_module.DIAS_MAXIMOS_DA_SERIE
