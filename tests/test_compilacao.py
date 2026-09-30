"""A compilacao dos cortes (etapa 7.8): o plano, os capitulos, a legenda no
tempo da compilacao e, com ffmpeg de verdade, o video que sai."""
import json
import os
import re
import shutil
import subprocess

import pytest

import compilacao
import compilar_video
import job_metrics


def _trecho(inicio, fim, titulo="", arquivo="a.mp4", palavras=None, **kw):
    return {"arquivo": arquivo, "corte_inicio": inicio, "corte_fim": fim, "titulo": titulo,
            "palavras": palavras or [], **kw}


# --------------------------------------------------------------------------- #
# As regras
# --------------------------------------------------------------------------- #

def test_o_plano_poe_cada_trecho_depois_do_anterior():
    plano = compilacao.planejar([_trecho(10, 25, "Um"), _trecho(0, 12.5, "  Dois \n")])
    assert [(t["inicio_no_video"], t["duracao"], t["titulo"]) for t in plano] == \
        [(0.0, 15.0, "Um"), (15.0, 12.5, "Dois")]
    assert compilacao.duracao_total(plano) == 27.5


@pytest.mark.parametrize("trechos,trecho", [
    ([_trecho(0, 10)], "pelo menos 2"),
    ([_trecho(0, 10)] * 61, "No máximo 60"),
    ([_trecho(0, 10), _trecho(5, 5.5)], "O corte 2 tem menos de 1 s"),
    ([_trecho(0, 10), _trecho("x", 5)], "corte 2: esperava um número"),
    ([_trecho(0, 1900), _trecho(0, 1900)], "passaria de 60 minutos"),
    # Os limites contam CORTES: tres pedacos de um corte re-editado sao um.
    ([_trecho(0, 5), _trecho(8, 9, continua=True), _trecho(12, 20, continua=True)],
     "pelo menos 2"),
    # O corte re-editado inteiro tem de ter 1 s; o pedaco, 0,2 s.
    ([_trecho(0, 10), _trecho(0, 0.4), _trecho(3, 3.4, continua=True)], "O corte 2 tem menos de 1 s"),
    ([_trecho(0, 10), _trecho(0, 5), _trecho(8, 8.1, continua=True)],
     "O corte 2 tem um trecho de menos de 0.2 s"),
    ([_trecho(0, 10), _trecho(0, 10)] + [_trecho(0, 1, continua=True)] * 119,
     "somam 121 trechos"),
])
def test_o_plano_torto_diz_o_corte(trechos, trecho):
    with pytest.raises(compilacao.CompilacaoInvalida, match=trecho):
        compilacao.planejar(trechos)


def test_o_corte_re_editado_entra_pelos_trechos_da_edicao():
    """Um corte re-editado no editor vem em pedacos: o primeiro com o titulo,
    os seguintes com `continua`. Um capitulo por corte, e escuro so entre dois
    cortes -- dentro do corte, a emenda e a da propria edicao."""
    plano = compilacao.planejar([
        _trecho(10, 22, "Um", arquivo="a.mp4"),
        _trecho(30, 36, "Dois", arquivo="b.mp4"),
        _trecho(50, 56, "ignorado", arquivo="b.mp4", continua=True),
        _trecho(0, 12, "Três", arquivo="c.mp4")])
    assert [(t["corte"], t["continua"], t["titulo"], t["inicio_no_video"]) for t in plano] == \
        [(1, False, "Um", 0.0), (2, False, "Dois", 12.0), (2, True, "", 18.0),
         (3, False, "Três", 24.0)]
    assert compilacao.quantos_cortes(plano) == 3
    assert compilacao.capitulos_do_plano(plano) == [(0, "Um"), (12, "Dois"), (24, "Três")]
    # O primeiro trecho de um plano nunca "continua" um anterior que nao existe.
    assert compilacao.planejar([_trecho(0, 5, continua=True), _trecho(0, 5)])[0]["continua"] is False

    grafo = compilacao.comando(plano, "s.mp4")
    grafo = grafo[grafo.index("-filter_complex") + 1].split(";")
    video = {int(re.search(r"\[v(\d+)\]$", g).group(1)): g for g in grafo if re.search(r"\[v\d+\]$", g)}
    audio = {int(re.search(r"\[a(\d+)\]$", g).group(1)): g for g in grafo if re.search(r"\[a\d+\]$", g)}
    # Entre dois cortes, escurece e silencia; entre os pedacos do corte 2, nao.
    assert "fade=t=in" in video[0] and "fade=t=out" in video[0]
    assert "fade=t=in" in video[1] and "fade=t=out" not in video[1]
    assert "fade=t=in" not in video[2] and "fade=t=out" in video[2]
    assert "afade=t=out" not in audio[1] and "afade=t=in" not in audio[2]
    assert "afade=t=in" in audio[3] and "afade=t=out" in audio[3]


