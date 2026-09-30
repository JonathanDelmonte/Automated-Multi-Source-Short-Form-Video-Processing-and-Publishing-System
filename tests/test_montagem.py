"""A montagem do video de IA (etapa 7.7): o tempo de cada cena, o grafo do
ffmpeg e, com ffmpeg de verdade, o arquivo que sai."""
import os
import re
import shutil
import subprocess
import wave

import pytest

import montagem


def _palavras(inicios):
    return [{"word": f"p{i}", "start": s, "end": s + 0.3} for i, s in enumerate(inicios)]


def test_as_cenas_somam_o_audio_e_seguem_a_proporcao_do_texto():
    falas = ["a" * 30, "b" * 30, "c" * 40]
    palavras = _palavras([i * 0.5 for i in range(20)])      # 20 palavras em 10 s
    duracoes = montagem.duracoes_das_cenas(falas, palavras, 10.0)
    assert sum(duracoes) == pytest.approx(10.0)
    # 30% do texto -> a palavra 6 (3,0 s); 60% -> a palavra 12 (6,0 s).
    assert duracoes == pytest.approx([3.0, 3.0, 4.0])


def test_sem_palavras_vale_a_proporcao_dos_caracteres():
    duracoes = montagem.duracoes_das_cenas(["a" * 10, "b" * 30], [], 8.0)
    assert duracoes == pytest.approx([2.0, 6.0])


def test_cena_relampago_pega_tempo_da_vizinha():
    duracoes = montagem.duracoes_das_cenas(["a", "b" * 99], [], 10.0)
    assert duracoes[0] >= montagem.CENA_MINIMA_S
    assert sum(duracoes) == pytest.approx(10.0)


def test_palavras_fora_de_ordem_nao_deixam_duracao_negativa():
    palavras = _palavras([0.0, 5.0, 1.0, 2.0, 3.0, 4.0])
    duracoes = montagem.duracoes_das_cenas(["a" * 10, "b" * 10, "c" * 10], palavras, 6.0)
    assert all(d >= 0 for d in duracoes) and sum(duracoes) == pytest.approx(6.0)


def _ouvidas(texto, inicio=0.0, passo=0.5):
    return [{"word": " " + w, "start": inicio + i * passo, "end": inicio + i * passo + 0.4}
            for i, w in enumerate(texto.split())]


def test_a_legenda_mostra_o_roteiro_no_tempo_da_voz():
    """O whisper escreveu "Lulú" e "três"; a legenda diz o que o roteiro diz,
    no tempo em que a voz disse."""
    falas = ["A Lulu achou 3 cenouras.", "Que dia!"]
    palavras = montagem.palavras_do_roteiro(
        falas, _ouvidas("a Lulú achou três cenouras que dia"))
    assert [p["word"] for p in palavras] == [
        " A", " Lulu", " achou", " 3", " cenouras.", " Que", " dia!"]
    assert [p["start"] for p in palavras] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert [p["cena"] for p in palavras] == [0, 0, 0, 0, 0, 1, 1]


def test_o_que_o_whisper_nao_ouviu_fica_entre_as_vizinhas_e_o_que_inventou_some():
    ouvidas = _ouvidas("era uma vez") + [{"word": " obrigado", "start": 1.5, "end": 1.9}] \
        + [{"word": " coelhinha", "start": 3.0, "end": 3.6}]
    palavras = montagem.palavras_do_roteiro(["Era uma vez uma coelhinha"], ouvidas)
    assert [p["word"].strip() for p in palavras] == ["Era", "uma", "vez", "uma", "coelhinha"]
    quarta = palavras[3]
    # "obrigado" (inventado) virou o tempo de "uma", que o whisper trocou.
    assert palavras[2]["end"] <= quarta["start"] < quarta["end"] <= palavras[4]["start"]
    assert palavras[4]["start"] == 3.0
    inicios = [p["start"] for p in palavras]
    assert inicios == sorted(inicios)


