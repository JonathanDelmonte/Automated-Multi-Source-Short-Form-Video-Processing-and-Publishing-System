"""Baixar o audio primeiro e transcrever enquanto o video chega (24-set-2026).

Tres camadas, cada uma com sua classe:

* o seletor de formato: o mesmo par, na ordem inversa;
* a thread do download: o audio chega antes, o erro nao se perde, a copia
  sobrevive ao yt-dlp apagar os pedacos;
* o yt-dlp DE VERDADE, baixando de um servidor local: e ele quem decide a
  ordem dos arquivos, e o teste confere que a ordem e a que o seletor pede
  (so roda onde ha yt-dlp e ffmpeg -- o CI nao instala o yt-dlp).
"""
import ast
import http.server
import io
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import audio_primeiro as ap
import linhas_inteiras
import sources

RAIZ = Path(__file__).resolve().parent.parent


def _seletores_do_main():
    """Os dois seletores que o `main._hd_fmt_for` devolve, lidos da fonte (o
    `main` so importa com torch)."""
    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arvore)
              if isinstance(n, ast.FunctionDef) and n.name == "_hd_fmt_for")
    return [ast.literal_eval(r.value) for r in ast.walk(fn) if isinstance(r, ast.Return)]


class TestSeletor:
    def test_inverte_so_os_pares_e_mantem_as_alternativas(self):
        entrada = ("bestvideo[vcodec^=avc1][height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                   "bestvideo[vcodec^=avc1][height<=1080]+bestaudio/"
                   "best[height<=1080][ext=mp4]/best[ext=mp4]/best")
        assert ap.audio_antes(entrada) == (
            "bestaudio[ext=m4a]+bestvideo[vcodec^=avc1][height<=1080][ext=mp4]/"
            "bestaudio+bestvideo[vcodec^=avc1][height<=1080]/"
            "best[height<=1080][ext=mp4]/best[ext=mp4]/best")

    @pytest.mark.parametrize("seletor", _seletores_do_main())
    def test_os_seletores_de_verdade(self, seletor):
        invertido = ap.audio_antes(seletor)
        antes, depois = seletor.split("/"), invertido.split("/")
        assert len(antes) == len(depois)
        for a, d in zip(antes, depois):
            if "+" in a:
                v, au = a.split("+")
                assert d == f"{au}+{v}"
            else:
                assert d == a
        assert invertido.split("/")[0].startswith("bestaudio")

    def test_mais_dentro_de_colchete_nao_corta(self):
        assert ap.audio_antes("bestvideo[format_note*=a+b]+bestaudio") == \
            "bestaudio+bestvideo[format_note*=a+b]"

    def test_so_inverte_video_mais_audio(self):
        assert ap.audio_antes("bestaudio+bestvideo") == "bestaudio+bestvideo"
        assert ap.audio_antes("137+140") == "137+140"

    @pytest.mark.parametrize("valor,esperado", [("1", True), ("", True), ("0", False)])
    def test_chave(self, monkeypatch, valor, esperado):
        monkeypatch.setenv("AUDIO_PRIMEIRO", valor)
        assert ap.ligado() is esperado


def _aviso(arquivo, audio=True, status="finished"):
    info = ({"vcodec": "none", "acodec": "mp4a.40.2"} if audio
            else {"vcodec": "avc1.640028", "acodec": "none"})
    return {"status": status, "filename": str(arquivo), "info_dict": info}