def test_os_capitulos_sao_os_cortes():
    plano = compilacao.planejar([_trecho(0, 40, "O começo"), _trecho(0, 5, "Rápido"),
                                 _trecho(0, 30, "O meio"), _trecho(0, 30, ""),
                                 _trecho(0, 30, "O fim")])
    # O de 5 s fica colado no seguinte e some; o sem titulo nao abre capitulo.
    assert compilacao.capitulos_do_plano(plano) == \
        [(0, "O começo"), (45, "O meio"), (105, "O fim")]


def test_a_legenda_e_a_do_projeto_no_tempo_da_compilacao():
    palavras_a = [{"word": " oi", "start": 0.5, "end": 0.9},
                  {"word": " gente", "start": 1.0, "end": 1.4},
                  {"word": " fora", "start": 12.0, "end": 12.5}]         # alem do trecho
    palavras_b = [{"word": " tchau", "start": 0.2, "end": 9.0},         # passa do fim
                  {"word": " torta", "start": "x", "end": 1}]
    plano = compilacao.planejar([_trecho(30, 40, palavras=palavras_a),
                                 _trecho(0, 5, palavras=palavras_b)])
    transcricao = compilacao.transcricao_do_plano(plano, "pt")
    assert transcricao["language"] == "pt"
    assert [s["text"] for s in transcricao["segments"]] == ["oi gente", "tchau"]
    assert transcricao["segments"][0]["words"][0] == {"word": " oi", "start": 0.5, "end": 0.9}
    # O segundo trecho comeca em 10 s na compilacao, e a palavra acaba no fim dele.
    assert transcricao["segments"][1]["words"] == [{"word": " tchau", "start": 10.2,
                                                    "end": 15.0}]


def test_o_comando_pula_para_cada_trecho_e_junta_tudo():
    plano = compilacao.planejar([_trecho(12.5, 20, arquivo="fonte.mp4"),
                                 _trecho(0, 3, arquivo="corte.mp4", tem_audio=False)])
    cmd = compilacao.comando(plano, "saida.mp4")
    assert cmd[cmd.index("fonte.mp4") - 5:cmd.index("fonte.mp4") + 1] == \
        ["-ss", "12.500", "-t", "7.500", "-i", "fonte.mp4"]
    grafo = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=2:v=1:a=1[vc][ac]" in grafo
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in grafo
    # O trecho sem audio entra com silencio do tamanho dele.
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=3.000" in grafo
    assert "[1:a]" not in grafo
    assert cmd[-1] == "saida.mp4" and "[vc]" in cmd
    # Com legenda e duas saidas: o mesmo grafo, dividido.
    dois = compilacao.comando(plano, "limpo.mp4", legenda="l.ass", saida_legendada="leg.mp4")
    grafo = dois[dois.index("-filter_complex") + 1]
    assert "[vc]split=2[vs][vq]" in grafo and "ass=filename='l.ass'" in grafo
    assert dois[-1] == "leg.mp4" and "limpo.mp4" in dois


def test_o_fundo_cobre_o_quadro_sem_esticar():
    fundo = compilacao.fundo(1920, 1080)
    assert fundo.startswith("crop=w=min(iw\\,ih*1920/1080):h=min(ih\\,iw*1080/1920)")
    assert "scale=480:270" in fundo and fundo.endswith("scale=1920:1080:flags=bilinear")


def test_a_sonda_le_o_que_o_ffmpeg_escreve():
    texto = ("Input #0, mov,mp4, from 'a.mp4':\n  Duration: 00:01:02.35, start: 0.0\n"
             "  Stream #0:0[0x1](und): Video: h264 (High), yuv420p, 1920x1080, 30 fps\n"
             "  Stream #0:1[0x2](und): Audio: aac (LC), 48000 Hz, stereo\n")
    assert compilacao.ler_sonda(texto) == {"duracao": 62.35, "tem_video": True,
                                           "tem_audio": True}
    mudo = texto.replace("  Stream #0:1[0x2](und): Audio: aac (LC), 48000 Hz, stereo\n", "")
    assert compilacao.ler_sonda(mudo)["tem_audio"] is False
    assert compilacao.ler_sonda("") == {"duracao": None, "tem_video": False, "tem_audio": False}


