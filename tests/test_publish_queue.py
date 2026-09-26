"""A fila de publicacao (Fase 3, bloco 3.5).

Junta o resolvedor da secao 6, as linhas de `clips` do bloco 3.3 e as contas de
plataforma. O que estes testes guardam:

**O chamador nunca escolhe o driver.** O corpo de `/api/publicar` aceita
`account_id` e nao `driver` -- deixar o painel mandar o driver reabriria por
fora a porta que o ADR-010 fechou, bastando um `driver: "browser"` numa
requisicao.

**A linha nasce antes do upload.** Gravar so no sucesso deixaria um upload que
morreu no meio sem rastro, e e a unicidade `(corte, conta)` que impede o retry
de publicar duas vezes.
"""
import asyncio
import json
import os
import uuid

import httpx
import pytest

app_module = pytest.importorskip("app")
db = pytest.importorskip("db")
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")

import publishers


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    """Banco proprio, saida propria e nenhuma credencial do YouTube herdada."""
    for nome in list(os.environ):
        if nome.startswith("YOUTUBE_"):
            monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield saida
    db.reset_engine()


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url, json=corpo)
    return asyncio.run(_do())


def _job_com_cortes(raiz, quantos=2):
    """Um job completo em disco E no banco, como o pipeline deixa."""
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = []
    for i in range(quantos):
        shorts.append({
            "start": float(i), "end": float(i) + 30.0,
            "predicted_score": 80 - i,
            "video_title_for_youtube_short": f"Corte {i + 1}",
            "video_description_for_tiktok": f"descricao {i + 1}",
        })
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps(
        {"shorts": shorts, "transcript": {"language": "none", "segments": []}}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    return job_id


# --------------------------------------------------------------------------- #
# Contas
# --------------------------------------------------------------------------- #

class TestContas:

    def test_cria_lista_e_apaga(self):
        r = _chama("POST", "/api/contas",
                   {"platform": "youtube", "handle": "meu-canal"})
        assert r.status_code == 200, r.text
        conta = r.json()
        assert conta["driver_pref"] == "auto"
        lista = _chama("GET", "/api/contas").json()["contas"]
        assert [c["handle"] for c in lista] == ["meu-canal"]
        assert _chama("DELETE", f"/api/contas/{conta['id']}").status_code == 200
        assert _chama("GET", "/api/contas").json()["contas"] == []

    def test_a_conta_nasce_apontando_para_o_cofre_e_nao_para_um_token(self):
        """A secao 7: "aponta pra um cofre, nunca guarda o token na linha"."""
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert conta["credentials_ref"] == "vault://env/youtube/canal"

    def test_diz_qual_driver_atenderia_agora(self):
        """E o que o painel usa para explicar por que um corte foi para a fila
        manual: sem credencial, sem quota, ou porque a conta pediu."""
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert conta["driver_agora"] == "manual"
        assert conta["capabilities"]["youtube-api"] == "none"

    def test_com_credencial_o_driver_muda(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "i")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "s")
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "r")
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert conta["driver_agora"] == "youtube-api"

    def test_plataforma_e_preferencia_sao_validadas(self):
        assert _chama("POST", "/api/contas",
                      {"platform": "orkut", "handle": "x"}).status_code == 400
        assert _chama("POST", "/api/contas",
                      {"platform": "youtube", "handle": "x",
                       "driver_pref": "ftp"}).status_code == 400

    def test_handle_vazio_e_recusado(self):
        assert _chama("POST", "/api/contas",
                      {"platform": "youtube", "handle": "   "}).status_code == 400

    def test_conta_repetida_e_recusada(self):
        _chama("POST", "/api/contas", {"platform": "youtube", "handle": "c"})
        r = _chama("POST", "/api/contas", {"platform": "youtube", "handle": "c"})
        assert r.status_code == 400
        assert "ja existe" in r.json()["detail"]

    def test_endereco_de_cofre_torto_e_recusado_na_criacao(self):
        """E nao na hora de publicar: um endereco errado descoberto no meio de
        um lote e um corte que nao subiu por um erro de digitacao feito dias
        antes."""
        r = _chama("POST", "/api/contas",
                   {"platform": "youtube", "handle": "c",
                    "credentials_ref": "nao-e-endereco"})
        assert r.status_code == 400
        assert "cofre" in r.json()["detail"]

    def test_apagar_diz_quantas_publicacoes_foram_junto(self, ambiente):
        """A FK de `publications` e ON DELETE CASCADE (secao 7): apagar a conta
        leva o historico dela. E o desenho, mas quem clica precisa saber."""
        job_id = _job_com_cortes(ambiente, 2)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/publicar",
               {"job_id": job_id, "account_id": conta["id"]})
        r = _chama("DELETE", f"/api/contas/{conta['id']}")
        assert r.status_code == 200
        assert r.json()["publicacoes_apagadas"] == 2
        assert _chama("GET", "/api/publicacoes").json()["publicacoes"] == []

    def test_apagar_conta_sem_publicacao_diz_zero(self):
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        assert _chama("DELETE", f"/api/contas/{conta['id']}"
                      ).json()["publicacoes_apagadas"] == 0

    def test_apagar_o_que_nao_existe_e_404(self):
        assert _chama("DELETE", f"/api/contas/{uuid.uuid4()}").status_code == 404

    def test_a_listagem_traz_a_quota_do_youtube(self):
        corpo = _chama("GET", "/api/contas").json()
        assert corpo["quota_youtube"]["uploads_por_dia"] == 100


