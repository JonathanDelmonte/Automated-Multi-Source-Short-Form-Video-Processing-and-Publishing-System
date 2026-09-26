"""Driver `youtube-api` -- o canal proprio, de graca, 100 por dia. Bloco 3.4.

O unico driver da secao 6 que publica sozinho sem custo e sem risco de conta: e
a API oficial, com o token do dono do canal. O limite nao e dinheiro, e quota:
desde jun-2026 o `videos.insert` tem cota propria, de 100 chamadas por dia por
projeto no Google Cloud (ate ali, 1.600 das 10.000 unidades: 6 por dia). O
contador esta em `publishers/quota.py` e o motivo de ele existir e que o envio
que nao cabe **caia na fila manual**, nao vire um job vermelho.

**HTTP direto, sem `google-api-python-client`.** Sao tres requisicoes (renovar o
token, abrir a sessao de upload, mandar o arquivo) e o cliente oficial traz
`google-auth`, `googleapis-common-protos` e amigos para dentro de uma imagem que
ja carrega torch e mediapipe. O `httpx` ja e dependencia e faz as tres.

**O que fala com a rede esta isolado em funcoes pequenas** (`_token_de_acesso`,
`_abrir_sessao`, `_enviar_arquivo`) e o que decide esta em funcoes puras
(`corpo_do_video`, `privacidade`, `erro_da_resposta`). Nao e gosto por camadas:
a parte de rede deste driver nao tem como ser exercitada no CI, e a parte que
decide tem -- separadas, o teste alcanca tudo o que da para alcancar.
"""
from __future__ import annotations

import json
import os

from . import quota
from .base import (Account, Cost, PostMeta, PublishOptions, PublishResult,
                   Publisher, PublisherError, QuotaEsgotada, RenderedClip)

URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_UPLOAD = ("https://www.googleapis.com/upload/youtube/v3/videos"
              "?uploadType=resumable&part=snippet,status")
URL_ASSISTIR = "https://www.youtube.com/watch?v="

#: Limites publicados do proprio YouTube. Cortar aqui e melhor que receber 400
#: depois de subir o arquivo inteiro.
MAX_TITULO = 100
MAX_DESCRICAO = 5000
MAX_TAGS_CHARS = 500

#: O endereco de cofre padrao quando a conta nao tem um. `env` porque o caso
#: real do projeto e uma conta so, entregue por `docker compose`.
REF_PADRAO = "vault://env/youtube/{handle}"

PRIVACIDADES = ("public", "private", "unlisted")


def ref_de(account: Account) -> str:
    return account.credentials_ref or REF_PADRAO.format(handle=account.handle or "conta")


def privacidade(visibilidade: str) -> str:
    """`privacyStatus` a partir do `visibility` das opcoes.

    Qualquer coisa fora da lista vira `private`. **A queda e para o valor mais
    fechado de proposito**: um erro de digitacao num campo de visibilidade nao
    pode ser o que publica um corte para o mundo.
    """
    valor = (visibilidade or "").strip().lower()
    return valor if valor in PRIVACIDADES else "private"


def _tags(meta: PostMeta) -> list:
    """As hashtags viram tags, sem a cerquilha e dentro do teto de 500 chars.

    O teto e do YouTube e conta a soma; estourar faz a API recusar o video
    inteiro por causa de uma tag a mais.
    """
    tags = []
    total = 0
    for bruta in meta.hashtags:
        tag = (bruta or "").strip().lstrip("#").strip()
        if not tag:
            continue
        if total + len(tag) > MAX_TAGS_CHARS:
            break
        tags.append(tag)
        total += len(tag)
    return tags


