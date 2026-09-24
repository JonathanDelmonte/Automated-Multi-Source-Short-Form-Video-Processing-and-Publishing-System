"""O `__main__` do `main.py` DE VERDADE, com o download em paralelo (24-set-2026).

O `main.py` so importa com torch, mediapipe e scenedetect, que nem o CI nem esta
maquina tem. So que o fluxo novo -- baixar o audio, transcrever, esperar o
video, cortar -- e o caminho de TODO video do YouTube: um nome errado ali
quebra todo job, e so apareceria na maquina do autor. Entao este teste executa
o bloco `__main__` do arquivo, linha por linha como ele esta, com as
bibliotecas pesadas trocadas por imitacoes e os passos caros (transcricao,
deteccao, render) trocados por funcoes que registram o que receberam.

O que ele prova: a transcricao comeca com o video AINDA baixando; o video e
esperado antes do metadata e da escolha de layout; a copia do audio nao
sobra; e o caminho de antes (`AUDIO_PRIMEIRO=0`) continua funcionando.
"""
import ast
import importlib
import json
import sys
import threading
import time
import types
from pathlib import Path
from unittest import mock

import pytest

import aquecimento
import audio_probe
import layout_picker
import linhas_inteiras
import sources
import transcribe_backends

RAIZ = Path(__file__).resolve().parent.parent
_PESADOS = ("torch", "mediapipe", "scenedetect", "scenedetect.detectors", "tqdm",
            "yt_dlp", "yt_dlp.version")


def _partes_do_main():
    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    principal = [n for n in arvore.body if isinstance(n, ast.If)
                 and "__main__" in ast.unparse(n.test)][-1]
    corpo = [n for n in arvore.body if n is not principal]
    return (compile(ast.Module(body=corpo, type_ignores=[]), "main.py", "exec"),
            compile(ast.Module(body=principal.body, type_ignores=[]), "main.py", "exec"))


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    # O que falta nesta maquina vira imitacao; o que existe fica de verdade.
    for nome in _PESADOS:
        try:
            importlib.import_module(nome)
        except ImportError:
            monkeypatch.setitem(sys.modules, nome, mock.MagicMock())
    # Nao trocar o stdout do proprio pytest.
    monkeypatch.setattr(linhas_inteiras, "instalar", lambda: None)
    monkeypatch.setattr(transcribe_backends, "antes_de_carregar_na_placa", None)
    monkeypatch.setitem(sys.modules, "reframe_v2", types.SimpleNamespace(
        source_already_fits=lambda w, h, a: False))
    for var in ("AUDIO_PRIMEIRO", "AUTO_HOOK", "WATERMARK", "HOOK_GROUNDING"):
        monkeypatch.delenv(var, raising=False)

    job = tmp_path / "job"
    job.mkdir()
    eventos = []
    video_liberado = threading.Event()

    class YouTubeFalso(sources.youtube.YouTubeAdapter):
        def fetch(self, raw, output_dir=".", ao_audio=None):
            eventos.append(("fetch", ao_audio is not None))
            pedaco = Path(output_dir) / "Titulo.f140.m4a"
            pedaco.write_bytes(b"a" * 64)
            if ao_audio is not None:
                ao_audio({"status": "finished", "filename": str(pedaco),
                          "info_dict": {"vcodec": "none", "acodec": "mp4a.40.2"}},
                         "Titulo")
                video_liberado.wait(5)
            video = Path(output_dir) / "Titulo.mp4"
            video.write_bytes(b"v" * 64)
            pedaco.unlink()                       # o yt-dlp apaga os pedacos
            eventos.append(("video_em_disco", str(video)))
            return sources.Fetched(path=str(video), title="Titulo", kind="youtube")

    monkeypatch.setattr(sources, "resolve", lambda raw: YouTubeFalso())

    def probe(caminho, timeout=60):
        info = {"duration_s": 30.0, "has_audio": True, "audio_codec": "aac",
                "size_bytes": 64}
        if caminho.endswith(".mp4"):
            info.update(width=1920, height=1080)
        return info

    def extract_wav(src, dest, timeout=3600):
        eventos.append(("wav_de", Path(src).name))
        Path(dest).write_bytes(b"RIFF")
        return dest

    monkeypatch.setattr(audio_probe, "probe", probe)
    monkeypatch.setattr(audio_probe, "extract_wav", extract_wav)
    monkeypatch.setattr(audio_probe, "wav_seconds", lambda p: 30.0)
    monkeypatch.setattr(layout_picker, "ENABLED", True)
    monkeypatch.setattr(layout_picker, "pick_and_apply", lambda v, d: eventos.append(
        ("layout", Path(v).exists())))
    # O aquecimento de verdade abriria uma thread que sobrevive ao teste; aqui
    # basta saber QUANDO ele e chamado e se recebeu a espera do download.
    monkeypatch.setattr(aquecimento, "iniciar", lambda esperar=None: eventos.append(
        ("aquecer", esperar is not None)))

    base, principal = _partes_do_main()
    g = {"__name__": "main_teste", "__file__": str(RAIZ / "main.py"),
         "__builtins__": __builtins__}
    exec(base, g)

    def transcribe_video(caminho):
        video = job / "Titulo.mp4"
        eventos.append(("transcricao", Path(caminho).name, video.exists()))
        video_liberado.set()
        return {"language": "pt", "text": "oi", "segments": [
            {"start": 0.0, "end": 5.0, "text": " oi",
             "words": [{"word": " oi", "start": 0.0, "end": 0.5}]}]}

    def cut_clip(entrada, saida, inicio, fim, n):
        eventos.append(("corte_de", Path(entrada).name))
        Path(saida).write_bytes(b"c")

    def render_clip(entrada, saida, formato="auto", *a, **k):
        Path(saida).write_bytes(b"r")
        return True

    g.update(
        transcribe_video=transcribe_video,
        speech_is_sparse=lambda t, d: False,
        get_viral_clips=lambda t, d, audio_path=None: eventos.append(("deteccao",)) or {
            "shorts": [{"start": 1.0, "end": 10.0, "viral_hook_text": "h",
                        "video_title_for_youtube_short": "t"}],
            "cost_analysis": {}},
        cut_clip=cut_clip,
        render_clip=render_clip,
        auto_caption_clip=lambda *a, **k: None,
    )

    def rodar(*extra):
        monkeypatch.setattr(sys, "argv", ["main.py", "-u", "https://youtu.be/x",
                                          "-o", str(job), "--keep-original", *extra])
        exec(principal, g)

    return types.SimpleNamespace(rodar=rodar, eventos=eventos, job=job, g=g)