# --------------------------------------------------------------------------- #
# Publicar
# --------------------------------------------------------------------------- #

class TestPublicar:

    def _conta(self, **kw):
        corpo = {"platform": "youtube", "handle": "canal"}
        corpo.update(kw)
        return _chama("POST", "/api/contas", corpo).json()

    def test_sem_credencial_o_corte_vai_para_a_fila_manual(self, ambiente):
        """O caminho padrao inteiro em um teste: resolve para `manual`, grava a
        linha como `scheduled` e deixa a legenda ao lado do corte."""
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        r = _chama("POST", "/api/publicar",
                   {"job_id": job_id, "account_id": conta["id"]})
        assert r.status_code == 200, r.text
        resultado = r.json()["resultados"][0]
        assert resultado["ok"] is True
        assert resultado["driver"] == "manual"
        assert resultado["status"] == "scheduled"
        legenda = ambiente / job_id / "v_clip_1.youtube.txt"
        assert legenda.exists()
        assert legenda.read_text(encoding="utf-8").startswith("Corte 1\n\n")

    def test_publica_so_os_indices_pedidos(self, ambiente):
        job_id = _job_com_cortes(ambiente, 3)
        conta = self._conta()
        r = _chama("POST", "/api/publicar",
                   {"job_id": job_id, "account_id": conta["id"], "clips": [2]})
        assert [x["clip_index"] for x in r.json()["resultados"]] == [2]

    def test_o_corpo_nao_aceita_driver(self, ambiente):
        """A trava do ADR-010 pelo lado da API: mandar `driver` nao muda nada,
        porque o campo nao existe -- quem escolhe e `publishers.resolve`."""
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        r = _chama("POST", "/api/publicar",
                   {"job_id": job_id, "account_id": conta["id"],
                    "driver": "browser"})
        assert r.status_code == 200
        assert r.json()["resultados"][0]["driver"] == "manual"

    def test_publicar_duas_vezes_e_recusado(self, ambiente):
        """A unicidade `(corte, conta)` do schema, exercitada pelo caminho de
        verdade: e o que impede um retry de postar o mesmo corte duas vezes."""
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        corpo = {"job_id": job_id, "account_id": conta["id"]}
        assert _chama("POST", "/api/publicar", corpo).json()["publicados"] == 1
        segundo = _chama("POST", "/api/publicar", corpo).json()["resultados"][0]
        assert segundo["ok"] is False
        assert "ja foi" in segundo["detail"]

    def test_um_corte_que_falha_nao_derruba_o_lote(self, ambiente):
        """Publicar em lote e ter metade dele desaparecer por causa do terceiro
        corte seria pior que lento."""
        job_id = _job_com_cortes(ambiente, 3)
        conta = self._conta()
        os.remove(ambiente / job_id / "v_clip_2.mp4")
        corpo = _chama("POST", "/api/publicar",
                       {"job_id": job_id, "account_id": conta["id"]}).json()
        assert corpo["publicados"] == 2
        assert len(corpo["resultados"]) == 3
        assert corpo["resultados"][1]["ok"] is False

    def test_corte_fora_do_banco_e_dito_pelo_nome(self, ambiente):
        """Job anterior ao bloco 3.3. Um 404 no lote inteiro esconderia que os
        outros cortes estavam prontos."""
        job_id = _job_com_cortes(ambiente, 2)

        async def _apagar():
            async with db.tenant() as t:
                for corte in await t.all(db_models.Clip):
                    if (corte.rubric_json or {}).get("clip_index") == 1:
                        await t.session.delete(corte)
                await t.commit()
        corre(_apagar)
        conta = self._conta()
        corpo = _chama("POST", "/api/publicar",
                       {"job_id": job_id, "account_id": conta["id"]}).json()
        assert corpo["publicados"] == 1
        assert "reprocesse" in corpo["resultados"][1]["detail"]

    def test_job_e_conta_inexistentes(self, ambiente):
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        assert _chama("POST", "/api/publicar",
                      {"job_id": str(uuid.uuid4()),
                       "account_id": conta["id"]}).status_code == 404
        assert _chama("POST", "/api/publicar",
                      {"job_id": job_id,
                       "account_id": str(uuid.uuid4())}).status_code == 404

    def test_indice_que_nao_existe(self, ambiente):
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        assert _chama("POST", "/api/publicar",
                      {"job_id": job_id, "account_id": conta["id"],
                       "clips": [99]}).status_code == 404

    def test_render_key_passa_a_apontar_para_o_arquivo_publicado(self, ambiente):
        """O corte pode ter ganhado legenda desde o fim do job, e e o arquivo
        atual que vai ao ar."""
        job_id = _job_com_cortes(ambiente, 1)
        (ambiente / job_id / "subtitled_9_v_clip_1.mp4").write_bytes(b"\x01" * 9)
        conta = self._conta()
        _chama("POST", "/api/publicar",
               {"job_id": job_id, "account_id": conta["id"]})

        async def _t():
            async with db.tenant() as t:
                return [c.render_key for c in await t.all(db_models.Clip)]
        assert corre(_t) == ["subtitled_9_v_clip_1.mp4"]

    def test_dry_run_nao_escreve_legenda(self, ambiente):
        job_id = _job_com_cortes(ambiente, 1)
        conta = self._conta()
        _chama("POST", "/api/publicar",
               {"job_id": job_id, "account_id": conta["id"], "dry_run": True})
        assert not (ambiente / job_id / "v_clip_1.youtube.txt").exists()


