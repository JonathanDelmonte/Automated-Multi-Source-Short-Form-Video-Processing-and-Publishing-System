"""Series em partes (Fase 7, etapa 7.6): um video longo vira Parte 1, 2, 3...

"Pego uma live, colo, e ele divide em varios clipes de um minuto (...) parte 1,
parte 2" (o autor, 25-set-2026). O "pronto quando" da etapa: uma live de 1 hora
vira uma serie agendada, na ordem, **sem buraco e sem repeticao**.

Este modulo e a regra, em stdlib pura (o CI o exercita sem torch nem ffmpeg):

- **onde cortar** (`partes`): pedacos CONTIGUOS -- o fim de uma parte e o
  comeco da seguinte, o mesmo numero --, de cerca de `alvo` segundos cada. A
  fronteira ideal e `k * passo`; ela escorrega ate 20% do passo para cair numa
  pausa entre palavras, de preferencia no fim de uma frase. Nunca no meio de
  uma palavra: a legenda de uma parte e o audio dela terminam juntos;
- **o texto de cada parte** (`titulo`, `descricao`, `rotulo`): "Parte N" no
  titulo e no video, no idioma do canal;
- **o documento da serie** (`normalizar_pedido`, `serie.json` na pasta do
  job): o `main.py` e outro processo e le dali -- e, gravado na pasta, ele
  sobrevive a retomada do job depois de um reinicio, que o ambiente do
  processo nao sobrevive;
- **a retomada** (`marcar_pronta`, `incompleta`): uma serie de 60 partes leva
  minutos para renderizar, e um reinicio no meio nao pode deixa-la com as
  ultimas partes faltando;
- **a ordem na hora de postar** (`seguradas`): a parte seguinte nunca sai
  enquanto uma anterior, na mesma conta, ainda vai sair, esta subindo ou falhou.
"""
from __future__ import annotations

import json
import math
import os
import re
import threading
import uuid
from typing import Iterable, Optional

#: A duracao de cada parte que a pessoa pede, em segundos. O minuto e o que o
#: autor pediu. O teto de 3 minutos e o dos Shorts e dos Reels (o TikTok aceita
#: mais); abaixo de 20 s uma parte nao conta nada.
ALVO_PADRAO_S = 60
ALVO_MIN_S = 20
ALVO_MAX_S = 180

#: Quanto a fronteira pode escorregar da posicao ideal para achar uma pausa,
#: como fracao do passo. Com 20%, duas fronteiras vizinhas ficam a pelo menos
#: 60% do passo uma da outra: nenhuma parte sai curta demais.
FOLGA = 0.2

#: Quanto antes da proxima palavra a parte seguinte comeca, numa pausa longa.
#: O comeco importa mais que o fim: quem cai numa parte que abre com tres
#: segundos de silencio passa para o proximo video.
ANTECEDENCIA_S = 0.3
#: E quanto a parte anterior leva depois da ultima palavra dela: o fim que o
#: whisper marca numa palavra erra por pouco, e cortar colado nele come a
#: cauda da palavra.
CAUDA_S = 0.15

#: Uma serie com mais partes que isto e quase certamente engano (partes de 20 s
#: num video de tres horas), e renderizar tudo levaria a tarde inteira. A saida
#: e "terminar em" ou partes mais longas -- a mensagem diz isso.
MAX_PARTES = 500

#: "Parte N" no video: nos primeiros segundos (como o gancho), o tempo todo, ou
#: nao. No titulo vai sempre.
ROTULOS = ("inicio", "sempre", "nao")
ROTULO_PADRAO = "inicio"
SEGUNDOS_DO_ROTULO = 5.0

#: Os estilos do rotulo sao os do gancho (`hooks.HOOK_STYLES`); ha teste
#: comparando. Aqui e nao importado porque o `hooks` puxa o Pillow.
ESTILOS_DO_ROTULO = ("classic", "dark", "yellow", "red", "outline", "outline_yellow")
ESTILO_PADRAO = "classic"