class TestThread:
    def test_o_audio_chega_antes_do_video(self, tmp_path):
        liberar_video = threading.Event()
        pedaco = tmp_path / "Titulo.f140.m4a"

        def baixar(ao_audio):
            pedaco.write_bytes(b"audio")
            ao_audio(_aviso(pedaco), "Titulo")
            liberar_video.wait(5)
            ao_audio(_aviso(tmp_path / "Titulo.f137.mp4", audio=False), "Titulo")
            return sources.Fetched(path=str(tmp_path / "Titulo.mp4"), title="Titulo",
                                   kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        audio = d.aguardar_audio()
        assert audio == str(tmp_path / ".audio_primeiro.m4a")
        assert Path(audio).read_bytes() == b"audio"
        assert d.caminho_previsto() == str(tmp_path / "Titulo.mp4")
        assert not d._terminou.is_set(), "o video tinha de estar a caminho ainda"
        liberar_video.set()
        assert d.aguardar_video().title == "Titulo"

    def test_a_copia_sobrevive_ao_ytdlp_apagar_os_pedacos(self, tmp_path):
        pedaco = tmp_path / "x.f140.m4a"

        def baixar(ao_audio):
            pedaco.write_bytes(b"som")
            ao_audio(_aviso(pedaco), "x")
            pedaco.unlink()                  # "Deleting original file ..."
            return sources.Fetched(path="x.mp4", title="x", kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        audio = d.aguardar_audio()
        d.aguardar_video()
        assert Path(audio).read_bytes() == b"som"

    def test_o_primeiro_audio_vale(self, tmp_path):
        """Uma tentativa que caiu no video recomeca e baixa o audio de novo."""
        um, dois = tmp_path / "a.f140.m4a", tmp_path / "b.f140.m4a"

        def baixar(ao_audio):
            um.write_bytes(b"primeiro")
            ao_audio(_aviso(um), "a")
            dois.write_bytes(b"segundo")
            ao_audio(_aviso(dois), "b")
            return sources.Fetched(path="a.mp4", title="a", kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        audio = d.aguardar_audio()
        d.aguardar_video()
        assert Path(audio).read_bytes() == b"primeiro"
        assert d.titulo == "a"

    def test_aviso_que_nao_e_audio_puro_nao_conta(self, tmp_path):
        """Formato progressivo (um arquivo com os dois): o caminho de antes."""
        def baixar(ao_audio):
            ao_audio(_aviso(tmp_path / "v.mp4", audio=False), "v")
            ao_audio(_aviso(tmp_path / "a.m4a", status="downloading"), "v")
            return sources.Fetched(path="v.mp4", title="v", kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        assert d.aguardar_audio() is None
        assert d.aguardar_video().path == "v.mp4"

    def test_falha_antes_do_audio_sobe_na_espera_do_audio(self, tmp_path):
        def baixar(ao_audio):
            raise RuntimeError("sign in to confirm you're not a bot")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        with pytest.raises(RuntimeError, match="not a bot"):
            d.aguardar_audio()

    def test_falha_depois_do_audio_sobe_quando_pedem_o_video(self, tmp_path):
        pedaco = tmp_path / "t.f140.m4a"

        def baixar(ao_audio):
            pedaco.write_bytes(b"a")
            ao_audio(_aviso(pedaco), "t")
            raise RuntimeError("HTTP Error 403: Forbidden")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        assert d.aguardar_audio()
        d.esperar_terminar()                      # nao levanta
        with pytest.raises(RuntimeError, match="403"):
            d.levantar_se_falhou()
        with pytest.raises(RuntimeError, match="403"):
            d.aguardar_video()

    def test_sem_falha_levantar_nao_faz_nada(self, tmp_path):
        d = ap.DownloadEmParalelo(
            lambda ao: sources.Fetched(path="v.mp4", title="v", kind="youtube"),
            str(tmp_path)).iniciar()
        d.esperar_terminar()
        d.levantar_se_falhou()

    def test_o_aviso_do_audio_nao_gruda_na_barra_do_ytdlp(self, tmp_path, monkeypatch):
        """No log de 165 s: `[download] 100% of 9.73MiB ...  🎧 Audio pronto`.

        O yt-dlp reescreve a barra com `\\r` e so poe o `\\n` depois, entao a
        linha dele ainda esta pela metade quando o aviso do audio chega. Com o
        escritor de linhas inteiras do `main.py`, o que decide e a THREAD que
        imprime: da thread do download, o aviso completava a linha dela.
        """
        destino = io.StringIO()
        monkeypatch.setattr(sys, "stdout", linhas_inteiras.LinhasInteiras(destino))
        pedaco = tmp_path / "t.f140.m4a"
        liberar = threading.Event()

        def baixar(ao_audio):
            pedaco.write_bytes(b"a")
            sys.stdout.write("\r[download] 100% of    9.73MiB in 00:00:01 at 5.70MiB/s")
            ao_audio(_aviso(pedaco), "t")
            liberar.wait(5)
            sys.stdout.write("\n")
            return sources.Fetched(path="t.mp4", title="t", kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        d.aguardar_audio()
        liberar.set()
        d.aguardar_video()
        linhas = destino.getvalue().split("\n")
        aviso = [linha for linha in linhas if "Audio pronto" in linha]
        assert len(aviso) == 1
        assert "[download]" not in aviso[0], f"grudou: {aviso[0]!r}"
        assert any(linha.strip().startswith("[download] 100%") for linha in linhas)

    def test_nao_conseguir_copiar_cai_no_caminho_de_antes(self, tmp_path, capsys):
        def baixar(ao_audio):
            ao_audio(_aviso(tmp_path / "nao-existe.m4a"), "t")
            return sources.Fetched(path="t.mp4", title="t", kind="youtube")

        d = ap.DownloadEmParalelo(baixar, str(tmp_path)).iniciar()
        assert d.aguardar_audio() is None
        assert "espera o video inteiro" in capsys.readouterr().out


class TestAdapter:
    def test_so_o_youtube_baixa_o_audio_antes(self):
        assert sources.resolve("https://youtu.be/x").audio_primeiro is True
        for entrada in ("https://cdn.x/a.mp4", "https://www.twitch.tv/videos/1",
                        "/tmp/a.mp4"):
            assert sources.resolve(entrada).audio_primeiro is False, entrada

    def test_o_aviso_chega_ao_download(self, monkeypatch):
        import sys
        import types

        chamadas = []
        fake = types.ModuleType("main")
        fake.download_youtube_video = lambda url, output_dir=".", ao_audio=None: (
            chamadas.append(ao_audio) or ("/o/v.mp4", "v"))
        monkeypatch.setitem(sys.modules, "main", fake)
        aviso = object()
        sources.resolve("https://youtu.be/x").fetch("https://youtu.be/x", "/o", ao_audio=aviso)
        assert chamadas == [aviso]


@pytest.fixture(scope="module")
def fonte():
    return (RAIZ / "main.py").read_text(encoding="utf-8")


class TestNoMain:
    """O `main.py` so importa com torch; o desenho e conferido pela fonte."""

    def test_o_download_inverte_o_seletor_so_com_o_aviso(self, fonte):
        arvore = ast.parse(fonte)
        fn = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)
                  and n.name == "download_youtube_video")
        assert [a.arg for a in fn.args.args][-1] == "ao_audio"
        texto = ast.unparse(fn)
        assert "if ao_audio is not None:\n            fmt = audio_primeiro.audio_antes(fmt)" in texto
        assert "ao_audio(d, _tentativa['titulo'])" in texto

    def test_o_video_e_esperado_antes_de_quem_le_o_video(self, fonte):
        """Metadata, analise visual e escolha de layout leem o VIDEO: com o
        download em paralelo, nenhum deles pode vir antes da espera."""
        linhas = fonte.splitlines()

        def primeira(trecho):
            return next(i for i, l in enumerate(linhas) if trecho in l)

        espera = primeira("            _esperar_video()")
        assert espera < primeira("clips_data['source_video'] = os.path.basename(input_video)")
        assert "get_visual_clips(_esperar_video(), duration)" in fonte
        assert espera < max(i for i, l in enumerate(linhas) if "_escolher_layout()" in l)

    def test_o_whisper_local_espera_o_download(self, fonte):
        assert ("transcribe_backends.antes_de_carregar_na_placa = "
                "baixando.esperar_terminar") in fonte


# --------------------------------------------------------------------------- #
# O yt-dlp de verdade, de um servidor local
# --------------------------------------------------------------------------- #

def _ffmpeg():
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


@pytest.fixture
def servidor_de_midia(tmp_path):
    ffmpeg = _ffmpeg()
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        pytest.skip("sem yt-dlp (o CI nao instala)")
    if not ffmpeg:
        pytest.skip("sem ffmpeg")
    pasta = tmp_path / "www"
    pasta.mkdir()
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=s=320x240:r=30:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-an", str(pasta / "video.mp4")], check=True)
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-c:a", "aac", "-vn",
                    str(pasta / "audio.m4a")], check=True)

    class Silencioso(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(pasta), **k)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Silencioso)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", ffmpeg
    httpd.shutdown()


