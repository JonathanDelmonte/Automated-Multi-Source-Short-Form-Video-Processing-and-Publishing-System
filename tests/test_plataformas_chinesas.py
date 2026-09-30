"""As plataformas chinesas: Douyin, Kuaishou, Bilibili e Xiaohongshu (etapa 7.10).

Nenhuma tem API de publicacao para uma pessoa (ADR-015), entao elas entram pelo
caminho do Instagram da 7.3d: o pacote do dia com a legenda pronta e o "ja
publiquei" com o link. O que estes testes guardam:

- **o cadastro e um so** (`plataformas.py`), e quem repete a lista (o CHECK do
  banco, a fila, as analises) e comparado com ele;
- **o link como o app o copia**: o "compartilhar" dos apps chineses copia um
  texto com o link no meio, e o link curto de cada um;
- **a legenda nas regras de cada app**: o titulo no campo e no limite dele, e as
  tags do Bilibili no campo proprio, sem `#`;
- **o texto em chines, e o original quando a traducao nao sai** -- com o
  LEIA-ME dizendo qual corte ficou assim;
- **o video longo vai tambem ao Bilibili**, e so a ele entre as chinesas.
"""
import asyncio
import io
import json
import os
import subprocess
import sys
import uuid
import zipfile

import httpx
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import links_de_post as L                                    # noqa: E402
import plataformas                                           # noqa: E402
import traducao                                              # noqa: E402
from publishers import PostMeta                              # noqa: E402
from publishers.manual import ManualPublisher, render_caption  # noqa: E402

CHINESAS = ("douyin", "kuaishou", "bilibili", "xiaohongshu")


# --------------------------------------------------------------------------- #
# O cadastro
# --------------------------------------------------------------------------- #

class TestCadastro:
    def test_as_sete_na_ordem_da_tela(self):
        assert plataformas.IDS == ("youtube", "tiktok", "instagram", *CHINESAS)

    def test_quem_repete_a_lista_repete_igual(self):
        import analises
        import calibracao
        import db_models
        import publish_queue
        assert db_models.PLATFORMS == plataformas.IDS
        assert publish_queue.PLATAFORMAS == plataformas.IDS
        # As analises e a calibracao so conhecem as que tem numero.
        assert analises.PLATAFORMAS == calibracao.PLATAFORMAS == plataformas.MEDIDAS
        assert set(ManualPublisher.platforms) == set(plataformas.IDS)

    def test_toda_plataforma_tem_leitor_de_link_e_host(self):
        assert set(L._LEITORES) == set(plataformas.IDS) == set(L._HOSTS)

    def test_as_chinesas_publicam_em_chines_e_nao_sao_medidas(self):
        for p in CHINESAS:
            regra = plataformas.de(p)
            assert regra.idioma == "zh-CN" and not regra.medida
        assert plataformas.MEDIDAS == ("youtube", "tiktok", "instagram")

    def test_o_video_longo_vai_ao_youtube_e_ao_bilibili(self):
        assert plataformas.VIDEO_LONGO == ("youtube", "bilibili")
        assert plataformas.lista_de_nomes(plataformas.VIDEO_LONGO) == "o YouTube e o Bilibili"


# --------------------------------------------------------------------------- #
# Os links
# --------------------------------------------------------------------------- #

ID_DY = "7123456789012345678"
BV = "BV1xx411c7mD"
NOTA = "674051740000000007027a15"


