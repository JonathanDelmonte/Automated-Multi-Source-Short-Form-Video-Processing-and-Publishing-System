"""A licenca de cada video, o credito e a busca com licenca livre (etapa 7.5).

Tudo aqui roda sem rede: a busca de verdade (o YouTube, pelo yt-dlp ou pela
API) nao e alcancavel do CI, entao o que se testa e o que DECIDE -- o filtro da
pagina de resultados, a leitura de cada resposta, o que entra e o que fica de
fora, e o credito que vai na descricao.
"""
import base64
import json
import os
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

import pytest

import busca_cc
import licencas
from publishers import quota
from publishers.base import PostMeta, com_credito
from publishers import manual, tiktok_api, youtube_api
from publishers.base import PublishOptions

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# A licenca
# --------------------------------------------------------------------------- #

class TestLicenca:

    @pytest.mark.parametrize("texto,esperado", [
        ("Creative Commons Attribution license (reuse allowed)", "cc-by"),
        ("creativeCommon", "cc-by"),
        ("Standard YouTube License", "youtube"),
        ("youtube", "youtube"),
        ("Public Domain", "dominio-publico"),
        ("cc-by", "cc-by"),
        (None, "desconhecida"), ("", "desconhecida"), ("qualquer coisa", "desconhecida"),
        # Outra variante de Creative Commons NAO e a do YouTube.
        ("Creative Commons Attribution-NonCommercial", "desconhecida"),
        ("Creative Commons Attribution-ShareAlike", "desconhecida"),
    ])
    def test_normalizar(self, texto, esperado):
        assert licencas.normalizar(texto) == esperado

    def test_as_licencas_sao_as_do_banco(self):
        db_models = pytest.importorskip("db_models")
        assert licencas.LICENCAS == db_models.LICENSES

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=30s",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "youtu.be/dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ?feature=share",
    ])
    def test_o_mesmo_video_de_varios_jeitos_e_uma_chave_so(self, url):
        assert licencas.chave(url) == "youtube:dQw4w9WgXcQ"

    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/@canal", "https://www.youtube.com/playlist?list=PL1",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ", "https://youtube.com/watch?v=curto"])
    def test_o_que_nao_e_video_do_youtube(self, url):
        assert licencas.youtube_id(url) is None

    def test_outra_url_pela_forma_normalizada(self):
        a = licencas.chave("https://www.twitch.tv/videos/123/")
        b = licencas.chave("http://twitch.tv/videos/123")
        assert a == b and a.startswith("url:")
        assert licencas.chave("https://twitch.tv/videos/124") != a
        assert licencas.chave("") is None and licencas.chave(None) is None

    @pytest.mark.parametrize("data,versao", [
        ("20240501", "3.0"), ("2025-07-31", "3.0"), ("2025-08-01", "4.0"),
        ("2026-01-10T12:00:00Z", "4.0"), (None, "4.0")])
    def test_a_versao_pela_data_de_envio(self, data, versao):
        assert licencas.versao_cc(data) == versao
        assert licencas.url_da_licenca("cc-by", data).endswith(f"/by/{versao}/")


