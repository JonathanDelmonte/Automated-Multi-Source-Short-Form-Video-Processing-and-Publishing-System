"""A compilacao dos cortes no motor (etapa 7.8): o pedido que vira job, os
trechos resolvidos (a origem deitada, ou o corte vertical), o credito das
fontes, a barra e a retomada.

O `compilar_video.py` e coberto por `tests/test_compilacao.py`; aqui a pasta de
cada projeto e montada a mao, como o pipeline a deixaria.
"""
import asyncio
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")
import compilacao


@pytest.fixture()
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "UPLOAD_DIR", str(uploads))
    monkeypatch.setattr(app_module, "jobs", {})
    fila = []
    monkeypatch.setattr(app_module, "_enqueue_job", lambda job_id, priority=2: fila.append(job_id))
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield {"saida": saida, "uploads": uploads, "fila": fila}
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo if corpo is not None else {})
    return asyncio.run(_do())


PALAVRAS = [{"word": " ola", "start": 10.2, "end": 10.6},
            {"word": " mundo", "start": 10.7, "end": 11.2},
            {"word": " depois", "start": 40.0, "end": 40.5}]


def _projeto(ambiente, com_origem=True, origem_cc=False, cortes=None):
    """Um projeto de cortes pronto, como o pipeline deixa: o metadata com a
    transcricao, os cortes limpos e, com `com_origem`, o video baixado."""
    job_id = str(uuid.uuid4())
    pasta = ambiente["saida"] / job_id
    pasta.mkdir()
    cortes = cortes or [(10.0, 25.0, "O começo"), (40.0, 70.0, "A virada")]
    data = {"transcript": {"language": "pt", "segments": [{"start": 10.2, "end": 40.5,
                                                          "words": PALAVRAS}]},
            "shorts": [{"start": a, "end": b, "video_title_for_youtube_short": t}
                       for a, b, t in cortes]}
    if com_origem:
        (pasta / "fonte.mp4").write_bytes(b"\x00" * 64)
        data["source_video"] = "fonte.mp4"
    (pasta / "v_metadata.json").write_text(json.dumps(data), encoding="utf-8")
    for i in range(len(cortes)):
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    if origem_cc:
        (pasta / ".origem.json").write_text(json.dumps({
            "url": "https://www.youtube.com/watch?v=abcdefghijk", "license": "cc-by",
            "title": "Palestra", "author": "Fulana", "published_at": "2025-09-01",
            "idioma": "pt-BR"}), encoding="utf-8")
    return job_id


def _pedido(ambiente, job_id):
    return json.loads((ambiente["saida"] / job_id / "compilacao.json").read_text(encoding="utf-8"))


def test_a_compilacao_vira_um_job_com_os_trechos_resolvidos(ambiente):
    com_origem = _projeto(ambiente, origem_cc=True)
    sem_origem = _projeto(ambiente, com_origem=False)
    r = _chama("POST", "/api/compilacoes", {
        "titulo": "  Os melhores   da semana ", "descricao": "Seleção.",
        "cortes": [{"job_id": com_origem, "clip": 1}, {"job_id": sem_origem, "clip": 0},
                   {"job_id": com_origem, "clip": 0}]})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    assert r.json()["duracao_s"] == 30 + 15 + 15
    assert ambiente["fila"] == [job_id]
    pedido = _pedido(ambiente, job_id)
    assert pedido["titulo"] == "Os melhores da semana" and pedido["legenda"] == "limpo"
    a, b, c = pedido["trechos"]
    # Da origem deitada, no tempo da origem, na ordem pedida.
    assert a["arquivo"] == str(ambiente["saida"] / com_origem / "fonte.mp4")
    assert (a["corte_inicio"], a["corte_fim"], a["vertical"]) == (40.0, 70.0, False)
    assert a["titulo"] == "A virada"
    assert a["palavras"] == [{"word": " depois", "start": 0.0, "end": 0.5}]
    # Sem a origem: o corte vertical limpo, do comeco ao fim dele.
    assert b["arquivo"] == str(ambiente["saida"] / sem_origem / "v_clip_1.mp4")
    assert (b["corte_inicio"], b["corte_fim"], b["vertical"]) == (0.0, 15.0, True)
    assert [w["word"] for w in b["palavras"]] == [" ola", " mundo"]
    assert b["palavras"][0]["start"] == pytest.approx(0.2)
    # O credito da fonte Creative Commons vai junto, uma vez por fonte.
    assert len(pedido["creditos"]) == 1 and "Fulana" in pedido["creditos"][0]
    job = app_module.jobs[job_id]
    assert job["kind"] == "compilacao"
    assert job["cmd"][-3:] == ["compilar_video.py", "--pasta", str(ambiente["saida"] / job_id)]
    assert "3 cortes de 2 projeto(s), 1:00 de vídeo" in job["logs"][0]
    manifesto = json.loads((ambiente["saida"] / job_id / app_module._RESUME_FILE).read_text())
    assert manifesto["cmd"] == job["cmd"]

    lista = {j["job_id"]: j for j in _chama("GET", "/api/jobs").json()["jobs"]}
    assert lista[job_id]["title"] == "Os melhores da semana"
    assert lista[job_id]["compilacao"] == {"titulo": "Os melhores da semana", "trechos": 3,
                                          "projetos": 2, "duracao_s": 60.0}
    assert lista[job_id]["stage_total"] == len(app_module.COMPILACAO_STAGES)


