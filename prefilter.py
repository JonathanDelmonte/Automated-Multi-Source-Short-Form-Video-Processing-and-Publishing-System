"""Pre-filtro heuristico das janelas de pontuacao (ADR-004).

**Por que e requisito de arquitetura e nao otimizacao.** O free tier do Groq
tem teto de 100.000 tokens/dia. Uma live de 4h da Twitch -- o caso que a propria
Fase 1 elege como pior caso -- vira ~240 janelas de 90s e, so no passe de
pontuacao, consome de 60% a 75% desse orcamento num video so. O rate limit nao
vai apertar no futuro: ja esta apertado no caso de uso alvo.

**O corte e por ORCAMENTO, nao por qualidade.** Esta e a decisao que torna o
modulo defensavel sem dados de calibracao ainda: ele nunca decide que uma
janela e ruim. Ele decide que so cabem N janelas hoje e manda as N mais
promissoras. Num video de 10 minutos, onde tudo cabe, **ele nao faz nada** --
nenhuma janela e descartada e o comportamento e identico ao de antes. Num video
de 4h, ele escolhe. Um limiar de qualidade com pesos inventados descartaria o
melhor momento de um video curto sem nunca ser notado; um teto de orcamento so
atua quando nao atuar significaria estourar a cota.

Os quatro sinais sao os do ADR-004, e vale ser honesto sobre a confianca em
cada um:

| Sinal | Confianca |
|---|---|
| densidade de palavras/segundo | alta -- uma janela quase sem fala nao pode conter um momento falado |
| silencio prolongado | alta -- 60% de ar morto e menos material, nao opiniao |
| troca de falante | media -- o ADR-004 pede; que mais turnos indiquem bom momento e hipotese |
| energia de audio | media -- risada e enfase aparecem aqui, mas tambem musica de fundo |

Por isso o `report` sai no log com os numeros de toda janela descartada: o
proximo video de verdade e que vira dado de calibracao, e o ADR-005 ja preve
trocar a rubrica por medicao na Fase 5.

Sem numpy o modulo continua funcionando: so a energia sai da conta.
"""
from __future__ import annotations

import os
import wave

#: Fracao do orcamento diario restante que o passe de pontuacao pode consumir.
#: O resto fica para o passe de detalhe (que le so as janelas vencedoras) e
#: para o proximo video do dia. 0.5 e conservador de proposito: estourar a cota
#: no meio de um job deixa o video pela metade.
FRACAO_DO_ORCAMENTO = 0.5

#: Nunca descer abaixo disto, por mais apertado que esteja o orcamento. Menos
#: que isto nao e um pre-filtro, e um video diferente.
MINIMO_DE_JANELAS = 8


# --------------------------------------------------------------------------- #
# Sinais
# --------------------------------------------------------------------------- #