#: A live da Twitch no ar vira UM bloco gravado (bloco 1.5). Para uma serie o
#: bloco padrao e de uma hora: e a live, nao um trecho dela, que a pessoa quer
#: em partes. O teto e o do proprio gravador (`twitch_live.block_seconds`).
BLOCO_PADRAO_MIN = 60
BLOCO_MAX_MIN = 120

NOME_MAX = 80
TITULO_MAX = 100          # o limite do YouTube para titulo

ARQUIVO = "serie.json"
PROGRESSO = "serie_progresso.json"

_PALAVRA = {"pt": "Parte", "en": "Part", "es": "Parte"}
_DE = {"pt": "de", "en": "of", "es": "de"}


class SerieInvalida(ValueError):
    """O pedido de serie nao serve. A mensagem vai para quem pediu."""


def _idioma(idioma: Optional[str]) -> str:
    curto = (idioma or "pt").split("-")[0].lower()
    return curto if curto in _PALAVRA else "pt"


# --------------------------------------------------------------------------- #
# O pedido
# --------------------------------------------------------------------------- #

def _numero(valor, nome: str, minimo: float, maximo: float, inteiro: bool = False):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise SerieInvalida(f"{nome} tem de ser um numero")
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise SerieInvalida(f"{nome} tem de ser um numero")
    if not math.isfinite(numero):
        raise SerieInvalida(f"{nome} tem de ser um numero")
    if inteiro and numero != int(numero):
        raise SerieInvalida(f"{nome} tem de ser um numero inteiro")
    if not minimo <= numero <= maximo:
        raise SerieInvalida(f"{nome} tem de ficar entre {minimo:g} e {maximo:g}")
    return int(numero) if inteiro else numero


def normalizar_pedido(pedido, *, idioma: Optional[str] = None) -> dict:
    """O documento da serie a partir do que o painel mandou, com os padroes.

    `pedido` pode vir como dict (corpo JSON) ou texto JSON (formulario com
    arquivo). Levanta `SerieInvalida` com o motivo em palavras. Campo que nao
    se conhece e ignorado: o documento e nosso, e o que ele carrega e decidido
    aqui.
    """
    if isinstance(pedido, str):
        texto = pedido.strip()
        if not texto:
            pedido = {}
        else:
            try:
                pedido = json.loads(texto)
            except ValueError:
                raise SerieInvalida("serie tem de ser um objeto JSON")
    if pedido is True:
        pedido = {}
    if not isinstance(pedido, dict):
        raise SerieInvalida("serie tem de ser um objeto JSON")

    nome = pedido.get("nome")
    if nome is not None and not isinstance(nome, str):
        raise SerieInvalida("nome tem de ser texto")
    nome = " ".join((nome or "").split())
    if len(nome) > NOME_MAX:
        raise SerieInvalida(f"o nome da serie passa de {NOME_MAX} caracteres")

    alvo = _numero(pedido.get("duracao_parte_s"), "duracao_parte_s",
                   ALVO_MIN_S, ALVO_MAX_S)
    inicio = _numero(pedido.get("inicio_s"), "inicio_s", 0, 24 * 3600)
    fim = _numero(pedido.get("fim_s"), "fim_s", 0, 24 * 3600)
    alvo = alvo or float(ALVO_PADRAO_S)
    if inicio is not None and fim is not None and fim - inicio < ALVO_MIN_S:
        raise SerieInvalida("o trecho escolhido e curto demais para uma serie")

    rotulo = pedido.get("rotulo") or ROTULO_PADRAO
    if rotulo not in ROTULOS:
        raise SerieInvalida("rotulo tem de ser inicio, sempre ou nao")
    estilo = pedido.get("estilo_rotulo") or ESTILO_PADRAO
    if estilo not in ESTILOS_DO_ROTULO:
        raise SerieInvalida("estilo_rotulo desconhecido")

    bloco = _numero(pedido.get("bloco_min"), "bloco_min", 1, BLOCO_MAX_MIN, inteiro=True)

    return {
        "versao": 1,
        "id": str(uuid.uuid4()),
        "nome": nome or None,
        "duracao_parte_s": alvo,
        "inicio_s": inicio,
        "fim_s": fim,
        "rotulo": rotulo,
        "estilo_rotulo": estilo,
        "agendar": bool(pedido.get("agendar")),
        "bloco_min": bloco or BLOCO_PADRAO_MIN,
        "idioma": _idioma(idioma or pedido.get("idioma")),
    }


