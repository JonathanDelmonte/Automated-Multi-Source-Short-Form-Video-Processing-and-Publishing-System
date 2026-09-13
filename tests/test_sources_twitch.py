"""Twitch: o que da para baixar agora, e o que so parece que da (Fase 1, bloco 1.2).

O teste que importa aqui nao e o do VOD -- e o da **live**. Sem reconhece-la, a
URL de um canal cairia no adapter generico, e o yt-dlp *aceita* gravar live da
Twitch: ficaria baixando ate a transmissao acabar. Um job que nao termina e pior
que um job que falha, porque ninguem percebe que esta errado.
"""
import pytest

import sources
from sources.twitch import SourceNotReady, classify


class TestClassificacao:
    @pytest.mark.parametrize("url", [
        "https://www.twitch.tv/videos/2345678901",
        "https://twitch.tv/videos/123",
        "https://m.twitch.tv/videos/123",
        "https://www.twitch.tv/videos/123?t=1h2m3s",
        "https://www.twitch.tv/gaules/v/998877",          # forma antiga, ainda circula
    ])
    def test_vod(self, url):
        assert classify(url) == "vod"
        assert sources.resolve(url).id == "twitch-vod"

    @pytest.mark.parametrize("url", [
        "https://www.twitch.tv/gaules/clip/AmorphousSuaveOryxCeilingCat",
        "https://clips.twitch.tv/AmorphousSuaveOryxCeilingCat",
        "https://m.twitch.tv/gaules/clip/Slug",
    ])
    def test_clip(self, url):
        assert classify(url) == "clip"
        assert sources.resolve(url).id == "twitch-vod"

    @pytest.mark.parametrize("url", [
        "https://www.twitch.tv/gaules",
        "https://twitch.tv/alanzoka",
        "https://m.twitch.tv/canal",
    ])
    def test_canal_e_live(self, url):
        assert classify(url) == "live"
        assert sources.resolve(url).id == "twitch-live"

    def test_lista_de_videos_do_canal(self):
        url = "https://www.twitch.tv/gaules/videos"
        assert classify(url) == "channel-list"
        assert sources.resolve(url).id == "twitch-live"

    @pytest.mark.parametrize("url", [
        "https://nottwitch.tv/videos/1",
        "https://twitch.tv.exemplo.com/videos/1",
        "https://youtu.be/x",
        "https://cdn.exemplo.com/a.mp4",
        "/videos/local.mp4",
    ])
    def test_nao_e_twitch(self, url):
        assert classify(url) is None

    def test_host_parecido_nao_vira_twitch(self):
        # `host.endswith("twitch.tv")` casaria com `nottwitch.tv`. Nao seria
        # vazamento de cookie (o formato Netscape e escopado por dominio), mas
        # mandaria o download pelo plano de rede errado e o log nomearia a
        # plataforma errada.
        assert sources.resolve("https://nottwitch.tv/videos/1").id == "direct"

    def test_dominio_raiz_sem_caminho(self):
        assert classify("https://www.twitch.tv/") is None
        assert sources.resolve("https://www.twitch.tv/").id == "direct"


class TestLiveRecusa:
    def test_fetch_de_canal_levanta_com_saida(self):
        a = sources.resolve("https://www.twitch.tv/gaules")
        with pytest.raises(SourceNotReady) as exc:
            a.fetch("https://www.twitch.tv/gaules", "/tmp")
        msg = str(exc.value)
        assert "1.5" in msg, "a mensagem precisa dizer onde isso vai existir"
        assert "/videos/" in msg, "e precisa dizer o que fazer agora"

    def test_fetch_de_lista_explica_a_diferenca(self):
        url = "https://www.twitch.tv/gaules/videos"
        with pytest.raises(SourceNotReady) as exc:
            sources.resolve(url).fetch(url, "/tmp")
        assert "lista de videos" in str(exc.value)

    def test_live_nunca_chega_ao_adapter_generico(self, monkeypatch):
        # A regressao de verdade: se `TwitchLiveAdapter` sair do REGISTRY ou
        # descer para depois do generico, isto passa a baixar -- para sempre.
        import sys
        import types

        baixou = []
        fake = types.ModuleType("main")
        fake.download_youtube_video = lambda url, output_dir=".": baixou.append(url) or ("/x.mp4", "x")
        monkeypatch.setitem(sys.modules, "main", fake)

        for url in ("https://www.twitch.tv/gaules", "https://www.twitch.tv/gaules/videos"):
            with pytest.raises(SourceNotReady):
                sources.resolve(url).fetch(url, "/tmp")
        assert baixou == [], "nenhuma URL de live pode ter chegado ao yt-dlp"

    def test_probe_marca_como_live(self):
        info = sources.resolve("https://www.twitch.tv/gaules").probe("https://www.twitch.tv/gaules")
        assert info.is_live is True