def envelope_from_wav(path: str, window_s: float = 1.0) -> list[float]:
    """RMS por janela de `window_s`, lido do WAV 16k mono do estagio 02.

    Le em pedacos: um WAV de 4h tem ~460 MB, e carrega-lo inteiro como float32
    seriam ~920 MB de RAM para calcular uma media movel.

    Devolve [] em qualquer problema -- arquivo ausente, formato inesperado,
    numpy indisponivel. A energia e um sinal entre quatro; sem ela o
    pre-filtro decide com os outros tres.
    """
    try:
        import numpy as np
    except ImportError:
        return []
    try:
        with wave.open(path, "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                return []
            taxa = wf.getframerate()
            por_janela = max(1, int(taxa * window_s))
            saida = []
            while True:
                bruto = wf.readframes(por_janela)
                if not bruto:
                    break
                amostras = np.frombuffer(bruto, dtype=np.int16).astype(np.float32)
                if amostras.size == 0:
                    break
                saida.append(float(np.sqrt(np.mean(amostras * amostras))))
            return saida
    except (wave.Error, OSError, ValueError):
        return []


def _palavras_na_janela(janela: dict, words: list[dict]) -> list[dict]:
    ini, fim = float(janela.get("start", 0)), float(janela.get("end", 0))
    return [w for w in words if ini <= float(w.get("s", 0)) < fim]


def features_for(janela: dict, words: list[dict],
                 envelope: list[float] | None = None,
                 envelope_window_s: float = 1.0) -> dict:
    """Os quatro sinais do ADR-004 para uma janela. Pura.

    `turns` usa o intervalo entre palavras como proxy de troca de falante: sem
    diarizacao, uma pausa longa no meio de fala continua e o unico sinal
    disponivel, e e o mesmo que separa pergunta de resposta.
    """
    ini, fim = float(janela.get("start", 0)), float(janela.get("end", 0))
    segundos = max(0.0, fim - ini)
    palavras = _palavras_na_janela(janela, words)

    maior_silencio = 0.0
    silencio_total = 0.0
    turnos = 0
    anterior_fim = ini
    for w in palavras:
        lacuna = float(w.get("s", 0)) - anterior_fim
        if lacuna > 0:
            silencio_total += lacuna
            maior_silencio = max(maior_silencio, lacuna)
            # 0,6 s e a pausa que separa turnos de conversa da respiracao
            # dentro de uma frase. Nao e medida: e ponto de partida, e o
            # relatorio no log e o que vai permitir ajusta-lo com dado.
            if lacuna >= 0.6:
                turnos += 1
        anterior_fim = max(anterior_fim, float(w.get("e", 0)))
    # A cauda entra nos dois: o trecho entre a ultima palavra e o fim da janela
    # e, muitas vezes, o maior silencio que existe nela (fim de fala, saida de
    # musica). Contava so no total e ficava invisivel no `longest_silence`.
    cauda = max(0.0, fim - anterior_fim)
    silencio_total += cauda
    maior_silencio = max(maior_silencio, cauda)

    energia = None
    if envelope:
        i0 = int(ini / envelope_window_s)
        i1 = max(i0 + 1, int(fim / envelope_window_s))
        fatia = envelope[i0:i1]
        if fatia:
            energia = sum(fatia) / len(fatia)

    return {
        "seconds": round(segundos, 2),
        "words": len(palavras),
        "words_per_second": round(len(palavras) / segundos, 3) if segundos else 0.0,
        "longest_silence": round(maior_silencio, 2),
        "silence_ratio": round(silencio_total / segundos, 3) if segundos else 1.0,
        "turns": turnos,
        "energy": round(energia, 1) if energia is not None else None,
    }


def _normaliza(valores: list[float]) -> list[float]:
    """Para [0,1] pelo minimo e maximo da propria lista.

    Relativo ao video, nao absoluto: o que e "fala densa" num podcast calmo e
    diferente do que e numa live de gameplay, e um limiar fixo escolheria
    sempre o mesmo tipo de conteudo.
    """
    if not valores:
        return []
    lo, hi = min(valores), max(valores)
    if hi <= lo:
        return [0.5] * len(valores)
    return [(v - lo) / (hi - lo) for v in valores]


def rank(janelas: list[dict], words: list[dict],
         envelope: list[float] | None = None) -> list[dict]:
    """`[{janela, features, score}]`, do mais promissor ao menos. Pura."""
    feats = [features_for(j, words, envelope) for j in janelas]
    if not feats:
        return []

    densidade = _normaliza([f["words_per_second"] for f in feats])
    # Silencio e turnos invertidos/diretos conforme o sinal: mais ar morto e
    # pior, mais turnos e melhor.
    silencio = _normaliza([f["silence_ratio"] for f in feats])
    turnos = _normaliza([float(f["turns"]) for f in feats])
    tem_energia = any(f["energy"] is not None for f in feats)
    energia = _normaliza([f["energy"] or 0.0 for f in feats]) if tem_energia else None

    saida = []
    for i, (j, f) in enumerate(zip(janelas, feats)):
        nota = (0.45 * densidade[i]
                + 0.25 * (1.0 - silencio[i])
                + 0.20 * turnos[i])
        nota += 0.10 * (energia[i] if energia else 0.5)
        saida.append({"window": j, "features": f, "score": round(nota, 4)})
    saida.sort(key=lambda r: r["score"], reverse=True)
    return saida


# --------------------------------------------------------------------------- #
# Orcamento
# --------------------------------------------------------------------------- #

def _teto_de_janelas(janelas: list[dict], tokens_disponiveis: int | None,
                     estimador) -> int | None:
    """Quantas janelas cabem no orcamento. None = cabem todas."""
    if not tokens_disponiveis or tokens_disponiveis <= 0 or not janelas:
        return None
    custo_total = sum(max(1, estimador(j.get("text") or "")) for j in janelas)
    permitido = int(tokens_disponiveis * FRACAO_DO_ORCAMENTO)
    if custo_total <= permitido:
        return None
    medio = max(1, custo_total // len(janelas))
    return max(MINIMO_DE_JANELAS, permitido // medio)


def tokens_disponiveis_hoje(chain) -> int | None:
    """O MENOR orcamento restante entre os provedores da cascata que publicam um.

    O menor, e nao o do primeiro, e a escolha que faz este modulo servir ao caso
    que o ADR-004 descreve. Pela ordem do ADR-005, uma fonte longa comeca no
    **Gemini**, cujo free tier nao publica teto estavel de tokens -- entao olhar
    so o primeiro provedor deixaria a live de 4h passar sem filtro nenhum,
    exatamente o video que o pre-filtro existe para viabilizar.

    Mas a cascata escorrega: basta o Gemini devolver 429 para o job cair no
    Groq no meio do caminho, e ai ele precisa caber nos 100.000 tokens/dia de
    la. O job tem que caber no provedor mais apertado em que ele pode aterrissar,
    nao no primeiro que vai tentar.

    None quando nenhum provedor da cadeia publica teto (so Gemini, so Ollama, ou
    um servidor local): sem numero divulgado, qualquer corte aqui seria o
    achismo que o proprio ADR-004 manda evitar. Ai o pre-filtro nao atua, e
    `PREFILTER_MAX_WINDOWS` continua disponivel para quem quiser mandar.
    """
    restantes = []
    for p in (chain or []):
        teto = getattr(p, "tokens_per_day", None)
        if not teto:
            continue
        try:
            import llm_cascade
            gasto = int(llm_cascade.usage(p.id).get("tokens") or 0)
        except Exception:
            gasto = 0
        restantes.append(max(0, teto - gasto))
    return min(restantes) if restantes else None


def apply(janelas: list[dict], words: list[dict], *, chain=None,
          envelope: list[float] | None = None,
          estimador=None, log=print) -> list[dict]:
    """As janelas que vao ao LLM, na ordem cronologica original.

    Devolve a lista inteira quando tudo cabe no orcamento -- que e o caso de
    todo video curto, e por isso este modulo e seguro de deixar ligado.
    """
    if not janelas:
        return janelas

    forcado = (os.environ.get("PREFILTER_MAX_WINDOWS") or "").strip()
    teto = None
    if forcado:
        try:
            teto = max(1, int(forcado))
        except ValueError:
            teto = None
    if teto is None:
        if estimador is None:
            import llm_cascade
            estimador = llm_cascade.estimate_tokens
        teto = _teto_de_janelas(janelas, tokens_disponiveis_hoje(chain), estimador)

    if teto is None or teto >= len(janelas):
        return janelas

    ordenadas = rank(janelas, words, envelope)
    escolhidas = ordenadas[:teto]
    descartadas = ordenadas[teto:]
    ids = {id(r["window"]) for r in escolhidas}

    log(f"   \U0001f3af Pre-filtro: {len(escolhidas)} de {len(janelas)} janelas "
        f"cabem no orcamento de tokens de hoje.")
    # Os numeros das descartadas vao para o log de proposito: a calibracao
    # deste filtro e trabalho da Fase 5, e ela precisa de casos reais.
    for r in descartadas[:5]:
        f = r["features"]
        log(f"      ✂️  {r['window'].get('id')} "
            f"({r['window'].get('start'):.0f}s): nota {r['score']:.2f}, "
            f"{f['words_per_second']} pal/s, {int(f['silence_ratio'] * 100)}% silencio, "
            f"{f['turns']} turnos")
    if len(descartadas) > 5:
        log(f"      ✂️  ... e mais {len(descartadas) - 5}.")

    return [j for j in janelas if id(j) in ids]
