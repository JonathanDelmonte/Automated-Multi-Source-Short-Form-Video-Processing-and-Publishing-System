"""Classificar as cenas de um corte lendo o clipe UMA vez (22-set-2026).

O `main.analyze_scenes_strategy` decide, cena a cena, entre TRACK (uma pessoa)
e GENERAL (grupo ou nenhum rosto), olhando 5 quadros de cada cena. Ele buscava
cada quadro com `cap.set(CAP_PROP_POS_FRAMES, n)` + `cap.read()` -- e um seek
num H.264 nao cai no quadro: cai no keyframe anterior e DECODIFICA ate o quadro
pedido. Com GOP de 250 quadros (o padrao do libx264 e do NVENC), cada um dos 5
quadros de cada cena custava, em media, uma centena de quadros 1080p
decodificados na CPU, e o rosto em si -- o BlazeFace, num quadro reduzido --
e a parte barata.

No log do autor (22-set-2026) isso aparecia como "Analyzing Scenes" a 1-4 s
POR CENA: 27 a 77 s por corte, cerca de um terco de todo o reenquadramento. A
mesma leitura, feita em uma passada so, e medida aqui com um clipe 1080p de
50 s e 23 cenas (a forma do corte 2 daquele job):

    seek por quadro   25,8 s
    uma passada        5,8 s     4,5x
    quadros identicos 115/115

**Quadros identicos e o que torna a troca segura**: a deteccao recebe
exatamente a mesma entrada, entao a decisao TRACK/GENERAL nao muda. Um teste
compara as duas estrategias quadro a quadro, em cenarios sorteados.

Mora fora do `main.py` porque o `main.py` so importa com torch e mediapipe, e
o CI de proposito nao instala nenhum dos dois. Aqui so ha numpy e um objeto
que se comporta como `cv2.VideoCapture` (`grab` / `retrieve`).
"""
import numpy as np

#: Quantos quadros olhar por cena. O mesmo 5 de sempre -- mudar isto muda a
#: decisao, e o objetivo aqui e mudar so a velocidade.
AMOSTRAS_POR_CENA = 5

#: Quadro mais escuro que isto (media de 0 a 255) e fade ou corte para preto:
#: nao tem rosto e puxava cena de uma pessoa para GENERAL.
LIMIAR_DE_ESCURO = 16


def quadros_da_cena(inicio, fim, amostras=AMOSTRAS_POR_CENA):
    """Os quadros que representam a cena `[inicio, fim)`.

    A mesma conta do `main` antigo: espalhados pela cena, com uma margem de ate
    2 quadros para nao cair na borda de um corte. O unico acrescimo e o piso em
    zero, para que uma cena degenerada no comeco nao peca o quadro -1.
    """
    margem = min(2, max(0, (fim - inicio - 1) // 2))
    return sorted(set(max(0, int(round(f)))
                      for f in np.linspace(inicio + margem, fim - 1 - margem, amostras)))


def contar_rostos_por_cena(cap, faixas, detectar, escuro=LIMIAR_DE_ESCURO):
    """Uma passada pelo clipe, e a contagem de rostos de cada quadro amostrado.

    `faixas` e a lista `[(inicio, fim), ...]` em quadros; `detectar(quadro)`
    devolve a lista de rostos. Devolve, para cada cena, a lista de contagens --
    vazia quando nenhum quadro da cena foi lido ou todos eram escuros, que e
    exatamente o caso em que o `main` antigo decidia GENERAL.

    `grab()` em todo quadro e `retrieve()` so nos pedidos: o `grab` decodifica
    mas nao converte a cor, e a leitura para no ultimo quadro que alguma cena
    pediu -- o fim do clipe nunca e decodificado a toa.
    """
    pedidos = {}
    for n_cena, (inicio, fim) in enumerate(faixas):
        for q in quadros_da_cena(inicio, fim):
            pedidos.setdefault(q, []).append(n_cena)

    contagens = [[] for _ in faixas]
    if not pedidos:
        return contagens

    ultimo = max(pedidos)
    n = 0
    while n <= ultimo:
        if not cap.grab():
            break
        cenas = pedidos.get(n)
        if cenas:
            ok, quadro = cap.retrieve()
            if ok and quadro is not None and quadro.mean() >= escuro:
                rostos = len(detectar(quadro))
                for c in cenas:
                    contagens[c].append(rostos)
        n += 1
    return contagens


def estrategia(contagens):
    """TRACK com uma pessoa em media; GENERAL com nenhuma ou com grupo.

    Os limiares sao os do `main` de sempre (0,5 e 1,2) -- esta mudanca nao
    mexe em decisao nenhuma.
    """
    media = sum(contagens) / len(contagens) if contagens else 0
    return "GENERAL" if (media > 1.2 or media < 0.5) else "TRACK"