def test_os_estagios_sao_os_da_barra():
    import ast
    import pathlib
    arvore = ast.parse(pathlib.Path(compilar_video.__file__).read_text(encoding="utf-8"))
    usados = [n.args[0].value for n in ast.walk(arvore)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "stage"
              and n.args and isinstance(n.args[0], ast.Constant)]
    assert tuple(usados) == compilacao.ESTAGIOS


# --------------------------------------------------------------------------- #
# Com ffmpeg de verdade
# --------------------------------------------------------------------------- #

@pytest.fixture()
def ffmpeg(tmp_path, monkeypatch):
    """Um `ffmpeg` no PATH: o do sistema, ou o do imageio-ffmpeg (CI)."""
    if not shutil.which("ffmpeg"):
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pytest.skip("sem ffmpeg nem imageio-ffmpeg")
        pasta = tmp_path / "bin"
        pasta.mkdir()
        destino = pasta / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        try:
            destino.symlink_to(exe)
        except OSError:
            shutil.copy(exe, destino)
        monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ.get('PATH', '')}")
    import ffmpeg_utils
    rapido = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "32"]
    monkeypatch.setattr(ffmpeg_utils, "video_encode_args", lambda tier=None: list(rapido))
    monkeypatch.setenv("FFMPEG_ENCODER", "x264")
    monkeypatch.delenv("AUDIO_NORMALIZE", raising=False)
    return "ffmpeg"


def _fonte(pasta, nome, tamanho, segundos, com_audio=True):
    caminho = str(pasta / nome)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", f"testsrc=size={tamanho}:rate=30:duration={segundos}"]
    if com_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac", "-shortest"] if com_audio else [])
    subprocess.run(cmd + [caminho], check=True, capture_output=True)
    return caminho


def _medidas(caminho):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", caminho], capture_output=True, text=True)
    tamanho = re.search(r"Video: .*?(\d{3,4})x(\d{3,4})", r.stderr)
    return (tuple(int(x) for x in tamanho.groups()), compilacao.ler_sonda(r.stderr))


def _tem_libass():
    r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return " ass " in r.stdout


def _pedido(pasta, trechos, legenda="limpo"):
    (pasta / compilacao.ARQUIVO_DO_PEDIDO).write_text(json.dumps({
        "titulo": "Os melhores da semana", "descricao": "Uma seleção.", "idioma": "pt-BR",
        "legenda": legenda, "canal_id": None, "hashtags": ["cortes"], "trechos": trechos}),
        encoding="utf-8")


def test_compila_deitado_da_origem_e_do_corte_vertical(ffmpeg, tmp_path, capsys):
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    deitada = _fonte(fontes, "deitada.mp4", "640x360", 6)
    em_pe = _fonte(fontes, "corte.mp4", "360x640", 3)
    muda = _fonte(fontes, "muda.mp4", "320x240", 3, com_audio=False)
    pasta = tmp_path / "job"
    pasta.mkdir()
    palavras = [{"word": " era", "start": 0.2, "end": 0.6},
                {"word": " uma", "start": 0.7, "end": 1.0},
                {"word": " vez", "start": 1.1, "end": 1.6}]
    _pedido(pasta, [
        {"job_id": "a", "clip": 0, "arquivo": deitada, "corte_inicio": 1, "corte_fim": 3,
         "titulo": "Primeiro", "palavras": palavras},
        {"job_id": "b", "clip": 2, "arquivo": em_pe, "corte_inicio": 0, "corte_fim": 9,
         "titulo": "Segundo", "palavras": palavras, "vertical": True},
        {"job_id": "c", "clip": 1, "arquivo": muda, "corte_inicio": 0.5, "corte_fim": 2,
         "titulo": "Terceiro"},
    ], legenda="limpo" if _tem_libass() else "nenhuma")
    job_metrics.reset(str(pasta), compilacao.BASE)

    entregue = compilar_video.compilar(str(pasta))

    saida = capsys.readouterr().out
    assert f"CLIP_READY 0 {entregue}" in saida
    assert "(2.0s, do corte vertical)" not in saida        # o do corte vertical encolheu
    medidas, sonda = _medidas(str(pasta / entregue))
    assert medidas == (1920, 1080)
    # 2 s + 3 s (o corte vertical tem 3, nao 9) + 1,5 s.
    assert sonda["duracao"] == pytest.approx(6.5, abs=0.15) and sonda["tem_audio"]
    assert (pasta / "compilacao_clip_1.mp4").is_file()
    meta = json.loads((pasta / "compilacao_metadata.json").read_text(encoding="utf-8"))
    video = meta["shorts"][0]
    assert video["formato"] == "longo" and video["end"] == pytest.approx(6.5)
    assert video["video_title_for_youtube_short"] == "Os melhores da semana"
    # Curta demais para capitulos (o YouTube pede 10 s cada): a descricao sai sem lista.
    assert video["video_description_for_youtube"] == "Uma seleção.\n\n#cortes"
    assert [t["titulo"] for t in meta["compilacao"]["trechos"]] == \
        ["Primeiro", "Segundo", "Terceiro"]
    assert meta["compilacao"]["trechos"][1]["vertical"] is True
    segmentos = meta["transcript"]["segments"]
    assert [s["words"][0]["start"] for s in segmentos] == [0.2, 2.2]
    if _tem_libass():
        assert entregue.startswith("subtitled_")
        ass = (pasta / compilar_video.ARQUIVO_DA_LEGENDA).read_text(encoding="utf-8")
        assert "era uma vez" in ass


