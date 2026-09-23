"""O pipeline escrevendo no banco (Fase 3, bloco 3.3).

Fecha a pendencia registrada no fim da Fase 1 -- `sources` e `jobs` nunca eram
escritas -- e e pre-requisito da Fase 3: `publications` tem FK composta para
`clips`, entao sem linha de corte nao ha publicacao a gravar.

Dois contratos que estes testes guardam:

**Nada aqui pode derrubar um job.** O banco e o registro do pipeline, nao um
participante. Um engine quebrado devolve zero e imprime uma linha.

**O indice de palavra e derivado da transcricao, e a derivacao vem do disco.**
O `result` em memoria e `{'clips', 'cost_analysis'}` e nunca teve transcricao:
ler dali devolveria (None, None) para todo corte, e como a coluna aceita nulo
(video mudo) a tabela encheria de nulo sem um erro sequer.
"""
import asyncio
import json
import os
import uuid

import pytest

job_registry = pytest.importorskip("job_registry")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
app_module = pytest.importorskip("app")


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture()
def banco(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield
    db.reset_engine()


def _palavras(*trios):
    return [{"word": w, "start": s, "end": e} for w, s, e in trios]


# --------------------------------------------------------------------------- #
# Derivacao do indice de palavra
# --------------------------------------------------------------------------- #

class TestFaixaDePalavras:

    PALAVRAS = _palavras(("um", 0.0, 0.4), ("dois", 0.5, 0.9),
                         ("tres", 1.0, 1.4), ("quatro", 8.0, 8.4))

    def test_fim_exclusivo_como_fatia_de_lista(self):
        """Nao e escolha de estilo: o CHECK exige `end > start`, e com fim
        inclusivo um corte de uma palavra so teria `end == start`."""
        inicio, fim = job_registry.faixa_de_palavras(self.PALAVRAS, 0.0, 0.45)
        assert (inicio, fim) == (0, 1)
        assert [p["word"] for p in self.PALAVRAS[inicio:fim]] == ["um"]

    def test_palavra_que_encosta_no_corte_entra(self):
        """O corte e feito em segundos e quase nunca cai na fronteira exata de
        uma palavra. Exigir contencao cortaria a primeira e a ultima de todo
        corte."""
        assert job_registry.faixa_de_palavras(self.PALAVRAS, 0.3, 1.1) == (0, 3)

    def test_trecho_sem_fala_num_video_que_fala(self):
        assert job_registry.faixa_de_palavras(self.PALAVRAS, 3.0, 7.0) == (None, None)

    def test_video_mudo_nao_tem_faixa(self):
        assert job_registry.faixa_de_palavras([], 0.0, 30.0) == (None, None)

    def test_segundos_invalidos_nao_levantam(self):
        assert job_registry.faixa_de_palavras(self.PALAVRAS, None, "x") == (None, None)

    def test_palavra_corrompida_e_pulada_sem_derrubar(self):
        palavras = [{"word": "a", "start": 0.0, "end": 0.4},
                    {"word": "b"},
                    {"word": "c", "start": "nao e numero", "end": 1.0},
                    {"word": "d", "start": 1.1, "end": 1.5}]
        assert job_registry.faixa_de_palavras(palavras, 0.0, 2.0) == (0, 4)

    def test_a_faixa_sempre_passa_no_check_da_tabela(self):
        """Qualquer par que esta funcao devolve tem de ser gravavel. O contrario
        seria descobrir a incompatibilidade no meio do commit dos cortes."""
        for inicio_s, fim_s in ((0.0, 0.45), (0.3, 1.1), (3.0, 7.0), (7.9, 9.0)):
            a, b = job_registry.faixa_de_palavras(self.PALAVRAS, inicio_s, fim_s)
            assert (a is None and b is None) or (a >= 0 and b > a)


class TestPalavrasDoTranscript:

    def test_achata_os_segmentos(self):
        transcript = {"language": "pt", "segments": [
            {"words": _palavras(("a", 0, 1), ("b", 1, 2))},
            {"words": _palavras(("c", 2, 3))}]}
        assert len(job_registry.palavras_do_transcript(transcript)) == 3

    def test_video_mudo_do_pipeline(self):
        """A forma exata que o `main.py` grava quando nao ha fala."""
        assert job_registry.palavras_do_transcript(
            {"language": "none", "segments": []}) == []

    def test_transcript_ausente_ou_estranho(self):
        for entrada in (None, [], "texto", {"segments": None}, {"segments": [None]}):
            assert job_registry.palavras_do_transcript(entrada) == []

    def test_segmento_sem_words_e_pulado(self):
        transcript = {"segments": [{"text": "sem palavras"},
                                   {"words": _palavras(("a", 0, 1))}]}
        assert len(job_registry.palavras_do_transcript(transcript)) == 1


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #

class TestEscrita:

    def test_fonte_e_job_com_o_id_do_pipeline(self, banco):
        """O id do painel, o da pasta em disco e o do banco sao o mesmo. Um id
        proprio aqui obrigaria a manter um mapa."""
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("youtube", "https://y/1",
                                                     duration_ms=600_000)
            ok = await job_registry.registrar_job(job_id, src)
            async with db.tenant() as t:
                job = await t.get(db_models.Job, job_id)
                fonte = await t.get(db_models.Source, src)
                return ok, job.status, job.stage, fonte.adapter, fonte.duration_ms
        assert corre(_t) == (True, "queued", "ingest", "youtube", 600_000)

    def test_duracao_zero_vira_nulo(self, banco):
        """A coluna e anulavel porque "nao medida" e um estado real -- gravar
        zero diria que a fonte tem duracao zero."""
        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4", duration_ms=0)
            async with db.tenant() as t:
                return (await t.get(db_models.Source, src)).duration_ms
        assert corre(_t) is None

    def test_job_sem_fonte_nao_e_gravado(self, banco):
        """A FK composta recusaria de qualquer jeito; recusar antes evita o
        IntegrityError no log de todo job."""
        async def _t():
            return await job_registry.registrar_job(str(uuid.uuid4()), None)
        assert corre(_t) is False

    def test_marcar_job_traduz_o_marcador_de_estagio(self, banco):
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4")
            await job_registry.registrar_job(job_id, src)
            await job_registry.marcar_job(job_id, status="completed",
                                          marcador="05_06_render",
                                          timings={"total_s": 12})
            async with db.tenant() as t:
                job = await t.get(db_models.Job, job_id)
                return job.status, job.stage, job.timings_json, job.finished_at
        status, stage, timings, fim = corre(_t)
        assert (status, stage, timings) == ("completed", "reframe", {"total_s": 12})
        assert fim is not None

    def test_cancelado_e_cancelado_e_nao_falho(self, banco):
        """A coluna aceita `cancelled` desde a migracao 6d9f4b12e0c7. Gravar
        `failed` seria contar no registro permanente a mentira que o
        cancelamento existe para nao contar."""
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4")
            await job_registry.registrar_job(job_id, src)
            await job_registry.marcar_job(job_id, status="cancelled")
            async with db.tenant() as t:
                return (await t.get(db_models.Job, job_id)).status
        assert corre(_t) == "cancelled"

    def test_marcar_job_que_nao_existe_nao_levanta(self, banco):
        async def _t():
            return await job_registry.marcar_job(str(uuid.uuid4()), status="failed")
        assert corre(_t) is False

    def test_erro_longo_e_cortado(self, banco):
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4")
            await job_registry.registrar_job(job_id, src)
            await job_registry.marcar_job(job_id, status="failed", error="x" * 9000)
            async with db.tenant() as t:
                return len((await t.get(db_models.Job, job_id)).error)
        assert corre(_t) == 2000


class TestRegistrarClipes:

    TRANSCRIPT = {"language": "pt", "segments": [
        {"words": _palavras(("um", 0.0, 0.5), ("dois", 0.6, 1.0),
                            ("tres", 1.1, 1.5), ("quatro", 20.0, 20.5))}]}
    SHORTS = [
        {"start": 0.0, "end": 1.6, "predicted_score": 87,
         "source_window_id": "w1", "viral_hook_text": "olha isso",
         "video_title_for_youtube_short": "Titulo"},
        {"start": 19.9, "end": 21.0, "predicted_score": 40},
    ]

    def _gravar(self, shorts=None, transcript=None, arquivos=None):
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4")
            await job_registry.registrar_job(job_id, src)
            n = await job_registry.registrar_clipes(
                job_id, shorts if shorts is not None else self.SHORTS,
                transcript=transcript if transcript is not None else self.TRANSCRIPT,
                arquivos=arquivos)
            async with db.tenant() as t:
                cortes = await t.all(db_models.Clip,
                                     db_models.Clip.job_id == job_id)
                return n, sorted(cortes, key=lambda c: c.rubric_json["start_s"])
        return corre(_t)

    def test_grava_a_faixa_derivada_da_transcricao(self, banco):
        n, cortes = self._gravar()
        assert n == 2
        assert (cortes[0].start_word_idx, cortes[0].end_word_idx) == (0, 3)
        assert (cortes[1].start_word_idx, cortes[1].end_word_idx) == (3, 4)

    def test_os_segundos_exatos_ficam_na_rubrica(self, banco):
        """A secao 7 nao tem coluna de tempo por decisao (a secao 2 escolheu
        indice de palavra). Sem isto, o corte exato que gerou o arquivo so
        existiria no arquivo."""
        _, cortes = self._gravar()
        assert cortes[0].rubric_json["start_s"] == 0.0
        assert cortes[0].rubric_json["end_s"] == 1.6
        assert cortes[0].rubric_json["source_window_id"] == "w1"
        assert cortes[0].rubric_json["visual"] is False

    def test_score_fora_da_faixa_e_preso_em_vez_de_derrubar(self, banco):
        """O CHECK recusa fora de 0..100, e um modelo que devolveu 120
        derrubaria a gravacao dos OUTROS cortes do mesmo job."""
        n, cortes = self._gravar(shorts=[{"start": 0, "end": 1, "predicted_score": 120},
                                         {"start": 1, "end": 2, "predicted_score": -5}])
        assert n == 2
        assert sorted(c.score for c in cortes) == [0.0, 100.0]

    def test_score_ausente_ou_invalido_vira_nulo(self, banco):
        _, cortes = self._gravar(shorts=[{"start": 0, "end": 1},
                                         {"start": 1, "end": 2,
                                          "predicted_score": "muito bom"}])
        assert all(c.score is None for c in cortes)

    def test_video_mudo_grava_com_faixa_nula(self, banco):
        """O caso que motivou a migracao 4a7e1c30d8b2: sem ela, um corte de
        video mudo nao entrava no banco e portanto nao podia ser publicado."""
        n, cortes = self._gravar(
            transcript={"language": "none", "segments": []},
            shorts=[{"start": 0, "end": 30, "predicted_score": 70}])
        assert n == 1
        assert cortes[0].start_word_idx is None
        assert cortes[0].rubric_json["visual"] is True

    def test_render_key_vem_de_fora(self, banco):
        """Quem sabe qual e a versao ATUAL de um corte (limpo, com legenda,
        recortado) e o `app.py`, nao este modulo."""
        _, cortes = self._gravar(arquivos={0: "subtitled_1_v_clip_1.mp4",
                                           1: "v_clip_2.mp4"})
        assert cortes[0].render_key == "subtitled_1_v_clip_1.mp4"

    def test_gravar_duas_vezes_nao_duplica(self, banco):
        """Um job retomado depois de um redeploy roda o fim do pipeline de
        novo, e `publications` tem unicidade por corte, nao por conteudo."""
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("upload", "x.mp4")
            await job_registry.registrar_job(job_id, src)
            a = await job_registry.registrar_clipes(job_id, self.SHORTS,
                                                    transcript=self.TRANSCRIPT)
            b = await job_registry.registrar_clipes(job_id, self.SHORTS,
                                                    transcript=self.TRANSCRIPT)
            async with db.tenant() as t:
                return a, b, len(await t.all(db_models.Clip))
        assert corre(_t) == (2, 0, 2)

    def test_job_que_nao_existe_nao_grava_corte(self, banco):
        async def _t():
            return await job_registry.registrar_clipes(str(uuid.uuid4()),
                                                       self.SHORTS)
        assert corre(_t) == 0

    def test_lista_vazia_e_zero_sem_tocar_o_banco(self, banco):
        async def _t():
            return await job_registry.registrar_clipes("qualquer", [])
        assert corre(_t) == 0


class TestFalhaAberto:
    """Um banco quebrado devolve zero e imprime uma linha. Nunca levanta.

    O pipeline nunca dependeu do banco e nao passa a depender agora: perder o
    registro de um job e ruim, perder o job e pior.
    """

    @pytest.fixture()
    def banco_quebrado(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATABASE_URL",
                           f"sqlite+aiosqlite:///{tmp_path}/nao-existe/x.db")
        db.reset_engine()
        yield
        db.reset_engine()

    def test_registrar_fonte(self, banco_quebrado, capsys):
        assert corre(lambda: job_registry.registrar_fonte("upload", "x")) is None
        assert "Banco" in capsys.readouterr().out

    def test_registrar_job(self, banco_quebrado):
        assert corre(lambda: job_registry.registrar_job("j", "s")) is False

    def test_marcar_job(self, banco_quebrado):
        assert corre(lambda: job_registry.marcar_job("j", status="failed")) is False

    def test_registrar_clipes(self, banco_quebrado):
        assert corre(lambda: job_registry.registrar_clipes(
            "j", [{"start": 0, "end": 1}])) == 0


class TestParidadeComOApp:
    """Os dois lados da lista de estagios tem de se encontrar."""

    def test_todo_marcador_do_pipeline_tem_destino(self):
        for nome, _rotulo in app_module.PIPELINE_STAGES:
            assert nome in job_registry.ESTAGIO_DO_MARCADOR, (
                f"o estagio {nome} nao tem traducao para db_models.STAGES -- "
                "acrescente-o em job_registry.ESTAGIO_DO_MARCADOR")

    def test_todo_destino_existe_na_coluna(self):
        for destino in job_registry.ESTAGIO_DO_MARCADOR.values():
            assert destino in db_models.STAGES

    def test_todo_status_em_memoria_cabe_na_coluna(self):
        for destino in app_module._STATUS_NO_BANCO.values():
            assert destino in db_models.JOB_STATUSES

    def test_o_status_de_cancelado_nao_virou_falha(self):
        assert app_module._STATUS_NO_BANCO["cancelled"] == "cancelled"


class TestTranscriptDoJob:

    def test_le_do_metadata_em_disco_e_nao_do_result(self, tmp_path, monkeypatch):
        """O `result` em memoria e `{'clips', 'cost_analysis'}`: ler dali
        devolveria (None, None) para todo corte, em silencio."""
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        job_id = str(uuid.uuid4())
        pasta = tmp_path / job_id
        pasta.mkdir()
        (pasta / "v_metadata.json").write_text(json.dumps(
            {"shorts": [], "transcript": {"language": "pt", "segments": [
                {"words": [{"word": "a", "start": 0, "end": 1}]}]}}))
        transcript = app_module._transcript_do_job(job_id)
        assert len(job_registry.palavras_do_transcript(transcript)) == 1

    def test_sem_metadata_devolve_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        assert app_module._transcript_do_job(str(uuid.uuid4())) is None

    def test_metadata_corrompido_nao_levanta(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
        job_id = str(uuid.uuid4())
        pasta = tmp_path / job_id
        pasta.mkdir()
        (pasta / "v_metadata.json").write_text("{nao e json")
        assert app_module._transcript_do_job(job_id) is None


class TestAdapterDe:

    def test_url_conhecida_usa_o_adapter_dela(self):
        assert job_registry.adapter_de("https://www.youtube.com/watch?v=a") == "youtube"
        assert job_registry.adapter_de("https://www.twitch.tv/videos/1") == "twitch-vod"

    def test_sem_url_e_upload(self):
        assert job_registry.adapter_de(None) == "upload"
        assert job_registry.adapter_de("") == "upload"

    def test_url_de_arquivo_solto_e_direct(self):
        """`direct` e um link de terceiro que pode expirar; `upload` e arquivo
        que entrou pelo nosso endpoint e fica ate a limpeza. Sao coisas
        diferentes e a coluna existe para distingui-las (migracao 2f1b7c4ae903)."""
        assert job_registry.adapter_de("https://cdn.exemplo.com/a.mp4") == "direct"

    def test_o_que_nao_e_url_e_caminho_local_logo_upload(self):
        """Nao chega a acontecer -- `/api/process` ja recusou antes --, mas o
        que `sources` responde e o que se grava: um caminho em disco e a mesma
        coisa que um upload, e nao um link de terceiro."""
        assert job_registry.adapter_de("/tmp/x.mp4") == "upload"

    def test_todo_adapter_possivel_passa_no_check_da_coluna(self, banco):
        """Um id fora da lista so falharia ao gravar a linha, depois do
        download inteiro."""
        import sources

        async def _t():
            for adapter_id in list(sources.adapter_ids()) + ["direct", "upload"]:
                assert await job_registry.registrar_fonte(
                    adapter_id, f"entrada {adapter_id}") is not None
        corre(_t)


class TestSubmitGravaNoBanco:
    """O caminho de verdade: `/api/process` deixa linha em `sources` e `jobs`.

    Os testes acima exercitam o modulo; este exercita a ligacao. Sem ele, o
    bloco inteiro poderia estar correto e simplesmente nunca ser chamado.
    """

    def _submeter(self, tmp_path, monkeypatch):
        import httpx

        up = tmp_path / "uploads"
        out = tmp_path / "output"
        up.mkdir(); out.mkdir()
        monkeypatch.setattr(app_module, "UPLOAD_DIR", str(up))
        monkeypatch.setattr(app_module, "OUTPUT_DIR", str(out))
        monkeypatch.setattr(app_module, "jobs", {})

        async def _do():
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://testserver") as client:
                return await client.post(
                    "/api/process",
                    files={"file": ("v.mp4", b"\0" * 2048, "video/mp4")},
                    data={"acknowledged": "true"},
                    headers={"X-Gemini-Key": "k"})
        return asyncio.run(_do())

    def test_um_upload_deixa_fonte_e_job(self, banco, tmp_path, monkeypatch):
        r = self._submeter(tmp_path, monkeypatch)
        assert r.status_code == 200, r.text
        job_id = r.json()["job_id"]

        async def _t():
            async with db.tenant() as t:
                job = await t.get(db_models.Job, job_id)
                fontes = await t.all(db_models.Source)
                return job, fontes
        job, fontes = corre(_t)
        assert job is not None, "o job do pipeline nao chegou ao banco"
        assert job.status == "queued"
        assert len(fontes) == 1
        assert fontes[0].adapter == "upload"
        assert fontes[0].storage_key and fontes[0].storage_key.endswith("v.mp4")
        assert job.source_id == fontes[0].id

    def test_banco_quebrado_nao_impede_o_submit(self, tmp_path, monkeypatch):
        """A regra da camada, no caminho que importa: perder o registro de um
        job e ruim, perder o job e pior."""
        monkeypatch.setenv("DATABASE_URL",
                           f"sqlite+aiosqlite:///{tmp_path}/nao-existe/x.db")
        db.reset_engine()
        try:
            r = self._submeter(tmp_path, monkeypatch)
            assert r.status_code == 200, r.text
            assert r.json()["job_id"]
        finally:
            db.reset_engine()


class TestApagarJob:
    """Apagar o projeto apaga o registro dele -- menos o que ja foi publicado.

    O cascade das FKs compostas leva os cortes junto (no SQLite, so com o
    `PRAGMA foreign_keys=ON` do `db.py`), e a fonte sai quando fica orfa. Um
    corte PUBLICADO segura tudo: `publications` e `metrics` sao o historico que
    a calibracao le, e o cascade os levaria junto sem ninguem pedir.
    """

    def _job_com_cortes(self):
        job_id = str(uuid.uuid4())

        async def _t():
            src = await job_registry.registrar_fonte("youtube", "https://y/apagar")
            await job_registry.registrar_job(job_id, src)
            await job_registry.registrar_clipes(
                job_id, [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}])
            return src
        return job_id, corre(_t)

    def _contar(self, job_id, src):
        async def _t():
            async with db.tenant() as t:
                return (await t.get(db_models.Job, job_id) is not None,
                        len(await t.all(db_models.Clip, db_models.Clip.job_id == job_id)),
                        await t.get(db_models.Source, src) is not None)
        return corre(_t)

    def test_leva_job_cortes_e_fonte(self, banco):
        job_id, src = self._job_com_cortes()
        assert self._contar(job_id, src) == (True, 2, True)

        assert corre(lambda: job_registry.apagar_job(job_id)) is True
        assert self._contar(job_id, src) == (False, 0, False)

    def test_fonte_usada_por_outro_job_fica(self, banco):
        job_id, src = self._job_com_cortes()
        outro = str(uuid.uuid4())
        corre(lambda: job_registry.registrar_job(outro, src))

        assert corre(lambda: job_registry.apagar_job(job_id)) is True
        assert self._contar(job_id, src) == (False, 0, True)

    def test_corte_publicado_segura_o_registro(self, banco):
        job_id, src = self._job_com_cortes()

        async def _publicar():
            async with db.tenant() as t:
                corte = (await t.all(db_models.Clip, db_models.Clip.job_id == job_id))[0]
                conta = t.add(db_models.Account(platform="youtube", handle="@canal"))
                await t.flush()
                t.add(db_models.Publication(clip_id=corte.id, account_id=conta.id,
                                            driver="manual", status="published"))
                await t.commit()
        corre(_publicar)

        assert corre(lambda: job_registry.apagar_job(job_id)) is False
        assert self._contar(job_id, src) == (True, 2, True)

    def test_job_que_nao_existe_nao_levanta(self, banco):
        assert corre(lambda: job_registry.apagar_job(str(uuid.uuid4()))) is False

    def test_banco_quebrado_nao_levanta(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATABASE_URL",
                           f"sqlite+aiosqlite:///{tmp_path}/nao-existe/x.db")
        db.reset_engine()
        try:
            assert corre(lambda: job_registry.apagar_job("qualquer")) is False
        finally:
            db.reset_engine()
