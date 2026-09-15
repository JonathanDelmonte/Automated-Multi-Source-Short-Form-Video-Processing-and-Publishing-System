"""O documento de template da secao 5 (Fase 2, bloco 2.1).

"Nao e um editor de timeline. E **um documento de configuracao versionado** que
o renderizador le." Este modulo e esse documento: defaults, validacao, os
presets de legenda, e a traducao dos campos para o que o caminho de queima ja
sabe receber.

**O que a Fase 2 encontrou pronto, e que muda o ADR-002.** Aquela ADR decidiu
trazer do `clippyme` duas coisas: o compositor de segunda passada -- "a melhor
ideia de arquitetura dos quatro" -- e seis presets de legenda. Lendo o codigo:

- **A segunda passada ja existe aqui.** `/api/subtitle` le o clipe JA
  RENDERIZADO e requeima a legenda sobre ele, com a transcricao vinda do
  metadata; `/api/hook` faz o mesmo com a sobreposicao de texto; o `recut`
  recorta sem reenquadrar. Trocar de legenda nunca reprocessou o video neste
  fork.
- **Os seis presets sao configuracao, nao codigo.** O `subtitles.generate_ass`
  ja expoe cor, contorno, realce, opacidade da base, caixa, efeito, caixa alta,
  alinhamento e janela de palavras. Um preset e uma combinacao desses botoes.

Entao o que faltava nao era motor: era **o documento**. Os botoes existiam
espalhados por parametros de endpoint, sem nome, sem versao e sem um lugar onde
"o meu estilo" pudesse ser escrito uma vez e reusado.

Este modulo e stdlib pura de proposito: o CI nao instala ffmpeg nem torch, e as
regras que valem a pena testar sao todas aqui.
"""
from __future__ import annotations

import copy

#: A altura virtual do ASS. `subtitles.generate_ass` escreve `PlayResY: 288`, e
#: toda margem vertical e expressa nessa escala -- e por isso que a conversao de
#: `safeArea` mora aqui e nao no chamador.
PLAY_RES_Y = 288


class TemplateInvalido(ValueError):
    """O documento tem um campo que o renderizador nao saberia obedecer."""


# --------------------------------------------------------------------------- #
# Presets de legenda
# --------------------------------------------------------------------------- #
#
# Cada um e um conjunto de kwargs de `subtitles.generate_ass`. O primeiro nao
# foi inventado aqui: e o `subtitles.AUTO_CAPTION_STYLE`, escolhido em
# 25-jul-2026 renderizando quatro candidatos num clipe real. O amarelo tem
# motivo -- e a cor que quase nunca aparece em imagem filmada, entao a palavra
# ativa se le na hora sobre qualquer fundo.
PRESETS_DE_LEGENDA = {
    "karaoke_fill": {
        "font_name": "Anton", "fontsize": 44, "font_color": "#FFFFFF",
        "highlight_color": "#FFE500", "border_color": "#000000", "border_width": 4,
        "effect": "pop", "base_opacity": 1.0, "uppercase": True,
        "alignment": "bottom", "max_chars": 16, "max_duration": 1.4,
    },
    "karaoke_glow": {
        "font_name": "Anton", "fontsize": 44, "font_color": "#FFFFFF",
        "highlight_color": "#00E5FF", "border_color": "#000000", "border_width": 3,
        "effect": "glow", "base_opacity": 1.0, "uppercase": True,
        "alignment": "bottom", "max_chars": 16, "max_duration": 1.4,
    },
    "karaoke_box": {
        "font_name": "Anton", "fontsize": 42, "font_color": "#FFFFFF",
        "highlight_color": "#FF2D55", "border_color": "#000000", "border_width": 6,
        "effect": "box", "base_opacity": 1.0, "uppercase": True,
        "alignment": "bottom", "max_chars": 14, "max_duration": 1.4,
    },
    # A base apagada e o visual de legendador moderno. Testou PIOR sobre cena
    # clara (por isso nao e o padrao), e continua sendo o melhor sobre material
    # escuro e uniforme.
    "base_apagada": {
        "font_name": "Anton", "fontsize": 46, "font_color": "#FFFFFF",
        "highlight_color": "#FFE500", "border_color": "#000000", "border_width": 4,
        "effect": "none", "base_opacity": 0.4, "uppercase": True,
        "alignment": "bottom", "max_chars": 18, "max_duration": 1.6,
    },
    # Sem karaoke: bloco inteiro de uma vez, como legenda de filme. Para
    # conteudo em que a fala corrida importa mais que o ritmo.
    "limpo": {
        "font_name": "Verdana", "fontsize": 38, "font_color": "#FFFFFF",
        "highlight_color": "#FFFFFF", "border_color": "#000000", "border_width": 3,
        "effect": "none", "base_opacity": 1.0, "uppercase": False,
        "alignment": "bottom", "max_chars": 26, "max_duration": 2.4,
    },
    # No meio do quadro: a unica posicao que nao cobre ninguem num layout SPLIT,
    # onde os dois falantes ocupam as metades de cima e de baixo.
    "centro": {
        "font_name": "Anton", "fontsize": 46, "font_color": "#FFFFFF",
        "highlight_color": "#FFE500", "border_color": "#000000", "border_width": 5,
        "effect": "pop", "base_opacity": 1.0, "uppercase": True,
        "alignment": "middle", "max_chars": 14, "max_duration": 1.3,
    },
}

