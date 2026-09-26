"""Camada de publicacao -- contrato, cascata e driver manual (Fase 3, bloco 3.1).

O teste que importa mais aqui e o `TestBrowserForaDaCascata`: ele guarda a
unica regra da secao 6 cuja violacao nao aparece como bug, e sim como uma conta
banida. E ele exercita a regra pela **propriedade** (risco zero), nao pelo nome
do driver -- porque um teste que so verificasse "resolve nao devolve browser"
passaria feliz no dia em que alguem registrasse um segundo driver arriscado.
"""
import os

import pytest

import publishers
from publishers import (Account, Cost, DriverDesligado, PostMeta,
                        PublishOptions, Publisher, RenderedClip)
from publishers.manual import ManualPublisher, caption_path, render_caption


@pytest.fixture(autouse=True)
def sem_credencial_e_com_quota_limpa(tmp_path, monkeypatch):
    """Isola a cascata do ambiente de quem roda o teste.

    Sem isto, uma `YOUTUBE_CLIENT_ID` no `.env` da maquina do autor faria o
    `youtube-api` entrar na cascata e estes testes falharem por um motivo que
    nao tem nada a ver com o que eles verificam. O contador de quota tambem vai
    para um diretorio proprio: um arquivo de quota de verdade em `output/`
    mudaria a resposta de `disponivel()`.
    """
    for nome in list(os.environ):
        if nome.startswith("YOUTUBE_"):
            monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "saida"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "dados"))
    yield


def conta(**kw):
    base = dict(id="acc-1", platform="youtube", handle="canal")
    base.update(kw)
    return Account(**base)


# --------------------------------------------------------------------------- #
# A regra que nao pode cair
# --------------------------------------------------------------------------- #

class TestBrowserForaDaCascata:

    @pytest.mark.parametrize("plataforma", ["youtube", "tiktok", "instagram"])
    @pytest.mark.parametrize("pref", ["auto"] + list(publishers.DRIVER_IDS))
    def test_resolve_nunca_devolve_o_browser(self, plataforma, pref, monkeypatch):
        """Nem com a preferencia da conta apontando para ele, nem com a
        instalacao ligada. As duas coisas juntas ainda nao bastam: `resolve()`
        e o caminho automatico, e o browser so existe pelo caminho explicito."""
        monkeypatch.setenv("PUBLISHER_BROWSER", "1")
        monkeypatch.setenv("PUBLISHER_AGGREGATOR", "1")
        escolhido = publishers.resolve(plataforma, conta(platform=plataforma,
                                                        driver_pref=pref))
        assert escolhido.id != "browser"

    def test_a_regra_e_sobre_risco_e_nao_sobre_o_nome(self, monkeypatch):
        """Um driver arriscado que o resolvedor nunca viu tambem fica de fora.

        E este o teste que prova que a protecao e estrutural: o `Perigoso`
        abaixo nao se chama browser, esta registrado ANTES do manual e responde
        `disponivel()` -- tudo o que um driver precisa para vencer a cascata,
        menos risco zero.
        """
        class Perigoso(Publisher):
            id = "perigoso"
            platforms = ("youtube",)

            def disponivel(self, account):
                return True

            def cost(self, n):
                return Cost(risk_score=0.1)

        monkeypatch.setattr(publishers, "REGISTRY",
                            (Perigoso,) + publishers.REGISTRY)
        assert publishers.resolve("youtube", conta()).id == "manual"

    def test_o_browser_declara_risco_maximo(self):
        from publishers.browser import BrowserPublisher
        assert BrowserPublisher().cost(1).risk_score > publishers.RISCO_MAXIMO_AUTOMATICO

    def test_o_teto_automatico_e_zero(self):
        """Um teto "baixo mas nao zero" e o comeco da conversa que termina com
        a conta banida por conveniencia."""
        assert publishers.RISCO_MAXIMO_AUTOMATICO == 0.0

    def test_o_browser_vem_depois_do_piso(self):
        """Terceira protecao: mesmo que o risco fosse zerado por engano, o
        `manual` responde antes e encerra a busca."""
        ids = publishers.driver_ids()
        assert ids.index("browser") > ids.index("manual")

    def test_caminho_explicito_existe_e_e_barrado_pelo_ambiente(self, monkeypatch):
        monkeypatch.delenv("PUBLISHER_BROWSER", raising=False)
        driver = publishers.driver_por_id("browser")
        assert driver.id == "browser"
        assert driver.disponivel(conta(driver_pref="browser")) is False
        monkeypatch.setenv("PUBLISHER_BROWSER", "1")
        assert driver.disponivel(conta(driver_pref="browser")) is True
        # Ligado ou nao, ele ainda nao publica nada.
        with pytest.raises(DriverDesligado):
            driver.publish(None, PostMeta(), PublishOptions(), conta())


