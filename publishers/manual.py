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

from .base import (Account, Cost, PostMeta, PublishOptions, PublishResult,
                   Publisher, RenderedClip)

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


def render_caption(meta: PostMeta, platform: str) -> str:
    """O texto que a pessoa cola. Titulo, linha em branco, descricao, hashtags.

    Sem cabecalho, sem rotulo, sem decoracao: qualquer coisa que nao va para o
    post e coisa que a pessoa tem de apagar depois de colar.
    """
    titulo = (meta.title or "").strip()
    corpo = meta.description_for(platform).strip()
    partes = [p for p in (titulo, corpo) if p]
    faltam = _hashtags_faltantes("\n".join(partes), meta.hashtags)
    if faltam:
        partes.append(" ".join(faltam))
    return "\n\n".join(partes) + "\n"


class ManualPublisher(Publisher):
    id = "manual"
    label = "fila manual"
    # Qualquer plataforma: o driver nao fala com nenhuma delas. E o que o torna
    # o piso da cascata -- ele nunca e a razao de uma publicacao nao acontecer.
    platforms = ("youtube", "tiktok", "instagram")

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
