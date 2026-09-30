"""O texto do post no idioma da plataforma (Fase 7, etapa 7.10).

As plataformas chinesas buscam e recomendam pelo texto do post, em chines: um
titulo em portugues no Douyin nao e achado por ninguem. O texto -- titulo,
descricao e tags -- sai traduzido pela cascata gratis de texto (ADR-011) e fica
guardado na pasta do projeto (`traducoes.json`), para nunca ser pedido duas
vezes.

- **A chave e o TEXTO de origem**, e nao o numero do corte: um titulo que mudou
  (o gancho reescrito, o corte re-editado) e traduzido de novo, e o mesmo texto
  nunca volta a gastar cota.
- **Uma chamada por pacote**, com os cortes que faltam juntos (em lotes de
  `LOTE`), e nao uma por corte: o pacote do dia de um canal ativo tem uma duzia
  de cortes.
- **O que ja esta no idioma passa como esta** (`ja_esta_no_idioma`): um canal
  que ja fala chines nao precisa de traducao.
- **Falha aberto.** Sem IA de texto, com todas fora do ar ou sem tempo, vai o
  texto original -- e o LEIA-ME do pacote diz quais cortes ficaram assim. O
  post atrasado por uma traducao que nao veio seria pior que o post em
  portugues, que a pessoa ainda pode corrigir antes de apertar publicar.
- **Roda num subprocesso** (`python traducao.py`, o pedido pela entrada
  padrao), como toda chamada de IA do programa: o `llm_cascade` guarda por
  processo o que recusou (chave recusada, modelo que nao existe), e no processo
  do servidor isso duraria ate o proximo reinicio -- uma chave corrigida nas
  Configuracoes continuaria recusada. E um provedor que trava nao prende o
  servidor: o prazo mata o subprocesso.

O video em si continua como foi feito: a fala e a legenda queimada no idioma
original. Legenda em chines e outra etapa ("Idiomas", no plano), e pede uma
fonte com os caracteres chineses dentro da imagem do programa.

O que decide e stdlib pura; so o `main()` fala com a cascata.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import sys
from typing import Optional

import plataformas

ARQUIVO = "traducoes.json"

#: Como o pedido descreve cada idioma de destino.
IDIOMAS = {
    "zh-CN": "chines simplificado (简体中文), como se escreve na China continental",
}

#: Quantos cortes vao numa chamada. Uma duzia cabe folgada no contexto de todo
#: provedor da cascata, e um lote que falha nao leva os outros junto.
LOTE = 12

#: O tamanho da descricao traduzida. Curta de proposito: o 简介 do Bilibili tem
#: 250 caracteres, e o credito da fonte (7.5) precisa caber junto dele.
TEXTO_ALVO = 150

TAGS_MIN, TAGS_MAX = 3, 6
TAG_MAX = 12


def titulo_max(idioma: str) -> int:
    """O menor campo de titulo entre as plataformas do idioma: uma traducao
    serve a todas (no chines, o do Xiaohongshu, 20 caracteres)."""
    limites = [p.titulo_max for p in plataformas.TODAS
               if p.idioma == idioma and p.titulo_max]
    return min(limites) if limites else 60


# --------------------------------------------------------------------------- #
# O que decide
# --------------------------------------------------------------------------- #

def origem_de(meta, plataforma: str) -> dict:
    """O texto que vai ser traduzido, como o `render_caption` o leria."""
    return {
        "titulo": (meta.title or "").strip(),
        "texto": (meta.description_for(plataforma) or "").strip(),
        "hashtags": [str(h).strip() for h in (meta.hashtags or ()) if str(h).strip()],
    }


def chave(origem: dict) -> str:
    bruto = json.dumps([origem.get("titulo", ""), origem.get("texto", ""),
                        list(origem.get("hashtags") or [])], ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:20]


def _e_cjk(c: str) -> bool:
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF


def ja_esta_no_idioma(origem: dict, idioma: str) -> bool:
    """Se o texto ja esta no idioma de destino (so o chines, por enquanto): a
    maioria das letras do titulo e da descricao sao caracteres chineses."""
    if not idioma.startswith("zh"):
        return False
    letras = [c for c in f"{origem.get('titulo', '')} {origem.get('texto', '')}" if c.isalpha()]
    if not letras:
        return False
    return sum(1 for c in letras if _e_cjk(c)) >= 0.5 * len(letras)


def ler_cache(pasta: str) -> dict:
    """`{idioma: {chave: traducao}}`, ou vazio. Nunca levanta."""
    try:
        with open(os.path.join(pasta, ARQUIVO), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {k: v for k, v in dados.items() if isinstance(v, dict)}


def guardada(pasta: str, idioma: str, origem: dict) -> Optional[dict]:
    feita = ler_cache(pasta).get(idioma, {}).get(chave(origem))
    return feita if valida(feita) else None


def valida(traducao) -> bool:
    return (isinstance(traducao, dict) and bool(str(traducao.get("titulo") or "").strip())
            and isinstance(traducao.get("tags", []), list))


def guardar(pasta: str, idioma: str, novas: dict) -> None:
    """Junta `novas` ({chave: traducao}) ao que ja esta na pasta. Escreve num
    arquivo ao lado e troca: quem le no meio nunca ve metade de um JSON."""
    if not novas:
        return
    dados = ler_cache(pasta)
    dados.setdefault(idioma, {}).update(novas)
    destino = os.path.join(pasta, ARQUIVO)
    temporario = f"{destino}.{os.getpid()}.tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(temporario, destino)


def aplicar(meta, plataforma: str, traducao: dict, idioma: str):
    """O `PostMeta` com o texto traduzido: o titulo, a descricao DESTA
    plataforma e as tags. O credito fica como veio: e o que a licenca exige,
    com o link da fonte."""
    return dataclasses.replace(
        meta, title=traducao["titulo"],
        descriptions={**(meta.descriptions or {}), plataforma: traducao.get("texto") or ""},
        hashtags=tuple(traducao.get("tags") or ()), language=idioma)


def prompt(itens: list, idioma: str) -> str:
    """O pedido de um lote. `itens`: `[{"i", "titulo", "texto", "hashtags"}]`."""
    alvo = IDIOMAS.get(idioma, idioma)
    entrada = [{"i": it["i"], "titulo": it["titulo"], "texto": it["texto"],
                "hashtags": it.get("hashtags") or []} for it in itens]
    return "\n".join([
        f"Voce adapta o texto de posts de videos curtos para {alvo}, para apps como "
        "Douyin, Kuaishou, Bilibili e Xiaohongshu.",
        "Para cada item, escreva:",
        f"- `titulo`: ate {titulo_max(idioma)} caracteres, com o gancho do titulo original. "
        "Natural, como um criador de la escreveria; nao traduza palavra por palavra.",
        f"- `texto`: 1 ou 2 frases, ate {TEXTO_ALVO} caracteres, com o sentido da descricao "
        "original. Sem hashtags, sem emojis em excesso e sem chamada para seguir outro perfil.",
        f"- `tags`: {TAGS_MIN} a {TAGS_MAX} tags curtas no idioma de destino, sem `#`, "
        "como as pessoas de la buscariam o assunto.",
        "Nomes de pessoas, marcas e lugares: a grafia de costume no idioma de destino, ou "
        "o original se nao houver. Nao invente fatos que o texto original nao diz. "
        "Horarios de capitulos (0:00) ficam como estao.",
        "Devolva `itens` com o mesmo `i` de cada item de entrada.",
        "Itens:",
        json.dumps(entrada, ensure_ascii=False),
    ])


def _limpar(texto, maximo: int) -> str:
    limpo = re.sub(r"\s+", " ", str(texto or "")).strip().strip("\"'“”「」")
    return limpo[:maximo].strip()


def _tags(bruto) -> list:
    vistas, saida = set(), []
    for tag in bruto if isinstance(bruto, list) else []:
        limpa = _limpar(str(tag).lstrip("#＃"), TAG_MAX)
        if limpa and limpa.lower() not in vistas:
            vistas.add(limpa.lower())
            saida.append(limpa)
    return saida[:TAGS_MAX]


def ler_resposta(bruto, idioma: str) -> dict:
    """`{i: traducao}` do que veio certo. Item sem titulo fica de fora (volta a
    ser pedido da proxima vez); texto e tags vazios valem -- o titulo e o que
    nao pode faltar."""
    if hasattr(bruto, "model_dump"):
        bruto = bruto.model_dump()
    itens = (bruto or {}).get("itens") if isinstance(bruto, dict) else None
    saida = {}
    for item in itens if isinstance(itens, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        titulo = _limpar(item.get("titulo"), titulo_max(idioma))
        if not titulo:
            continue
        saida[i] = {"titulo": titulo,
                    "texto": _limpar(item.get("texto"), TEXTO_ALVO * 2),
                    "tags": _tags(item.get("tags"))}
    return saida


def pedido(idioma: str, faltam: list) -> dict:
    """O que o servidor manda ao subprocesso: `faltam` e `[(pasta, origem)]`,
    sem repetir o mesmo texto da mesma pasta."""
    vistos, itens = set(), []
    for pasta, origem in faltam:
        marca = (pasta, chave(origem))
        if marca in vistos:
            continue
        vistos.add(marca)
        itens.append({"pasta": pasta, **origem})
    return {"idioma": idioma, "itens": itens}


# --------------------------------------------------------------------------- #
# O subprocesso
# --------------------------------------------------------------------------- #

def _schema():
    from typing import List

    from pydantic import BaseModel

    # Sem valor padrao nos campos, como os schemas do `criar_video`: o
    # `response_schema` do Gemini ja recusou `default`.
    class Traducao(BaseModel):
        i: int
        titulo: str
        texto: str
        tags: List[str]

    class Traducoes(BaseModel):
        itens: List[Traducao]

    return Traducoes


def traduzir(dados: dict, call=None, log=print) -> int:
    """Traduz o pedido e grava na pasta de cada corte. Devolve quantos sairam."""
    import llm_cascade
    if call is None:
        import chamar_llm
        call = chamar_llm.chamar_provedor
    idioma = dados.get("idioma") or "zh-CN"
    itens = [dict(it, i=n) for n, it in enumerate(dados.get("itens") or [])
             if isinstance(it, dict) and it.get("pasta")]
    # Outro pedido pode ter traduzido enquanto este esperava a vez.
    itens = [it for it in itens if guardada(it["pasta"], idioma, it) is None]
    feitas = 0
    for inicio in range(0, len(itens), LOTE):
        lote = itens[inicio:inicio + LOTE]
        try:
            bruto, _custo = llm_cascade.run(prompt(lote, idioma), _schema(), call=call, log=log)
        except llm_cascade.AllProvidersFailed as e:
            log(f"🈶 Traducao: nenhuma IA de texto respondeu ({e})")
            continue
        except Exception as e:
            log(f"🈶 Traducao: {type(e).__name__}: {e}")
            continue
        respostas = ler_resposta(bruto, idioma)
        por_pasta: dict = {}
        for it in lote:
            feita = respostas.get(it["i"])
            if feita:
                por_pasta.setdefault(it["pasta"], {})[chave(it)] = feita
        for pasta, novas in por_pasta.items():
            try:
                guardar(pasta, idioma, novas)
                feitas += len(novas)
            except OSError as e:
                log(f"🈶 Traducao: nao consegui gravar em {pasta} ({e})")
    log(f"🈶 Traducao para {idioma}: {feitas} de {len(itens)} texto(s)")
    return feitas


def main() -> int:
    try:
        dados = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("🈶 Traducao: pedido ilegivel")
        return 2
    traduzir(dados if isinstance(dados, dict) else {})
    return 0


if __name__ == "__main__":
    sys.exit(main())
