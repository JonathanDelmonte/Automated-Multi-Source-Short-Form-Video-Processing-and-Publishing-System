"""O estilo de criacao do canal (etapa 7.7): o documento que faz um video de IA
sair parecido com o anterior.

Decisao do autor (26-set-2026): "nao coloca estilo 3D no infantil
automaticamente (...) alguma funcionalidade que configura um estilo de criacao,
para que ele nao fuja desse estilo (...) vai ficar salvo". Entao **nada aqui e
deduzido do nicho**: o estilo nasce com os padroes abaixo, e quem usa escolhe
cada campo. Os presets visuais sao atalhos para preencher a descricao, nunca
uma escolha que o motor faz sozinho.

E um documento versionado, como o template da secao 5 (`template.py`):
defaults, validacao, campo desconhecido passa intacto. Stdlib pura, para o CI.

O que faz o segundo video sair reconhecivel (ADR-013):

- **os personagens tem ficha**: nome, descricao e uma imagem de referencia que
  a pessoa gerou e aprovou. Toda cena em que ele aparece leva a imagem ao
  modelo de imagem, com a MESMA descricao em texto;
- **o visual e um texto fixo** que entra em toda imagem, com o que evitar;
- **a voz e o tom** sao os mesmos em todo video;
- **a semente** do estilo e a mesma, de video para video.
"""
from __future__ import annotations

import json
import random
import re
import secrets
from typing import Optional

VERSAO = 1

#: O jeito do video. A frase vai para o roteiro.
FORMATOS = {
    "historia": "uma historinha com comeco, meio e fim, contada por um narrador",
    "fatos": "fatos curiosos e surpreendentes, um atras do outro",
    "explicacao": "uma explicacao simples de um assunto, passo a passo",
    "livre": "o formato que as instrucoes pedirem",
}

#: Atalhos do visual, em ingles porque e a lingua em que o modelo de imagem
#: foi mais treinado. O painel mostra o nome em portugues (`lib/criacao.js`, e
#: ha teste comparando as chaves).
PRESETS_VISUAIS = {
    "livro-infantil": "2D children's book illustration, soft pastel colors, gentle rounded "
                      "shapes, warm lighting",
    "animacao-3d": "3D animated feature film style, soft global illumination, expressive "
                   "characters, vibrant colors",
    "anime": "anime style, clean line art, cel shading, vibrant colors",
    "aquarela": "watercolor painting, soft edges, visible paper texture",
    "quadrinhos": "comic book style, bold ink outlines, flat colors, halftone shading",
    "realista": "photorealistic, cinematic lighting, shallow depth of field",
    "pixel-art": "pixel art, 16-bit video game style, crisp pixels, limited palette",
    "nenhum": "",
}

#: Os presets de legenda do `template.py`, mais "nenhuma".
LEGENDAS = ("karaoke_fill", "karaoke_glow", "karaoke_box", "base_apagada", "limpo",
            "centro", "nenhuma")

#: O limite de referencias do Workers AI (`midia_ia.MAX_REFERENCIAS`): uma cena
#: nunca leva mais personagens que isso, entao o estilo tambem nao.
MAX_PERSONAGENS = 4

DURACAO_MIN, DURACAO_MAX = 20, 90
CENAS_MIN, CENAS_MAX = 3, 14

