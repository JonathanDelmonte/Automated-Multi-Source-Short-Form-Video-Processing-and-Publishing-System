"""O pacote do dia -- a metade do driver `manual` que o plano pede por escrito.

    "Faca ele entregar um **pacote por dia**: os cortes do dia mais um arquivo
    de legenda pronta pra colar."  (secao 6)

E o que transforma "nao publicou" em "publicar leva dois minutos": um ZIP com
os cortes do dia, a legenda de cada um ja escrita para a plataforma da conta, e
um `LEIA-ME.txt` com a ordem sugerida.

**Este modulo nao sabe onde o pipeline guarda nada.** Ele recebe uma lista de
`(RenderedClip, PostMeta)` que o chamador montou. Isso nao e cerimonia: achar o
arquivo atual de um corte e conhecimento do `app.py`, que ja resolve as versoes
derivadas (`subtitled_`, `recut_`, `hooked_`) em `_canonical_clip_file`. Copiar
essa logica para ca criaria uma segunda verdade que silenciosamente empacotaria
a versao sem legenda.
"""
from __future__ import annotations

import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

import plataformas

from .base import PostMeta, RenderedClip
from .manual import render_caption

# Orcamento em bytes para o pedaco do nome que vem do titulo. Mesma ideia do
# `main.MAX_TITLE_BYTES` e deliberadamente mais apertado: o nome aqui ganha
# prefixo (`01_`) e sufixo (`.youtube.txt`), e vai ser extraido num sistema de
# arquivos que conta BYTES, nao caracteres -- um titulo em bengali passa de 255
# bytes muito antes de parecer longo. Duplicado em vez de importado do `main`
# porque este pacote precisa abrir sem a pilha de ML (ver o `__init__`).
MAX_NOME_BYTES = 80


@dataclass(frozen=True)
class Item:
    clip: RenderedClip
    meta: PostMeta


@dataclass(frozen=True)
class Pacote:
    caminho: str
    dia: str
    plataforma: str
    cortes: int
    faltando: tuple[str, ...] = field(default=())


def _limitar_bytes(texto: str, maximo: int) -> str:
    dados = texto.encode("utf-8")
    if len(dados) <= maximo:
        return texto
    return dados[:maximo].decode("utf-8", "ignore")


def slug(texto: str) -> str:
    """Um pedaco de nome de arquivo a partir do titulo do corte.

    Acento vira letra sem acento (`unicodedata`), porque o ZIP vai ser extraido
    numa maquina qualquer e nem todo descompactador do Windows acerta UTF-8 no
    nome. O que nao for letra, numero, `-` ou `_` sai.
    """
    normalizado = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in normalizado if not unicodedata.combining(c))
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", sem_acento).strip("_")
    return _limitar_bytes(limpo, MAX_NOME_BYTES)


def dia_de(timestamp: float, fuso=None) -> str:
    """A data ISO de um mtime, no fuso de quem usa.

    Fuso de quem usa, e nao UTC: "o pacote de hoje" e uma frase sobre o dia de
    quem vai publicar. Desde a etapa 7.5 o painel manda o fuso ao motor
    (`fuso.py`), porque num container sem `TZ` o processo esta em UTC e os
    cortes gerados de noite caiam no pacote do dia seguinte. Sem `fuso`, o do
    processo -- e a data continua escrita no nome do arquivo e no LEIA-ME.
    """
    return datetime.fromtimestamp(timestamp, tz=fuso).strftime("%Y-%m-%d")


def hoje(fuso=None) -> str:
    return datetime.now(tz=fuso).strftime("%Y-%m-%d")


def nome_do_pacote(dia: str, plataforma: str) -> str:
    return f"cortes_{dia}_{plataforma}.zip"


def nome_no_zip(ordem: int, item: Item) -> str:
    """`01_titulo_do_corte`, sem extensao -- o video e a legenda a compartilham.

    A numeracao vem na frente porque a ordem importa: o passo de deteccao ja
    entrega os cortes do melhor para o pior, e essa e a ordem de publicar.
    """
    # O titulo traduzido (7.10) e para o app; o nome do arquivo e para quem
    # abre o ZIP, e sai do titulo original do corte -- do chines o `slug` so
    # guardaria os numeros ("小猫1" viraria "1").
    fontes = ((item.clip.title, item.meta.title) if item.meta.language
              else (item.meta.title, item.clip.title))
    titulo = next((s for s in map(slug, fontes) if s), "")
    if not titulo:
        titulo = f"corte_{item.clip.index + 1}"
    return f"{ordem:02d}_{titulo}"


#: Como colar o .txt, por plataforma (7.10): onde o app tem um campo para o
#: titulo e outro para o texto, a primeira linha vai num e o resto no outro. Os
#: nomes dos campos em chines sao os que a tela do app mostra.
COMO_COLAR = {
    "douyin": [
        "A primeira linha é o título (o Douyin aceita até 30 caracteres); o",
        "resto é a descrição, com as hashtags. Não há rótulo nem cabeçalho a apagar.",
    ],
    "kuaishou": [
        "O .txt é para selecionar tudo e colar no texto do post: o Kuaishou",
        "tem um campo só. Não há rótulo nem cabeçalho a apagar.",
    ],
    "bilibili": [
        "A primeira linha é o título (标题). Depois vem a descrição (简介), e a",
        "última linha são as tags (标签): cole uma de cada vez e aperte Enter",
        "depois de cada uma.",
    ],
    "xiaohongshu": [
        "A primeira linha é o título (标题, até 20 caracteres); o resto é o",
        "texto (正文), com as hashtags.",
    ],
}

