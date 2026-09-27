"""O `__main__` do `main.py` DE VERDADE em modo serie (etapa 7.6).

Mesmo desenho do `test_main_audio_primeiro.py`: o bloco principal do arquivo
roda como esta, com torch, mediapipe e scenedetect imitados e os passos caros
(transcricao, corte, render, gancho, legenda) trocados por funcoes que anotam o
que receberam. E o caminho de toda serie, e um nome errado ali so apareceria na
maquina do autor, depois de baixar uma live inteira.

O que ele prova: com o `serie.json` na pasta, a deteccao de momentos nao roda e
as partes cobrem o video inteiro, contiguas; cada parte ganha o "Parte N" pelo
documento (e nao pelo ambiente); a parte que falha e refeita sozinha, e depois
pela reserva sem reenquadramento, e so vira buraco anunciado se tudo falhar; e
a retomada refaz so o que falta, com as MESMAS fronteiras da primeira vez.
"""
import ast
import importlib
import json
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

import aquecimento
import audio_probe
import hook_grounding
import layout_picker
import linhas_inteiras
import series
import sources
import transcribe_backends

RAIZ = Path(__file__).resolve().parent.parent
_PESADOS = ("torch", "mediapipe", "scenedetect", "scenedetect.detectors", "tqdm",
            "yt_dlp", "yt_dlp.version")
DURACAO = 185.0


def _partes_do_main():
    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    principal = [n for n in arvore.body if isinstance(n, ast.If)
                 and "__main__" in ast.unparse(n.test)][-1]
    corpo = [n for n in arvore.body if n is not principal]
    return (compile(ast.Module(body=corpo, type_ignores=[]), "main.py", "exec"),
            compile(ast.Module(body=principal.body, type_ignores=[]), "main.py", "exec"))


