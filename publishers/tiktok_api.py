"""Driver `tiktok-api` -- o Content Posting API do TikTok (Fase 7, etapa 7.3).

O app de desenvolvedor e o de quem usa (decisao do autor, 26-set-2026), e a
conta e conectada pelo site, como a do YouTube (`conexoes.py`). O post vai pelo
**Direct Post**: o video sobe e aparece no perfil, sem passar pela caixa de
rascunhos do app.

**Antes da auditoria do TikTok, o Direct Post e so para testar**, e o motivo e
do TikTok, nao nosso:

- todo post sai `SELF_ONLY` (so a propria conta ve);
- **a conta precisa estar PRIVADA no app** na hora do post;
- no maximo 5 contas por dia postam pelo mesmo app.

Ate a auditoria, o caminho para postar publico continua sendo o pacote do dia.
O driver nao finge o contrario: pede a privacidade que o TikTok diz que a conta
aceita AGORA (`creator_info`), e traduz a recusa de conta publica numa frase que
diz o que fazer.

**O que fala com a rede esta isolado** (`_pedir`, `_enviar_pedaco`) e o que
decide e puro (`plano_de_pedacos`, `escolher_privacidade`, `legenda`,
`corpo_do_post`, `erro_do_tiktok`) -- a mesma divisao do `youtube_api.py`, e
pelo mesmo motivo: a parte de rede nao e alcancavel no CI.

**O refresh token muda a cada renovacao** (o TikTok pode devolver outro): o
driver grava o novo no cofre antes de seguir. Perder isso seria perder a conexao
em silencio na proxima publicacao.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from .base import (Account, Cost, PostMeta, PublishOptions, PublishResult,
                   Publisher, PublisherError, RenderedClip)

TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INICIAR = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

#: Os campos da credencial de uma conta do TikTok no cofre.
CAMPOS = ("client_key", "client_secret", "refresh_token")

REF_PADRAO = "vault://local/tiktok/{handle}"

#: O limite da legenda (`title` do Direct Post), em caracteres.
MAX_LEGENDA = 2200

#: As regras do envio em pedacos (Media Transfer Guide): pedaco de 5 MB a
#: 64 MB, o ultimo pode passar ate 128 MB, e a contagem e ARREDONDADA PARA
#: BAIXO -- arredondar para cima produz um ultimo pedaco abaixo de 5 MB, que o
#: TikTok recusa.
PEDACO_MINIMO = 5 * 1024 * 1024
PEDACO_MAXIMO = 64 * 1024 * 1024
PEDACO_PADRAO = 10 * 1024 * 1024

#: Quanto esperar o TikTok terminar de processar, e de quanto em quanto
#: perguntar.
ESPERA_DO_PROCESSAMENTO_S = 300
INTERVALO_DO_STATUS_S = 5

PRIVADO = "SELF_ONLY"
PUBLICO = "PUBLIC_TO_EVERYONE"


def ref_de(account: Account) -> str:
    """Onde mora a credencial desta conta: **sempre no cofre local**.

    O TikTok pode devolver outro refresh token a cada renovacao, e o driver
    grava o novo antes de seguir -- o backend `env` e somente leitura, entao
    uma credencial do TikTok no ambiente morreria na primeira troca, com o post
    ja pela metade. A conta nasce apontando para o `env` (o padrao de toda
    conta); o driver usa o endereco local, que e onde o "conectar" grava.
    """
    ref = account.credentials_ref or ""
    if ref.startswith("vault://local/tiktok/"):
        return ref
    return REF_PADRAO.format(handle=account.handle or "conta")


# --------------------------------------------------------------------------- #
# O que decide -- puro
# --------------------------------------------------------------------------- #

def plano_de_pedacos(tamanho: int) -> tuple:
    """`(chunk_size, total_chunk_count)` para um arquivo deste tamanho.

    Ate 64 MB vai inteiro, num pedaco so (e abaixo de 5 MB so pode ir inteiro).
    Acima disso, pedacos de 10 MB, e o ultimo leva o resto.
    """
    if tamanho <= 0:
        raise PublisherError("o arquivo do corte esta vazio")
    if tamanho <= PEDACO_MAXIMO:
        return tamanho, 1
    return PEDACO_PADRAO, tamanho // PEDACO_PADRAO


def pedacos(tamanho: int) -> list:
    """Os intervalos `(inicio, fim_inclusivo)` de cada pedaco, na ordem."""
    passo, total = plano_de_pedacos(tamanho)
    saida = []
    for i in range(total):
        inicio = i * passo
        fim = tamanho - 1 if i == total - 1 else inicio + passo - 1
        saida.append((inicio, fim))
    return saida


def auditado() -> bool:
    """O app de quem usa ja passou na auditoria do TikTok? Nao da para saber do
    lado de ca: quem sabe e a instalacao, pelo `TIKTOK_APP_AUDITADO=1`."""
    return os.environ.get("TIKTOK_APP_AUDITADO") == "1"


def escolher_privacidade(pedida: str, opcoes, *, auditado: bool = False) -> str:
    """A privacidade do post, dentre as que o TikTok diz que a conta aceita.

    **Antes da auditoria, sempre `SELF_ONLY`**, pedido o que for: e a unica que
    o TikTok aceita de app nao auditado, e pedir outra so trocaria o post por um
    erro. Depois dela, publico so quando pedido E oferecido; senao, privado. Na
    duvida, o mais fechado -- um erro de digitacao nao pode ser o que publica um
    corte.
    """
    opcoes = list(opcoes or [])
    if not auditado:
        if PRIVADO in opcoes:
            return PRIVADO
        raise PublisherError("antes da auditoria o TikTok so aceita post privado, e nao "
                             "ofereceu o privado para esta conta agora")
    if (pedida or "").strip().lower() == "public" and PUBLICO in opcoes:
        return PUBLICO
    if PRIVADO in opcoes:
        return PRIVADO
    fechadas = [o for o in opcoes if o != PUBLICO]
    if fechadas:
        return fechadas[0]
    raise PublisherError("o TikTok nao ofereceu nenhuma privacidade para esta conta agora")


def legenda(meta: PostMeta) -> str:
    """A legenda do post: a descricao do TikTok (que ja vem com hashtags do
    detector), as hashtags que faltarem, e o titulo se nao houver descricao."""
    from .manual import _hashtags_faltantes
    corpo = (meta.description_for("tiktok") or "").strip() or (meta.title or "").strip()
    faltam = _hashtags_faltantes(corpo, meta.hashtags)
    texto = " ".join([corpo] + faltam).strip() if faltam else corpo
    return texto[:MAX_LEGENDA]


def corpo_do_post(meta: PostMeta, privacidade: str, info: dict, tamanho: int) -> dict:
    """O JSON do `video/init` do Direct Post."""
    passo, total = plano_de_pedacos(tamanho)
    return {
        "post_info": {
            "title": legenda(meta),
            "privacy_level": privacidade,
            # O que o criador desligou nas configuracoes da conta tem de ir
            # desligado aqui: o TikTok recusa o post que liga o que ele proibiu.
            "disable_comment": bool(info.get("comment_disabled")),
            "disable_duet": bool(info.get("duet_disabled")),
            "disable_stitch": bool(info.get("stitch_disabled")),
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": tamanho,
            "chunk_size": passo,
            "total_chunk_count": total,
        },
    }


_FRASES = {
    "unaudited_client_can_only_post_to_private_accounts":
        "Antes da auditoria do TikTok, a conta precisa estar PRIVADA no app para receber video "
        "pela API (e o video sai so para voce). Deixe a conta privada, ou poste pelo pacote do dia.",
    "reached_active_user_cap":
        "O seu app do TikTok ja teve 5 contas postando nas ultimas 24 h, o limite antes da auditoria.",
    "spam_risk_too_many_posts":
        "O TikTok recusou por excesso de posts hoje nesta conta.",
    "spam_risk_user_banned_from_posting":
        "O TikTok bloqueou esta conta de postar.",
    "access_token_invalid":
        "A conexao com o TikTok venceu. Conecte a conta de novo.",
    "scope_not_authorized":
        "A conexao com o TikTok nao tem permissao de postar. Conecte a conta de novo.",
    "rate_limit_exceeded":
        "Muitos pedidos ao TikTok agora; tente de novo em um minuto.",
    "privacy_level_option_mismatch":
        "O TikTok nao aceitou a privacidade pedida para esta conta.",
}


def erro_do_tiktok(status: int, dados: dict) -> PublisherError:
    """A resposta de erro do TikTok, numa frase que diz o que fazer."""
    erro = (dados or {}).get("error") if isinstance(dados, dict) else None
    codigo = ""
    mensagem = ""
    if isinstance(erro, dict):
        codigo = erro.get("code") or ""
        mensagem = erro.get("message") or ""
    elif isinstance(erro, str):          # o endpoint de token responde assim
        codigo = erro
        mensagem = (dados or {}).get("error_description") or ""
    if codigo in _FRASES:
        return PublisherError(_FRASES[codigo])
    return PublisherError(f"o TikTok respondeu {status}: {codigo or 'erro'} {mensagem}".strip())


def _ok(dados: dict) -> bool:
    erro = (dados or {}).get("error")
    return not erro or (isinstance(erro, dict) and erro.get("code") in ("ok", "", None))


# --------------------------------------------------------------------------- #
# Rede -- o que o CI nao alcanca
# --------------------------------------------------------------------------- #

def _pedir(url: str, *, token: Optional[str] = None, json: Optional[dict] = None,
           data: Optional[dict] = None, timeout: float = 60.0) -> dict:
    import httpx
    cabecalhos = {}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    if json is not None:
        cabecalhos["Content-Type"] = "application/json; charset=UTF-8"
    r = httpx.post(url, json=json, data=data, headers=cabecalhos, timeout=timeout)
    try:
        dados = r.json()
    except ValueError:
        dados = {}
    if r.status_code != 200 or not _ok(dados):
        raise erro_do_tiktok(r.status_code, dados)
    return dados


def _enviar_pedaco(url: str, caminho: str, inicio: int, fim: int, total: int) -> None:
    import httpx
    with open(caminho, "rb") as fh:
        fh.seek(inicio)
        corpo = fh.read(fim - inicio + 1)
    r = httpx.put(url, content=corpo, timeout=600.0, headers={
        "Content-Type": "video/mp4",
        "Content-Length": str(len(corpo)),
        "Content-Range": f"bytes {inicio}-{fim}/{total}",
    })
    if r.status_code not in (200, 201, 206):
        raise PublisherError(f"o TikTok recusou o envio do video ({r.status_code})")


def renovar(segredo: dict) -> dict:
    """Um access token novo (e, talvez, um refresh token novo)."""
    dados = _pedir(TOKEN, data={
        "client_key": segredo["client_key"],
        "client_secret": segredo["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": segredo["refresh_token"],
    })
    if not dados.get("access_token"):
        raise PublisherError("o TikTok nao devolveu access_token")
    return dados


# --------------------------------------------------------------------------- #
# O driver
# --------------------------------------------------------------------------- #

class TikTokApiPublisher(Publisher):
    id = "tiktok-api"
    label = "TikTok (API oficial)"
    platforms = ("tiktok",)

    def disponivel(self, account: Account) -> bool:
        if account.platform != "tiktok":
            return False
        import vault
        return vault.existe(ref_de(account), CAMPOS)

    def capability(self, account: Account) -> str:
        if not self.disponivel(account):
            return "none"
        # Antes da auditoria, tudo sai so para a propria conta.
        return "public" if auditado() else "private_only"

    def cost(self, n: int) -> Cost:
        return Cost(risk_score=0.0, usd=0.0)

    def publish(self, clip: RenderedClip, meta: PostMeta,
                opts: PublishOptions, account: Account) -> PublishResult:
        if not os.path.exists(clip.path):
            return PublishResult(ok=False, driver=self.id, status="failed",
                                 detail=f"O arquivo do corte nao existe: {clip.path}")
        tamanho = os.path.getsize(clip.path)
        if opts.dry_run:
            corpo = corpo_do_post(meta, PRIVADO, {}, tamanho)
            return PublishResult(ok=True, driver=self.id, status="scheduled",
                                 detail=f"dry-run: {corpo['post_info']['title'][:80]}")

        import vault
        ref = ref_de(account)
        segredo = vault.resolve(ref, exigir=CAMPOS)
        tokens = renovar(segredo)
        if tokens.get("refresh_token") and tokens["refresh_token"] != segredo["refresh_token"]:
            # O TikTok trocou o refresh token: o velho pode deixar de valer.
            vault.gravar(ref, {**segredo, "refresh_token": tokens["refresh_token"]})
        token = tokens["access_token"]

        info = (_pedir(CREATOR_INFO, token=token, json={}).get("data") or {})
        maximo = info.get("max_video_post_duration_sec")
        if maximo and clip.duration_s and clip.duration_s > maximo:
            raise PublisherError(f"o corte tem {clip.duration_s:.0f} s e esta conta do TikTok "
                                 f"aceita ate {maximo} s")
        privacidade = escolher_privacidade(opts.visibility, info.get("privacy_level_options"),
                                           auditado=auditado())

        inicio = _pedir(INICIAR, token=token,
                        json=corpo_do_post(meta, privacidade, info, tamanho)).get("data") or {}
        publish_id, destino = inicio.get("publish_id"), inicio.get("upload_url")
        if not publish_id or not destino:
            raise PublisherError("o TikTok aceitou o pedido e nao mandou para onde enviar")
        for de, ate in pedacos(tamanho):
            _enviar_pedaco(destino, clip.path, de, ate, tamanho)

        prazo = time.monotonic() + ESPERA_DO_PROCESSAMENTO_S
        situacao, dados = "PROCESSING_UPLOAD", {}
        while time.monotonic() < prazo:
            dados = _pedir(STATUS, token=token, json={"publish_id": publish_id}).get("data") or {}
            situacao = dados.get("status") or ""
            if situacao in ("PUBLISH_COMPLETE", "FAILED"):
                break
            time.sleep(INTERVALO_DO_STATUS_S)
        if situacao == "FAILED":
            raise PublisherError(f"o TikTok nao publicou: {dados.get('fail_reason') or 'sem motivo'}")

        ids = dados.get("publicaly_available_post_id") or []
        usuario = info.get("creator_username") or account.handle.lstrip("@")
        url = f"https://www.tiktok.com/@{usuario}/video/{ids[0]}" if ids else None
        detalhe = ("publicado so para voce (antes da auditoria do TikTok)"
                   if privacidade == PRIVADO else "publicado")
        if situacao != "PUBLISH_COMPLETE":
            detalhe = "enviado; o TikTok ainda estava processando -- confira no app"
        return PublishResult(ok=True, driver=self.id, status="published",
                             remote_id=str(ids[0]) if ids else None, url=url,
                             detail=detalhe)
