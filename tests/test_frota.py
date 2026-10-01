"""A frota de aparelhos pelo motor inteiro (etapa 7.9, ADR-016): a API, o banco,
o driver e um celular imitado atras do servidor do adb falso.

O que estes testes guardam:

**A frota nasce desligada**, e ligar pede que a pessoa leia os limites.

**O automatico tem tres travas, e nenhuma e padrao**: o consentimento da conta
(o banco recusa automatico sem ele), um roteiro ensinado e um ensaio passando
neste aparelho. Sem as tres, a conta so recebe a entrega -- o video no app, e a
pessoa toca em publicar.

**Cada aparelho separado**: uma conta num aparelho so, um app por conta em
cada aparelho, e um tenant nao alcanca o aparelho do outro.
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
db_models = pytest.importorskip("db_models")
db_seed = pytest.importorskip("db_seed")
job_registry = pytest.importorskip("job_registry")
publish_queue = pytest.importorskip("publish_queue")

import frota
import frota_aparelho
import frota_limite
import frota_roteiro
import publishers
from adb_falso import (ADBKEYBOARD, COMPARTILHAR, GBOARD, AparelhoFalso, CelularComTelas,
                       ServidorFalso)

SERIAL = "R9TW12345AB"


def corre(coro_fn):
    return asyncio.run(coro_fn())


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    for nome in list(os.environ):
        if nome.startswith(("YOUTUBE_", "TIKTOK_")):
            monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    saida = tmp_path / "saida"
    saida.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(saida))
    monkeypatch.setattr(app_module, "jobs", {})
    # Sem esperar segundos de verdade pela tela imitada.
    for modulo in (frota, frota_aparelho, frota_roteiro):
        monkeypatch.setattr(modulo, "_dormir", lambda s: None)
    teste = tmp_path / "teste.mp4"
    teste.write_bytes(b"\x00\x00\x00\x18ftypmp42video-de-teste")
    monkeypatch.setattr(frota, "video_de_teste", lambda: str(teste))
    auth.esquecer_segredo()
    auth.limpar_tentativas()
    db.reset_engine()
    asyncio.run(db_seed.seed())
    frota._ENSINOS.clear()
    frota._ENSAIOS.clear()
    frota._ESTADOS.clear()
    yield saida
    for device_id in list(frota._ENSINOS):
        frota.encerrar_ensino(device_id)
    db.reset_engine()
    auth.esquecer_segredo()
    db.usar_tenant(db.SELF_HOST_TENANT_ID)


@pytest.fixture
def adb(monkeypatch):
    with ServidorFalso() as s:
        monkeypatch.setenv("ADB_SERVER", f"127.0.0.1:{s.porta}")
        celular = CelularComTelas(s.acrescentar(AparelhoFalso(SERIAL, modelo="SM_A145M")))
        yield s, celular


def _chama(metodo, url, corpo=None, token=None):
    async def _do():
        cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(metodo, url, json=corpo, headers=cabecalhos)
    return asyncio.run(_do())


def _ligar(token=None):
    r = _chama("PUT", "/api/frota", {"ligada": True, "entendi": True}, token=token)
    assert r.status_code == 200, r.text


def _aparelho(token=None, serial=SERIAL, nome="Celular 1"):
    r = _chama("POST", "/api/aparelhos", {"serial": serial, "nome": nome}, token=token)
    assert r.status_code == 200, r.text
    return r.json()


def _conta(plataforma="instagram", handle="@corte", token=None):
    r = _chama("POST", "/api/contas", {"platform": plataforma, "handle": handle}, token=token)
    assert r.status_code == 200, r.text
    return r.json()


def _contas():
    return {c["handle"]: c for c in _chama("GET", "/api/contas").json()["contas"]}


def _job_com_corte(raiz):
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = [{"start": 0.0, "end": 30.0, "predicted_score": 80,
               "video_title_for_youtube_short": "O corte do dia",
               "video_description_for_instagram": "Descricao com acento: ação"}]
    (pasta / "v_clip_1.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 512)
    (pasta / "v_metadata.json").write_text(json.dumps(
        {"shorts": shorts, "transcript": {"language": "none", "segments": []}}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    corre(_t)
    return job_id


def _corte_e_conta(job_id, handle):
    async def _t():
        async with db.tenant() as t:
            corte = (await t.all(db_models.Clip, db_models.Clip.job_id == job_id))[0]
            conta = (await t.all(db_models.Account, db_models.Account.handle == handle))[0]
            return corte, conta
    return corre(_t)


def _ensinar(device_id):
    """O ensino pelo painel, como a pessoa faria: Avancar, o campo da legenda,
    e marcar Compartilhar sem tocar."""
    r = _chama("POST", f"/api/aparelhos/{device_id}/ensino", {"plataforma": "instagram"})
    assert r.status_code == 200, r.text
    for x, y in ((950, 140), (500, 400)):
        r = _chama("POST", f"/api/aparelhos/{device_id}/ensino/tocar",
                   {"x": x / 1080, "y": y / 2400})
        assert r.status_code == 200, r.text
    r = _chama("POST", f"/api/aparelhos/{device_id}/ensino/publicar",
               {"x": 500 / 1080, "y": 2250 / 2400})
    assert r.status_code == 200, r.text
    assert r.json()["pronto"] is True
    r = _chama("POST", f"/api/aparelhos/{device_id}/ensino/salvar", {})
    assert r.status_code == 200, r.text
    return r.json()


def _ensaiar(device_id):
    """Pede o ensaio e espera a tarefa dele no MESMO laco: cada `_chama` roda
    num laco proprio, que fecha no fim e levaria a tarefa junto."""
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            r = await c.post(f"/api/aparelhos/{device_id}/ensaio", json={"plataforma": "instagram"})
            assert r.status_code == 200, r.text
            assert r.json()["estado"] == "rodando"
            await asyncio.wait_for(asyncio.gather(*list(frota._TAREFAS)), timeout=30)
    asyncio.run(_do())
    aparelho = _chama("GET", f"/api/aparelhos/{device_id}?vivo=0").json()
    assert (aparelho["ensaio"] or {}).get("estado") in ("passou", "falhou"), aparelho["ensaio"]
    return aparelho


# --------------------------------------------------------------------------- #
# Ligar a frota
# --------------------------------------------------------------------------- #

class TestLigar:

    def test_nasce_desligada_e_sem_falar_com_o_adb(self):
        r = _chama("GET", "/api/frota")
        assert r.status_code == 200
        assert r.json()["ligada"] is False
        assert r.json()["adb"] == {"alcancado": False}
        assert r.json()["limite"] == {"padrao": 3, "maximo": 15}

    def test_ligar_pede_que_leia_os_limites(self):
        r = _chama("PUT", "/api/frota", {"ligada": True})
        assert r.status_code == 400 and "leu os limites" in r.json()["detail"]
        _ligar()
        assert _chama("GET", "/api/frota").json()["ligada"] is True
        assert _chama("PUT", "/api/frota", {"ligada": False}).json()["ligada"] is False

    def test_desligada_nao_cadastra_nem_toca(self, adb):
        r = _chama("POST", "/api/aparelhos", {"serial": SERIAL, "nome": "x"})
        assert r.status_code == 409 and "desligada" in r.json()["detail"]

    def test_o_motor_antigo_e_reconhecido_pela_marca(self):
        assert _chama("GET", "/api/config").json()["frota"] is True


# --------------------------------------------------------------------------- #
# Aparelhos
# --------------------------------------------------------------------------- #

class TestAparelhos:

    def test_o_adb_e_os_aparelhos_vistos(self, adb):
        _ligar()
        frota_ = _chama("GET", "/api/frota").json()
        assert frota_["adb"]["alcancado"] is True and frota_["adb"]["versao"] == 41
        assert [v["serial"] for v in frota_["vistos"]] == [SERIAL]
        aparelho = _aparelho()
        assert aparelho["nome"] == "Celular 1" and aparelho["tipo"] == "cabo"
        assert _chama("GET", "/api/frota").json()["vistos"] == []

    def test_estado_ao_vivo(self, adb):
        servidor, celular = adb
        celular.ap.responder(r'^echo "@@props"', "@@props\nsamsung\nSM-A145M\n13\n33\nR9\n"
                             "@@pacotes\npackage:com.instagram.android\n"
                             "@@versoes\ncom.instagram.android versionName=312.0\n@@fim\n")
        _ligar()
        aparelho = _aparelho()
        detalhe = _chama("GET", f"/api/aparelhos/{aparelho['id']}").json()
        assert detalhe["estado"]["no_ar"] is True
        assert detalhe["estado"]["apps"]["instagram"]["versao"] == "312.0"

    def test_aparelho_fora_do_ar_aparece_como_tal(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        celular.ap.estado = "offline"
        frota._ESTADOS.clear()
        estado = _chama("GET", f"/api/aparelhos/{aparelho['id']}").json()["estado"]
        assert estado["no_ar"] is False and "offline" in estado["erro"]

    def test_serial_repetido_e_invalido(self, adb):
        _ligar()
        _aparelho()
        r = _chama("POST", "/api/aparelhos", {"serial": SERIAL, "nome": "outro"})
        assert r.status_code == 409
        for serial in ("", "a b", "x\nhost:kill"):
            assert _chama("POST", "/api/aparelhos",
                          {"serial": serial, "nome": "x"}).status_code == 400

    def test_aparelho_de_rede_guarda_o_endereco(self, adb):
        _ligar()
        r = _chama("POST", "/api/aparelhos", {"endereco": "192.168.0.9:5555", "nome": "Rede",
                                              "tipo": "rede"})
        assert r.status_code == 200, r.text
        assert r.json()["serial"] == "192.168.0.9:5555"
        assert r.json()["endereco"] == "192.168.0.9:5555"

    def test_tela_e_controle_remoto(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        tela = _chama("GET", f"/api/aparelhos/{aparelho['id']}/tela").json()
        assert tela["imagem"].startswith("data:image/") and tela["largura"] == 1080
        celular.atual = "legenda"
        r = _chama("POST", f"/api/aparelhos/{aparelho['id']}/tecla", {"tecla": "voltar"})
        assert r.status_code == 200 and celular.atual == "editor"
        r = _chama("POST", f"/api/aparelhos/{aparelho['id']}/toque",
                   {"x": 950 / 1080, "y": 140 / 2400})
        assert r.status_code == 200 and celular.atual == "legenda"
        assert _chama("POST", f"/api/aparelhos/{aparelho['id']}/tecla",
                      {"tecla": "formatar"}).status_code == 502

    def test_apagar_leva_o_historico(self, adb, tmp_path):
        _ligar()
        aparelho = _aparelho()
        pasta = tmp_path / "dados" / "frota" / aparelho["id"]
        pasta.mkdir(parents=True)
        assert _chama("DELETE", f"/api/aparelhos/{aparelho['id']}").status_code == 200
        assert not pasta.exists()
        assert _chama("GET", f"/api/aparelhos/{aparelho['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# As contas de cada aparelho
# --------------------------------------------------------------------------- #

class TestContas:

    def test_entregar_e_o_padrao_e_vira_o_driver_da_conta(self, adb):
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        assert _contas()["@corte"]["driver_agora"] == "manual"
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
                   {"account_id": conta["id"]})
        assert r.status_code == 200, r.text
        ligada = r.json()["contas"][0]
        assert (ligada["modo"], ligada["limite"], ligada["consentiu_em"]) == ("entregar", 3, None)
        lista = _contas()["@corte"]
        assert lista["driver_agora"] == "aparelho"
        assert lista["aparelho"]["nome"] == "Celular 1"

    def test_frota_desligada_devolve_a_conta_ao_caminho_de_antes(self, adb):
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": conta["id"]})
        _chama("PUT", "/api/frota", {"ligada": False})
        assert _contas()["@corte"]["driver_agora"] == "manual"

    def test_um_app_por_aparelho(self, adb):
        _ligar()
        aparelho = _aparelho()
        a, b = _conta(handle="@a"), _conta(handle="@b")
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": a["id"]})
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": b["id"]})
        assert r.status_code == 409 and "uma conta por app" in r.json()["detail"]
        tiktok = _conta("tiktok", "@t")
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": tiktok["id"]})
        assert r.status_code == 200 and len(r.json()["contas"]) == 2

    def test_a_conta_muda_de_aparelho(self, adb):
        servidor, _ = adb
        servidor.acrescentar(AparelhoFalso("OUTRO1"))
        _ligar()
        um, dois = _aparelho(), _aparelho(serial="OUTRO1", nome="Celular 2")
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{um['id']}/contas", {"account_id": conta["id"]})
        _chama("PUT", f"/api/aparelhos/{dois['id']}/contas", {"account_id": conta["id"]})
        assert _chama("GET", f"/api/aparelhos/{um['id']}?vivo=0").json()["contas"] == []
        assert _contas()["@corte"]["aparelho"]["nome"] == "Celular 2"

    @pytest.mark.parametrize("limite", [0, 16, "muito"])
    def test_limite_fora_da_faixa(self, adb, limite):
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
                   {"account_id": conta["id"], "limite": limite})
        assert r.status_code == 400

    def test_automatico_pede_consentimento_e_ensaio(self, adb):
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        url = f"/api/aparelhos/{aparelho['id']}/contas"
        r = _chama("PUT", url, {"account_id": conta["id"], "modo": "automatico"})
        assert r.status_code == 400 and "consentimento" in r.json()["detail"]
        r = _chama("PUT", url, {"account_id": conta["id"], "modo": "automatico",
                                "consentimento": True})
        assert r.status_code == 409 and "ensaie" in r.json()["detail"]

    def test_o_banco_recusa_automatico_sem_consentimento(self, adb):
        """A metade do consentimento que mora no banco: um CHECK."""
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                t.add(db_models.DeviceAccount(device_id=aparelho["id"], account_id=conta["id"],
                                              platform="instagram", mode="automatico"))
                await t.commit()
        with pytest.raises(IntegrityError):
            corre(_t)

    def test_plataforma_sem_app_nao_entra(self, adb, monkeypatch):
        import plataformas
        monkeypatch.setattr(plataformas, "NO_APARELHO", ("youtube",))
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": conta["id"]})
        assert r.status_code == 400 and "não tem app" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# Ensinar, ensaiar e o automatico
# --------------------------------------------------------------------------- #

class TestEnsinoEEnsaio:

    def test_ensinar_grava_o_roteiro_sem_publicar(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        r = _chama("POST", f"/api/aparelhos/{aparelho['id']}/ensino", {"plataforma": "instagram"})
        assert r.status_code == 200, r.text
        estado = r.json()
        assert estado["digita"] is True and estado["imagem"].startswith("data:image/")
        assert any(e["rotulo"] == "Avançar" for e in estado["elementos"])
        assert "ClipsShareHandlerActivity" in celular.aberturas[0]
        # Durante o ensino o aparelho esta reservado: um toque remoto espera.
        assert _chama("POST", f"/api/aparelhos/{aparelho['id']}/tecla",
                      {"tecla": "voltar"}).status_code == 409
        _chama("DELETE", f"/api/aparelhos/{aparelho['id']}/ensino")

        salvo = _ensinar(aparelho["id"])
        roteiro = salvo["roteiro"] if "roteiro" in salvo else salvo["roteiros"]["instagram"]
        assert [p["tipo"] for p in roteiro["passos"]] == ["tocar", "legenda", "publicar"]
        assert roteiro["versao"] == "312.0.0.39.120" and roteiro["ensaio_ok"] is None
        assert COMPARTILHAR["rid"] not in celular.tocados
        assert celular.digitado == frota_roteiro.LEGENDA_DE_TESTE
        # O teclado da pessoa voltou, e o video de teste saiu da galeria.
        assert celular.teclado == GBOARD
        assert any(c.startswith("rm -f '/sdcard/Movies/Virtu Clips/vc-teste-")
                   for c in celular.ap.executados)
        assert frota_aparelho.ocupado_com(SERIAL) is None

    def test_ensaio_passa_e_nao_publica(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        celular.tocados.clear()
        depois = _ensaiar(aparelho["id"])
        assert depois["ensaio"]["estado"] == "passou", depois["ensaio"]
        assert depois["roteiros"]["instagram"]["ensaio_ok"] is True
        assert COMPARTILHAR["rid"] not in celular.tocados
        assert celular.digitado == frota.LEGENDA_DO_ENSAIO
        assert celular.teclado == GBOARD

    def test_ensaio_sem_adbkeyboard_falha_dizendo_por_que(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        celular.adbkeyboard = False
        depois = _ensaiar(aparelho["id"])
        assert depois["ensaio"]["estado"] == "falhou"
        assert "ADBKeyBoard" in depois["ensaio"]["detalhe"]
        assert depois["roteiros"]["instagram"]["ensaio_ok"] is False

    def test_consentida_e_ensaiada_a_conta_vira_automatica(self, adb):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        _ensaiar(aparelho["id"])
        conta = _conta()
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
                   {"account_id": conta["id"], "modo": "automatico", "consentimento": True})
        assert r.status_code == 200, r.text
        assert r.json()["contas"][0]["consentiu_em"]
        assert _contas()["@corte"]["driver_agora"] == "aparelho-auto"
        # Voltar a entregar retira o consentimento.
        r = _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
                   {"account_id": conta["id"], "modo": "entregar"})
        assert r.json()["contas"][0]["consentiu_em"] is None
        assert _contas()["@corte"]["driver_agora"] == "aparelho"

    def test_ensinar_de_novo_zera_o_ensaio(self, adb):
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        _ensaiar(aparelho["id"])
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
               {"account_id": conta["id"], "modo": "automatico", "consentimento": True})
        _ensinar(aparelho["id"])
        assert _contas()["@corte"]["driver_agora"] == "aparelho"


# --------------------------------------------------------------------------- #
# O post
# --------------------------------------------------------------------------- #

class TestPost:

    def _publicar(self, raiz, handle="@corte"):
        job_id = _job_com_corte(raiz)
        corte, conta = _corte_e_conta(job_id, handle)
        meta = publishers.PostMeta(title="O corte do dia",
                                   descriptions={"instagram": "Descricao com acento: ação"},
                                   hashtags=("#cortes",))
        caminho = str(raiz / job_id / "v_clip_1.mp4")
        return corre(lambda: publish_queue.publicar(corte, conta, caminho, meta))

    def test_entrega_poe_o_video_no_app_e_espera_a_pessoa(self, adb, ambiente):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": conta["id"]})
        r = self._publicar(ambiente)
        assert r["driver"] == "aparelho" and r["status"] == "scheduled", r
        assert "toque em publicar" in r["detail"].lower()
        # O video na galeria, a legenda num .txt, o app aberto -- e nada tocado.
        arquivos = celular.ap.arquivos
        assert any(k.startswith("/sdcard/Movies/Virtu Clips/vc-") for k in arquivos)
        texto = next(v for k, v in arquivos.items() if k.endswith(".txt")).decode("utf-8")
        assert "O corte do dia" in texto and "ação" in texto
        assert celular.atual == "editor" and celular.tocados == []
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        assert fila["aparelho"]["nome"] == "Celular 1"
        assert fila["aparelho"]["situacao"] == "entregue"

    def test_automatico_publica_e_registra_o_post(self, adb, ambiente):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        _ensaiar(aparelho["id"])
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
               {"account_id": conta["id"], "modo": "automatico", "consentimento": True})
        celular.tocados.clear()
        r = self._publicar(ambiente)
        assert r["driver"] == "aparelho-auto" and r["status"] == "published", r
        assert celular.tocados[-1] == COMPARTILHAR["rid"]
        assert celular.digitado.startswith("O corte do dia")
        assert celular.teclado == GBOARD
        fila = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        assert fila["status"] == "published" and fila["posted_at"]
        assert fila["aparelho"]["situacao"] == "publicado"
        execucao = _chama("GET", f"/api/aparelhos/{aparelho['id']}?vivo=0").json()["execucoes"][0]
        fotos = _chama("GET", f"/api/aparelhos/{aparelho['id']}/execucoes/{execucao['id']}").json()
        assert fotos["fotos"] and fotos["fotos"][0]["imagem"].startswith("data:image/")

    def test_app_noutra_versao_vira_entrega(self, adb, ambiente):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        _ensinar(aparelho["id"])
        _ensaiar(aparelho["id"])
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
               {"account_id": conta["id"], "modo": "automatico", "consentimento": True})
        celular.versao = "315.0.0.1"
        celular.tocados.clear()
        r = self._publicar(ambiente)
        assert r["status"] == "scheduled" and "mudou de versão" in r["detail"]
        assert celular.tocados == []

    def test_limite_do_dia(self, adb, ambiente):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas",
               {"account_id": conta["id"], "limite": 1})
        hoje = frota.hoje_de(db.SELF_HOST_TENANT_ID)
        assert frota_limite.debitar(conta["id"], hoje, 1)
        # O limite cheio tira o aparelho da cascata: o corte vai para a fila manual.
        assert _contas()["@corte"]["driver_agora"] == "manual"

    def test_aparelho_fora_do_ar_devolve_o_limite(self, adb, ambiente):
        servidor, celular = adb
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": conta["id"]})
        celular.ap.estado = "offline"
        r = self._publicar(ambiente)
        assert r["status"] == "scheduled" and "não chegou" in r["detail"]
        assert frota_limite.usados(conta["id"], frota.hoje_de(db.SELF_HOST_TENANT_ID)) == 0

    def test_tela_bloqueada_nao_e_desbloqueada(self, adb, ambiente):
        servidor, celular = adb
        celular.bloqueado = True
        _ligar()
        aparelho = _aparelho()
        conta = _conta()
        _chama("PUT", f"/api/aparelhos/{aparelho['id']}/contas", {"account_id": conta["id"]})
        r = self._publicar(ambiente)
        assert r["status"] == "scheduled" and "bloqueio" in r["detail"]
        assert celular.aberturas == []


# --------------------------------------------------------------------------- #
# Um tenant nao alcanca o aparelho do outro
# --------------------------------------------------------------------------- #

class TestIsolamento:

    @pytest.fixture()
    def dois_donos(self):
        a = _chama("POST", "/api/auth/bootstrap",
                   {"email": "a@exemplo.com", "senha": "senha-do-primeiro-1"}).json()["token"]
        _chama("POST", "/api/usuarios", {"email": "b@exemplo.com", "senha": "senha-do-segundo-2"},
               token=a)
        b = _chama("POST", "/api/auth/login",
                   {"email": "b@exemplo.com", "senha": "senha-do-segundo-2"}).json()["token"]
        return a, b

    def test_o_vizinho_nao_ve_nem_toca(self, adb, dois_donos):
        a, b = dois_donos
        _ligar(token=a)
        _ligar(token=b)
        aparelho = _aparelho(token=a)
        assert _chama("GET", "/api/frota", token=b).json()["aparelhos"] == []
        for metodo, url, corpo in (
                ("GET", f"/api/aparelhos/{aparelho['id']}", None),
                ("GET", f"/api/aparelhos/{aparelho['id']}/tela", None),
                ("POST", f"/api/aparelhos/{aparelho['id']}/tecla", {"tecla": "voltar"}),
                ("POST", f"/api/aparelhos/{aparelho['id']}/ensino", {"plataforma": "instagram"}),
                ("DELETE", f"/api/aparelhos/{aparelho['id']}", None)):
            assert _chama(metodo, url, corpo, token=b).status_code == 404, url

    def test_o_mesmo_celular_nao_entra_em_duas_contas(self, adb, dois_donos):
        a, b = dois_donos
        _ligar(token=a)
        _ligar(token=b)
        _aparelho(token=a)
        r = _chama("POST", "/api/aparelhos", {"serial": SERIAL, "nome": "meu"}, token=b)
        assert r.status_code == 409 and "outra conta" in r.json()["detail"]
