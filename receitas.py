"""A receita de um canal e os ajustes dele -- os documentos da etapa 7.5.

"Cada canal tem uma receita (de onde vem os videos, como editar, quando postar,
se espera aprovacao), e o motor a cumpre sem ninguem olhar"
(docs/PLANO-DA-PLATAFORMA.md). Dois documentos, os dois validados aqui:

- **os ajustes do canal** (`channel_settings`): a agenda -- as janelas do dia e
  quantos posts por dia -- e o "feito para criancas". Sao do CANAL, e nao da
  receita: valem para todo conteudo dele, feito pela automacao ou a mao, e a
  trava do agendador trabalha por conta, entao duas receitas no mesmo canal
  (cortes e, na 7.7, IA) postariam pelas mesmas janelas de qualquer jeito;
- **a receita** (`recipes`): de onde vem o video (busca por tema, links, live
  da Twitch ou a pasta do canal) e como editar.

Se o canal espera aprovacao ja era escolha do canal desde a 7.1
(`channels.requires_approval`), e continua sendo: a receita so a le.

Documentos e nao colunas, como o template da secao 5: campo novo de receita nao
vira migracao. Stdlib pura (o `sources` tambem e), entao o CI exercita as
regras sem banco.
"""
from __future__ import annotations

import copy
import re
import unicodedata
from typing import Optional

#: O que o painel oferece e o motor aceita. `serie` (7.6) e `ia` (7.7) ja
#: estao no CHECK do banco; aqui, so o que existe.
TIPOS_ACEITOS = ("cortes",)
FONTES = ("busca", "links", "twitch", "pasta")
#: A duracao do video que a busca procura. `media` e 4 a 20 minutos e `longa`,
#: mais de 20 -- as faixas da propria busca do YouTube. Curta (menos de 4 min)
#: nao entra: e pouco material para cortar.
DURACOES_DA_BUSCA = ("longa", "media", "qualquer")
LAYOUTS = ("auto", "split", "screencast", "none")

MAX_LINKS = 50
MAX_TEMA = 120
MAX_JANELAS = 8
MAX_POR_DIA = 20
MAX_VIDEOS_POR_DIA = 10

#: Palavras que marcam um nicho infantil, sem acento e em minuscula. O nicho e
#: texto livre (o painel so sugere), entao a conferencia e por palavra.
_NICHO_INFANTIL = ("infantil", "infantis", "crianca", "criancas", "kids", "kid",
                   "bebe", "bebes", "desenho", "desenhos", "ninar")

_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class ReceitaInvalida(ValueError):
    """Pedido recusado por uma regra; o texto vai para a tela como esta."""


# --------------------------------------------------------------------------- #
# Os ajustes do canal
# --------------------------------------------------------------------------- #

AJUSTES_PADRAO = {
    # `None` e "o padrao da instalacao" (SCHEDULE_WINDOWS e SCHEDULE_PER_DAY):
    # um canal que nunca mexeu na agenda acompanha a instalacao.
    "agenda": {"janelas": None, "por_dia": None},
    # `None` e "decida pelo nicho" (`feito_para_criancas`).
    "feito_para_criancas": None,
}


