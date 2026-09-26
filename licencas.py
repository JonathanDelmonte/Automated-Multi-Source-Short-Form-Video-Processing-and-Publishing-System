"""A origem e a licenca de cada video, e o credito que a licenca exige (7.5).

Tres perguntas moram aqui, e as tres sao regra, entao este modulo e stdlib
pura -- o CI as exercita sem rede e sem banco:

1. **Que licenca e esta?** O YouTube diz de dois jeitos: a pagina do video
   (lida pelo yt-dlp) escreve "Creative Commons Attribution license (reuse
   allowed)"; a API responde `creativeCommon`. Os dois viram `cc-by`.
2. **Que video e este?** A chave (`youtube:<id>`) que faz o "nao repetir"
   funcionar entre fontes e entre canais: o mesmo video colado de tres jeitos
   (`youtu.be/`, `watch?v=`, `shorts/`) e um video so.
3. **O que o credito diz?** A licenca Creative Commons Atribuicao pede
   titulo, autor, fonte e licenca, e que se diga que houve alteracao. O credito
   vai no fim da descricao de toda plataforma, e **nunca e cortado** para caber
   (`publishers.base.com_credito`).

**A versao da licenca.** O YouTube usou a CC BY 3.0 ate jul-2025 e passou a
usar a 4.0 (pesquisado em 26-set-2026). Nem a pagina nem a API dizem qual vale
para um video, entao a versao e deduzida da data de envio -- a melhor
aproximacao que ha: quem marcou Creative Commons num video antigo depois da
troca fica com o link da 3.0, e as duas pedem o mesmo credito.

A origem de um projeto mora tambem na PASTA dele (`.origem.json`), ao lado do
`.canal` e do `.tenant`: a lista de projetos e o pacote do dia vem do disco, e
o credito tem de sair mesmo com o banco fora do ar.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

#: As mesmas de `db_models.LICENSES`, repetidas para que este modulo nao
#: dependa do SQLAlchemy -- um teste compara as duas.
LICENCAS = ("cc-by", "dominio-publico", "youtube", "propria", "autorizada", "desconhecida")

#: As que pedem credito. Dominio publico nao exige, mas dizer de onde veio
#: custa uma linha e responde a pergunta antes de alguem faze-la.
COM_CREDITO = ("cc-by", "dominio-publico")

#: As que deixam um video entrar sozinho pela busca: a licenca CONFERIDA pelo
#: programa. As declaradas pela pessoa (`propria`, `autorizada`) entram pelos
#: links, pela live e pela pasta, com a confirmacao dela.
LIVRES = ("cc-by", "dominio-publico")

#: Quando o YouTube trocou a CC BY 3.0 pela 4.0.
TROCA_PARA_A_4 = date(2025, 8, 1)

ARQUIVO_ORIGEM = ".origem.json"

_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS_YOUTUBE = ("youtube.com", "youtube-nocookie.com")


def normalizar(texto) -> str:
    """A licenca num dos valores de `LICENCAS`, venha como vier.

    Aceita o texto da pagina ("Creative Commons Attribution license (reuse
    allowed)", "Standard YouTube License"), o valor da API (`creativeCommon`,
    `youtube`) e os proprios valores. O que nao se reconhece e `desconhecida`
    -- nunca `cc-by` por aproximacao: a busca so deixa entrar o que foi
    CONFERIDO livre.
    """
    if not isinstance(texto, str) or not texto.strip():
        return "desconhecida"
    bruto = texto.strip()
    if bruto in LICENCAS:
        return bruto
    baixo = bruto.lower()
    if baixo in ("creativecommon", "creative commons") or "creative commons" in baixo:
        # "Creative Commons Attribution" e a unica que o YouTube oferece. Outra
        # variante (NC, ND, SA) numa fonte que nao seja o YouTube nao e a
        # mesma licenca, e nao passa por aqui como se fosse.
        if any(v in baixo for v in ("noncommercial", "non-commercial", "noderiv",
                                    "no deriv", "sharealike", "share alike")):
            return "desconhecida"
        return "cc-by"
    if baixo in ("youtube", "standard youtube license") or "standard youtube" in baixo:
        return "youtube"
    if "public domain" in baixo or "dominio publico" in baixo or "domínio público" in baixo:
        return "dominio-publico"
    return "desconhecida"


def youtube_id(url) -> Optional[str]:
    """O id de 11 caracteres de um link do YouTube, ou None."""
    if not isinstance(url, str):
        return None
    bruto = url.strip()
    if not bruto:
        return None
    if "://" not in bruto:
        bruto = "https://" + bruto
    try:
        partes = urlparse(bruto)
    except ValueError:
        return None
    host = (partes.hostname or "").lower()
    caminho = [p for p in (partes.path or "").split("/") if p]
    candidato = None
    if host == "youtu.be" or host.endswith(".youtu.be"):
        candidato = caminho[0] if caminho else None
    elif host in _HOSTS_YOUTUBE or host.endswith(tuple("." + h for h in _HOSTS_YOUTUBE)):
        if caminho[:1] == ["watch"]:
            candidato = (parse_qs(partes.query).get("v") or [None])[0]
        elif len(caminho) >= 2 and caminho[0] in ("shorts", "embed", "live", "v", "e"):
            candidato = caminho[1]
    if candidato and _YOUTUBE_ID.match(candidato):
        return candidato
    return None


def chave(url) -> Optional[str]:
    """A identidade do video entre fontes e canais, ou None sem URL.

    YouTube pelo id; o resto pela URL sem o que nao muda o video (esquema,
    `www.`, a barra do fim, o fragmento). Quem chama com um arquivo da pasta
    monta a chave dele (`pasta:`), que depende do conteudo e nao do nome.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    vid = youtube_id(url)
    if vid:
        return f"youtube:{vid}"
    bruto = url.strip()
    if "://" not in bruto:
        bruto = "https://" + bruto
    try:
        partes = urlparse(bruto)
    except ValueError:
        return None
    host = (partes.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    caminho = (partes.path or "").rstrip("/")
    texto = f"{host}{caminho}" + (f"?{partes.query}" if partes.query else "")
    return "url:" + hashlib.sha1(texto.encode("utf-8")).hexdigest()[:20]


def url_do_youtube(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _data(valor) -> Optional[date]:
    """`2024-05-01`, `20240501` (o `upload_date` do yt-dlp), um datetime ou
    uma data."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if not isinstance(valor, str) or not valor.strip():
        return None
    bruto = valor.strip()
    for formato in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(bruto[:10] if "-" in bruto else bruto[:8], formato).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(bruto.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def versao_cc(publicado_em) -> str:
    """"4.0" para video enviado depois da troca do YouTube, "3.0" antes.

    Sem data, a atual: e a que vale para o que se marca hoje.
    """
    dia = _data(publicado_em)
    if dia is None or dia >= TROCA_PARA_A_4:
        return "4.0"
    return "3.0"


def url_da_licenca(licenca: str, publicado_em=None) -> Optional[str]:
    if licenca == "cc-by":
        return f"https://creativecommons.org/licenses/by/{versao_cc(publicado_em)}/"
    if licenca == "dominio-publico":
        return "https://creativecommons.org/publicdomain/mark/1.0/"
    return None


_FRASES = {
    "pt": {
        "credito": "Créditos",
        "de": "de",
        "sem_titulo": "vídeo original",
        "cc": "licença Creative Commons Atribuição {versao}",
        "dp": "domínio público",
        "editado": "Trecho cortado e editado.",
    },
    "en": {
        "credito": "Credit",
        "de": "by",
        "sem_titulo": "original video",
        "cc": "licensed under Creative Commons Attribution {versao}",
        "dp": "public domain",
        "editado": "Excerpt cut and edited.",
    },
    "es": {
        "credito": "Créditos",
        "de": "de",
        "sem_titulo": "video original",
        "cc": "licencia Creative Commons Atribución {versao}",
        "dp": "dominio público",
        "editado": "Fragmento recortado y editado.",
    },
}


def _idioma(idioma: Optional[str]) -> str:
    curto = (idioma or "pt").split("-")[0].lower()
    return curto if curto in _FRASES else "pt"


def credito(origem: Optional[dict], idioma: Optional[str] = None) -> str:
    """A linha de credito, ou "" quando a licenca nao pede.

    Titulo, autor, link do video, a licenca com o link dela, e a frase de que o
    trecho foi editado -- o que a Creative Commons Atribuicao pede. No idioma do
    canal (pt, en, es), porque e a descricao do post que a pessoa le.
    """
    if not isinstance(origem, dict):
        return ""
    licenca = normalizar(origem.get("license"))
    if licenca not in COM_CREDITO:
        return ""
    f = _FRASES[_idioma(idioma)]
    # Sem "#": no Instagram, uma "#palavra" dentro do credito viraria hashtag
    # -- e o credito entra depois do limite de 5 (`publishers.manual`).
    titulo = (origem.get("title") or "").replace("#", "").strip()
    autor = (origem.get("author") or "").replace("#", "").strip()
    url = (origem.get("url") or "").strip()
    obra = f"“{titulo}”" if titulo else f["sem_titulo"]
    partes = [obra]
    if autor:
        partes.append(f"{f['de']} {autor}")
    texto = " ".join(partes)
    if url:
        texto += f" ({url})"
    if licenca == "cc-by":
        versao = versao_cc(origem.get("published_at"))
        texto += ", " + f["cc"].format(versao=versao)
    else:
        texto += ", " + f["dp"]
    link = url_da_licenca(licenca, origem.get("published_at"))
    if link:
        texto += f" ({link})"
    return f"{f['credito']}: {texto}. {f['editado']}"


# --------------------------------------------------------------------------- #
# A origem na pasta do projeto
# --------------------------------------------------------------------------- #

#: `idioma` e o do canal quando o projeto nasceu: e nele que o credito sai.
CAMPOS_DA_ORIGEM = ("url", "key", "title", "author", "author_url", "license",
                    "license_text", "published_at", "declared_by", "found_by",
                    "idioma")


def limpar_origem(origem: dict) -> dict:
    """So os campos conhecidos, em texto, com a licenca normalizada."""
    saida = {}
    for campo in CAMPOS_DA_ORIGEM:
        valor = origem.get(campo) if isinstance(origem, dict) else None
        if valor is None:
            continue
        if isinstance(valor, (datetime, date)):
            valor = valor.isoformat()
        texto = str(valor).strip()
        if texto:
            saida[campo] = texto[:2000]
    saida["license"] = normalizar(saida.get("license"))
    if saida.get("declared_by") not in ("plataforma", "pessoa"):
        saida["declared_by"] = ("pessoa" if saida["license"] in ("propria", "autorizada")
                                else "plataforma")
    if not saida.get("key") and saida.get("url"):
        chave_da_url = chave(saida["url"])
        if chave_da_url:
            saida["key"] = chave_da_url
    return saida


def juntar(da_plataforma: Optional[dict], pedida: Optional[dict]) -> Optional[dict]:
    """A origem de um projeto: o que a PAGINA do video diz, e por baixo o que
    quem pediu acrescentou.

    Os fatos da pagina (titulo, autor, link, data, licenca) vencem: uma receita
    que achou o video ontem nao sabe mais que a pagina de hoje, e um pedido que
    diga "Creative Commons" nao passa por cima de uma pagina que diz licenca
    padrao. Quem pediu completa o que a pagina nao disse -- a licenca
    declarada de um arquivo da pasta, por onde o video chegou, o idioma do
    canal.
    """
    plataforma = limpar_origem(da_plataforma) if isinstance(da_plataforma, dict) else {}
    pedido = limpar_origem(pedida) if isinstance(pedida, dict) else {}
    if not plataforma.get("url") and not plataforma.get("title"):
        plataforma = {}
    if not plataforma and not pedido:
        return None
    saida = dict(pedido)
    for campo in ("url", "key", "title", "author", "author_url", "published_at",
                  "license_text"):
        if plataforma.get(campo):
            saida[campo] = plataforma[campo]
    if plataforma.get("license", "desconhecida") != "desconhecida":
        saida["license"] = plataforma["license"]
        saida["declared_by"] = "plataforma"
    elif pedido.get("license", "desconhecida") == "desconhecida":
        saida["license"] = "desconhecida"
    return limpar_origem(saida)


def gravar_origem(pasta_do_job: str, origem: dict) -> bool:
    """Grava `.origem.json` na pasta do projeto. Nunca levanta."""
    try:
        os.makedirs(pasta_do_job, exist_ok=True)
        caminho = os.path.join(pasta_do_job, ARQUIVO_ORIGEM)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(limpar_origem(origem), f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print(f"⚠️  Nao consegui gravar a origem do projeto em {pasta_do_job}: {e}")
        return False


def ler_origem(pasta_do_job: str) -> Optional[dict]:
    """A origem gravada na pasta, ou None."""
    try:
        with open(os.path.join(pasta_do_job, ARQUIVO_ORIGEM), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return None
    return limpar_origem(dados) if isinstance(dados, dict) else None
