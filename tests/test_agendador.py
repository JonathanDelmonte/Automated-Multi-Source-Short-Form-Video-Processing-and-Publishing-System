"""Agendador com jitter -- Fase 4, bloco 4.4, ADR-007.

Fecha a decisao em aberto §10.2. Os numeros nao sao chute: 3/dia vem da conta
do §1 ("3 videos/dia gastam 4.800 e sobra metade"), e o espacamento de 3 h e o
jitter de ±25 min sao os pontos de partida que o ADR-007 propos. Sao
**defaults** -- calibrar horario de publicacao exige retencao real, que e a
tabela `metrics` e a Fase 5.

O teste que nao pode cair e `test_pedir_jitter_zero_nao_desliga`. O §1 lista
"postagens em horarios regulares demais" entre os sinais que a deteccao de
automacao cruza, e o ADR-007 trata o jitter como requisito de desenho por causa
disso. Um agendador que aceita zero e um agendador que um dia roda com zero.
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
scheduler = pytest.importorskip("scheduler")

MEIO_DIA = datetime(2026, 9, 16, 9, 0).astimezone()


def corre(coro_fn):
    return asyncio.run(coro_fn())


def _fixo(valor):
    """Sorteador deterministico, para o calculo poder ser conferido."""
    return lambda a, b: valor


# --------------------------------------------------------------------------- #
# Os numeros da decisao §10.2
# --------------------------------------------------------------------------- #

class TestNumeros:

    def test_tres_por_dia_e_a_conta_do_plano(self):
        assert scheduler.POR_DIA_PADRAO == 3

    def test_o_padrao_cabe_na_quota_do_youtube(self):
        """Agendar mais do que a quota comporta deixaria posts falhando toda
        noite, horas depois de quem clicou ter ido dormir."""
        import publishers
        assert scheduler.POR_DIA_PADRAO <= publishers.quota.uploads_por_dia()

    def test_as_janelas_cabem_no_espacamento(self):
        """Tres janelas com 3 h de espacamento minimo so funcionam se estiverem
        a pelo menos 3 h uma da outra -- senao o agendador empurra tudo para a
        frente e o horario escolhido deixa de valer."""
        horas = scheduler.JANELAS_PADRAO
        minimo = scheduler.ESPACAMENTO_PADRAO_MIN / 60
        assert all(b - a >= minimo for a, b in zip(horas, horas[1:]))

    def test_configuravel_por_ambiente(self, monkeypatch):
        """Calibrar isto e trabalho da Fase 5, com `metrics` na mao. Nao pode
        exigir deploy."""
        monkeypatch.setenv("SCHEDULE_PER_DAY", "5")
        monkeypatch.setenv("SCHEDULE_WINDOWS", "8, 12,20")
        monkeypatch.setenv("SCHEDULE_MIN_GAP_MINUTES", "60")
        assert scheduler.por_dia() == 5
        assert scheduler.janelas() == (8, 12, 20)
        assert scheduler.espacamento_minimo() == timedelta(minutes=60)

    @pytest.mark.parametrize("bruto", ["", "abc", "99,-3", ",,,"])
    def test_janela_invalida_cai_no_padrao(self, monkeypatch, bruto):
        monkeypatch.setenv("SCHEDULE_WINDOWS", bruto)
        assert scheduler.janelas() == scheduler.JANELAS_PADRAO


class TestJitter:

    def test_pedir_jitter_zero_nao_desliga(self, monkeypatch, capsys):
        """O ADR-007 trata o jitter como requisito de desenho: o §1 lista
        horario regular demais entre os sinais que a deteccao cruza."""
        for pedido in ("0", "-5", "1"):
            monkeypatch.setenv("SCHEDULE_JITTER_MINUTES", pedido)
            assert scheduler.jitter_minutos() == scheduler.JITTER_MINIMO_MIN
        assert "deteccao de automacao" in capsys.readouterr().out

    def test_o_piso_nao_e_configuravel(self, monkeypatch):
        monkeypatch.setenv("JITTER_MINIMO_MIN", "0")
        assert scheduler.JITTER_MINIMO_MIN == 5

    def test_jitter_maior_e_respeitado(self, monkeypatch):
        monkeypatch.setenv("SCHEDULE_JITTER_MINUTES", "40")
        assert scheduler.jitter_minutos() == 40

    def test_o_horario_nao_e_a_hora_cheia(self):
        """A prova do pudim: com jitter, o minuto nao e zero."""
        h = scheduler.proximos_horarios(3, MEIO_DIA, sorteador=_fixo(17))
        assert [x.minute for x in h] == [17, 17, 17]

    def test_dois_dias_nao_saem_iguais(self):
        """Com sorteio de verdade, duas execucoes nao produzem a mesma
        assinatura."""
        import random
        a = scheduler.proximos_horarios(6, MEIO_DIA,
                                        sorteador=lambda x, y: random.randint(x, y))
        b = scheduler.proximos_horarios(6, MEIO_DIA,
                                        sorteador=lambda x, y: random.randint(x, y))
        assert [x.minute for x in a] != [x.minute for x in b]


class TestHorarios:

    def test_usa_as_janelas_do_dia(self):
        h = scheduler.proximos_horarios(3, MEIO_DIA, sorteador=_fixo(0))
        assert [x.hour for x in h] == list(scheduler.JANELAS_PADRAO)

    def test_nunca_no_passado(self):
        """Agendar para tras publicaria tudo de uma vez no primeiro tique, que
        e o oposto de espacar."""
        tarde = datetime(2026, 9, 16, 20, 0).astimezone()
        h = scheduler.proximos_horarios(2, tarde, sorteador=_fixo(0))
        assert all(x > tarde for x in h)
        assert h[0].day == tarde.day + 1

    def test_transborda_para_o_dia_seguinte(self):
        h = scheduler.proximos_horarios(5, MEIO_DIA, sorteador=_fixo(0))
        assert len(h) == 5
        assert len({x.date() for x in h}) == 2

    def test_respeita_o_teto_por_dia(self):
        h = scheduler.proximos_horarios(4, MEIO_DIA, sorteador=_fixo(0),
                                        teto_por_dia=2)
        por_dia = {}
        for x in h:
            por_dia[x.date()] = por_dia.get(x.date(), 0) + 1
        assert max(por_dia.values()) == 2

    def test_o_espacamento_vence_o_jitter(self):
        """Duas janelas a uma hora com jitter de -25 e +25 terminariam a 10 min
        uma da outra -- o jitter destruindo a regra que o espacamento existe
        para manter. Por isso o espacamento e aplicado DEPOIS."""
        sorteios = iter([25, -25, 0, 0, 0, 0])
        h = scheduler.proximos_horarios(
            2, MEIO_DIA, sorteador=lambda a, b: next(sorteios),
            horas=(11, 12), jitter=25, gap=timedelta(minutes=60))
        assert h[1] - h[0] >= timedelta(minutes=60)

    def test_sempre_crescente(self):
        h = scheduler.proximos_horarios(9, MEIO_DIA, sorteador=_fixo(-25))
        assert h == sorted(h)

    def test_zero_nao_pede_nada(self):
        assert scheduler.proximos_horarios(0, MEIO_DIA) == []

    def test_sem_janela_e_erro_e_nao_laco_infinito(self):
        with pytest.raises(scheduler.AgendaInvalida):
            scheduler.proximos_horarios(1, MEIO_DIA, horas=())

    def test_devolve_com_fuso(self):
        """`scheduled_at` e comparado com `now()` do laco: sem fuso, a
        comparacao e entre grandezas diferentes."""
        h = scheduler.proximos_horarios(1, MEIO_DIA, sorteador=_fixo(0))
        assert h[0].tzinfo is not None
        assert scheduler.para_utc(h[0]).tzinfo == timezone.utc

    def test_agora_sem_fuso_nao_quebra(self):
        h = scheduler.proximos_horarios(1, datetime(2026, 9, 16, 9, 0),
                                        sorteador=_fixo(0))
        assert h and h[0].tzinfo is not None


# --------------------------------------------------------------------------- #
# A fila, de ponta a ponta
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
    auth.esquecer_segredo()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()
    auth.esquecer_segredo()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


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
                       "video_description_for_tiktok": "d"})
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps(
        {"shorts": shorts, "transcript": {"language": "none", "segments": []}}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    return job_id


class TestAgendarPelaApi:

    def test_agenda_e_nao_publica_agora(self, ambiente):
        job_id = _projeto(ambiente, 2)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        r = _chama("POST", "/api/agendar",
                   {"job_id": job_id, "account_id": conta["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["agendados"] == 2
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        assert all(p["status"] == "scheduled" for p in fila)
        assert all(p["scheduled_at"] for p in fila)
        # E nada foi escrito ao lado do corte: o driver nao rodou.
        assert not list((ambiente / job_id).glob("*.youtube.txt"))

    def test_os_horarios_saem_espacados(self, ambiente):
        job_id = _projeto(ambiente, 3)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/agendar", {"job_id": job_id, "account_id": conta["id"]})
        quando = sorted(datetime.fromisoformat(p["scheduled_at"])
                        for p in _chama("GET", "/api/publicacoes").json()["publicacoes"])
        for a, b in zip(quando, quando[1:]):
            assert b - a >= scheduler.espacamento_minimo()

    def test_agendar_duas_vezes_e_recusado(self, ambiente):
        job_id = _projeto(ambiente, 1)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        corpo = {"job_id": job_id, "account_id": conta["id"]}
        assert _chama("POST", "/api/agendar", corpo).json()["agendados"] == 1
        segundo = _chama("POST", "/api/agendar", corpo).json()["resultados"][0]
        assert segundo["ok"] is False
        assert "ja esta na fila" in segundo["detail"]

    def test_job_e_conta_inexistentes(self, ambiente):
        job_id = _projeto(ambiente, 1)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert _chama("POST", "/api/agendar",
                      {"job_id": str(uuid.uuid4()),
                       "account_id": conta["id"]}).status_code == 404
        assert _chama("POST", "/api/agendar",
                      {"job_id": job_id,
                       "account_id": str(uuid.uuid4())}).status_code == 404

    def test_a_agenda_e_visivel_antes_de_agendar(self, ambiente):
        """Para ninguem descobrir o horario depois do post."""
        corpo = _chama("GET", "/api/agenda").json()
        assert corpo["por_dia"] == scheduler.POR_DIA_PADRAO
        assert corpo["jitter_min"] >= scheduler.JITTER_MINIMO_MIN


class TestLaco:

    def _agendar_para_tras(self, ambiente, segundos=-60):
        job_id = _projeto(ambiente, 1)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/agendar", {"job_id": job_id, "account_id": conta["id"]})

        async def _t():
            async with db.tenant() as t:
                linhas = await t.all(db_models.Publication)
                linhas[0].scheduled_at = (datetime.now(timezone.utc)
                                          + timedelta(seconds=segundos))
                await t.commit()
                return linhas[0].id
        return job_id, corre(_t)

    def test_o_que_venceu_aparece_como_devido(self, ambiente):
        _, pub_id = self._agendar_para_tras(ambiente)
        devidas = corre(lambda: publish_queue.devidas(datetime.now(timezone.utc)))
        assert [d["id"] for d in devidas] == [pub_id]

    def test_o_que_nao_venceu_nao_aparece(self, ambiente):
        self._agendar_para_tras(ambiente, segundos=3600)
        assert corre(lambda: publish_queue.devidas(datetime.now(timezone.utc))) == []

    def test_reservar_so_funciona_uma_vez(self, ambiente):
        """Durante um deploy ha DUAS instancias com o mesmo banco e o mesmo
        laco. A unicidade `(corte, conta)` nao pega este caso, porque a linha e
        a mesma -- quem segura e o UPDATE condicional."""
        _, pub_id = self._agendar_para_tras(ambiente)
        assert corre(lambda: publish_queue.reservar(pub_id)) is True
        assert corre(lambda: publish_queue.reservar(pub_id)) is False

    def test_o_laco_publica_e_fecha_a_linha(self, ambiente):
        job_id, pub_id = self._agendar_para_tras(ambiente)
        devidas = corre(lambda: publish_queue.devidas(datetime.now(timezone.utc)))
        corre(lambda: publish_queue.reservar(pub_id))
        corre(lambda: app_module._publicar_uma_agendada(devidas[0]))
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"]
        assert fila[0]["status"] == "scheduled"   # driver manual: espera a pessoa
        assert (ambiente / job_id / "v_clip_1.youtube.txt").exists()

    def test_arquivo_sumido_vira_falha_e_nao_excecao(self, ambiente):
        job_id, pub_id = self._agendar_para_tras(ambiente)
        for arquivo in (ambiente / job_id).glob("*.mp4"):
            os.remove(arquivo)
        devidas = corre(lambda: publish_queue.devidas(datetime.now(timezone.utc)))
        corre(lambda: publish_queue.reservar(pub_id))
        corre(lambda: app_module._publicar_uma_agendada(devidas[0]))
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"][0]["status"] \
            == "failed"

    def test_apagar_o_corte_leva_a_publicacao_junto(self, ambiente):
        """A FK de `publications` e ON DELETE CASCADE (secao 7). Nao ha
        publicacao orfa esperando um corte que nao existe mais -- a linha some
        com ele, e o laco nunca a ve."""
        self._agendar_para_tras(ambiente)

        async def _apagar():
            async with db.tenant() as t:
                for c in await t.all(db_models.Clip):
                    await t.session.delete(c)
                await t.commit()
        corre(_apagar)
        assert corre(lambda: publish_queue.devidas(datetime.now(timezone.utc))) == []
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"] == []

    def test_corte_sumido_entre_a_leitura_e_o_envio_vira_falha(self, ambiente):
        """A janela real: o laco leu a lista, e o corte sumiu antes do envio.
        Tem de fechar a linha como falha, e nao explodir dentro do laco."""
        _, pub_id = self._agendar_para_tras(ambiente)
        corre(lambda: publish_queue.reservar(pub_id))
        fantasma = {"id": pub_id, "tenant_id": db.SELF_HOST_TENANT_ID,
                    "clip_id": str(uuid.uuid4()),
                    "account_id": str(uuid.uuid4()), "driver": "manual"}
        corre(lambda: app_module._publicar_uma_agendada(fantasma))
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"][0]["status"] \
            == "failed"

    def test_o_laco_repoe_o_tenant(self, ambiente):
        """O laco e do servidor e atravessa tenants. Sem repor, ler o corte
        usaria o tenant errado -- e `db.tenant()` nao reclama, so devolve None
        e a publicacao morre dizendo "corte nao encontrado"."""
        _, pub_id = self._agendar_para_tras(ambiente)
        devidas = corre(lambda: publish_queue.devidas(datetime.now(timezone.utc)))
        assert devidas[0]["tenant_id"] == db.SELF_HOST_TENANT_ID
        db.usar_tenant("tenant-errado-de-proposito")
        corre(lambda: publish_queue.reservar(pub_id))
        corre(lambda: app_module._publicar_uma_agendada(devidas[0]))
        # A leitura de conferencia precisa voltar ao tenant certo: o
        # `usar_tenant` acima sujou ESTE contexto de proposito, e ele vale ate o
        # fim do teste. (Se isto nao fosse preciso, o `ContextVar` nao estaria
        # fazendo nada.)
        db.usar_tenant(db.SELF_HOST_TENANT_ID)
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"][0]["status"] \
            != "failed"


# --------------------------------------------------------------------------- #
# A agenda por conta e a trava do post atrasado (etapa 7.3)
# --------------------------------------------------------------------------- #
#
# O autor, 26-set-2026: o post cuja hora passou com o PC desligado "posta
# quando o PC voltar, com trava: nunca varios de uma vez".

GAP = timedelta(hours=3)
NOITE = datetime(2026, 9, 16, 20, 0).astimezone()


def _vencida(i, conta="A", horas_atras=1):
    return {"id": f"p{i}", "account_id": conta,
            "scheduled_at": NOITE - timedelta(hours=horas_atras, minutes=i)}


def _espacados(horarios, gap=GAP):
    ordenados = sorted(horarios)
    return all(b - a >= gap for a, b in zip(ordenados, ordenados[1:]))


class TestAgendaPorConta:

    def test_janela_tomada_fica_para_a_proxima(self):
        ja_tem = [MEIO_DIA.replace(hour=11, minute=4)]
        (quando,) = scheduler.proximos_horarios(
            1, MEIO_DIA, sorteador=_fixo(0), horas=(11, 15, 19), gap=GAP,
            ocupados=ja_tem)
        assert quando.hour == 15

    def test_nao_empurra_para_colar_no_ocupado(self):
        """Empurrar para depois do ocupado daria posts a exatamente 3 h um do
        outro, dia apos dia: o relogio regular que o jitter existe para apagar."""
        ja_tem = [MEIO_DIA.replace(hour=11, minute=20)]
        (quando,) = scheduler.proximos_horarios(
            1, MEIO_DIA, sorteador=_fixo(-10), horas=(11, 15, 19), gap=GAP,
            ocupados=ja_tem)
        assert quando == MEIO_DIA.replace(hour=14, minute=50)

    def test_o_ultimo_post_empurra_o_proximo(self):
        postado = MEIO_DIA.replace(hour=10, minute=30)
        (quando,) = scheduler.proximos_horarios(
            1, MEIO_DIA.replace(hour=10, minute=40), sorteador=_fixo(0),
            horas=(11, 15, 19), gap=GAP, ocupados=[postado])
        assert quando == postado + GAP

    def test_o_teto_do_dia_conta_o_que_a_conta_ja_tem(self):
        ja_tem = [MEIO_DIA.replace(hour=h) for h in (11, 15, 19)]
        (quando,) = scheduler.proximos_horarios(
            1, MEIO_DIA, sorteador=_fixo(0), horas=(11, 15, 19), gap=GAP,
            teto_por_dia=3, ocupados=ja_tem)
        assert quando.date() == MEIO_DIA.date() + timedelta(days=1)

    def test_ocupado_sem_fuso_e_utc(self):
        """E como o SQLite devolve: a hora que foi gravada em UTC, sem fuso."""
        ja_tem_utc = MEIO_DIA.replace(hour=11, minute=4).astimezone(timezone.utc)
        (quando,) = scheduler.proximos_horarios(
            1, MEIO_DIA, sorteador=_fixo(0), horas=(11, 15, 19), gap=GAP,
            ocupados=[ja_tem_utc.replace(tzinfo=None)])
        assert quando.hour == 15


class TestTravaDoPostAtrasado:

    def test_cinco_vencidos_da_mesma_conta_nao_saem_juntos(self):
        vencidas = [_vencida(i, horas_atras=5 - i) for i in range(5)]
        triagem = scheduler.triar_vencidas(vencidas, NOITE, {}, gap=GAP,
                                           teto_por_dia=3)
        assert len(triagem.agora) == 1
        assert len(triagem.reagendar) == 4
        novos = list(triagem.reagendar.values())
        assert all(q >= NOITE + GAP for q in novos)
        assert _espacados([NOITE] + novos)

    def test_sai_o_mais_antigo(self):
        vencidas = [_vencida(1, horas_atras=1), _vencida(2, horas_atras=4)]
        assert scheduler.triar_vencidas(vencidas, NOITE, {}, gap=GAP).agora == ["p2"]

    def test_o_dia_normal_nao_muda(self):
        """Uma janela vence sozinha e o ultimo post foi ha mais de 3 h: sai."""
        triagem = scheduler.triar_vencidas(
            [_vencida(0, horas_atras=0)], NOITE,
            {"A": [NOITE - timedelta(hours=4)]}, gap=GAP)
        assert triagem.agora == ["p0"] and triagem.reagendar == {}

    def test_post_recente_segura_ate_o_primeiro(self):
        postado = NOITE - timedelta(hours=1)
        vencidas = [_vencida(i) for i in range(3)]
        triagem = scheduler.triar_vencidas(vencidas, NOITE, {"A": [postado]}, gap=GAP)
        assert triagem.agora == []
        assert len(triagem.reagendar) == 3
        assert all(q >= postado + GAP for q in triagem.reagendar.values())

    def test_o_teto_do_dia_segura(self):
        hoje = [NOITE.replace(hour=h) for h in (8, 11, 15)]
        triagem = scheduler.triar_vencidas([_vencida(0)], NOITE, {"A": hoje},
                                           gap=GAP, teto_por_dia=3)
        assert triagem.agora == []
        (quando,) = triagem.reagendar.values()
        assert quando.date() > NOITE.date()

    def test_uma_conta_nao_trava_a_outra(self):
        vencidas = [_vencida(0, "A", horas_atras=2), _vencida(1, "A"),
                    _vencida(2, "B")]
        triagem = scheduler.triar_vencidas(vencidas, NOITE, {}, gap=GAP)
        assert sorted(triagem.agora) == ["p0", "p2"]
        assert list(triagem.reagendar) == ["p1"]

    def test_os_reespalhados_respeitam_o_que_a_conta_ja_tem(self):
        amanha = (NOITE + timedelta(days=1)).replace(hour=11, minute=3)
        vencidas = [_vencida(i) for i in range(4)]
        triagem = scheduler.triar_vencidas(vencidas, NOITE, {"A": [amanha]},
                                           gap=GAP, teto_por_dia=3)
        assert _espacados([NOITE, amanha] + list(triagem.reagendar.values()))

    def test_o_jitter_continua(self):
        """Reespalhar nao pode virar hora cheia: e a mesma agenda, com o
        mesmo sorteio."""
        vencidas = [_vencida(i) for i in range(6)]
        sorteios = iter([-17, 9, 23, -4, 12, -21, 3, 8, -9, 14] * 10)
        triagem = scheduler.triar_vencidas(
            vencidas, NOITE, {}, gap=GAP, jitter=25,
            sorteador=lambda a, b: next(sorteios))
        minutos = {q.minute for q in triagem.reagendar.values()}
        assert minutos != {0}


class TestTravaNoLaco:
    """O mesmo, de ponta a ponta: banco, laco e driver de verdade (o
    `manual`, porque nenhuma conta tem credencial aqui)."""

    def _cinco_vencidas(self, ambiente):
        job_id = _projeto(ambiente, 5)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert _chama("POST", "/api/agendar", {"job_id": job_id,
                                               "account_id": conta["id"]}
                      ).json()["agendados"] == 5
        agora = datetime.now(timezone.utc)

        async def _t():
            async with db.tenant() as t:
                linhas = await t.all(db_models.Publication)
                for i, linha in enumerate(linhas):
                    linha.scheduled_at = agora - timedelta(hours=5 - i)
                await t.commit()
        corre(_t)
        return job_id, conta, agora

    def _fila(self):
        return _chama("GET", "/api/publicacoes").json()["publicacoes"]

    def test_cinco_posts_vencidos_da_mesma_conta_nao_saem_juntos(self, ambiente):
        """O teste que o plano pede para a 7.3."""
        job_id, _, agora = self._cinco_vencidas(ambiente)
        feito = corre(lambda: app_module._uma_volta_do_agendador(agora))
        assert len(feito["publicadas"]) == 1
        assert len(feito["reagendadas"]) == 4
        # Um corte foi entregue a fila manual; os outros quatro esperam.
        assert len(list((ambiente / job_id).glob("*.youtube.txt"))) == 1
        esperando = [datetime.fromisoformat(p["scheduled_at"]) for p in self._fila()
                     if p["status"] == "scheduled" and p["scheduled_at"]]
        assert len(esperando) == 4
        assert all(q >= agora + scheduler.espacamento_minimo() for q in esperando)
        assert _espacados(esperando, scheduler.espacamento_minimo())
        # E a volta seguinte, no mesmo minuto, nao publica nada.
        assert corre(lambda: app_module._uma_volta_do_agendador(agora))["publicadas"] == []

    def test_quando_a_hora_nova_chega_sai_um(self, ambiente):
        _, _, agora = self._cinco_vencidas(ambiente)
        corre(lambda: app_module._uma_volta_do_agendador(agora))
        proxima = min(datetime.fromisoformat(p["scheduled_at"]) for p in self._fila()
                      if p["status"] == "scheduled" and p["scheduled_at"])
        feito = corre(lambda: app_module._uma_volta_do_agendador(
            proxima + timedelta(minutes=1)))
        assert len(feito["publicadas"]) == 1 and feito["reagendadas"] == {}

    def test_a_fila_manual_nao_recebe_a_mesma_de_novo(self, ambiente):
        """Ate a 7.3 a linha entregue a fila manual voltava a `scheduled` com a
        hora antiga, e o laco a entregava de novo a cada minuto, para sempre."""
        job_id, _, agora = self._cinco_vencidas(ambiente)
        corre(lambda: app_module._uma_volta_do_agendador(agora))
        entregue = [p for p in self._fila()
                    if p["status"] == "scheduled" and not p["scheduled_at"]]
        assert len(entregue) == 1
        devidas = corre(lambda: publish_queue.devidas(agora + timedelta(minutes=1)))
        assert entregue[0]["id"] not in {d["id"] for d in devidas}

    def test_post_de_verdade_segura_o_proximo(self, ambiente):
        """O espacamento conta do ultimo post DE VERDADE da conta."""
        job_id = _projeto(ambiente, 2)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/agendar", {"job_id": job_id, "account_id": conta["id"]})
        agora = datetime.now(timezone.utc)
        primeira, segunda = sorted(self._fila(), key=lambda p: p["scheduled_at"])
        assert _chama("POST", f"/api/publicacoes/{primeira['id']}/publicado",
                      {"url": "https://youtube.com/shorts/abcdefghijk"}).status_code == 200

        async def _t():
            async with db.tenant() as t:
                (post,) = await t.all(db_models.PublicationPost)
                post.posted_at = agora - timedelta(hours=1)
                linha = await t.get(db_models.Publication, segunda["id"])
                linha.scheduled_at = agora - timedelta(minutes=5)
                await t.commit()
        corre(_t)
        feito = corre(lambda: app_module._uma_volta_do_agendador(agora))
        assert feito["publicadas"] == []
        (quando,) = feito["reagendadas"].values()
        assert quando >= agora + timedelta(hours=2)

    def test_agendar_dois_projetos_nao_cola_os_posts(self, ambiente):
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        for _ in range(2):
            job_id = _projeto(ambiente, 2)
            assert _chama("POST", "/api/agendar", {"job_id": job_id,
                                                   "account_id": conta["id"]}
                          ).json()["agendados"] == 2
        quando = [datetime.fromisoformat(p["scheduled_at"]) for p in self._fila()]
        assert len(quando) == 4
        assert _espacados(quando, scheduler.espacamento_minimo())
        por_dia = {}
        for q in quando:
            dia = q.astimezone().date()
            por_dia[dia] = por_dia.get(dia, 0) + 1
        assert max(por_dia.values()) <= scheduler.por_dia()

    def test_reservar_so_o_que_venceu(self, ambiente):
        """A triagem da outra instancia pode ter acabado de mandar a linha
        para amanha: ai ela nao sai hoje."""
        _, _, agora = self._cinco_vencidas(ambiente)
        (linha,) = [p for p in self._fila()][:1]

        async def _adiar():
            async with db.tenant() as t:
                l = await t.get(db_models.Publication, linha["id"])
                l.scheduled_at = agora + timedelta(days=1)
                await t.commit()
        corre(_adiar)
        assert corre(lambda: publish_queue.reservar(linha["id"], agora)) is False

    def test_a_hora_volta_com_fuso(self, ambiente):
        """O navegador le hora sem fuso como hora LOCAL: sem o `+00:00`, a
        agenda aparecia com a diferenca do fuso."""
        job_id = _projeto(ambiente, 1)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/agendar", {"job_id": job_id, "account_id": conta["id"]})
        (pub,) = self._fila()
        assert datetime.fromisoformat(pub["scheduled_at"]).tzinfo is not None
        assert datetime.fromisoformat(pub["created_at"]).tzinfo is not None
