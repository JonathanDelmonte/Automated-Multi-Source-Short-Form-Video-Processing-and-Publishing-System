"""Camada de ingestao: roteamento de fonte (Fase 1, §4).

Estes testes rodam sem torch de proposito -- `sources/` nao importa `main` no
topo justamente para isso. O unico bloco que precisa do `main` e o de paridade
com `is_youtube_url`, e ele se pula sozinho onde a pilha pesada nao existe (o
CI e um desses lugares).
"""
import pathlib

import pytest

import sources
from sources import UnknownSource


class TestRoteamento:
    @pytest.mark.parametrize("url", [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=x",
        "https://m.youtube.com/watch?v=x",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube-nocookie.com/embed/x",
        "https://rr3---sn-abc.googlevideo.com/videoplayback?x=1",
        "http://www.youtube.com/watch?v=x",
    ])
    def test_youtube(self, url):
        assert sources.resolve(url).id == "youtube"

    @pytest.mark.parametrize("url", [
        "https://cdn.example.com/video.mp4",
        "https://tmpfiles.org/dl/123/a.mp4",
        "https://pub-abc.r2.dev/clip.mp4",
        "http://192.0.2.10/a.mp4",
    ])
    def test_url_direta(self, url):
        assert sources.resolve(url).id == "direct"

    @pytest.mark.parametrize("caminho", [
        "/videos/entrevista.mp4",
        "video.mp4",
        "./uploads/a b c.mov",
        r"C:\Users\User\Videos\live.mkv",
        "/tmp/x.mp4",
    ])
    def test_arquivo_local(self, caminho):
        assert sources.resolve(caminho).id == "upload"

    def test_caminho_do_windows_nao_vira_url(self):
        # `urlparse(r"C:\x\y.mp4").scheme` e "c": testar "tem esquema" em vez
        # de "http ou https" mandaria arquivo local para o caminho de rede.
        assert sources.resolve(r"C:\x\y.mp4").id == "upload"

    @pytest.mark.parametrize("vazio", ["", "   ", None])
    def test_vazio_levanta(self, vazio):
        with pytest.raises(UnknownSource):
            sources.resolve(vazio)

    def test_esquema_nao_http_e_arquivo(self):
        # `file://`, `ftp://` e afins nao tem adapter de rede; caem no local,
        # que e onde o erro "arquivo nao encontrado" ja e claro.
        assert sources.resolve("ftp://host/a.mp4").id == "upload"


class TestOrdemDoRegistro:
    def test_youtube_antes_do_generico(self):
        # `DirectUrlAdapter.matches` aceita qualquer http(s). Uma plataforma
        # registrada depois dele nunca seria alcancada -- e o modo de falhar
        # que a ordem do REGISTRY existe para impedir.
        ids = sources.adapter_ids()
        assert ids.index("youtube") < ids.index("direct")

    def test_generico_nao_engole_plataforma_futura(self):
        from sources.base import SourceAdapter

        genericos = [a for a in sources.REGISTRY if a.matches("https://exemplo.com/a.mp4")]
        assert genericos and genericos[0].id == "direct", (
            "so o adapter generico pode responder a um host desconhecido")
        assert issubclass(genericos[0], SourceAdapter)


class TestArquivoLocal:
    def test_nao_copia_nem_move(self, tmp_path):
        f = tmp_path / "entrevista longa.mp4"
        f.write_bytes(b"x")
        got = sources.resolve(str(f)).fetch(str(f))
        assert got.path == str(f), "o arquivo e lido onde esta; copiar 10GB seria pagar disco por nada"
        assert f.exists()

    def test_titulo_e_o_nome_sem_extensao(self, tmp_path):
        f = tmp_path / "corte.final.mp4"
        got = sources.resolve(str(f)).fetch(str(f))
        # Mesma expressao que o __main__ usava antes desta camada existir.
        assert got.title == "corte.final"

    def test_kind_viaja_junto(self, tmp_path):
        got = sources.resolve(str(tmp_path / "a.mp4")).fetch(str(tmp_path / "a.mp4"))
        assert got.kind == "upload"


