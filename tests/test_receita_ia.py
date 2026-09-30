"""A receita de IA (etapa 7.7): o canal cria sozinho, no estilo dele.

O "pronto quando" da etapa, na parte da automacao: com o estilo salvo e a
receita ligada, o laco pede o video pela mesma porta do painel
(`/api/criacoes`), espera o job, e o video vai para a caixa de aprovacao ou
para a agenda do canal -- e o proximo sai com a proxima ideia, sem repetir.

O job e "terminado" a mao (a pasta como o `criar_video.py` a deixaria), e a
rede das midias e a de `midia_ia._post`, imitada.
"""
import asyncio
import base64
import io
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
automacao = pytest.importorskip("automacao")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")
import fuso
import midia_ia
import receitas


def corre(coro_fn):
    return asyncio.run(coro_fn())


def _png():
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (64, 64), (240, 240, 240)).save(saida, format="PNG")
    return saida.getvalue()


def _rede(url, *, headers, json_body=None, files=None, timeout=180.0):
    return 200, "application/json", json.dumps(
        {"result": {"image": base64.b64encode(_png()).decode()}, "success": True}).encode()


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("SCHEDULE_JITTER_MINUTES", "5")
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    fila = []
    monkeypatch.setattr(app_module, "_enqueue_job", lambda job_id, priority=2: fila.append(job_id))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "conta")
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    for var in ("CLOUDFLARE_IMAGE_NEURONS_DAILY", "GEMINI_TTS_CALLS_DAILY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(midia_ia, "_post", _rede)
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    fuso.guardar(db.SELF_HOST_TENANT_ID, "Etc/GMT+3", -180)
    yield {"saida": saida, "fila": fila, "tmp": tmp_path}
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo if corpo is not None
                                        else ({} if metodo in ("POST", "PUT") else None))
    return asyncio.run(_do())


def _canal(aprovacao=False, por_dia=3, com_estilo=True):
    r = _chama("POST", "/api/canais", {
        "name": f"Historinhas {uuid.uuid4().hex[:4]}", "niche": "infantil",
        "requires_approval": aprovacao, "language": "pt-BR",
        "novas_contas": [{"platform": "youtube", "handle": f"yt-{uuid.uuid4().hex[:6]}"}],
        "ajustes": {"agenda": {"janelas": [11, 15, 19], "por_dia": por_dia}}})
    assert r.status_code == 200, r.text
    canal = r.json()
    if com_estilo:
        estilo = _chama("PUT", f"/api/canais/{canal['id']}/estilo", {"spec": {
            "cenas": 4, "personagens": [{"nome": "Lulu", "descricao": "coelhinha"}]}}).json()
        pid = estilo["estilo"]["spec"]["personagens"][0]["id"]
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        assert r.status_code == 200, r.text
    return canal


def _receita(canal_id, spec, ativa=True):
    return _chama("PUT", f"/api/canais/{canal_id}/receita?tipo=ia", {"spec": spec, "ativa": ativa})


def _volta():
    return list(corre(lambda: app_module._uma_volta_da_automacao()).values())[0]


def _estado(canal_id):
    return _chama("GET", f"/api/canais/{canal_id}/receita?tipo=ia").json()["receita"]["estado"]


def _terminar(ambiente, job_id, status="completed", titulo="A Lulu e a cenoura"):
    """O que o `criar_video.py` deixaria na pasta, e o fim do job no motor."""
    pasta = ambiente["saida"] / job_id
    job = app_module.jobs[job_id]
    job["status"] = status
    if status != "completed":
        job["logs"].append("❌ A cota gratis de imagem de hoje acabou.")
        corre(lambda: app_module._ia_depois_do_job(job_id))
        return
    (pasta / "roteiro.json").write_text(json.dumps(
        {"titulo": titulo, "descricao": "", "hashtags": [], "cenas": []}), encoding="utf-8")
    (pasta / "criacao_clip_1.mp4").write_bytes(b"\x00" * 64)
    (pasta / "criacao_metadata.json").write_text(json.dumps({"shorts": [{
        "start": 0, "end": 30.0, "video_title_for_youtube_short": titulo,
        "video_description_for_tiktok": "uma historia"}],
        "transcript": {"language": "pt", "segments": []}}))
    job["result"] = {"clips": [{"start": 0, "end": 30.0, "clip_index": 0,
                                "video_title_for_youtube_short": titulo,
                                "video_url": f"/videos/{job_id}/criacao_clip_1.mp4"}]}
    corre(lambda: app_module._fechar_job_no_banco(job_id))
    corre(lambda: app_module._ia_depois_do_job(job_id))


