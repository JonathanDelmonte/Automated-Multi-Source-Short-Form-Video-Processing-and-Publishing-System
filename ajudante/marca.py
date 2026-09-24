"""A marca Virtu Clips desenhada para cada lugar em que ela aparece (24-set-2026).

A logo e do autor: `marca/virtu-clips.png` -- VIRTU em letra liquida, a barra
com o alfinete e CLIPS em caixa alta condensada --, branca sobre transparente.
Foi feita para fundo escuro, e todo desenho daqui poe preto por baixo dela.

**Abaixo de 48 px a logo vira borrao**: VIRTU e CLIPS empilhados num icone de
16 px teriam uns quatro pixels de altura cada. Ali entra o MONOGRAMA, um V na
Anton -- a mesma familia pesada e condensada do CLIPS, que ja vem com o motor
(`fonts/`, os ganchos usam). O .ico leva os dois desenhos, e o Windows escolhe
pelo tamanho: cada tamanho recebe o que se le nele.

Um lugar so desenha, e todos chamam:

- a bandeja do ajudante (`monograma`);
- o instalador (`gravar_ico` e `gravar_imagens_do_assistente`, pelo
  `empacotar.py`, no CI);
- o site: `python ajudante/marca.py` regrava os arquivos de
  `dashboard/public/`. O build do site nao roda Python, entao o resultado e
  versionado -- e `tests/test_marca.py` falha se ele ficar para tras da logo.

Pillow so dentro das funcoes: o `ajudante.py` importa este modulo, e o CI de
sempre roda sem Pillow.
"""
from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
LOGO = RAIZ / "marca" / "virtu-clips.png"
FONTE = RAIZ / "fonts" / "Anton-Regular.ttf"
PUBLICO = RAIZ / "dashboard" / "public"

NOME = "Virtu Clips"
PRETO = (10, 10, 11, 255)  # o --color-paper do site
BRANCO = (255, 255, 255, 255)

# Ate este lado o icone e o monograma; acima, a logo inteira.
MAIOR_MONOGRAMA = 40
TAMANHOS_DO_ICO = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)

# As areas de imagem do assistente do Inno Setup 6.7 (100%, 150%, 250% de
# DPI). Ele escolhe a mais proxima e ajusta, sempre na proporcao 164:314.
ASSISTENTE_GRANDE = ((202, 386), (336, 643), (534, 1022))
ASSISTENTE_PEQUENA = (58, 97, 159)

# Desenha grande e reduz: a borda do V e as curvas da logo saem suaves, que
# e o que o LANCZOS faz e o desenho direto no tamanho final nao.
_ESCALA = 8


def _imagem():
    from PIL import Image
    return Image


def logo():
    """A logo, recortada justa: quem usa decide a margem."""
    Image = _imagem()
    with Image.open(LOGO) as im:
        return im.convert("RGBA")


def _fundo(lado: int, cheio: bool):
    from PIL import ImageDraw
    Image = _imagem()
    img = Image.new("RGBA", (lado, lado), PRETO if cheio else (0, 0, 0, 0))
    if not cheio:
        ImageDraw.Draw(img).rounded_rectangle(
            (0, 0, lado - 1, lado - 1), radius=round(lado * 0.22), fill=PRETO)
    return img


def monograma(lado: int = 64, cheio: bool = False):
    """O V da Anton, branco sobre o quadrado preto de cantos redondos (ou o
    quadrado inteiro, com `cheio`: o iOS e o Android arredondam sozinhos)."""
    from PIL import ImageDraw, ImageFont
    Image = _imagem()
    grande = lado * _ESCALA
    img = _fundo(grande, cheio)
    d = ImageDraw.Draw(img)
    fonte = ImageFont.truetype(str(FONTE), grande)
    x0, y0, x1, y1 = d.textbbox((0, 0), "V", font=fonte)
    # O V ocupa 66% da altura: menos some em 16 px, mais encosta nos cantos
    # redondos.
    alvo = grande * 0.66
    fonte = ImageFont.truetype(str(FONTE), round(grande * alvo / (y1 - y0)))
    x0, y0, x1, y1 = d.textbbox((0, 0), "V", font=fonte)
    d.text(((grande - (x1 - x0)) / 2 - x0, (grande - (y1 - y0)) / 2 - y0), "V",
           font=fonte, fill=BRANCO)
    return img.resize((lado, lado), Image.LANCZOS)


