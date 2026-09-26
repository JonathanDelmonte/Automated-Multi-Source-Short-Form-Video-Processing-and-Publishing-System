"""Analises por canal -- Fase 7, etapa 7.4.

Recebe os galhos publicados (uma publicacao = um corte numa conta) com as
leituras de cada um, e devolve os numeros das telas: a soma do canal, a de cada
plataforma, o ganho das ultimas 24 h, a serie por dia, os cortes que mais
renderam e o desempenho por faixa de horario. **Puro**: recebe `agora` e o
fuso, e o CI roda a conta inteira sem banco e sem relogio.

### Tres regras que as telas herdam daqui

**Vale o ULTIMO numero de cada publicacao, campo a campo.** `metrics` e serie
temporal: somar as leituras contaria o mesmo video uma vez por coleta. E uma
leitura pode vir sem um campo (o Analytics recusou a retencao hoje, os insights
do Instagram nao responderam): o ultimo numero CONHECIDO de cada campo e o que
vale, e nao o buraco da leitura mais recente.

**Ganho so se conta com base.** "Quanto rendeu hoje" e o numero de agora menos
o de antes. Sem leitura antes, a base so e zero se o post nasceu dentro do
periodo; um post antigo medido pela primeira vez ontem nao "ganhou" ontem todas
as views da vida dele. Ele fica de fora da conta daquele dia -- um pico falso no
dia em que alguem conectou a conta seria pior que a falta.

**Horario so vira conclusao com amostra e com folga.** O ADR-007 poe
11h/15h/19h como chute informado, e a 7.4 existe para que o horario deixe de
ser palpite. Mas o mesmo cuidado da calibracao vale aqui: abaixo de
`MINIMO_POR_HORARIO` posts por faixa, os numeros saem (olhar e honesto) e a
frase de "qual faixa rende mais" nao sai (afirmar nao e). E com amostra, a
melhor faixa so e dita se passar a segunda por `MARGEM_DO_MELHOR`: sem isso,
duas faixas quase iguais teriam um "vencedor" escolhido pelo ruido.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Iterable, Optional

#: Os numeros de uma leitura, na ordem em que as telas os mostram.
NUMEROS = ("views", "retention_pct", "likes", "comments", "shares", "saves", "avg_watch_s")
#: Os que se somam entre publicacoes. Retencao e tempo medio se tiram media.
SOMAVEIS = ("views", "likes", "comments", "shares", "saves")

PLATAFORMAS = ("youtube", "tiktok", "instagram")

#: As faixas do dia, em hora LOCAL de quem olha (o navegador manda o fuso).
FAIXAS_DO_DIA = ((0, 6, "madrugada"), (6, 12, "manha"), (12, 18, "tarde"), (18, 24, "noite"))

#: Abaixo disto, a faixa mostra os numeros e nao entra na conclusao.
MINIMO_POR_HORARIO = 5

#: Quanto a melhor faixa tem de passar a segunda (em mediana) para ser dita a
#: melhor. Views de posts curtos variam muito de um post para o outro: 2.036
#: contra 2.020 nao e "a tarde rende mais", e dizer isso seria o chute que a
#: 7.4 existe para tirar do horario.
MARGEM_DO_MELHOR = 0.25

#: A janela do "primeiro dia" de um post: a leitura mais perto de 24 h depois
#: dele, entre 18 h e 36 h. Views de posts de idades diferentes nao se comparam
#: (o mais velho sempre tem mais); as do primeiro dia, sim.
PRIMEIRO_DIA = (timedelta(hours=18), timedelta(hours=36))


# --------------------------------------------------------------------------- #
# Tempo
# --------------------------------------------------------------------------- #

def quando(valor) -> Optional[datetime]:
    """datetime com fuso (UTC se vier sem), de datetime ou texto ISO."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        dt = valor
    else:
        try:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def fuso(fuso_min: int) -> timezone:
    """O fuso de quem olha, em minutos a leste de UTC (Brasil: -180)."""
    try:
        minutos = int(fuso_min or 0)
    except (TypeError, ValueError):
        minutos = 0
    minutos = max(-14 * 60, min(14 * 60, minutos))
    return timezone(timedelta(minutes=minutos))


def inicio_do_dia(momento: datetime, tz: timezone) -> datetime:
    local = momento.astimezone(tz)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Uma publicacao
# --------------------------------------------------------------------------- #

