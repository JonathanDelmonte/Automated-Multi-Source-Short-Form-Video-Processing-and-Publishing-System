"""Os capitulos do video longo (etapa 7.8): a lista de tempos na descricao, que
o YouTube transforma nas marcas da barra do video.

As regras sao do YouTube (ajuda "Capitulos do video"), e **uma lista fora
delas e ignorada inteira, sem aviso** -- o video sobe e simplesmente nao tem
capitulo nenhum:

- o primeiro comeca em 0:00;
- pelo menos tres;
- em ordem crescente;
- cada um com pelo menos 10 segundos.

Por isso quem escreve a lista passa por `validos` antes: o capitulo curto
demais sai (o trecho dele fica com o anterior), o primeiro vai para 0:00, e com
menos de tres a descricao sai sem lista (e nao com uma lista que o YouTube
recusaria).

O tempo que aparece e o ARREDONDADO PARA BAIXO, e e sobre ele que as regras
sao conferidas: e o numero que o YouTube le. Stdlib pura, para o CI.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

MINIMO = 3
DURACAO_MINIMA_S = 10
#: O YouTube nao publica um teto; titulo de capitulo longo quebra a barra.
TITULO_MAX = 80

_ROTULOS = {"pt": "Capítulos", "en": "Chapters", "es": "Capítulos"}


def tempo(segundos) -> str:
    """`m:ss`, ou `h:mm:ss` a partir de uma hora -- o formato que o YouTube le."""
    try:
        total = max(0, int(float(segundos)))
    except (TypeError, ValueError):
        total = 0
    horas, resto = divmod(total, 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas}:{minutos:02d}:{segs:02d}" if horas else f"{minutos}:{segs:02d}"


def titulo(texto) -> str:
    """Uma linha, sem espaco sobrando, no teto. Um tempo no comeco do titulo
    ("1:23 a volta") seria lido como outro capitulo, entao sai."""
    limpo = re.sub(r"\s+", " ", str(texto or "")).strip()
    limpo = re.sub(r"^\(?\d{1,2}(:\d{2}){1,2}\)?\s*[-–—:]?\s*", "", limpo)
    return limpo[:TITULO_MAX].rstrip()


def validos(capitulos: Iterable, total_s: Optional[float] = None) -> List[Tuple[int, str]]:
    """`[(segundos, titulo)]` dentro das regras, ou `[]` quando nao da.

    `capitulos` e uma lista de `(inicio_em_segundos, titulo)`, em qualquer
    ordem. O primeiro vai para 0:00. **O capitulo curto demais (menos de 10 s
    ate o seguinte, ou ate o fim do video) e o que sai**, e o trecho dele fica
    com o capitulo anterior -- tirar o seguinte poria o titulo do curto em
    cima do conteudo longo do outro. Se o curto e o primeiro, o seguinte passa
    a comecar em 0:00. Sem `total_s`, o fim do video nao e conferido.
    """
    itens = []
    for item in capitulos or ():
        try:
            inicio, nome = item
            segundos = max(0, int(float(inicio)))
        except (TypeError, ValueError):
            continue
        nome = titulo(nome)
        if nome:
            itens.append((segundos, nome))
    try:
        total = int(float(total_s or 0))
    except (TypeError, ValueError):
        total = 0
    itens.sort(key=lambda x: x[0])
    saida = []
    for i, (segundos, nome) in enumerate(itens):
        if not saida:
            segundos = 0
        if i + 1 < len(itens):
            fim = itens[i + 1][0]
        else:
            fim = total if total > 0 else segundos + DURACAO_MINIMA_S
        if fim - segundos < DURACAO_MINIMA_S:
            continue
        saida.append((segundos, nome))
    return saida if len(saida) >= MINIMO else []


def rotulo(idioma: Optional[str]) -> str:
    codigo = (idioma or "pt").strip().lower()[:2]
    return _ROTULOS.get(codigo, _ROTULOS["pt"])


def texto(capitulos: Iterable) -> str:
    """As linhas da lista, uma por capitulo: `0:00 Titulo`."""
    return "\n".join(f"{tempo(t)} {n}" for t, n in capitulos or ())


def na_descricao(descricao: str, capitulos: Iterable, idioma: Optional[str] = None,
                 hashtags: Iterable = ()) -> str:
    """A descricao do video longo: o texto, a lista de capitulos (com o rotulo
    no idioma do canal) e as hashtags, nessa ordem. Sem capitulos validos, a
    lista nao aparece -- o chamador passa o que `validos` devolveu."""
    partes = []
    if (descricao or "").strip():
        partes.append(descricao.strip())
    lista = texto(capitulos)
    if lista:
        partes.append(f"{rotulo(idioma)}\n{lista}")
    tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags or () if str(h).strip("# "))
    if tags:
        partes.append(tags)
    return "\n\n".join(partes)