# O episodio longo (etapa 7.8): a mesma maquina, em video horizontal de varios
# minutos para o YouTube. A duracao e escolhida em cada episodio, e nao no
# estilo: o estilo diz COMO o canal conta (visual, personagens, voz, tom), e
# cabe um Short e um episodio no mesmo canal.
DURACAO_LONGA_MIN, DURACAO_LONGA_MAX = 120, 600
#: Uma imagem a cada ~15 s de fala. O movimento lento segura a cena, e a conta
#: fecha com a cota: ~70 imagens por dia dao um episodio de 10 minutos (40
#: cenas) com folga.
SEGUNDOS_POR_CENA_LONGA = 15
CENAS_LONGAS_MIN, CENAS_LONGAS_MAX = 8, 40
#: Quanta fala vai numa chamada de voz (~2,5 minutos). A narracao de um
#: episodio inteiro numa chamada so e o que o Gemini TTS faz pior -- a voz
#: acelera, muda e corta em falas de varios minutos --, e cada chamada e uma da
#: cota baixa do dia: blocos desse tamanho equilibram as duas coisas.
CARACTERES_POR_BLOCO = 2200
HISTORIA_MAX = 80
RESUMO_MAX = 600
#: Quantos episodios anteriores o roteiro le por inteiro (titulo e resumo). Os
#: mais antigos entram so pela contagem: o pedido nao cresce sem fim.
ANTERIORES_NO_ROTEIRO = 8

LIMITES_DE_TEXTO = {"publico": 200, "tom": 200, "instrucoes": 1200}
NOME_MAX = 40
DESCRICAO_MAX = 400
VISUAL_MAX = 400
EVITAR_MAX = 200
INSTRUCAO_DE_VOZ_MAX = 200


class EstiloInvalido(ValueError):
    """A frase e para a pessoa ler: diz o campo e o que esperava."""


def _texto(valor, nome: str, maximo: int) -> str:
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise EstiloInvalido(f"{nome}: esperava texto")
    limpo = re.sub(r"[ \t]+", " ", valor).strip()
    if len(limpo) > maximo:
        raise EstiloInvalido(f"{nome}: no maximo {maximo} caracteres")
    return limpo


def _inteiro(valor, nome: str, minimo: int, maximo: int) -> int:
    if isinstance(valor, bool):
        raise EstiloInvalido(f"{nome}: esperava numero")
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise EstiloInvalido(f"{nome}: esperava numero")
    if not minimo <= n <= maximo:
        raise EstiloInvalido(f"{nome}: entre {minimo} e {maximo}")
    return n


def novo_id() -> str:
    return secrets.token_hex(4)


def padrao() -> dict:
    """O estilo novo. A semente e sorteada uma vez e fica: e ela que repete o
    jeito das imagens de um video para o outro."""
    return {
        "versao": VERSAO,
        "formato": "historia",
        "publico": "",
        "tom": "",
        "instrucoes": "",
        "duracao_s": 60,
        "cenas": 8,
        "visual": {"preset": "livro-infantil", "descricao": "", "evitar": ""},
        "personagens": [],
        "voz": {"nome": "Kore", "instrucao": ""},
        "legenda": {"preset": "karaoke_fill"},
        "semente": random.randint(1, 2_000_000_000),
    }


def _personagem(p, i: int) -> dict:
    if not isinstance(p, dict):
        raise EstiloInvalido(f"personagem {i + 1}: esperava um objeto")
    nome = _texto(p.get("nome"), f"personagem {i + 1}: nome", NOME_MAX)
    if not nome:
        raise EstiloInvalido(f"personagem {i + 1}: falta o nome")
    pid = p.get("id")
    if not isinstance(pid, str) or not re.fullmatch(r"[0-9a-f]{8}", pid):
        pid = novo_id()
    imagem = p.get("imagem")
    # So o nome do arquivo que o motor mesmo gravou: o documento vem do corpo
    # de uma requisicao, e um caminho aqui viraria leitura de arquivo alheio.
    if not (isinstance(imagem, str) and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{6})?\.png", imagem)):
        imagem = None
    return {**{k: v for k, v in p.items() if k not in ("id", "nome", "descricao", "imagem")},
            "id": pid, "nome": nome,
            "descricao": _texto(p.get("descricao"), f"personagem {nome}: descricao", DESCRICAO_MAX),
            "imagem": imagem}