# --------------------------------------------------------------------------- #
# A fila
# --------------------------------------------------------------------------- #

class TestFila:

    def _publicar_um(self, ambiente):
        job_id = _job_com_cortes(ambiente, 1)
        conta = _chama("POST", "/api/contas",
                       {"platform": "youtube", "handle": "canal"}).json()
        _chama("POST", "/api/publicar",
               {"job_id": job_id, "account_id": conta["id"]})
        return _chama("GET", "/api/publicacoes").json()["publicacoes"][0]

    def test_a_fila_mostra_corte_conta_e_driver(self, ambiente):
        linha = self._publicar_um(ambiente)
        assert linha["status"] == "scheduled"
        assert linha["driver"] == "manual"
        assert linha["account"]["handle"] == "canal"
        assert linha["clip"]["index"] == 0
        assert linha["clip"]["title"] == "Corte 1"

    def test_filtra_por_status(self, ambiente):
        self._publicar_um(ambiente)
        assert _chama("GET", "/api/publicacoes?status=scheduled").json()["publicacoes"]
        assert _chama("GET", "/api/publicacoes?status=published").json()["publicacoes"] == []

    def test_ja_publiquei_e_o_unico_caminho_para_published(self, ambiente):
        """O driver `manual` nao tem como saber que a pessoa apertou publicar.
        Dizer `published` sozinho seria a unica mentira capaz de fazer o painel
        contar como postado um corte que ninguem postou."""
        linha = self._publicar_um(ambiente)
        r = _chama("POST", f"/api/publicacoes/{linha['id']}/publicado")
        assert r.status_code == 200
        atual = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        assert atual["status"] == "published"

    def test_cancelar_tira_da_fila(self, ambiente):
        linha = self._publicar_um(ambiente)
        assert _chama("DELETE", f"/api/publicacoes/{linha['id']}").status_code == 200
        atual = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        assert atual["status"] == "cancelled"

    def test_o_que_ja_foi_publicado_nao_volta_para_a_fila(self, ambiente):
        """Cancelar uma linha `published` sugeriria que o post sumiu da
        plataforma, e ele nao sumiu."""
        linha = self._publicar_um(ambiente)
        _chama("POST", f"/api/publicacoes/{linha['id']}/publicado")
        r = _chama("DELETE", f"/api/publicacoes/{linha['id']}")
        assert r.status_code == 400
        assert "apague o post" in r.json()["detail"]

    def test_publicacao_inexistente(self):
        falso = str(uuid.uuid4())
        assert _chama("POST", f"/api/publicacoes/{falso}/publicado").status_code == 404
        assert _chama("DELETE", f"/api/publicacoes/{falso}").status_code == 404

    def test_a_rota_do_pacote_nao_foi_engolida_pela_do_id(self, ambiente):
        """`/api/publicacoes/dias` e `/pacote` sao anteriores a
        `/api/publicacoes/{pub_id}` e precisam continuar alcancaveis."""
        _job_com_cortes(ambiente, 1)
        assert _chama("GET", "/api/publicacoes/dias").status_code == 200
        assert _chama("GET", "/api/publicacoes/pacote").status_code == 200