def _numero_de_partes(total: float, alvo: float) -> int:
    """Meio para cima, e nao o `round` do Python, que arredonda 2,5 para 2:
    150 s com partes de 60 viram tres de 50 (curtas seguram mais que longas),
    e o numero e o mesmo que a pessoa faria de cabeca."""
    return max(1, int(total / alvo + 0.5))


def quantas_partes(duracao: float, spec: dict) -> int:
    """Quantas partes a serie vai ter, para recusar cedo o absurdo."""
    inicio, fim = _trecho(duracao, spec)
    total = fim - inicio
    if total <= 0:
        return 0
    return _numero_de_partes(total, max(1.0, float(spec.get("duracao_parte_s")
                                                   or ALVO_PADRAO_S)))


def _trecho(duracao: float, spec: dict) -> tuple:
    duracao = max(0.0, float(duracao or 0))
    inicio = float(spec.get("inicio_s") or 0)
    fim = spec.get("fim_s")
    fim = duracao if fim is None or float(fim) > duracao else float(fim)
    return min(inicio, duracao), fim


# --------------------------------------------------------------------------- #
# Onde cortar
# --------------------------------------------------------------------------- #

_FIM_DE_FRASE = re.compile(r"[.!?…]['\"”’»)\]]*$")
_PAUSA_CURTA = re.compile(r"[,;:—–-]['\"”’»)\]]*$")