class TestLinks:
    @pytest.mark.parametrize("plataforma, link, id_, url", [
        ("douyin", f"https://www.douyin.com/video/{ID_DY}?previous_page=app",
         ID_DY, f"https://www.douyin.com/video/{ID_DY}"),
        ("douyin", f"https://www.douyin.com/user/MS4wLjABAAAA?modal_id={ID_DY}",
         ID_DY, f"https://www.douyin.com/video/{ID_DY}"),
        ("douyin", f"https://www.iesdouyin.com/share/video/{ID_DY}/?region=CN",
         ID_DY, f"https://www.douyin.com/video/{ID_DY}"),
        ("douyin", f"https://www.douyin.com/note/{ID_DY}",
         ID_DY, f"https://www.douyin.com/note/{ID_DY}"),
        ("kuaishou", "https://www.kuaishou.com/short-video/3xk9abcdefgh?authorId=3x",
         "3xk9abcdefgh", "https://www.kuaishou.com/short-video/3xk9abcdefgh"),
        ("kuaishou", "https://v.m.chenzhongtech.com/fw/photo/3xk9abcdefgh?fid=1",
         "3xk9abcdefgh", "https://www.kuaishou.com/short-video/3xk9abcdefgh"),
        ("bilibili", f"https://www.bilibili.com/video/{BV}/?spm_id_from=333.1007",
         BV, f"https://www.bilibili.com/video/{BV}/"),
        ("bilibili", f"https://m.bilibili.com/video/{BV}", BV,
         f"https://www.bilibili.com/video/{BV}/"),
        ("bilibili", "https://www.bilibili.com/video/av170001/", "av170001",
         "https://www.bilibili.com/video/av170001/"),
        ("bilibili", f"https://b23.tv/{BV}", BV, f"https://www.bilibili.com/video/{BV}/"),
        ("xiaohongshu", f"https://www.xiaohongshu.com/explore/{NOTA}", NOTA,
         f"https://www.xiaohongshu.com/explore/{NOTA}"),
        ("xiaohongshu", f"https://www.xiaohongshu.com/user/profile/5f00a1/{NOTA}", NOTA,
         f"https://www.xiaohongshu.com/explore/{NOTA}"),
    ])
    def test_le_o_id(self, plataforma, link, id_, url):
        post = L.ler_para(plataforma, link)
        assert (post.plataforma, post.id, post.url, post.curto) == (plataforma, id_, url, False)

    def test_o_xsec_token_fica_no_link_do_xiaohongshu(self):
        """Sem ele a pagina da nota nao abre fora do app: nao e rastreador."""
        post = L.ler(f"https://www.xiaohongshu.com/discovery/item/{NOTA}"
                     "?xsec_token=CBge12=&xsec_source=pc_share")
        assert post.id == NOTA
        assert post.url == f"https://www.xiaohongshu.com/explore/{NOTA}?xsec_token=CBge12%3D"

    @pytest.mark.parametrize("plataforma, texto, curto", [
        ("douyin", "7.94 复制打开抖音，看看【小猫的作品】好可爱 https://v.douyin.com/iRNBho6u/ :9pm z@A.gb",
         "https://v.douyin.com/iRNBho6u/"),
        ("kuaishou", "https://v.kuaishou.com/abC12x 小猫 复制此消息，打开【快手】直接观看！",
         "https://v.kuaishou.com/abC12x"),
        ("bilibili", "【猫猫第一次见到雪-哔哩哔哩】 https://b23.tv/AbCd123", "https://b23.tv/AbCd123"),
        ("xiaohongshu", "小猫发布了一篇小红书笔记，快来看吧！ 😆 abc 😆 http://xhslink.com/a/AbCdE12，"
                        "复制本条信息，打开【小红书】App查看精彩内容！",
         "https://xhslink.com/a/AbCdE12"),
    ])
    def test_o_texto_de_compartilhar_do_app(self, plataforma, texto, curto):
        """O "compartilhar" dos apps chineses copia um texto com o link no meio;
        o link curto fica guardado como o app o escreveu (com ou sem barra)."""
        post = L.ler_para(plataforma, texto)
        assert (post.plataforma, post.id, post.url, post.curto) == (plataforma, None, curto, True)

    @pytest.mark.parametrize("link", [
        "https://www.kwai.com/@x/video/123",          # o Kuaishou de fora da China
        "https://www.bilibili.tv/en/video/2000",       # o Bilibili de fora da China
        "https://notdouyin.com/video/" + ID_DY,
    ])
    def test_o_que_nao_e_das_chinesas(self, link):
        with pytest.raises(L.LinkInvalido, match="plataforma que o programa conhece"):
            L.ler(link)

    @pytest.mark.parametrize("link, frase", [
        ("https://www.douyin.com/user/MS4wLjABAAAA", "nao e de um video"),
        ("https://space.bilibili.com/12345", "nao e de um video"),
        ("https://www.xiaohongshu.com/user/profile/5f00a1", "nao e de uma nota"),
        ("https://www.kuaishou.com/profile/3xabc", "nao e de um video"),
    ])
    def test_perfil_nao_e_post(self, link, frase):
        with pytest.raises(L.LinkInvalido, match=frase):
            L.ler(link)

    def test_link_de_outra_plataforma_no_galho(self):
        with pytest.raises(L.LinkInvalido) as e:
            L.ler_para("bilibili", f"https://www.douyin.com/video/{ID_DY}")
        assert "e do Douyin" in str(e.value) and "e do Bilibili" in str(e.value)

    def test_o_link_curto_e_seguido(self, monkeypatch):
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0:
                            f"https://www.iesdouyin.com/share/video/{ID_DY}/?region=CN&mid=1")
        post = L.ler_com_rede("douyin", "https://v.douyin.com/iRNBho6u/")
        assert (post.id, post.url, post.curto) == (ID_DY, f"https://www.douyin.com/video/{ID_DY}", False)

    def test_ate_dois_saltos(self, monkeypatch):
        destinos = iter(["https://b23.tv/OutroCodigo", f"https://www.bilibili.com/video/{BV}/?x=1"])
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0: next(destinos))
        assert L.ler_com_rede("bilibili", "https://b23.tv/AbCd123").id == BV

    def test_sem_rede_fica_o_link_colado(self, monkeypatch):
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0: None)
        post = L.ler_com_rede("xiaohongshu", "http://xhslink.com/a/AbCdE12")
        assert post.curto and post.id is None and post.url == "https://xhslink.com/a/AbCdE12"

    def test_o_link_puro_continua_como_era(self):
        """Sem espaco e so ASCII, o texto e o proprio link -- sem `https://`
        inclusive, como antes da 7.10."""
        assert L.extrair_link("youtube.com/shorts/abcdefghijk") == "youtube.com/shorts/abcdefghijk"
        assert L.extrair_link("veja isto: https://b23.tv/AbCd123.") == "https://b23.tv/AbCd123"