def normalizar(spec, *, vozes: Optional[tuple] = None) -> dict:
    """O estilo completo e valido, a partir do que veio (parcial, JSON ou
    None). `vozes` e a lista de nomes aceitos (`midia_ia.NOMES_DAS_VOZES`);
    sem ela, qualquer nome passa."""
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            raise EstiloInvalido("o estilo nao e um JSON valido")
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        raise EstiloInvalido("o estilo tem de ser um objeto")
    base = padrao()
    doc = {**base, **{k: v for k, v in spec.items() if k not in base}}
    doc["versao"] = VERSAO

    formato = spec.get("formato", base["formato"])
    if formato not in FORMATOS:
        raise EstiloInvalido(f"formato: um de {', '.join(FORMATOS)}")
    doc["formato"] = formato
    for campo, maximo in LIMITES_DE_TEXTO.items():
        doc[campo] = _texto(spec.get(campo, ""), campo, maximo)
    doc["duracao_s"] = _inteiro(spec.get("duracao_s", base["duracao_s"]), "duracao_s",
                                DURACAO_MIN, DURACAO_MAX)
    doc["cenas"] = _inteiro(spec.get("cenas", base["cenas"]), "cenas", CENAS_MIN, CENAS_MAX)

    visual = spec.get("visual") or {}
    if not isinstance(visual, dict):
        raise EstiloInvalido("visual: esperava um objeto")
    preset = visual.get("preset", base["visual"]["preset"])
    if preset not in PRESETS_VISUAIS:
        raise EstiloInvalido(f"visual.preset: um de {', '.join(PRESETS_VISUAIS)}")
    doc["visual"] = {**{k: v for k, v in visual.items() if k not in ("preset", "descricao", "evitar")},
                     "preset": preset,
                     "descricao": _texto(visual.get("descricao"), "visual.descricao", VISUAL_MAX),
                     "evitar": _texto(visual.get("evitar"), "visual.evitar", EVITAR_MAX)}

    personagens = spec.get("personagens") or []
    if not isinstance(personagens, list):
        raise EstiloInvalido("personagens: esperava uma lista")
    if len(personagens) > MAX_PERSONAGENS:
        raise EstiloInvalido(f"no maximo {MAX_PERSONAGENS} personagens: e o numero de imagens "
                             "de referencia que o modelo aceita numa cena")
    lista = [_personagem(p, i) for i, p in enumerate(personagens)]
    nomes = [p["nome"].casefold() for p in lista]
    if len(set(nomes)) != len(nomes):
        raise EstiloInvalido("dois personagens com o mesmo nome")
    ids = [p["id"] for p in lista]
    if len(set(ids)) != len(ids):
        for p in lista[1:]:
            if ids.count(p["id"]) > 1:
                p["id"] = novo_id()
    doc["personagens"] = lista

    voz = spec.get("voz") or {}
    if not isinstance(voz, dict):
        raise EstiloInvalido("voz: esperava um objeto")
    nome_da_voz = voz.get("nome") or base["voz"]["nome"]
    if vozes is not None and nome_da_voz not in vozes:
        raise EstiloInvalido(f"voz.nome: {nome_da_voz!r} nao e uma das vozes")
    doc["voz"] = {"nome": nome_da_voz,
                  "instrucao": _texto(voz.get("instrucao"), "voz.instrucao", INSTRUCAO_DE_VOZ_MAX)}

    legenda = spec.get("legenda") or {}
    if not isinstance(legenda, dict):
        raise EstiloInvalido("legenda: esperava um objeto")
    preset_da_legenda = legenda.get("preset", base["legenda"]["preset"])
    if preset_da_legenda not in LEGENDAS:
        raise EstiloInvalido(f"legenda.preset: um de {', '.join(LEGENDAS)}")
    doc["legenda"] = {"preset": preset_da_legenda}

    semente = spec.get("semente")
    doc["semente"] = (int(semente) if isinstance(semente, int) and not isinstance(semente, bool)
                      and 0 < semente < 2**31 else base["semente"])
    return doc


