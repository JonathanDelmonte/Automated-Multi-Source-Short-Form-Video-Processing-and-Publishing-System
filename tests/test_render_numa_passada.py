"""O reenquadramento renderiza o clipe numa passada so, cortando por QUADRO.

Antes era um ffmpeg por cena mais um concat. Alem do custo de subir o ffmpeg e
o encoder a cada cena (no NVENC, um contexto CUDA por processo), o corte por
TEMPO (`-ss` / `-t`) saia com 0 a 2 quadros a mais por trecho: 1515 quadros
para 1500 num clipe de 50 s com 23 cenas, e como o audio vem inteiro do clipe
original, a imagem ia atrasando em relacao ao som a cada troca de cena.

A prova que importa e a ultima classe: com ffmpeg de verdade, a passada unica
tem de sair IGUAL, quadro a quadro, ao que cada trecho renderizado sozinho e
cortado por quadro daria. No CI o ffmpeg vem do `imageio-ffmpeg`; sem nenhum
dos dois, esses testes sao pulados.
"""
import os
import re
import shutil
import subprocess

import pytest

import reframe_v2
from reframe_v2 import (dedupe_sendcmd_lines, escape_filter_value,
                        general_filtergraph, grafo_numa_passada, taxa_racional)


class TestTaxaRacional:

    @pytest.mark.parametrize("fps,esperado", [
        (30.0, "30/1"),
        (29.97002997002997, "30000/1001"),
        (23.976023976023978, "24000/1001"),
        (59.94005994005994, "60000/1001"),
        (25.0, "25/1"),
        (60.0, "60/1"),
    ])
    def test_taxas_comuns_saem_exatas(self, fps, esperado):
        assert taxa_racional(fps) == esperado

    @pytest.mark.parametrize("fps", [0, -30.0])
    def test_taxa_invalida_nao_vira_comando(self, fps):
        with pytest.raises(ValueError):
            taxa_racional(fps)


def _rotulos(grafo):
    return re.findall(r"\[([^\]]+)\]", grafo)


class TestGrafoNumaPassada:
    TRECHOS = [(0, 30, "TRACK"), (30, 45, "GENERAL"), (45, 90, "TRACK")]

    def _grafos(self):
        geral = general_filtergraph(216, 384, orig_w=320, orig_h=180)
        return [
            "[0:v]sendcmd=f='a.txt',crop@c0=w=100:h=180:x=0:y=0,scale=216:384,setsar=1[v]",
            geral,
            "[0:v]sendcmd=f='c.txt',crop@c2=w=100:h=180:x=9:y=0,scale=216:384,setsar=1[v]",
        ]

    def test_cada_fio_nasce_uma_vez_e_morre_uma_vez(self):
        """Dois `[bg]` num grafo so seriam o mesmo fio. Todo rotulo tem de
        aparecer exatamente duas vezes: quem produz e quem consome."""
        grafo = grafo_numa_passada(self.TRECHOS, self._grafos(), "30/1")
        contagem = {}
        for r in _rotulos(grafo):
            contagem[r] = contagem.get(r, 0) + 1
        assert contagem.pop("0:v") == 1
        assert contagem.pop("v") == 1
        assert all(n == 2 for n in contagem.values()), contagem

    def test_corta_por_quadro_e_zera_o_relogio(self):
        grafo = grafo_numa_passada(self.TRECHOS, self._grafos(), "30/1")
        for inicio, fim, _ in self.TRECHOS:
            assert (f"trim=start_frame={inicio}:end_frame={fim},"
                    f"setpts=PTS-STARTPTS") in grafo
        assert "split=3" in grafo and "concat=n=3:v=1:a=0," in grafo

    def test_a_ordem_do_concat_e_a_ordem_dos_trechos(self):
        grafo = grafo_numa_passada(self.TRECHOS, self._grafos(), "30/1")
        assert "[v_0][v_1][v_2]concat=n=3:v=1:a=0," in grafo

    def test_renumera_os_quadros_depois_do_concat(self):
        """O concat da duracao zero a um trecho de um quadro so, e o seguinte
        comecaria no mesmo instante. Renumerar poe o quadro N em N/taxa."""
        grafo = grafo_numa_passada(self.TRECHOS, self._grafos(), "30000/1001")
        assert grafo.endswith("concat=n=3:v=1:a=0,setpts=N/(30000/1001)/TB[v]")

    def test_grafo_fora_do_formato_e_recusado(self):
        with pytest.raises(ValueError):
            grafo_numa_passada([(0, 10, "TRACK")], ["scale=10:10[v]"], "30/1")
        with pytest.raises(ValueError):
            grafo_numa_passada([(0, 10, "TRACK")], [], "30/1")