# --------------------------------------------------------------------------- #
# A cascata
# --------------------------------------------------------------------------- #

class TestCascata:

    def test_o_manual_e_o_piso(self, monkeypatch):
        """Nao existe "nenhum driver atende". A alternativa a um driver
        indisponivel e a fila manual, nunca um job vermelho."""
        monkeypatch.delenv("PUBLISHER_AGGREGATOR", raising=False)
        monkeypatch.delenv("PUBLISHER_BROWSER", raising=False)
        for plataforma in ("youtube", "tiktok", "instagram"):
            assert publishers.resolve(plataforma, conta(platform=plataforma)).id == "manual"

    def test_resolve_devolve_algo_ate_com_o_registro_vazio(self, monkeypatch):
        monkeypatch.setattr(publishers, "REGISTRY", ())
        assert publishers.resolve("youtube", conta()).id == "manual"

    def test_agregador_so_entra_assinado(self, monkeypatch):
        monkeypatch.delenv("PUBLISHER_AGGREGATOR", raising=False)
        assert publishers.resolve("youtube", conta(driver_pref="aggregator")).id == "manual"
        monkeypatch.setenv("PUBLISHER_AGGREGATOR", "1")
        assert publishers.resolve("youtube", conta(driver_pref="aggregator")).id == "aggregator"

    def test_preferencia_reordena_mas_nao_amplia(self, monkeypatch):
        """Preferir um driver inelegivel nao o torna elegivel -- so escolhe
        entre os que a cascata ja aceitava."""
        monkeypatch.setenv("PUBLISHER_AGGREGATOR", "1")
        monkeypatch.setenv("PUBLISHER_BROWSER", "1")
        # Sem preferencia (`auto`): o primeiro elegivel da ordem do registro.
        assert publishers.resolve("youtube", conta()).id == "aggregator"
        assert publishers.resolve("youtube", conta(driver_pref="auto")).id == "aggregator"
        # Preferindo o piso: o piso.
        assert publishers.resolve("youtube", conta(driver_pref="manual")).id == "manual"
        # Preferindo o arriscado: ele continua fora, e vale o primeiro elegivel.
        assert publishers.resolve("youtube", conta(driver_pref="browser")).id == "aggregator"

    def test_plataforma_que_o_driver_nao_atende_e_pulada(self, monkeypatch):
        class SoYoutube(Publisher):
            id = "so-youtube"
            platforms = ("youtube",)

            def disponivel(self, account):
                return True

            def cost(self, n):
                return Cost(risk_score=0.0)

        monkeypatch.setattr(publishers, "REGISTRY",
                            (SoYoutube,) + publishers.REGISTRY)
        assert publishers.resolve("youtube", conta()).id == "so-youtube"
        assert publishers.resolve("tiktok", conta(platform="tiktok")).id == "manual"

    def test_nada_depois_do_piso_e_alcancavel(self, monkeypatch):
        class DepoisDoPiso(Publisher):
            id = "tarde-demais"
            platforms = ("youtube",)

            def disponivel(self, account):
                return True

            def cost(self, n):
                return Cost(risk_score=0.0)

        monkeypatch.setattr(publishers, "REGISTRY",
                            publishers.REGISTRY + (DepoisDoPiso,))
        assert publishers.resolve("youtube",
                                  conta(driver_pref="tarde-demais")).id == "manual"

    def test_driver_por_id_desconhecido(self):
        with pytest.raises(KeyError):
            publishers.driver_por_id("nao-existe")


