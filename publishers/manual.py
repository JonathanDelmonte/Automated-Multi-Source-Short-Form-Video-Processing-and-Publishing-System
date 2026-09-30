"""Driver `manual` -- o default da secao 6, e nao a versao capada.

O plano insiste nisto e vale repetir: *"ele automatiza 90% do trabalho, e o que
sobra e abrir o app e apertar publicar, com titulo, descricao e hashtags ja
gerados e copiaveis"*. O que ele entrega nao e um aviso de que nao publicou --
e o texto pronto ao lado do arquivo pronto.

**Um arquivo por corte e por plataforma, nao um arquivo com tudo.** "Pronto
pra colar" so e verdade se der para selecionar tudo e colar; um arquivo com
secoes de YouTube, TikTok e Instagram obriga a escolher o pedaco certo toda
vez. E o driver ja sabe a plataforma: ele publica *numa conta*, e uma conta tem
uma so.

Ele termina em `scheduled`, nunca em `published`. O driver entregou o pacote;
quem aperta publicar e a pessoa, e o sistema nao tem como saber que ela apertou
ate ela dizer. Contar como postado aqui seria a unica mentira capaz de fazer o
painel mostrar como publicado um corte que ninguem publicou.
"""
from __future__ import annotations

import os
import re

import plataformas

from .base import (Account, Cost, PostMeta, PublishOptions, PublishResult,
                   Publisher, RenderedClip, _encolher, com_credito)

#: Quantas hashtags cada plataforma aceita num post (`plataformas.py`). **O
#: Instagram passou a limitar a 5 por post e por Reel em dez-2025** (eram 30) e
#: ignora as que passam: as que sobram seriam so texto a mais na legenda, e
#: QUAIS ele descarta nao seria escolha de ninguem. Ficam as primeiras -- as da
#: descricao, que o detector escreveu para aquela plataforma, antes das
#: acrescentadas.
MAX_HASHTAGS = {p.id: p.hashtags_max for p in plataformas.TODAS if p.hashtags_max}

#: O tamanho maximo do texto, em caracteres, onde o app recusa ou corta o que
#: passa. Onde o app tem campo de titulo (Douyin, Bilibili, Xiaohongshu), o
#: limite e do texto sem o titulo.
MAX_CARACTERES = {p.id: p.texto_max for p in plataformas.TODAS if p.texto_max}

# Uma hashtag: `#` e pelo menos uma letra, fora de palavra, entidade ou URL
# (`site.com/pagina#secao` nao e hashtag, e `#1` o Instagram nao transforma em
# uma).
_HASHTAG = re.compile(r"(?<![\w&/])#(?=\w*[^\W\d_])\w+")

# O sufixo do arquivo de legenda, ao lado do clipe. `.txt` e proposital: e o
# que abre com um duplo clique em qualquer maquina.
def caption_path(clip_path: str, platform: str) -> str:
    base, _ = os.path.splitext(clip_path)
    return f"{base}.{platform}.txt"


def _hashtags_faltantes(texto: str, hashtags) -> list[str]:
    """As hashtags que o texto ainda nao tem.

    A descricao que o passo de deteccao gera ja costuma vir com hashtags dentro
    (o prompt pede CTA e contexto), e repetir a mesma tag duas vezes no mesmo
    post e o tipo de detalhe que so aparece depois de publicado.
    """
    baixo = texto.lower()
    faltam = []
    for tag in hashtags:
        limpa = (tag or "").strip()
        if not limpa:
            continue
        if not limpa.startswith("#"):
            limpa = "#" + limpa.lstrip("#")
        if limpa.lower() in baixo:
            continue
        faltam.append(limpa)
    return faltam


def limitar_hashtags(texto: str, maximo: int) -> str:
    """O texto com so as `maximo` primeiras hashtags. As outras saem, e o
    espaco que elas deixavam tambem; o resto do texto fica como estava."""
    vistas = 0

    def troca(m):
        nonlocal vistas
        vistas += 1
        return m.group(0) if vistas <= maximo else ""
    saida = _HASHTAG.sub(troca, texto)
    if vistas <= maximo:
        return texto
    saida = re.sub(r"[ \t]{2,}", " ", saida)
    saida = re.sub(r"[ \t]+(?=\n|$)", "", saida)
    saida = re.sub(r"\n{3,}", "\n\n", saida)
    return saida.strip()


