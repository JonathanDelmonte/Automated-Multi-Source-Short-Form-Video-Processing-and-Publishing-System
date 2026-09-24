"""A marca Virtu Clips em cada lugar em que ela aparece (24-set-2026).

A logo mora num arquivo so (`marca/virtu-clips.png`) e um modulo so a desenha
(`ajudante/marca.py`). O site nao roda Python no build, entao os arquivos dele
sao versionados -- e estes testes pegam o dia em que a logo muda e eles ficam
para tras, ou em que um tamanho do icone recebe o desenho errado.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image, ImageChops  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ajudante"))

import marca  # noqa: E402


def _diferenca(a, b) -> int:
    """A maior diferenca de um canal entre duas imagens do mesmo tamanho. O
    LANCZOS pode variar um ponto entre versoes do Pillow; um desenho
    diferente varia dezenas."""
    assert a.size == b.size
    extremos = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getextrema()
    return max(maximo for _minimo, maximo in extremos)


@pytest.mark.parametrize("nome", sorted(marca.arquivos_do_site()))
def test_o_site_serve_a_marca_desenhada_agora(nome):
    esperado = marca.arquivos_do_site()[nome]
    with Image.open(marca.PUBLICO / nome) as servido:
        assert servido.size == esperado.size, (
            f"{nome} mudou de tamanho: rode `python ajudante/marca.py`")
        assert _diferenca(servido, esperado) <= 3, (
            f"dashboard/public/{nome} nao e o que a logo de hoje desenha: "
            "rode `python ajudante/marca.py` e versione o resultado")


def test_o_html_aponta_para_a_marca():
    html = (RAIZ / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert "<title>Virtu Clips</title>" in html
    assert 'href="/favicon.png"' in html and "logo-openshorts" not in html


def test_cada_tamanho_do_icone_recebe_o_desenho_que_se_le_nele(tmp_path):
    """Abaixo de 48 px a logo inteira e um borrao: la vai o monograma."""
    ico = tmp_path / "v.ico"
    marca.gravar_ico(ico)
    with Image.open(ico) as im:
        assert {(t, t) for t in marca.TAMANHOS_DO_ICO} <= set(im.info["sizes"])
        for lado in (16, 32, 48, 256):
            im.size = (lado, lado)
            quadro = im.copy()
            assert _diferenca(quadro, marca.icone(lado)) <= 3, lado
    assert marca.icone(16).tobytes() == marca.monograma(16).tobytes()
    assert marca.icone(48).tobytes() == marca.icone_grande(48).tobytes()


def test_a_logo_e_branca_sobre_transparente():
    """Todo desenho daqui poe preto por baixo dela; uma logo que viesse com
    fundo proprio apareceria como um quadrado no site."""
    logo = marca.logo()
    assert logo.getpixel((0, 0))[3] == 0, "o canto da logo tem de ser transparente"
    dados = logo.tobytes()  # RGBA, 4 bytes por pixel
    opacos = [dados[i:i + 4] for i in range(0, len(dados), 4) if dados[i + 3] == 255]
    claros = [p for p in opacos if min(p[:3]) > 200]
    assert len(claros) > 0.9 * len(opacos)


def test_as_imagens_do_instalador_tem_a_proporcao_do_inno(tmp_path):
    feitos = marca.gravar_imagens_do_assistente(tmp_path)
    for caminho in feitos:
        with Image.open(caminho) as im:
            largura, altura = im.size
            if caminho.name.startswith("grande-"):
                # O Inno mantem 164:314 e ajusta a imagem a area.
                assert abs(largura / altura - 164 / 314) < 0.01, caminho.name
            else:
                assert largura == altura, caminho.name