# --------------------------------------------------------------------------- #
# A legenda pronta para colar
# --------------------------------------------------------------------------- #

CREDITO = "Vídeo original: Neve, de Fulano (https://youtu.be/abcdefghijk), licença CC BY 4.0"


def _meta(titulo="小猫第一次见到雪，反应太可爱了！真的笑死我了哈哈哈哈哈哈哈哈哈哈哈哈哈",
          texto="它先是愣住，然后在雪地里打滚。", tags=("猫咪", "#萌宠", "下雪"), credito=""):
    return PostMeta(title=titulo, descriptions={p: texto for p in CHINESAS},
                    hashtags=tuple(tags), credit=credito, language="zh-CN")


class TestLegenda:
    def test_douyin_titulo_no_campo_e_hashtags_no_texto(self):
        texto = render_caption(_meta(credito=CREDITO), "douyin")
        titulo, resto = texto.split("\n\n", 1)
        assert len(titulo) == 30
        assert "#猫咪 #萌宠 #下雪" in resto
        assert resto.rstrip("\n").endswith(CREDITO)

    def test_xiaohongshu_titulo_de_20(self):
        titulo = render_caption(_meta(), "xiaohongshu").split("\n\n", 1)[0]
        assert titulo == "小猫第一次见到雪，反应太可爱了！真的笑死"

    def test_bilibili_tags_no_campo_proprio(self):
        muitas = [f"标签{i}" for i in range(14)] + ["#猫咪", "猫咪", "这是一个特别特别特别特别特别特别长的标签啊"]
        texto = render_caption(_meta(tags=muitas, credito=CREDITO), "bilibili")
        partes = texto.rstrip("\n").split("\n\n")
        titulo, descricao, tags = partes[0], "\n\n".join(partes[1:-1]), partes[-1].split(" ")
        assert titulo.startswith("小猫第一次见到雪")
        assert "#" not in texto
        assert len(tags) == 10 and tags[0] == "标签0"
        assert descricao.endswith(CREDITO) and len(descricao) <= 250

    def test_bilibili_o_credito_nunca_e_cortado(self):
        longo = "很长的描述。" * 80
        descricao = render_caption(_meta(texto=longo, credito=CREDITO), "bilibili").split("\n\n")
        corpo = "\n\n".join(descricao[1:-1])
        assert len(corpo) <= 250 and corpo.endswith(CREDITO)

    def test_kuaishou_um_bloco_so(self):
        """O Kuaishou tem um campo so: titulo, texto e hashtags num bloco, como
        no TikTok -- e sem limite inventado."""
        meta = _meta()
        assert render_caption(meta, "kuaishou") == render_caption(
            PostMeta(title=meta.title, descriptions={"tiktok": meta.description_for("douyin")},
                     hashtags=meta.hashtags, language="zh-CN"), "tiktok")

    def test_as_de_sempre_nao_mudaram(self):
        meta = PostMeta(title="Titulo", descriptions={"tiktok": "Corpo"}, hashtags=("a",))
        assert render_caption(meta, "youtube") == "Titulo\n\nCorpo\n\n#a\n"


