"""O download baixa pela extracao que ja fez (24-set-2026).

Cada tentativa do `main.download_youtube_video` abria duas instancias do
yt-dlp: uma para o titulo e outra para baixar -- e a segunda, com
`ydl.download([url])`, extraia tudo de novo (pagina, cliente do player,
provedores de PO token): ~3,5 s no log de 165 s, entre o titulo e o primeiro
byte do audio. Agora a segunda baixa pelo `info` da primeira, pelo mesmo
caminho do `--load-info-json` do yt-dlp, e so extrai de novo se isso falhar.

Duas camadas:

* com um yt-dlp de imitacao (roda no CI, que nao instala o yt-dlp): quantas
  extracoes, o que chega ao `process_ie_result`, a queda e a conta de bytes;
* com o yt-dlp de verdade, baixando de um servidor local que conta os
  pedidos: a segunda extracao some e o arquivo final e o mesmo.

O `main.py` so importa com torch; o corpo do modulo e executado com as
bibliotecas pesadas trocadas por imitacoes, como em
`test_main_audio_primeiro.py`.
"""
import ast
import http.server
import importlib
import json
import shutil
import subprocess
import sys
import threading
import types
from pathlib import Path
from unittest import mock

import pytest

import security_utils

RAIZ = Path(__file__).resolve().parent.parent
_PESADOS = ("torch", "mediapipe", "scenedetect", "scenedetect.detectors", "tqdm")


def _corpo_do_main():
    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    corpo = [n for n in arvore.body
             if not (isinstance(n, ast.If) and "__main__" in ast.unparse(n.test))]
    return compile(ast.Module(body=corpo, type_ignores=[]), "main.py", "exec")


def _carregar_main(monkeypatch, yt_dlp_modulo):
    for nome in _PESADOS:
        try:
            importlib.import_module(nome)
        except ImportError:
            monkeypatch.setitem(sys.modules, nome, mock.MagicMock())
    monkeypatch.setitem(sys.modules, "yt_dlp", yt_dlp_modulo)
    monkeypatch.setitem(sys.modules, "yt_dlp.version", yt_dlp_modulo.version)
    for var in ("PROXY_URL", "STATIC_PROXY_URLS", "DIRECT_FIRST", "YOUTUBE_COOKIES",
                "BGUTIL_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    g = {"__name__": "main_teste", "__file__": str(RAIZ / "main.py"),
         "__builtins__": __builtins__}
    exec(_corpo_do_main(), g)
    return g


# --------------------------------------------------------------------------- #
# yt-dlp de imitacao
# --------------------------------------------------------------------------- #

class _Falso:
    """Anota o que cada instancia recebeu; baixa escrevendo o mp4 esperado."""

    instancias = []
    falhar_reaproveitamento = False

    def __init__(self, params):
        self.params = params
        self.chamadas = []
        _Falso.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download=True):
        self.chamadas.append(("extract_info", download))
        # O que a escolha de formato da extracao deixa no dict: um
        # `requested_formats` que nao pode chegar ao download.
        return {"id": "x", "title": "Um titulo", "webpage_url": url,
                "formats": [{"format_id": "140"}, {"format_id": "137"}],
                "requested_formats": [{"format_id": "velho"}], "__privado": 1}

    @staticmethod
    def sanitize_info(info, remove_private_keys=False):
        fora = {"requested_formats", "requested_downloads"}
        return {k: v for k, v in info.items()
                if not (remove_private_keys and (k in fora or k.startswith("__")))}

    def _baixar(self):
        for gancho in self.params.get("progress_hooks", []):
            gancho({"status": "downloading", "downloaded_bytes": 700})
            gancho({"status": "finished", "total_bytes": 1000, "filename": "a.m4a",
                    "info_dict": {"vcodec": "none", "acodec": "mp4a.40.2"}})
        destino = self.params["outtmpl"].replace("%(ext)s", "mp4")
        Path(destino).write_bytes(b"video")

    def process_ie_result(self, info, download=True):
        self.chamadas.append(("process_ie_result", info, download))
        if _Falso.falhar_reaproveitamento:
            for gancho in self.params.get("progress_hooks", []):
                gancho({"status": "downloading", "downloaded_bytes": 300})
            raise RuntimeError("formato com objeto que o sanitize estragou")
        self._baixar()

    def download(self, urls):
        self.chamadas.append(("download", list(urls)))
        self._baixar()