# --------------------------------------------------------------------------- #
# O documento
# --------------------------------------------------------------------------- #

class TestDocumento:

    def test_padrao_e_ideias_limpas(self):
        spec = receitas.normalizar_ia({"ideias": "A Lulu e a chuva\n\n  a lulu e a CHUVA!\nO Bento",
                                       "tema": " amizade "})
        assert spec["ideias"] == ["A Lulu e a chuva", "O Bento"]
        assert spec["tema"] == "amizade" and spec["ritmo"] == {"videos_por_dia": 1}

    def test_a_proxima_ideia_segue_a_lista_e_depois_o_tema(self):
        spec = receitas.normalizar_ia({"ideias": ["um", "dois", "tres"], "tema": "animais"})
        assert receitas.proxima_ideia(spec) == ("um", True)
        assert receitas.proxima_ideia(spec, feitas=["UM"], puladas=["dois"]) == ("tres", True)
        assert receitas.proxima_ideia(spec, feitas=["um", "dois", "tres"]) == \
            ("uma ideia nova sobre animais", False)
        assert receitas.proxima_ideia(receitas.normalizar_ia(None)) == ("", False)

    @pytest.mark.parametrize("spec,trecho", [
        ({"ideias": ["x" * 400]}, "cada ideia"),
        ({"ritmo": {"videos_por_dia": 0}}, "vídeos por dia"),
        ({"ideias": 3}, "lista"),
    ])
    def test_receita_torta(self, spec, trecho):
        with pytest.raises(receitas.ReceitaInvalida, match=trecho):
            receitas.normalizar_ia(spec)


# --------------------------------------------------------------------------- #
# A API
# --------------------------------------------------------------------------- #

class TestAPI:

    def test_canal_sem_receita_de_ia_mostra_a_padrao(self, ambiente):
        canal = _canal()
        corpo = _chama("GET", f"/api/canais/{canal['id']}/receita?tipo=ia").json()
        assert corpo["receita"]["kind"] == "ia" and corpo["receita"]["ativa"] is False
        assert corpo["proxima_ideia"] == "" and corpo["estilo_falta"] is None
        # A de cortes continua sendo a de antes.
        cortes = _chama("GET", f"/api/canais/{canal['id']}/receita").json()["receita"]
        assert cortes["kind"] == "cortes"

    def test_so_liga_com_o_estilo_pronto(self, ambiente):
        canal = _canal(com_estilo=False)
        r = _receita(canal["id"], {"tema": "amizade"})
        assert r.status_code == 400 and "estilo de criação" in r.json()["detail"]
        assert _receita(canal["id"], {"tema": "amizade"}, ativa=False).status_code == 200

    def test_tipo_desconhecido(self, ambiente):
        canal = _canal(com_estilo=False)
        assert _chama("GET", f"/api/canais/{canal['id']}/receita?tipo=serie").status_code == 400


# --------------------------------------------------------------------------- #
# O laco
# --------------------------------------------------------------------------- #

