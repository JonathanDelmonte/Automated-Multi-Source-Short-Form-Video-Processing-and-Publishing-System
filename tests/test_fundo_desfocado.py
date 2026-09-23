"""O fundo desfocado do GENERAL e do INSET e desfocado em 1/4 da resolucao.

A cadeia de antes ampliava o quadro inteiro da fonte ate a altura da saida
(1920x1080 -> 3413x1920) para jogar dois tercos fora e borrar o resto em
resolucao cheia. Era o filtro mais caro do render, para produzir um borrao.

Duas coisas precisam continuar verdade, e cada uma tem sua classe:

* a cadeia nao volta a ampliar a fonte inteira, nem a reduzir sem filtro
  (`fast_bilinear` serrilha textura fina e o fundo passa a tremer);
* o fundo novo continua sendo o MESMO fundo: medido com ffmpeg de verdade
  contra a cadeia antiga, que fica aqui como referencia.
"""
import os
import shutil
import subprocess

import pytest

import camera_inset
import reframe_v2
from ffmpeg_utils import FUNDO_DIVISOR, fundo_desfocado


def _fundo(grafo):
    """A cadeia que ENTRA por `[bga]` e sai em `[bg]` (o `split` tambem nomeia
    `[bga]`, como saida, e vem antes)."""
    return grafo.split(";[bga]", 1)[1].split("[bg]", 1)[0]


class TestCadeia:

    def test_general_usa_o_fundo_em_um_quarto(self):
        grafo = reframe_v2.general_filtergraph(1080, 1920, orig_w=1920, orig_h=1080)
        assert _fundo(grafo) == fundo_desfocado(1080, 1920, 12)

    def test_wide_usa_o_mesmo_fundo(self):
        # WIDE e o GENERAL sem cortar as laterais: o fundo e o mesmo.
        grafo = reframe_v2.general_filtergraph(
            1080, 1920, reframe_v2.full_width_content_height(1920, 1080, 1080))
        assert _fundo(grafo) == fundo_desfocado(1080, 1920, 12)

    def test_inset_usa_o_mesmo_fundo(self):
        grafo = camera_inset.inset_filtergraph(1920, 1080, 1080, 1920,
                                               (1500, 880, 350, 200))
        assert _fundo(grafo) == fundo_desfocado(1080, 1920, 14)

    def test_borra_em_um_quarto_e_volta_ao_tamanho_da_saida(self):
        cadeia = fundo_desfocado(1080, 1920, 12)
        assert "scale=270:480," in cadeia
        assert "gblur=sigma=3," in cadeia
        assert cadeia.endswith("scale=1080:1920:flags=bilinear")

    def test_o_desfoque_e_o_mesmo_na_escala_da_saida(self):
        # sigma 12 na saida = sigma 3 num quadro 4x menor.
        assert f"gblur=sigma={14 / FUNDO_DIVISOR:g}," in fundo_desfocado(1080, 1920, 14)

    def test_nunca_amplia_a_fonte_inteira_antes_de_borrar(self):
        # O `scale=-2:<altura da saida>` era a ampliacao de 3413x1920 por
        # quadro. O primeiro passo agora e recortar, na resolucao da fonte.
        cadeia = fundo_desfocado(1080, 1920, 12)
        assert "scale=-2:" not in cadeia
        assert cadeia.startswith("crop=")

    def test_reducao_com_filtro_de_verdade(self):
        # fast_bilinear nao alarga o filtro ao reduzir: textura fina dobra em
        # frequencia baixa, que o desfoque nao tira (ver a classe abaixo).
        assert "fast_bilinear" not in fundo_desfocado(1080, 1920, 12)

    @pytest.mark.parametrize("w,h", [(1080, 1920), (1078, 1918), (1080, 1080),
                                     (720, 1280), (6, 6)])
    def test_dimensoes_pares(self, w, h):
        # yuv420p recusa dimensao impar no meio do grafo.
        cadeia = fundo_desfocado(w, h, 12)
        reduzido = cadeia.split(",scale=", 1)[1].split(",", 1)[0]
        rw, rh = (int(v) for v in reduzido.split(":")[:2])
        assert rw % 2 == 0 and rh % 2 == 0 and rw >= 2 and rh >= 2


# --- com ffmpeg de verdade -----------------------------------------------------

def _antigo(w, h, sigma):
    """A cadeia de antes de 23-set-2026, como referencia do que o fundo era."""
    return (f"scale=-2:{h},crop=w=min(iw\\,{w}):h={h},"
            f"scale={w}:{h},gblur=sigma={sigma}")


@pytest.fixture()
def ffmpeg():
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pytest.skip("sem ffmpeg nem imageio-ffmpeg")


def _ssim(ffmpeg, fonte, a, b):
    grafo = f"{fonte},split=2[a0][b0];[a0]{a}[x];[b0]{b}[y];[x][y]ssim"
    r = subprocess.run([ffmpeg, "-hide_banner", "-f", "lavfi", "-i", "nullsrc",
                        "-filter_complex", grafo, "-f", "null", "-"],
                       capture_output=True, text=True, env=os.environ)
    linhas = [l for l in r.stderr.splitlines() if "SSIM" in l]
    assert linhas, r.stderr[-500:]
    return float(linhas[-1].split("All:")[1].split()[0])


class TestFidelidade:
    """O fundo novo contra o antigo, numa fonte 16:9 e numa saida 9:16.

    Os limites vieram da medicao: 0,9985 e 0,985 com a reducao bicubica que o
    codigo usa, 0,996 e 0,925 com `fast_bilinear`. O zone plate e o pior caso
    de serrilhado -- e nele que a reducao sem filtro aparece.
    """
    W, H = 360, 640

    def test_video_comum(self, ffmpeg):
        fonte = "testsrc2=s=640x360:r=30:d=2"
        assert _ssim(ffmpeg, fonte, _antigo(self.W, self.H, 12),
                     fundo_desfocado(self.W, self.H, 12)) >= 0.99

    def test_zone_plate(self, ffmpeg):
        # O `zoneplate` entrou no ffmpeg 7.0; num mais velho, nada a medir.
        filtros = subprocess.run([ffmpeg, "-hide_banner", "-filters"],
                                 capture_output=True, text=True).stdout
        if " zoneplate " not in filtros:
            pytest.skip("ffmpeg sem a fonte zoneplate")
        fonte = "zoneplate=s=640x360:r=30:d=2:kt2=4:kx2=256:ky2=256:kt=2"
        assert _ssim(ffmpeg, fonte, _antigo(self.W, self.H, 12),
                     fundo_desfocado(self.W, self.H, 12)) >= 0.97

    def test_fonte_mais_estreita_que_a_saida(self, ffmpeg):
        # 9:20 numa saida 9:16: a cadeia antiga esticava a fonte inteira, e a
        # nova tem de esticar do mesmo jeito, nao recortar.
        fonte = "testsrc2=s=288x640:r=30:d=1"
        assert _ssim(ffmpeg, fonte, _antigo(self.W, self.H, 12),
                     fundo_desfocado(self.W, self.H, 12)) >= 0.99