def palavras(transcript) -> list:
    """`[(inicio, fim, texto)]` da transcricao do pipeline, em ordem.

    Palavra sem tempo e descartada; a lista sai ordenada pelo inicio porque as
    pausas sao lidas entre vizinhas.
    """
    saida = []
    if not isinstance(transcript, dict):
        return saida
    for segmento in transcript.get("segments") or []:
        if not isinstance(segmento, dict):
            continue
        for p in segmento.get("words") or []:
            if not isinstance(p, dict):
                continue
            try:
                ini, fim = float(p["start"]), float(p["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (math.isfinite(ini) and math.isfinite(fim)):
                continue
            saida.append((ini, max(ini, fim), str(p.get("word") or "").strip()))
    saida.sort(key=lambda w: (w[0], w[1]))
    return saida


def _pausas(lista: list, inicio: float, fim: float) -> list:
    """As pausas `(de, ate, texto_antes)` entre as palavras dentro do trecho,
    mais o silencio antes da primeira e depois da ultima. Palavras que se
    sobrepoem dao pausa de tamanho zero no meio delas."""
    dentro = [w for w in lista if w[1] > inicio and w[0] < fim]
    if not dentro:
        return [(inicio, fim, ".")]
    pausas = [(inicio, max(inicio, dentro[0][0]), ".")]
    for a, b in zip(dentro, dentro[1:]):
        if b[0] >= a[1]:
            pausas.append((a[1], b[0], a[2]))
        else:
            meio = (a[1] + b[0]) / 2
            pausas.append((meio, meio, a[2]))
    pausas.append((min(fim, dentro[-1][1]), fim, dentro[-1][2]))
    return pausas


def _ponto_na_pausa(de: float, ate: float, ideal: float) -> float:
    """Onde cortar dentro de uma pausa: o ideal, se ele cai nela; senao, perto
    do comeco da proxima fala (`ANTECEDENCIA_S` antes dela) -- ou no meio, se
    a pausa e curta demais para isso."""
    if ate - de <= 2 * ANTECEDENCIA_S:
        return (de + ate) / 2
    return min(max(ideal, de + CAUDA_S), ate - ANTECEDENCIA_S)


def _melhor_corte(ideal: float, janela: float, pausas: list,
                  piso: float, teto: float) -> float:
    """A melhor fronteira perto do ideal: pausa longa, fim de frase e
    proximidade, nesta ordem de peso. Toda fronteira entre duas palavras e
    uma pausa (de tamanho zero, se elas encostam), entao so fica sem candidata
    a janela sem duas palavras dentro -- e ai vale o proprio ideal."""
    melhor, nota_melhor = None, None
    for de, ate, antes in pausas:
        if ate < ideal - janela or de > ideal + janela:
            continue
        ponto = _ponto_na_pausa(de, ate, ideal)
        if not piso < ponto < teto or abs(ponto - ideal) > janela:
            continue
        # A pausa satura em 1 s: de um segundo para cima ja e uma pausa clara,
        # e um silencio de um minuto nao pode vencer o fim de frase colado no
        # ideal so por ser comprido.
        nota = min(ate - de, 1.0)
        if _FIM_DE_FRASE.search(antes or ""):
            nota += 1.0
        elif _PAUSA_CURTA.search(antes or ""):
            nota += 0.3
        nota -= 1.5 * abs(ponto - ideal) / janela
        if nota_melhor is None or nota > nota_melhor:
            melhor, nota_melhor = ponto, nota
    if melhor is not None:
        return melhor
    return min(max(ideal, piso), teto)


def partes(duracao: float, lista_de_palavras: Iterable = (), *,
           alvo: float = ALVO_PADRAO_S, inicio: float = 0.0,
           fim: Optional[float] = None) -> list:
    """`[(inicio, fim)]` das partes, contiguas, cobrindo [inicio, fim].

    `total / alvo` partes (meio para cima) de tamanho parecido: um video de
    90 s com alvo de 60 vira duas de 45, e nao uma de 60 e uma sobra de 30. A fronteira
    k fica perto de `inicio + k * passo`, escorregando ate `FOLGA` do passo para
    cair numa pausa.
    """
    duracao = max(0.0, float(duracao or 0))
    inicio = max(0.0, min(float(inicio or 0), duracao))
    fim = duracao if fim is None else max(inicio, min(float(fim), duracao))
    total = fim - inicio
    if total <= 0:
        return []
    alvo = max(1.0, float(alvo or ALVO_PADRAO_S))
    n = _numero_de_partes(total, alvo)
    passo = total / n
    janela = FOLGA * passo
    pausas = _pausas(list(lista_de_palavras), inicio, fim)
    fronteiras = [inicio]
    for k in range(1, n):
        ideal = inicio + k * passo
        # Cada parte fica com pelo menos metade do passo: a janela de 20%
        # ja garante isso, e o piso e o teto sao a rede.
        piso = fronteiras[-1] + 0.5 * passo
        teto = fim - 0.5 * passo
        fronteiras.append(round(_melhor_corte(ideal, janela, pausas, piso, teto), 3))
    fronteiras.append(round(fim, 3))
    fronteiras[0] = round(inicio, 3)
    return list(zip(fronteiras, fronteiras[1:]))


# --------------------------------------------------------------------------- #
# O texto de cada parte
# --------------------------------------------------------------------------- #

def rotulo(n: int, idioma: Optional[str] = None) -> str:
    """"Parte 3" -- o que vai no video e no fim do titulo."""
    return f"{_PALAVRA[_idioma(idioma)]} {int(n)}"


def titulo(nome: str, n: int, idioma: Optional[str] = None) -> str:
    """"Nome - Parte 3", sem passar de 100 caracteres. Quem encolhe e o nome,
    nunca o numero da parte: um titulo sem ele e uma parte perdida."""
    fim = f" - {rotulo(n, idioma)}"
    nome = " ".join((nome or "").split())
    espaco = TITULO_MAX - len(fim)
    if len(nome) > espaco:
        nome = nome[:max(0, espaco - 1)].rstrip() + "…"
    return (nome + fim) if nome else rotulo(n, idioma)


def descricao(nome: str, n: int, total: int, idioma: Optional[str] = None) -> str:
    """"Parte 3 de 60 — Nome" -- a descricao de cada plataforma. O credito da
    licenca, quando houver, entra depois pelo `PostMeta` (7.5)."""
    lingua = _idioma(idioma)
    trecho = f"{_PALAVRA[lingua]} {int(n)} {_DE[lingua]} {int(total)}"
    nome = " ".join((nome or "").split())
    return f"{trecho} — {nome}" if nome else trecho


def cortes(spec: dict, duracao: float, transcript=None, nome_do_video: str = "") -> list:
    """Os `shorts` do metadata para uma serie: um por parte, na ordem, com o
    texto de cada plataforma ja escrito. E o que o `main.py` renderiza no lugar
    do que a deteccao de momentos devolveria."""
    inicio, fim = _trecho(duracao, spec)
    trechos = partes(duracao, palavras(transcript),
                     alvo=float(spec.get("duracao_parte_s") or ALVO_PADRAO_S),
                     inicio=inicio, fim=fim)
    nome = (spec.get("nome") or nome_do_video or "").strip()
    idioma = spec.get("idioma")
    total = len(trechos)
    saida = []
    for i, (ini, fim_da_parte) in enumerate(trechos, start=1):
        texto = descricao(nome, i, total, idioma)
        saida.append({
            "start": ini,
            "end": fim_da_parte,
            "video_title_for_youtube_short": titulo(nome, i, idioma),
            "video_description_for_tiktok": texto,
            "video_description_for_instagram": texto,
            "viral_hook_text": rotulo(i, idioma),
            "serie": {"id": spec.get("id"), "nome": nome, "parte": i, "partes": total},
        })
    return saida


def resumo(spec: dict, shorts: list, nome_do_video: str = "") -> dict:
    """O que o metadata guarda da serie inteira (e a lista de projetos mostra)."""
    return {
        "id": spec.get("id"),
        "nome": (spec.get("nome") or nome_do_video or "").strip(),
        "partes": len(shorts),
        "duracao_parte_s": spec.get("duracao_parte_s"),
        "idioma": spec.get("idioma"),
        "agendar": bool(spec.get("agendar")),
    }


def segundos_do_rotulo(spec: Optional[dict]) -> Optional[float]:
    """Quanto tempo o "Parte N" fica no video: `SEGUNDOS_DO_ROTULO`, `0` para o
    video inteiro, ou None quando nao vai no video."""
    modo = (spec or {}).get("rotulo") or ROTULO_PADRAO
    if modo == "nao":
        return None
    return 0.0 if modo == "sempre" else SEGUNDOS_DO_ROTULO


# --------------------------------------------------------------------------- #
# O documento na pasta do job, e a retomada
# --------------------------------------------------------------------------- #

def gravar_spec(pasta: str, spec: dict) -> str:
    caminho = os.path.join(pasta, ARQUIVO)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    return caminho


def ler_spec(pasta: Optional[str]) -> Optional[dict]:
    """O documento da serie deste job, ou None -- job de cortes, ou arquivo
    ilegivel. Nunca levanta: quem pergunta e o pipeline e a lista de projetos."""
    if not pasta:
        return None
    try:
        with open(os.path.join(pasta, ARQUIVO), encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError):
        return None
    return spec if isinstance(spec, dict) and spec.get("id") else None


_TRAVA_DO_PROGRESSO = threading.Lock()


def _ler_progresso(pasta: str) -> dict:
    try:
        with open(os.path.join(pasta, PROGRESSO), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def marcar_pronta(pasta: str, indice: int, arquivo: str, total: int,
                  extra: Optional[dict] = None) -> None:
    """Anota que a parte `indice` terminou a cadeia inteira, e em que arquivo.

    As partes renderizam em paralelo (`CLIP_WORKERS`), entao a escrita e sob
    trava e por `os.replace`: um arquivo pela metade faria a retomada refazer
    tudo. Falha aqui nao derruba a parte -- so a retomada perde o atalho.
    """
    with _TRAVA_DO_PROGRESSO:
        dados = _ler_progresso(pasta)
        prontas = dados.get("prontas") if isinstance(dados.get("prontas"), dict) else {}
        prontas[str(int(indice))] = {"arquivo": os.path.basename(arquivo), **(extra or {})}
        dados = {"total": int(total), "prontas": prontas}
        destino = os.path.join(pasta, PROGRESSO)
        temporario = destino + ".tmp"
        try:
            with open(temporario, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
            os.replace(temporario, destino)
        except OSError as e:
            print(f"   ⚠️ Nao consegui anotar a parte {indice + 1} como pronta ({e}).")


def prontas(pasta: str) -> dict:
    """`{indice: {"arquivo": ..., ...}}` das partes prontas cujo arquivo ainda
    esta na pasta. As que sumiram (apagadas a mao) sao feitas de novo."""
    saida = {}
    for chave, valor in (_ler_progresso(pasta).get("prontas") or {}).items():
        if not isinstance(valor, dict) or not valor.get("arquivo"):
            continue
        try:
            indice = int(chave)
        except ValueError:
            continue
        caminho = os.path.join(pasta, os.path.basename(valor["arquivo"]))
        try:
            if os.path.getsize(caminho) > 0:
                saida[indice] = valor
        except OSError:
            continue
    return saida


def incompleta(pasta: str) -> bool:
    """Uma serie que parou no meio do render: tem documento e nao tem todas as
    partes prontas. E o que faz o motor retomar o job em vez de da-lo por
    terminado so porque o metadata ja existe (ele e escrito ANTES do render)."""
    if ler_spec(pasta) is None:
        return False
    total = _ler_progresso(pasta).get("total")
    if not isinstance(total, int) or total <= 0:
        return True
    return len(prontas(pasta)) < total


# --------------------------------------------------------------------------- #
# A ordem na hora de postar
# --------------------------------------------------------------------------- #

#: Uma parte anterior nestes estados ainda vai sair (ou falhou e espera a
#: pessoa), entao a seguinte espera. Publicada, cancelada (a pessoa pulou) e a
#: fila manual (`scheduled` sem hora: o sistema ja entregou, quem posta e a
#: pessoa) nao seguram nada.
def _ainda_vem(p: dict) -> bool:
    status = p.get("status")
    if status in ("failed", "publishing"):
        return True
    return status == "scheduled" and p.get("scheduled_at") is not None


def seguradas(pendentes: Iterable[dict], todas: Iterable[dict]) -> dict:
    """`{id: parte}` das pendentes que nao podem sair agora, com a parte
    anterior que as segura (a mais baixa).

    Cada dict traz `id`, `account_id`, `serie_id` e `parte`; as de `todas`
    trazem tambem `status` e `scheduled_at`. `todas` sao as publicacoes das
    mesmas series (inclusive as pendentes). Publicacao fora de serie nunca e
    segurada.

    **Na mesma conta**: o YouTube e o TikTok de uma serie andam cada um no seu
    passo -- uma parte que falhou no TikTok nao prende o YouTube.
    """
    anteriores: dict = {}
    for p in todas:
        if not p.get("serie_id") or not _ainda_vem(p):
            continue
        chave = (p["serie_id"], p.get("account_id"))
        anteriores.setdefault(chave, []).append(int(p.get("parte") or 0))
    saida = {}
    for p in pendentes:
        if not p.get("serie_id"):
            continue
        parte = int(p.get("parte") or 0)
        antes = [a for a in anteriores.get((p["serie_id"], p.get("account_id")), ())
                 if a < parte]
        if antes:
            saida[p["id"]] = min(antes)
    return saida


def planos(vencidas: Iterable[str], linhas: Iterable[dict]) -> dict:
    """O que o agendador faz, nesta volta, com cada serie que tem parte vencida
    numa conta. A serie numa conta e uma FILA: as partes consomem os horarios
    na ordem das partes, e nao cada uma o seu.

    `linhas` sao as publicacoes (`id`, `account_id`, `serie_id`, `parte`,
    `status`, `scheduled_at`) das series e contas envolvidas; `vencidas`, os
    ids que venceram. Devolve `{(serie_id, conta): plano}`, com
    `plano["acao"]`:

    - `"segurar"`: a primeira parte que ainda vai sair vem depois de uma que
      falhou ou esta subindo. Nada sai e nada muda, ate a pessoa tentar de
      novo ou pular (`parte_que_segura` diz qual);
    - `"normal"`: uma vencida so, e ela e a primeira da fila -- o dia de todo
      dia, que segue pela trava de sempre;
    - `"replanejar"`: mais de uma vencida, ou a vencida nao e a primeira (uma
      parte tentada de novo, uma pulada, o PC desligado): a fila INTEIRA ganha
      horarios novos, na ordem das partes (`scheduler.replanejar_fila`).

    `plano["fila"]` sao os ids que ainda vao sair, na ordem das partes.
    """
    vencidas = set(vencidas)
    grupos: dict = {}
    for p in linhas:
        if p.get("serie_id"):
            grupos.setdefault((p["serie_id"], p.get("account_id")), []).append(p)
    saida = {}
    for chave, grupo in grupos.items():
        vencidas_do_grupo = [p["id"] for p in grupo if p["id"] in vencidas]
        if not vencidas_do_grupo:
            continue
        fila = sorted((p for p in grupo if _ainda_vem(p) and p.get("status") == "scheduled"),
                      key=lambda p: int(p.get("parte") or 0))
        if not fila:
            continue
        primeira = int(fila[0].get("parte") or 0)
        travas = sorted(int(p.get("parte") or 0) for p in grupo
                        if p.get("status") in ("failed", "publishing")
                        and int(p.get("parte") or 0) < primeira)
        if travas:
            acao = "segurar"
        elif vencidas_do_grupo == [fila[0]["id"]]:
            acao = "normal"
        else:
            acao = "replanejar"
        saida[chave] = {"acao": acao, "fila": [p["id"] for p in fila],
                        "vencidas": vencidas_do_grupo,
                        "parte_que_segura": travas[0] if travas else None}
    return saida


def entram_na_playlist(linhas: Iterable[dict], ja_entraram: set) -> list:
    """Os ids que entram na playlist agora, na ordem das partes, de UMA serie
    numa conta do YouTube.

    Anda pelas partes em ordem. A publicada, com o id do video e ainda fora da
    playlist, entra. A que ainda vai sair -- agendada, na fila manual,
    subindo, ou que falhou e espera a pessoa -- PARA a caminhada: as seguintes
    esperam por ela, e a playlist fica na ordem das partes, e nao na ordem em
    que foram postadas. A pulada (cancelada) nao segura nada; a postada a mao
    sem o link tambem nao -- sem o id do video ela nunca vai poder entrar.
    """
    saida = []
    for p in sorted(linhas, key=lambda p: int(p.get("parte") or 0)):
        status = p.get("status")
        if status == "cancelled":
            continue
        if status == "published":
            if p["id"] not in ja_entraram and p.get("remote_id"):
                saida.append(p["id"])
            continue
        break
    return saida


def paradas(publicacoes: Iterable[dict]) -> dict:
    """`{id: {"parte": N, "motivo": "falhou"|"subindo"}}`: as partes agendadas
    que estao paradas porque uma anterior, na mesma conta, falhou (ou esta
    presa subindo). E o que a fila mostra -- a espera normal pela parte de
    antes, que sai primeiro pela agenda, nao e noticia."""
    lista = list(publicacoes)
    problemas: dict = {}
    for p in lista:
        if p.get("serie_id") and p.get("status") in ("failed", "publishing"):
            chave = (p["serie_id"], p.get("account_id"))
            problemas.setdefault(chave, []).append(
                (int(p.get("parte") or 0),
                 "falhou" if p["status"] == "failed" else "subindo"))
    saida = {}
    for p in lista:
        if not p.get("serie_id") or p.get("status") != "scheduled" \
                or p.get("scheduled_at") is None:
            continue
        parte = int(p.get("parte") or 0)
        antes = sorted(a for a in problemas.get((p["serie_id"], p.get("account_id")), ())
                       if a[0] < parte)
        if antes:
            saida[p["id"]] = {"parte": antes[0][0], "motivo": antes[0][1]}
    return saida