#: O documento da secao 5, inteiro. Um spec parcial e completado com isto, entao
#: `{"captions": {"preset": "limpo"}}` e um template valido.
PADRAO = {
    "name": "Padrao Cortes",
    "aspect": "9:16",
    "hook": {"mode": "text_punch", "durationMs": 1200, "font": "Anton",
             "from": "clip.title"},
    "captions": {"preset": "karaoke_fill"},
    "overlays": [],
    "audio": {"bgm": None, "gainDb": -22, "ducking": "sidechain"},
    "cuts": {"removeSilence": False, "thresholdDb": -35, "maxGapMs": 400},
    # 12% em cima e o nome do perfil; 18% embaixo sao legenda e botoes do app.
    # Nao e enfeite: legenda fora dessa faixa fica ilegivel NO APP mesmo com o
    # arquivo exportado parecendo certo, e a secao 5 chama isso de "o erro n. 1
    # de quem automatiza corte". O `subtitles.SAFE_MARGIN_V` de hoje sao 43 em
    # PlayResY=288, ou ~15%, numero que ja veio de uma falha observada (25 era
    # 8.7% e a legenda saia por baixo da interface do TikTok). Os 18% da secao 5
    # sao mais folga na mesma direcao.
    "safeArea": {"topPct": 12, "bottomPct": 18},
}

_MODOS_DE_HOOK = ("text_punch", "none")
_ANCORAS = ("top-left", "top-right", "bottom-left", "bottom-right", "full",
            "center")


def _numero(valor, nome, minimo=None, maximo=None):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise TemplateInvalido(f"{nome}: esperava numero, veio {valor!r}")
    if minimo is not None and valor < minimo:
        raise TemplateInvalido(f"{nome}: {valor} e menor que o minimo {minimo}")
    if maximo is not None and valor > maximo:
        raise TemplateInvalido(f"{nome}: {valor} e maior que o maximo {maximo}")
    return valor


def _funde(base: dict, por_cima: dict) -> dict:
    """Merge raso por secao: `{"captions": {"sizePt": 90}}` mantem o resto do
    preset em vez de zerar a secao inteira."""
    saida = copy.deepcopy(base)
    for chave, valor in (por_cima or {}).items():
        if isinstance(valor, dict) and isinstance(saida.get(chave), dict):
            saida[chave] = {**saida[chave], **valor}
        else:
            saida[chave] = copy.deepcopy(valor)
    return saida


def normalizar(spec: dict | None) -> dict:
    """Documento completo e valido, ou `TemplateInvalido`.

    Campos desconhecidos passam intactos de proposito: a secao 5 chama isto de
    documento versionado, e recusar o que ainda nao se le transformaria todo
    campo novo em migracao.
    """
    if spec is None:
        return copy.deepcopy(PADRAO)
    if not isinstance(spec, dict):
        raise TemplateInvalido(f"o template tem que ser um objeto, veio {type(spec).__name__}")

    doc = _funde(PADRAO, spec)

    if not str(doc.get("name") or "").strip():
        raise TemplateInvalido("name: nao pode ser vazio")

    legendas = doc.get("captions") or {}
    preset = legendas.get("preset", "karaoke_fill")
    if preset not in PRESETS_DE_LEGENDA:
        conhecidos = ", ".join(sorted(PRESETS_DE_LEGENDA))
        raise TemplateInvalido(f"captions.preset '{preset}' nao existe. Conhecidos: {conhecidos}")

    area = doc.get("safeArea") or {}
    topo = _numero(area.get("topPct", 12), "safeArea.topPct", 0, 45)
    base = _numero(area.get("bottomPct", 18), "safeArea.bottomPct", 0, 45)
    # Guarda-corpo, nao medicao: 45+45 nao "come o quadro inteiro", mas deixa
    # 10% de altura para a legenda, que num 1920 sao 192px -- menos que duas
    # linhas de Anton no tamanho padrao. Um documento que pede isso esta errado
    # e o erro so apareceria no clipe pronto.
    if topo + base > 80:
        raise TemplateInvalido(
            f"safeArea: topo ({topo}%) e base ({base}%) deixam so "
            f"{100 - topo - base}% do quadro para a legenda")

    gancho = doc.get("hook") or {}
    if gancho.get("mode") not in _MODOS_DE_HOOK:
        raise TemplateInvalido(
            f"hook.mode '{gancho.get('mode')}' nao existe. Conhecidos: "
            + ", ".join(_MODOS_DE_HOOK))
    _numero(gancho.get("durationMs", 1200), "hook.durationMs", 0, 15000)

    sobreposicoes = doc.get("overlays")
    if not isinstance(sobreposicoes, list):
        raise TemplateInvalido("overlays: esperava uma lista")
    for i, ov in enumerate(sobreposicoes):
        if not isinstance(ov, dict) or not ov.get("asset"):
            raise TemplateInvalido(f"overlays[{i}]: precisa de 'asset'")
        ancora = ov.get("anchor", "top-right")
        if ancora not in _ANCORAS:
            raise TemplateInvalido(
                f"overlays[{i}].anchor '{ancora}' nao existe. Conhecidos: "
                + ", ".join(_ANCORAS))
        _numero(ov.get("opacity", 1.0), f"overlays[{i}].opacity", 0, 1)

    _numero((doc.get("audio") or {}).get("gainDb", -22), "audio.gainDb", -60, 0)
    _numero((doc.get("cuts") or {}).get("thresholdDb", -35), "cuts.thresholdDb", -90, 0)
    return doc