def falta_para_criar(doc: dict) -> Optional[str]:
    """O que impede de criar um video com este estilo, ou None. So o que o
    roteiro nao consegue inventar: o visual."""
    visual = doc.get("visual") or {}
    if not visual.get("descricao") and visual.get("preset") in (None, "nenhum"):
        return "Descreva o visual (ou escolha um dos visuais prontos)."
    return None


def personagens_sem_imagem(doc: dict) -> list:
    return [p["nome"] for p in doc.get("personagens") or [] if not p.get("imagem")]


# --------------------------------------------------------------------------- #
# Os textos que vao aos modelos
# --------------------------------------------------------------------------- #

def visual_em_texto(doc: dict) -> str:
    visual = doc.get("visual") or {}
    partes = [PRESETS_VISUAIS.get(visual.get("preset") or "", ""), visual.get("descricao") or ""]
    return ", ".join(p for p in partes if p)


def evitar_em_texto(doc: dict) -> str:
    base = "no text, no letters, no watermark, no logos"
    extra = (doc.get("visual") or {}).get("evitar") or ""
    return f"{base}, {extra}" if extra else base


def prompt_do_personagem(doc: dict, personagem: dict) -> str:
    """A ficha do personagem: corpo inteiro, de frente, fundo liso. E a imagem
    que volta como referencia em toda cena -- fundo limpo para o modelo copiar
    o personagem, e nao o cenario."""
    return (f"Character reference sheet of {personagem['nome']}: {personagem.get('descricao') or ''}. "
            "Full body, facing the viewer, neutral pose, plain white background, centered. "
            f"Style: {visual_em_texto(doc)}. Avoid: {evitar_em_texto(doc)}.")


def prompt_da_cena(doc: dict, cena: dict, personagens_na_cena: list,
                   horizontal: bool = False) -> str:
    """O pedido de imagem de uma cena. Os personagens vao na ordem das
    referencias ("image 0 is ..."), que e como o FLUX.2 as enxerga."""
    partes = [cena.get("imagem") or ""]
    if personagens_na_cena:
        quem = "; ".join(f"image {i} shows {p['nome']} ({p.get('descricao') or 'as in the reference'})"
                         for i, p in enumerate(personagens_na_cena))
        partes.append(f"Keep each character exactly as in the reference images: {quem}.")
    enquadramento = "Horizontal 16:9 composition" if horizontal else "Vertical 9:16 composition"
    partes.append(f"{enquadramento}. Style: {visual_em_texto(doc)}.")
    partes.append(f"Avoid: {evitar_em_texto(doc)}.")
    return " ".join(p for p in partes if p)


def cenas_do_longo(duracao_s) -> int:
    """Quantas cenas (imagens) tem um episodio desta duracao."""
    try:
        segundos = float(duracao_s)
    except (TypeError, ValueError):
        segundos = DURACAO_LONGA_MIN
    return max(CENAS_LONGAS_MIN, min(CENAS_LONGAS_MAX,
                                     int(round(segundos / SEGUNDOS_POR_CENA_LONGA))))


def nome_da_historia(texto) -> str:
    """O nome de uma historia de varios episodios, limpo: uma linha, sem espaco
    sobrando, no teto. Vazio quando nao ha historia."""
    return re.sub(r"\s+", " ", str(texto or "")).strip()[:HISTORIA_MAX].rstrip()


def chave_da_historia(texto) -> str:
    """Duas grafias do mesmo nome ("A Lulu" e "a  lulu") sao a mesma historia."""
    return nome_da_historia(texto).casefold()


_EPISODIO = {"pt": "Episódio", "en": "Episode", "es": "Episodio"}
#: O teto de titulo do YouTube.
TITULO_MAX = 100