def test_o_trecho_que_sumiu_para_o_job_dizendo_qual(ffmpeg, tmp_path):
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    deitada = _fonte(fontes, "deitada.mp4", "640x360", 3)
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta, [
        {"arquivo": deitada, "corte_inicio": 0, "corte_fim": 2, "titulo": "Fica"},
        {"arquivo": str(fontes / "apagado.mp4"), "corte_inicio": 0, "corte_fim": 2,
         "titulo": "Sumiu"}])
    with pytest.raises(compilar_video.CompilacaoFalhou, match="O corte 2 .*Sumiu"):
        compilar_video.compilar(str(pasta))
    assert not (pasta / "compilacao_metadata.json").exists()


def test_o_corte_re_editado_sai_em_pedacos_de_verdade(ffmpeg, tmp_path, capsys):
    """O corte re-editado (dois trechos da mesma origem, com o meio tirado)
    sai com a duracao dos trechos, e nao da faixa que os cobre; o pedaco que
    sumiu fala do corte dele."""
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    deitada = _fonte(fontes, "deitada.mp4", "640x360", 6)
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta, [
        {"arquivo": deitada, "corte_inicio": 0, "corte_fim": 2, "titulo": "Inteiro"},
        {"arquivo": deitada, "corte_inicio": 2.5, "corte_fim": 3.5, "titulo": "Editado"},
        {"arquivo": deitada, "corte_inicio": 5, "corte_fim": 6, "titulo": "", "continua": True},
    ], legenda="nenhuma")
    job_metrics.reset(str(pasta), compilacao.BASE)
    entregue = compilar_video.compilar(str(pasta))
    saida = capsys.readouterr().out
    assert "🎬 2 cortes em 3 trechos" in saida and "do mesmo corte (re-editado)" in saida
    _, sonda = _medidas(str(pasta / entregue))
    assert sonda["duracao"] == pytest.approx(4.0, abs=0.15)      # 2 + 1 + 1, e nao 2 + 3,5
    meta = json.loads((pasta / "compilacao_metadata.json").read_text(encoding="utf-8"))
    assert meta["shorts"][0]["compilacao"] == {"cortes": 2, "trechos": 3}
    assert [(t["corte"], t["continua"]) for t in meta["compilacao"]["trechos"]] == \
        [(1, False), (2, False), (2, True)]

    outra = tmp_path / "outra"
    outra.mkdir()
    _pedido(outra, [
        {"arquivo": deitada, "corte_inicio": 0, "corte_fim": 2, "titulo": "Inteiro"},
        {"arquivo": deitada, "corte_inicio": 2.5, "corte_fim": 3.5, "titulo": "Editado"},
        {"arquivo": str(fontes / "apagado.mp4"), "corte_inicio": 0, "corte_fim": 1,
         "titulo": "", "continua": True}])
    with pytest.raises(compilar_video.CompilacaoFalhou, match="O corte 2 .“Editado”"):
        compilar_video.compilar(str(outra))


def test_main_diz_o_erro_e_sai_com_1(tmp_path, capsys):
    pasta = tmp_path / "vazia"
    pasta.mkdir()
    assert compilar_video.main(["--pasta", str(pasta)]) == 1
    assert "❌ O pedido da compilação" in capsys.readouterr().out
