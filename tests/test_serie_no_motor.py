"""A serie em partes no motor (etapa 7.6): o pedido, o banco, a agenda e a ordem.

O "pronto quando" da etapa: **uma live de 1 hora vira uma serie agendada, na
ordem, sem buraco e sem repeticao**. Aqui ele roda de ponta a ponta com o
motor de verdade -- o `/api/process`, o fim do job, o agendamento no canal e o
laco do agendador, volta a volta --, com o `main.py` trocado pelo que ele
deixaria na pasta (o `tests/test_main_serie.py` cobre o `main.py`).

E os casos que o dia real traz: a parte que falha segura as seguintes (e so na
conta dela), "tentar de novo" e "pular" devolvem a serie a ordem, a publicacao
presa "subindo" por um reinicio vira "falhou", e um corte que nao renderizou
nao desloca os outros no banco.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")
import fuso
import series

BRASILIA = timezone(timedelta(hours=-3))
URL_DA_LIVE = "https://www.youtube.com/watch?v=live1hora00"


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
    monkeypatch.setattr(app_module, "_enqueue_job", lambda job_id, priority=2: None)
    probes = {}

    async def _probe(url):
        return probes.get(url, {"max_height": 1080, "duration": 3600, "origem": None})
    monkeypatch.setattr(app_module, "_probe_youtube_quality", _probe)
    # Nenhuma IA: a serie nao precisa de uma (e os cortes, sim).
    async def _sem_chave(request):
        return None
    monkeypatch.setattr(app_module, "resolve_gemini", _sem_chave)
    monkeypatch.setattr(app_module.llm_cascade, "has_text_provider", lambda: False)
    monkeypatch.setattr(app_module.llm_backend, "active", lambda: False)
    monkeypatch.setattr(publish_queue, "_VISTA_SUBINDO", {})
    monkeypatch.setattr(publish_queue, "EM_VOO", set())
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


def _canal(nome="Lives do Fulano", plataformas=("youtube", "tiktok"), **extra):
    r = _chama("POST", "/api/canais", {
        "name": nome, "niche": "games", "requires_approval": False,
        "novas_contas": [{"platform": p, "handle": f"{nome[:5]}-{p}-{uuid.uuid4().hex[:4]}"}
                         for p in plataformas],
        "ajustes": {"agenda": {"janelas": [11, 15, 19], "por_dia": 3}}, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _pedir_serie(canal_id=None, **serie):
    corpo = {"url": URL_DA_LIVE, "acknowledged": True, "serie": serie}
    if canal_id:
        corpo["channel_id"] = canal_id
    return _chama("POST", "/api/process", corpo)


def _terminar_serie(ambiente, job_id, duracao=3600.0, faltando=(), nome_do_video="Live"):
    """O que o `main.py` deixaria na pasta de uma serie, e o fim do job no
    motor (`run_job_wrapper`): o banco e o "agendar quando ficar pronta"."""
    pasta = ambiente["saida"] / job_id
    spec = series.ler_spec(str(pasta))
    shorts = series.cortes(spec, duracao, None, nome_do_video)
    resumo = {**series.resumo(spec, shorts, nome_do_video), "faltando": list(faltando)}
    prontos = {}
    for i in range(len(shorts)):
        if i + 1 in faltando:
            continue
        arquivo = f"subtitled_1_hooked_1_Live_clip_{i + 1}.mp4"
        (pasta / arquivo).write_bytes(b"\x00" * 64)
        series.marcar_pronta(str(pasta), i, arquivo, len(shorts))
        prontos[i] = arquivo
    (pasta / "Live_metadata.json").write_text(json.dumps({
        "shorts": shorts, "serie": resumo,
        "transcript": {"language": "pt", "segments": []}}))
    # O fim do job apaga o manifesto de retomada (`run_job_wrapper`).
    (pasta / app_module._RESUME_FILE).unlink(missing_ok=True)
    job = app_module.jobs[job_id]
    job["ready_files"] = prontos
    job["status"] = "completed"
    feitos, _ = app_module._clips_actually_rendered(job_id, str(pasta), "Live", shorts)
    job["result"] = {"clips": feitos}
    corre(lambda: app_module._fechar_job_no_banco(job_id))
    corre(lambda: app_module._serie_depois_do_job(job_id))
    return shorts


def _publicacoes():
    """{conta: [(parte, status, scheduled_at, id)]} por parte."""
    async def _t():
        async with db.tenant() as t:
            pubs = await t.all(db_models.Publication)
            partes = {p.clip_id: p.part for p in await t.all(db_models.SeriesPart)}
        saida = {}
        for p in pubs:
            quando = p.scheduled_at
            if quando is not None and quando.tzinfo is None:
                quando = quando.replace(tzinfo=timezone.utc)
            saida.setdefault(p.account_id, []).append(
                (partes.get(p.clip_id), p.status, quando, p.id))
        return {c: sorted(v, key=lambda x: x[0]) for c, v in saida.items()}
    return corre(_t)


def _proxima_hora(depois_de=None):
    """A proxima hora marcada -- depois de `depois_de`: uma parte segurada
    fica com a hora vencida de proposito, e o relogio tem de passar por ela."""
    horas = [q for linhas in _publicacoes().values() for (_, st, q, _) in linhas
             if st == "scheduled" and q is not None
             and (depois_de is None or q + timedelta(minutes=1) > depois_de)]
    return min(horas) if horas else None


def _volta(agora):
    return corre(lambda: app_module._uma_volta_do_agendador(agora))


def _andar_ate(entregues, parar, limite=400):
    """Volta a volta do agendador, sempre na hora da proxima publicacao, ate
    `parar(entregues)` -- `entregues` e {conta: [partes, na ordem em que sairam]}.
    Conta so o que SAIU: `publicadas` e o que a volta tentou, e uma tentativa
    que falhou tambem esta la. Devolve o ultimo `agora`."""
    agora = None
    for _ in range(limite):
        if parar(entregues):
            return agora
        proxima = _proxima_hora(agora)
        if proxima is None:
            return agora
        agora = max(proxima + timedelta(minutes=1),
                    (agora or proxima) + timedelta(minutes=1))
        tentadas = _volta(agora)["publicadas"]
        estado = {pid: (conta, parte, st) for conta, linhas in _publicacoes().items()
                  for (parte, st, _, pid) in linhas}
        for pid in tentadas:
            conta, parte, st = estado[pid]
            if st != "failed":
                entregues.setdefault(conta, []).append(parte)
    raise AssertionError("o agendador nao chegou la")


# --------------------------------------------------------------------------- #
# O pedido
# --------------------------------------------------------------------------- #

class TestPedido:

    def test_a_serie_nao_precisa_de_ia_e_o_documento_vai_para_a_pasta(self, ambiente):
        canal = _canal(language="pt-BR")
        r = _pedir_serie(canal["id"], nome="Live do Fulano", duracao_parte_s=45,
                         rotulo="sempre")
        assert r.status_code == 200, r.text
        spec = series.ler_spec(str(ambiente["saida"] / r.json()["job_id"]))
        assert spec["nome"] == "Live do Fulano" and spec["duracao_parte_s"] == 45
        assert spec["rotulo"] == "sempre" and spec["idioma"] == "pt"
        # Os cortes de sempre continuam pedindo a chave de IA.
        r = _chama("POST", "/api/process", {"url": URL_DA_LIVE, "acknowledged": True})
        assert r.status_code == 400 and "Key" in r.text

    def test_serie_falsa_e_o_pedido_de_sempre(self, ambiente):
        r = _chama("POST", "/api/process", {"url": URL_DA_LIVE, "acknowledged": True,
                                            "serie": False})
        assert r.status_code == 400 and "Key" in r.text

    @pytest.mark.parametrize("serie, trecho", [
        ({"duracao_parte_s": 5}, "duracao_parte_s"),
        ({"rotulo": "piscando"}, "rotulo"),
        ({"agendar": True}, "canal"),
    ])
    def test_pedido_torto(self, ambiente, serie, trecho):
        r = _pedir_serie(**serie)
        assert r.status_code == 400 and trecho in r.json()["detail"]

    def test_partes_demais_sao_recusadas_antes_do_download(self, ambiente):
        ambiente["probes"][URL_DA_LIVE] = {"max_height": 1080, "duration": 36000}
        r = _pedir_serie(duracao_parte_s=20)
        assert r.status_code == 400 and "1800 partes" in r.json()["detail"]
        assert list(ambiente["saida"].iterdir()) == [], "a pasta do job ficou para tras"


# --------------------------------------------------------------------------- #
# O pronto quando
# --------------------------------------------------------------------------- #

class TestProntoQuando:

    def test_uma_live_de_uma_hora_vira_uma_serie_agendada_na_ordem(self, ambiente):
        canal = _canal()
        r = _pedir_serie(canal["id"], nome="Live do Fulano", agendar=True)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]
        shorts = _terminar_serie(ambiente, job_id)
        assert len(shorts) == 60

        # O banco: a serie, e cada parte uma vez so.
        async def _banco():
            async with db.tenant() as t:
                return (await t.all(db_models.Series), await t.all(db_models.SeriesPart))
        linhas_serie, partes = corre(_banco)
        assert len(linhas_serie) == 1 and linhas_serie[0].total_parts == 60
        assert linhas_serie[0].name == "Live do Fulano"
        assert sorted(p.part for p in partes) == list(range(1, 61))

        # A agenda: as 60 partes em cada conta, sem buraco e sem repeticao, e
        # os horarios crescem com a parte -- nas janelas do canal.
        pubs = _publicacoes()
        assert len(pubs) == 2
        for linhas in pubs.values():
            assert [p for p, *_ in linhas] == list(range(1, 61))
            horas = [q for _, _, q, _ in linhas]
            assert horas == sorted(horas)
            assert all(b - a >= timedelta(hours=3) for a, b in zip(horas, horas[1:]))
            for q in horas:
                local = q.astimezone(BRASILIA)
                minutos = local.hour * 60 + local.minute
                assert any(abs(minutos - h * 60) <= 5 for h in (11, 15, 19)), local

        # E o tempo passando: cada conta entrega as partes na ordem, todas.
        entregues = {}
        _andar_ate(entregues, lambda e: sum(len(v) for v in e.values()) == 120)
        assert all(v == list(range(1, 61)) for v in entregues.values())

        # O documento anota que ja agendou: um job retomado nao agenda de novo.
        spec = series.ler_spec(str(ambiente["saida"] / job_id))
        assert spec["agendada_em"] and spec["agendamento"]["agendados"] == 120
        corre(lambda: app_module._serie_depois_do_job(job_id))
        assert sum(len(v) for v in _publicacoes().values()) == 120

    def test_sem_agendar_a_serie_fica_no_projeto(self, ambiente):
        canal = _canal()
        job_id = _pedir_serie(canal["id"]).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=300)
        assert _publicacoes() == {}
        # E o botao de agendar faz a mesma coisa, pelo mesmo caminho.
        r = _chama("POST", "/api/agendar", {"job_id": job_id, "channel_id": canal["id"]})
        assert r.status_code == 200 and r.json()["agendados"] == 10

    def test_a_parte_que_nao_renderizou_nao_entra_na_agenda(self, ambiente):
        canal = _canal(plataformas=("youtube",))
        job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=300, faltando=(3,))
        [linhas] = _publicacoes().values()
        assert [p for p, *_ in linhas] == [1, 2, 4, 5]
        estado = _chama("GET", f"/api/status/{job_id}").json()["serie"]
        assert estado["faltando"] == [3] and estado["partes"] == 5
        # A parte 4 nao espera pela 3, que nunca vai existir.
        entregues = {}
        _andar_ate(entregues, lambda e: sum(len(v) for v in e.values()) == 4)
        assert list(entregues.values()) == [[1, 2, 4, 5]]


# --------------------------------------------------------------------------- #
# A ordem quando o dia nao e normal
# --------------------------------------------------------------------------- #

def _serie_agendada(ambiente, plataformas=("youtube",), duracao=360.0):
    canal = _canal(plataformas=plataformas)
    job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
    _terminar_serie(ambiente, job_id, duracao=duracao)
    return canal, job_id


def _falhar_a_parte(ambiente, job_id, parte):
    """O arquivo da parte some: na hora dela, a publicacao falha."""
    arquivo = ambiente["saida"] / job_id / f"subtitled_1_hooked_1_Live_clip_{parte}.mp4"
    guardado = arquivo.read_bytes()
    arquivo.unlink()
    return lambda: arquivo.write_bytes(guardado)


class TestOrdem:

    def test_a_parte_que_falhou_segura_as_seguintes_e_tentar_de_novo_volta_a_ordem(self, ambiente):
        canal, job_id = _serie_agendada(ambiente)
        devolver = _falhar_a_parte(ambiente, job_id, 3)
        entregues = {}
        _andar_ate(entregues, lambda e: sum(len(v) for v in e.values()) == 2)
        [conta] = list(_publicacoes())

        # A vez da parte 3: falha. A da 4: fica segurada, e a fila diz por que.
        agora = _proxima_hora() + timedelta(minutes=1)
        _volta(agora)
        linhas = _publicacoes()[conta]
        assert linhas[2][1] == "failed"
        agora = _proxima_hora() + timedelta(minutes=1)
        feito = _volta(agora)
        assert feito["publicadas"] == [] and set(feito["seguradas"].values()) == {3}
        fila = {p["serie"]["parte"]: p for p in _chama("GET", "/api/publicacoes").json()["publicacoes"]}
        assert fila[4]["parada"] == {"parte": 3, "motivo": "falhou"}
        assert fila[3]["serie"]["nome"] == "Live" and fila[3]["serie"]["partes"] == 6
        # Segurada nao anda: a 4 nao ganhou hora nova, nem a 5 e a 6.
        antes = [q for _, _, q, _ in _publicacoes()[conta]]
        _volta(agora + timedelta(minutes=1))
        assert [q for _, _, q, _ in _publicacoes()[conta]] == antes

        # Tentar de novo: a 3 sai na proxima volta, e as outras voltam a fila
        # na ordem -- nenhuma vai para o fim da agenda.
        devolver()
        pid3 = linhas[2][3]
        r = _chama("POST", f"/api/publicacoes/{pid3}/tentar")
        assert r.status_code == 200, r.text
        feito = _volta(agora + timedelta(minutes=2))
        assert feito["publicadas"] == [pid3]
        entregues[conta].append(3)
        horas = [q for p, st, q, _ in _publicacoes()[conta] if p > 3]
        assert horas == sorted(horas) and horas[0] > agora
        _andar_ate(entregues, lambda e: sum(len(v) for v in e.values()) == 6)
        assert entregues[conta] == [1, 2, 3, 4, 5, 6]

    def test_pular_a_parte_que_falhou(self, ambiente):
        canal, job_id = _serie_agendada(ambiente)
        _falhar_a_parte(ambiente, job_id, 2)
        entregues = {}
        _andar_ate(entregues, lambda e: sum(len(v) for v in e.values()) == 1)
        [conta] = list(_publicacoes())
        agora = _proxima_hora() + timedelta(minutes=1)
        _volta(agora)
        pid2 = _publicacoes()[conta][1][3]
        assert _chama("DELETE", f"/api/publicacoes/{pid2}").status_code == 200
        entregues_depois = {}
        _andar_ate(entregues_depois, lambda e: sum(len(v) for v in e.values()) == 4)
        assert entregues_depois[conta] == [3, 4, 5, 6]

    def test_cada_conta_anda_no_seu_passo(self, ambiente):
        canal, job_id = _serie_agendada(ambiente, plataformas=("youtube", "tiktok"))
        contas = {c["platform"]: c["id"] for c in canal["contas"]}
        # A parte 2 falha so no YouTube: a publicacao dele e marcada falha.
        async def _falha():
            async with db.tenant() as t:
                partes = {p.clip_id: p.part for p in await t.all(db_models.SeriesPart)}
                for p in await t.all(db_models.Publication):
                    if p.account_id == contas["youtube"] and partes[p.clip_id] == 2:
                        p.status = "failed"
                await t.commit()
        corre(_falha)
        entregues = {}
        _andar_ate(entregues, lambda e: len(e.get(contas["tiktok"], [])) == 6)
        assert entregues[contas["tiktok"]] == [1, 2, 3, 4, 5, 6]
        assert entregues.get(contas["youtube"], []) == [1]

    def test_tentar_de_novo_so_o_que_falhou(self, ambiente):
        _serie_agendada(ambiente, duracao=120)
        [linhas] = _publicacoes().values()
        r = _chama("POST", f"/api/publicacoes/{linhas[0][3]}/tentar")
        assert r.status_code == 400 and "falhou" in r.json()["detail"]
        assert _chama("POST", f"/api/publicacoes/{uuid.uuid4()}/tentar").status_code == 404


class TestPresaSubindo:

    def test_a_presa_vira_falhou_e_a_que_esta_subindo_nao(self, ambiente, capsys):
        _serie_agendada(ambiente, duracao=180)
        [linhas] = _publicacoes().values()
        presa, subindo = linhas[0][3], linhas[1][3]

        async def _subindo():
            async with db.tenant() as t:
                for p in await t.all(db_models.Publication):
                    if p.id in (presa, subindo):
                        p.status = "publishing"
                await t.commit()
        corre(_subindo)
        publish_queue.EM_VOO.add(subindo)       # esta, o motor esta enviando
        agora = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        assert corre(lambda: publish_queue.destravar_presas(agora)) == []
        assert corre(lambda: publish_queue.destravar_presas(
            agora + timedelta(minutes=29))) == []
        assert corre(lambda: publish_queue.destravar_presas(
            agora + timedelta(minutes=31))) == [presa]
        [linhas] = _publicacoes().values()
        estados = {pid: st for _, st, _, pid in linhas}
        assert estados[presa] == "failed" and estados[subindo] == "publishing"
        assert "Confira na plataforma" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# O indice do corte, a lista de projetos e a retomada
# --------------------------------------------------------------------------- #

class TestIndiceEstavel:

    def test_o_corte_que_falhou_nao_desloca_os_outros(self, ambiente):
        """Com o 3 de 5 falhando, o 4 era gravado como "corte 3" -- e publicar
        o corte 3 subia o arquivo do 4. Numa serie, a Parte 4 com o titulo da 3."""
        canal = _canal(plataformas=("youtube",))
        job_id = _pedir_serie(canal["id"]).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=300, faltando=(3,))
        cortes = corre(lambda: app_module._cortes_do_job(job_id))
        assert sorted(c.rubric_json["clip_index"] for c in cortes) == [0, 1, 3, 4]
        por_indice = {c.rubric_json["clip_index"]: c for c in cortes}
        assert por_indice[3].render_key == "subtitled_1_hooked_1_Live_clip_4.mp4"
        assert por_indice[3].rubric_json["video_title_for_youtube_short"] == "Live - Parte 4"
        itens = {i.clip.index: i for i in app_module._itens_do_job(job_id)}
        assert os.path.basename(itens[3].clip.path) == "subtitled_1_hooked_1_Live_clip_4.mp4"
        assert not os.path.exists(itens[2].clip.path)
        job = app_module.jobs[job_id]
        assert app_module._clip_em_memoria(job, 3)["video_url"].endswith("clip_4.mp4")
        assert app_module._clip_em_memoria(job, 2) is None

    def test_depois_de_um_reinicio_a_parte_que_falta_nao_vira_cartao(self, ambiente):
        """O metadata e a promessa: recuperado do disco, o projeto mostrava as
        8 partes, com a 5 sem video, e contava 8 de 8."""
        canal = _canal(plataformas=("youtube",))
        job_id = _pedir_serie(canal["id"]).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=480, faltando=(5,))
        del app_module.jobs[job_id]                 # o motor reiniciou
        app_module._recover_jobs_from_disk()
        cortes = app_module.jobs[job_id]["result"]["clips"]
        assert [c["clip_index"] for c in cortes] == [0, 1, 2, 3, 5, 6, 7]
        job = app_module.jobs[job_id]
        assert app_module._clip_em_memoria(job, 5)["video_url"].endswith("clip_6.mp4")
        assert app_module._clip_em_memoria(job, 4) is None
        status = _chama("GET", f"/api/status/{job_id}").json()
        assert status["serie"]["partes"] == 8 and status["serie"]["faltando"] == [5]
        [projeto] = [p for p in _chama("GET", "/api/jobs").json()["jobs"]
                     if p["job_id"] == job_id]
        assert projeto["clip_count"] == 7

    def test_a_lista_de_projetos_chama_a_serie_pelo_nome(self, ambiente):
        canal = _canal(plataformas=("youtube",))
        job_id = _pedir_serie(canal["id"], nome="Filme de 1920").json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=240)
        [projeto] = [p for p in _chama("GET", "/api/jobs").json()["jobs"]
                     if p["job_id"] == job_id]
        assert projeto["title"] == "Filme de 1920"
        assert projeto["serie"]["partes"] == 4 and projeto["serie"]["prontas"] == 4


class TestRetomada:

    def _manifesto(self, pasta, env=None):
        (pasta / ".resume.json").write_text(json.dumps({
            "cmd": ["python", "main.py"], "priority": 2, "attempts": 0,
            "tenant_id": db.SELF_HOST_TENANT_ID, "env": env or {}}))

    def test_a_serie_parada_no_meio_e_retomada_e_nao_dada_por_pronta(self, ambiente, monkeypatch):
        pasta = ambiente["saida"] / str(uuid.uuid4())
        pasta.mkdir()
        series.gravar_spec(str(pasta), series.normalizar_pedido({}))
        (pasta / "Live_metadata.json").write_text(json.dumps({"shorts": [{"start": 0, "end": 60}]}))
        self._manifesto(pasta, {"AUTO_LAYOUT": "0", "PATH": "/tmp/malicioso",
                                "CAPTION_TEMPLATE_FILE": "/x/caption_template.json"})
        enfileirados = []
        monkeypatch.setattr(app_module, "_enqueue_job",
                            lambda job_id, priority=2: enfileirados.append(job_id))
        app_module._recover_jobs_from_disk()
        assert pasta.name not in app_module.jobs, "dada por pronta so porque tem metadata"
        app_module._resume_interrupted_jobs()
        assert enfileirados == [pasta.name]
        env = app_module.jobs[pasta.name]["env"]
        # As escolhas do job voltam; o que nao e escolha de job, nao.
        assert env["AUTO_LAYOUT"] == "0"
        assert env["CAPTION_TEMPLATE_FILE"] == "/x/caption_template.json"
        assert env.get("PATH") != "/tmp/malicioso"

    def test_a_serie_completa_continua_pronta(self, ambiente):
        pasta = ambiente["saida"] / str(uuid.uuid4())
        pasta.mkdir()
        series.gravar_spec(str(pasta), series.normalizar_pedido({}))
        (pasta / "Live_metadata.json").write_text(json.dumps({"shorts": [{"start": 0, "end": 60}]}))
        (pasta / "p.mp4").write_bytes(b"x")
        series.marcar_pronta(str(pasta), 0, str(pasta / "p.mp4"), 1)
        self._manifesto(pasta)
        app_module._recover_jobs_from_disk()
        assert app_module.jobs[pasta.name]["status"] == "completed"

    def test_o_manifesto_leva_as_escolhas_do_job(self, ambiente):
        canal = _canal(plataformas=("youtube",))
        r = _chama("POST", "/api/process", {
            "url": URL_DA_LIVE, "acknowledged": True, "channel_id": canal["id"],
            "serie": {}, "layouts": "none", "captions": False})
        job_id = r.json()["job_id"]
        manifesto = json.loads((ambiente["saida"] / job_id / ".resume.json").read_text())
        assert manifesto["env"] == {"AUTO_LAYOUT": "0", "AUTO_CAPTIONS": "0"}


# --------------------------------------------------------------------------- #
# A playlist de cada serie no YouTube
# --------------------------------------------------------------------------- #

@pytest.fixture()
def youtube_de_mentira(monkeypatch):
    """A rede do YouTube imitada: o que foi criado e o que entrou, em ordem."""
    import playlists_youtube
    chamadas = {"criadas": [], "itens": [], "sumiu": False}

    def criar(token, corpo):
        assert token == "TOKEN"
        chamadas["criadas"].append(corpo)
        return f"PL{len(chamadas['criadas'])}"

    def inserir(token, corpo):
        if chamadas["sumiu"]:
            chamadas["sumiu"] = False
            raise playlists_youtube.PlaylistSumiu("apagada")
        trecho = corpo["snippet"]
        chamadas["itens"].append((trecho["playlistId"], trecho["resourceId"]["videoId"]))
        return f"IT{len(chamadas['itens'])}"

    monkeypatch.setattr(playlists_youtube, "token_de_acesso", lambda segredo: "TOKEN")
    monkeypatch.setattr(playlists_youtube, "criar", criar)
    monkeypatch.setattr(playlists_youtube, "inserir", inserir)
    return chamadas


def _conectar_organizar(canal):
    import playlists_youtube
    import vault
    conta = next(c for c in canal["contas"] if c["platform"] == "youtube")
    vault.gravar(playlists_youtube.ref_de(conta["handle"]),
                 {"client_id": "id", "client_secret": "s", "refresh_token": "r"})
    return conta


def _mudar(parte, **campos):
    """Muda a publicacao da parte `parte` (na unica conta do teste)."""
    async def _t():
        async with db.tenant() as t:
            partes = {p.clip_id: p.part for p in await t.all(db_models.SeriesPart)}
            for p in await t.all(db_models.Publication):
                if partes.get(p.clip_id) == parte:
                    for k, v in campos.items():
                        setattr(p, k, v)
            await t.commit()
    corre(_t)


def _arrumar():
    return corre(lambda: app_module._arrumar_playlists(forcar=True))


class TestPlaylist:

    def test_a_playlist_nasce_com_a_primeira_parte_e_segue_a_ordem(self, ambiente,
                                                                   youtube_de_mentira):
        canal = _canal(plataformas=("youtube",), language="pt-BR")
        _conectar_organizar(canal)
        job_id = _pedir_serie(canal["id"], nome="Filme de 1920", agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=240)
        assert _arrumar()["criadas"] == []          # nada foi ao ar ainda

        _mudar(1, status="published", remote_id="vid1")
        feito = _arrumar()
        assert feito["criadas"] == ["PL1"] and youtube_de_mentira["itens"] == [("PL1", "vid1")]
        corpo = youtube_de_mentira["criadas"][0]
        assert corpo["snippet"]["title"] == "Filme de 1920"
        assert "na ordem" in corpo["snippet"]["description"]
        assert corpo["status"]["privacyStatus"] == "public"

        # A 3 foi postada a mao antes da 2: espera a 2, e as duas entram em ordem.
        _mudar(3, status="published", remote_id="vid3", scheduled_at=None)
        assert _arrumar()["itens"] == []
        _mudar(2, status="published", remote_id="vid2")
        _arrumar()
        assert youtube_de_mentira["itens"] == [("PL1", "vid1"), ("PL1", "vid2"), ("PL1", "vid3")]
        # De novo, nada: cada parte entra uma vez so, e a playlist e uma so.
        assert _arrumar() == {"criadas": [], "itens": [], "sem_cota": False}
        # A fila leva o link da playlist, para a tela mostrar.
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        assert {p["serie"]["playlist"] for p in fila} == \
            {"https://www.youtube.com/playlist?list=PL1"}

    def test_pulada_e_postada_sem_link_nao_seguram(self, ambiente, youtube_de_mentira):
        canal = _canal(plataformas=("youtube",))
        _conectar_organizar(canal)
        job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=240)
        _mudar(1, status="published", remote_id=None)      # postada sem o link
        _mudar(2, status="cancelled")                      # pulada
        _mudar(3, status="published", remote_id="vid3")
        _arrumar()
        assert youtube_de_mentira["itens"] == [("PL1", "vid3")]

    def test_sem_a_conexao_nao_ha_playlist(self, ambiente, youtube_de_mentira):
        canal = _canal(plataformas=("youtube",))
        job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=120)
        _mudar(1, status="published", remote_id="vid1")
        assert _arrumar()["criadas"] == [] and youtube_de_mentira["criadas"] == []

    def test_a_cota_do_dia_e_respeitada_e_o_resto_entra_depois(self, ambiente, monkeypatch,
                                                               youtube_de_mentira):
        monkeypatch.setenv("YOUTUBE_QUOTA_DAILY", "120")   # a playlist e UM item
        canal = _canal(plataformas=("youtube",))
        _conectar_organizar(canal)
        job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=180)
        for parte in (1, 2, 3):
            _mudar(parte, status="published", remote_id=f"vid{parte}")
        feito = _arrumar()
        assert feito["sem_cota"] and youtube_de_mentira["itens"] == [("PL1", "vid1")]
        # O dia seguinte (a cota zerou): o resto entra, na ordem, na MESMA playlist.
        monkeypatch.setenv("YOUTUBE_QUOTA_DAILY", "10000")
        _arrumar()
        assert youtube_de_mentira["itens"] == [("PL1", "vid1"), ("PL1", "vid2"), ("PL1", "vid3")]
        assert len(youtube_de_mentira["criadas"]) == 1

    def test_a_playlist_apagada_no_youtube_e_refeita(self, ambiente, youtube_de_mentira):
        canal = _canal(plataformas=("youtube",))
        _conectar_organizar(canal)
        job_id = _pedir_serie(canal["id"], agendar=True).json()["job_id"]
        _terminar_serie(ambiente, job_id, duracao=120)
        _mudar(1, status="published", remote_id="vid1")
        _arrumar()
        youtube_de_mentira["sumiu"] = True
        _mudar(2, status="published", remote_id="vid2")
        _arrumar()                                   # a 2 descobre que ela sumiu
        _arrumar()                                   # e a seguinte refaz, com as duas
        assert youtube_de_mentira["itens"][-2:] == [("PL2", "vid1"), ("PL2", "vid2")]
