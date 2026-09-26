"""O galho por plataforma (etapa 7.3): publicar e agendar NO CANAL.

O autor, 25-set-2026: "todo video que a gente criar para esse canal vai lancar
o mesmo conteudo, tanto pro YouTube quanto pro TikTok (...) vai virar uma
ramificacao, dois galhos (...) e depois voce gerencia cada um
individualmente". Cada galho e uma linha de `publications` -- com o texto da
plataforma dele e horario proprio.
"""
import asyncio
import json
import uuid
from datetime import datetime

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
scheduler = pytest.importorskip("scheduler")


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


def _projeto(raiz, quantos=2):
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = []
    for i in range(quantos):
        shorts.append({"start": float(i), "end": float(i) + 30.0,
                       "video_title_for_youtube_short": f"Corte {i + 1}",
                       "video_description_for_tiktok": f"texto do TikTok {i + 1} #fyp",
                       "video_description_for_instagram": f"texto do Instagram {i + 1}"})
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    return job_id


def _canal(plataformas=("youtube", "tiktok", "instagram")):
    r = _chama("POST", "/api/canais", {
        "name": f"Canal {uuid.uuid4().hex[:6]}", "requires_approval": False,
        "novas_contas": [{"platform": p, "handle": f"infantil-{p}"} for p in plataformas]})
    assert r.status_code == 200, r.text
    return r.json()


def _fila():
    return _chama("GET", "/api/publicacoes").json()["publicacoes"]


def test_publicar_no_canal_abre_um_galho_por_conta(ambiente):
    job_id = _projeto(ambiente, 1)
    canal = _canal()
    r = _chama("POST", "/api/publicar", {"job_id": job_id, "channel_id": canal["id"]})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [x["platform"] for x in corpo["resultados"]] == ["youtube", "tiktok", "instagram"]
    assert corpo["publicados"] == 3
    fila = _fila()
    assert sorted(p["account"]["platform"] for p in fila) == ["instagram", "tiktok", "youtube"]
    assert {p["account"]["channel_id"] for p in fila} == {canal["id"]}
    assert len({p["clip"]["id"] for p in fila}) == 1


def test_cada_galho_leva_o_texto_da_plataforma_dele(ambiente):
    """O driver `manual` escreve a legenda de cada plataforma ao lado do corte."""
    job_id = _projeto(ambiente, 1)
    canal = _canal()
    _chama("POST", "/api/publicar", {"job_id": job_id, "channel_id": canal["id"]})
    pasta = ambiente / job_id
    assert "texto do TikTok 1" in (pasta / "v_clip_1.tiktok.txt").read_text(encoding="utf-8")
    assert "texto do Instagram 1" in (pasta / "v_clip_1.instagram.txt").read_text(encoding="utf-8")
    youtube = (pasta / "v_clip_1.youtube.txt").read_text(encoding="utf-8")
    assert youtube.startswith("Corte 1")