def _transcricao(deslocamento=0.0):
    """Fala continua com uma pausa a cada ~10 s; `deslocamento` muda as
    pausas, para provar que a retomada NAO recalcula as fronteiras."""
    palavras, t = [], 0.3 + deslocamento
    while t < DURACAO - 1:
        palavras.append({"word": " fala.", "start": round(t, 2), "end": round(t + 8.5, 2)})
        t += 10.0
    return {"language": "pt", "text": "fala", "segments": [
        {"start": 0.0, "end": DURACAO, "text": "fala", "words": palavras}]}


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    for nome in _PESADOS:
        try:
            importlib.import_module(nome)
        except ImportError:
            monkeypatch.setitem(sys.modules, nome, mock.MagicMock())
    monkeypatch.setattr(linhas_inteiras, "instalar", lambda: None)
    monkeypatch.setattr(transcribe_backends, "antes_de_carregar_na_placa", None)
    monkeypatch.setitem(sys.modules, "reframe_v2", types.SimpleNamespace(
        source_already_fits=lambda w, h, a: False))
    for var in ("AUTO_HOOK", "WATERMARK", "HOOK_GROUNDING"):
        monkeypatch.delenv(var, raising=False)
    # O `main.py` escreve esta no ambiente do processo; o `setenv` e o que faz o
    # monkeypatch devolver o estado de antes no fim (o `delenv` de uma variavel
    # ausente nao anota nada, e ela vazaria para os testes seguintes).
    monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "15")
    monkeypatch.setenv("AUDIO_PRIMEIRO", "0")
    monkeypatch.setenv("CLIP_WORKERS", "3")

    job = tmp_path / "job"
    job.mkdir()
    ev = {"cortes": [], "renders": [], "reservas": [], "ganchos": [], "transcricoes": 0}
    estado = {"falhas": {}, "reserva_falha": False, "deslocamento": 0.0}

    class YouTubeFalso(sources.youtube.YouTubeAdapter):
        def fetch(self, raw, output_dir=".", ao_audio=None):
            video = Path(output_dir) / "Titulo.mp4"
            video.write_bytes(b"v" * 64)
            return sources.Fetched(path=str(video), title="Titulo", kind="youtube")

    monkeypatch.setattr(sources, "resolve", lambda raw: YouTubeFalso())
    monkeypatch.setattr(audio_probe, "probe", lambda c, timeout=60: {
        "duration_s": DURACAO, "has_audio": True, "audio_codec": "aac",
        "size_bytes": 64, "width": 1920, "height": 1080})
    monkeypatch.setattr(audio_probe, "extract_wav",
                        lambda s, d, timeout=3600: Path(d).write_bytes(b"RIFF") and d)
    monkeypatch.setattr(audio_probe, "wav_seconds", lambda p: DURACAO)
    monkeypatch.setattr(layout_picker, "ENABLED", False)
    monkeypatch.setattr(aquecimento, "iniciar", lambda esperar=None: None)

    def _proibido(*a, **k):
        raise AssertionError("o hook grounding nao roda numa serie")
    monkeypatch.setattr(hook_grounding, "wanted", _proibido)

    base, principal = _partes_do_main()
    g = {"__name__": "main_teste", "__file__": str(RAIZ / "main.py"),
         "__builtins__": __builtins__}
    exec(base, g)

    def transcribe_video(caminho):
        ev["transcricoes"] += 1
        return _transcricao(estado["deslocamento"])

    def cut_clip(entrada, saida, inicio, fim, n):
        ev["cortes"].append((n, inicio, fim))
        Path(saida).write_bytes(b"c")

    def render_clip(entrada, saida, formato="auto", *a, **k):
        n = int(Path(saida).stem.rsplit("_", 1)[-1])
        ev["renders"].append(n)
        if estado["falhas"].get(n, 0) > 0:
            estado["falhas"][n] -= 1
            return False
        Path(saida).write_bytes(b"r")
        return True

    def parte_sem_reenquadrar(entrada, saida, formato="auto"):
        n = int(Path(saida).stem.rsplit("_", 1)[-1])
        ev["reservas"].append(n)
        if estado["reserva_falha"]:
            raise RuntimeError("o trecho nao abriu")
        Path(saida).write_bytes(b"s")
        return True

    def auto_hook_clip(caminho, clip, seconds=None, style=None):
        ev["ganchos"].append((clip["viral_hook_text"], seconds, style))
        saida = Path(caminho).with_name(f"hooked_1_{Path(caminho).name}")
        saida.write_bytes(b"h")
        return str(saida), {"text": clip["viral_hook_text"], "duration_seconds": seconds}

    def auto_caption_clip(caminho, *a, **k):
        saida = Path(caminho).with_name(f"subtitled_1_{Path(caminho).name}")
        saida.write_bytes(b"l")
        return str(saida)

    def _nunca(*a, **k):
        raise AssertionError("a deteccao de momentos nao roda numa serie")

    g.update(transcribe_video=transcribe_video, speech_is_sparse=lambda t, d: False,
             get_viral_clips=_nunca, get_visual_clips=_nunca, cut_clip=cut_clip,
             render_clip=render_clip, parte_sem_reenquadrar=parte_sem_reenquadrar,
             auto_hook_clip=auto_hook_clip, auto_caption_clip=auto_caption_clip)

    def rodar():
        monkeypatch.setattr(sys, "argv", ["main.py", "-u", "https://youtu.be/x",
                                          "-o", str(job), "--keep-original"])
        exec(principal, g)

    def metadata():
        return json.loads((job / "Titulo_metadata.json").read_text())

    return types.SimpleNamespace(rodar=rodar, ev=ev, estado=estado, job=job,
                                 metadata=metadata)


def _serie(cenario, **pedido):
    spec = series.normalizar_pedido({"estilo_rotulo": "yellow", **pedido}, idioma="pt")
    series.gravar_spec(str(cenario.job), spec)
    return spec


def test_a_serie_no_lugar_da_deteccao(cenario, capsys):
    spec = _serie(cenario, bloco_min=90)
    cenario.rodar()

    cortes = sorted(cenario.ev["cortes"])
    assert [n for n, _, _ in cortes] == [1, 2, 3]
    assert cortes[0][1] == 0 and cortes[-1][2] == DURACAO
    for (_, _, fim), (_, inicio, _) in zip(cortes, cortes[1:]):
        assert fim == inicio, "buraco ou trecho repetido entre duas partes"

    # O "Parte N" pelo documento: cinco segundos, no estilo escolhido.
    assert sorted(cenario.ev["ganchos"]) == [
        ("Parte 1", 5.0, "yellow"), ("Parte 2", 5.0, "yellow"), ("Parte 3", 5.0, "yellow")]

    meta = cenario.metadata()
    assert meta["serie"]["id"] == spec["id"] and meta["serie"]["partes"] == 3
    assert meta["serie"]["nome"] == "Titulo" and meta["serie"]["faltando"] == []
    assert [c["video_title_for_youtube_short"] for c in meta["shorts"]] == [
        "Titulo - Parte 1", "Titulo - Parte 2", "Titulo - Parte 3"]

    prontas = series.prontas(str(cenario.job))
    assert {i: p["arquivo"] for i, p in prontas.items()} == {
        i: f"subtitled_1_hooked_1_Titulo_clip_{i + 1}.mp4" for i in range(3)}
    assert not series.incompleta(str(cenario.job))

    out = capsys.readouterr().out
    for i in range(3):
        assert f"CLIP_READY {i} subtitled_1_hooked_1_Titulo_clip_{i + 1}.mp4" in out
    assert "Serie pronta: 3 partes" in out
    # A live da Twitch gravaria um bloco do tamanho escolhido.
    import os
    assert os.environ["TWITCH_LIVE_BLOCK_MINUTES"] == "90"