# --------------------------------------------------------------------------- #
# A traducao
# --------------------------------------------------------------------------- #

class TestTraducao:
    def test_a_chave_e_o_texto(self):
        meta = PostMeta(title="O gato", descriptions={"tiktok": "neve"})
        um = traducao.chave(traducao.origem_de(meta, "douyin"))
        assert um == traducao.chave(traducao.origem_de(meta, "bilibili"))
        outro = PostMeta(title="O gato!", descriptions={"tiktok": "neve"})
        assert um != traducao.chave(traducao.origem_de(outro, "douyin"))

    @pytest.mark.parametrize("titulo, texto, ja", [
        ("小猫第一次见到雪", "它先是愣住 #cat", True),
        ("O gato viu neve", "Ele ficou parado #猫", False),
        ("", "", False),
    ])
    def test_ja_esta_no_idioma(self, titulo, texto, ja):
        assert traducao.ja_esta_no_idioma({"titulo": titulo, "texto": texto}, "zh-CN") is ja

    def test_a_resposta_e_limpa_e_cabe(self):
        bruto = {"itens": [
            {"i": 0, "titulo": "「小猫第一次见到雪，反应太可爱了真的笑死我了哈哈」",
             "texto": "它先是愣住。", "tags": ["#猫咪", "猫咪", "萌宠", "", "一二三四五六七八九十一二三"]},
            {"i": "x", "titulo": "ruim"},
            {"i": 2, "titulo": "  "},
        ]}
        saida = traducao.ler_resposta(bruto, "zh-CN")
        assert list(saida) == [0]
        assert saida[0]["titulo"] == "小猫第一次见到雪，反应太可爱了真的笑死我"
        assert saida[0]["tags"] == ["猫咪", "萌宠", "一二三四五六七八九十一二"]

    def test_guardar_junta_e_nao_perde(self, tmp_path):
        traducao.guardar(str(tmp_path), "zh-CN", {"a": {"titulo": "一", "texto": "", "tags": []}})
        traducao.guardar(str(tmp_path), "zh-CN", {"b": {"titulo": "二", "texto": "", "tags": []}})
        assert set(traducao.ler_cache(str(tmp_path))["zh-CN"]) == {"a", "b"}
        assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]

    def test_aplicar_troca_o_texto_e_guarda_o_credito(self):
        meta = PostMeta(title="O gato", descriptions={"tiktok": "neve #gato"}, credit=CREDITO)
        novo = traducao.aplicar(meta, "douyin", {"titulo": "小猫", "texto": "下雪了", "tags": ["猫咪"]},
                                "zh-CN")
        assert (novo.title, novo.description_for("douyin"), novo.hashtags, novo.language) == \
            ("小猫", "下雪了", ("猫咪",), "zh-CN")
        assert novo.credit == CREDITO and novo.descriptions["tiktok"] == "neve #gato"

    def test_o_pedido_nao_repete_o_mesmo_texto(self):
        origem = {"titulo": "a", "texto": "b", "hashtags": []}
        pedido = traducao.pedido("zh-CN", [("/p1", origem), ("/p1", origem), ("/p2", origem)])
        assert [i["pasta"] for i in pedido["itens"]] == ["/p1", "/p2"]

    def test_traduz_em_lotes_e_um_lote_que_falha_nao_leva_os_outros(self, tmp_path, monkeypatch):
        import llm_cascade
        chamadas = []

        def run(prompt, schema, call=None, log=print, **_):
            itens = json.loads(prompt.split("Itens:\n", 1)[1])
            chamadas.append([i["i"] for i in itens])
            if len(chamadas) == 2:
                raise llm_cascade.AllProvidersFailed("todas fora do ar")
            return {"itens": [{"i": i["i"], "titulo": f"标题{i['i']}", "texto": "文",
                               "tags": ["标签"]} for i in itens]}, {}
        monkeypatch.setattr(llm_cascade, "run", run)
        pasta = str(tmp_path)
        itens = [{"pasta": pasta, "titulo": f"Corte {n}", "texto": "x", "hashtags": []}
                 for n in range(traducao.LOTE + 3)]
        # Um ja traduzido nao volta a ser pedido.
        traducao.guardar(pasta, "zh-CN", {traducao.chave(itens[0]): {"titulo": "旧", "tags": []}})
        feitas = traducao.traduzir({"idioma": "zh-CN", "itens": itens}, call=object(), log=lambda *_: None)
        assert [len(c) for c in chamadas] == [traducao.LOTE, 2]
        assert 0 not in chamadas[0]
        assert feitas == traducao.LOTE
        assert traducao.guardada(pasta, "zh-CN", itens[0])["titulo"] == "旧"
        assert traducao.guardada(pasta, "zh-CN", itens[-1]) is None

    def test_o_subprocesso_sem_chave_nenhuma_sai_limpo(self, tmp_path):
        """O ponto de entrada de verdade (`python traducao.py`), como o servidor
        o chama: sem nenhuma IA configurada ele diz isso e sai com 0 -- e quem
        chamou segue com o texto original."""
        ambiente = {k: v for k, v in os.environ.items()
                    if not (k.endswith("_API_KEY") or k.endswith("_TOKEN") or k.startswith("OLLAMA")
                            or k.startswith("LLM_") or k.endswith("_ACCOUNT_ID"))}
        ambiente["OUTPUT_DIR"] = str(tmp_path)
        pedido = {"idioma": "zh-CN", "itens": [{"pasta": str(tmp_path), "titulo": "O gato",
                                                "texto": "neve", "hashtags": []}]}
        feito = subprocess.run([sys.executable, "traducao.py"], cwd=REPO, env=ambiente,
                               input=json.dumps(pedido), capture_output=True, text=True, timeout=120)
        assert feito.returncode == 0, feito.stdout + feito.stderr
        assert "0 de 1" in feito.stdout
        assert not (tmp_path / traducao.ARQUIVO).exists()