class TestCredito:
    ORIGEM = {"license": "cc-by", "title": "A Casa Assombrada", "author": "Estúdio Livre",
              "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "published_at": "2024-03-02"}

    def test_o_credito_tem_o_que_a_licenca_pede(self):
        texto = licencas.credito(self.ORIGEM)
        assert texto.startswith("Créditos:")
        for pedaco in ("“A Casa Assombrada”", "de Estúdio Livre",
                       "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                       "Creative Commons Atribuição 3.0",
                       "https://creativecommons.org/licenses/by/3.0/",
                       "cortado e editado"):
            assert pedaco in texto

    def test_no_idioma_do_canal(self):
        assert licencas.credito(self.ORIGEM, "en-US").startswith("Credit: “A Casa Assombrada” by")
        assert "Atribución" in licencas.credito(self.ORIGEM, "es-ES")
        assert licencas.credito(self.ORIGEM, "fr-FR").startswith("Créditos:")

    @pytest.mark.parametrize("licenca", ["youtube", "propria", "autorizada", "desconhecida"])
    def test_licenca_que_nao_pede_credito(self, licenca):
        assert licencas.credito({**self.ORIGEM, "license": licenca}) == ""

    def test_sem_titulo_nem_autor(self):
        texto = licencas.credito({"license": "cc-by", "url": "https://youtu.be/dQw4w9WgXcQ"})
        assert "vídeo original" in texto and " de " not in texto.split("(")[0]

    def test_cerquilha_do_titulo_nao_vira_hashtag(self):
        texto = licencas.credito({**self.ORIGEM, "title": "Desenho #3 #fyp"})
        assert "#" not in texto


class TestOrigem:

    def test_a_pagina_vence_nos_fatos(self):
        pagina = {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "Da pagina",
                  "license": None, "author": "Canal"}
        pedido = {"title": "Do pedido", "license": "cc-by", "found_by": "busca", "idioma": "pt-BR"}
        junto = licencas.juntar(pagina, pedido)
        assert junto["title"] == "Da pagina"
        # A pagina nao disse a licenca: vale a do pedido (a busca conferiu).
        assert junto["license"] == "cc-by" and junto["found_by"] == "busca"
        assert junto["key"] == "youtube:dQw4w9WgXcQ"

    def test_a_licenca_da_pagina_nao_e_desfeita_pelo_pedido(self):
        pagina = {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "x",
                  "license": "Standard YouTube License"}
        junto = licencas.juntar(pagina, {"license": "cc-by"})
        assert junto["license"] == "youtube" and junto["declared_by"] == "plataforma"

    def test_declarada_pela_pessoa(self):
        junto = licencas.juntar(None, {"license": "autorizada", "title": "meu.mp4",
                                       "found_by": "pasta"})
        assert junto["declared_by"] == "pessoa"

    def test_nada_nao_vira_origem(self):
        assert licencas.juntar(None, None) is None

    def test_gravar_e_ler_na_pasta(self, tmp_path):
        assert licencas.gravar_origem(str(tmp_path), {**TestCredito.ORIGEM, "lixo": 1,
                                                      "idioma": "pt-BR"})
        lida = licencas.ler_origem(str(tmp_path))
        assert lida["license"] == "cc-by" and "lixo" not in lida and lida["idioma"] == "pt-BR"
        assert licencas.ler_origem(str(tmp_path / "nao-existe")) is None


# --------------------------------------------------------------------------- #
# O credito nas tres plataformas
# --------------------------------------------------------------------------- #

CREDITO = licencas.credito(TestCredito.ORIGEM)


class TestCreditoNosDrivers:
    """Os tres lugares que montam texto de post levam o credito no fim, e ele
    nunca e o que se corta."""

    def test_com_credito(self):
        assert com_credito("texto", "") == "texto"
        assert com_credito("", "credito") == "credito"
        curto = com_credito("abc def ghi", "cred", 12)
        assert curto.startswith("abc") and curto.endswith("\n\ncred") and len(curto) <= 12
        # Com o espaco perto do fim, corta nele e nao no meio da palavra.
        assert com_credito("palavra palavra outra", "cred", 21) == "palavra palavra\n\ncred"
        assert com_credito("x" * 100, "credito", 20).endswith("\n\ncredito")
        assert len(com_credito("x" * 100, "credito", 20)) <= 20

    def test_youtube(self):
        meta = PostMeta(title="Corte", descriptions={"tiktok": "palavra " * 1000}, credit=CREDITO)
        corpo = youtube_api.corpo_do_video(meta, PublishOptions())
        assert corpo["snippet"]["description"].endswith(CREDITO)
        assert len(corpo["snippet"]["description"]) <= youtube_api.MAX_DESCRICAO

    def test_tiktok(self):
        meta = PostMeta(descriptions={"tiktok": "palavra " * 600}, hashtags=("#fyp",), credit=CREDITO)
        legenda = tiktok_api.legenda(meta)
        assert legenda.endswith(CREDITO) and len(legenda) <= tiktok_api.MAX_LEGENDA

    def test_instagram_com_o_limite_de_hashtags(self):
        meta = PostMeta(title="Corte", descriptions={
            "instagram": "texto " * 500 + " ".join(f"#tag{i}" for i in range(9))},
            credit=CREDITO)
        texto = manual.render_caption(meta, "instagram").rstrip("\n")
        assert texto.endswith(CREDITO)
        assert len(texto) <= manual.MAX_CARACTERES["instagram"]
        assert len(manual._HASHTAG.findall(texto)) <= 5

    def test_sem_credito_nada_muda(self):
        meta = PostMeta(title="Corte", descriptions={"tiktok": "desc #fyp"})
        assert manual.render_caption(meta, "tiktok") == "Corte\n\ndesc #fyp\n"

    def test_feito_para_criancas_no_youtube(self):
        assert youtube_api.corpo_do_video(PostMeta(made_for_kids=True), PublishOptions()
                                          )["status"]["selfDeclaredMadeForKids"] is True
        assert youtube_api.corpo_do_video(PostMeta(), PublishOptions()
                                          )["status"]["selfDeclaredMadeForKids"] is False


# --------------------------------------------------------------------------- #
# A busca
# --------------------------------------------------------------------------- #

def _campos(sp: str) -> dict:
    """Le o protobuf do `sp`: {campo_de_dentro: valor} do campo 2."""
    dados = base64.b64decode(sp)
    assert dados[0] == (2 << 3) | 2
    tamanho = dados[1]
    dentro = dados[2:2 + tamanho]
    campos, i = {}, 0
    while i < len(dentro):
        chave = dentro[i]
        campos[chave >> 3] = dentro[i + 1]
        i += 2
    return campos


class TestFiltroDaBusca:

    def test_o_valor_conhecido_do_youtube(self):
        """`EgIwAQ==` e o "Creative Commons" da propria busca do YouTube, e
        `EgIQAQ==` o "so video": as duas pecas que o filtro junta."""
        assert _campos("EgIwAQ==") == {6: 1}
        assert _campos("EgIQAQ==") == {2: 1}

    @pytest.mark.parametrize("duracao,campos", [
        ("qualquer", {2: 1, 6: 1}), ("longa", {2: 1, 3: 2, 6: 1}), ("media", {2: 1, 3: 3, 6: 1})])
    def test_o_filtro_sempre_pede_creative_commons(self, duracao, campos):
        assert _campos(busca_cc.sp_da_busca(duracao)) == campos

    def test_a_url_e_a_que_o_yt_dlp_reconhece(self):
        url = busca_cc.url_da_busca("desenho animado", "longa")
        consulta = parse_qs(urlparse(url).query)
        assert consulta["search_query"] == ["desenho animado"]
        assert _campos(consulta["sp"][0]) == {2: 1, 3: 2, 6: 1}
        yt_dlp = pytest.importorskip("yt_dlp")
        from yt_dlp.extractor.youtube import YoutubeSearchURLIE
        assert YoutubeSearchURLIE.suitable(url)

    @pytest.mark.parametrize("segundos,duracao,serve", [
        (1500, "longa", True), (1199, "longa", False), (600, "media", True),
        (1300, "media", False), (90, "qualquer", True), (30, "qualquer", False),
        (None, "longa", False), (0, "qualquer", False)])
    def test_a_faixa_de_duracao(self, segundos, duracao, serve):
        assert busca_cc.duracao_serve(segundos, duracao) is serve

    @pytest.mark.parametrize("iso,segundos", [
        ("PT1H2M3S", 3723), ("PT45M", 2700), ("PT59S", 59), ("P1DT1S", 86401), ("x", None)])
    def test_duracao_da_api(self, iso, segundos):
        assert busca_cc.segundos_iso(iso) == segundos


def _pagina(vid="dQw4w9WgXcQ", licenca="Creative Commons Attribution license (reuse allowed)",
            duracao=1800, **extra):
    return {"id": vid, "webpage_url": f"https://www.youtube.com/watch?v={vid}",
            "extractor_key": "Youtube", "title": f"Video {vid}", "channel": "Canal Livre",
            "channel_url": "https://www.youtube.com/channel/UC1", "duration": duracao,
            "upload_date": "20240105", "view_count": 1234, "license": licenca,
            "live_status": "not_live", "age_limit": 0, **extra}


class TestLeituraDoVideo:

    def test_video_creative_commons(self):
        c = busca_cc.candidato_do_video(_pagina())
        assert c["license"] == "cc-by" and c["key"] == "youtube:dQw4w9WgXcQ"
        assert c["published_at"] == "2024-01-05" and c["author"] == "Canal Livre"
        assert busca_cc.serve_para_a_busca(c, "longa") is None

    def test_sem_a_linha_de_licenca_nao_entra(self):
        c = busca_cc.candidato_do_video(_pagina(licenca=None))
        assert c["license"] == "desconhecida"
        assert "não confirmou" in busca_cc.serve_para_a_busca(c, "longa")

    @pytest.mark.parametrize("extra,motivo", [
        ({"live_status": "is_live"}, "ao vivo"), ({"age_limit": 18}, "idade"),
        ({"duration": 300}, "duração")])
    def test_o_que_fica_de_fora(self, extra, motivo):
        c = busca_cc.candidato_do_video(_pagina(**extra))
        assert motivo in busca_cc.serve_para_a_busca(c, "longa")

    def test_lista_plana_com_listas_dentro(self):
        info = {"entries": [
            {"id": "aaaaaaaaaaa", "title": "A", "duration": 1500},
            {"_type": "playlist", "entries": [{"url": "https://youtu.be/bbbbbbbbbbb"}]},
            {"title": "sem endereco"}]}
        entradas = busca_cc.entradas_da_lista(info)
        assert [e["key"] for e in entradas] == ["youtube:aaaaaaaaaaa", "youtube:bbbbbbbbbbb"]


class _Falso:
    """O yt-dlp de mentira: a lista da busca e as paginas de cada video."""

    def __init__(self, lista, paginas):
        self.lista, self.paginas, self.abertas = lista, paginas, []

    def __call__(self, url, plano=False, limite=None):
        if plano:
            return self.lista
        self.abertas.append(url)
        vid = licencas.youtube_id(url)
        if vid not in self.paginas:
            raise RuntimeError("video indisponivel")
        return self.paginas[vid]


class TestBuscaPeloYtdlp:

    def _lista(self, *ids, duracao=1800):
        return {"entries": [{"id": v, "title": v, "duration": duracao} for v in ids]}

    def test_confere_a_licenca_de_cada_video(self):
        falso = _Falso(self._lista("aaaaaaaaaaa", "bbbbbbbbbbb"), {
            "aaaaaaaaaaa": _pagina("aaaaaaaaaaa"),
            "bbbbbbbbbbb": _pagina("bbbbbbbbbbb", licenca=None)})
        r = busca_cc.buscar_pelo_ytdlp("tema", "longa", extrair=falso)
        assert [c["key"] for c in r["candidatos"]] == ["youtube:aaaaaaaaaaa"]
        assert [c["key"] for c in r["recusados"]] == ["youtube:bbbbbbbbbbb"]
        assert len(falso.abertas) == 2

    def test_o_que_o_motor_ja_conhece_nao_e_aberto(self):
        falso = _Falso(self._lista("aaaaaaaaaaa", "bbbbbbbbbbb"),
                       {"bbbbbbbbbbb": _pagina("bbbbbbbbbbb")})
        r = busca_cc.buscar_pelo_ytdlp("tema", "longa", vistos=["youtube:aaaaaaaaaaa"],
                                       extrair=falso)
        assert falso.abertas == ["https://www.youtube.com/watch?v=bbbbbbbbbbb"]
        assert len(r["candidatos"]) == 1

    def test_duracao_errada_nem_abre_a_pagina(self):
        falso = _Falso(self._lista("aaaaaaaaaaa", duracao=200), {})
        r = busca_cc.buscar_pelo_ytdlp("tema", "longa", extrair=falso)
        assert falso.abertas == [] and r["candidatos"] == []

    def test_no_maximo_dez_paginas_por_busca(self):
        ids = [f"{i:011d}" for i in range(15)]
        falso = _Falso(self._lista(*ids), {i: _pagina(i) for i in ids})
        r = busca_cc.buscar_pelo_ytdlp("tema", "longa", extrair=falso)
        assert len(falso.abertas) == busca_cc.MAX_CONFERIDOS == len(r["candidatos"])

    def test_um_video_que_falha_nao_para_a_busca(self):
        falso = _Falso(self._lista("aaaaaaaaaaa", "bbbbbbbbbbb"),
                       {"bbbbbbbbbbb": _pagina("bbbbbbbbbbb")})
        r = busca_cc.buscar_pelo_ytdlp("tema", "longa", extrair=falso)
        assert [c["key"] for c in r["candidatos"]] == ["youtube:bbbbbbbbbbb"]
        assert any("indisponivel" in a for a in r["avisos"])


class TestLinks:

    def test_video_lista_e_link_de_outro_lugar(self):
        falso = _Falso({"entries": [{"id": "ccccccccccc"}, {"id": "ddddddddddd"}]}, {
            "aaaaaaaaaaa": _pagina("aaaaaaaaaaa", licenca=None),
            "ccccccccccc": _pagina("ccccccccccc"), "ddddddddddd": _pagina("ddddddddddd")})
        r = busca_cc.listar_links(["https://youtu.be/aaaaaaaaaaa",
                                   "https://www.youtube.com/@canal",
                                   "https://drive.google.com/file/d/abc/view"], extrair=falso)
        chaves = [c["key"] for c in r["candidatos"]]
        assert chaves[:3] == ["youtube:aaaaaaaaaaa", "youtube:ccccccccccc", "youtube:ddddddddddd"]
        # A licenca dos links nao filtra (quem usa confirmou os direitos), mas e registrada.
        assert r["candidatos"][0]["license"] == "desconhecida"
        assert r["candidatos"][1]["license"] == "cc-by"
        assert r["candidatos"][3]["url"].startswith("https://drive.google.com/")

    @pytest.mark.parametrize("url,esperado", [
        ("https://www.youtube.com/@canal", "https://www.youtube.com/@canal/videos"),
        ("https://www.youtube.com/@canal/", "https://www.youtube.com/@canal/videos"),
        ("https://www.youtube.com/channel/UC1", "https://www.youtube.com/channel/UC1/videos"),
        ("https://www.youtube.com/@canal/shorts", "https://www.youtube.com/@canal/shorts"),
        ("https://www.youtube.com/playlist?list=PL1", "https://www.youtube.com/playlist?list=PL1")])
    def test_canal_vira_a_aba_de_videos(self, url, esperado):
        assert busca_cc._lista_de_canal(url) == esperado

    def test_e_lista(self):
        assert busca_cc.e_lista("https://www.youtube.com/playlist?list=PL1")
        assert busca_cc.e_lista("https://www.youtube.com/@canal")
        assert not busca_cc.e_lista("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert not busca_cc.e_lista("https://twitch.tv/videos/1")


class TestTwitch:

    def test_fora_do_ar(self):
        assert busca_cc.twitch_ao_vivo("https://twitch.tv/x", extrair=lambda u: {"is_live": False}) \
            == {"ao_vivo": False, "titulo": None}

    def test_no_ar(self):
        r = busca_cc.twitch_ao_vivo("https://twitch.tv/x", extrair=lambda u: {
            "is_live": True, "title": "Live!", "url": "https://stream"})
        assert r == {"ao_vivo": True, "titulo": "Live!"}


class TestBuscaPelaApi:

    VIDEOS = {"items": [
        {"id": "aaaaaaaaaaa", "snippet": {"title": "A", "channelTitle": "Canal",
                                          "channelId": "UC1", "publishedAt": "2025-09-01T00:00:00Z",
                                          "thumbnails": {"high": {"url": "https://i/a.jpg"}}},
         "status": {"license": "creativeCommon"}, "contentDetails": {"duration": "PT25M"},
         "statistics": {"viewCount": "900"}},
        {"id": "bbbbbbbbbbb", "snippet": {"title": "B"}, "status": {"license": "youtube"},
         "contentDetails": {"duration": "PT30M"}}]}

    def test_a_licenca_que_a_api_diz(self):
        candidatos = busca_cc.candidatos_da_api(self.VIDEOS)
        assert [c["license"] for c in candidatos] == ["cc-by", "youtube"]
        assert candidatos[0]["duration_s"] == 1500 and candidatos[0]["views"] == 900
        assert candidatos[0]["author_url"] == "https://www.youtube.com/channel/UC1"

    def test_parametros(self):
        p = busca_cc.parametros_da_api("tema", "longa", "pt-BR", 25, criancas=True)
        assert p["videoLicense"] == "creativeCommon" and p["type"] == "video"
        assert p["videoDuration"] == "long" and p["relevanceLanguage"] == "pt"
        assert p["safeSearch"] == "strict"
        assert "videoDuration" not in busca_cc.parametros_da_api("t", "qualquer", None, 5)

    def test_gasta_uma_busca_e_segue_a_ordem_da_busca(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        chamadas = []

        def http(url, params, headers):
            chamadas.append(url)
            if url == busca_cc.URL_BUSCA_API:
                return 200, {"items": [{"id": {"videoId": "bbbbbbbbbbb"}},
                                       {"id": {"videoId": "aaaaaaaaaaa"}}]}
            return 200, self.VIDEOS
        achados = busca_cc.buscar_pela_api("tema", "longa", "pt", "token", http_get=http)
        assert [a["key"] for a in achados] == ["youtube:bbbbbbbbbbb", "youtube:aaaaaaaaaaa"]
        assert quota.buscas_hoje() == 1
        assert chamadas == [busca_cc.URL_BUSCA_API, busca_cc.URL_VIDEOS_API]

    def test_sem_cota_nao_chama(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
        monkeypatch.setenv("YOUTUBE_SEARCHES_DAILY", "1")
        quota.registrar_busca()
        from publishers.base import PublisherError
        with pytest.raises(PublisherError):
            busca_cc.buscar_pela_api("t", "longa", None, "x",
                                     http_get=lambda *a: pytest.fail("chamou a API"))

    def test_a_cota_de_busca_e_100_por_dia(self):
        assert quota.BUSCAS_POR_DIA_PADRAO == 100


def test_o_subprocesso_responde_so_json():
    """A saida padrao do `busca_cc.py` e so o JSON da resposta."""
    proc = subprocess.run([sys.executable, os.path.join(RAIZ, "busca_cc.py")],
                          input=json.dumps({"acao": "nao-existe"}).encode(),
                          capture_output=True, timeout=60, cwd=RAIZ)
    assert json.loads(proc.stdout.decode()) == {"erro": "acao desconhecida: nao-existe"}