def titulo_do_episodio(historia, episodio, titulo: str, idioma: Optional[str] = None) -> str:
    """O titulo do video: "Historia - Episódio N: titulo" quando o episodio e
    de uma historia (quem chega pelo YouTube sabe em que ponto esta), e o
    titulo do roteiro quando e avulso. O titulo do roteiro e o que encolhe
    para caber nos 100 caracteres do YouTube -- a historia e o numero ficam."""
    titulo = re.sub(r"\s+", " ", str(titulo or "")).strip()
    nome = nome_da_historia(historia)
    try:
        numero = int(episodio)
    except (TypeError, ValueError):
        numero = 0
    if not nome or numero < 1:
        return titulo[:TITULO_MAX].rstrip()
    palavra = _EPISODIO.get((idioma or "pt").strip().lower()[:2], _EPISODIO["pt"])
    cabeca = f"{nome} - {palavra} {numero}"
    if not titulo:
        return cabeca[:TITULO_MAX]
    sobra = TITULO_MAX - len(cabeca) - 2
    if sobra < 10:
        return cabeca[:TITULO_MAX]
    return f"{cabeca}: {titulo[:sobra].rstrip()}"


def palavras_por_duracao(segundos: int) -> int:
    """Uma narracao calma fala ~2,3 palavras por segundo (140 por minuto)."""
    return max(30, int(round(segundos * 2.3)))


_IDIOMAS = {"pt": "portugues do Brasil", "pt-br": "portugues do Brasil",
            "pt-pt": "portugues de Portugal", "en": "ingles", "es": "espanhol",
            "fr": "frances", "de": "alemao", "it": "italiano"}


def nome_do_idioma(codigo: Optional[str]) -> str:
    """O idioma do canal ("pt-BR", "en") como o modelo le melhor, por extenso.
    Sem idioma no canal, portugues do Brasil; codigo desconhecido passa como
    veio."""
    c = (codigo or "").strip().lower().replace("_", "-")
    if not c:
        return _IDIOMAS["pt-br"]
    return _IDIOMAS.get(c) or _IDIOMAS.get(c.split("-")[0]) or codigo.strip()


def _linhas_do_estilo(doc: dict) -> list:
    """O que o estilo diz ao roteiro, igual no video curto e no episodio."""
    personagens = doc.get("personagens") or []
    linhas = [f"Formato: {FORMATOS.get(doc.get('formato'), FORMATOS['livre'])}."]
    if doc.get("publico"):
        linhas.append(f"Publico: {doc['publico']}.")
    if doc.get("tom"):
        linhas.append(f"Tom: {doc['tom']}.")
    if doc.get("instrucoes"):
        linhas.append(f"Regras do canal: {doc['instrucoes']}")
    if personagens:
        linhas.append("Personagens fixos (use os nomes exatamente assim):")
        for p in personagens:
            linhas.append(f"- {p['nome']}: {p.get('descricao') or 'sem descricao'}")
    return linhas


_LINHA_DAS_CENAS = (
    "Para cada cena: `fala` e o que o narrador diz (frases curtas, sem indicacao de cena, "
    "sem emoji); `imagem` descreve a imagem da cena EM INGLES, concreta e visual (quem, "
    "fazendo o que, onde, enquadramento), sem texto escrito na imagem; `personagens` lista "
    "os nomes dos personagens fixos que aparecem nela.")


def prompt_do_roteiro(doc: dict, ideia: str, idioma: str = "pt-BR",
                      ja_feitos: Optional[list] = None) -> str:
    """O pedido do roteiro, para a cascata de texto. A resposta segue o schema
    `criar_video.Roteiro`."""
    linhas = [f"Voce escreve roteiros de videos curtos verticais (TikTok, Reels, Shorts) em {idioma}."]
    linhas += _linhas_do_estilo(doc)
    linhas.append(
        f"Duracao: cerca de {doc.get('duracao_s', 60)} segundos de fala, ou seja, umas "
        f"{palavras_por_duracao(doc.get('duracao_s', 60))} palavras de narracao no total, "
        f"divididas em exatamente {doc.get('cenas', 8)} cenas.")
    linhas.append(_LINHA_DAS_CENAS)
    linhas.append(
        "A primeira fala prende a atencao nos primeiros 2 segundos. A ultima fecha a historia.")
    linhas.append(
        "Tambem: `titulo` (ate 90 caracteres, no idioma do video), `descricao` (1 ou 2 "
        "frases) e `hashtags` (3 a 5, sem espaco).")
    if ja_feitos:
        lista = "; ".join(t for t in ja_feitos[-30:] if t)
        linhas.append(f"Nao repita estes temas, que o canal ja fez: {lista}.")
    linhas.append(f"Ideia deste video: {ideia or 'invente uma nova, no estilo do canal'}.")
    return "\n".join(linhas)