def _inteiro(valor, campo: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor != int(valor):
        raise ReceitaInvalida(f"{campo} tem de ser um número inteiro")
    valor = int(valor)
    if not minimo <= valor <= maximo:
        raise ReceitaInvalida(f"{campo} tem de ficar entre {minimo} e {maximo}")
    return valor


def normalizar_ajustes(dados: Optional[dict], base: Optional[dict] = None) -> dict:
    """Os ajustes completos: `base` (o que ja estava) com `dados` por cima.

    Por secao, como o template: mandar so `{"agenda": {"por_dia": 2}}` mantem as
    janelas. Levanta `ReceitaInvalida` com o motivo.
    """
    saida = copy.deepcopy(AJUSTES_PADRAO)
    for origem in (base, dados):
        if origem is None:
            continue
        if not isinstance(origem, dict):
            raise ReceitaInvalida("os ajustes do canal têm de ser um objeto")
        agenda = origem.get("agenda")
        if agenda is not None:
            if not isinstance(agenda, dict):
                raise ReceitaInvalida("agenda tem de ser um objeto")
            if "janelas" in agenda:
                saida["agenda"]["janelas"] = _janelas(agenda["janelas"])
            if "por_dia" in agenda:
                por_dia = agenda["por_dia"]
                saida["agenda"]["por_dia"] = (
                    None if por_dia is None
                    else _inteiro(por_dia, "por_dia", 1, MAX_POR_DIA))
        if "feito_para_criancas" in origem:
            valor = origem["feito_para_criancas"]
            if valor is not None and not isinstance(valor, bool):
                raise ReceitaInvalida("feito_para_criancas tem de ser true, false ou null")
            saida["feito_para_criancas"] = valor
    return saida


def ajustes_gravados(documento) -> dict:
    """Os ajustes como estao no banco, para LER. Um documento torto (gravado
    por uma versao futura, ou a mao) nao derruba a lista de canais nem o
    agendador: vale o padrao, com uma linha no log."""
    try:
        return normalizar_ajustes(documento or None)
    except ReceitaInvalida as e:
        print(f"⚠️  Ajustes do canal ilegiveis ({e}); usando o padrao.")
        return copy.deepcopy(AJUSTES_PADRAO)


def _janelas(valor) -> Optional[list]:
    if valor is None:
        return None
    if not isinstance(valor, list) or not valor:
        raise ReceitaInvalida("janelas têm de ser uma lista de horas, como [11, 15, 19]")
    horas = sorted({_inteiro(h, "cada janela", 0, 23) for h in valor})
    if len(horas) > MAX_JANELAS:
        raise ReceitaInvalida(f"no máximo {MAX_JANELAS} janelas por dia")
    return horas


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn").lower()


def nicho_infantil(nicho: Optional[str]) -> bool:
    if not isinstance(nicho, str):
        return False
    palavras = set(re.findall(r"[a-z]+", _sem_acento(nicho)))
    return bool(palavras & set(_NICHO_INFANTIL))


def feito_para_criancas(ajustes: Optional[dict], nicho: Optional[str]) -> dict:
    """`{"valor": bool, "origem": "ajuste" | "nicho"}`.

    **E marcado sozinho no canal infantil** (o plano: exigencia do YouTube pela
    COPPA, a lei americana, e nao opcional). O nicho e texto livre, entao
    "sozinho" e: sem escolha explicita, vale o que o nome do nicho diz. A
    escolha explicita vence -- e a tela mostra de onde veio o valor, para que
    ninguem descubra depois do post.
    """
    explicito = (ajustes or {}).get("feito_para_criancas")
    if isinstance(explicito, bool):
        return {"valor": explicito, "origem": "ajuste"}
    return {"valor": nicho_infantil(nicho), "origem": "nicho"}


def agenda_efetiva(ajustes: Optional[dict], janelas_padrao, por_dia_padrao: int) -> dict:
    """As janelas e o por-dia que valem para o canal: o dele, ou o da
    instalacao onde ele nao escolheu."""
    agenda = (ajustes or {}).get("agenda") or {}
    janelas = agenda.get("janelas") or list(janelas_padrao)
    por_dia = agenda.get("por_dia") or int(por_dia_padrao)
    return {"janelas": list(janelas), "por_dia": int(por_dia),
            "do_canal": bool(agenda.get("janelas") or agenda.get("por_dia"))}


# --------------------------------------------------------------------------- #
# A receita
# --------------------------------------------------------------------------- #

PADRAO = {
    "fonte": {
        "tipo": "busca",
        # busca: o tema e a duracao do video procurado.
        "tema": "",
        "duracao": "longa",
        # links: videos, playlists ou canais, um por linha.
        "links": [],
        # twitch: o canal (twitch.tv/<canal>); cada bloco da live vira um corte.
        "twitch": "",
    },
    "edicao": {
        "cortes_por_video": 5,
        "duracao_min": 20,
        "duracao_max": 60,
        "layout": "auto",
        "legenda": True,
        "gancho": True,
        # O template de legenda salvo (`templates.id`); None = o padrao.
        "template_id": None,
    },
    "ritmo": {
        # Quantos videos de fonte a receita corta por dia, no maximo. O que
        # manda de verdade e o estoque: com cortes suficientes para os
        # proximos dias, ela nao corta mais nada.
        "videos_por_dia": 1,
    },
    # Quando quem usa confirmou ter os direitos (ISO-8601). A busca so aceita
    # video com licenca livre CONFERIDA; links, live e pasta dependem dessa
    # confirmacao, como o "confirmo" do Criar.
    "direitos": None,
}


def _texto(valor, campo: str, limite: int, vazio_ok: bool = True) -> str:
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise ReceitaInvalida(f"{campo} tem de ser texto")
    limpo = valor.strip()
    if _CONTROLE.search(limpo):
        raise ReceitaInvalida(f"{campo} tem caractere de controle")
    if len(limpo) > limite:
        raise ReceitaInvalida(f"{campo} passa de {limite} caracteres")
    if not limpo and not vazio_ok:
        raise ReceitaInvalida(f"{campo} não pode ficar vazio")
    return limpo


def _links(valor) -> list:
    if valor is None:
        return []
    if isinstance(valor, str):
        valor = [l for l in re.split(r"[\s,]+", valor) if l]
    if not isinstance(valor, list):
        raise ReceitaInvalida("links têm de ser uma lista")
    import sources

    limpos = []
    for bruto in valor:
        link = _texto(bruto, "cada link", 2000)
        if not link:
            continue
        if not sources.is_http_url(link):
            raise ReceitaInvalida(f"{link[:80]} não é um endereço (comece com https://)")
        adapter = sources.resolve(link)
        try:
            adapter.assert_fetchable(link)
        except sources.SourceNotReady as e:
            raise ReceitaInvalida(str(e))
        if adapter.id == "twitch-live":
            raise ReceitaInvalida(
                f"{link[:80]} é uma live da Twitch: escolha a fonte \"live da Twitch\"")
        if link not in limpos:
            limpos.append(link)
    if len(limpos) > MAX_LINKS:
        raise ReceitaInvalida(f"no máximo {MAX_LINKS} links por receita")
    return limpos


def _twitch(valor) -> str:
    canal = _texto(valor, "o canal da Twitch", 300)
    if not canal:
        return ""
    if "://" not in canal:
        canal = "https://" + canal
    from sources import twitch

    if twitch.classify(canal) != "live":
        raise ReceitaInvalida("use o endereço do canal na Twitch, como twitch.tv/nome")
    return canal


def normalizar(spec: Optional[dict], base: Optional[dict] = None) -> dict:
    """A receita completa: `base` com `spec` por cima, secao por secao.

    Campo fora do documento passa intacto (como no template): documento
    versionado que recusa campo novo transforma todo campo novo em migracao.
    """
    saida = copy.deepcopy(PADRAO)
    for origem in (base, spec):
        if origem is None:
            continue
        if not isinstance(origem, dict):
            raise ReceitaInvalida("a receita tem de ser um objeto")
        for secao, valor in origem.items():
            if secao in ("fonte", "edicao", "ritmo") and valor is not None:
                if not isinstance(valor, dict):
                    raise ReceitaInvalida(f"{secao} tem de ser um objeto")
                saida[secao].update(valor)
            elif secao == "direitos":
                saida["direitos"] = valor if isinstance(valor, str) and valor else None
            elif secao not in ("fonte", "edicao", "ritmo"):
                saida[secao] = copy.deepcopy(valor)

    fonte = saida["fonte"]
    if fonte.get("tipo") not in FONTES:
        raise ReceitaInvalida("a fonte tem de ser busca, links, twitch ou pasta")
    fonte["tema"] = _texto(fonte.get("tema"), "o tema da busca", MAX_TEMA)
    if fonte.get("duracao") not in DURACOES_DA_BUSCA:
        raise ReceitaInvalida("a duração da busca tem de ser longa, média ou qualquer")
    fonte["links"] = _links(fonte.get("links"))
    fonte["twitch"] = _twitch(fonte.get("twitch"))

    edicao = saida["edicao"]
    edicao["cortes_por_video"] = _inteiro(edicao.get("cortes_por_video"), "cortes por vídeo", 1, 15)
    edicao["duracao_min"] = _inteiro(edicao.get("duracao_min"), "a duração mínima do corte", 5, 175)
    edicao["duracao_max"] = _inteiro(edicao.get("duracao_max"), "a duração máxima do corte", 10, 180)
    if edicao["duracao_max"] < edicao["duracao_min"] + 5:
        raise ReceitaInvalida("a duração máxima tem de passar a mínima em pelo menos 5 s")
    if edicao.get("layout") not in LAYOUTS:
        raise ReceitaInvalida("layout tem de ser auto, split, screencast ou none")
    for chave in ("legenda", "gancho"):
        if not isinstance(edicao.get(chave), bool):
            raise ReceitaInvalida(f"{chave} tem de ser true ou false")
    template_id = edicao.get("template_id")
    if template_id in ("", None):
        edicao["template_id"] = None
    elif not isinstance(template_id, str) or not _UUID.match(template_id):
        raise ReceitaInvalida("template_id não é o id de um template")

    ritmo = saida["ritmo"]
    ritmo["videos_por_dia"] = _inteiro(ritmo.get("videos_por_dia"), "vídeos por dia",
                                       1, MAX_VIDEOS_POR_DIA)
    return saida


def precisa_de_direitos(spec: dict) -> bool:
    """A busca confere a licenca sozinha; o resto depende de quem usa dizer
    que tem os direitos."""
    return (spec.get("fonte") or {}).get("tipo") != "busca"


def mesma_fonte(a: Optional[dict], b: Optional[dict]) -> bool:
    """Se a fonte mudou -- e a confirmacao de direitos era sobre a outra."""
    fa = (a or {}).get("fonte") or {}
    fb = (b or {}).get("fonte") or {}
    tipo = fa.get("tipo")
    if tipo != fb.get("tipo"):
        return False
    if tipo == "links":
        return list(fa.get("links") or []) == list(fb.get("links") or [])
    if tipo == "twitch":
        return (fa.get("twitch") or "") == (fb.get("twitch") or "")
    return True


def pronta(spec: dict) -> Optional[str]:
    """None quando a receita pode ser ligada; senao, o que falta, em frase."""
    fonte = spec.get("fonte") or {}
    tipo = fonte.get("tipo")
    if tipo == "busca" and not fonte.get("tema"):
        return "falta o tema da busca"
    if tipo == "links" and not fonte.get("links"):
        return "falta pelo menos um link"
    if tipo == "twitch" and not fonte.get("twitch"):
        return "falta o canal da Twitch"
    if precisa_de_direitos(spec) and not spec.get("direitos"):
        return "falta confirmar que você tem os direitos sobre esses vídeos"
    return None