def _logo_centrada(largura: int, altura: int, ocupa: float, fundo):
    """A logo no meio de `fundo`, com `ocupa` da largura (ou da altura, o que
    couber primeiro)."""
    Image = _imagem()
    marca = logo()
    escala = min(largura * ocupa / marca.width, altura * ocupa / marca.height)
    tamanho = (max(1, round(marca.width * escala)), max(1, round(marca.height * escala)))
    marca = marca.resize(tamanho, Image.LANCZOS)
    fundo.alpha_composite(marca, ((largura - tamanho[0]) // 2, (altura - tamanho[1]) // 2))
    return fundo


def icone_grande(lado: int = 256, cheio: bool = False):
    """A logo inteira sobre o quadrado preto: para 48 px e acima."""
    return _logo_centrada(lado, lado, 0.74, _fundo(lado, cheio))


def icone(lado: int):
    """O desenho certo para cada tamanho."""
    return monograma(lado) if lado <= MAIOR_MONOGRAMA else icone_grande(lado)


def gravar_ico(destino: Path) -> None:
    """Um .ico com um desenho por tamanho. O Pillow so guarda os tamanhos ate
    o da imagem principal, entao ela e a MAIOR, e as outras vao prontas em
    `append_images` -- sem elas, ele reduziria a logo de 256 para 16."""
    tamanhos = sorted(TAMANHOS_DO_ICO, reverse=True)
    imagens = [icone(t) for t in tamanhos]
    destino.parent.mkdir(parents=True, exist_ok=True)
    imagens[0].save(destino, format="ICO", sizes=[(t, t) for t in tamanhos],
                    append_images=imagens[1:])


def imagem_do_assistente(largura: int, altura: int):
    """A faixa da esquerda do instalador (primeira e ultima tela): preta, com
    a logo no meio."""
    Image = _imagem()
    return _logo_centrada(largura, altura, 0.72, Image.new("RGBA", (largura, altura), PRETO))


def imagem_pequena_do_assistente(lado: int):
    """O canto de cima das outras telas: a logo sem fundo, porque o
    instalador e escuro (WizardStyle dark) e a faixa de cima ja e preta."""
    Image = _imagem()
    return _logo_centrada(lado, lado, 0.9, Image.new("RGBA", (lado, lado), (0, 0, 0, 0)))


def gravar_imagens_do_assistente(pasta: Path) -> list:
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = []
    for largura, altura in ASSISTENTE_GRANDE:
        caminho = pasta / f"grande-{largura}.png"
        imagem_do_assistente(largura, altura).save(caminho, optimize=True)
        feitos.append(caminho)
    for lado in ASSISTENTE_PEQUENA:
        caminho = pasta / f"pequena-{lado}.png"
        imagem_pequena_do_assistente(lado).save(caminho, optimize=True)
        feitos.append(caminho)
    return feitos


# --- o site -------------------------------------------------------------------

# O que o site serve de dashboard/public/, e o desenho de cada um. A logo sai
# com o dobro do tamanho em que aparece (a barra lateral a mostra com ~80 px
# de largura), para ficar nitida em tela de alta densidade.
def arquivos_do_site() -> dict:
    Image = _imagem()
    marca = logo()
    largura = 240
    altura = round(marca.height * largura / marca.width)
    return {
        "virtu-clips.png": marca.resize((largura, altura), Image.LANCZOS),
        "favicon.png": monograma(64),
        "apple-touch-icon.png": icone_grande(180, cheio=True),
    }


def gravar_site(pasta: Path = PUBLICO) -> list:
    feitos = []
    for nome, imagem in arquivos_do_site().items():
        imagem.save(pasta / nome, optimize=True)
        feitos.append(pasta / nome)
    return feitos


def main() -> int:
    for caminho in gravar_site():
        print(f"gravado: {caminho.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