def margem_vertical(spec: dict | None) -> int:
    """`safeArea` traduzida para o `margin_v` que o `generate_ass` recebe.

    O ASS trabalha numa altura virtual de 288 (`PlayResY`), entao a
    porcentagem vira essa escala aqui -- e nao no chamador, que teria de
    conhecer um detalhe de formato de legenda para posicionar uma caixa.
    """
    doc = normalizar(spec)
    alinhamento = kwargs_de_legenda(doc).get("alignment", "bottom")
    area = doc["safeArea"]
    if alinhamento == "top":
        pct = area["topPct"]
    else:
        # `middle` cai aqui de proposito: com `an=5` o ASS centra verticalmente e
        # a MarginV nao posiciona nada. Devolver a margem de baixo assim mesmo e
        # mais honesto que inventar 0, que sugeriria que o valor importa.
        pct = area["bottomPct"]
    return int(round(PLAY_RES_Y * pct / 100.0))


#: Caracteres por palavra, com o espaco. A secao 5 fala em PALAVRAS
#: (`maxWords: 3`) e o `generate_ass` conta CARACTERES (`max_chars`) -- sao
#: unidades diferentes, e a traducao ingenua entre elas produzia blocos de tres
#: LETRAS. Sete e a media que cobre portugues e ingles com folga (a media de
#: ambos fica perto de 5 letras, mais o espaco, mais um pouco para nao cortar a
#: palavra seguinte cedo demais).
#:
#: **E aproximacao, e esta escrito que e.** O certo seria o `generate_ass`
#: aceitar um teto por palavras, que e mudanca no caminho de queima herdado do
#: upstream; ate la, `maxChars` esta disponivel para quem quiser o numero exato.
CHARS_POR_PALAVRA = 7


def chars_por_palavras(palavras) -> int:
    """`maxWords` -> `max_chars`, com um piso que nao produz bloco de uma letra."""
    try:
        n = int(palavras)
    except (TypeError, ValueError):
        raise TemplateInvalido(f"captions.maxWords: esperava numero, veio {palavras!r}")
    return max(8, n * CHARS_POR_PALAVRA)


def kwargs_de_legenda(spec: dict | None) -> dict:
    """Os argumentos de `subtitles.generate_ass` que este template pede.

    O preset da a base; o que estiver escrito no proprio `captions` vence,
    entao dá para pegar um preset e mudar so a cor sem copiar o resto.
    """
    doc = normalizar(spec)
    legendas = dict(doc.get("captions") or {})
    base = dict(PRESETS_DE_LEGENDA[legendas.pop("preset", "karaoke_fill")])

    # Os nomes da secao 5 nao sao os do `generate_ass`, e traduzir aqui e o que
    # permite ao documento ser legivel sem conhecer a assinatura dele.
    traducao = {"sizePt": "fontsize", "font": "font_name", "highlight": "highlight_color",
                "strokePx": "border_width", "color": "font_color",
                "maxChars": "max_chars"}
    for chave, valor in legendas.items():
        if chave == "yAnchor":
            continue          # posicao vem de safeArea, nao daqui
        if chave == "maxWords":
            base["max_chars"] = chars_por_palavras(valor)
            continue
        base[traducao.get(chave, chave)] = valor
    return base
