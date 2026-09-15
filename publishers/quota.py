"""O contador de quota do YouTube -- Fase 3, bloco 3.4.

O plano da um numero exato para respeitar, e ele nao e negociavel do nosso
lado: **`videos.insert` custa 1600 unidades contra 10.000/dia**, ou seja **6
uploads por dia**. A conta da secao 1 fecha: 3 videos/dia gastam 4.800 e sobra
metade para listagem e reprocessamento.

O contador existe para que o 7o upload **caia na fila manual em vez de falhar**.
Sem ele a API responde `quotaExceeded`, o job fica vermelho e o corte se perde
de vista -- que e o oposto do que a cascata da secao 6 promete.

**O dia e o do Pacifico, nao o nosso.** A quota da API do YouTube zera a
meia-noite em horario do Pacifico; contar em UTC daria uma janela de 7 a 8
horas por dia em que o contador acha que tem quota e a API discorda (ou o
contrario). Sem a base de fusos do sistema, a queda e para UTC-8 fixo -- que e
o horario de inverno, o **mais tarde** dos dois, entao no verao a gente zera
uma hora depois do YouTube. Errar para o lado de segurar o upload e o lado
certo de errar.

Em disco pelo mesmo motivo do orcamento de LLM (`llm_cascade`): sobrevive a
restart e e compartilhado pelas duas instancias durante um deploy, porque as
duas enxergam o mesmo `output/`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

#: Custo publicado de um `videos.insert`.
CUSTO_INSERT = 1600
#: Teto diario padrao de um projeto novo na API do YouTube.
TETO_PADRAO = 10000

ARQUIVO = ".youtube_quota.json"


def teto_diario() -> int:
    """`YOUTUBE_QUOTA_DAILY` manda, para quem conseguiu aumento de quota."""
    try:
        valor = int(os.environ.get("YOUTUBE_QUOTA_DAILY") or TETO_PADRAO)
    except ValueError:
        return TETO_PADRAO
    return valor if valor > 0 else TETO_PADRAO


def uploads_por_dia() -> int:
    """Quantos `videos.insert` cabem no teto. Seis, com os numeros padrao."""
    return max(0, teto_diario() // CUSTO_INSERT)


def _caminho() -> str:
    d = (os.environ.get("OUTPUT_DIR") or "output").strip() or "output"
    return os.path.join(d, ARQUIVO)


def dia_do_youtube(agora: datetime | None = None) -> str:
    """A data ISO no fuso em que a quota zera."""
    agora = agora or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return agora.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        # Sem tzdata no sistema. UTC-8 e o horario de inverno: no verao zeramos
        # uma hora depois do YouTube, que e segurar upload em vez de tentar um
        # que seria recusado.
        return agora.astimezone(timezone(timedelta(hours=-8))).strftime("%Y-%m-%d")


def _ler() -> dict:
    try:
        with open(_caminho(), "r", encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {"dia": dia_do_youtube(), "unidades": 0, "uploads": 0}
    if not isinstance(dados, dict) or dados.get("dia") != dia_do_youtube():
        return {"dia": dia_do_youtube(), "unidades": 0, "uploads": 0}
    dados.setdefault("unidades", 0)
    dados.setdefault("uploads", 0)
    return dados


def _gravar(dados: dict) -> None:
    caminho = _caminho()
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        tmp = f"{caminho}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(dados, fh)
        os.replace(tmp, caminho)    # troca atomica, como o orcamento de LLM
    except OSError:
        pass
    # Melhor-esforco, como o orcamento de LLM: duas publicacoes simultaneas
    # podem ler o mesmo valor e uma das somas se perder. O arquivo nunca
    # corrompe (a troca e atomica) e o erro e de UM upload a mais, que o
    # YouTube recusa com `quotaExceeded` -- o que o driver ja traduz em
    # "caiu na fila manual" em vez de job vermelho. Um lock de arquivo para
    # isso custaria mais que o erro que evita.


def usadas() -> int:
    try:
        return max(0, int(_ler().get("unidades") or 0))
    except (TypeError, ValueError):
        return 0


def restante() -> int:
    return max(0, teto_diario() - usadas())


def cabe(custo: int = CUSTO_INSERT) -> bool:
    """Se ainda ha quota para um `videos.insert` hoje."""
    return restante() >= max(0, int(custo))


def registrar(custo: int = CUSTO_INSERT, upload: bool = True) -> int:
    """Soma o custo ao dia e devolve o que sobrou.

    **Chamado ANTES da chamada, nao depois.** A quota do YouTube e debitada
    quando a requisicao e aceita, e um upload que estoura no meio ja gastou as
    1600 unidades -- contar so no sucesso deixaria o contador abaixo da
    verdade justamente no dia em que as coisas dao errado, que e quando ele
    precisa estar certo.
    """
    dados = _ler()
    try:
        dados["unidades"] = int(dados.get("unidades") or 0) + max(0, int(custo))
    except (TypeError, ValueError):
        dados["unidades"] = max(0, int(custo))
    if upload:
        dados["uploads"] = int(dados.get("uploads") or 0) + 1
    _gravar(dados)
    return max(0, teto_diario() - dados["unidades"])


def estado() -> dict:
    """O que o painel desenha para explicar por que um corte caiu na fila."""
    dados = _ler()
    usado = max(0, int(dados.get("unidades") or 0))
    return {
        "dia": dados.get("dia"),
        "teto": teto_diario(),
        "usadas": usado,
        "restante": max(0, teto_diario() - usado),
        "uploads_hoje": int(dados.get("uploads") or 0),
        "uploads_por_dia": uploads_por_dia(),
        "cabe_mais_um": cabe(),
    }