def test_o_upload_guardado_tambem_e_origem(ambiente):
    job_id = _projeto(ambiente, com_origem=False)
    (ambiente["uploads"] / f"{job_id}_meu_video.mp4").write_bytes(b"\x00" * 64)
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": [
        {"job_id": job_id, "clip": 0}, {"job_id": job_id, "clip": 1}]})
    assert r.status_code == 200, r.text
    trecho = _pedido(ambiente, r.json()["job_id"])["trechos"][0]
    assert trecho["arquivo"].endswith("_meu_video.mp4") and trecho["vertical"] is False


@pytest.mark.parametrize("corpo,trecho", [
    ({"cortes": "x"}, "Dê um título"),
    ({"titulo": "x" * 101}, "no máximo 100"),
    ({"titulo": "T", "descricao": "x" * 1501}, "no máximo 1500"),
    ({"titulo": "T", "legenda": "neon"}, "legenda: uma de"),
    ({"titulo": "T"}, "Escolha os cortes"),
    ({"titulo": "T", "cortes": [{"job_id": "nao-e-id", "clip": 0}] * 2}, "{job_id, clip}"),
])
def test_o_pedido_torto_e_400(ambiente, corpo, trecho):
    r = _chama("POST", "/api/compilacoes", corpo)
    assert r.status_code == 400 and trecho in r.json()["detail"], r.text
    assert ambiente["fila"] == []


def test_cada_corte_ruim_diz_qual_e_por_que(ambiente):
    job_id = _projeto(ambiente, com_origem=False)
    um = [{"job_id": job_id, "clip": 0}]
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": um})
    assert r.status_code == 400 and "pelo menos 2" in r.json()["detail"]
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": um + [
        {"job_id": job_id, "clip": 7}]})
    assert r.status_code == 400 and "O corte 8 não existe" in r.json()["detail"]
    os.remove(ambiente["saida"] / job_id / "v_clip_2.mp4")
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": um + [
        {"job_id": job_id, "clip": 1}]})
    assert r.status_code == 400 and "“A virada”) não tem mais o vídeo" in r.json()["detail"]
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": um + [
        {"job_id": str(uuid.uuid4()), "clip": 0}]})
    assert r.status_code == 404
    # Um video longo (episodio ou outra compilacao) nao entra.
    longo = _projeto(ambiente)
    meta = ambiente["saida"] / longo / "v_metadata.json"
    data = json.loads(meta.read_text(encoding="utf-8"))
    data["shorts"][0]["formato"] = "longo"
    meta.write_text(json.dumps(data), encoding="utf-8")
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": um + [
        {"job_id": longo, "clip": 0}]})
    assert r.status_code == 400 and "já é um vídeo longo" in r.json()["detail"]
    assert ambiente["fila"] == []


def test_a_compilacao_no_canal(ambiente):
    canal = _chama("POST", "/api/canais", {"name": "Cortes da Fulana", "niche": "podcast",
                                           "requires_approval": False,
                                           "language": "en"}).json()
    job_id = _projeto(ambiente)
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "channel_id": canal["id"], "cortes": [
        {"job_id": job_id, "clip": 0}, {"job_id": job_id, "clip": 1}]})
    assert r.status_code == 200, r.text
    novo = r.json()["job_id"]
    assert (ambiente["saida"] / novo / ".canal").read_text().strip() == canal["id"]
    assert _pedido(ambiente, novo)["idioma"] == "en"
    r = _chama("POST", "/api/compilacoes", {"titulo": "T", "channel_id": str(uuid.uuid4()),
                                            "cortes": [{"job_id": job_id, "clip": 0}] * 2})
    assert r.status_code == 404