# --------------------------------------------------------------------------- #
# No motor: contas, pacote, publicar e o video longo
# --------------------------------------------------------------------------- #

app_module = pytest.importorskip("app")


def _chama(metodo, url, corpo=None):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            return await c.request(metodo, url, json=corpo)
    return asyncio.run(_do())


@pytest.fixture()
def motor(tmp_path, monkeypatch):
    import db
    import db_seed
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


@pytest.fixture()
def tradutor(monkeypatch):
    """O subprocesso da traducao, imitado: escreve na pasta o que a IA diria."""
    chamadas = []

    def falso(pedido):
        chamadas.append(pedido)
        por_pasta = {}
        for it in pedido["itens"]:
            por_pasta.setdefault(it["pasta"], {})[traducao.chave(it)] = {
                "titulo": "小猫" + it["titulo"][-1], "texto": "它先是愣住。", "tags": ["猫咪", "萌宠"]}
        for pasta, novas in por_pasta.items():
            traducao.guardar(pasta, pedido["idioma"], novas)
    monkeypatch.setattr(app_module, "_traduzir_no_subprocesso", falso)
    return chamadas


@pytest.fixture()
def sem_ia(monkeypatch):
    chamadas = []
    monkeypatch.setattr(app_module, "_traduzir_no_subprocesso", chamadas.append)
    return chamadas