def test_transcreve_enquanto_o_video_baixa(cenario, capsys):
    cenario.rodar()
    ev = cenario.eventos
    assert ev[0] == ("fetch", True)
    # O WAV sai da copia do audio, e a transcricao comeca SEM o video em disco.
    assert ("wav_de", ".audio_primeiro.m4a") in ev
    transcricao = next(e for e in ev if e[0] == "transcricao")
    assert transcricao == ("transcricao", ".audio16k.wav", False)
    # Quem le o video so vem depois dele: layout e corte.
    i_video = next(i for i, e in enumerate(ev) if e[0] == "video_em_disco")
    assert ev.index(("layout", True)) > i_video
    assert ("corte_de", "Titulo.mp4") in ev

    meta = json.loads((cenario.job / "Titulo_metadata.json").read_text())
    assert meta["source_video"] == "Titulo.mp4"
    assert not (cenario.job / ".audio_primeiro.m4a").exists(), "a copia do audio sobrou"

    # O render se aquece DURANTE a deteccao, esperando o download terminar.
    i_transcricao = next(i for i, e in enumerate(ev) if e[0] == "transcricao")
    assert i_transcricao < ev.index(("aquecer", True)) < ev.index(("deteccao",))

    out = capsys.readouterr().out
    assert "Audio pronto em" in out
    assert "Video pronto" in out and "1920x1080" in out
    assert "Found 1 clips" in out
    # A espera pelo video e ingest, sem mexer na barra.
    assert out.count("__STAGE__BEGIN 01_ingest") == 1


def test_o_whisper_local_esperaria_o_download(cenario):
    cenario.rodar()
    gancho = transcribe_backends.antes_de_carregar_na_placa
    assert gancho is not None
    gancho()                        # o download ja acabou: volta na hora


def test_sem_audio_primeiro_e_o_caminho_de_antes(cenario, monkeypatch, capsys):
    monkeypatch.setenv("AUDIO_PRIMEIRO", "0")
    cenario.rodar()
    ev = cenario.eventos
    assert ev[0] == ("fetch", False)
    assert ("wav_de", "Titulo.mp4") in ev
    assert next(e for e in ev if e[0] == "transcricao")[2] is True
    # A escolha de layout volta para antes da transcricao.
    assert ev.index(("layout", True)) < next(
        i for i, e in enumerate(ev) if e[0] == "transcricao")
    assert transcribe_backends.antes_de_carregar_na_placa is None
    # O video ja esta em disco: o aquecimento nao tem download a esperar.
    assert ev.index(("aquecer", False)) < ev.index(("deteccao",))
    assert "Audio pronto" not in capsys.readouterr().out


def test_download_que_cai_depois_do_audio_derruba_o_job_antes_da_deteccao(cenario):
    deteccoes = []
    original = cenario.g["get_viral_clips"]
    cenario.g["get_viral_clips"] = lambda *a, **k: deteccoes.append(1) or original(*a, **k)

    class Cai(sources.youtube.YouTubeAdapter):
        def fetch(self, raw, output_dir=".", ao_audio=None):
            pedaco = Path(output_dir) / "Titulo.f140.m4a"
            pedaco.write_bytes(b"a")
            ao_audio({"status": "finished", "filename": str(pedaco),
                      "info_dict": {"vcodec": "none", "acodec": "mp4a.40.2"}}, "Titulo")
            raise RuntimeError("HTTP Error 403: Forbidden")

    cenario.g["sources"].resolve = lambda raw: Cai()

    def transcreve_devagar(caminho):
        time.sleep(0.2)              # o download cai enquanto isto roda
        return {"language": "pt", "text": "oi", "segments": []}

    cenario.g["transcribe_video"] = transcreve_devagar
    with pytest.raises(RuntimeError, match="403"):
        cenario.rodar()
    assert deteccoes == [], "gastou a deteccao num job cujo download ja tinha caido"