def test_a_barra_da_compilacao(ambiente):
    assert tuple(n for n, _ in app_module.COMPILACAO_STAGES) == compilacao.ESTAGIOS
    vista = app_module._stage_view({"stage": "k3_montagem"})
    assert vista == {"stage": "k3_montagem", "stage_label": "montando o vídeo",
                     "stage_index": 3, "stage_total": 3}
    assert app_module._stage_view({"kind": "compilacao"})["stage_total"] == 3


def test_a_compilacao_parada_e_montada_de_novo(ambiente, monkeypatch):
    job_id = _projeto(ambiente)
    novo = _chama("POST", "/api/compilacoes", {"titulo": "Semana", "cortes": [
        {"job_id": job_id, "clip": 0}, {"job_id": job_id, "clip": 1}]}).json()["job_id"]
    assert _chama("POST", f"/api/compilacoes/{novo}/refazer").status_code == 409   # na fila
    (ambiente["saida"] / novo / app_module._RESUME_FILE).unlink()     # falhou
    monkeypatch.setattr(app_module, "jobs", {})                        # e o motor reiniciou
    lista = {j["job_id"]: j for j in _chama("GET", "/api/jobs").json()["jobs"]}
    assert (lista[novo]["status"], lista[novo]["title"]) == ("failed", "Semana")
    status = _chama("GET", f"/api/status/{novo}").json()
    assert status["compilacao"]["trechos"] == 2 and "montar de novo" in status["logs"][-1]
    r = _chama("POST", f"/api/compilacoes/{novo}/refazer")
    assert r.status_code == 200, r.text
    assert app_module.jobs[novo]["status"] == "queued" and ambiente["fila"][-1] == novo
    # O que nao e compilacao nao existe para esta rota.
    assert _chama("POST", f"/api/compilacoes/{job_id}/refazer").status_code == 404


def test_o_credito_das_fontes_vai_na_descricao_do_post(ambiente):
    com_cc = _projeto(ambiente, origem_cc=True)
    outro = _projeto(ambiente)
    novo = _chama("POST", "/api/compilacoes", {"titulo": "T", "cortes": [
        {"job_id": com_cc, "clip": 0}, {"job_id": outro, "clip": 0}]}).json()["job_id"]
    pasta = ambiente["saida"] / novo
    (pasta / "compilacao_clip_1.mp4").write_bytes(b"\x00" * 64)
    (pasta / "compilacao_metadata.json").write_text(json.dumps({"shorts": [{
        "start": 0, "end": 30, "video_title_for_youtube_short": "T", "formato": "longo",
        "video_description_for_youtube": "Seleção."}]}), encoding="utf-8")
    itens = app_module._itens_do_job(novo)
    assert len(itens) == 1 and "Fulana" in itens[0].meta.credit
    assert itens[0].meta.description_for("youtube") == "Seleção."


def test_os_cortes_de_um_projeto_para_escolher(ambiente):
    job_id = _projeto(ambiente, cortes=[(10.0, 25.0, "O começo"), (40.0, 70.0, "A virada"),
                                        (80.0, 90.0, "Não renderizou")])
    os.remove(ambiente["saida"] / job_id / "v_clip_3.mp4")
    dados = _chama("GET", f"/api/jobs/{job_id}/cortes").json()
    assert dados["origem"] is True
    assert dados["cortes"] == [
        {"clip": 0, "duracao_s": 15.0, "titulo": "O começo",
         "video_url": f"/videos/{job_id}/v_clip_1.mp4", "formato": "curto"},
        {"clip": 1, "duracao_s": 30.0, "titulo": "A virada",
         "video_url": f"/videos/{job_id}/v_clip_2.mp4", "formato": "curto"}]
    sem = _projeto(ambiente, com_origem=False)
    assert _chama("GET", f"/api/jobs/{sem}/cortes").json()["origem"] is False
    assert _chama("GET", f"/api/jobs/{uuid.uuid4()}/cortes").status_code == 404
