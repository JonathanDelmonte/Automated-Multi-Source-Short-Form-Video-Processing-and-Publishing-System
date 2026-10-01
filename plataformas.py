"""As plataformas onde um canal publica, num lugar so (Fase 7, etapa 7.10).

Ate a 7.10 eram tres (YouTube, TikTok e Instagram), e a lista estava escrita
em seis lugares -- a fila, os links, o driver manual, o pacote do dia, a ordem
das contas e o que o `/api/contas` responde. Com as quatro chinesas (Douyin,
Kuaishou, Bilibili e Xiaohongshu) seriam sete em seis lugares, e o que ficasse
para tras so apareceria na conta que nao pode ser criada ou no link que nao e
lido. Aqui fica o que e da PLATAFORMA; quem precisa, le daqui.

O que e de outro dono continua com ele: o CHECK do banco em `db_models`
(`PLATFORMS`, com teste comparando), os formatos de link em `links_de_post`, e
as frases da tela no painel (`dashboard/src/lib/plataformas.js`, com teste
comparando os ids).

**Nenhuma das chinesas tem API de publicacao para uma pessoa** (ver o ADR-015):
publicar em nome de alguem e para empresa, MCN ou site de governo e de imprensa,
com cadastro e revisao na China. Elas publicam pelo caminho do Instagram da 7.3d
-- o pacote do dia com a legenda pronta e o "ja publiquei" com o link --, e o
texto do post sai em chines (`traducao.py`), porque e em chines que o app busca
e recomenda. Nenhuma e medida: o numero de cada post so existe dentro do app.

Stdlib pura: o CI le as regras sem banco e sem rede.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Plataforma:
    id: str
    nome: str
    #: O idioma do texto do post. Vazio: o do video, que e o que o detector
    #: escreveu. `zh-CN`: o texto sai traduzido para o chines simplificado.
    idioma: str = ""
    #: O app tem um campo so para o titulo: a primeira linha da legenda e o
    #: titulo, cortado neste limite, e o limite do texto vale para o resto.
    #: Sem ele (YouTube, TikTok, Instagram, Kuaishou), a legenda e um bloco so.
    titulo_max: Optional[int] = None
    #: O tamanho maximo do texto, em caracteres, onde o app recusa ou corta.
    texto_max: Optional[int] = None
    #: Quantas hashtags o app aceita num post (as que passam ele ignora).
    hashtags_max: Optional[int] = None
    #: As tags vao num campo proprio, sem `#`, na ultima linha da legenda.
    tags_no_campo: bool = False
    tags_max: Optional[int] = None
    #: O tamanho de cada tag, em caracteres.
    tag_max: Optional[int] = None
    #: Recebe o video longo e deitado (7.8).
    video_longo: bool = False
    #: Tem coleta de metricas (7.4).
    medida: bool = False
    #: Os pacotes do app no Android, o principal primeiro (a frota, 7.9). O
    #: TikTok tem dois: o `trill` e o mesmo app, distribuido em parte da Asia.
    apps: tuple = ()
    #: Qual tela do app recebe o video, quando ele tem mais de uma no
    #: "compartilhar" (o Instagram tem Reels, Stories e o Direct). Expressao
    #: sobre o nome da tela, que e perguntado ao aparelho (`frota_aparelho`).
    tela_preferida: str = ""
    #: As telas que nunca servem para postar o corte (Stories, mensagens).
    telas_evitadas: str = ""


#: Na ordem da tela: as tres de sempre, e as chinesas na ordem do plano.
TODAS = (
    Plataforma("youtube", "YouTube", video_longo=True, medida=True,
               apps=("com.google.android.youtube",), tela_preferida="short|upload"),
    Plataforma("tiktok", "TikTok", medida=True,
               apps=("com.zhiliaoapp.musically", "com.ss.android.ugc.trill")),
    # O Instagram limita a 5 hashtags por post desde dez-2025 (eram 30), e a
    # legenda a 2.200 caracteres (7.3d).
    Plataforma("instagram", "Instagram", texto_max=2200, hashtags_max=5, medida=True,
               apps=("com.instagram.android",), tela_preferida="clips|reel",
               telas_evitadas="story|stories|direct|chat|message"),
    # Os limites das chinesas sao os das paginas de ajuda e dos guias de quem
    # posta la, em set-2026 (ADR-015). O que nao tem numero publicado fica sem
    # limite: cortar por palpite e pior que deixar o app avisar.
    Plataforma("douyin", "Douyin", idioma="zh-CN", titulo_max=30, texto_max=1000,
               apps=("com.ss.android.ugc.aweme",)),
    Plataforma("kuaishou", "Kuaishou", idioma="zh-CN", apps=("com.smile.gifmaker",)),
    # O Bilibili e o do video longo na China, e deitado: e para la que ele vai
    # alem do YouTube. O 简介 (a descricao) tem 250 caracteres na maioria das
    # categorias; as tags, ate 10, vao no campo 标签.
    Plataforma("bilibili", "Bilibili", idioma="zh-CN", titulo_max=80, texto_max=250,
               tags_no_campo=True, tags_max=10, tag_max=20, video_longo=True,
               apps=("tv.danmaku.bili",)),
    Plataforma("xiaohongshu", "Xiaohongshu", idioma="zh-CN", titulo_max=20,
               texto_max=1000, apps=("com.xingin.xhs",)),
)

IDS = tuple(p.id for p in TODAS)
NOMES = {p.id: p.nome for p in TODAS}
_POR_ID = {p.id: p for p in TODAS}

#: As que publicam pela API ou pela fila e SAO medidas (7.4).
MEDIDAS = tuple(p.id for p in TODAS if p.medida)
#: Para onde vai o video longo e deitado (7.8).
VIDEO_LONGO = tuple(p.id for p in TODAS if p.video_longo)
#: As que recebem o texto do post em outro idioma.
TRADUZIDAS = tuple(p.id for p in TODAS if p.idioma)
#: As que tem app conhecido no Android: as que a frota sabe abrir (7.9).
NO_APARELHO = tuple(p.id for p in TODAS if p.apps)


def de(plataforma: str) -> Optional[Plataforma]:
    return _POR_ID.get(plataforma)


def nome(plataforma: str) -> str:
    return NOMES.get(plataforma, plataforma)


def ordem(plataforma: str) -> int:
    """A posicao na tela; plataforma desconhecida vai para o fim."""
    try:
        return IDS.index(plataforma)
    except ValueError:
        return len(IDS)


def lista_de_nomes(ids) -> str:
    """"o YouTube e o Bilibili": os nomes, com o artigo, como a frase pede."""
    nomes = [f"o {nome(i)}" for i in ids]
    if len(nomes) <= 1:
        return "".join(nomes)
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]