def corpo_do_video(meta: PostMeta, opts: PublishOptions) -> dict:
    """O JSON de `videos.insert`. Funcao pura -- e onde moram as regras.

    O titulo perde `<` e `>` porque a API recusa os dois, e a recusa vem depois
    do upload do arquivo: um envio da cota do dia gasto para descobrir que um
    hook trazia uma seta.
    """
    titulo = (meta.title or "").replace("<", "").replace(">", "").strip()
    titulo = titulo[:MAX_TITULO] or "Corte"
    descricao = meta.description_for("youtube")[:MAX_DESCRICAO]
    corpo = {
        "snippet": {
            "title": titulo,
            "description": descricao,
            "categoryId": os.environ.get("YOUTUBE_CATEGORY_ID", "22"),
        },
        "status": {
            "privacyStatus": privacidade(opts.visibility),
            # Declaracao obrigatoria desde a COPPA. `False` e a resposta certa
            # para conteudo de cortes; quem faz video infantil tem de mudar, e
            # deixar o campo fora faz a API assumir o pior.
            "selfDeclaredMadeForKids": False,
        },
    }
    tags = _tags(meta)
    if tags:
        corpo["snippet"]["tags"] = tags
    if meta.language:
        corpo["snippet"]["defaultLanguage"] = meta.language
    if opts.scheduled_at and corpo["status"]["privacyStatus"] == "private":
        # O YouTube so aceita agendamento em video privado -- e ele vira
        # publico sozinho na hora marcada. Mandar `publishAt` num video ja
        # publico e erro 400.
        corpo["status"]["publishAt"] = opts.scheduled_at
    return corpo


def erro_da_resposta(status: int, texto: str) -> Exception:
    """Traduz a resposta da API na excecao certa.

    Separar `quotaExceeded` do resto e a decisao aqui: quota estourada nao e
    falha do corte, e o sinal de que os proximos vao para a fila manual.
    """
    razao = ""
    try:
        dados = json.loads(texto or "{}")
        erros = (dados.get("error") or {}).get("errors") or []
        if erros and isinstance(erros[0], dict):
            razao = erros[0].get("reason") or ""
        mensagem = (dados.get("error") or {}).get("message") or texto
    except (ValueError, AttributeError):
        mensagem = texto
    if razao in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
        return QuotaEsgotada(f"quota do YouTube esgotada ({razao}): {mensagem}")
    return PublisherError(f"YouTube respondeu {status}: {mensagem}")


# --------------------------------------------------------------------------- #
# Rede -- as tres funcoes que o CI nao alcanca
# --------------------------------------------------------------------------- #

def _token_de_acesso(segredo: dict) -> str:
    import httpx

    resposta = httpx.post(URL_TOKEN, timeout=30.0, data={
        "client_id": segredo["client_id"],
        "client_secret": segredo["client_secret"],
        "refresh_token": segredo["refresh_token"],
        "grant_type": "refresh_token",
    })
    if resposta.status_code != 200:
        # A resposta de erro do OAuth nao carrega o segredo, so o motivo
        # (`invalid_grant`), entao pode ir para a mensagem.
        raise erro_da_resposta(resposta.status_code, resposta.text)
    token = (resposta.json() or {}).get("access_token")
    if not token:
        raise PublisherError("o Google nao devolveu access_token")
    return token


def _abrir_sessao(token: str, corpo: dict, tamanho: int) -> str:
    import httpx

    resposta = httpx.post(URL_UPLOAD, timeout=60.0, json=corpo, headers={
        "Authorization": f"Bearer {token}",
        "X-Upload-Content-Length": str(tamanho),
        "X-Upload-Content-Type": "video/*",
    })
    if resposta.status_code not in (200, 201):
        raise erro_da_resposta(resposta.status_code, resposta.text)
    destino = resposta.headers.get("location")
    if not destino:
        raise PublisherError("o YouTube aceitou a sessao e nao mandou Location")
    return destino


def _enviar_arquivo(destino: str, caminho: str) -> dict:
    """Manda o arquivo inteiro num PUT so.

    Um corte tem no maximo 60 s e alguns megabytes -- a fonte de horas nunca
    chega aqui. Fatiar em blocos so faria sentido para retomar upload longo, e
    retomar um arquivo de 20 MB e mais codigo que refazer.
    """
    import httpx

    tamanho = os.path.getsize(caminho)
    with open(caminho, "rb") as fh:
        resposta = httpx.put(destino, content=fh, timeout=1800.0, headers={
            "Content-Type": "video/*",
            "Content-Length": str(tamanho),
        })
    if resposta.status_code not in (200, 201):
        raise erro_da_resposta(resposta.status_code, resposta.text)
    return resposta.json() or {}