def _leituras(galho: dict) -> list:
    """As leituras do galho, da mais antiga para a mais nova, com a hora lida."""
    saida = []
    for leitura in galho.get("leituras") or []:
        momento = quando(leitura.get("collected_at"))
        if momento is not None:
            saida.append((momento, leitura))
    saida.sort(key=lambda par: par[0])
    return saida


def ultimo(galho: dict) -> dict:
    """O ultimo numero CONHECIDO de cada campo, e quando foi a ultima leitura."""
    numeros = {campo: None for campo in NUMEROS}
    medido_em = None
    for momento, leitura in _leituras(galho):
        medido_em = momento
        for campo in NUMEROS:
            if leitura.get(campo) is not None:
                numeros[campo] = leitura[campo]
    numeros["medido_em"] = medido_em
    return numeros


def valor_em(galho: dict, campo: str, ate: datetime) -> Optional[float]:
    """O ultimo valor conhecido de `campo` ate o instante `ate` (inclusive)."""
    valor = None
    for momento, leitura in _leituras(galho):
        if momento > ate:
            break
        if leitura.get(campo) is not None:
            valor = leitura[campo]
    return valor


def ganho_no_periodo(galho: dict, campo: str, de: datetime, ate: datetime) -> Optional[float]:
    """Quanto `campo` cresceu entre `de` e `ate`, ou None se nao ha base.

    Sem leitura ate `de`, a base so e zero se o post nasceu dentro do periodo.
    """
    fim = valor_em(galho, campo, ate)
    if fim is None:
        return None
    base = valor_em(galho, campo, de)
    if base is None:
        postado = quando(galho.get("posted_at"))
        if postado is None or not (de <= postado <= ate):
            return None
        base = 0
    return max(0, fim - base)


def views_no_primeiro_dia(galho: dict) -> Optional[int]:
    """As views da leitura mais perto de 24 h depois do post (entre 18 h e 36 h)."""
    postado = quando(galho.get("posted_at"))
    if postado is None:
        return None
    alvo = postado + timedelta(hours=24)
    melhor = None
    for momento, leitura in _leituras(galho):
        if leitura.get("views") is None:
            continue
        if not (postado + PRIMEIRO_DIA[0] <= momento <= postado + PRIMEIRO_DIA[1]):
            continue
        if melhor is None or abs(momento - alvo) < abs(melhor[0] - alvo):
            melhor = (momento, leitura["views"])
    return melhor[1] if melhor else None


def medido(numeros: dict) -> bool:
    return any(numeros.get(campo) is not None for campo in NUMEROS)


# --------------------------------------------------------------------------- #
# Somas
# --------------------------------------------------------------------------- #

def _media(valores: list, casas: int = 1) -> Optional[float]:
    return round(sum(valores) / len(valores), casas) if valores else None


def totais(galhos: Iterable[dict]) -> dict:
    """A soma de um conjunto de galhos: o que o canal (ou a plataforma) rendeu.

    Cada soma usa so quem tem aquele numero: um post sem curtidas conhecidas
    nao entra como zero curtidas."""
    galhos = list(galhos)
    ultimos = [ultimo(g) for g in galhos]
    saida = {"publicados": len(galhos), "medidos": sum(1 for u in ultimos if medido(u))}
    for campo in SOMAVEIS:
        valores = [u[campo] for u in ultimos if u[campo] is not None]
        saida[campo] = sum(valores) if valores else None
    retencoes = [u["retention_pct"] for u in ultimos if u["retention_pct"] is not None]
    saida["retencao_media"] = _media(retencoes)
    saida["com_retencao"] = len(retencoes)
    tempos = [u["avg_watch_s"] for u in ultimos if u["avg_watch_s"] is not None]
    saida["tempo_medio_s"] = _media(tempos)
    return saida


def ganho(galhos: Iterable[dict], agora: datetime, horas: int = 24) -> dict:
    """O que cresceu nas ultimas `horas`, somando so quem tem base."""
    de = agora - timedelta(hours=horas)
    saida = {"horas": horas}
    contribuiram = set()
    for campo in SOMAVEIS:
        total, algum = 0, False
        for g in galhos:
            valor = ganho_no_periodo(g, campo, de, agora)
            if valor is not None:
                total += valor
                algum = True
                if campo == "views":
                    contribuiram.add(g.get("publication_id"))
        saida[campo] = total if algum else None
    saida["medidos"] = len(contribuiram)
    return saida