def test_sem_rotulo_no_video(cenario):
    _serie(cenario, rotulo="nao")
    cenario.rodar()
    assert cenario.ev["ganchos"] == []
    # O titulo leva o numero de qualquer jeito.
    assert cenario.metadata()["shorts"][1]["video_title_for_youtube_short"] == "Titulo - Parte 2"


def test_o_rotulo_o_video_inteiro(cenario):
    _serie(cenario, rotulo="sempre")
    cenario.rodar()
    assert {s for _, s, _ in cenario.ev["ganchos"]} == {0.0}


def test_a_parte_que_falha_e_refeita_sozinha(cenario, capsys):
    _serie(cenario)
    cenario.estado["falhas"] = {2: 1}          # falha uma vez
    cenario.rodar()
    assert cenario.ev["renders"].count(2) == 2
    assert cenario.ev["reservas"] == []
    assert cenario.metadata()["serie"]["faltando"] == []
    assert len(series.prontas(str(cenario.job))) == 3
    assert "Parte 2 falhou; tentando de novo" in capsys.readouterr().out


def test_depois_a_reserva_sem_reenquadramento(cenario, capsys):
    _serie(cenario)
    cenario.estado["falhas"] = {2: 99}         # o render de sempre nunca sai
    cenario.rodar()
    assert cenario.ev["reservas"] == [2]
    assert cenario.metadata()["serie"]["faltando"] == []
    # A parte da reserva ganha o rotulo e a legenda como as outras.
    assert series.prontas(str(cenario.job))[1]["arquivo"] == \
        "subtitled_1_hooked_1_Titulo_clip_2.mp4"
    assert "sem o enquadramento inteligente" in capsys.readouterr().out


def test_o_buraco_so_quando_tudo_falha_e_e_anunciado(cenario, capsys):
    _serie(cenario)
    cenario.estado["falhas"] = {2: 99}
    cenario.estado["reserva_falha"] = True
    cenario.rodar()
    assert cenario.metadata()["serie"]["faltando"] == [2]
    assert set(series.prontas(str(cenario.job))) == {0, 2}
    assert series.incompleta(str(cenario.job))
    assert "Faltam: 2" in capsys.readouterr().out


def test_a_retomada_refaz_so_o_que_falta_com_as_mesmas_fronteiras(cenario, capsys):
    _serie(cenario)
    cenario.rodar()
    primeira = sorted(cenario.ev["cortes"])
    # O motor caiu antes de a parte 2 ficar pronta (o arquivo dela sumiu), e a
    # transcricao da volta sai um pouco diferente.
    (cenario.job / "subtitled_1_hooked_1_Titulo_clip_2.mp4").unlink()
    assert series.incompleta(str(cenario.job))
    cenario.ev["cortes"].clear()
    cenario.ev["renders"].clear()
    cenario.estado["deslocamento"] = 1.7
    capsys.readouterr()

    cenario.rodar()
    assert cenario.ev["cortes"] == [primeira[1]], "so a parte 2, e no mesmo trecho"
    assert cenario.ev["renders"] == [2]
    out = capsys.readouterr().out
    assert "1 de 3 partes ja" not in out and "2 de 3 partes ja estavam prontas" in out
    assert "as mesmas 3 partes da primeira vez" in out
    assert "CLIP_READY 0 subtitled_1_hooked_1_Titulo_clip_1.mp4" in out
    assert not series.incompleta(str(cenario.job))