def prompt_do_episodio(doc: dict, ideia: str, idioma: str, duracao_s: int, cenas: int,
                       historia: Optional[dict] = None,
                       ja_feitos: Optional[list] = None) -> str:
    """O pedido do roteiro de um episodio longo (7.8). Alem das cenas, pede os
    `capitulos` (as marcas na barra do YouTube) e o `resumo`, que e o que o
    proximo episodio da mesma historia le para continuar de onde este parou.

    `historia` e `{"nome", "episodio", "anteriores": [{"episodio", "titulo",
    "resumo"}]}`, ou None para um episodio avulso."""
    minutos = max(1, int(round(duracao_s / 60)))
    palavras = palavras_por_duracao(duracao_s)
    linhas = [f"Voce escreve roteiros de episodios de video longo e horizontal para o YouTube, "
              f"em {idioma}."]
    linhas += _linhas_do_estilo(doc)
    linhas.append(
        f"Duracao: cerca de {minutos} minutos de fala, ou seja, umas {palavras} palavras de "
        f"narracao no total, divididas em exatamente {cenas} cenas de tamanho parecido (umas "
        f"{max(10, palavras // max(1, cenas))} palavras cada).")
    linhas.append(_LINHA_DAS_CENAS + " A `imagem` tem no maximo 40 palavras.")
    linhas.append(
        "O comeco prende a atencao e diz do que o episodio trata; o meio desenvolve com calma, "
        "sem repetir; o fim fecha o episodio.")
    linhas.append(
        "`capitulos`: de 3 a 8 partes do episodio, na ordem, cada uma com `titulo` (ate 60 "
        "caracteres, no idioma do video) e `cena` (o numero da cena em que a parte comeca, "
        "contando da 1; a primeira comeca na cena 1). Cada parte com varias cenas.")
    linhas.append(
        "`resumo`: 2 a 4 frases com o que aconteceu neste episodio, para quem for escrever o "
        "proximo.")
    linhas.append(
        "Tambem: `titulo` (ate 90 caracteres, no idioma do video), `descricao` (2 a 4 frases) "
        "e `hashtags` (3 a 5, sem espaco).")
    anteriores = [a for a in (historia or {}).get("anteriores") or [] if isinstance(a, dict)]
    if historia and historia.get("nome"):
        numero = int(historia.get("episodio") or len(anteriores) + 1)
        if anteriores:
            linhas.append(f"Esta e a historia \"{historia['nome']}\". Episodios anteriores, do "
                          "primeiro ao mais recente:")
            lidos = anteriores[-ANTERIORES_NO_ROTEIRO:]
            fora = len(anteriores) - len(lidos)
            if fora:
                linhas.append(f"(antes destes, mais {fora} episodio(s))")
            for a in lidos:
                resumo = a.get("resumo") or "sem resumo"
                linhas.append(f"- Episodio {a.get('episodio')}, \"{a.get('titulo') or ''}\": "
                              f"{resumo}")
            linhas.append(
                f"Este e o episodio {numero}: continue de onde o anterior parou, com os mesmos "
                "personagens e o que ja aconteceu. Nao reconte tudo -- no maximo uma frase de "
                "lembranca no comeco -- e nao repita o que ja aconteceu.")
        else:
            linhas.append(
                f"Este e o episodio 1 da historia \"{historia['nome']}\": apresente o mundo e os "
                "personagens, e termine deixando vontade de ver o proximo.")
    if ja_feitos and not anteriores:
        lista = "; ".join(t for t in ja_feitos[-30:] if t)
        linhas.append(f"Nao repita estes temas, que o canal ja fez: {lista}.")
    padrao = "continue a historia" if anteriores else "invente uma nova, no estilo do canal"
    linhas.append(f"Ideia deste episodio: {ideia or padrao}.")
    return "\n".join(linhas)