def serie(galhos: Iterable[dict], agora: datetime, dias: int = 28, fuso_min: int = 0) -> list:
    """Views ganhas por dia (local), do mais antigo ao de hoje, por plataforma."""
    galhos = list(galhos)
    tz = fuso(fuso_min)
    hoje = inicio_do_dia(agora, tz)
    saida = []
    for atras in range(max(1, int(dias)) - 1, -1, -1):
        inicio = hoje - timedelta(days=atras)
        fim = min(inicio + timedelta(days=1), agora)
        dia = {"dia": inicio.date().isoformat(), "views": None,
               "por_plataforma": {}}
        for g in galhos:
            valor = ganho_no_periodo(g, "views", inicio, fim)
            if valor is None:
                continue
            dia["views"] = (dia["views"] or 0) + valor
            plataforma = g.get("platform") or "?"
            dia["por_plataforma"][plataforma] = dia["por_plataforma"].get(plataforma, 0) + valor
        saida.append(dia)
    return saida


def melhores(galhos: Iterable[dict], n: int = 5) -> list:
    """Os cortes que mais renderam, pelo ultimo numero de views."""
    linhas = []
    for g in galhos:
        u = ultimo(g)
        if u["views"] is None:
            continue
        linhas.append({
            "publication_id": g.get("publication_id"),
            "titulo": g.get("titulo"),
            "plataforma": g.get("platform"),
            "handle": g.get("handle"),
            "channel_id": g.get("channel_id"),
            "job_id": g.get("job_id"),
            "clip_index": g.get("clip_index"),
            "url": g.get("url"),
            "posted_at": g.get("posted_at"),
            "score": g.get("score"),
            **{campo: u[campo] for campo in NUMEROS},
        })
    linhas.sort(key=lambda linha: (-(linha["views"] or 0), linha.get("titulo") or ""))
    return linhas[:max(0, int(n))]


def faixa_de(hora: int) -> str:
    for de, ate, rotulo in FAIXAS_DO_DIA:
        if de <= hora < ate:
            return rotulo
    return FAIXAS_DO_DIA[-1][2]


