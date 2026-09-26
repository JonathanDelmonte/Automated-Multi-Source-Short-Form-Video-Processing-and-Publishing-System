"""O contador de quota do YouTube -- Fase 3, bloco 3.4; cota nova na etapa 7.3.

**Sao duas cotas, e o envio tem a sua.** Um projeto na API do YouTube recebe,
por dia, **100 chamadas de `videos.insert`**, 100 de `search.list` e **10.000
unidades para todo o resto** (conferido na documentacao do Google em 25 e
26-set-2026). O envio saiu das 10.000 unidades: em dez-2025 caiu de 1.600 para
~100 unidades por chamada, e desde 1-jun-2026 mora numa cota propria, contada
em chamadas.

Ate a 7.3 este contador seguia a regra antiga -- 1.600 unidades por envio
contra 10.000, **6 envios por dia** -- e o agendador herdava o 6. Errava para o
lado de segurar, e por isso ninguem percebeu: a correcao veio da leitura da
documentacao, nao de um erro. O numero novo esta congelado num teste, para que
volte a ser uma decisao se mudar outra vez.

O contador existe para que o envio que nao cabe **caia na fila manual em vez de
falhar**. Sem ele a API responde `quotaExceeded`, o job fica vermelho e o corte
se perde de vista -- o oposto do que a cascata da secao 6 promete.

A cota de envio e do PROJETO no Google Cloud, nao do canal: todas as contas do
YouTube ligadas com o mesmo cadastro de aplicativo dividem as 100. Um contador
por instalacao e o mesmo que um por projeto no caso de sempre (uma pessoa, um
cadastro, como decidido em 26-set-2026) e erra para o lado de segurar no resto.

**O dia e o do Pacifico, nao o nosso.** A quota zera a meia-noite no horario
do Pacifico; contar em UTC daria uma janela de 7 a 8 horas por dia em que o
contador acha que tem quota e a API discorda (ou o contrario). Sem a base de
fusos do sistema, a queda e para UTC-8 fixo -- o horario de inverno, o **mais
tarde** dos dois, entao no verao a gente zera uma hora depois do YouTube.
Errar para o lado de segurar o upload e o lado certo de errar.

Em disco pelo mesmo motivo do orcamento de LLM (`llm_cascade`): sobrevive a
restart e e compartilhado pelas duas instancias durante um deploy, porque as
duas enxergam o mesmo `output/`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

#: Chamadas de `videos.insert` por dia, na cota propria do envio.
UPLOADS_POR_DIA_PADRAO = 100
#: Unidades por dia para as outras chamadas (o `videos.list` do coletor de
#: metricas, por exemplo). O envio NAO sai daqui desde jun-2026.
TETO_PADRAO = 10000
#: Chamadas de `search.list` por dia, na cota propria da busca (desde
#: jun-2026, como o envio). E o que a busca de videos com licenca da
#: automacao (etapa 7.5) gasta quando vai pela API.
BUSCAS_POR_DIA_PADRAO = 100

ARQUIVO = ".youtube_quota.json"


def _inteiro_positivo(variavel: str, padrao: int) -> int:
    try:
        valor = int(os.environ.get(variavel) or padrao)
    except ValueError:
        return padrao
    return valor if valor > 0 else padrao


def uploads_por_dia() -> int:
    """`YOUTUBE_UPLOADS_DAILY` manda, para quem conseguiu mais cota de envio."""
    return _inteiro_positivo("YOUTUBE_UPLOADS_DAILY", UPLOADS_POR_DIA_PADRAO)


def teto_diario() -> int:
    """As unidades das OUTRAS chamadas. `YOUTUBE_QUOTA_DAILY` manda."""
    return _inteiro_positivo("YOUTUBE_QUOTA_DAILY", TETO_PADRAO)


def buscas_por_dia() -> int:
    """`YOUTUBE_SEARCHES_DAILY` manda, para quem conseguiu mais cota de busca."""
    return _inteiro_positivo("YOUTUBE_SEARCHES_DAILY", BUSCAS_POR_DIA_PADRAO)


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


def _vazio() -> dict:
    return {"dia": dia_do_youtube(), "unidades": 0, "uploads": 0, "buscas": 0}


def _ler() -> dict:
    try:
        with open(_caminho(), "r", encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return _vazio()
    if not isinstance(dados, dict) or dados.get("dia") != dia_do_youtube():
        return _vazio()
    dados.setdefault("unidades", 0)
    dados.setdefault("uploads", 0)
    dados.setdefault("buscas", 0)
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


def _contagem(dados: dict, campo: str) -> int:
    try:
        return max(0, int(dados.get(campo) or 0))
    except (TypeError, ValueError):
        return 0


# --- O envio ------------------------------------------------------------------

def uploads_hoje() -> int:
    return _contagem(_ler(), "uploads")


def uploads_restantes() -> int:
    return max(0, uploads_por_dia() - uploads_hoje())


def cabe() -> bool:
    """Se ainda cabe um `videos.insert` hoje."""
    return uploads_restantes() > 0


def registrar_upload() -> int:
    """Conta um envio e devolve quantos ainda cabem hoje.

    **Chamado ANTES da chamada, nao depois.** A quota e debitada quando a
    requisicao e aceita, e um upload que estoura no meio ja gastou o envio --
    contar so no sucesso deixaria o contador abaixo da verdade justamente no
    dia em que as coisas dao errado, que e quando ele precisa estar certo.
    """
    dados = _ler()
    dados["uploads"] = _contagem(dados, "uploads") + 1
    _gravar(dados)
    return max(0, uploads_por_dia() - dados["uploads"])


# --- A busca (etapa 7.5) ------------------------------------------------------

def buscas_hoje() -> int:
    return _contagem(_ler(), "buscas")


def cabe_busca() -> bool:
    """Se ainda cabe um `search.list` hoje. Sem cota, a automacao busca pelo
    yt-dlp, que nao gasta cota nenhuma."""
    return buscas_hoje() < buscas_por_dia()


def registrar_busca() -> int:
    """Conta uma busca, ANTES da chamada, pelo mesmo motivo do envio."""
    dados = _ler()
    dados["buscas"] = _contagem(dados, "buscas") + 1
    _gravar(dados)
    return max(0, buscas_por_dia() - dados["buscas"])


# --- As outras chamadas -------------------------------------------------------

def usadas() -> int:
    """Unidades das outras chamadas gastas hoje."""
    return _contagem(_ler(), "unidades")


def restante() -> int:
    return max(0, teto_diario() - usadas())


def cabe_unidades(custo: int) -> bool:
    return restante() >= max(0, int(custo))


def registrar_unidades(custo: int) -> int:
    """Soma o custo de uma chamada que nao e envio e devolve o que sobrou."""
    dados = _ler()
    dados["unidades"] = _contagem(dados, "unidades") + max(0, int(custo))
    _gravar(dados)
    return max(0, teto_diario() - dados["unidades"])


def estado() -> dict:
    """O que o painel desenha para explicar por que um corte caiu na fila."""
    dados = _ler()
    envios = _contagem(dados, "uploads")
    unidades = _contagem(dados, "unidades")
    return {
        "dia": dados.get("dia"),
        "uploads_hoje": envios,
        "uploads_por_dia": uploads_por_dia(),
        "uploads_restantes": max(0, uploads_por_dia() - envios),
        "cabe_mais_um": envios < uploads_por_dia(),
        # A busca da automacao (7.5), na cota propria dela.
        "buscas_hoje": _contagem(dados, "buscas"),
        "buscas_por_dia": buscas_por_dia(),
        # As unidades das outras chamadas.
        "teto": teto_diario(),
        "usadas": unidades,
        "restante": max(0, teto_diario() - unidades),
    }
