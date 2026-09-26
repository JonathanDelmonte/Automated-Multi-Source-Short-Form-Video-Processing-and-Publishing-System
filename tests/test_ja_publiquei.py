"""O "ja publiquei" pede o link do post (etapa 7.3), de ponta a ponta.

O motor de verdade, com banco, fila e o driver `manual`: o corte vai para a
fila, a pessoa posta no app e cola o link, e o link vira o id que o coletor de
metricas le. O que so o motor pode garantir -- e o que estes testes cobram --
e que link de outra plataforma e recusado, que o painel de antes (sem corpo)
continua funcionando e que repetir o botao corrige o link sem mudar a hora do
post, que e o que a trava do agendador le.
"""
import asyncio
import json
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")
links_de_post = pytest.importorskip("links_de_post")

ID_YT = "dQw4w9WgXcQ"


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
    # Nada de rede nos testes: o link curto do TikTok fica como esta.
    monkeypatch.setattr(links_de_post, "resolver_link_curto", lambda url, timeout=8.0: None)
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    auth.esquecer_segredo()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo)
    return asyncio.run(_do())


def _na_fila_manual(raiz, plataforma="youtube"):
    """Um corte entregue a fila manual de uma conta: o caso do "ja publiquei"."""
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = [{"start": 0.0, "end": 30.0, "video_title_for_youtube_short": "Corte 1",
               "video_description_for_tiktok": "d"}]
    (pasta / "v_clip_1.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    conta = _chama("POST", "/api/contas", {"platform": plataforma,
                                           "handle": f"canal-{uuid.uuid4().hex[:6]}"}).json()
    r = _chama("POST", "/api/publicar", {"job_id": job_id, "account_id": conta["id"]})
    assert r.status_code == 200, r.text
    (pub,) = [p for p in _chama("GET", "/api/publicacoes").json()["publicacoes"]
              if p["account"]["id"] == conta["id"]]
    assert pub["status"] == "scheduled" and pub["driver"] == "manual"
    return pub


def _publicacao(pub_id):
    (pub,) = [p for p in _chama("GET", "/api/publicacoes").json()["publicacoes"]
              if p["id"] == pub_id]
    return pub


def test_o_link_vira_o_id_do_video(ambiente):
    pub = _na_fila_manual(ambiente)
    r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
               {"url": f"https://youtube.com/shorts/{ID_YT}?si=rastreio"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["remote_id"] == ID_YT and corpo["aviso"] is None
    depois = _publicacao(pub["id"])
    assert depois["status"] == "published"
    assert depois["remote_id"] == ID_YT
    assert depois["url"] == f"https://www.youtube.com/shorts/{ID_YT}"
    assert depois["posted_at"]


def test_o_post_feito_a_mao_entra_na_medicao(ambiente):
    pub = _na_fila_manual(ambiente)
    _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
           {"url": f"https://youtu.be/{ID_YT}"})
    medir = corre(publish_queue.publicadas_com_remote_id)
    assert [(m["id"], m["remote_id"], m["platform"]) for m in medir] == \
        [(pub["id"], ID_YT, "youtube")]


def test_link_de_outra_plataforma_e_recusado(ambiente):
    pub = _na_fila_manual(ambiente)
    r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
               {"url": "https://www.tiktok.com/@c/video/7412345678901234567"})
    assert r.status_code == 400
    assert "TikTok" in r.json()["detail"] and "YouTube" in r.json()["detail"]
    assert _publicacao(pub["id"])["status"] == "scheduled"


def test_link_torto_e_recusado_com_a_frase_da_tela(ambiente):
    pub = _na_fila_manual(ambiente)
    r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
               {"url": "https://www.youtube.com/@meucanal"})
    assert r.status_code == 400
    assert "nao e de um video" in r.json()["detail"]


def test_o_painel_de_antes_continua_funcionando(ambiente):
    """Sem corpo: o site de uma versao anterior falando com este motor."""
    pub = _na_fila_manual(ambiente)
    assert _chama("POST", f"/api/publicacoes/{pub['id']}/publicado").status_code == 200
    depois = _publicacao(pub["id"])
    assert depois["status"] == "published" and depois["url"] is None


def test_o_link_curto_do_tiktok_fica_guardado_com_aviso(ambiente):
    pub = _na_fila_manual(ambiente, "tiktok")
    r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
               {"url": "https://vm.tiktok.com/ZMhAbC123/"})
    assert r.status_code == 200
    assert r.json()["remote_id"] is None
    assert "link completo" in r.json()["aviso"]
    assert _publicacao(pub["id"])["url"] == "https://vm.tiktok.com/ZMhAbC123/"


def test_repetir_corrige_o_link_e_nao_a_hora(ambiente):
    """A hora do post e o que a trava do agendador le; corrigir o link nao
    pode fazer o post parecer mais novo."""
    pub = _na_fila_manual(ambiente)
    _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
           {"url": f"https://youtu.be/{ID_YT}"})
    primeira = _publicacao(pub["id"])["posted_at"]
    outro = "abcdefghijk"
    assert _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
                  {"url": f"https://youtube.com/shorts/{outro}"}).status_code == 200
    depois = _publicacao(pub["id"])
    assert depois["remote_id"] == outro
    assert depois["url"].endswith(outro)
    assert depois["posted_at"] == primeira

    async def _conta_posts():
        async with db.tenant() as t:
            return len(await t.all(db_models.PublicationPost))
    assert corre(_conta_posts) == 1


def test_publicacao_que_nao_existe(ambiente):
    r = _chama("POST", f"/api/publicacoes/{uuid.uuid4()}/publicado",
               {"url": f"https://youtu.be/{ID_YT}"})
    assert r.status_code == 404