def test_agendar_no_canal_da_horario_proprio_a_cada_galho(ambiente):
    job_id = _projeto(ambiente, 3)
    canal = _canal(("youtube", "tiktok"))
    r = _chama("POST", "/api/agendar", {"job_id": job_id, "channel_id": canal["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["agendados"] == 6
    por_conta = {}
    for p in _fila():
        por_conta.setdefault(p["account"]["platform"], []).append(
            datetime.fromisoformat(p["scheduled_at"]))
    assert sorted(por_conta) == ["tiktok", "youtube"]
    gap = scheduler.espacamento_minimo()
    for horarios in por_conta.values():
        horarios.sort()
        assert len(horarios) == 3
        assert all(b - a >= gap for a, b in zip(horarios, horarios[1:]))


def test_um_galho_que_ja_existe_nao_derruba_os_outros(ambiente):
    """Publicou no YouTube antes de ligar o canal: o galho do YouTube ja existe,
    e o do TikTok nasce assim mesmo."""
    job_id = _projeto(ambiente, 1)
    canal = _canal(("youtube", "tiktok"))
    youtube = next(c for c in canal["contas"] if c["platform"] == "youtube")
    _chama("POST", "/api/publicar", {"job_id": job_id, "account_id": youtube["id"]})
    corpo = _chama("POST", "/api/publicar", {"job_id": job_id,
                                             "channel_id": canal["id"]}).json()
    por_plataforma = {x["platform"]: x for x in corpo["resultados"]}
    assert por_plataforma["youtube"]["ok"] is False
    assert "ja foi" in por_plataforma["youtube"]["detail"]
    assert por_plataforma["tiktok"]["ok"] is True


@pytest.mark.parametrize("rota", ["/api/publicar", "/api/agendar"])
def test_conta_ou_canal_um_dos_dois(ambiente, rota):
    job_id = _projeto(ambiente, 1)
    canal = _canal(("youtube",))
    conta = canal["contas"][0]["id"]
    assert _chama("POST", rota, {"job_id": job_id}).status_code == 400
    assert _chama("POST", rota, {"job_id": job_id, "account_id": conta,
                                 "channel_id": canal["id"]}).status_code == 400


def test_canal_sem_conta_diz_o_que_fazer(ambiente):
    job_id = _projeto(ambiente, 1)
    canal = _canal(())
    r = _chama("POST", "/api/publicar", {"job_id": job_id, "channel_id": canal["id"]})
    assert r.status_code == 400
    assert "nao tem conta ligada" in r.json()["detail"]


def test_canal_que_nao_existe(ambiente):
    job_id = _projeto(ambiente, 1)
    r = _chama("POST", "/api/agendar", {"job_id": job_id, "channel_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_o_galho_do_tiktok_conectado_sobe_pela_api_e_so_para_voce(ambiente, monkeypatch):
    """O "pronto quando" da 7.3 pelo lado do TikTok: o canal publica, o galho do
    TikTok vai pelo Direct Post (privado, antes da auditoria) com o texto do
    TikTok, e o post fica registrado -- sem link, porque privado nao tem. O
    galho do YouTube, sem conectar, fica na fila manual."""
    from publishers import tiktok_api
    vault = pytest.importorskip("vault")
    monkeypatch.delenv("TIKTOK_APP_AUDITADO", raising=False)
    job_id = _projeto(ambiente, 1)
    canal = _canal(("youtube", "tiktok"))
    tiktok = next(c for c in canal["contas"] if c["platform"] == "tiktok")
    vault.gravar(f"vault://local/tiktok/{tiktok['handle']}", {
        "client_key": "sbawabcdef123456", "client_secret": "s" * 20, "refresh_token": "R"})

    enviado = {}

    def pedir(url, *, token=None, json=None, data=None, timeout=60.0):
        if url == tiktok_api.CREATOR_INFO:
            return {"data": {"privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
                             "creator_username": "infantil", "max_video_post_duration_sec": 600}}
        if url == tiktok_api.INICIAR:
            enviado["init"] = json
            return {"data": {"publish_id": "P", "upload_url": "https://upload.tiktok/x"}}
        if url == tiktok_api.STATUS:
            return {"data": {"status": "PUBLISH_COMPLETE"}}
        raise AssertionError(url)
    monkeypatch.setattr(tiktok_api, "renovar", lambda segredo: {"access_token": "A"})
    monkeypatch.setattr(tiktok_api, "_pedir", pedir)
    monkeypatch.setattr(tiktok_api, "_enviar_pedaco",
                        lambda url, caminho, de, ate, total: enviado.setdefault("bytes", total))
    monkeypatch.setattr(tiktok_api, "INTERVALO_DO_STATUS_S", 0)

    r = _chama("POST", "/api/publicar", {"job_id": job_id, "channel_id": canal["id"],
                                         "visibility": "public"})
    assert r.status_code == 200, r.text
    por_plataforma = {x["platform"]: x for x in r.json()["resultados"]}
    assert por_plataforma["tiktok"]["driver"] == "tiktok-api"
    assert por_plataforma["youtube"]["driver"] == "manual"
    # Pedido publico, e o TikTok oferecendo: antes da auditoria, so para voce.
    assert enviado["init"]["post_info"]["privacy_level"] == "SELF_ONLY"
    assert enviado["init"]["post_info"]["title"] == "texto do TikTok 1 #fyp"
    assert enviado["bytes"] == 64
    fila = {p["account"]["platform"]: p for p in _fila()}
    assert fila["tiktok"]["status"] == "published"
    assert fila["tiktok"]["posted_at"] and fila["tiktok"]["url"] is None
    assert fila["youtube"]["status"] == "scheduled" and fila["youtube"]["posted_at"] is None