class TestUploadNaoTrancaOLoop:

    def _corpo_de_publicar(self):
        """A arvore sintatica de `publish_queue.publicar`.

        Le o AST, e nao o texto: a primeira versao deste teste procurava
        "asyncio.run" na fonte e quebrava por causa do COMENTARIO que explica
        por que ele nao pode estar ali.
        """
        import ast
        import pathlib as _p
        arvore = ast.parse(_p.Path("publish_queue.py").read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.AsyncFunctionDef) and no.name == "publicar":
                return no
        raise AssertionError("publish_queue.publicar mudou de forma")

    def _chamadas(self, no):
        import ast
        nomes = set()
        for filho in ast.walk(no):
            if isinstance(filho, ast.Call):
                nomes.add(ast.unparse(filho.func))
        return nomes

    def test_publish_vai_para_um_executor(self):
        """`publish()` e sincrono (ADR-010) e sobe arquivo pela rede. Rodar no
        loop travaria o polling de todo mundo durante o upload."""
        chamadas = self._chamadas(self._corpo_de_publicar())
        assert any("run_in_executor" in c for c in chamadas)

    def test_e_o_banco_nao_vai(self):
        """Um `asyncio.run` dentro da thread criaria um SEGUNDO loop, e o
        engine async do SQLAlchemy pertence ao loop que o criou."""
        chamadas = self._chamadas(self._corpo_de_publicar())
        assert "asyncio.run" not in chamadas