# --------------------------------------------------------------------------- #
# O driver
# --------------------------------------------------------------------------- #

class YouTubeApiPublisher(Publisher):
    id = "youtube-api"
    label = "YouTube (API oficial)"
    platforms = ("youtube",)

    def _segredo(self, account: Account) -> dict:
        import vault
        return vault.resolve(ref_de(account),
                             exigir=("client_id", "client_secret", "refresh_token"))

    def disponivel(self, account: Account) -> bool:
        """`ifQuotaLeft()` da secao 6, mais a credencial.

        As duas perguntas juntas porque as duas tem a mesma resposta pratica:
        o corte vai para a fila manual. Sem credencial isso e permanente ate
        alguem configurar; sem quota e ate meia-noite no Pacifico.
        """
        if account.platform != "youtube":
            return False
        import vault
        if not vault.existe(ref_de(account),
                            ("client_id", "client_secret", "refresh_token")):
            return False
        return quota.cabe()

    def capability(self, account: Account) -> str:
        if account.platform != "youtube":
            return "none"
        import vault
        if not vault.existe(ref_de(account),
                            ("client_id", "client_secret", "refresh_token")):
            return "none"
        if not quota.cabe():
            return "none"
        # Um app OAuth que ainda nao passou pela verificacao do Google sobe
        # video trancado em privado. Nao da para saber isso antes de tentar,
        # entao quem sabe e a instalacao -- e o driver conta no `detail` o que
        # o YouTube respondeu de verdade.
        if os.environ.get("YOUTUBE_APP_UNVERIFIED") == "1":
            return "private_only"
        return "public"

    def cost(self, n: int) -> Cost:
        # Na cota do envio a unidade e a chamada: `n` cortes gastam `n` das 100.
        return Cost(risk_score=0.0, usd=0.0, quota_units=max(0, int(n)))

    def publish(self, clip: RenderedClip, meta: PostMeta,
                opts: PublishOptions, account: Account) -> PublishResult:
        if not os.path.exists(clip.path):
            return PublishResult(ok=False, driver=self.id, status="failed",
                                 detail=f"O arquivo do corte nao existe: {clip.path}")
        if not quota.cabe():
            raise QuotaEsgotada(
                f"a cota de envios do YouTube de hoje acabou ({quota.uploads_hoje()}"
                f" de {quota.uploads_por_dia()}). O corte fica na fila manual ate "
                "a meia-noite no Pacifico.")

        corpo = corpo_do_video(meta, opts)
        pedida = corpo["status"]["privacyStatus"]
        if opts.dry_run:
            return PublishResult(ok=True, driver=self.id, status="scheduled",
                                 detail=f"dry-run: {json.dumps(corpo, ensure_ascii=False)}")

        segredo = self._segredo(account)
        # Debita ANTES de chamar: o YouTube cobra a quota quando aceita a
        # requisicao, e um upload que morre no meio ja gastou o envio. Contar
        # so no sucesso deixaria o contador abaixo da verdade justamente no dia
        # ruim, que e quando ele precisa estar certo.
        quota.registrar_upload()

        token = _token_de_acesso(segredo)
        destino = _abrir_sessao(token, corpo, os.path.getsize(clip.path))
        resposta = _enviar_arquivo(destino, clip.path)

        video_id = resposta.get("id") or ""
        entregue = ((resposta.get("status") or {}).get("privacyStatus")
                    or pedida)
        detalhe = f"publicado como {entregue}"
        if entregue != pedida:
            # Acontece com app OAuth nao verificado: pede-se `public` e o video
            # sobe `private`. Dizer isso e a diferenca entre "publiquei" e
            # "subiu, mas ninguem ve".
            detalhe = (f"pedimos {pedida} e o YouTube publicou como {entregue}"
                       " -- o app OAuth provavelmente ainda nao foi verificado")
        return PublishResult(
            ok=True, driver=self.id, status="published",
            remote_id=video_id or None,
            url=(URL_ASSISTIR + video_id) if video_id else None,
            detail=f"{detalhe} · restam {quota.uploads_restantes()} envio(s) hoje")