class TestParidadeComOBanco:
    """Os ids do registro tem de caber no `CHECK` de `publications.driver`.

    Um id que o banco nao conhece so falharia ao gravar a linha da publicacao
    -- depois do upload inteiro, que e o pior momento possivel para descobrir.
    """

    def test_todo_id_registrado_e_aceito_pelo_banco(self):
        db_models = pytest.importorskip("db_models")
        for driver_id in publishers.driver_ids():
            assert driver_id in db_models.DRIVERS

    def test_as_duas_listas_nao_divergiram(self):
        db_models = pytest.importorskip("db_models")
        assert set(publishers.DRIVER_IDS) == set(db_models.DRIVERS)

    def test_a_preferencia_padrao_da_conta_e_a_mesma_dos_dois_lados(self):
        """O default da coluna e o default da dataclass tem de concordar, senao
        a cascata se comporta de um jeito no teste e de outro com a conta que
        veio do banco."""
        db_models = pytest.importorskip("db_models")
        coluna = db_models.Account.__table__.c.driver_pref.default.arg
        assert coluna == Account(id="x", platform="youtube", handle="h").driver_pref
        assert coluna == "auto"

    def test_toda_preferencia_aceita_pelo_banco_e_um_id_ou_auto(self):
        """`auto` e a unica preferencia que nao nomeia um driver. Se aparecer
        uma segunda, ela precisa de regra propria no resolvedor -- e este teste
        e quem avisa."""
        db_models = pytest.importorskip("db_models")
        assert set(db_models.DRIVER_PREFS) - set(publishers.DRIVER_IDS) == {"auto"}

    def test_status_devolvido_cabe_no_check(self):
        db_models = pytest.importorskip("db_models")
        clip = RenderedClip(path=__file__, job_id="j", index=0)
        r = ManualPublisher().publish(clip, PostMeta(title="t"),
                                      PublishOptions(dry_run=True), conta())
        assert r.status in db_models.PUB_STATUSES


# --------------------------------------------------------------------------- #
# Driver manual
# --------------------------------------------------------------------------- #

class TestDriverManual:

    def test_nunca_diz_publicado(self, tmp_path):
        """A unica mentira capaz de fazer o painel contar como postado um corte
        que ninguem postou."""
        arquivo = tmp_path / "clip_1.mp4"
        arquivo.write_bytes(b"x")
        r = ManualPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(title="t"), PublishOptions(), conta())
        assert r.ok is True
        assert r.status == "scheduled"

    def test_escreve_a_legenda_ao_lado_do_corte(self, tmp_path):
        arquivo = tmp_path / "clip_1.mp4"
        arquivo.write_bytes(b"x")
        meta = PostMeta(title="Titulo do corte",
                        descriptions={"youtube": "Descricao longa"},
                        hashtags=("#corte", "#shorts"))
        r = ManualPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            meta, PublishOptions(), conta())
        destino = tmp_path / "clip_1.youtube.txt"
        assert destino.exists()
        assert str(destino) in r.artifacts
        texto = destino.read_text(encoding="utf-8")
        assert texto.startswith("Titulo do corte\n\n")
        assert "Descricao longa" in texto
        assert "#corte #shorts" in texto

    def test_a_plataforma_vem_da_conta(self, tmp_path):
        """Um arquivo por plataforma: "pronto pra colar" so e verdade se der
        para selecionar tudo."""
        arquivo = tmp_path / "clip_1.mp4"
        arquivo.write_bytes(b"x")
        meta = PostMeta(descriptions={"youtube": "para o youtube",
                                      "tiktok": "para o tiktok"})
        driver = ManualPublisher()
        for plataforma in ("youtube", "tiktok"):
            driver.publish(RenderedClip(path=str(arquivo), job_id="j", index=0),
                           meta, PublishOptions(), conta(platform=plataforma))
        assert (tmp_path / "clip_1.youtube.txt").read_text().strip() == "para o youtube"
        assert (tmp_path / "clip_1.tiktok.txt").read_text().strip() == "para o tiktok"

    def test_arquivo_que_nao_existe_e_falha_e_nao_excecao(self, tmp_path):
        r = ManualPublisher().publish(
            RenderedClip(path=str(tmp_path / "sumiu.mp4"), job_id="j", index=0),
            PostMeta(), PublishOptions(), conta())
        assert r.ok is False
        assert r.status == "failed"

    def test_dry_run_nao_escreve(self, tmp_path):
        arquivo = tmp_path / "clip_1.mp4"
        arquivo.write_bytes(b"x")
        r = ManualPublisher().publish(
            RenderedClip(path=str(arquivo), job_id="j", index=0),
            PostMeta(title="t"), PublishOptions(dry_run=True), conta())
        assert r.ok is True
        assert not (tmp_path / "clip_1.youtube.txt").exists()

    def test_o_manual_nunca_esta_indisponivel(self):
        driver = ManualPublisher()
        for plataforma in ("youtube", "tiktok", "instagram"):
            assert driver.disponivel(conta(platform=plataforma)) is True

    def test_caption_path_troca_a_extensao_do_video(self):
        assert caption_path("/a/b/video_clip_1.mp4", "tiktok") == \
            "/a/b/video_clip_1.tiktok.txt"