class TestAvisos:
    def test_vod_avisa_da_expiracao(self):
        url = "https://www.twitch.tv/videos/123"
        notas = " ".join(sources.resolve(url).probe(url).notes).lower()
        # O plano lista "VOD da Twitch expira em 7-60 dias" como risco a
        # monitorar: quem le o log tem que saber que a fonte e perecivel.
        assert "expira" in notas

    def test_vod_avisa_do_sub_only(self):
        url = "https://www.twitch.tv/videos/123"
        notas = " ".join(sources.resolve(url).probe(url).notes)
        assert "TWITCH_COOKIES" in notas

    def test_clip_nao_avisa_de_sub_only(self):
        # Clip e publico; o aviso so faria ruido.
        url = "https://clips.twitch.tv/Slug"
        notas = " ".join(sources.resolve(url).probe(url).notes)
        assert "TWITCH_COOKIES" not in notas


class TestOrdemNoRegistro:
    def test_twitch_antes_do_generico(self):
        ids = sources.adapter_ids()
        assert ids.index("twitch-vod") < ids.index("direct")
        assert ids.index("twitch-live") < ids.index("direct")

    def test_ids_batem_com_o_schema(self):
        # A secao 4 do Plano Tecnico nomeia estes dois; o CHECK de
        # `sources.adapter` ja os aceitava desde a Fase 0.5.
        assert {"twitch-vod", "twitch-live"} <= set(sources.adapter_ids())


class TestPoteDeCookies:
    """Propriedade do adapter, nao tabela no `main`: assim roda no CI."""

    def test_twitch_usa_o_proprio_pote(self):
        var, caminho = sources.cookie_jar_for("https://www.twitch.tv/videos/1")
        assert var == "TWITCH_COOKIES"
        assert caminho != "/app/cookies.txt", (
            "arquivo separado: dois jobs simultaneos, um de cada plataforma, "
            "se sobrescreveriam no mesmo caminho")

    def test_live_usa_o_mesmo_pote_do_vod(self):
        # Quando o bloco 1.5 chegar, a live vai precisar da mesma conta.
        assert (sources.cookie_jar_for("https://www.twitch.tv/canal")
                == sources.cookie_jar_for("https://www.twitch.tv/videos/1"))

    def test_youtube_continua_onde_o_probe_procura(self):
        assert sources.cookie_jar_for("https://youtu.be/x") == (
            "YOUTUBE_COOKIES", "/app/cookies.txt"), (
            "quality_probe.py procura /app/cookies.txt pelo nome")

    @pytest.mark.parametrize("raw", ["https://cdn.x/a.mp4", "/tmp/a.mp4", "", None])
    def test_resto_cai_no_padrao(self, raw):
        assert sources.cookie_jar_for(raw)[0] == "YOUTUBE_COOKIES"

    def test_nenhum_adapter_fica_sem_pote(self):
        for adapter in sources.REGISTRY:
            assert adapter.cookie_env and adapter.cookie_file, adapter.id


class TestRotuloDaFonte:
    def test_rotulo_nomeia_a_plataforma(self):
        assert "Twitch" in sources.label_for("https://www.twitch.tv/videos/1")
        assert sources.label_for("https://youtu.be/x") == "YouTube"

    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_nao_explode_em_entrada_ruim(self, raw):
        # Isto vai para uma mensagem de erro; levantar aqui esconderia o erro
        # de verdade atras de um traceback sobre o rotulo.
        assert sources.label_for(raw)

    def test_main_reexporta_os_mesmos(self):
        main = pytest.importorskip("main")
        assert main.cookie_jar_for is sources.cookie_jar_for
        assert main.source_label is sources.label_for