def _job(raiz, quantos=2, longo=False):
    import job_registry
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = []
    for i in range(quantos):
        shorts.append({"start": 30.0 * i, "end": 30.0 * i + 25.0, "predicted_score": 80 - i,
                       "video_title_for_youtube_short": f"Corte {i + 1}",
                       "video_description_for_tiktok": f"descricao {i + 1} #gato"})
        if longo:
            shorts[-1].update({"formato": "longo", "video_description_for_youtube": "capitulos"})
        (pasta / f"v_clip_{i + 1}.mp4").write_bytes(b"\x00" * 64)
    (pasta / "v_metadata.json").write_text(json.dumps(
        {"shorts": shorts, "transcript": {"language": "pt", "segments": []}}))

    async def _t():
        src = await job_registry.registrar_fonte("upload", "v.mp4")
        await job_registry.registrar_job(job_id, src)
        await job_registry.registrar_clipes(job_id, shorts)
    asyncio.run(_t())
    return job_id


def _conta(plataforma, handle="canal"):
    r = _chama("POST", "/api/contas", {"platform": plataforma, "handle": handle})
    assert r.status_code == 200, r.text
    return r.json()


def _pacote(plataforma):
    r = _chama("GET", f"/api/publicacoes/pacote?plataforma={plataforma}")
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


class TestContas:
    def test_cria_conta_de_cada_uma(self, motor):
        for p in CHINESAS:
            conta = _conta(p, f"canal-{p}")
            assert conta["platform"] == p and conta["driver_agora"] == "manual"
            assert conta["conexao"] == {"publicar": False, "medir": False, "tipos": []}

    def test_o_motor_diz_quais_conhece(self, motor):
        assert _chama("GET", "/api/contas").json()["plataformas"] == list(plataformas.IDS)
        assert _chama("GET", "/api/canais").json()["plataformas"] == list(plataformas.IDS)


class TestPacote:
    def test_o_texto_vai_em_chines(self, motor, tradutor):
        _job(motor, 2)
        zf = _pacote("douyin")
        nomes = zf.namelist()
        assert "01_Corte_1.douyin.txt" in nomes and "02_Corte_2.douyin.txt" in nomes
        legenda = zf.read("01_Corte_1.douyin.txt").decode("utf-8")
        assert legenda.startswith("小猫1\n\n它先是愣住。") and "#猫咪 #萌宠" in legenda
        leia = zf.read("LEIA-ME.txt").decode("utf-8")
        assert "O texto está em chinês" in leia
        assert "Texto no idioma original" not in leia and "cortes marcados" not in leia
        assert len(tradutor) == 1 and len(tradutor[0]["itens"]) == 2

    def test_a_traducao_guardada_nao_gasta_de_novo(self, motor, tradutor):
        _job(motor, 2)
        _pacote("douyin")
        _pacote("xiaohongshu")          # o mesmo texto serve as quatro
        assert len(tradutor) == 1

    def test_sem_ia_vai_o_original_e_o_leia_me_diz(self, motor, sem_ia):
        _job(motor, 1)
        zf = _pacote("bilibili")
        assert zf.read("01_Corte_1.bilibili.txt").decode("utf-8").startswith("Corte 1\n\ndescricao 1 #gato")
        leia = zf.read("LEIA-ME.txt").decode("utf-8")
        assert "Texto no idioma original: a tradução não saiu." in leia
        assert len(sem_ia) == 1

    def test_as_de_sempre_nao_traduzem(self, motor, tradutor):
        _job(motor, 1)
        for p in ("youtube", "tiktok", "instagram"):
            assert _pacote(p).read(f"01_Corte_1.{p}.txt").decode("utf-8").startswith("Corte 1")
        assert tradutor == []

    def test_a_traducao_que_trava_nao_prende_o_pacote(self, motor, monkeypatch, capsys):
        def trava(*a, **k):
            raise subprocess.TimeoutExpired(cmd="traducao.py", timeout=1)
        monkeypatch.setattr(app_module.subprocess, "run", trava)
        _job(motor, 1)
        assert _pacote("kuaishou").read("01_Corte_1.kuaishou.txt").decode("utf-8").startswith("Corte 1")
        assert "sem resposta" in capsys.readouterr().out


