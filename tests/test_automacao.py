"""A automacao por canal de ponta a ponta (etapa 7.5): banco, API e o laco.

O "pronto quando" da etapa: "o canal infantil, com o PC ligado e ninguem
mexendo, acha um video com licenca, corta, espera a aprovacao (ou nao, se o
canal estiver assim) e posta nos horarios dele, com o credito na descricao."

A busca de verdade e o pipeline de verdade nao rodam aqui: a busca e trocada
por uma resposta pronta (a forma que o `busca_cc.py` devolve), e o job, que o
`/api/process` cria de verdade, e "terminado" a mao -- a pasta com os cortes e
o metadata, como o `main.py` deixaria. Todo o resto e o motor de verdade: a
receita, a caixa de entrada, o `/api/process` pelo mesmo caminho do painel, o
fim do job, a caixa de aprovacao e a agenda do canal.
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
automacao = pytest.importorskip("automacao")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
import fuso
import licencas
import template

BRASILIA = timezone(timedelta(hours=-3))


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.setenv("SCHEDULE_JITTER_MINUTES", "5")
    saida = tmp_path / "saida"
    saida.mkdir()
    envios = tmp_path / "envios"
    envios.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(envios))
    monkeypatch.setattr(app_module, "jobs", {})
    # O job nasce na fila e fica la: o worker nao roda nos testes.
    monkeypatch.setattr(app_module, "_enqueue_job", lambda job_id, priority=2: None)
    # O probe de qualidade abriria o YouTube; aqui ele responde como a pagina.
    probes = {}

    async def _probe(url):
        return probes.get(url, {"max_height": 1080, "duration": 1800, "origem": None})
    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_teste")
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    fuso.guardar(db.SELF_HOST_TENANT_ID, "Etc/GMT+3", -180)
    yield {"saida": saida, "probes": probes, "tmp": tmp_path}
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo)
    return asyncio.run(_do())


def _canal(nome="Canal infantil", aprovacao=False, plataformas=("youtube", "tiktok"), **extra):
    r = _chama("POST", "/api/canais", {
        "name": nome, "niche": extra.pop("niche", "infantil"),
        "requires_approval": aprovacao,
        "novas_contas": [{"platform": p, "handle": f"{nome[:6]}-{p}-{uuid.uuid4().hex[:4]}"}
                         for p in plataformas],
        "ajustes": {"agenda": {"janelas": [11, 15, 19], "por_dia": 3}}, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _video(vid, **extra):
    return {"key": f"youtube:{vid}", "url": f"https://www.youtube.com/watch?v={vid}",
            "title": f"Desenho {vid}", "author": "Estudio Livre",
            "author_url": "https://www.youtube.com/channel/UC1", "duration_s": 1800,
            "published_at": "2024-02-01", "license": "cc-by",
            "license_text": "Creative Commons Attribution license (reuse allowed)", **extra}


@pytest.fixture()
def busca(monkeypatch):
    """O `busca_cc.py` de mentira: devolve o que o teste mandar."""
    estado = {"respostas": [], "pedidos": []}

    def _rodar(pedido):
        estado["pedidos"].append(pedido)
        if estado["respostas"]:
            return estado["respostas"].pop(0)
        return {"candidatos": [], "recusados": [], "avisos": []}
    monkeypatch.setattr(app_module, "_rodar_busca_cc", _rodar)
    return estado


def _receita(canal_id, spec, ativa=True, confirmar=False):
    r = _chama("PUT", f"/api/canais/{canal_id}/receita",
               {"spec": spec, "ativa": ativa, "confirmar_direitos": confirmar})
    return r


def _terminar_o_job(ambiente, job_id, cortes=3, status="completed"):
    """Faz o que o `main.py` faria: a pasta com os cortes e o metadata, e o
    registro dos cortes no banco (`_fechar_job_no_banco`)."""
    pasta = ambiente["saida"] / job_id
    pasta.mkdir(exist_ok=True)
    shorts = []
    for i in range(cortes):
        shorts.append({"start": i * 40.0, "end": i * 40.0 + 30.0,
                       "video_title_for_youtube_short": f"Corte {i + 1}",
                       "video_description_for_tiktok": f"descricao {i + 1} #fyp",
                       "predicted_score": 90 - i * 10})
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))
    job = app_module.jobs[job_id]
    job["status"] = status
    if status == "completed":
        job["result"] = {"clips": [{"video_url": f"/videos/{job_id}/v_clip_{i + 1}.mp4"}
                                   for i in range(cortes)]}
        corre(lambda: job_registry.registrar_clipes(job_id, shorts))
    else:
        job["logs"].append("❌ ERROR: o download falhou")


def _candidatos(canal_id, status=None):
    url = f"/api/canais/{canal_id}/candidatos" + (f"?status={status}" if status else "")
    return _chama("GET", url).json()["candidatos"]


def _volta():
    return corre(lambda: app_module._uma_volta_da_automacao())


# --------------------------------------------------------------------------- #
# A receita
# --------------------------------------------------------------------------- #

class TestReceita:

    def test_canal_sem_receita_mostra_a_padrao_desligada(self, ambiente):
        canal = _canal()
        corpo = _chama("GET", f"/api/canais/{canal['id']}/receita").json()
        assert corpo["receita"]["id"] is None and corpo["receita"]["ativa"] is False
        assert corpo["receita"]["pronta"] == "falta o tema da busca"
        assert corpo["agenda"]["janelas"] == [11, 15, 19]
        assert corpo["agenda"]["fuso"]["origem"] == "painel"
        assert corpo["criancas"] == {"valor": True, "origem": "nicho"}

    def test_ligar_sem_tema_e_recusado(self, ambiente):
        canal = _canal()
        r = _receita(canal["id"], {"fonte": {"tipo": "busca"}})
        assert r.status_code == 400 and "tema" in r.json()["detail"]

    def test_salvar_e_ligar(self, ambiente):
        canal = _canal()
        r = _receita(canal["id"], {"fonte": {"tema": "desenho animado"},
                                   "edicao": {"cortes_por_video": 3}})
        assert r.status_code == 200, r.text
        receita = r.json()["receita"]
        assert receita["ativa"] and receita["spec"]["edicao"]["cortes_por_video"] == 3

    def test_links_so_ligam_com_a_confirmacao_de_direitos(self, ambiente):
        canal = _canal()
        spec = {"fonte": {"tipo": "links", "links": ["https://youtu.be/dQw4w9WgXcQ"]}}
        assert _receita(canal["id"], spec).status_code == 400
        r = _receita(canal["id"], spec, confirmar=True)
        assert r.status_code == 200 and r.json()["receita"]["spec"]["direitos"]
        # Trocar os links apaga a confirmacao: ela era sobre a lista de antes.
        outro = {"fonte": {"tipo": "links", "links": ["https://youtu.be/aaaaaaaaaaa"]}}
        r = _receita(canal["id"], outro, ativa=False)
        assert r.json()["receita"]["spec"]["direitos"] is None

    def test_template_que_nao_existe(self, ambiente):
        canal = _canal()
        r = _receita(canal["id"], {"fonte": {"tema": "x"},
                                   "edicao": {"template_id": str(uuid.uuid4())}})
        assert r.status_code == 400 and "template" in r.json()["detail"]

    def test_a_pasta_do_canal_e_criada(self, ambiente):
        canal = _canal(nome="Fatos Desconhecidos", niche="curiosidades")
        r = _receita(canal["id"], {"fonte": {"tipo": "pasta"}}, confirmar=True)
        pasta = r.json()["receita"]["pasta"]
        assert pasta["nome"] == "fatos-desconhecidos"
        assert os.path.isdir(pasta["caminho"])
        assert pasta["caminho"].startswith(str(ambiente["tmp"] / "dados" / "entrada"))

    def test_canal_de_outro_tenant_e_404(self, ambiente):
        assert _chama("GET", f"/api/canais/{uuid.uuid4()}/receita").status_code == 404
        assert _chama("GET", "/api/canais/nao-e-id/receita").status_code == 404


# --------------------------------------------------------------------------- #
# O laco: achar, cortar, aprovar, agendar
# --------------------------------------------------------------------------- #

class TestLacoDoCanalInfantil:

    def test_acha_corta_e_agenda_nos_horarios_com_o_credito(self, ambiente, busca):
        """O "pronto quando", no canal que posta sozinho."""
        canal = _canal()
        assert _receita(canal["id"], {"fonte": {"tema": "desenho animado"},
                                      "edicao": {"cortes_por_video": 2}}).status_code == 200
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")], "recusados": [
            {**_video("bbbbbbbbbbb", license="desconhecida"),
             "motivo": "o YouTube nao confirmou a licenca Creative Commons neste video"}]})
        situacao = _volta()
        assert "cortando" in list(situacao.values())[0]
        assert busca["pedidos"][0]["acao"] == "busca"
        assert busca["pedidos"][0]["tema"] == "desenho animado"

        cortando = _candidatos(canal["id"], "processando")
        assert len(cortando) == 1
        job_id = cortando[0]["job_id"]
        # O /api/process de verdade: o canal, a origem e o que a receita pediu.
        job = app_module.jobs[job_id]
        assert job["channel_id"] == canal["id"]
        assert job["env"]["CLIP_TARGET_MIN"] == "2"
        origem = licencas.ler_origem(str(ambiente["saida"] / job_id))
        assert origem["license"] == "cc-by" and origem["found_by"] == "busca"
        assert origem["key"] == "youtube:aaaaaaaaaaa"
        recusados = _candidatos(canal["id"], "recusado")
        assert [c["key"] for c in recusados] == ["youtube:bbbbbbbbbbb"]

        # O job termina: os cortes vao para a agenda do canal, sem aprovacao.
        _terminar_o_job(ambiente, job_id, cortes=3)
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        assert _candidatos(canal["id"], "processado")[0]["job_id"] == job_id
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        # Dois cortes (a receita pediu 2) x duas contas (YouTube e TikTok).
        assert len(fila) == 4
        for p in fila:
            local = datetime.fromisoformat(p["scheduled_at"]).astimezone(BRASILIA)
            minutos = local.hour * 60 + local.minute
            assert any(abs(minutos - h * 60) <= 5 for h in (11, 15, 19)), local
        # Os dois de nota maior.
        assert {p["clip"]["index"] for p in fila} == {0, 1}

        # E o post sai com o credito da licenca, em toda plataforma.
        itens = app_module._itens_do_job(job_id)
        assert itens[0].meta.credit.startswith("Créditos: “Desenho aaaaaaaaaaa”")
        assert "Creative Commons" in itens[0].meta.credit

    def test_canal_com_aprovacao_espera_a_pessoa(self, ambiente, busca):
        canal = _canal(aprovacao=True)
        _receita(canal["id"], {"fonte": {"tema": "desenho"}, "edicao": {"cortes_por_video": 2}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        job_id = _candidatos(canal["id"], "processando")[0]["job_id"]
        _terminar_o_job(ambiente, job_id, cortes=2)
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        # Nada na agenda: os cortes estao na caixa de aprovacao.
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"] == []
        caixa = _chama("GET", f"/api/aprovacoes?canal={canal['id']}").json()["aprovacoes"]
        assert len(caixa) == 2
        assert caixa[0]["clip"]["video_url"].startswith(f"/videos/{job_id}/")
        assert _chama("GET", "/api/automacao").json()["esperando_aprovacao"] == {canal["id"]: 2}

        aprovar, recusar = caixa[0]["id"], caixa[1]["id"]
        r = _chama("POST", "/api/aprovacoes/decidir", {"ids": [aprovar], "decisao": "aprovar"})
        assert r.status_code == 200 and r.json()["resultados"][0]["ok"]
        r = _chama("POST", "/api/aprovacoes/decidir", {"ids": [recusar], "decisao": "recusar"})
        assert r.json()["decididas"] == 1
        # O aprovado ganhou um galho por conta; o recusado, nenhum.
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        assert len(fila) == 2
        assert {p["account"]["platform"] for p in fila} == {"youtube", "tiktok"}
        # Decidir de novo nao faz nada.
        assert _chama("POST", "/api/aprovacoes/decidir",
                      {"ids": [aprovar], "decisao": "aprovar"}).json()["decididas"] == 0
        assert _chama("GET", f"/api/aprovacoes?canal={canal['id']}").json()["aprovacoes"] == []

    def test_aprovar_sem_conta_no_canal_volta_a_esperar(self, ambiente, busca):
        canal = _canal(aprovacao=True, plataformas=())
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        job_id = _candidatos(canal["id"], "processando")[0]["job_id"]
        _terminar_o_job(ambiente, job_id, cortes=1)
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        caixa = _chama("GET", "/api/aprovacoes").json()["aprovacoes"]
        r = _chama("POST", "/api/aprovacoes/decidir", {"ids": [caixa[0]["id"]], "decisao": "aprovar"})
        assert r.json()["resultados"][0]["ok"] is False
        assert "conta" in r.json()["resultados"][0]["detail"]
        assert len(_chama("GET", "/api/aprovacoes").json()["aprovacoes"]) == 1

    def test_job_que_falha_marca_o_video(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        job_id = _candidatos(canal["id"], "processando")[0]["job_id"]
        _terminar_o_job(ambiente, job_id, status="failed")
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        falhou = _candidatos(canal["id"], "falhou")
        assert falhou and "download" in falhou[0]["reason"]

    def test_um_video_de_cada_vez(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}, "ritmo": {"videos_por_dia": 5}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa"), _video("bbbbbbbbbbb")]})
        _volta()
        assert "cortando" in list(_volta().values())[0]
        assert len(_candidatos(canal["id"], "processando")) == 1

    def test_o_ritmo_do_dia(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}, "ritmo": {"videos_por_dia": 1}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa"), _video("bbbbbbbbbbb")]})
        _volta()
        job_id = _candidatos(canal["id"], "processando")[0]["job_id"]
        _terminar_o_job(ambiente, job_id, cortes=1)
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        assert "hoje" in list(_volta().values())[0]

    def test_estoque_cheio_espera(self, ambiente, busca):
        """Com cortes para os proximos dias na agenda, a receita nao corta mais."""
        canal = _canal(ajustes={"agenda": {"janelas": [11, 15, 19], "por_dia": 1}})
        _receita(canal["id"], {"fonte": {"tema": "desenho"}, "edicao": {"cortes_por_video": 3},
                               "ritmo": {"videos_por_dia": 5}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa"), _video("bbbbbbbbbbb")]})
        _volta()
        job_id = _candidatos(canal["id"], "processando")[0]["job_id"]
        _terminar_o_job(ambiente, job_id, cortes=3)
        corre(lambda: app_module._automacao_depois_do_job(job_id))
        situacao = list(_volta().values())[0]
        assert "espera" in situacao, situacao
        assert _candidatos(canal["id"], "novo")[0]["key"] == "youtube:bbbbbbbbbbb"

    def test_video_de_qualidade_baixa_fica_de_fora(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        ambiente["probes"]["https://www.youtube.com/watch?v=aaaaaaaaaaa"] = {
            "max_height": 360, "duration": 1800}
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        recusado = _candidatos(canal["id"], "recusado")
        assert recusado and "360p" in recusado[0]["reason"]

    def test_a_busca_so_repete_depois_do_intervalo(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        assert "não achou" in list(_volta().values())[0]
        assert "mais tarde" in list(_volta().values())[0]
        assert len(busca["pedidos"]) == 1
        # "Buscar agora" nao espera.
        r = _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        assert r.status_code == 200 and len(busca["pedidos"]) == 2

    def test_receita_desligada_nao_roda(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}}, ativa=False)
        assert _volta() == {}
        assert _chama("POST", f"/api/canais/{canal['id']}/receita/rodar").status_code == 400


# --------------------------------------------------------------------------- #
# Nao repetir
# --------------------------------------------------------------------------- #

class TestNaoRepetir:

    def test_o_mesmo_video_nao_e_cortado_por_dois_canais(self, ambiente, busca):
        a = _canal(nome="Canal A")
        b = _canal(nome="Canal B")
        _receita(a["id"], {"fonte": {"tema": "desenho"}})
        _receita(b["id"], {"fonte": {"tema": "desenho"}})
        busca["respostas"] = [{"candidatos": [_video("aaaaaaaaaaa")]},
                              {"candidatos": [_video("aaaaaaaaaaa")]}]
        _volta()
        cortando = _candidatos(a["id"], "processando") + _candidatos(b["id"], "processando")
        assert len(cortando) == 1
        repetido = _candidatos(a["id"], "repetido") + _candidatos(b["id"], "repetido")
        assert [c["key"] for c in repetido] == ["youtube:aaaaaaaaaaa"]

    def test_o_que_foi_cortado_a_mao_tambem_conta(self, ambiente, busca):
        r = _chama("POST", "/api/process", {"url": "https://youtu.be/aaaaaaaaaaa",
                                            "acknowledged": True})
        assert r.status_code == 200, r.text
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        assert _candidatos(canal["id"], "repetido")
        assert not _candidatos(canal["id"], "processando")

    def test_a_busca_nao_confere_de_novo_o_que_ja_conhece(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}})
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _volta()
        _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        assert "youtube:aaaaaaaaaaa" in busca["pedidos"][-1]["vistos"]

    def test_o_mesmo_corte_nao_vai_a_duas_contas_da_mesma_plataforma(self, ambiente):
        """A outra metade do "nao repetir": o corte, nem entre canais. Mas o
        galho do TikTok do mesmo corte e o desenho."""
        job_id = str(uuid.uuid4())
        app_module.jobs[job_id] = {"status": "processing", "logs": [], "tenant_id": db.SELF_HOST_TENANT_ID}

        async def _fonte():
            src = await job_registry.registrar_fonte("upload", "v.mp4")
            await job_registry.registrar_job(job_id, src)
        corre(_fonte)
        _terminar_o_job(ambiente, job_id, cortes=1)
        yt1 = _chama("POST", "/api/contas", {"platform": "youtube", "handle": "um"}).json()
        yt2 = _chama("POST", "/api/contas", {"platform": "youtube", "handle": "dois"}).json()
        tt = _chama("POST", "/api/contas", {"platform": "tiktok", "handle": "tres"}).json()
        assert _chama("POST", "/api/publicar", {"job_id": job_id, "account_id": yt1["id"]}
                      ).json()["publicados"] == 1
        r = _chama("POST", "/api/publicar", {"job_id": job_id, "account_id": yt2["id"]}).json()
        assert r["publicados"] == 0 and "youtube/um" in r["resultados"][0]["detail"]
        r = _chama("POST", "/api/agendar", {"job_id": job_id, "account_id": yt2["id"]}).json()
        assert r["agendados"] == 0
        assert _chama("POST", "/api/publicar", {"job_id": job_id, "account_id": tt["id"]}
                      ).json()["publicados"] == 1


# --------------------------------------------------------------------------- #
# As outras fontes
# --------------------------------------------------------------------------- #

class TestOutrasFontes:

    def test_live_da_twitch_so_corta_no_ar(self, ambiente, busca):
        canal = _canal(nome="Cortes da live", niche="games")
        r = _receita(canal["id"], {"fonte": {"tipo": "twitch", "twitch": "twitch.tv/streamer"}},
                     confirmar=True)
        assert r.status_code == 200, r.text
        busca["respostas"].append({"ao_vivo": False, "titulo": None})
        assert "fora do ar" in list(_volta().values())[0]
        assert not _candidatos(canal["id"])
        busca["respostas"].append({"ao_vivo": True, "titulo": "Jogando"})
        assert "cortando" in list(_volta().values())[0]
        bloco = _candidatos(canal["id"], "processando")[0]
        assert bloco["key"].startswith("twitch-live:") and bloco["license"] == "autorizada"
        job = app_module.jobs[bloco["job_id"]]
        assert "https://twitch.tv/streamer" in job["cmd"]

    def test_pasta_do_canal(self, ambiente, busca):
        canal = _canal(nome="Meus videos", niche="podcasts")
        receita = _receita(canal["id"], {"fonte": {"tipo": "pasta"}}, confirmar=True).json()["receita"]
        pasta = receita["pasta"]["caminho"]
        video = os.path.join(pasta, "episodio 1.mp4")
        with open(video, "wb") as f:
            f.write(b"\x00" * 4096)
        fresco = os.path.join(pasta, "copiando.mp4")
        with open(fresco, "wb") as f:
            f.write(b"\x01" * 4096)
        antigo = time.time() - 600
        os.utime(video, (antigo, antigo))
        with open(os.path.join(pasta, "leia.txt"), "w") as f:
            f.write("nao e video")
        # O ffprobe do upload de verdade leria o arquivo; aqui ele e um video.
        original = app_module._media_duration_seconds
        app_module._media_duration_seconds = lambda caminho: 1200.0
        try:
            assert "cortando" in list(_volta().values())[0]
        finally:
            app_module._media_duration_seconds = original
        cortando = _candidatos(canal["id"], "processando")
        assert [c["url"] for c in cortando] == ["episodio 1.mp4"]
        # O original fica na pasta: e da pessoa.
        assert os.path.exists(video)
        origem = licencas.ler_origem(str(ambiente["saida"] / cortando[0]["job_id"]))
        assert origem["license"] == "autorizada" and origem["declared_by"] == "pessoa"

    def test_o_mesmo_arquivo_com_outro_nome_e_o_mesmo_video(self, ambiente, tmp_path):
        a = tmp_path / "a.mp4"
        b = tmp_path / "b.mp4"
        a.write_bytes(os.urandom(5000))
        b.write_bytes(a.read_bytes())
        assert automacao.chave_do_arquivo(str(a)) == automacao.chave_do_arquivo(str(b))

    def test_nome_de_arquivo_nao_sai_da_pasta(self, ambiente):
        assert automacao.caminho_do_arquivo("canal", "../../segredo.txt") is None
        assert automacao.caminho_do_arquivo("../fora", "a.mp4") is None


# --------------------------------------------------------------------------- #
# A caixa de entrada
# --------------------------------------------------------------------------- #

class TestCaixaDeEntrada:

    def test_escolher_passa_na_frente(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}}, ativa=False)
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa"), _video("bbbbbbbbbbb")]})
        _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        segundo = next(c for c in _candidatos(canal["id"]) if c["key"] == "youtube:bbbbbbbbbbb")
        r = _chama("POST", f"/api/candidatos/{segundo['id']}", {"acao": "escolher"})
        assert r.status_code == 200 and r.json()["status"] == "escolhido"
        _receita(canal["id"], {}, ativa=True)
        _volta()
        assert _candidatos(canal["id"], "processando")[0]["key"] == "youtube:bbbbbbbbbbb"

    def test_recusar_e_voltar(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}}, ativa=False)
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        c = _candidatos(canal["id"])[0]
        assert _chama("POST", f"/api/candidatos/{c['id']}", {"acao": "recusar"}).json()["status"] == "recusado"
        assert _chama("POST", f"/api/candidatos/{c['id']}", {"acao": "voltar"}).json()["status"] == "novo"
        assert _chama("POST", f"/api/candidatos/{c['id']}", {"acao": "sumir"}).status_code == 400

    def test_licenca_nao_conferida_nao_passa_na_busca(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}}, ativa=False)
        busca["respostas"].append({"candidatos": [], "recusados": [
            {**_video("aaaaaaaaaaa", license="desconhecida"), "motivo": "sem licenca"}]})
        _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        c = _candidatos(canal["id"])[0]
        r = _chama("POST", f"/api/candidatos/{c['id']}", {"acao": "escolher"})
        assert r.status_code == 400 and "licença" in r.json()["detail"]

    def test_o_credito_aparece_na_caixa(self, ambiente, busca):
        canal = _canal()
        _receita(canal["id"], {"fonte": {"tema": "desenho"}}, ativa=False)
        busca["respostas"].append({"candidatos": [_video("aaaaaaaaaaa")]})
        _chama("POST", f"/api/canais/{canal['id']}/receita/buscar")
        assert _candidatos(canal["id"])[0]["credito"].startswith("Créditos:")


# --------------------------------------------------------------------------- #
# O que o /api/process ganhou
# --------------------------------------------------------------------------- #

class TestProcessComOrigem:

    def test_a_pagina_do_video_da_a_origem(self, ambiente):
        url = "https://www.youtube.com/watch?v=ccccccccccc"
        ambiente["probes"][url] = {"max_height": 1080, "duration": 1800, "origem": {
            "url": url, "title": "Da pagina", "author": "Canal",
            "license": "Creative Commons Attribution license (reuse allowed)",
            "license_text": "Creative Commons Attribution license (reuse allowed)",
            "published_at": "20250901"}}
        r = _chama("POST", "/api/process", {"url": url, "acknowledged": True})
        job_id = r.json()["job_id"]
        origem = licencas.ler_origem(str(ambiente["saida"] / job_id))
        assert origem["license"] == "cc-by" and origem["found_by"] == "manual"
        assert origem["title"] == "Da pagina"

        async def _t():
            async with db.tenant() as t:
                return await t.all(db_models.SourceLicense)
        linhas = corre(_t)
        assert [l.key for l in linhas] == ["youtube:ccccccccccc"]
        assert linhas[0].license == "cc-by"

    def test_origem_torta_e_400(self, ambiente):
        r = _chama("POST", "/api/process", {"url": "https://youtu.be/ccccccccccc",
                                            "acknowledged": True, "origem": "nao e json"})
        assert r.status_code == 400

    def test_o_template_vai_para_a_pasta_do_job(self, ambiente):
        salvo = _chama("POST", "/api/templates", {"name": "Meu estilo", "spec": {
            "captions": {"preset": "karaoke_fill", "color": "#FF0000"}}}).json()
        tid = salvo.get("id") or salvo["template"]["id"]
        r = _chama("POST", "/api/process", {"url": "https://youtu.be/ccccccccccc",
                                            "acknowledged": True, "template_id": tid})
        job_id = r.json()["job_id"]
        caminho = app_module.jobs[job_id]["env"]["CAPTION_TEMPLATE_FILE"]
        import template
        kwargs = template.kwargs_do_arquivo(caminho)
        assert kwargs["font_color"] == "#FF0000" and "margin_v" in kwargs
        assert _chama("POST", "/api/process", {"url": "https://youtu.be/ddddddddddd",
                                               "acknowledged": True,
                                               "template_id": str(uuid.uuid4())}).status_code == 400

    def test_template_torto_nao_custa_a_legenda(self, tmp_path, capsys):
        import template
        (tmp_path / "t.json").write_text("{")
        assert template.kwargs_do_arquivo(str(tmp_path / "t.json")) is None
        assert template.kwargs_do_arquivo(None) is None

    @pytest.mark.parametrize("preset", [None, *sorted(template.PRESETS_DE_LEGENDA)])
    def test_todo_campo_do_arquivo_e_aceito_pelo_generate_ass(self, tmp_path, preset):
        """O `auto_caption_clip` passa o arquivo inteiro ao `generate_ass`
        dentro de um try: um argumento que ele nao conheca seria TypeError
        engolido, e o corte sairia SEM legenda, sem erro nenhum na tela."""
        import inspect

        import subtitles
        spec = template.PADRAO if preset is None else {"captions": {"preset": preset}}
        (tmp_path / "t.json").write_text(json.dumps(spec), encoding="utf-8")
        kwargs = template.kwargs_do_arquivo(str(tmp_path / "t.json"))
        assert kwargs and "margin_v" in kwargs
        aceitos = set(inspect.signature(subtitles.generate_ass).parameters)
        assert set(kwargs) <= aceitos, sorted(set(kwargs) - aceitos)


# --------------------------------------------------------------------------- #
# COPPA
# --------------------------------------------------------------------------- #

class TestFeitoParaCriancas:

    def test_o_projeto_do_canal_infantil_sai_marcado(self, ambiente, busca):
        infantil = _canal()
        financas = _canal(nome="Financas", niche="finanças")
        for canal, esperado in ((infantil, True), (financas, False)):
            job_id = str(uuid.uuid4())
            pasta = ambiente["saida"] / job_id
            pasta.mkdir()
            (pasta / ".canal").write_text(canal["id"])
            assert corre(lambda: app_module._para_criancas(job_id)) is esperado
        solto = str(uuid.uuid4())
        (ambiente["saida"] / solto).mkdir()
        assert corre(lambda: app_module._para_criancas(solto)) is False

    def test_a_conta_do_canal_infantil_marca_o_envio(self, ambiente):
        """Um projeto sem canal publicado na conta do canal infantil e envio
        do canal infantil, e sai marcado. Olhar so o canal do projeto deixaria
        esse passar desmarcado -- o erro caro, o que a lei pune."""
        infantil = _canal(plataformas=("youtube",))
        financas = _canal(nome="Financas", niche="finanças", plataformas=("youtube",))
        conta_infantil = infantil["contas"][0]["id"]
        conta_financas = financas["contas"][0]["id"]
        solto = str(uuid.uuid4())
        (ambiente["saida"] / solto).mkdir()
        assert corre(lambda: app_module._para_criancas(solto, conta_infantil)) is True
        assert corre(lambda: app_module._para_criancas(solto, conta_financas)) is False
        # O projeto do canal infantil continua marcado em qualquer conta:
        # marcar a mais so desliga os comentarios daquele video.
        do_infantil = str(uuid.uuid4())
        (ambiente["saida"] / do_infantil).mkdir()
        (ambiente["saida"] / do_infantil / ".canal").write_text(infantil["id"])
        assert corre(lambda: app_module._para_criancas(do_infantil, conta_financas)) is True

    def test_a_escolha_do_canal_vence_o_nicho(self, ambiente):
        canal = _canal()
        _chama("PATCH", f"/api/canais/{canal['id']}", {"ajustes": {"feito_para_criancas": False}})
        job_id = str(uuid.uuid4())
        pasta = ambiente["saida"] / job_id
        pasta.mkdir()
        (pasta / ".canal").write_text(canal["id"])
        assert corre(lambda: app_module._para_criancas(job_id)) is False


class TestPacoteDoCanalInfantil:

    def test_o_leia_me_lembra_o_feito_para_criancas(self, ambiente):
        import io
        import zipfile
        canal = _canal()
        job_id = str(uuid.uuid4())
        app_module.jobs[job_id] = {"status": "processing", "logs": [],
                                   "tenant_id": db.SELF_HOST_TENANT_ID}

        async def _fonte():
            src = await job_registry.registrar_fonte("upload", "v.mp4")
            await job_registry.registrar_job(job_id, src)
        corre(_fonte)
        _terminar_o_job(ambiente, job_id, cortes=1)
        (ambiente["saida"] / job_id / ".canal").write_text(canal["id"])
        r = _chama("GET", "/api/publicacoes/pacote?plataforma=youtube")
        assert r.status_code == 200, r.text
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            leia = z.read("LEIA-ME.txt").decode("utf-8")
        assert "conteúdo para crianças" in leia
        r = _chama("GET", "/api/publicacoes/pacote?plataforma=tiktok")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert "crianças" not in z.read("LEIA-ME.txt").decode("utf-8")


def test_a_caixa_de_aprovacao_mostra_os_cortes_na_ordem():
    """Projeto mais novo primeiro; dentro dele, corte 1, 2, 3. As aprovacoes
    de um job nascem com microssegundos de diferenca, e ordenar so pela hora
    de criacao punha o corte 4 antes do 1."""
    from types import SimpleNamespace as N

    import automacao

    t0 = datetime(2026, 9, 26, 10, 0, 0)
    cortes = {f"{job}{i}": N(job_id=job, rubric_json={"clip_index": i})
              for job in ("velho", "novo") for i in range(3)}
    aprovacoes = [N(clip_id=f"velho{i}", created_at=t0 + timedelta(microseconds=i))
                  for i in range(3)]
    aprovacoes += [N(clip_id=f"novo{i}", created_at=t0 + timedelta(hours=1, microseconds=i))
                   for i in range(3)]
    ordem = [a.clip_id for a in automacao._na_ordem_da_caixa(aprovacoes, cortes)]
    assert ordem == ["novo0", "novo1", "novo2", "velho0", "velho1", "velho2"]
    # Corte que sumiu do banco nao derruba a caixa.
    sem_corte = [N(clip_id="x", created_at=None)] + aprovacoes
    assert len(automacao._na_ordem_da_caixa(sem_corte, cortes)) == 7