def _texto_de_uma_linha(valor, maximo: int) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:maximo]


def ler_roteiro(bruto: dict, doc: dict, alvo: Optional[int] = None,
                longo: bool = False) -> dict:
    """O roteiro que a cascata devolveu, conferido: cenas com fala, os nomes de
    personagem trocados pelos ids do estilo (nome desconhecido sai), e o numero
    de cenas dentro do pedido (`alvo`; sem ele, o do estilo). Levanta
    `EstiloInvalido` se nao ha o que narrar.

    No episodio longo (`longo`), guarda tambem os `capitulos` (`[{"cena",
    "titulo"}]`, a cena contada do 0) e o `resumo`. O capitulo e marcado na
    cena ANTES de juntar as cenas a mais, para que a marca ande junto com a
    cena em que ele comeca."""
    import capitulos as _capitulos
    if not isinstance(bruto, dict):
        raise EstiloInvalido("o roteiro veio vazio")
    por_nome = {p["nome"].casefold(): p["id"] for p in doc.get("personagens") or []}
    marcas = {}
    if longo:
        for c in bruto.get("capitulos") or []:
            if not isinstance(c, dict):
                continue
            try:
                numero = int(c.get("cena"))
            except (TypeError, ValueError):
                continue
            nome = _capitulos.titulo(c.get("titulo"))
            if nome and numero not in marcas:
                marcas[numero] = nome
    cenas = []
    pendente = None
    for numero, c in enumerate(bruto.get("cenas") or [], start=1):
        if not isinstance(c, dict):
            pendente = pendente or marcas.get(numero)
            continue
        fala = re.sub(r"\s+", " ", str(c.get("fala") or "")).strip()
        if not fala:
            # A cena sem fala sai; o capitulo que comecava nela passa a seguinte.
            pendente = pendente or marcas.get(numero)
            continue
        ids = []
        for nome in c.get("personagens") or []:
            pid = por_nome.get(str(nome).strip().casefold())
            if pid and pid not in ids:
                ids.append(pid)
        cena = {"fala": fala, "imagem": str(c.get("imagem") or "").strip()[:900],
                "personagens": ids[:MAX_PERSONAGENS]}
        marca = pendente or marcas.get(numero)
        pendente = None
        if longo and marca:
            cena["capitulo"] = marca
        cenas.append(cena)
    if not cenas:
        raise EstiloInvalido("o roteiro veio sem nenhuma fala")
    cenas = juntar_cenas(cenas, int(alvo or doc.get("cenas") or CENAS_MAX))
    hashtags = []
    for h in bruto.get("hashtags") or []:
        tag = re.sub(r"[^\w]", "", str(h).lstrip("#"))
        if tag and tag.casefold() not in {x.casefold() for x in hashtags}:
            hashtags.append(tag)
    titulo = _texto_de_uma_linha(bruto.get("titulo"), 100)
    roteiro = {"titulo": titulo or cenas[0]["fala"][:90],
               "descricao": _texto_de_uma_linha(bruto.get("descricao"), 500 if not longo else 1500),
               "hashtags": hashtags[:5],
               "cenas": cenas}
    if longo:
        # O primeiro capitulo comeca no comeco do video (e o que o YouTube pede):
        # se o roteiro o marcou mais adiante, a marca volta para a cena 1.
        marcadas = [k for k, c in enumerate(cenas) if c.get("capitulo")]
        if marcadas and marcadas[0] != 0:
            cenas[0]["capitulo"] = cenas[marcadas[0]].pop("capitulo")
        roteiro["capitulos"] = [{"cena": k, "titulo": c.pop("capitulo")}
                                for k, c in enumerate(cenas) if c.get("capitulo")]
        roteiro["resumo"] = _texto_de_uma_linha(bruto.get("resumo"), RESUMO_MAX)
    return roteiro


