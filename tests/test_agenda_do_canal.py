"""A agenda do canal, o fuso de quem usa e o "feito para criancas" (etapa 7.5).

O defeito que puxou isto foi achado na 7.4: o agendador calculava as janelas no
fuso do PROCESSO, e no Docker o container roda em UTC -- 11h, 15h e 19h viravam
8h, 12h e 16h em Brasilia. O conserto tem duas metades, e as duas sao
conferidas aqui: as janelas passam a ser do canal, e valem no fuso de quem usa,
que o painel manda ao motor.
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import fuso
import receitas
import scheduler

BRASILIA = timezone(timedelta(hours=-3))


def _fixo(valor):
    return lambda a, b: valor


# --------------------------------------------------------------------------- #
# Os ajustes do canal (documento puro)
# --------------------------------------------------------------------------- #

class TestAjustes:

    def test_padrao_e_acompanhar_a_instalacao(self):
        assert receitas.normalizar_ajustes(None) == {
            "agenda": {"janelas": None, "por_dia": None},
            "feito_para_criancas": None}

    def test_merge_por_secao(self):
        base = receitas.normalizar_ajustes({"agenda": {"janelas": [9, 13, 20], "por_dia": 3}})
        junto = receitas.normalizar_ajustes({"agenda": {"por_dia": 2}}, base=base)
        assert junto["agenda"] == {"janelas": [9, 13, 20], "por_dia": 2}

    def test_janelas_saem_em_ordem_e_sem_repetir(self):
        ajustes = receitas.normalizar_ajustes({"agenda": {"janelas": [19, 11, 15, 11]}})
        assert ajustes["agenda"]["janelas"] == [11, 15, 19]

    @pytest.mark.parametrize("janelas", [[], [24], [-1], ["11"], [1.5], list(range(9)), "11,15"])
    def test_janela_torta_e_recusada(self, janelas):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar_ajustes({"agenda": {"janelas": janelas}})

    @pytest.mark.parametrize("por_dia", [0, 21, True, "3", 2.5])
    def test_por_dia_torto_e_recusado(self, por_dia):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar_ajustes({"agenda": {"por_dia": por_dia}})

    def test_nulo_volta_ao_padrao(self):
        base = receitas.normalizar_ajustes({"agenda": {"janelas": [9], "por_dia": 1}})
        limpo = receitas.normalizar_ajustes({"agenda": {"janelas": None, "por_dia": None}},
                                            base=base)
        assert limpo["agenda"] == {"janelas": None, "por_dia": None}

    def test_documento_gravado_torto_nao_derruba_quem_le(self, capsys):
        assert receitas.ajustes_gravados({"agenda": {"janelas": [99]}}) == receitas.AJUSTES_PADRAO
        assert "ilegiveis" in capsys.readouterr().out

    def test_agenda_efetiva(self):
        padrao = receitas.agenda_efetiva(None, (11, 15, 19), 3)
        assert padrao == {"janelas": [11, 15, 19], "por_dia": 3, "do_canal": False}
        do_canal = receitas.agenda_efetiva({"agenda": {"janelas": [10], "por_dia": None}},
                                           (11, 15, 19), 3)
        assert do_canal == {"janelas": [10], "por_dia": 3, "do_canal": True}


class TestFeitoParaCriancas:
    """A COPPA: todo envio de canal infantil vai marcado, sem ninguem lembrar."""

    @pytest.mark.parametrize("nicho", ["infantil", "Infantil", "desenhos para crianças",
                                       "Músicas de ninar", "kids", "bebês"])
    def test_nicho_infantil_marca_sozinho(self, nicho):
        assert receitas.feito_para_criancas(None, nicho) == {"valor": True, "origem": "nicho"}

    @pytest.mark.parametrize("nicho", ["finanças", "acidentes", "fatos desconhecidos",
                                       None, "", "incrível"])
    def test_outro_nicho_nao_marca(self, nicho):
        assert receitas.feito_para_criancas(None, nicho)["valor"] is False

    def test_a_escolha_explicita_vence_o_nicho(self):
        assert receitas.feito_para_criancas({"feito_para_criancas": False}, "infantil") == \
            {"valor": False, "origem": "ajuste"}
        assert receitas.feito_para_criancas({"feito_para_criancas": True}, "finanças") == \
            {"valor": True, "origem": "ajuste"}

    def test_valor_que_nao_e_booleano_e_recusado(self):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar_ajustes({"feito_para_criancas": "sim"})


# --------------------------------------------------------------------------- #
# O fuso de quem usa
# --------------------------------------------------------------------------- #

class TestFuso:

    @pytest.mark.parametrize("nome,offset", [
        ("America/Sao_Paulo", -180), ("Europe/Lisbon", 60), ("UTC", 0), ("Etc/GMT+3", -180)])
    def test_nomes_que_existem_passam(self, nome, offset):
        assert fuso.validar(nome, offset) == (nome, offset)

    @pytest.mark.parametrize("nome,offset", [
        ("../../etc/passwd", 0), ("/etc/localtime", 0), ("America/Sao_Paulo", 900),
        ("America/Sao_Paulo", -800), ("America/Sao_Paulo", True), (None, 0), ("", 0),
        ("America/Sao_Paulo", "−180")])
    def test_o_resto_e_recusado(self, nome, offset):
        with pytest.raises(fuso.FusoInvalido):
            fuso.validar(nome, offset)

    def test_guarda_por_tenant(self, tmp_path):
        fuso.guardar("a", "America/Sao_Paulo", -180, data_dir=str(tmp_path))
        fuso.guardar("b", "Europe/Lisbon", 60, data_dir=str(tmp_path))
        assert fuso.do_tenant("a", str(tmp_path))["nome"] == "America/Sao_Paulo"
        assert fuso.do_tenant("b", str(tmp_path))["offset_min"] == 60
        assert fuso.do_tenant("c", str(tmp_path)) is None
        assert json.loads((tmp_path / "fuso.json").read_text())["a"]["offset_min"] == -180

    def test_sem_nada_guardado_vale_o_do_processo(self, tmp_path):
        assert fuso.descricao("x", str(tmp_path))["origem"] == "processo"
        assert fuso.tz_do_tenant("x", str(tmp_path)) is not None

    def test_sem_base_de_fusos_vale_a_diferenca_guardada(self, tmp_path, monkeypatch):
        """O Python do Windows nao traz a base de fusos, e o Debian trixie
        deixou de instalar o tzdata: sem ela, a diferenca de agora."""
        class _SemBase:
            def ZoneInfo(self, nome):
                raise KeyError(nome)
        monkeypatch.setitem(sys.modules, "zoneinfo", _SemBase())
        fuso.guardar("a", "America/Sao_Paulo", -180, data_dir=str(tmp_path))
        tz = fuso.tz_do_tenant("a", str(tmp_path))
        assert tz.utcoffset(None) == timedelta(hours=-3)

    def test_arquivo_torto_nao_derruba(self, tmp_path):
        (tmp_path / "fuso.json").write_text("{nao e json")
        assert fuso.do_tenant("a", str(tmp_path)) is None
        fuso.guardar("a", "UTC", 0, data_dir=str(tmp_path))
        assert fuso.do_tenant("a", str(tmp_path))["nome"] == "UTC"


# --------------------------------------------------------------------------- #
# O agendador no fuso de quem usa
# --------------------------------------------------------------------------- #

class TestAgendadorNoFuso:

    def test_as_janelas_valem_no_fuso_de_quem_usa(self):
        """O defeito da 7.4: com o processo em UTC, 11h virava 8h em Brasilia.
        Com `agora` no fuso de quem usa, as janelas sao as dela."""
        agora = datetime(2026, 9, 26, 8, 0, tzinfo=BRASILIA)
        horarios = scheduler.proximos_horarios(3, agora, sorteador=_fixo(0),
                                               horas=(11, 15, 19), jitter=0)
        assert [h.astimezone(BRASILIA).hour for h in horarios] == [11, 15, 19]
        assert [h.astimezone(timezone.utc).hour for h in horarios] == [14, 18, 22]

    def test_o_dia_do_teto_e_o_de_quem_usa(self):
        """22h em Brasilia ja e o dia seguinte em UTC: o teto do dia conta o
        dia de quem usa, nao o do container."""
        agora = datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc)   # 21h30 em Brasilia
        ocupados = [datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc),
                    datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)]
        agenda = scheduler.AgendaDaConta(horas=(11, 15, 19, 23), teto=2, fuso=BRASILIA)
        triagem = scheduler.triar_vencidas(
            [{"id": "p", "account_id": "c",
              "scheduled_at": datetime(2026, 9, 27, 0, 0, tzinfo=timezone.utc)}],
            agora, {"c": ocupados}, sorteador=_fixo(0), jitter=0, agendas={"c": agenda})
        # Dois posts no dia 26 de Brasilia: o teto de 2 segura, e o post vai
        # para as 11h do dia 27 -- em Brasilia.
        assert triagem.agora == []
        quando = triagem.reagendar["p"].astimezone(BRASILIA)
        assert (quando.day, quando.hour) == (27, 11)

    def test_cada_conta_com_as_janelas_do_canal_dela(self):
        agora = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)   # 9h em Brasilia
        vencidas = [{"id": f"{c}{i}", "account_id": c,
                     "scheduled_at": agora - timedelta(hours=3 - i)}
                    for c in ("infantil", "financas") for i in range(2)]
        agendas = {"infantil": scheduler.AgendaDaConta(horas=(13,), teto=3, fuso=BRASILIA),
                   "financas": scheduler.AgendaDaConta(horas=(20,), teto=3, fuso=BRASILIA)}
        triagem = scheduler.triar_vencidas(vencidas, agora, {}, sorteador=_fixo(0),
                                           jitter=0, agendas=agendas)
        assert sorted(triagem.agora) == ["financas0", "infantil0"]
        assert triagem.reagendar["infantil1"].astimezone(BRASILIA).hour == 13
        assert triagem.reagendar["financas1"].astimezone(BRASILIA).hour == 20

    def test_sem_agenda_a_conta_segue_a_instalacao(self):
        agora = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        vencidas = [{"id": "a", "account_id": "c", "scheduled_at": agora},
                    {"id": "b", "account_id": "c", "scheduled_at": agora}]
        triagem = scheduler.triar_vencidas(vencidas, agora, {}, sorteador=_fixo(0),
                                           horas=(22,), jitter=0)
        assert triagem.agora == ["a"]
        assert triagem.reagendar["b"].astimezone().hour == 22

    def test_descricao_com_a_agenda_do_canal(self):
        descricao = scheduler.descricao(scheduler.AgendaDaConta(horas=(9, 21), teto=2))
        assert descricao["janelas"] == [9, 21] and descricao["por_dia"] == 2
        assert scheduler.descricao()["janelas"] == list(scheduler.janelas())


# --------------------------------------------------------------------------- #
# De ponta a ponta: API, banco e laco
# --------------------------------------------------------------------------- #

app_module = pytest.importorskip("app")
auth = pytest.importorskip("auth")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")


def corre(coro_fn):
    return asyncio.run(coro_fn())


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
    shorts = [{"start": float(i), "end": float(i) + 30.0,
               "video_title_for_youtube_short": f"Corte {i + 1}"} for i in range(quantos)]
    for i in range(quantos):
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps({"shorts": shorts}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    return job_id


def _canal(**extra):
    corpo = {"name": f"Canal {uuid.uuid4().hex[:6]}", "requires_approval": False,
             "novas_contas": [{"platform": "youtube", "handle": f"yt-{uuid.uuid4().hex[:5]}"}],
             **extra}
    r = _chama("POST", "/api/canais", corpo)
    assert r.status_code == 200, r.text
    return r.json()


class TestAjustesPelaApi:

    def test_canal_novo_vem_com_os_ajustes_padrao(self, ambiente):
        canal = _canal(niche="infantil")
        assert canal["ajustes"]["agenda"] == {"janelas": None, "por_dia": None}
        assert canal["ajustes"]["agenda_efetiva"]["janelas"] == list(scheduler.janelas())
        assert canal["ajustes"]["criancas"] == {"valor": True, "origem": "nicho"}

    def test_criar_com_a_agenda_e_editar_por_cima(self, ambiente):
        canal = _canal(ajustes={"agenda": {"janelas": [9, 13, 20], "por_dia": 2}})
        assert canal["ajustes"]["agenda_efetiva"] == {"janelas": [9, 13, 20], "por_dia": 2,
                                                      "do_canal": True}
        r = _chama("PATCH", f"/api/canais/{canal['id']}",
                   {"ajustes": {"feito_para_criancas": True}})
        assert r.status_code == 200, r.text
        ajustes = r.json()["ajustes"]
        assert ajustes["agenda"]["janelas"] == [9, 13, 20]
        assert ajustes["criancas"] == {"valor": True, "origem": "ajuste"}
        lista = _chama("GET", "/api/canais").json()["canais"]
        assert next(c for c in lista if c["id"] == canal["id"])["ajustes"]["agenda"]["por_dia"] == 2

    def test_ajuste_torto_e_400_e_nao_grava_nada(self, ambiente):
        canal = _canal()
        r = _chama("PATCH", f"/api/canais/{canal['id']}",
                   {"name": "outro nome", "ajustes": {"agenda": {"janelas": [25]}}})
        assert r.status_code == 400
        assert _chama("GET", f"/api/canais/{canal['id']}").json()["name"] == canal["name"]

    def test_apagar_o_canal_leva_os_ajustes(self, ambiente):
        canal = _canal(ajustes={"agenda": {"por_dia": 1}})
        assert _chama("DELETE", f"/api/canais/{canal['id']}").status_code == 200

        async def _t():
            async with db.tenant() as t:
                return await t.all(db_models.ChannelSettings)
        assert corre(_t) == []


class TestFusoPelaApi:

    def test_o_painel_manda_e_a_agenda_diz(self, ambiente):
        assert _chama("GET", "/api/agenda").json()["fuso"]["origem"] == "processo"
        r = _chama("PUT", "/api/fuso", {"nome": "America/Sao_Paulo", "offset_min": -180})
        assert r.status_code == 200, r.text
        agenda = _chama("GET", "/api/agenda").json()
        assert agenda["fuso"] == {"nome": "America/Sao_Paulo", "offset_min": -180,
                                  "origem": "painel"}

    def test_fuso_torto_e_400(self, ambiente):
        r = _chama("PUT", "/api/fuso", {"nome": "../segredo", "offset_min": 0})
        assert r.status_code == 400

    def test_a_agenda_de_um_canal(self, ambiente):
        canal = _canal(ajustes={"agenda": {"janelas": [8, 12], "por_dia": 2}})
        agenda = _chama("GET", f"/api/agenda?canal={canal['id']}").json()
        assert agenda["janelas"] == [8, 12] and agenda["por_dia"] == 2
        assert _chama("GET", f"/api/agenda?canal={uuid.uuid4()}").status_code == 404
        assert _chama("GET", "/api/agenda?canal=nao-e-id").status_code == 400


class TestAgendarNoFuso:

    def test_agendar_usa_as_janelas_do_canal_no_fuso_de_quem_usa(self, ambiente):
        """O conserto de ponta a ponta: janelas do canal, no fuso que o painel
        mandou -- e nao no do processo."""
        _chama("PUT", "/api/fuso", {"nome": "Etc/GMT+3", "offset_min": -180})
        canal = _canal(ajustes={"agenda": {"janelas": [9, 13, 17], "por_dia": 3}})
        job_id = _projeto(ambiente, 3)
        r = _chama("POST", "/api/agendar", {"job_id": job_id, "channel_id": canal["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["agenda"]["janelas"] == [9, 13, 17]
        for item in r.json()["resultados"]:
            local = datetime.fromisoformat(item["scheduled_at"]).astimezone(BRASILIA)
            minutos = local.hour * 60 + local.minute
            assert any(abs(minutos - h * 60) <= 5 for h in (9, 13, 17)), local

    def test_as_agendas_das_contas(self, ambiente):
        fuso.guardar(db.SELF_HOST_TENANT_ID, "Etc/GMT+3", -180)
        canal = _canal(ajustes={"agenda": {"janelas": [10], "por_dia": 1}})
        conta_do_canal = canal["contas"][0]["id"]
        solta = _chama("POST", "/api/contas", {"platform": "tiktok", "handle": "solta"}).json()
        agendas = corre(lambda: app_module._agendas_das_contas([conta_do_canal, solta["id"]]))
        assert agendas[conta_do_canal].horas == (10,)
        assert agendas[conta_do_canal].teto == 1
        assert agendas[solta["id"]].horas is None
        assert agendas[solta["id"]].teto == app_module._teto_do_agendador()
        assert agendas[solta["id"]].fuso.utcoffset(None) == timedelta(hours=-3)

    def test_a_trava_reagenda_nas_janelas_do_canal(self, ambiente):
        _chama("PUT", "/api/fuso", {"nome": "Etc/GMT+3", "offset_min": -180})
        canal = _canal(ajustes={"agenda": {"janelas": [10, 20], "por_dia": 3}})
        job_id = _projeto(ambiente, 3)
        assert _chama("POST", "/api/agendar", {"job_id": job_id,
                                               "channel_id": canal["id"]}).json()["agendados"] == 3
        agora = datetime.now(timezone.utc)

        async def _vencer():
            async with db.tenant() as t:
                for i, linha in enumerate(await t.all(db_models.Publication)):
                    linha.scheduled_at = agora - timedelta(hours=3 - i)
                await t.commit()
        corre(_vencer)
        feito = corre(lambda: app_module._uma_volta_do_agendador(agora))
        assert len(feito["publicadas"]) == 1 and len(feito["reagendadas"]) == 2
        for quando in feito["reagendadas"].values():
            local = quando.astimezone(BRASILIA)
            minutos = local.hour * 60 + local.minute
            assert any(abs(minutos - h * 60) <= 5 for h in (10, 20)), local


class TestPacoteNoDiaDeQuemUsa:
    """O pacote do dia tambem era contado no fuso do processo: no Docker, um
    corte das 22h em Brasilia caia no pacote do dia seguinte."""

    def test_o_dia_do_arquivo(self):
        from publishers import pacote
        meia_noite_e_meia_utc = datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc).timestamp()
        assert pacote.dia_de(meia_noite_e_meia_utc, BRASILIA) == "2026-09-26"
        assert pacote.dia_de(meia_noite_e_meia_utc, timezone.utc) == "2026-09-27"
        assert len(pacote.hoje(BRASILIA)) == 10