def test_cada_trecho_tem_crop_com_nome_proprio():
    """O `sendcmd` manda o comando a TODO filtro com o nome dado. Numa passada
    so, `crop@c` repetido faria a camera de um trecho mexer a de outro."""
    fonte = open(reframe_v2.__file__, encoding="utf-8").read()
    assert 'alvo = f"crop@c{idx}"' in fonte
    assert "target=alvo" in fonte
    assert "f\"{alvo}={init},\"" in fonte


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
    (pasta / "ffmpeg").symlink_to(exe)
    monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ.get('PATH', '')}")
    return "ffmpeg"


def _md5_por_quadro(ffmpeg, *args):
    r = subprocess.run([ffmpeg, "-loglevel", "error", *args, "-f", "framemd5", "-"],
                       capture_output=True, text=True, check=True)
    return [l.rsplit(",", 1)[-1].strip() for l in r.stdout.splitlines()
            if l and not l.startswith("#")]


@pytest.fixture()
def clipe(ffmpeg, tmp_path):
    """90 quadros 320x180 a 30 fps, com imagem que muda a cada quadro."""
    caminho = tmp_path / "clipe.mp4"
    subprocess.run([
        ffmpeg, "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30",
        "-f", "lavfi", "-i", "sine=f=440:r=48000",
        "-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-shortest", str(caminho),
    ], check=True)
    return caminho


# Tres trechos de UM quadro seguidos: cada um deixava o seguinte comecar no
# mesmo instante, e o encoder jogava quadro fora quando o atraso somava.
TRECHOS = [(0, 20, "TRACK"), (20, 21, "TRACK"), (21, 22, "TRACK"),
           (22, 23, "GENERAL"), (23, 50, "GENERAL"), (50, 77, "TRACK"),
           (77, 90, "TRACK")]


@pytest.mark.parametrize("ramos_por_passada", [40, 2],
                         ids=["uma-passada", "em-lotes"])
def test_passada_unica_bate_quadro_a_quadro_com_cada_trecho_sozinho(
        ffmpeg, clipe, tmp_path, monkeypatch, ramos_por_passada):
    fps = 30.0
    # Sem perda, para que "igual" queira dizer igual.
    monkeypatch.setattr(reframe_v2, "video_encode_args",
                        lambda _tier: ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0"])
    monkeypatch.setattr(reframe_v2, "_RAMOS_POR_PASSADA", ramos_por_passada)
    trechos = TRECHOS
    grafos = []
    for k, (inicio, fim, estrategia) in enumerate(trechos):
        if estrategia == "GENERAL":
            grafos.append(general_filtergraph(216, 384, orig_w=320, orig_h=180))
            continue
        # Cada trecho com a SUA camera -- se os crops se confundissem, os
        # quadros de um trecho sairiam com o enquadramento de outro.
        xs = [(k * 40 + i) % 200 for i in range(fim - inicio)]
        cmd = tmp_path / f"cmd_{k}.txt"
        cmd.write_text("\n".join(dedupe_sendcmd_lines(xs, fps, target=f"crop@c{k}")) + "\n")
        grafos.append(f"[0:v]sendcmd=f='{escape_filter_value(str(cmd))}',"
                      f"crop@c{k}=w=100:h=180:x={xs[0]}:y=0,scale=216:384,setsar=1[v]")

    saida = tmp_path / "saida.mp4"
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    reframe_v2._render_numa_passada(str(clipe), str(saida), trechos, grafos, fps,
                                    str(trabalho))

    obtido = _md5_por_quadro(ffmpeg, "-i", str(saida), "-map", "0:v:0")
    referencia = []
    for (inicio, fim, _), grafo in zip(trechos, grafos):
        sozinho = grafo.replace(
            "[0:v]", f"[0:v]trim=start_frame={inicio}:end_frame={fim},"
                     f"setpts=PTS-STARTPTS,", 1)
        referencia += _md5_por_quadro(ffmpeg, "-i", str(clipe),
                                      "-filter_complex", sozinho, "-map", "[v]")

    assert len(obtido) == 90, "cada quadro da fonte vira exatamente um da saida"
    assert obtido == referencia


def test_a_saida_leva_o_audio_do_clipe(ffmpeg, clipe, tmp_path):
    saida = tmp_path / "saida.mp4"
    grafo = "[0:v]scale=216:384,setsar=1[v]"
    reframe_v2._render_numa_passada(str(clipe), str(saida), [(0, 90, "TRACK")],
                                    [grafo], 30.0, str(tmp_path))
    sonda = subprocess.run([ffmpeg, "-i", str(saida)], capture_output=True, text=True).stderr
    assert "Audio: aac" in sonda
    assert "30 fps" in sonda