def test_o_ytdlp_de_verdade_baixa_o_audio_primeiro(servidor_de_midia, tmp_path):
    import yt_dlp

    base, ffmpeg = servidor_de_midia
    saida = tmp_path / "job"
    saida.mkdir()
    ordem = []

    def gancho(d):
        info = d.get("info_dict") or {}
        ordem.append((d["status"], info.get("format_id")))
        baixando._ao_audio(d, "Titulo")

    info = {
        "id": "teste", "title": "Titulo", "extractor": "generic",
        "extractor_key": "Generic", "webpage_url": base + "/",
        "formats": [
            {"format_id": "137", "url": base + "/video.mp4", "ext": "mp4",
             "vcodec": "avc1.640028", "acodec": "none", "width": 320, "height": 240,
             "protocol": "http"},
            {"format_id": "140", "url": base + "/audio.m4a", "ext": "m4a",
             "vcodec": "none", "acodec": "mp4a.40.2", "protocol": "http"},
        ],
    }
    seletor = ap.audio_antes(_seletores_do_main()[-1])

    def baixar(ao_audio):
        opcoes = {"format": seletor, "outtmpl": str(saida / "Titulo.%(ext)s"),
                  "merge_output_format": "mp4", "progress_hooks": [gancho],
                  "ffmpeg_location": ffmpeg, "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.process_ie_result(dict(info), download=True)
        return sources.Fetched(path=str(saida / "Titulo.mp4"), title="Titulo",
                               kind="youtube")

    baixando = ap.DownloadEmParalelo(baixar, str(saida))
    baixando.iniciar()
    audio = baixando.aguardar_audio()
    video = baixando.aguardar_video()

    terminados = [f for status, f in ordem if status == "finished"]
    assert terminados[:2] == ["140", "137"], ordem       # audio, depois video
    assert audio and os.path.getsize(audio) > 0
    # O mp4 final tem as duas trilhas: nada mudou no que se entrega.
    sonda = subprocess.run([ffmpeg, "-hide_banner", "-i", video.path],
                           capture_output=True, text=True).stderr
    assert "Video: h264" in sonda and "Audio: aac" in sonda
