"""Achar video com licenca livre -- as fontes da receita da etapa 7.5.

"O YouTube marca os videos Creative Commons, e a busca filtra so esses: pela
API (100 buscas por dia) ou pelo yt-dlp, conferindo a licenca de cada video
antes de baixar" (docs/PLANO-DA-PLATAFORMA.md). Os dois caminhos estao aqui, e
devolvem a mesma forma de candidato:

- **pela API** (`buscar_pela_api`): `search.list` com `videoLicense=
  creativeCommon` e, para cada achado, `videos.list` com `status.license` -- a
  licenca dita pelo proprio YouTube, sem depender da pagina. Gasta uma das 100
  buscas do dia (cota propria desde jun-2026) e precisa de uma conta do YouTube
  conectada para MEDIR (o escopo `youtube.readonly`): quem ja conectou para ver
  as analises ganha a busca de graca;
- **pelo yt-dlp** (`buscar_pelo_ytdlp` + `conferir_pelo_ytdlp`): a pagina de
  resultados com o filtro Creative Commons e, depois, a pagina de cada video,
  onde o YouTube escreve "Creative Commons Attribution license (reuse
  allowed)". Sem cadastro e sem cota -- e o caminho de quem nao conectou nada.

**A licenca e conferida no VIDEO, nunca so no filtro da busca.** O filtro diz o
que o YouTube achou; o credito que vai na descricao diz que a licenca permite,
e isso se afirma do video, um por um. Na pagina, a ausencia da linha de
licenca e "nao confirmado", e a busca nao deixa entrar: `desconhecida` nunca
vira `cc-by` por aproximacao (`licencas.normalizar`).

A parte de rede do yt-dlp roda num SUBPROCESSO (`python busca_cc.py`, pedido em
JSON pela entrada padrao, resposta em JSON na saida), como o `quality_probe.py`:
o processo do servidor nao importa o yt-dlp, uma busca travada morre no prazo
sem levar o servidor junto, e o log do yt-dlp nao se mistura com o do motor.
A da API roda no proprio motor, que e quem tem a credencial.

O que decide -- o filtro da busca, a leitura de cada resposta -- e puro, e o CI
exercita tudo sem rede.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse

import licencas

#: A faixa de duracao, em segundos, de cada escolha da receita -- as faixas da
#: propria busca do YouTube ("4-20 minutos", "mais de 20 minutos").
FAIXAS = {"media": (4 * 60, 20 * 60), "longa": (20 * 60, None), "qualquer": (60, None)}
#: O `videoDuration` da API e o campo 3 do filtro da pagina, para cada escolha.
_DURACAO_DA_API = {"media": "medium", "longa": "long"}
_DURACAO_DO_FILTRO = {"longa": 2, "media": 3}

#: Quantos videos novos uma busca confere, no maximo. Cada conferencia pelo
#: yt-dlp e uma pagina inteira (2 a 5 s); dez por busca da conta de sobra para
#: quem corta um video por dia, sem deixar a busca levar minutos.
MAX_CONFERIDOS = 10

URL_BUSCA_API = "https://www.googleapis.com/youtube/v3/search"
URL_VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"

_ISO_DURACAO = re.compile(
    r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


# --------------------------------------------------------------------------- #
# O filtro da pagina de resultados -- puro
# --------------------------------------------------------------------------- #

def _varint(n: int) -> bytes:
    saida = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            saida.append(byte | 0x80)
        else:
            saida.append(byte)
            return bytes(saida)


def sp_da_busca(duracao: str = "qualquer") -> str:
    """O parametro `sp` da busca do YouTube: so video, so Creative Commons e,
    se pedido, a faixa de duracao.

    O `sp` e um protobuf em base64. O que importa dele: o campo 2 guarda os
    filtros, e dentro dele o 2 e o tipo (1 = video), o 3 a duracao (2 = mais de
    20 min, 3 = de 4 a 20) e o 6 o Creative Commons. Os valores conhecidos --
    `EgIwAQ==` (so Creative Commons) e `EgIQAQ==` (so video) -- estao no teste,
    montados por esta mesma funcao.
    """
    filtros = _varint((2 << 3) | 0) + _varint(1)          # tipo: video
    faixa = _DURACAO_DO_FILTRO.get(duracao)
    if faixa:
        filtros += _varint((3 << 3) | 0) + _varint(faixa)  # duracao
    filtros += _varint((6 << 3) | 0) + _varint(1)          # Creative Commons
    mensagem = _varint((2 << 3) | 2) + _varint(len(filtros)) + filtros
    return base64.b64encode(mensagem).decode("ascii")


def url_da_busca(tema: str, duracao: str = "qualquer") -> str:
    return "https://www.youtube.com/results?" + urlencode(
        {"search_query": tema, "sp": sp_da_busca(duracao)})


def duracao_serve(segundos, duracao: str) -> bool:
    """Se o video cabe na faixa pedida. Sem duracao conhecida, nao cabe: a
    busca nao sabe o que esta mandando cortar."""
    if not isinstance(segundos, (int, float)) or segundos <= 0:
        return False
    minimo, maximo = FAIXAS.get(duracao, FAIXAS["qualquer"])
    return segundos >= minimo and (maximo is None or segundos <= maximo)


def segundos_iso(texto) -> Optional[int]:
    """`PT1H2M3S` (o `contentDetails.duration` da API) em segundos."""
    if not isinstance(texto, str):
        return None
    m = _ISO_DURACAO.match(texto.strip())
    if not m:
        return None
    dias, horas, minutos, segundos = m.groups()
    total = (int(dias or 0) * 86400 + int(horas or 0) * 3600 + int(minutos or 0) * 60
             + float(segundos or 0))
    return int(total)


def _inteiro(valor) -> Optional[int]:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero >= 0 else None


def _miniatura(info: dict) -> Optional[str]:
    """A miniatura de maior resolucao que nao seja enorme, ou a do id."""
    miniaturas = [t for t in (info.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    medias = [t for t in miniaturas if (t.get("width") or 0) <= 720]
    if medias:
        return max(medias, key=lambda t: t.get("width") or 0)["url"]
    if info.get("thumbnail"):
        return info["thumbnail"]
    vid = info.get("id")
    if isinstance(vid, str) and re.match(r"^[A-Za-z0-9_-]{11}$", vid):
        return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    return None


# --------------------------------------------------------------------------- #
# Leitura do que o yt-dlp devolve -- puro
# --------------------------------------------------------------------------- #

def candidato_do_video(info: dict) -> Optional[dict]:
    """O candidato a partir da extracao COMPLETA de um video (a pagina dele).

    E aqui que a licenca e lida: `info["license"]` e o texto que o YouTube
    escreve na pagina, e so os videos Creative Commons tem a linha. A ausencia
    vira `desconhecida` -- nunca `cc-by`.
    """
    if not isinstance(info, dict):
        return None
    url = info.get("webpage_url") or info.get("original_url") or info.get("url")
    vid = info.get("id")
    if info.get("extractor_key", "").lower().startswith("youtube") or licencas.youtube_id(url):
        vid = licencas.youtube_id(url) or (vid if isinstance(vid, str) else None)
        if vid:
            url = licencas.url_do_youtube(vid)
    if not url:
        return None
    texto = info.get("license")
    return {
        "key": licencas.chave(url),
        "url": url,
        "title": (info.get("title") or "")[:300] or None,
        "author": (info.get("channel") or info.get("uploader") or "")[:200] or None,
        "author_url": info.get("channel_url") or info.get("uploader_url"),
        "duration_s": _inteiro(info.get("duration")),
        "published_at": _data_do_ytdlp(info.get("upload_date") or info.get("release_date")),
        "thumbnail": _miniatura(info),
        "views": _inteiro(info.get("view_count")),
        "license": licencas.normalizar(texto),
        "license_text": (texto or "")[:200] or None,
        "language": info.get("language"),
        "age_limit": _inteiro(info.get("age_limit")) or 0,
        "live_status": info.get("live_status"),
    }


def _data_do_ytdlp(valor) -> Optional[str]:
    """`20240501` -> `2024-05-01`."""
    if isinstance(valor, str) and re.match(r"^\d{8}$", valor):
        return f"{valor[:4]}-{valor[4:6]}-{valor[6:]}"
    return None


def entradas_da_lista(info: dict) -> list:
    """As entradas de uma busca ou lista extraida em modo plano (so id e
    titulo, sem abrir cada video), achatando as listas dentro de listas."""
    saida = []
    for entrada in (info or {}).get("entries") or []:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("_type") == "playlist" or entrada.get("entries"):
            saida.extend(entradas_da_lista(entrada))
            continue
        url = entrada.get("url") or entrada.get("webpage_url")
        vid = entrada.get("id")
        if not url and isinstance(vid, str):
            url = licencas.url_do_youtube(vid) if re.match(r"^[A-Za-z0-9_-]{11}$", vid) else None
        if not url:
            continue
        saida.append({"url": url, "key": licencas.chave(url),
                      "title": entrada.get("title"),
                      "duration_s": _inteiro(entrada.get("duration")),
                      "views": _inteiro(entrada.get("view_count"))})
    return saida


def serve_para_a_busca(candidato: dict, duracao: str) -> Optional[str]:
    """None quando o video entra; senao, o motivo de ficar de fora, em frase."""
    if candidato.get("license") not in licencas.LIVRES:
        return "o YouTube não confirmou a licença Creative Commons neste vídeo"
    if candidato.get("live_status") in ("is_live", "is_upcoming"):
        return "é uma transmissão ao vivo"
    if (candidato.get("age_limit") or 0) >= 18:
        return "o vídeo tem restrição de idade"
    if not duracao_serve(candidato.get("duration_s"), duracao):
        return "a duração não é a pedida na receita"
    return None


# --------------------------------------------------------------------------- #
# Leitura do que a API devolve -- puro
# --------------------------------------------------------------------------- #

def ids_da_busca_api(resposta: dict) -> list:
    ids = []
    for item in (resposta or {}).get("items") or []:
        vid = ((item or {}).get("id") or {}).get("videoId")
        if isinstance(vid, str) and vid not in ids:
            ids.append(vid)
    return ids


def candidatos_da_api(resposta_videos: dict) -> list:
    """Os candidatos do `videos.list`, com a licenca que o YouTube diz em
    `status.license` (`creativeCommon` ou `youtube`)."""
    saida = []
    for item in (resposta_videos or {}).get("items") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        snippet = item.get("snippet") or {}
        status = item.get("status") or {}
        detalhes = item.get("contentDetails") or {}
        numeros = item.get("statistics") or {}
        url = licencas.url_do_youtube(item["id"])
        miniaturas = snippet.get("thumbnails") or {}
        miniatura = next((miniaturas[k]["url"] for k in ("high", "medium", "default")
                          if isinstance(miniaturas.get(k), dict) and miniaturas[k].get("url")),
                         None)
        canal = snippet.get("channelId")
        saida.append({
            "key": licencas.chave(url),
            "url": url,
            "title": (snippet.get("title") or "")[:300] or None,
            "author": (snippet.get("channelTitle") or "")[:200] or None,
            "author_url": f"https://www.youtube.com/channel/{canal}" if canal else None,
            "duration_s": segundos_iso(detalhes.get("duration")),
            "published_at": (snippet.get("publishedAt") or "")[:10] or None,
            "thumbnail": miniatura,
            "views": _inteiro(numeros.get("viewCount")),
            "license": licencas.normalizar(status.get("license")),
            "license_text": status.get("license"),
            "language": snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
            "age_limit": 18 if (detalhes.get("contentRating") or {}).get("ytRating") == "ytAgeRestricted" else 0,
            "live_status": ("is_live" if snippet.get("liveBroadcastContent") == "live"
                            else "is_upcoming" if snippet.get("liveBroadcastContent") == "upcoming"
                            else "not_live"),
        })
    return saida


def parametros_da_api(tema: str, duracao: str, idioma: Optional[str],
                      limite: int, criancas: bool = False) -> dict:
    """Os parametros do `search.list`. `safeSearch=strict` no canal infantil."""
    parametros = {
        "part": "snippet", "type": "video", "videoLicense": "creativeCommon",
        "q": tema, "maxResults": max(1, min(50, int(limite))),
        "safeSearch": "strict" if criancas else "moderate",
    }
    if duracao in _DURACAO_DA_API:
        parametros["videoDuration"] = _DURACAO_DA_API[duracao]
    curto = (idioma or "").split("-")[0].lower()
    if re.match(r"^[a-z]{2}$", curto):
        parametros["relevanceLanguage"] = curto
    return parametros


# --------------------------------------------------------------------------- #
# Rede: a API (roda no motor, que tem a credencial)
# --------------------------------------------------------------------------- #

def buscar_pela_api(tema: str, duracao: str, idioma: Optional[str], token: str,
                    limite: int = 25, criancas: bool = False,
                    http_get: Optional[Callable] = None) -> list:
    """Busca e confere pela API. Debita a busca ANTES de chamar, como o envio.

    `http_get(url, params, headers) -> (status, json)` e injetavel para teste.
    """
    from publishers import quota
    from publishers.base import PublisherError

    if http_get is None:
        def http_get(url, params, headers):
            import httpx
            resposta = httpx.get(url, params=params, headers=headers, timeout=30.0)
            try:
                corpo = resposta.json()
            except ValueError:
                corpo = {}
            return resposta.status_code, corpo

    if not quota.cabe_busca():
        raise PublisherError("a cota de buscas do YouTube de hoje acabou")
    cabecalho = {"Authorization": f"Bearer {token}"}
    quota.registrar_busca()
    status, achados = http_get(URL_BUSCA_API,
                               parametros_da_api(tema, duracao, idioma, limite, criancas),
                               cabecalho)
    if status != 200:
        raise PublisherError(f"a busca do YouTube respondeu {status}")
    ids = ids_da_busca_api(achados)
    if not ids:
        return []
    quota.registrar_unidades(1)
    status, videos = http_get(URL_VIDEOS_API, {
        "part": "snippet,contentDetails,status,statistics", "id": ",".join(ids[:50])},
        cabecalho)
    if status != 200:
        raise PublisherError(f"a lista de vídeos do YouTube respondeu {status}")
    por_id = {c["url"]: c for c in candidatos_da_api(videos)}
    # Na ordem da busca, que e a da relevancia.
    return [por_id[licencas.url_do_youtube(v)] for v in ids
            if licencas.url_do_youtube(v) in por_id]


# --------------------------------------------------------------------------- #
# Rede: o yt-dlp (roda no subprocesso)
# --------------------------------------------------------------------------- #

class _Registro:
    """Junta os avisos do yt-dlp em vez de imprimi-los: a saida padrao do
    subprocesso e so o JSON da resposta."""

    def __init__(self):
        self.avisos = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.avisos.append(str(msg)[:300])

    def error(self, msg):
        self.avisos.append(str(msg)[:300])


def _opcoes(registro: _Registro, url: str, cookies: bool, plano: bool = False) -> dict:
    """As mesmas opcoes do `quality_probe.py`: a lista de clientes e a do
    download (`yt_clients`), e o jar de cookies o de `sources.jar_em_disco`."""
    import sources
    import yt_clients

    opcoes = {
        "quiet": True, "no_warnings": False, "logger": registro,
        "socket_timeout": 20, "retries": 2, "cachedir": False,
        "skip_download": True,
    }
    if plano:
        opcoes["extract_flat"] = "in_playlist"
    jar = sources.jar_em_disco(url) if cookies else None
    if jar:
        opcoes["cookiefile"] = jar
    if licencas.youtube_id(url) or "youtube.com" in url:
        opcoes["extractor_args"] = yt_clients.fallback_extractor_args(
            os.environ.get("BGUTIL_BASE_URL", "").strip(),
            os.environ.get("BGUTIL_SCRIPT_PATH", "").strip(), cookies=bool(jar))
    return opcoes


def _extrair_de_verdade(url: str, registro: _Registro, plano: bool = False,
                        limite: Optional[int] = None) -> dict:
    """Extrai com cookies (se houver jar) e, falhando, sem -- a ordem do
    `quality_probe.py`."""
    import sources
    import yt_dlp

    tentativas = [True, False] if sources.jar_em_disco(url) else [False]
    ultimo = None
    for cookies in tentativas:
        opcoes = _opcoes(registro, url, cookies, plano)
        if limite:
            opcoes["playlistend"] = int(limite)
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                return ydl.extract_info(url, download=False) or {}
        except Exception as e:           # noqa: BLE001 -- o proximo tenta
            ultimo = e
    raise RuntimeError(str(ultimo)[:300] if ultimo else "o yt-dlp nao respondeu")


def buscar_pelo_ytdlp(tema: str, duracao: str, vistos=(), limite: int = 25,
                      extrair: Optional[Callable] = None,
                      registro: Optional[_Registro] = None) -> dict:
    """`{"candidatos": [...], "recusados": [...], "avisos": [...]}`.

    Busca com o filtro Creative Commons e confere a licenca de cada video
    novo -- no maximo `MAX_CONFERIDOS` por busca. `vistos` sao as chaves que o
    motor ja conhece (candidatos desta receita e fontes ja usadas): nao gastam
    conferencia.
    """
    registro = registro or _Registro()
    extrair = extrair or (lambda url, plano=False, limite=None:
                          _extrair_de_verdade(url, registro, plano, limite))
    vistos = set(vistos or ())
    lista = extrair(url_da_busca(tema, duracao), plano=True, limite=limite)
    candidatos, recusados = [], []
    conferidos = 0
    for entrada in entradas_da_lista(lista):
        if not entrada.get("key") or entrada["key"] in vistos:
            continue
        vistos.add(entrada["key"])
        # A duracao da lista plana ja descarta sem abrir a pagina.
        if entrada.get("duration_s") and not duracao_serve(entrada["duration_s"], duracao):
            continue
        if conferidos >= MAX_CONFERIDOS:
            break
        conferidos += 1
        try:
            candidato = candidato_do_video(extrair(entrada["url"]))
        except Exception as e:           # noqa: BLE001 -- um video nao para a busca
            registro.avisos.append(f"{entrada['url']}: {str(e)[:200]}")
            continue
        if candidato is None:
            continue
        motivo = serve_para_a_busca(candidato, duracao)
        if motivo:
            recusados.append({**candidato, "motivo": motivo})
        else:
            candidatos.append(candidato)
    return {"candidatos": candidatos, "recusados": recusados, "avisos": registro.avisos[-10:]}


def _lista_de_canal(url: str) -> str:
    """O endereco de um canal do YouTube sem aba vira o da aba de videos:
    sem ela, o yt-dlp devolve as abas (Videos, Shorts, Ao vivo) como listas."""
    partes = urlparse(url)
    caminho = [p for p in (partes.path or "").split("/") if p]
    host = (partes.hostname or "").lower()
    if "youtube.com" not in host or not caminho:
        return url
    raiz = caminho[0]
    e_canal = raiz.startswith("@") or (raiz in ("channel", "c", "user") and len(caminho) >= 2)
    tamanho_da_raiz = 1 if raiz.startswith("@") else 2
    if e_canal and len(caminho) == tamanho_da_raiz:
        return url.rstrip("/") + "/videos"
    return url


def e_lista(url: str) -> bool:
    """Se o link e uma lista (playlist ou canal) em vez de um video."""
    if licencas.youtube_id(url):
        return False
    partes = urlparse(url)
    host = (partes.hostname or "").lower()
    if "youtube.com" not in host:
        return False
    caminho = [p for p in (partes.path or "").split("/") if p]
    return bool(caminho) and (caminho[0] in ("playlist", "channel", "c", "user")
                              or caminho[0].startswith("@"))


def listar_links(links, vistos=(), por_lista: int = 15,
                 extrair: Optional[Callable] = None,
                 registro: Optional[_Registro] = None) -> dict:
    """Os videos dos links de uma receita: o link de video vira candidato, e a
    lista (playlist ou canal) vira os videos mais recentes dela.

    Cada video e aberto para saber titulo, autor, duracao e licenca -- a
    licenca aqui nao filtra (quem usa confirmou ter os direitos), mas decide o
    credito.
    """
    registro = registro or _Registro()
    extrair = extrair or (lambda url, plano=False, limite=None:
                          _extrair_de_verdade(url, registro, plano, limite))
    vistos = set(vistos or ())
    candidatos = []
    conferidos = 0
    for link in links or []:
        if e_lista(link):
            try:
                entradas = entradas_da_lista(extrair(_lista_de_canal(link), plano=True,
                                                     limite=por_lista))
            except Exception as e:       # noqa: BLE001
                registro.avisos.append(f"{link}: {str(e)[:200]}")
                continue
            urls = [e["url"] for e in entradas]
        else:
            urls = [link]
        for url in urls:
            chave = licencas.chave(url)
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            if conferidos >= MAX_CONFERIDOS:
                break
            conferidos += 1
            candidato = None
            if licencas.youtube_id(url) or "twitch.tv" in url:
                try:
                    candidato = candidato_do_video(extrair(url))
                except Exception as e:   # noqa: BLE001
                    registro.avisos.append(f"{url}: {str(e)[:200]}")
            if candidato is None:
                # Drive, URL direta ou pagina que nao abriu: entra com o que se
                # sabe, e o download descobre o resto.
                candidato = {"key": chave, "url": url, "title": None, "author": None,
                             "author_url": None, "duration_s": None, "published_at": None,
                             "thumbnail": None, "views": None, "license": "desconhecida",
                             "license_text": None}
            candidatos.append(candidato)
    return {"candidatos": candidatos, "recusados": [], "avisos": registro.avisos[-10:]}


def twitch_ao_vivo(url: str, extrair: Optional[Callable] = None) -> dict:
    """`{"ao_vivo": bool, "titulo": str | None}` -- o canal esta transmitindo?

    E o que impede a receita de criar um job por minuto para um canal fora do
    ar: o job so nasce quando ha o que gravar.
    """
    from sources import twitch_live

    try:
        if extrair is None:
            vivo = twitch_live.resolve_live(url)
        else:
            vivo = twitch_live.resolve_live(url, ydl=extrair)
    except twitch_live.LiveOffline:
        return {"ao_vivo": False, "titulo": None}
    return {"ao_vivo": True, "titulo": vivo.get("title")}


# --------------------------------------------------------------------------- #
# O subprocesso
# --------------------------------------------------------------------------- #

def responder(pedido: dict) -> dict:
    acao = (pedido or {}).get("acao")
    if acao == "busca":
        return buscar_pelo_ytdlp(str(pedido.get("tema") or ""),
                                 str(pedido.get("duracao") or "qualquer"),
                                 vistos=pedido.get("vistos") or (),
                                 limite=int(pedido.get("limite") or 25))
    if acao == "links":
        return listar_links(pedido.get("links") or [], vistos=pedido.get("vistos") or ())
    if acao == "twitch":
        return twitch_ao_vivo(str(pedido.get("url") or ""))
    return {"erro": f"acao desconhecida: {acao}"}


def main() -> int:
    try:
        pedido = json.loads(sys.stdin.read() or "{}")
        resposta = responder(pedido)
    except Exception as e:               # noqa: BLE001 -- a resposta diz o que houve
        resposta = {"erro": f"{type(e).__name__}: {str(e)[:300]}"}
    sys.stdout.write(json.dumps(resposta, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
