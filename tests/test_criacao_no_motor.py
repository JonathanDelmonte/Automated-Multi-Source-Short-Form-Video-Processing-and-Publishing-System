"""O video criado por IA no motor (etapa 7.7): o estilo do canal pela API, a
ficha dos personagens, o pedido que vira job e o fim do job no banco.

O `criar_video.py` e coberto por `tests/test_criar_video.py`; aqui ele e
trocado pelo que deixaria na pasta, e a rede das midias por `midia_ia._post`.
"""
import asyncio
import base64
import io
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
import criacoes
import criar_video
import midia_ia


def _png(cor=(250, 250, 250), tamanho=(96, 96)):
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(saida, format="PNG")
    return saida.getvalue()


class Rede:
    def __init__(self):
        self.imagens = 0
        self.vozes = 0

    def __call__(self, url, *, headers, json_body=None, files=None, timeout=180.0):
        if "api.cloudflare.com" in url:
            self.imagens += 1
            return 200, "application/json", json.dumps(
                {"result": {"image": base64.b64encode(_png((10 * self.imagens, 80, 120))).decode()},
                 "success": True}).encode()
        self.vozes += 1
        pcm = b"\x00\x00" * 24000
        return 200, "application/json", json.dumps({"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                            "data": base64.b64encode(pcm).decode()}}]}}]}).encode()


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
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
    for var in ("CLOUDFLARE_IMAGE_NEURONS_DAILY", "GEMINI_TTS_CALLS_DAILY",
                "CLOUDFLARE_IMAGE_MODEL", "GEMINI_TTS_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(midia_ia, "_SUMIRAM", set())
    rede = Rede()
    monkeypatch.setattr(midia_ia, "_post", rede)
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield {"saida": saida, "fila": fila, "rede": rede, "tmp": tmp_path}
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None, **kw):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            if corpo is None and metodo in ("POST", "PUT") and "content" not in kw:
                return await client.request(metodo, url, json={}, **kw)
            return await client.request(metodo, url, json=corpo, **kw)
    return asyncio.run(_do())


def _canal(nome="Historinhas da Lulu", language="pt-BR"):
    r = _chama("POST", "/api/canais", {"name": nome, "niche": "infantil",
                                        "requires_approval": False, "language": language})
    assert r.status_code == 200, r.text
    return r.json()


def _estilo_com_lulu(canal_id, cenas=4):
    r = _chama("PUT", f"/api/canais/{canal_id}/estilo", {"spec": {
        "publico": "criancas de 4 a 8 anos", "cenas": cenas, "duracao_s": 30,
        "visual": {"preset": "aquarela"},
        "personagens": [{"nome": "Lulu", "descricao": "coelhinha branca de laco vermelho"}]}})
    assert r.status_code == 200, r.text
    return r.json()["estilo"]


class TestOEstilo:

    def test_canal_sem_estilo_mostra_o_padrao_e_o_catalogo(self, ambiente):
        canal = _canal()
        r = _chama("GET", f"/api/canais/{canal['id']}/estilo")
        assert r.status_code == 200
        dados = r.json()
        assert dados["estilo"] is None and dados["padrao"]["cenas"] == 8
        assert len(dados["catalogo"]["vozes"]) == 30
        assert "livro-infantil" in dados["catalogo"]["visuais"]
        assert dados["midia"] == {"imagem": True, "voz": True}
        assert "ainda não tem estilo" in dados["pode_criar"]
        assert dados["cota"]["imagens_hoje"] > 0

    def test_salvar_da_id_ao_personagem_e_pede_a_imagem(self, ambiente):
        canal = _canal()
        estilo = _estilo_com_lulu(canal["id"])
        lulu = estilo["spec"]["personagens"][0]
        assert len(lulu["id"]) == 8 and lulu["imagem"] is None
        assert estilo["sem_imagem"] == ["Lulu"]
        r = _chama("GET", f"/api/canais/{canal['id']}/estilo")
        assert "imagem de referência de Lulu" in r.json()["pode_criar"]

    def test_a_semente_nao_muda_quando_o_estilo_e_editado(self, ambiente):
        canal = _canal()
        estilo = _estilo_com_lulu(canal["id"])
        spec = {**estilo["spec"], "semente": 7, "tom": "calmo"}
        r = _chama("PUT", f"/api/canais/{canal['id']}/estilo", {"spec": spec})
        assert r.json()["estilo"]["spec"]["semente"] == estilo["spec"]["semente"]
        assert r.json()["estilo"]["spec"]["tom"] == "calmo"

    def test_estilo_torto_e_400_com_o_campo(self, ambiente):
        canal = _canal()
        r = _chama("PUT", f"/api/canais/{canal['id']}/estilo",
                   {"spec": {"voz": {"nome": "Inventada"}}})
        assert r.status_code == 400 and "voz.nome" in r.json()["detail"]

    def test_canal_que_nao_existe_e_404(self, ambiente):
        outro = str(uuid.uuid4())
        assert _chama("GET", f"/api/canais/{outro}/estilo").status_code == 404
        r = _chama("PUT", f"/api/canais/{outro}/estilo", {"spec": {}})
        assert r.status_code == 400 and "canal nao existe" in r.json()["detail"]


class TestOPersonagem:

    def test_gerar_a_ficha_guarda_a_imagem_e_libera_a_criacao(self, ambiente):
        canal = _canal()
        estilo = _estilo_com_lulu(canal["id"])
        lulu = estilo["spec"]["personagens"][0]
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{lulu['id']}/gerar")
        assert r.status_code == 200, r.text
        dados = r.json()
        assert dados["estilo"]["imagens"][lulu["id"]].startswith("data:image/jpeg;base64,")
        assert dados["pode_criar"] is None and ambiente["rede"].imagens == 1
        pasta = ambiente["tmp"] / "dados" / "estilos" / estilo["id"]
        primeira = sorted(os.listdir(pasta))
        # Gerar de novo troca a imagem e apaga a anterior.
        _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{lulu['id']}/gerar")
        segunda = sorted(os.listdir(pasta))
        assert len(primeira) == len(segunda) == 1 and primeira != segunda

    def test_personagem_sem_descricao_nao_gasta_a_cota(self, ambiente):
        canal = _canal()
        r = _chama("PUT", f"/api/canais/{canal['id']}/estilo",
                   {"spec": {"personagens": [{"nome": "Bento"}]}})
        pid = r.json()["estilo"]["spec"]["personagens"][0]["id"]
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        assert r.status_code == 400 and "descreva como Bento" in r.json()["detail"]
        assert ambiente["rede"].imagens == 0

    def test_sem_a_chave_da_cloudflare_diz_onde_por(self, ambiente, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
        canal = _canal()
        pid = _estilo_com_lulu(canal["id"])["spec"]["personagens"][0]["id"]
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        assert r.status_code == 400 and "Cloudflare" in r.json()["detail"]

    def test_enviar_a_imagem_do_personagem(self, ambiente):
        canal = _canal()
        pid = _estilo_com_lulu(canal["id"])["spec"]["personagens"][0]["id"]
        url = f"/api/canais/{canal['id']}/estilo/personagens/{pid}/imagem"
        data_url = "data:image/png;base64," + base64.b64encode(_png(tamanho=(2000, 1000))).decode()
        r = _chama("POST", url, {"imagem": data_url})
        assert r.status_code == 200, r.text
        assert r.json()["estilo"]["sem_imagem"] == []
        assert _chama("POST", url, {"imagem": "data:image/svg+xml;base64,PHN2Zz4="}).status_code == 400
        assert _chama("POST", url, {"imagem": "data:image/png;base64,bmFvIGUgaW1hZ2Vt"}).status_code == 400
        # Multipart (ou sem tipo) e recusado: pedido de outra origem passaria sem preflight.
        r = _chama("POST", url, content=b"x", headers={"content-type": "text/plain"})
        assert r.status_code == 415


class TestAVoz:

    def test_a_amostra_fica_guardada(self, ambiente):
        canal = _canal()
        corpo = {"voz": "Sulafat", "instrucao": "como uma avo carinhosa"}
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/ouvir", corpo)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        assert r.content[:4] == b"RIFF"
        _chama("POST", f"/api/canais/{canal['id']}/estilo/ouvir", corpo)
        assert ambiente["rede"].vozes == 1
        r = _chama("POST", f"/api/canais/{canal['id']}/estilo/ouvir", {"voz": "Inventada"})
        assert r.status_code == 400


class TestCriar:

    def _pronto(self, ambiente, cenas=4):
        canal = _canal()
        estilo = _estilo_com_lulu(canal["id"], cenas=cenas)
        pid = estilo["spec"]["personagens"][0]["id"]
        _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        return canal, estilo, pid

    def test_o_pedido_vira_um_job_na_fila(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        r = _chama("POST", "/api/criacoes", {"channel_id": canal["id"],
                                             "ideia": "a Lulu aprende a dividir"})
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert ambiente["fila"] == [job_id]
        pasta = ambiente["saida"] / job_id
        pedido = json.loads((pasta / "criacao.json").read_text(encoding="utf-8"))
        assert pedido["ideia"] == "a Lulu aprende a dividir" and pedido["idioma"] == "pt-BR"
        assert pedido["estilo"]["personagens"][0]["id"] == pid
        assert (pasta / pedido["referencias"][pid]).is_file()
        assert (pasta / ".canal").read_text().strip() == canal["id"]
        job = app_module.jobs[job_id]
        assert job["cmd"][-3:] == ["criar_video.py", "--pasta", str(pasta)]
        assert job["kind"] == "criacao" and job["channel_id"] == canal["id"]
        manifesto = json.loads((pasta / app_module._RESUME_FILE).read_text())
        assert manifesto["cmd"] == job["cmd"]

        async def _banco():
            async with db.tenant() as t:
                linhas = await t.all(db_models.Creation)
                fontes = await t.all(db_models.Source)
                return linhas, fontes
        linhas, fontes = asyncio.run(_banco())
        assert [(l.job_id, l.idea) for l in linhas] == [(job_id, "a Lulu aprende a dividir")]
        assert [f.adapter for f in fontes] == ["ia"]

        lista = _chama("GET", f"/api/jobs?canal={canal['id']}").json()["jobs"]
        assert lista[0]["title"] == "a Lulu aprende a dividir"
        assert lista[0]["criacao"] == {"ideia": "a Lulu aprende a dividir"}
        assert lista[0]["stage_total"] == len(app_module.CRIACAO_STAGES)

    def test_editar_o_estilo_depois_nao_muda_o_video_em_andamento(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]}).json()["job_id"]
        copia = ambiente["saida"] / job_id / "referencias" / f"{pid}.png"
        antes = copia.read_bytes()
        _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        assert copia.read_bytes() == antes

    @pytest.mark.parametrize("caso,trecho", [
        ("sem_estilo", "ainda não tem estilo"),
        ("sem_imagem", "imagem de referência de Lulu"),
        ("sem_voz", "chave do Gemini"),
        ("sem_cota", "só dá para 1 imagem(ns), e o vídeo tem 4 cenas"),
    ])
    def test_o_que_impede_criar_vem_antes_do_job(self, ambiente, monkeypatch, caso, trecho):
        canal = _canal()
        if caso != "sem_estilo":
            estilo = _estilo_com_lulu(canal["id"])
            if caso != "sem_imagem":
                pid = estilo["spec"]["personagens"][0]["id"]
                _chama("POST", f"/api/canais/{canal['id']}/estilo/personagens/{pid}/gerar")
        if caso == "sem_voz":
            monkeypatch.delenv("GEMINI_API_KEY")
        if caso == "sem_cota":
            monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "260")
        r = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]})
        assert r.status_code == 400 and trecho in r.json()["detail"], r.text
        # Nenhuma pasta de projeto (o `.midia_budget.json` e a conta da cota).
        assert ambiente["fila"] == []
        assert [n for n in os.listdir(ambiente["saida"]) if not n.startswith(".")] == []

    def test_sem_canal_e_400(self, ambiente):
        r = _chama("POST", "/api/criacoes", {"ideia": "x"})
        assert r.status_code == 400 and "Escolha o canal" in r.json()["detail"]

    def test_o_fim_do_job_grava_o_titulo_e_o_proximo_nao_repete(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]}).json()["job_id"]
        pasta = ambiente["saida"] / job_id
        roteiro = {"titulo": "A Lulu e a cenoura gigante", "descricao": "d", "hashtags": [],
                   "cenas": [{"fala": "Era uma vez.", "imagem": "x", "personagens": [pid]}]}
        (pasta / "roteiro.json").write_text(json.dumps(roteiro), encoding="utf-8")
        (pasta / "criacao_clip_1.mp4").write_bytes(b"\x00" * 64)
        (pasta / "criacao_metadata.json").write_text(json.dumps({"shorts": [{
            "start": 0, "end": 1.0, "video_title_for_youtube_short": roteiro["titulo"]}],
            "transcript": {"language": "pt", "segments": []}}))
        job = app_module.jobs[job_id]
        job["status"] = "completed"
        job["result"] = {"clips": [{"start": 0, "end": 1.0, "clip_index": 0,
                                    "video_title_for_youtube_short": roteiro["titulo"],
                                    "video_url": f"/videos/{job_id}/criacao_clip_1.mp4"}]}
        asyncio.run(app_module._fechar_job_no_banco(job_id))
        temas = asyncio.run(criacoes.temas_do_canal(canal["id"]))
        assert temas == ["A Lulu e a cenoura gigante"]
        segundo = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]}).json()["job_id"]
        pedido = json.loads((ambiente["saida"] / segundo / "criacao.json").read_text(encoding="utf-8"))
        assert "A Lulu e a cenoura gigante" in pedido["ja_feitos"]

    def test_continuar_uma_criacao_que_parou(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]}).json()["job_id"]
        assert _chama("POST", f"/api/criacoes/{job_id}/continuar").status_code == 409  # na fila
        app_module.jobs[job_id]["status"] = "failed"
        r = _chama("POST", f"/api/criacoes/{job_id}/continuar")
        assert r.status_code == 200, r.text
        assert ambiente["fila"] == [job_id, job_id]
        assert app_module.jobs[job_id]["status"] == "queued"
        # Pronto nao continua; o que nao e criacao nao existe para esta rota.
        app_module.jobs[job_id]["status"] = "completed"
        (ambiente["saida"] / job_id / "criacao_metadata.json").write_text("{}")
        assert _chama("POST", f"/api/criacoes/{job_id}/continuar").status_code == 409
        assert _chama("POST", f"/api/criacoes/{uuid.uuid4()}/continuar").status_code == 404


    def test_a_criacao_parada_continua_depois_de_um_reinicio(self, ambiente, monkeypatch):
        """Um video de IA que parou nao tem metadata: sem o registro de disco,
        ele sumia da lista depois de um reinicio e a tela dizia "nao existe
        mais" -- justo o projeto que so precisa de "continuar"."""
        canal, estilo, pid = self._pronto(ambiente)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"],
                                                  "ideia": "a Lulu e a chuva"}).json()["job_id"]
        (ambiente["saida"] / job_id / app_module._RESUME_FILE).unlink()   # o job falhou
        monkeypatch.setattr(app_module, "jobs", {})                        # e o motor reiniciou
        lista = _chama("GET", "/api/jobs").json()["jobs"]
        assert [(j["job_id"], j["status"], j["title"]) for j in lista] == \
            [(job_id, "failed", "a Lulu e a chuva")]
        status = _chama("GET", f"/api/status/{job_id}").json()
        assert status["status"] == "failed" and status["criacao"]["ideia"] == "a Lulu e a chuva"
        assert "continuar de onde parou" in status["logs"][-1]
        assert _chama("POST", f"/api/criacoes/{job_id}/continuar").status_code == 200
        assert app_module.jobs[job_id]["status"] == "queued"

    def test_continuar_espera_a_cota_das_imagens_que_faltam(self, ambiente, monkeypatch):
        canal, estilo, pid = self._pronto(ambiente, cenas=4)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"]}).json()["job_id"]
        pasta = ambiente["saida"] / job_id
        roteiro = {"titulo": "t", "descricao": "", "hashtags": [], "cenas": [
            {"fala": f"fala {i}", "imagem": "x", "personagens": []} for i in range(4)]}
        (pasta / "roteiro.json").write_text(json.dumps(roteiro), encoding="utf-8")
        for i in (1, 2, 3):
            (pasta / f"cena_0{i}.png").write_bytes(_png())
        app_module.jobs[job_id]["status"] = "failed"
        monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "1")
        r = _chama("POST", f"/api/criacoes/{job_id}/continuar")
        assert r.status_code == 400 and "faltam 1" in r.json()["detail"]
        monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "8000")
        assert _chama("POST", f"/api/criacoes/{job_id}/continuar").status_code == 200


