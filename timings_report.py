"""Onde vai o tempo -- Fase 5.

O `job_metrics` mede por estagio desde a Fase 0.5 e o bloco 3.3 grava o dict em
`jobs.timings_json`. Ate aqui ninguem lia isso ENTRE jobs: cada execucao
imprimia o proprio resumo no log e o numero morria ali.

A Fase 5 diz que "a instrumentacao da Fase 0.5 e o que alimenta" a calibracao.
Este modulo e a leitura dela.

**Ele mede, e nao conserta.** A tentacao, diante de "esta lento", e abrir o
`main.py` e procurar o culpado. Este projeto vem recusando esse movimento em
toda decisao -- o pre-filtro corta por orcamento e nao por qualidade, o layout
picker responde entre opcoes fechadas e nao com uma medida, o ADR-006 recusou
virar um numero nao sabido em constante. Chutar entre transcricao, deteccao e
render seria o mesmo erro com outra roupa. Primeiro o numero.

### O numero que importa

`fator_tempo_real` = tempo de parede ÷ duracao da fonte. Um video de 10 minutos
que leva 40 e 4,0x. E a unica grandeza que responde "esta lento" sem depender
de quao longo era o video, e a que da para comparar entre execucoes.

O segundo e a **fatia de cada estagio**. "A transcricao e 78% do tempo" aponta
para onde olhar; "o job demorou 40 minutos" nao aponta para lugar nenhum.

### Stdlib pura

Agrega listas de dicts. O CI exercita a conta inteira sem banco e sem job.
"""
from __future__ import annotations

from typing import Iterable, Optional

#: Quando um estagio passa desta fatia do tempo de parede, ele e o assunto.
FATIA_DOMINANTE = 0.5

#: Os nomes de estagio que o pipeline emite, na ordem em que acontecem. Serve
#: para ordenar o relatorio por ACONTECIMENTO e nao por tamanho -- ler na ordem
#: do pipeline e o que deixa ver onde ele engasga.
ORDEM_DOS_ESTAGIOS = ("01_ingest", "02_probe", "03_transcribe", "04_detect",
                      "05_06_render")


def _numero(valor, padrao=0.0) -> float:
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return padrao
    return n if n == n and n not in (float("inf"), float("-inf")) else padrao


def resumo_de_um(timings: Optional[dict]) -> Optional[dict]:
    """Um job, reduzido ao que o relatorio usa. None se o dict nao servir.

    Aceita dict incompleto de proposito: um job que morreu no meio gravou o que
    deu, e o pedaco que ele mediu continua valendo.
    """
    if not isinstance(timings, dict):
        return None
    fatos = timings.get("facts") or {}
    estagios = timings.get("stages") or {}
    totais = timings.get("totals") or {}
    if not isinstance(estagios, dict):
        estagios = {}
    parede = _numero(timings.get("wall_seconds"))
    if not parede:
        # Sem tempo de parede ainda da para somar os estagios -- e o que um job
        # interrompido deixa.
        parede = sum(_numero((v or {}).get("seconds"))
                     for v in estagios.values() if isinstance(v, dict))
    fonte = _numero(fatos.get("source_seconds"))
    falada = _numero(fatos.get("spoken_seconds"))
    return {
        "wall_seconds": round(parede, 1),
        "source_seconds": round(fonte, 1),
        "spoken_seconds": round(falada, 1),
        "tokens": int(_numero(totais.get("tokens"))),
        "calls": int(_numero(totais.get("calls"))),
        # Zero e "nao medido" aqui: sem a duracao da fonte nao da para dizer se
        # 40 minutos foi rapido ou lento, e inventar 1,0x seria pior que nada.
        "fator_tempo_real": round(parede / fonte, 2) if fonte > 0 else None,
        "estagios": {nome: round(_numero((v or {}).get("seconds")), 1)
                     for nome, v in estagios.items() if isinstance(v, dict)},
    }