def juntar_cenas(cenas: list, alvo: int) -> list:
    """Cenas demais viram o numero pedido juntando as vizinhas mais curtas.

    Cada cena e uma imagem da cota do dia, e a tela conferiu a cota pelo numero
    do estilo: o modelo que escreve 11 cenas quando se pediram 8 nao pode
    gastar 3 imagens a mais. Cortar as ultimas perderia o fim da historia;
    juntar mantem toda a fala, com a imagem da primeira das duas. A marca de
    capitulo (episodio longo) fica com a primeira das duas; se so a segunda
    tinha, ela passa a comecar na primeira."""
    cenas = [dict(c) for c in cenas]
    alvo = max(1, min(int(alvo), max(CENAS_MAX, CENAS_LONGAS_MAX)))
    while len(cenas) > alvo:
        # Nao junta duas cenas que abrem capitulos diferentes, enquanto houver
        # outro par: o capitulo de uma delas sumiria.
        pares = [k for k in range(len(cenas) - 1)
                 if not (cenas[k].get("capitulo") and cenas[k + 1].get("capitulo"))]
        i = min(pares or range(len(cenas) - 1),
                key=lambda k: len(cenas[k]["fala"]) + len(cenas[k + 1]["fala"]))
        a, b = cenas[i], cenas.pop(i + 1)
        a["fala"] = f"{a['fala']} {b['fala']}"
        a["personagens"] = (a["personagens"] + [p for p in b["personagens"]
                                                if p not in a["personagens"]])[:MAX_PERSONAGENS]
        a["imagem"] = a["imagem"] or b["imagem"]
        if not a.get("capitulo") and b.get("capitulo"):
            a["capitulo"] = b["capitulo"]
    return cenas


def narracao(roteiro: dict) -> str:
    """O texto que a voz le: as falas, uma por paragrafo (a pausa entre cenas)."""
    return "\n\n".join(c["fala"] for c in roteiro.get("cenas") or [])


def blocos_de_narracao(roteiro: dict, maximo: Optional[int] = None) -> list:
    """As cenas agrupadas em blocos de fala (listas de indices), um bloco por
    chamada de voz.

    O bloco nunca parte uma cena: a pausa entre dois blocos cai entre duas
    cenas, onde ja haveria uma. Os blocos saem de tamanho parecido (um ultimo
    bloco de uma frase seria uma chamada da cota do dia por quase nada), e uma
    cena maior que o teto vai sozinha."""
    falas = [c.get("fala") or "" for c in roteiro.get("cenas") or []]
    if not falas:
        return []
    maximo = max(200, int(maximo or CARACTERES_POR_BLOCO))
    total = sum(len(f) for f in falas) + 2 * (len(falas) - 1)
    quantos = max(1, -(-total // maximo))
    alvo = total / quantos
    blocos, atual, tamanho = [], [], 0
    for k, fala in enumerate(falas):
        acrescimo = len(fala) + (2 if atual else 0)
        if atual and tamanho + acrescimo > maximo:
            blocos.append(atual)
            atual, tamanho, acrescimo = [], 0, len(fala)
        atual.append(k)
        tamanho += acrescimo
        if tamanho >= alvo and len(blocos) < quantos - 1:
            blocos.append(atual)
            atual, tamanho = [], 0
    if atual:
        blocos.append(atual)
    return blocos


def texto_do_bloco(roteiro: dict, bloco: list) -> str:
    cenas = roteiro.get("cenas") or []
    return "\n\n".join(cenas[k]["fala"] for k in bloco if 0 <= k < len(cenas))