@pytest.fixture
def falso(monkeypatch):
    _Falso.instancias = []
    _Falso.falhar_reaproveitamento = False
    modulo = types.ModuleType("yt_dlp")
    modulo.YoutubeDL = _Falso
    modulo.version = types.SimpleNamespace(__version__="teste")
    g = _carregar_main(monkeypatch, modulo)
    monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
    return g


def _pares(instancias):
    """(extracao, download) de cada tentativa."""
    return [instancias[i:i + 2] for i in range(0, len(instancias), 2)]


def test_uma_extracao_por_tentativa(falso, tmp_path):
    caminho, titulo = falso["download_youtube_video"]("https://youtu.be/x", str(tmp_path))
    assert titulo == "Um_titulo" and Path(caminho).exists()
    extracao, download = _pares(_Falso.instancias)[0]
    assert extracao.chamadas == [("extract_info", False)]
    assert [c[0] for c in download.chamadas] == ["process_ie_result"], \
        "a segunda instancia extraiu de novo"
    _, info, baixar = download.chamadas[0]
    assert baixar is True
    assert "requested_formats" not in info, "a escolha velha chegou ao download"
    assert not any(k.startswith("__") for k in info)
    assert info["formats"] == [{"format_id": "140"}, {"format_id": "137"}]


def test_a_extracao_escolhe_com_o_mesmo_seletor_do_download(falso, tmp_path):
    falso["download_youtube_video"]("https://youtu.be/x", str(tmp_path), ao_audio=lambda d, t: None)
    extracao, download = _pares(_Falso.instancias)[0]
    assert extracao.params["format"] == download.params["format"]
    assert extracao.params["format"].startswith("bestaudio"), "o audio primeiro sumiu"


def test_o_aviso_do_audio_chega_com_o_titulo(falso, tmp_path):
    avisos = []
    falso["download_youtube_video"]("https://youtu.be/x", str(tmp_path),
                                    ao_audio=lambda d, titulo: avisos.append(titulo))
    assert avisos == ["Um_titulo"]


def test_se_o_reaproveitamento_cai_extrai_de_novo(falso, tmp_path, capsys):
    _Falso.falhar_reaproveitamento = True
    caminho, _ = falso["download_youtube_video"]("https://youtu.be/x", str(tmp_path))
    assert Path(caminho).exists()
    _, download = _pares(_Falso.instancias)[0]
    assert [c[0] for c in download.chamadas] == ["process_ie_result", "download"]
    assert download.chamadas[1][1] == ["https://youtu.be/x"]
    out = capsys.readouterr().out
    assert "extraindo de novo" in out
    # Os 300 bytes da tentativa que caiu entram na conta: pelo proxy pago, ja
    # estao cobrados.
    rota = json.loads(next(linha for linha in out.splitlines()
                           if linha.startswith("PROXY_ROUTE="))[len("PROXY_ROUTE="):])
    assert rota["attempts"][-1]["bytes"] == 1300


# --------------------------------------------------------------------------- #
# yt-dlp de verdade, de um servidor local que conta os pedidos
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
def servidor(tmp_path):
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        pytest.skip("sem yt-dlp (o CI nao instala)")
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("sem ffmpeg")
    pasta = tmp_path / "www"
    pasta.mkdir()
    subprocess.run([ffmpeg, "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(pasta / "video.mp4")], check=True)
    pedidos = []

    class Contador(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(pasta), **k)

        def send_head(self):
            pedidos.append((self.command, self.path))
            return super().send_head()

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Contador)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield types.SimpleNamespace(url=f"http://127.0.0.1:{httpd.server_address[1]}/video.mp4",
                                pedidos=pedidos, ffmpeg=ffmpeg)
    httpd.shutdown()


@pytest.fixture
def main_real(monkeypatch, servidor):
    import yt_dlp
    g = _carregar_main(monkeypatch, yt_dlp)
    monkeypatch.setattr(security_utils, "assert_public_url", lambda u: u)
    return g


def test_o_ytdlp_de_verdade_extrai_uma_vez_so(main_real, servidor, tmp_path):
    saida = tmp_path / "job"
    saida.mkdir()
    caminho, _ = main_real["download_youtube_video"](servidor.url, str(saida))
    # Um pedido da extracao (o extrator generico olha o comeco do arquivo) e um
    # do download. Com a extracao repetida eram tres.
    assert len(servidor.pedidos) == 2, servidor.pedidos
    sonda = subprocess.run([servidor.ffmpeg, "-hide_banner", "-i", caminho],
                           capture_output=True, text=True).stderr
    assert "Video: h264" in sonda and "Audio: aac" in sonda