class TestLaco:

    def test_cria_agenda_e_segue_para_a_proxima_ideia(self, ambiente):
        canal = _canal()
        assert _receita(canal["id"], {"ideias": ["A Lulu e a chuva", "A Lulu no mar"],
                                      "ritmo": {"videos_por_dia": 5}}).status_code == 200
        assert "criando “A Lulu e a chuva”" in _volta()
        job_id = ambiente["fila"][0]
        pedido = json.loads((ambiente["saida"] / job_id / "criacao.json").read_text(encoding="utf-8"))
        assert pedido["ideia"] == "A Lulu e a chuva" and pedido["receita_id"]
        # Enquanto o job roda, a receita espera: um video de cada vez.
        assert "criando" in _volta() and len(ambiente["fila"]) == 1

        _terminar(ambiente, job_id, titulo="A Lulu e a chuva de verao")
        estado = _estado(canal["id"])
        assert estado["criando"] is None and estado["feitas"] == ["A Lulu e a chuva"]
        assert "na agenda do canal" in estado["situacao"]
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        assert len(fila) == 1 and fila[0]["scheduled_at"]

        # A proxima volta cria o proximo, com a proxima ideia e o titulo feito na lista.
        assert "criando “A Lulu no mar”" in _volta()
        segundo = json.loads((ambiente["saida"] / ambiente["fila"][1] / "criacao.json")
                             .read_text(encoding="utf-8"))
        assert "A Lulu e a chuva de verao" in segundo["ja_feitos"]

    def test_canal_com_aprovacao_espera_a_pessoa(self, ambiente):
        canal = _canal(aprovacao=True)
        _receita(canal["id"], {"tema": "amizade"})
        _volta()
        _terminar(ambiente, ambiente["fila"][0])
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"] == []
        caixa = _chama("GET", f"/api/aprovacoes?canal={canal['id']}").json()["aprovacoes"]
        assert len(caixa) == 1
        assert "esperando a sua aprovação" in _estado(canal["id"])["situacao"]

    def test_o_video_que_parou_continua_de_onde_parou(self, ambiente):
        canal = _canal()
        _receita(canal["id"], {"ideias": ["um", "dois"], "ritmo": {"videos_por_dia": 5}})
        _volta()
        job_id = ambiente["fila"][0]
        _terminar(ambiente, job_id, status="failed")
        assert "parou" in _estado(canal["id"])["situacao"]
        # Tentativa 2 e 3: o MESMO projeto volta para a fila.
        assert "tentativa 2" in _volta()
        app_module.jobs[job_id]["status"] = "failed"
        assert "tentativa 3" in _volta()
        assert ambiente["fila"] == [job_id, job_id, job_id]
        # Depois da terceira, a receita pula a ideia e segue.
        app_module.jobs[job_id]["status"] = "failed"
        assert "parou 3 vezes" in _volta()
        estado = _estado(canal["id"])
        assert estado["puladas"] == ["um"] and estado["criando"] is None
        assert "criando “dois”" in _volta()

    def test_sem_cota_espera_sem_criar(self, ambiente, monkeypatch):
        canal = _canal()
        _receita(canal["id"], {"tema": "amizade"})
        monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "300")
        assert "cota grátis de imagem" in _volta()
        assert ambiente["fila"] == []

    def test_o_ritmo_do_dia(self, ambiente):
        canal = _canal()
        _receita(canal["id"], {"tema": "amizade", "ritmo": {"videos_por_dia": 1}})
        _volta()
        _terminar(ambiente, ambiente["fila"][0])
        assert "hoje" in _volta() and len(ambiente["fila"]) == 1

    def test_estoque_cheio_espera(self, ambiente):
        canal = _canal(por_dia=1)
        _receita(canal["id"], {"tema": "amizade", "ritmo": {"videos_por_dia": 5}})
        _volta()
        _terminar(ambiente, ambiente["fila"][0])
        _volta()
        _terminar(ambiente, ambiente["fila"][1])
        assert "dá para 2 dias" in _volta()
        assert len(ambiente["fila"]) == 2

    def test_cancelado_pula_a_ideia(self, ambiente):
        canal = _canal()
        _receita(canal["id"], {"ideias": ["um", "dois"], "ritmo": {"videos_por_dia": 5}})
        _volta()
        app_module.jobs[ambiente["fila"][0]]["status"] = "cancelled"
        assert "foi cancelado" in _volta()
        assert "criando “dois”" in _volta()

    def test_salvar_a_receita_devolve_as_puladas(self, ambiente):
        canal = _canal()
        _receita(canal["id"], {"ideias": ["um", "dois"], "ritmo": {"videos_por_dia": 5}})
        _volta()
        app_module.jobs[ambiente["fila"][0]]["status"] = "cancelled"
        _volta()
        assert _estado(canal["id"])["puladas"] == ["um"]
        _receita(canal["id"], {"ideias": ["um", "dois"]})
        assert "puladas" not in _estado(canal["id"])

    def test_receita_de_ia_e_de_cortes_no_mesmo_canal(self, ambiente):
        canal = _canal()
        _receita(canal["id"], {"tema": "amizade"})
        r = _chama("PUT", f"/api/canais/{canal['id']}/receita",
                   {"spec": {"fonte": {"tema": "desenho"}}, "ativa": False})
        assert r.status_code == 200
        tipos = sorted(r["tipo"] for r in _chama("GET", "/api/automacao").json()["receitas"])
        assert tipos == ["busca", "ia"]

    def test_a_porta_da_criacao_confere_a_receita(self, ambiente):
        canal = _canal()
        outro = _canal()
        _receita(outro["id"], {"tema": "x"}, ativa=False)
        receita_do_outro = _chama("GET", f"/api/canais/{outro['id']}/receita?tipo=ia") \
            .json()["receita"]["id"]
        r = _chama("POST", "/api/criacoes", {"channel_id": canal["id"],
                                             "receita_id": receita_do_outro})
        assert r.status_code == 400 and "receita de IA deste canal" in r.json()["detail"]