def render_caption(meta: PostMeta, platform: str) -> str:
    """O texto que a pessoa cola. Titulo, linha em branco, descricao, hashtags.

    Sem cabecalho, sem rotulo, sem decoracao: qualquer coisa que nao va para o
    post e coisa que a pessoa tem de apagar depois de colar. E dentro das regras
    da plataforma (`plataformas.py`): texto que o app recusa ou ignora nao esta
    "pronto para colar".

    Onde o app tem um campo so para o titulo (Douyin, Bilibili, Xiaohongshu,
    etapa 7.10), o formato e o mesmo -- a primeira linha e o titulo, o resto e
    o texto --, com o limite de cada campo valendo para ele; e as tags do
    Bilibili, que tem campo proprio (标签), saem sem `#` na ultima linha.
    """
    regra = plataformas.de(platform)
    if regra is not None and (regra.titulo_max or regra.tags_no_campo):
        return _legenda_com_campos(meta, platform, regra)
    titulo = (meta.title or "").strip()
    corpo = meta.description_for(platform).strip()
    partes = [p for p in (titulo, corpo) if p]
    faltam = _hashtags_faltantes("\n".join(partes), meta.hashtags)
    if faltam:
        partes.append(" ".join(faltam))
    texto = "\n\n".join(partes)
    if platform in MAX_HASHTAGS:
        texto = limitar_hashtags(texto, MAX_HASHTAGS[platform])
    # O credito da fonte (7.5) entra depois do limite de hashtags e nunca e o
    # que se corta: quem encolhe para caber e o resto do texto.
    texto = com_credito(texto, meta.credit, MAX_CARACTERES.get(platform))
    return texto + "\n"


def tags_do_campo(hashtags, regra) -> list:
    """As tags de um campo proprio (o 标签 do Bilibili): sem `#`, sem repetir,
    no tamanho e na quantidade que o app aceita."""
    vistas, saida = set(), []
    for tag in hashtags or ():
        limpa = re.sub(r"\s+", " ", (tag or "").strip().lstrip("#").strip())
        if regra.tag_max:
            limpa = limpa[:regra.tag_max].strip()
        if not limpa or limpa.lower() in vistas:
            continue
        vistas.add(limpa.lower())
        saida.append(limpa)
    return saida[:regra.tags_max] if regra.tags_max else saida


def _legenda_com_campos(meta: PostMeta, platform: str, regra) -> str:
    titulo = (meta.title or "").strip()
    if regra.titulo_max:
        titulo = _encolher(titulo, regra.titulo_max)
    texto = meta.description_for(platform).strip()
    tags = []
    if regra.tags_no_campo:
        tags = tags_do_campo(meta.hashtags, regra)
    else:
        faltam = _hashtags_faltantes("\n".join((titulo, texto)), meta.hashtags)
        if faltam:
            texto = "\n\n".join(p for p in (texto, " ".join(faltam)) if p)
    if regra.hashtags_max:
        texto = limitar_hashtags(texto, regra.hashtags_max)
    texto = com_credito(texto, meta.credit, regra.texto_max)
    partes = [p for p in (titulo, texto, " ".join(tags)) if p]
    return "\n\n".join(partes) + "\n"


class ManualPublisher(Publisher):
    id = "manual"
    label = "fila manual"
    # Qualquer plataforma: o driver nao fala com nenhuma delas. E o que o torna
    # o piso da cascata -- ele nunca e a razao de uma publicacao nao acontecer.
    # E e o unico caminho das chinesas (7.10), que nao tem API para uma pessoa.
    platforms = plataformas.IDS

    def disponivel(self, account: Account) -> bool:
        return True

    def capability(self, account: Account) -> str:
        # `draft`: o corte fica pronto para publicacao, sem estar publicado.
        return "draft"

    def cost(self, n: int) -> Cost:
        return Cost(risk_score=0.0)

    def publish(self, clip: RenderedClip, meta: PostMeta,
                opts: PublishOptions, account: Account) -> PublishResult:
        if not os.path.exists(clip.path):
            return PublishResult(
                ok=False, driver=self.id, status="failed",
                detail=f"O arquivo do corte nao existe: {clip.path}")

        plataforma = account.platform
        destino = caption_path(clip.path, plataforma)
        texto = render_caption(meta, plataforma)
        if opts.dry_run:
            return PublishResult(ok=True, driver=self.id, status="scheduled",
                                 detail="dry-run: nada escrito em disco")
        with open(destino, "w", encoding="utf-8") as f:
            f.write(texto)
        return PublishResult(
            ok=True, driver=self.id, status="scheduled",
            detail="na fila manual: o corte e a legenda estao prontos",
            artifacts=(clip.path, destino))