def test_sem_nada_ouvido_nao_ha_legenda():
    assert montagem.palavras_do_roteiro(["Era uma vez"], []) == []
    assert montagem.palavras_do_roteiro([], _ouvidas("era uma vez")) == []


def test_com_as_palavras_do_roteiro_a_cena_troca_quando_a_fala_comeca():
    falas = ["Um dois tres.", "Quatro.", "Cinco seis."]
    palavras = montagem.palavras_do_roteiro(falas, _ouvidas("um dois tres quatro cinco seis",
                                                            passo=1.0))
    duracoes = montagem.duracoes_das_cenas(falas, palavras, 7.0)
    # A cena 2 comeca em 3,0 s ("Quatro") e a 3 em 4,0 s -- a 2 tem 1,0 s, menos
    # que a minima, e pega 0,2 s da seguinte.
    assert duracoes == pytest.approx([3.0, 1.2, 2.8])


def test_cada_cena_anda_de_um_jeito_na_ordem():
    filtros = [montagem.filtro_da_cena(i, i, 2.0) for i in range(4)]
    assert "z='1+0.15*on/60'" in filtros[0]                  # aproximar
    assert "z='1.15-0.15*on/60'" in filtros[1]               # afastar
    assert "x='(iw-iw/zoom)*on/60'" in filtros[2]            # direita
    assert "x='(iw-iw/zoom)*(1-on/60)'" in filtros[3]        # esquerda
    assert all(":d=60:s=1080x1920:fps=30" in f for f in filtros)
    assert filtros[0].endswith("[v0]") and filtros[0].startswith("[0:v]scale=1620:2880")


def test_o_comando_junta_as_cenas_a_voz_e_a_legenda():
    cmd = montagem.comando(["a.png", "b.png"], [1.5, 2.0], "voz.wav", "out.mp4",
                           legenda="C:\\pasta\\legenda.ass")
    grafo = cmd[cmd.index("-filter_complex") + 1]
    assert "[v0][v1]concat=n=2:v=1:a=0[vc]" in grafo
    assert "ass=filename='C\\:/pasta/legenda.ass'" in grafo
    assert cmd[cmd.index("-map") + 1] == "[vl]" and "2:a" in cmd
    sem = montagem.comando(["a.png"], [1.0], "voz.wav", "out.mp4")
    assert sem[sem.index("-map") + 1] == "[vc]"
    duas = montagem.comando(["a.png"], [1.0], "voz.wav", "limpo.mp4", legenda="l.ass",
                            saida_legendada="legendado.mp4",
                            video_args_legendada=["-c:v", "libx264", "-crf", "18"])
    grafo = duas[duas.index("-filter_complex") + 1]
    assert "[vc]split=2[vs][va]" in grafo and "[va]ass=filename='l.ass'" in grafo
    mapas = [duas[i + 1] for i, a in enumerate(duas) if a == "-map"]
    assert mapas == ["[vs]", "1:a", "[vl]", "1:a"]
    # Cada saida com os argumentos dela: o legendado leva os proprios.
    depois_do_limpo = duas[duas.index("limpo.mp4"):]
    assert depois_do_limpo[depois_do_limpo.index("-crf") + 1] == "18"
    assert duas[duas.index("-crf") + 1] == "20"
    with pytest.raises(ValueError):
        montagem.comando(["a.png"], [1.0, 2.0], "voz.wav", "out.mp4")


# --- com ffmpeg de verdade -----------------------------------------------------

