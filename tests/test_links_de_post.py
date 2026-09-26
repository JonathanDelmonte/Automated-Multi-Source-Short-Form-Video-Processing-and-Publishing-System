"""O link do post no "ja publiquei" (etapa 7.3).

Os links aqui sao como chegam de verdade: do botao "copiar link" de cada app,
com o rastreador de compartilhamento (`?si=`, `?igsh=`, `?_r=`), sem `https://`,
com `m.` na frente. O que o CI nao alcanca e o redirecionamento do link curto
do TikTok, e por isso ele esta isolado em `resolver_link_curto`.
"""
import pytest

import links_de_post as L
from links_de_post import LinkInvalido

ID_YT = "dQw4w9WgXcQ"
ID_TT = "7412345678901234567"


class TestYouTube:
    @pytest.mark.parametrize("link, url", [
        (f"https://youtube.com/shorts/{ID_YT}?si=AbCdEf123", f"https://www.youtube.com/shorts/{ID_YT}"),
        (f"https://www.youtube.com/shorts/{ID_YT}", f"https://www.youtube.com/shorts/{ID_YT}"),
        (f"m.youtube.com/shorts/{ID_YT}/", f"https://www.youtube.com/shorts/{ID_YT}"),
        (f"https://www.youtube.com/watch?v={ID_YT}&t=4s", f"https://www.youtube.com/watch?v={ID_YT}"),
        (f"https://youtu.be/{ID_YT}?si=x", f"https://www.youtube.com/watch?v={ID_YT}"),
        (f"https://www.youtube.com/live/{ID_YT}", f"https://www.youtube.com/watch?v={ID_YT}"),
    ])
    def test_le_o_id(self, link, url):
        post = L.ler(link)
        assert (post.plataforma, post.id, post.url) == ("youtube", ID_YT, url)

    @pytest.mark.parametrize("link", [
        "https://www.youtube.com/@canal",
        "https://www.youtube.com/watch?list=PL123",
        "https://youtube.com/shorts/curto",
    ])
    def test_link_que_nao_e_de_video(self, link):
        with pytest.raises(LinkInvalido, match="nao e de um video"):
            L.ler(link)


class TestTikTok:
    def test_link_do_navegador(self):
        post = L.ler(f"https://www.tiktok.com/@canal.infantil/video/{ID_TT}?is_from_webapp=1&sender_device=pc")
        assert (post.id, post.url, post.curto) == (
            ID_TT, f"https://www.tiktok.com/@canal.infantil/video/{ID_TT}", False)

    def test_link_de_foto(self):
        assert L.ler(f"https://www.tiktok.com/@c/photo/{ID_TT}").id == ID_TT

    def test_link_antigo_do_celular(self):
        post = L.ler(f"https://m.tiktok.com/v/{ID_TT}.html?_r=1")
        assert post.id == ID_TT
        assert "?_r" not in post.url

    @pytest.mark.parametrize("link", [
        "https://vm.tiktok.com/ZMhAbC123/",
        "vt.tiktok.com/ZSxYz987",
        "https://www.tiktok.com/t/ZTRabcdEF/",
    ])
    def test_o_link_curto_do_app_fica_guardado_sem_id(self, link):
        """O "copiar link" do app nao carrega o id: so redireciona."""
        post = L.ler(link)
        assert post.plataforma == "tiktok" and post.id is None and post.curto

    def test_perfil_nao_e_video(self):
        with pytest.raises(LinkInvalido, match="nao e de um video"):
            L.ler("https://www.tiktok.com/@canal.infantil")


class TestInstagram:
    @pytest.mark.parametrize("link", [
        "https://www.instagram.com/reel/C9xYz_AbC12/?igsh=MWdmZ3Rz",
        "https://instagram.com/reels/C9xYz_AbC12",
        "https://www.instagram.com/p/C9xYz_AbC12/",
        "https://www.instagram.com/canalinfantil/reel/C9xYz_AbC12/",
        "instagr.am/reel/C9xYz_AbC12",
    ])
    def test_le_o_codigo(self, link):
        post = L.ler(link)
        assert (post.plataforma, post.id) == ("instagram", "C9xYz_AbC12")
        assert post.url == "https://www.instagram.com/reel/C9xYz_AbC12/"

    def test_perfil_nao_e_post(self):
        with pytest.raises(LinkInvalido, match="nao e de um post"):
            L.ler("https://www.instagram.com/canalinfantil/")


class TestRecusas:
    @pytest.mark.parametrize("link, frase", [
        ("", "cole o link"),
        ("   ", "cole o link"),
        ("https://www.kwai.com/@x/video/123", "nao e do YouTube"),
        ("javascript:alert(1)", "nao parece um link"),
        ("ftp://youtube.com/shorts/" + ID_YT, "nao parece um link"),
    ])
    def test_recusa(self, link, frase):
        with pytest.raises(LinkInvalido, match=frase):
            L.ler(link)

    def test_host_parecido_nao_passa(self):
        """`notyoutube.com` nao e o YouTube."""
        assert L.plataforma_de(f"https://notyoutube.com/shorts/{ID_YT}") is None

    def test_link_de_outra_plataforma_no_galho(self):
        """Medir o video errado, em silencio, seria pior que nao medir."""
        with pytest.raises(LinkInvalido) as e:
            L.ler_para("youtube", f"https://www.tiktok.com/@c/video/{ID_TT}")
        assert "e do TikTok" in str(e.value) and "e do YouTube" in str(e.value)


class TestLinkCurto:
    def test_seguido_vira_link_com_id(self, monkeypatch):
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0:
                            f"https://www.tiktok.com/@canal/video/{ID_TT}?_r=1&_t=abc")
        post = L.ler_com_rede("tiktok", "https://vm.tiktok.com/ZMhAbC123/")
        assert post.id == ID_TT and not post.curto
        assert post.url == f"https://www.tiktok.com/@canal/video/{ID_TT}"

    @pytest.mark.parametrize("destino", [None, "https://www.tiktok.com/login",
                                         "https://example.com/x"])
    def test_sem_rede_fica_o_que_a_pessoa_colou(self, monkeypatch, destino):
        monkeypatch.setattr(L, "resolver_link_curto", lambda url, timeout=8.0: destino)
        post = L.ler_com_rede("tiktok", "https://vm.tiktok.com/ZMhAbC123/")
        assert post.curto and post.id is None
        assert post.url == "https://vm.tiktok.com/ZMhAbC123/"

    def test_link_completo_nao_vai_a_rede(self, monkeypatch):
        def explode(*a, **kw):
            raise AssertionError("nao devia ir a rede")
        monkeypatch.setattr(L, "resolver_link_curto", explode)
        assert L.ler_com_rede("youtube", f"https://youtu.be/{ID_YT}").id == ID_YT

    def test_segue_um_redirecionamento_so(self, monkeypatch):
        import httpx
        pedidos = []

        class Resposta:
            status_code = 301
            headers = {"location": f"https://www.tiktok.com/@c/video/{ID_TT}"}

        def get(url, **kw):
            pedidos.append(kw)
            return Resposta()
        monkeypatch.setattr(httpx, "get", get)
        assert L.resolver_link_curto("https://vm.tiktok.com/Z/") == \
            f"https://www.tiktok.com/@c/video/{ID_TT}"
        assert pedidos[0]["follow_redirects"] is False

    def test_a_rede_que_falha_nao_levanta(self, monkeypatch):
        import httpx

        def get(url, **kw):
            raise httpx.ConnectError("sem internet")
        monkeypatch.setattr(httpx, "get", get)
        assert L.resolver_link_curto("https://vm.tiktok.com/Z/") is None
