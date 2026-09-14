"""Google Drive (Fase 1, bloco 1.6).

O §4 previa "Drive API v3 + OAuth com refresh token". Este bloco usa **cookies**
em vez disso, e a divergência é deliberada: OAuth é o desenho certo para um SaaS
multiusuário, onde cada cliente autoriza a própria conta, e é desproporcional
para uma ferramenta pessoal — projeto no Google Cloud, tela de consentimento,
credenciais de cliente e fluxo de refresh, tudo para o autor ler arquivos da
própria conta. O yt-dlp já tem extrator de Drive e resolve os dois casos reais.
"""
import pytest

import sources
from sources.gdrive import classify


class TestRoteamento:
    @pytest.mark.parametrize("url", [
        "https://drive.google.com/file/d/1AbC_dEf/view?usp=sharing",
        "https://drive.google.com/file/d/1AbC/view",
        "https://docs.google.com/file/d/1AbC/edit",
        "https://drive.google.com/open?id=1AbC",
        "https://drive.google.com/uc?id=1AbC&export=download",
    ])
    def test_arquivo(self, url):
        assert classify(url) == "file"
        assert sources.resolve(url).id == "gdrive"

    def test_pasta(self):
        url = "https://drive.google.com/drive/folders/1XyZ"
        assert classify(url) == "folder"
        assert sources.resolve(url).id == "gdrive"

    @pytest.mark.parametrize("url", [
        "https://drive.google.com/",
        "https://drive.google.com/open",             # sem id
        "https://docs.google.com/spreadsheets/d/1A/edit",
        "https://youtu.be/x",
        "/tmp/a.mp4",
    ])
    def test_nao_e_arquivo_do_drive(self, url):
        assert classify(url) is None

    def test_host_parecido_nao_vira_drive(self):
        # `endswith("drive.google.com")` casaria com `notdrive.google.com`, e
        # um dominio de terceiro receberia o jar de cookies do Google.
        assert classify("https://notdrive.google.com.mau.com/file/d/x") is None
        assert sources.resolve("https://notdrive.google.com.mau.com/file/d/x").id == "direct"

    def test_vem_antes_do_generico(self):
        ids = sources.adapter_ids()
        assert ids.index("gdrive") < ids.index("direct")


class TestPasta:
    def test_recusa_com_saida(self):
        url = "https://drive.google.com/drive/folders/1XyZ"
        with pytest.raises(sources.SourceNotReady) as exc:
            sources.resolve(url).assert_fetchable(url)
        msg = str(exc.value)
        assert "pasta" in msg
        assert "/file/d/" in msg, "precisa dizer qual URL usar no lugar"

    def test_nunca_chega_ao_yt_dlp(self, monkeypatch):
        # Sem a recusa, a URL cairia no adapter generico e falharia com uma
        # mensagem sobre extrator, que nao ajuda ninguem.
        import sys
        import types

        baixou = []
        fake = types.ModuleType("main")
        fake.download_youtube_video = lambda u, output_dir=".": baixou.append(u) or ("/x", "x")
        monkeypatch.setitem(sys.modules, "main", fake)

        url = "https://drive.google.com/drive/folders/1XyZ"
        with pytest.raises(sources.SourceNotReady):
            sources.resolve(url).fetch(url, "/tmp")
        assert baixou == []

    def test_arquivo_passa_no_portao(self):
        url = "https://drive.google.com/file/d/1A/view"
        sources.resolve(url).assert_fetchable(url)      # nao levanta


class TestCookies:
    def test_jar_proprio(self):
        var, caminho = sources.cookie_jar_for("https://drive.google.com/file/d/1A/view")
        assert var == "GDRIVE_COOKIES"
        assert caminho not in ("/app/cookies.txt", "/app/cookies-twitch.txt"), (
            "arquivo separado: dois jobs de plataformas diferentes se sobrescreveriam")

    def test_nao_rouba_o_jar_do_youtube(self):
        assert sources.cookie_jar_for("https://youtu.be/x")[0] == "YOUTUBE_COOKIES"


class TestBusca:
    def test_delega_ao_caminho_que_ja_existe(self, monkeypatch):
        import sys
        import types

        chamadas = []
        fake = types.ModuleType("main")
        fake.download_youtube_video = lambda u, output_dir=".": (
            chamadas.append((u, output_dir)) or ("/out/v.mp4", "v"))
        monkeypatch.setitem(sys.modules, "main", fake)

        url = "https://drive.google.com/file/d/1A/view"
        got = sources.resolve(url).fetch(url, "/saida")
        assert chamadas == [(url, "/saida")]
        assert (got.path, got.kind) == ("/out/v.mp4", "gdrive")


class TestProbe:
    def test_avisa_do_compartilhamento(self):
        url = "https://drive.google.com/file/d/1A/view"
        notas = " ".join(sources.resolve(url).probe(url).notes)
        assert "GDRIVE_COOKIES" in notas

    def test_pasta_nao_avisa_de_cookie(self):
        # Cookie nenhum faz pasta virar arquivo; o aviso so seria ruido.
        url = "https://drive.google.com/drive/folders/1X"
        assert sources.resolve(url).probe(url).notes == ()

    def test_nao_toca_a_rede(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "main", None)
        url = "https://drive.google.com/file/d/1A/view"
        assert sources.resolve(url).probe(url).kind == "gdrive"