def agregar(varios: Iterable[Optional[dict]]) -> dict:
    """O relatorio sobre um conjunto de jobs."""
    resumos = [r for r in (resumo_de_um(t) for t in varios) if r]
    if not resumos:
        return {"jobs": 0, "estagios": [], "fator_tempo_real": None,
                "wall_seconds": 0.0, "source_seconds": 0.0,
                "tokens_por_minuto_falado": None, "observacoes": []}

    parede = sum(r["wall_seconds"] for r in resumos)
    fonte = sum(r["source_seconds"] for r in resumos)
    falada = sum(r["spoken_seconds"] for r in resumos)
    tokens = sum(r["tokens"] for r in resumos)

    por_estagio: dict = {}
    for r in resumos:
        for nome, seg in r["estagios"].items():
            por_estagio[nome] = por_estagio.get(nome, 0.0) + seg

    def _ordem(nome: str):
        return (ORDEM_DOS_ESTAGIOS.index(nome)
                if nome in ORDEM_DOS_ESTAGIOS else len(ORDEM_DOS_ESTAGIOS))

    estagios = [{"estagio": nome,
                 "seconds": round(seg, 1),
                 "fatia": round(seg / parede, 3) if parede > 0 else None}
                for nome, seg in sorted(por_estagio.items(), key=lambda kv: _ordem(kv[0]))]

    em_estagios = sum(por_estagio.values())
    agregado = {
        "jobs": len(resumos),
        # O tempo de parede que nao esta em estagio NENHUM. Nao e resto de
        # arredondamento: e espera na fila, subida do subprocesso, ou um
        # pedaco do pipeline que ninguem instrumentou. Se for grande, e ele o
        # assunto -- e sem esta linha ele seria invisivel, porque cada estagio
        # pareceria pequeno sem que nada explicasse por que.
        "fora_de_estagio_seconds": round(max(0.0, parede - em_estagios), 1),
        "wall_seconds": round(parede, 1),
        "source_seconds": round(fonte, 1),
        "spoken_seconds": round(falada, 1),
        "tokens": tokens,
        "fator_tempo_real": round(parede / fonte, 2) if fonte > 0 else None,
        "tokens_por_minuto_falado": (round(tokens / (falada / 60.0), 1)
                                     if falada > 0 and tokens else None),
        "estagios": estagios,
    }
    agregado["observacoes"] = observacoes(agregado)
    return agregado


def observacoes(agregado: dict) -> list:
    """O que os numeros dizem -- e onde CONFERIR, nunca o que consertar.

    Cada observacao aponta para uma coisa verificavel que ja esta escrita neste
    repositorio. E deliberado: uma frase como "provavelmente e a CPU" viraria a
    conclusao de alguem sem ninguem ter medido, que e o erro que este modulo
    existe para nao cometer.
    """
    saida = []
    fator = agregado.get("fator_tempo_real")
    if fator:
        saida.append(
            f"Cada minuto de video custou {fator:.1f} minuto(s) de processamento.")

    parede = _numero(agregado.get("wall_seconds"))
    fora = _numero(agregado.get("fora_de_estagio_seconds"))
    if parede > 0 and fora / parede >= FATIA_DOMINANTE:
        saida.append(
            f"{int(fora / parede * 100)}% do tempo nao esta em estagio nenhum "
            "-- e espera na fila, subida do subprocesso, ou um pedaco do "
            "pipeline sem instrumentacao. Nenhum estagio explica este job.")
        return saida

    dominante = None
    for e in agregado.get("estagios") or []:
        if e.get("fatia") and e["fatia"] >= FATIA_DOMINANTE:
            dominante = e
            break

    if dominante:
        pct = int(dominante["fatia"] * 100)
        nome = dominante["estagio"]
        saida.append(f"O estagio {nome} e {pct}% do tempo de parede.")
        if nome == "03_transcribe":
            saida.append(
                "A transcricao domina. Confira se a GPU esta mesmo em uso: sem "
                "a placa reservada no container, `WHISPER_DEVICE=cuda` cai para "
                "CPU **em silencio** -- funciona, so que lento. Sao dois passos "
                "(`--build-arg GPU=1` na imagem E o docker-compose.gpu.yml).")
        elif nome == "05_06_render":
            saida.append(
                "O render domina. Ele cresce com o NUMERO de cortes, nao com a "
                "duracao da fonte -- comece conferindo quantos cortes o job "
                "produziu (ADR-006: o teto e configuravel).")
        elif nome == "04_detect":
            saida.append(
                "A deteccao domina, o que e incomum: ela e chamada de LLM, nao "
                "processamento local. Provedor lento ou muitas janelas -- o "
                "pre-filtro (ADR-004) e quem limita as janelas.")
        elif nome == "01_ingest":
            saida.append(
                "O download domina. Confira a rota de proxy no log "
                "(`PROXY_ROUTE=`): uma queda para o proxy por GB e lenta alem "
                "de cara.")

    tpm = agregado.get("tokens_por_minuto_falado")
    if tpm:
        saida.append(
            f"{tpm:.0f} tokens por minuto falado. O ADR-004 estimou ~75.000 "
            "tokens para uma live de 4 h (~313/min); este numero diz se a "
            "estimativa estava certa.")
    if agregado.get("jobs", 0) < 3:
        saida.append(
            f"Amostra de {agregado.get('jobs')} job(s) -- o suficiente para "
            "apontar onde olhar, nao para calibrar. A calibracao pede mais "
            "execucoes.")
    return saida