class TestDelegacao:
    """Os adapters de rede chamam o `main`; nao reimplementam o download."""

    def _fake_main(self, monkeypatch, retorno=("/out/video.mp4", "video")):
        import sys
        import types

        chamadas = []
        fake = types.ModuleType("main")

        def download_youtube_video(url, output_dir="."):
            chamadas.append((url, output_dir))
            return retorno

        fake.download_youtube_video = download_youtube_video
        monkeypatch.setitem(sys.modules, "main", fake)
        return chamadas

    def test_youtube_delega(self, monkeypatch):
        chamadas = self._fake_main(monkeypatch)
        got = sources.resolve("https://youtu.be/x").fetch("https://youtu.be/x", "/saida")
        assert chamadas == [("https://youtu.be/x", "/saida")]
        assert (got.path, got.title, got.kind) == ("/out/video.mp4", "video", "youtube")

    def test_url_direta_delega_pela_mesma_porta(self, monkeypatch):
        # Uma funcao so para os dois porque ela ja separa os casos por dentro
        # (`plan_download_attempts(..., youtube=False)`): sem proxy, sem cookies.
        chamadas = self._fake_main(monkeypatch)
        got = sources.resolve("https://cdn.x/a.mp4").fetch("https://cdn.x/a.mp4", "/saida")
        assert chamadas == [("https://cdn.x/a.mp4", "/saida")]
        assert got.kind == "direct"


class TestProbe:
    def test_probe_nao_toca_a_rede(self, monkeypatch):
        # Nenhum adapter atual chama `main` no probe. Se um passar a chamar,
        # este teste quebra -- e e para quebrar: o probe barato roda em todo
        # job, antes do download, e uma ida na rede aqui pode custar dinheiro
        # (ver `cloud/metering.probe_url_minutes`).
        import sys

        monkeypatch.setitem(sys.modules, "main", None)
        for raw in ("https://youtu.be/x", "https://cdn.x/a.mp4", "/tmp/a.mp4"):
            info = sources.resolve(raw).probe(raw)
            assert info.kind and info.label
            assert info.is_live is False

    def test_label_e_legivel(self):
        assert sources.resolve("https://youtu.be/x").probe("https://youtu.be/x").label == "YouTube"


def _hosts_declarados_no_main():
    """A tupla de hosts de `main.is_youtube_url`, lida do CODIGO, sem importar.

    Importar o `main` traz torch, scenedetect e mediapipe -- que o CI nao
    instala de proposito --, entao a checagem de paridade so rodaria na maquina
    de quem tem a pilha inteira, e a duplicacao poderia divergir por semanas
    sem ninguem ver. Ler a funcao com `ast` custa milissegundos e roda em todo
    lugar. Devolve None se a forma do codigo mudar, e ai o teste diz isso em
    vez de passar em silencio.
    """
    import ast

    arvore = ast.parse(pathlib.Path("main.py").read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == "is_youtube_url":
            for chamada in ast.walk(no):
                if (isinstance(chamada, ast.Call)
                        and isinstance(chamada.func, ast.Attribute)
                        and chamada.func.attr == "endswith"
                        and chamada.args
                        and isinstance(chamada.args[0], ast.Tuple)):
                    valores = [e.value for e in chamada.args[0].elts
                               if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                    if valores:
                        return tuple(valores)
    return None


class TestParidadeComOMain:
    """`YouTubeAdapter.HOSTS` repete a lista de `main.is_youtube_url`.

    A duplicacao e deliberada (o pacote precisa abrir sem torch), entao o custo
    dela e este teste: se uma das duas listas mudar sozinha, aqui quebra.
    """

    def test_mesma_lista_de_hosts_que_o_main(self):
        from sources.youtube import HOSTS

        declarados = _hosts_declarados_no_main()
        assert declarados is not None, (
            "nao achei a tupla de hosts em main.is_youtube_url -- se a funcao "
            "mudou de forma, atualize este teste em vez de apaga-lo: ele e a "
            "unica coisa que impede as duas listas de divergirem")
        assert set(declarados) == set(HOSTS)

    def test_mesma_resposta_que_is_youtube_url(self):
        main = pytest.importorskip("main")
        from sources.youtube import YouTubeAdapter

        urls = [
            "https://www.youtube.com/watch?v=x",
            "https://youtu.be/x",
            "https://www.youtube-nocookie.com/embed/x",
            "https://rr3---sn-abc.googlevideo.com/videoplayback",
            "https://cdn.example.com/a.mp4",
            "https://www.twitch.tv/videos/123",
            "https://tmpfiles.org/dl/1/a.mp4",
        ]
        for u in urls:
            assert YouTubeAdapter.matches(u) == main.is_youtube_url(u), u