@pytest.fixture()
def ffmpeg(tmp_path, monkeypatch):
    """Um `ffmpeg` no PATH: o do sistema, ou o do imageio-ffmpeg (CI)."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
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
    return "ffmpeg"


def _imagens(tmp_path, n):
    from PIL import Image
    caminhos = []
    for i in range(n):
        caminho = tmp_path / f"cena_{i}.png"
        Image.new("RGB", (384, 672), (60 * i % 255, 120, 200)).save(caminho)
        caminhos.append(str(caminho))
    return caminhos


def _voz(tmp_path, segundos):
    caminho = tmp_path / "voz.wav"
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(b"\x00\x01" * int(24000 * segundos))
    return str(caminho)


def _quadros(ffmpeg, caminho):
    r = subprocess.run([ffmpeg, "-loglevel", "error", "-i", caminho, "-map", "0:v",
                        "-f", "framemd5", "-"], capture_output=True, text=True, check=True)
    return [l for l in r.stdout.splitlines() if l and not l.startswith("#")]


def _medidas(ffmpeg, caminho):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", caminho], capture_output=True, text=True)
    achou = re.search(r"Video: .*?(\d{3,4})x(\d{3,4})", r.stderr)
    return (int(achou.group(1)), int(achou.group(2))) if achou else None


def test_o_video_sai_vertical_com_o_tempo_da_voz(ffmpeg, tmp_path):
    saida = str(tmp_path / "video.mp4")
    montagem.montar(_imagens(tmp_path, 3), [1.0, 1.0, 1.5], _voz(tmp_path, 3.5), saida,
                    video_args=["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"])
    assert _medidas(ffmpeg, saida) == (1080, 1920)
    # 3,5 s a 30 quadros por segundo.
    assert abs(len(_quadros(ffmpeg, saida)) - 105) <= 2


def test_a_legenda_queima_no_mesmo_encode(ffmpeg, tmp_path):
    subtitles = pytest.importorskip("subtitles")
    ass = str(tmp_path / "legenda.ass")
    transcricao = {"segments": [{"start": 0.0, "end": 2.0, "text": "era uma vez",
                                 "words": [{"word": "era", "start": 0.0, "end": 0.5},
                                           {"word": "uma", "start": 0.5, "end": 1.0},
                                           {"word": "vez", "start": 1.0, "end": 2.0}]}]}
    assert subtitles.generate_ass(transcricao, 0.0, 2.0, ass)
    filtros = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True,
                             text=True).stdout
    if " ass " not in filtros:
        pytest.skip("este ffmpeg nao tem libass")
    saida = str(tmp_path / "com_legenda.mp4")
    montagem.montar(_imagens(tmp_path, 2), [1.0, 1.0], _voz(tmp_path, 2.0), saida, legenda=ass,
                    video_args=["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"])
    assert _medidas(ffmpeg, saida) == (1080, 1920)


def test_o_limpo_e_o_legendado_saem_do_mesmo_grafo(ffmpeg, tmp_path):
    subtitles = pytest.importorskip("subtitles")
    filtros = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True,
                             text=True).stdout
    if " ass " not in filtros:
        pytest.skip("este ffmpeg nao tem libass")
    ass = str(tmp_path / "legenda.ass")
    transcricao = {"segments": [{"start": 0.0, "end": 2.0, "text": "era uma vez", "words":
                                 montagem.palavras_do_roteiro(["Era uma vez"],
                                                              _ouvidas("era uma vez"))}]}
    assert subtitles.generate_ass(transcricao, 0.0, 2.0, ass)
    limpo, legendado = str(tmp_path / "limpo.mp4"), str(tmp_path / "legendado.mp4")
    rapido = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30"]
    montagem.montar(_imagens(tmp_path, 2), [1.0, 1.0], _voz(tmp_path, 2.0), limpo,
                    legenda=ass, saida_legendada=legendado, video_args=rapido,
                    audio_args=["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac"])
    a, b = _quadros(ffmpeg, limpo), _quadros(ffmpeg, legendado)
    assert len(a) == len(b) and abs(len(a) - 60) <= 2
    # O mesmo movimento, e a legenda so no segundo.
    assert a != b and _medidas(ffmpeg, legendado) == (1080, 1920)


def test_a_montagem_que_falha_diz_o_erro(ffmpeg, tmp_path):
    with pytest.raises(RuntimeError, match="a montagem falhou"):
        montagem.montar([str(tmp_path / "nao-existe.png")], [1.0], _voz(tmp_path, 1.0),
                        str(tmp_path / "x.mp4"))