class TestPublicar:
    def test_a_legenda_ao_lado_do_corte_vai_em_chines(self, motor, tradutor):
        job = _job(motor, 1)
        conta = _conta("xiaohongshu")
        r = _chama("POST", "/api/publicar", {"job_id": job, "account_id": conta["id"]})
        assert r.status_code == 200, r.text
        resultado = r.json()["resultados"][0]
        assert resultado["ok"] and resultado["status"] == "scheduled"
        legenda = (motor / job / "v_clip_1.xiaohongshu.txt").read_text(encoding="utf-8")
        assert legenda.startswith("小猫1\n\n")
        assert "idioma original" not in resultado["detail"]

    def test_sem_traducao_a_publicacao_diz(self, motor, sem_ia):
        job = _job(motor, 1)
        conta = _conta("douyin")
        resultado = _chama("POST", "/api/publicar",
                           {"job_id": job, "account_id": conta["id"]}).json()["resultados"][0]
        assert resultado["ok"] and "idioma original" in resultado["detail"]

    def test_o_video_longo_vai_ao_bilibili_e_nao_ao_douyin(self, motor, tradutor):
        job = _job(motor, 1, longo=True)
        bili, douyin = _conta("bilibili"), _conta("douyin")
        feito = _chama("POST", "/api/publicar", {"job_id": job, "account_id": bili["id"]}).json()
        assert feito["resultados"][0]["ok"]
        pulado = _chama("POST", "/api/publicar", {"job_id": job, "account_id": douyin["id"]}).json()
        assert pulado["resultados"][0]["pulado"]
        assert "YouTube e o Bilibili" in pulado["resultados"][0]["detail"]
        # O galho que pula o video longo nao gasta cota traduzindo o texto dele.
        pedidos = len(tradutor)
        _chama("POST", "/api/publicar", {"job_id": _job(motor, 1, longo=True),
                                         "account_id": douyin["id"]})
        assert len(tradutor) == pedidos

    def test_ja_publiquei_com_o_link_do_app(self, motor, tradutor, monkeypatch):
        job = _job(motor, 1)
        conta = _conta("bilibili")
        _chama("POST", "/api/publicar", {"job_id": job, "account_id": conta["id"]})
        pub = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
                   {"url": f"【猫猫-哔哩哔哩】 https://www.bilibili.com/video/{BV}/?spm_id_from=1"})
        assert r.status_code == 200, r.text
        assert r.json()["remote_id"] == BV and r.json()["aviso"] is None

    def test_link_curto_sem_rede_nao_fala_em_medir(self, motor, tradutor, monkeypatch):
        """Nenhuma chinesa e medida: o aviso "para medir, cole o link completo"
        mandaria fazer uma coisa que nao serve a nada."""
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0: None)
        job = _job(motor, 1)
        conta = _conta("douyin")
        _chama("POST", "/api/publicar", {"job_id": job, "account_id": conta["id"]})
        pub = _chama("GET", "/api/publicacoes").json()["publicacoes"][0]
        r = _chama("POST", f"/api/publicacoes/{pub['id']}/publicado",
                   {"url": "https://v.douyin.com/iRNBho6u/"}).json()
        assert r["url"] == "https://v.douyin.com/iRNBho6u/" and r["aviso"] is None