def por_horario(galhos: Iterable[dict], fuso_min: int = 0) -> dict:
    """Como os posts rendem pela faixa do dia em que foram ao ar.

    Compara as views do PRIMEIRO dia (views de idades diferentes nao se
    comparam) e a retencao. Abaixo de `MINIMO_POR_HORARIO` posts medidos na
    faixa, os numeros saem e a conclusao nao."""
    tz = fuso(fuso_min)
    baldes = {rotulo: {"faixa": rotulo, "de": de, "ate": ate, "posts": 0,
                       "views": [], "retencao": []}
              for de, ate, rotulo in FAIXAS_DO_DIA}
    for g in galhos:
        postado = quando(g.get("posted_at"))
        if postado is None:
            continue
        balde = baldes[faixa_de(postado.astimezone(tz).hour)]
        balde["posts"] += 1
        views = views_no_primeiro_dia(g)
        if views is not None:
            balde["views"].append(views)
        retencao = ultimo(g)["retention_pct"]
        if retencao is not None:
            balde["retencao"].append(retencao)
    faixas = []
    for _de, _ate, rotulo in FAIXAS_DO_DIA:
        b = baldes[rotulo]
        faixas.append({
            "faixa": rotulo, "de": b["de"], "ate": b["ate"], "posts": b["posts"],
            "com_views_do_primeiro_dia": len(b["views"]),
            "views_do_primeiro_dia_mediana": median(b["views"]) if b["views"] else None,
            "retencao_media": _media(b["retencao"]),
            "amostra_suficiente": len(b["views"]) >= MINIMO_POR_HORARIO,
        })
    validas = sorted((f for f in faixas if f["amostra_suficiente"]),
                     key=lambda f: f["views_do_primeiro_dia_mediana"], reverse=True)
    melhor = None
    parecidas = False
    if len(validas) >= 2:
        primeira = validas[0]["views_do_primeiro_dia_mediana"]
        segunda = validas[1]["views_do_primeiro_dia_mediana"]
        if primeira > segunda * (1 + MARGEM_DO_MELHOR):
            melhor = validas[0]["faixa"]
        else:
            parecidas = True
    return {"faixas": faixas, "minimo": MINIMO_POR_HORARIO, "melhor": melhor,
            "parecidas": parecidas, "margem": MARGEM_DO_MELHOR,
            "fuso_min": int(tz.utcoffset(None).total_seconds() // 60)}


def por_plataforma(galhos: Iterable[dict]) -> list:
    galhos = list(galhos)
    presentes = [p for p in PLATAFORMAS if any(g.get("platform") == p for g in galhos)]
    presentes += sorted({g.get("platform") for g in galhos
                         if g.get("platform") and g.get("platform") not in PLATAFORMAS})
    return [{"plataforma": p, **totais(g for g in galhos if g.get("platform") == p)}
            for p in presentes]


def filtrar(galhos: Iterable[dict], canal: Optional[str] = None,
            plataforma: Optional[str] = None) -> list:
    """Os galhos de um canal (`"sem"` = sem canal) e/ou de uma plataforma."""
    saida = []
    for g in galhos:
        if canal == "sem" and g.get("channel_id"):
            continue
        if canal and canal != "sem" and g.get("channel_id") != canal:
            continue
        if plataforma and g.get("platform") != plataforma:
            continue
        saida.append(g)
    return saida


# --------------------------------------------------------------------------- #
# As telas
# --------------------------------------------------------------------------- #

def resumo(galhos: Iterable[dict], agora: datetime, dias: int = 28, fuso_min: int = 0) -> dict:
    """Tudo o que a tela de analises de um canal (ou de uma plataforma) mostra."""
    galhos = list(galhos)
    agora = quando(agora)
    return {
        "totais": totais(galhos),
        "ganho_24h": ganho(galhos, agora),
        "por_plataforma": por_plataforma(galhos),
        "serie": serie(galhos, agora, dias, fuso_min),
        "melhores": melhores(galhos),
        "por_horario": por_horario(galhos, fuso_min),
    }


def lado_a_lado(canais: Iterable[dict], galhos: Iterable[dict], agora: datetime,
                dias: int = 14, fuso_min: int = 0) -> list:
    """Todos os canais lado a lado (Analises, no menu). Os galhos sem canal
    entram como um grupo proprio no fim, se houver algum."""
    galhos = list(galhos)
    agora = quando(agora)
    saida = []
    for canal in canais:
        deste = filtrar(galhos, canal=canal.get("id"))
        saida.append({"canal": canal, "totais": totais(deste),
                      "ganho_24h": ganho(deste, agora),
                      "plataformas": [p["plataforma"] for p in por_plataforma(deste)],
                      "serie": serie(deste, agora, dias, fuso_min)})
    sem_canal = filtrar(galhos, canal="sem")
    if sem_canal:
        saida.append({"canal": None, "totais": totais(sem_canal),
                      "ganho_24h": ganho(sem_canal, agora),
                      "plataformas": [p["plataforma"] for p in por_plataforma(sem_canal)],
                      "serie": serie(sem_canal, agora, dias, fuso_min)})
    return saida


def hoje(canais: Iterable[dict], galhos: Iterable[dict], agora: datetime,
         fuso_min: int = 0) -> dict:
    """Os numeros do dia, para o Inicio: o que cresceu nas ultimas 24 h, o que
    foi ao ar hoje e o corte que mais cresceu."""
    galhos = list(galhos)
    agora = quando(agora)
    tz = fuso(fuso_min)
    comeco = inicio_do_dia(agora, tz)
    postados_hoje = [g for g in galhos
                     if (quando(g.get("posted_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= comeco]
    destaque = None
    for g in galhos:
        valor = ganho_no_periodo(g, "views", agora - timedelta(hours=24), agora)
        if valor and (destaque is None or valor > destaque["ganho_views"]):
            destaque = {"publication_id": g.get("publication_id"), "titulo": g.get("titulo"),
                        "plataforma": g.get("platform"), "handle": g.get("handle"),
                        "channel_id": g.get("channel_id"), "url": g.get("url"),
                        "ganho_views": valor}
    por_canal = []
    for canal in canais:
        deste = filtrar(galhos, canal=canal.get("id"))
        if deste:
            por_canal.append({"canal": canal, "ganho_24h": ganho(deste, agora),
                              "publicados": len(deste)})
    return {"ganho_24h": ganho(galhos, agora), "publicados_hoje": len(postados_hoje),
            "publicados": len(galhos), "medidos": sum(1 for g in galhos if medido(ultimo(g))),
            "destaque": destaque, "por_canal": por_canal}