class TestABarra:

    def test_os_estagios_sao_os_do_criar_video(self):
        assert tuple(n for n, _ in app_module.CRIACAO_STAGES) == criar_video.ESTAGIOS

    def test_a_barra_da_criacao(self):
        vista = app_module._stage_view({"stage": "c3_voz"})
        assert vista == {"stage": "c3_voz", "stage_label": "gravando a narração",
                         "stage_index": 3, "stage_total": 5}
        assert app_module._stage_view({"stage": "04_detect"})["stage_label"] == \
            "escolhendo os melhores momentos"

    def test_o_motor_diz_que_sabe_criar(self, ambiente):
        assert _chama("GET", "/api/config").json()["criacao"] is True


class TestOEpisodio:
    """O episodio longo (7.8): o mesmo `/api/criacoes`, com `formato: longo`."""

    _pronto = TestCriar._pronto

    def _pedido(self, ambiente, job_id):
        return json.loads((ambiente["saida"] / job_id / "criacao.json").read_text(encoding="utf-8"))

    def test_o_episodio_vira_um_job_com_a_duracao_e_as_cenas(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        r = _chama("POST", "/api/criacoes", {"channel_id": canal["id"], "formato": "longo",
                                             "duracao_min": 3, "ideia": "a Lulu no mar"})
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        assert "episodio" not in r.json()                  # avulso: sem numero
        pedido = self._pedido(ambiente, job_id)
        assert (pedido["formato"], pedido["duracao_s"], pedido["cenas"]) == ("longo", 180, 12)
        assert pedido["historia"] is None
        assert app_module.jobs[job_id]["kind"] == "criacao"
        assert "Episódio na fila: 3 minutos, 12 cenas" in app_module.jobs[job_id]["logs"][0]
        lista = _chama("GET", "/api/jobs").json()["jobs"]
        assert lista[0]["criacao"]["formato"] == "longo" and lista[0]["title"] == "a Lulu no mar"

    @pytest.mark.parametrize("corpo,trecho", [
        ({"duracao_min": 1}, "de 2 a 10 minutos"),
        ({"duracao_min": 11}, "de 2 a 10 minutos"),
        ({"duracao_min": "x"}, "quantos minutos"),
        ({}, "quantos minutos"),
        ({"duracao_min": 3, "historia": "x" * 81}, "no máximo 80"),
        ({"duracao_min": 3, "formato": "enorme"}, "curto ou longo"),
    ])
    def test_o_pedido_torto_do_episodio_e_400(self, ambiente, corpo, trecho):
        canal, estilo, pid = self._pronto(ambiente)
        r = _chama("POST", "/api/criacoes", {"channel_id": canal["id"], "formato": "longo",
                                             **corpo})
        assert r.status_code == 400 and trecho in r.json()["detail"], r.text
        assert ambiente["fila"] == []

    def _terminar(self, ambiente, job_id, titulo, resumo, historia, episodio):
        """O que o `criar_video.py` deixaria na pasta, e o fim do job no banco."""
        pasta = ambiente["saida"] / job_id
        roteiro = {"titulo": titulo, "descricao": "d", "hashtags": [], "resumo": resumo,
                   "formato": "longo", "historia": historia, "episodio": episodio,
                   "capitulos": [], "cenas": [{"fala": "Era uma vez.", "imagem": "x",
                                               "personagens": []}]}
        (pasta / "roteiro.json").write_text(json.dumps(roteiro), encoding="utf-8")
        (pasta / "criacao_clip_1.mp4").write_bytes(b"\x00" * 64)
        (pasta / "criacao_metadata.json").write_text(json.dumps({"shorts": [{
            "start": 0, "end": 1.0, "video_title_for_youtube_short": titulo,
            "formato": "longo"}], "transcript": {"language": "pt", "segments": []}}))
        job = app_module.jobs[job_id]
        job["status"] = "completed"
        job["result"] = {"clips": [{"start": 0, "end": 1.0, "clip_index": 0,
                                    "video_title_for_youtube_short": titulo,
                                    "video_url": f"/videos/{job_id}/criacao_clip_1.mp4"}]}
        asyncio.run(app_module._fechar_job_no_banco(job_id))

    def test_a_historia_numera_os_episodios_e_espera_o_anterior(self, ambiente):
        canal, estilo, pid = self._pronto(ambiente)
        base = {"channel_id": canal["id"], "formato": "longo", "duracao_min": 2}
        r = _chama("POST", "/api/criacoes", {**base, "historia": "A  Lulu na floresta"})
        assert r.status_code == 200 and r.json()["episodio"] == 1
        primeiro = r.json()["job_id"]
        assert self._pedido(ambiente, primeiro)["historia"] == \
            {"nome": "A Lulu na floresta", "episodio": 1, "anteriores": []}
        assert "Episódio 1 de “A Lulu na floresta” na fila" in \
            app_module.jobs[primeiro]["logs"][0]

        # O segundo nao sai antes de o primeiro terminar: ele continua do resumo.
        r = _chama("POST", "/api/criacoes", {**base, "historia": "a lulu na FLORESTA"})
        assert r.status_code == 400 and "O episódio 1 de “A Lulu na floresta” ainda não" in \
            r.json()["detail"]

        self._terminar(ambiente, primeiro, "A chegada", "A Lulu chegou e fez um amigo.",
                       "A Lulu na floresta", 1)
        r = _chama("POST", "/api/criacoes", {**base, "historia": "a lulu na FLORESTA"})
        assert r.status_code == 200 and r.json()["episodio"] == 2
        segundo = r.json()["job_id"]
        # A grafia fica a da historia; os anteriores vao com titulo e resumo.
        assert self._pedido(ambiente, segundo)["historia"] == {
            "nome": "A Lulu na floresta", "episodio": 2,
            "anteriores": [{"episodio": 1, "titulo": "A chegada",
                            "resumo": "A Lulu chegou e fez um amigo."}]}
        historias = _chama("GET", f"/api/canais/{canal['id']}/historias").json()["historias"]
        assert historias == [{"nome": "A Lulu na floresta", "episodios": 2,
                              "ultimo": {"episodio": 2, "job_id": segundo, "titulo": "",
                                         "pronto": False}}]
        # Sem ideia, a lista chama o episodio pela historia e pelo numero.
        lista = {j["job_id"]: j for j in _chama("GET", "/api/jobs").json()["jobs"]}
        assert lista[segundo]["title"] == "A Lulu na floresta - Episódio 2"
        # Outra historia no mesmo canal comeca do 1, sem esperar ninguem.
        r = _chama("POST", "/api/criacoes", {**base, "historia": "O Bento no mar"})
        assert r.status_code == 200 and r.json()["episodio"] == 1

    def test_apagar_o_episodio_parado_destrava_a_historia(self, ambiente):
        """A tela manda "continue (ou apague) esse episodio": apagar o projeto
        leva a linha de `creations` junto (o CASCADE da FK composta com
        `jobs`), e a historia volta a aceitar o proximo -- com o numero do que
        sobrou, e nao pulando o apagado."""
        canal, estilo, pid = self._pronto(ambiente)
        base = {"channel_id": canal["id"], "formato": "longo", "duracao_min": 2,
                "historia": "A Lulu na floresta"}
        primeiro = _chama("POST", "/api/criacoes", base).json()["job_id"]
        self._terminar(ambiente, primeiro, "A chegada", "Resumo.", "A Lulu na floresta", 1)
        parado = _chama("POST", "/api/criacoes", base).json()["job_id"]
        assert _chama("POST", "/api/criacoes", base).status_code == 400

        r = _chama("DELETE", f"/api/jobs/{parado}")
        assert r.status_code == 200, r.text
        r = _chama("POST", "/api/criacoes", base)
        assert r.status_code == 200, r.text
        assert r.json()["episodio"] == 2

    def test_a_cota_do_episodio_conta_as_cenas_da_duracao(self, ambiente, monkeypatch):
        canal, estilo, pid = self._pronto(ambiente)
        # A ficha da Lulu ja gastou uma imagem; sobram umas 10.
        monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "1250")
        base = {"channel_id": canal["id"], "formato": "longo"}
        r = _chama("POST", "/api/criacoes", {**base, "duracao_min": 3})
        assert r.status_code == 400 and "o vídeo tem 12 cenas" in r.json()["detail"]
        assert _chama("POST", "/api/criacoes", {**base, "duracao_min": 2}).status_code == 200

    def test_o_teto_de_voz_conta_os_blocos_do_episodio(self, ambiente, monkeypatch):
        canal, estilo, pid = self._pronto(ambiente)
        monkeypatch.setenv("GEMINI_TTS_CALLS_DAILY", "2")
        base = {"channel_id": canal["id"], "formato": "longo"}
        r = _chama("POST", "/api/criacoes", {**base, "duracao_min": 10})
        assert r.status_code == 400 and "precisa de 4 chamadas de voz" in r.json()["detail"]
        assert _chama("POST", "/api/criacoes", {**base, "duracao_min": 2}).status_code == 200

    def test_continuar_o_episodio_conta_os_blocos_que_faltam(self, ambiente, monkeypatch):
        canal, estilo, pid = self._pronto(ambiente)
        job_id = _chama("POST", "/api/criacoes", {"channel_id": canal["id"], "formato": "longo",
                                                  "duracao_min": 2}).json()["job_id"]
        pasta = ambiente["saida"] / job_id
        roteiro = {"titulo": "t", "descricao": "", "hashtags": [], "cenas": [
            {"fala": "x" * 1500, "imagem": "x", "personagens": []} for _ in range(8)]}
        (pasta / "roteiro.json").write_text(json.dumps(roteiro), encoding="utf-8")
        for i in range(1, 9):
            (pasta / f"cena_{i:02d}.png").write_bytes(_png())
        # 8 cenas de 1500 caracteres: 8 blocos; os dois primeiros ja estao na pasta.
        for k in (1, 2):
            (pasta / f"narracao_bloco_{k:02d}.wav").write_bytes(b"\x00" * 100)
        app_module.jobs[job_id]["status"] = "failed"
        monkeypatch.setenv("GEMINI_TTS_CALLS_DAILY", "5")
        r = _chama("POST", f"/api/criacoes/{job_id}/continuar")
        assert r.status_code == 400 and "Faltam 6 chamadas de voz" in r.json()["detail"]
        monkeypatch.setenv("GEMINI_TTS_CALLS_DAILY", "6")
        assert _chama("POST", f"/api/criacoes/{job_id}/continuar").status_code == 200

    def test_a_tela_sabe_do_episodio_antes_do_clique(self, ambiente, monkeypatch):
        canal, estilo, pid = self._pronto(ambiente)
        dados = _chama("GET", f"/api/canais/{canal['id']}/estilo").json()
        assert dados["catalogo"]["episodio"] == {"duracao_s": [120, 600], "segundos_por_cena": 15,
                                                 "cenas": [8, 40]}
        assert dados["pode_criar_episodio"] is None
        # A cota do episodio e conferida pela duracao, na tela: aqui nao.
        monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "300")
        dados = _chama("GET", f"/api/canais/{canal['id']}/estilo").json()
        assert dados["pode_criar"] and dados["pode_criar_episodio"] is None
        assert _chama("GET", "/api/config").json()["video_longo"] is True
