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

#: Os passes medidos DENTRO de `05_06_render`, na ordem em que um corte os
#: atravessa. Cada um e um encode inteiro do clipe (menos o hook grounding, que
#: e uma chamada de LLM), e ate 16-set-2026 todos eram invisiveis.
ORDEM_DOS_SUBESTAGIOS = ("05_corte", "06_reenquadra", "06_marca_dagua",
                         "06_hook_grounding", "06_gancho", "06_legenda")

#: Acima desta razao entre a soma dos estagios e a parede do job, a medida nao
#: fecha. O caso real e o dado anterior a 16-set-2026: o laco de cortes somava
#: a duracao de cada worker no mesmo estagio, entao com `CLIP_WORKERS=3` o
#: render vinha ate 3x. A folga de 2% e arredondamento.
TOLERANCIA_DE_SOMA = 1.02


def _numero(valor, padrao=0.0) -> float:
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return padrao
    return n if n == n and n not in (float("inf"), float("-inf")) else padrao


def _parede_do_estagio(slot: dict) -> float:
    """Quanto tempo o job passou NESTE estagio -- parede, nao ocupado.

    `wall_seconds` so existe a partir de 16-set-2026. Antes havia so `seconds`,
    que no laco paralelo de cortes e a SOMA dos workers: um render de 200 s com
    `CLIP_WORKERS=3` gravou 600 s. Cair para `seconds` e o certo mesmo assim --
    e o unico numero que aquele job tem, e nos estagios sequenciais (que sao
    quatro dos cinco) as duas grandezas coincidem. Quem avisa que o numero do
    render nao fecha e `medida_inflada`.
    """
    parede = _numero(slot.get("wall_seconds"), padrao=-1.0)
    return parede if parede >= 0 else _numero(slot.get("seconds"))


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
        parede = sum(_parede_do_estagio(v)
                     for v in estagios.values() if isinstance(v, dict))
    fonte = _numero(fatos.get("source_seconds"))
    falada = _numero(fatos.get("spoken_seconds"))
    por_estagio = {nome: _parede_do_estagio(v)
                   for nome, v in estagios.items() if isinstance(v, dict)}
    subestagios = timings.get("substages") or {}
    if not isinstance(subestagios, dict):
        subestagios = {}
    soma = sum(por_estagio.values())
    return {
        "wall_seconds": round(parede, 1),
        "source_seconds": round(fonte, 1),
        "spoken_seconds": round(falada, 1),
        "tokens": int(_numero(totais.get("tokens"))),
        "calls": int(_numero(totais.get("calls"))),
        # Zero e "nao medido" aqui: sem a duracao da fonte nao da para dizer se
        # 40 minutos foi rapido ou lento, e inventar 1,0x seria pior que nada.
        "fator_tempo_real": round(parede / fonte, 2) if fonte > 0 else None,
        "estagios": {n: round(s, 1) for n, s in por_estagio.items()},
        "substages": {nome: round(_parede_do_estagio(v), 1)
                      for nome, v in subestagios.items() if isinstance(v, dict)},
        # A soma dos estagios nao cabe na parede do job: medida de antes do
        # conserto de 16-set-2026. Vale registrar, nao esconder -- e a unica
        # forma de quem le saber que a ordem de culpa daquele job nao serve.
        "medida_inflada": bool(parede > 0 and soma > parede * TOLERANCIA_DE_SOMA),
    }


def agregar(varios: Iterable[Optional[dict]]) -> dict:
    """O relatorio sobre um conjunto de jobs."""
    resumos = [r for r in (resumo_de_um(t) for t in varios) if r]
    if not resumos:
        return {"jobs": 0, "estagios": [], "fator_tempo_real": None,
                "wall_seconds": 0.0, "source_seconds": 0.0,
                "substages": [], "jobs_com_medida_inflada": 0,
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

    por_sub: dict = {}
    for r in resumos:
        for nome, seg in (r.get("substages") or {}).items():
            por_sub[nome] = por_sub.get(nome, 0.0) + seg

    def _ordem_sub(nome: str):
        return (ORDEM_DOS_SUBESTAGIOS.index(nome)
                if nome in ORDEM_DOS_SUBESTAGIOS else len(ORDEM_DOS_SUBESTAGIOS))

    # A fatia do substage e sobre a parede do JOB, e nao sobre a do render: a
    # pergunta que se faz olhando esta lista e "quanto do job foi queimar
    # legenda?", que so tem resposta na mesma escala das outras linhas.
    substages = [{"estagio": nome,
                  "seconds": round(seg, 1),
                  "fatia": round(seg / parede, 3) if parede > 0 else None}
                 for nome, seg in sorted(por_sub.items(), key=lambda kv: _ordem_sub(kv[0]))]

    inflados = sum(1 for r in resumos if r.get("medida_inflada"))
    em_estagios = sum(por_estagio.values())
    agregado = {
        "jobs": len(resumos),
        "substages": substages,
        # Quantos jobs desta amostra foram medidos com o laco de cortes somando
        # os workers. Neles a fatia do render vem multiplicada e a ordem de
        # culpa nao vale -- e a observacao diz isso em vez de o `max(0, ...)`
        # abaixo esconder a conta que nao fecha.
        "jobs_com_medida_inflada": inflados,
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

    # Antes de qualquer conclusao: dizer quando o proprio numero nao fecha. A
    # versao anterior calava isto -- somava os workers no estagio do render e
    # depois clampava a sobra negativa com `max(0, ...)`, entao o relatorio saia
    # plausivel, com fatias somando mais de 100%, e acusava o primeiro estagio
    # acima de 50% na ordem do pipeline: a transcricao, no lugar do render.
    inflados = int(_numero(agregado.get("jobs_com_medida_inflada")))
    if inflados:
        saida.append(
            f"{inflados} job(s) desta amostra foram medidos antes de "
            "16-set-2026, quando o laco de cortes somava o tempo de cada "
            "worker no mesmo estagio: neles o render aparece multiplicado por "
            "ate `CLIP_WORKERS` e a soma dos estagios passa da parede. Os "
            "estagios sequenciais valem; a ordem de culpa, nao. Rode um job "
            "novo para ter o numero certo.")

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

    # Dentro do render, QUAL passe. E o que o bloco 5.3 nao respondia: a
    # cadeia de um corte e corte -> reenquadra -> [marca] -> [gancho] ->
    # legenda, e cada seta e um encode inteiro do clipe.
    dominante_sub = None
    for e in agregado.get("substages") or []:
        if e.get("fatia") and (dominante_sub is None
                               or e["fatia"] > dominante_sub["fatia"]):
            dominante_sub = e
    if dominante_sub and dominante_sub["fatia"] >= 0.15:
        pct = int(dominante_sub["fatia"] * 100)
        saida.append(
            f"Dentro do render, o passe mais caro e {dominante_sub['estagio']} "
            f"({pct}% da parede do job).")
        if dominante_sub["estagio"] == "06_hook_grounding":
            saida.append(
                "Esse passe nao e encode: e uma chamada de LLM por corte "
                "(tres quadros a 1024px). `HOOK_GROUNDING=0` desliga.")

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