_COMO_COLAR_DE_SEMPRE = [
    "O .txt é para selecionar tudo e colar. A primeira linha é o título;",
    "o resto é a descrição. Não há rótulo nem cabeçalho a apagar.",
]


def sem_traducao(item: "Item", plataforma: str) -> bool:
    """O corte cujo texto devia ir traduzido (7.10) e foi no idioma original."""
    regra = plataformas.de(plataforma)
    return bool(regra and regra.idioma and item.meta.language != regra.idioma)


def leia_me(itens: list, dia: str, plataforma: str,
            faltando: tuple = ()) -> str:
    """O texto que abre o ZIP. Instrucao, nao relatorio."""
    quantos = (f"{len(itens)} cortes" if len(itens) != 1 else "1 corte")
    exemplo_video = "  NN_titulo.mp4"
    exemplo_texto = f"  NN_titulo.{plataforma}.txt"
    coluna = max(len(exemplo_video), len(exemplo_texto)) + 4
    regra = plataformas.de(plataforma)
    # O Bilibili (7.10) tem tags num campo proprio, sem `#`.
    marcas = "tags" if regra and regra.tags_no_campo else "hashtags"
    linhas = [
        f"CORTES DE {dia} — {plataforma}",
        "",
        f"{quantos}, na ordem sugerida de publicação: o passo de detecção",
        "já os entrega do melhor para o pior.",
        "",
        "Para cada corte há dois arquivos com o mesmo nome:",
        "",
        f"{exemplo_video:<{coluna}}o vídeo, pronto para subir",
        f"{exemplo_texto:<{coluna}}título, descrição e {marcas}",
        "",
        *COMO_COLAR.get(plataforma, _COMO_COLAR_DE_SEMPRE),
        "",
    ]
    if regra and regra.idioma:
        linhas += [
            "O texto está em chinês: as IAs gratuitas do programa o traduziram do",
            "texto original, e o app busca e recomenda por ele. O vídeo continua como",
            "foi feito, com a fala e a legenda no idioma original.",
            "",
        ]
        if any(sem_traducao(item, plataforma) for item in itens):
            linhas += [
                "Os cortes marcados abaixo ficaram com o texto no idioma original:",
                "nenhuma IA de texto respondeu a tempo. Baixe o pacote de novo mais",
                "tarde, ou traduza antes de postar.",
                "",
            ]
    linhas += ["-" * 60, ""]
    for i, item in enumerate(itens, start=1):
        base = nome_no_zip(i, item)
        titulo = (item.meta.title or item.clip.title or "").strip() or "(sem título)"
        duracao = item.clip.duration_s
        sufixo = f"  ·  {duracao:.0f}s" if duracao else ""
        linhas.append(f"{i:02d}. {titulo}{sufixo}")
        linhas.append(f"    {base}.mp4")
        if plataforma == "youtube" and item.meta.made_for_kids:
            # A COPPA (etapa 7.5): pela API o programa marca sozinho; postando a
            # mao, quem marca e a pessoa, e o YouTube pergunta na hora de subir.
            linhas.append("    Canal infantil: marque \"Sim, é conteúdo para crianças\".")
        if sem_traducao(item, plataforma):
            linhas.append("    Texto no idioma original: a tradução não saiu.")
        linhas.append("")
    if faltando:
        linhas += [
            "-" * 60,
            "",
            "NÃO ENTRARAM (o arquivo do corte não estava no disco):",
            "",
        ]
        linhas += [f"  - {nome}" for nome in faltando]
        linhas.append("")
    return "\n".join(linhas)


def montar(itens: list, destino: str, plataforma: str = "youtube",
           dia: str = "") -> Pacote:
    """Escreve o ZIP do dia e devolve o que foi parar dentro dele.

    **Um corte sem arquivo em disco nao derruba o pacote.** Ele sai da lista,
    entra em `faltando` e e nomeado no LEIA-ME. Perder os outros cinco cortes
    do dia por causa de um arquivo que a limpeza levou seria trocar um problema
    pequeno por um grande.
    """
    dia = dia or hoje()
    presentes = []
    faltando = []
    for item in itens:
        if os.path.exists(item.clip.path):
            presentes.append(item)
        else:
            faltando.append(os.path.basename(item.clip.path))

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    with zipfile.ZipFile(destino, "w") as zf:
        # O texto comprime bem; o mp4 ja esta comprimido e deflate nele so
        # queima CPU -- mesma razao do ZIP_STORED em `download_all_clips`.
        zf.writestr("LEIA-ME.txt",
                    leia_me(presentes, dia, plataforma, tuple(faltando)),
                    compress_type=zipfile.ZIP_DEFLATED)
        for i, item in enumerate(presentes, start=1):
            base = nome_no_zip(i, item)
            extensao = os.path.splitext(item.clip.path)[1] or ".mp4"
            zf.write(item.clip.path, arcname=f"{base}{extensao}",
                     compress_type=zipfile.ZIP_STORED)
            zf.writestr(f"{base}.{plataforma}.txt",
                        render_caption(item.meta, plataforma),
                        compress_type=zipfile.ZIP_DEFLATED)

    return Pacote(caminho=destino, dia=dia, plataforma=plataforma,
                  cortes=len(presentes), faltando=tuple(faltando))