class TestTextoDaLegenda:

    def test_hashtag_ja_presente_nao_repete(self):
        """A descricao que o passo de deteccao gera ja costuma trazer hashtags
        dentro. Repetir a mesma tag duas vezes so aparece depois de publicado."""
        meta = PostMeta(title="T", descriptions={"youtube": "texto #shorts aqui"},
                        hashtags=("#shorts", "#corte"))
        texto = render_caption(meta, "youtube")
        assert texto.count("#shorts") == 1
        assert "#corte" in texto

    def test_hashtag_sem_cerquilha_ganha_uma(self):
        meta = PostMeta(descriptions={"youtube": "d"}, hashtags=("corte",))
        assert "#corte" in render_caption(meta, "youtube")

    def test_sem_descricao_para_a_plataforma_cai_na_que_existe(self):
        """Nao ter texto para o TikTok nao pode impedir a publicacao no TikTok."""
        meta = PostMeta(descriptions={"instagram": "so instagram"})
        assert meta.description_for("tiktok") == "so instagram"

    def test_sem_nada_devolve_vazio_em_vez_de_quebrar(self):
        assert PostMeta().description_for("youtube") == ""
        assert render_caption(PostMeta(), "youtube").strip() == ""

    def test_o_texto_nao_tem_rotulo_nenhum(self):
        """Qualquer coisa que nao va para o post e coisa que a pessoa tem de
        apagar depois de colar."""
        meta = PostMeta(title="Titulo", descriptions={"youtube": "Corpo"},
                        hashtags=("#a",))
        assert render_caption(meta, "youtube") == "Titulo\n\nCorpo\n\n#a\n"


class TestSubmodulosNoNamespace:
    """`import publishers` tem de bastar para `publishers.pacote` e
    `publishers.quota`.

    O `app.py` so faz `import publishers`. Sem os submodulos no `__init__`,
    `publishers.pacote.Item` e `AttributeError` em PRODUCAO e passa no teste --
    porque o arquivo de teste do pacote faz `from publishers import pacote` e
    esse import deixa o atributo posto para toda a sessao. Foi exatamente assim
    que o bug se escondeu ate o bloco 3.5.
    """

    def test_o_que_o_app_usa_existe_sem_import_extra(self):
        import subprocess
        import sys
        r = subprocess.run(
            [sys.executable, "-c",
             "import publishers; publishers.pacote.Item; publishers.quota.UPLOADS_POR_DIA_PADRAO"],
            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_o_app_nao_importa_os_submodulos_por_fora(self):
        """Se o `app.py` passar a importa-los direto, este teste perde o
        sentido -- e a protecao volta a ser acidental."""
        import pathlib as _p
        fonte = _p.Path("app.py").read_text(encoding="utf-8")
        assert "from publishers import" not in fonte
        assert "import publishers.pacote" not in fonte


class TestContratoSemDependenciaPesada:

    def test_o_pacote_abre_sem_o_main_e_sem_o_orm(self):
        """Mesma razao do `sources/`: a regra de negocio desta camada e *qual
        driver atende*, e isso tem de ser testavel sem a pilha de ML e sem
        banco. Um `import main` no topo levaria torch junto."""
        import ast
        import pathlib

        proibidos = {"main", "sqlalchemy", "db", "db_models", "app",
                     "torch", "cv2", "numpy"}
        for arquivo in sorted(pathlib.Path("publishers").glob("*.py")):
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
            for no in ast.walk(arvore):
                if isinstance(no, ast.Import):
                    nomes = [a.name.split(".")[0] for a in no.names]
                elif isinstance(no, ast.ImportFrom):
                    nomes = [(no.module or "").split(".")[0]] if no.level == 0 else []
                else:
                    continue
                for nome in nomes:
                    assert nome not in proibidos, \
                        f"{arquivo.name} importa {nome} no topo"
