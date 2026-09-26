"""Coletor de `metrics` -- Fase 5.

A secao 7 chama `metrics` de "a tabela mais valiosa do projeto" e explica por
que: e ela que permite trocar a rubrica do LLM por **retencao medida**. A
tabela existe desde a Fase 0.5 e ate aqui estava vazia, porque nada a escrevia.

### O escopo que o upload nao pediu, e por que ele continua nao pedindo

O bloco 3.4 emitiu o token de publicacao com `youtube.upload` **e so ele**, com
o motivo escrito: se o token vazar, a diferenca para o escopo `youtube` completo
e a diferenca entre um video indesejado e um canal vazio.

Ler estatistica exige mais que isso. `videos.list` de um video **privado** --
e os nossos sobem privados por padrao -- precisa de `youtube.readonly`; a
retencao precisa da API de Analytics, com `yt-analytics.readonly`.

**A saida nao foi ampliar o token de upload.** Foi um SEGUNDO consentimento, so
de leitura, guardado em outro endereco de cofre
(`vault://<backend>/youtube-metrics/<handle>`). Duas credenciais pequenas em vez
de uma grande: a que publica nao le, a que le nao publica, e nenhuma das duas
apaga. `python youtube_oauth.py --leitura` emite a segunda.

Enquanto ela nao existir, o coletor **nao falha**: ele registra o que consegue
(nada) e diz uma vez o que rodar. Um projeto sem metricas funciona; um projeto
que nao sobe porque faltou metrica, nao.

### `metrics` e serie temporal, nao cache do estado atual

Cada coleta **acrescenta linha**, nunca atualiza. Nao e desperdicio: retencao
matura em dias, e o valor de 24 h depois e diferente do de uma semana depois. A
coluna `collected_at` da secao 7 existe exatamente para isso, e a tabela nao tem
unicidade por publicacao -- o que seria um bug se fosse cache, e e o desenho
sendo respeitado aqui.

### Rede isolada, decisao pura

Mesmo padrao do `youtube_api.py`: o que fala com a rede esta em funcoes
pequenas, e o que interpreta resposta e funcao pura. O CI nao alcanca as
primeiras e cobre as segundas.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from publishers import quota
from publishers.base import PublisherError

URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
URL_ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"

#: Os dois escopos de LEITURA. `youtube.readonly` ve a estatistica publica de um
#: video privado que e seu; `yt-analytics.readonly` ve a retencao. Nenhum dos
#: dois sobe, apaga ou edita nada.
ESCOPOS_DE_LEITURA = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)

#: Custo publicado de um `videos.list`. Uma unidade das 10.000 do dia -- que,
#: desde jun-2026, sao so das chamadas que NAO sao envio (o envio tem cota
#: propria). Barato, mas debitado: um contador que ignora o que e barato deixa
#: de ser o contador.
CUSTO_LIST = 1

#: O endereco da credencial de leitura. Namespace proprio de proposito: e outro
#: arquivo, com outro escopo, e confundi-lo com o de publicacao seria o jeito
#: mais facil de acabar com um token so, grande.
REF_LEITURA = "vault://{backend}/youtube-metrics/{handle}"

#: A janela que a consulta de retencao cobre. 90 dias para tras: um corte
#: publicado ontem tem dado de ontem, e um de dois meses atras continua
#: respondendo em vez de sumir da coleta.
DIAS_DE_JANELA = 90


def ref_de_leitura(handle: str, backend: str = "local") -> str:
    return REF_LEITURA.format(backend=backend, handle=handle or "conta")


def credencial_de_leitura(handle: str) -> Optional[dict]:
    """O segredo de leitura, ou None se ainda nao houver.

    Tenta `local` (o que o `youtube_oauth.py --leitura` grava) e depois `env`,
    na mesma ordem de preferencia do driver de publicacao.
    """
    import vault
    for backend in ("local", "env"):
        try:
            return vault.resolve(ref_de_leitura(handle, backend),
                                 exigir=("client_id", "client_secret",
                                         "refresh_token"))
        except vault.VaultError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Interpretacao -- puro
# --------------------------------------------------------------------------- #

def parse_views(payload: dict) -> Optional[int]:
    """`viewCount` da resposta de `videos.list`, ou None.

    Devolve None, e nao zero, quando o campo nao veio: zero e um numero que a
    Fase 5 vai cruzar com a rubrica, e "nao medido" nao pode entrar na media
    como se fosse "ninguem assistiu".
    """
    try:
        itens = payload.get("items") or []
        if not itens:
            return None
        bruto = (itens[0].get("statistics") or {}).get("viewCount")
        return None if bruto is None else max(0, int(bruto))
    except (AttributeError, TypeError, ValueError):
        return None


def parse_retencao(payload: dict) -> Optional[float]:
    """`averageViewPercentage` do relatorio de Analytics, ou None.

    **Le pelo nome da coluna, nunca pela posicao.** A API devolve
    `columnHeaders` junto das linhas justamente porque a ordem pode mudar com a
    lista de metricas pedida -- e ler a coluna errada aqui nao daria erro, so
    gravaria o numero de views no campo de retencao.
    """
    try:
        cabecalhos = [c.get("name") for c in (payload.get("columnHeaders") or [])]
        linhas = payload.get("rows") or []
        if not linhas or "averageViewPercentage" not in cabecalhos:
            return None
        valor = linhas[0][cabecalhos.index("averageViewPercentage")]
        pct = float(valor)
    except (AttributeError, TypeError, ValueError, IndexError):
        return None
    # O CHECK da coluna recusa fora de 0..100, e um valor estranho da API
    # derrubaria a gravacao das OUTRAS publicacoes da mesma rodada.
    return max(0.0, min(100.0, round(pct, 2)))


def janela(hoje: Optional[date] = None) -> tuple:
    hoje = hoje or date.today()
    return (hoje - timedelta(days=DIAS_DE_JANELA)).isoformat(), hoje.isoformat()


# --------------------------------------------------------------------------- #
# Rede -- o que o CI nao alcanca
# --------------------------------------------------------------------------- #

def _token_de_leitura(segredo: dict) -> str:
    import httpx

    resposta = httpx.post(URL_TOKEN, timeout=30.0, data={
        "client_id": segredo["client_id"],
        "client_secret": segredo["client_secret"],
        "refresh_token": segredo["refresh_token"],
        "grant_type": "refresh_token",
    })
    if resposta.status_code != 200:
        raise PublisherError(
            f"o Google recusou o token de leitura ({resposta.status_code}). "
            "Rode `python youtube_oauth.py --leitura` de novo.")
    token = (resposta.json() or {}).get("access_token")
    if not token:
        raise PublisherError("o Google nao devolveu access_token de leitura")
    return token


def _buscar_views(token: str, video_id: str) -> Optional[int]:
    import httpx

    quota.registrar_unidades(CUSTO_LIST)
    resposta = httpx.get(URL_VIDEOS, timeout=30.0,
                         headers={"Authorization": f"Bearer {token}"},
                         params={"part": "statistics", "id": video_id})
    if resposta.status_code != 200:
        raise PublisherError(f"videos.list respondeu {resposta.status_code}: "
                             f"{resposta.text[:200]}")
    return parse_views(resposta.json() or {})


def _buscar_retencao(token: str, video_id: str) -> Optional[float]:
    import httpx

    inicio, fim = janela()
    resposta = httpx.get(URL_ANALYTICS, timeout=30.0,
                         headers={"Authorization": f"Bearer {token}"},
                         params={"ids": "channel==MINE",
                                 "startDate": inicio, "endDate": fim,
                                 "metrics": "averageViewPercentage",
                                 "filters": f"video=={video_id}"})
    if resposta.status_code == 403:
        # Falta o escopo de Analytics, ou o canal nao tem dado suficiente.
        # Nao e erro do coletor: as views continuam valendo.
        return None
    if resposta.status_code != 200:
        raise PublisherError(f"analytics respondeu {resposta.status_code}: "
                             f"{resposta.text[:200]}")
    return parse_retencao(resposta.json() or {})


def medir(video_id: str, handle: str) -> dict:
    """Views e retencao de um video. Levanta `PublisherError` se a rede falhar.

    Devolve `{"views": .., "retention_pct": ..}` com None no que nao deu para
    medir -- e nao zero. A diferenca entre "ninguem assistiu" e "nao consegui
    perguntar" e a diferenca entre um dado e um dado falso.
    """
    segredo = credencial_de_leitura(handle)
    if segredo is None:
        raise PublisherError(
            "esta instalacao ainda nao tem credencial de LEITURA do YouTube. "
            "Rode `python youtube_oauth.py --leitura` uma vez -- o token de "
            "publicacao nao serve, e nao serve de proposito (escopo minimo).")
    token = _token_de_leitura(segredo)
    return {"views": _buscar_views(token, video_id),
            "retention_pct": _buscar_retencao(token, video_id)}
