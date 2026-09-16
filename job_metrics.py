"""Custo de um job: tempo de parede e tokens, por estagio.

Por que existe (docs/PLANO-DE-ACAO.md, bloco 0.5): meia hora de trabalho que
converte a calibracao do pre-filtro da Fase 1 de achismo em medicao, e da
resposta a pergunta que hoje nao tem nenhuma -- "quanto custou aquele video de
40 minutos?". Sem isso, o ADR-004 fica sendo estimativa: sabemos que uma live
de 4h *deveria* consumir ~75.000 tokens, mas nunca medimos um video real.

O que o upstream ja tinha era fragmentado e nao sobrevivia ao job: `stage_seconds`
de detect/write dentro do laco de reframe, e prints soltos de download e de
reframe. Nada agregado, nada persistido, nada sobre tokens.

**Grava em arquivo, nao em banco.** O campo `timings_json` da tabela `jobs` da
secao 7 do Plano Tecnico e o destino final, mas aquela tabela so nasce na Fase
0.5 -- e o caminho self-host nao tem banco nenhum hoje (ADR-008). Enquanto
isso, o sidecar `<base>.timings.json` fica junto dos outros arquivos de estado
que o job ja escreve no seu diretorio, com a mesma forma que a coluna vai ter.
Quando a tabela existir, e um INSERT lendo este dict.

A atribuicao de tokens a estagio e automatica: o coletor mantem a pilha de
estagios abertos, entao `add_llm` credita a chamada a quem esta por cima sem o
chamador precisar saber onde esta. E o que permite instrumentar o LLM num lugar
so (`main._run_llm_stage`) em vez de em cada sitio de chamada.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from typing import Optional

_job: dict = {}

#: Protege `_job` e `_abertos`. O laco de cortes do `main.py` roda em
#: `ThreadPoolExecutor` (`CLIP_WORKERS`, 3 por padrao), entao varias threads
#: medem o MESMO estagio ao mesmo tempo.
_lock = threading.RLock()

#: A pilha de estagios abertos, **por thread**. Era global, e num pool de
#: cortes isso credita a chamada de LLM de um worker ao estagio de outro: quem
#: estiver no topo da pilha compartilhada na hora ganha os tokens, e quem
#: ganha depende do escalonador. Por thread, cada worker credita ao proprio.
_local = threading.local()

#: `(sub, nome) -> {"n": abertos agora, "t0": quando o primeiro abriu}`. E o
#: que permite medir PAREDE alem de OCUPADO -- ver `_medir`.
_abertos: dict = {}


def _pilha() -> list:
    p = getattr(_local, "pilha", None)
    if p is None:
        p = []
        _local.pilha = p
    return p


def reset(output_dir: str = ".", base_name: str = "job") -> None:
    """Zera o coletor para um job novo."""
    global _job
    with _lock:
        _job = {
            "base_name": base_name,
            "output_dir": output_dir,
            "started_at": time.time(),
            # nome -> {seconds, wall_seconds, entries, calls, tokens_in,
            #          tokens_out, providers}
            "stages": {},
            "substages": {},  # medidos DENTRO de um estagio; nao somam com ele
            "facts": {},      # duracao da fonte, duracao falada, n de cortes...
        }
        _abertos.clear()
    _pilha().clear()


def set_destination(output_dir: str, base_name: str) -> None:
    """Onde gravar o sidecar, depois que o job resolveu isso.

    Separado do `reset` de proposito: o estagio 01 (ingest) e medido antes de
    `output_dir` e do titulo existirem, e um reset ali apagaria a medicao.
    """
    if _job:
        _job["output_dir"] = output_dir or "."
        _job["base_name"] = base_name or "job"


def _slot(name: str, sub: bool = False) -> dict:
    onde = "substages" if sub else "stages"
    return _job.setdefault(onde, {}).setdefault(
        name, {"seconds": 0.0, "wall_seconds": 0.0, "entries": 0, "calls": 0,
               "tokens_in": 0, "tokens_out": 0, "providers": {}})


def _aberto_agora() -> tuple:
    """`(nome, sub)` do passe aberto nesta thread, ou o balde de fora.

    Devolve o par e nao so o nome porque `add_llm` precisa saber em QUAL
    dicionario creditar: o `hook_grounding` chama o Gemini de dentro de um
    substage, e procurar o nome nos dois dicionarios erra enquanto o slot ainda
    nao existe -- os tokens iam para `stages` e nunca saiam de la.
    """
    p = _pilha()
    return p[-1] if p else ("sem_estagio", False)


#: Prefixo do marcador que o `app.py` le no stdout para saber em que estagio o
#: job esta. Existe porque o `main.py` e um subprocesso e o stdout ja e o canal
#: entre os dois -- o `app.py` le linha a linha para montar o log. Anunciar o
#: estagio por aqui custa uma linha e nao inventa um segundo canal (socket,
#: arquivo de estado, polling de disco) so para desenhar uma barra.
#:
#: O `app.py` consome e **descarta** estas linhas, entao elas nunca aparecem no
#: log que o painel mostra.
STAGE_MARKER = "__STAGE__"


@contextmanager
def _medir(name: str, sub: bool, marcar: bool):
    """O motor de `stage` e `substage`. Mede DUAS grandezas, e sao diferentes.

    **`seconds` e OCUPADO; `wall_seconds` e PAREDE.** Num estagio sequencial as
    duas coincidem. No laco de cortes nao: com `CLIP_WORKERS=3`, tres workers
    medem `05_06_render` ao mesmo tempo, e somar a duracao de cada um da o
    trabalho gasto (util: sao CPU-segundos), **nao** o tempo que a pessoa
    esperou. A versao anterior so somava, entao um render de 200 s de parede
    reportava 600 s -- fatia de 1,0 sobre a parede do job, `fora_de_estagio`
    negativo (silenciado por um `max(0, ...)`) e, porque o relatorio escolhe o
    primeiro estagio acima de 50%, a transcricao acusada no lugar do render.
    Um instrumento que aponta o culpado errado e pior que nenhum.

    A parede e a **uniao dos intervalos**, calculada na entrada: `n` conta
    quantos estao abertos com este nome, `t0` guarda quando o primeiro abriu, e
    so quando o ultimo fecha e que o trecho inteiro entra. Sobreposicao conta
    uma vez; um estagio que abre e fecha varias vezes soma cada trecho.

    `marcar` separa as duas funcoes que a versao anterior misturava: o marcador
    no stdout e a BARRA DE PROGRESSO do painel, que so conhece os cinco nomes
    de `app.PIPELINE_STAGES` -- um nome fora dessa lista vira `stage_index` 0,
    ou seja, a barra volta para o comeco. Medicao fina nao pode custar isso,
    entao `substage` mede sem anunciar.
    """
    if not _job:
        reset()
    _pilha().append((name, sub))
    with _lock:
        # O slot nasce na ENTRADA e nao na saida: `add_llm` credita ao passe
        # aberto, e um passe aberto tem de existir para ser creditado.
        _slot(name, sub)
    if marcar:
        # O `flush` e obrigatorio: o stdout do subprocesso e um pipe, logo
        # bufferizado em blocos, e sem ele o marcador chegaria minutos depois
        # -- tarde demais para servir de progresso.
        print(f"{STAGE_MARKER}BEGIN {name}", flush=True)
    t0 = time.time()
    with _lock:
        a = _abertos.setdefault((sub, name), {"n": 0, "t0": t0})
        if a["n"] == 0:
            a["t0"] = t0
        a["n"] += 1
    try:
        yield
    finally:
        t1 = time.time()
        with _lock:
            s = _slot(name, sub)
            s["seconds"] += t1 - t0
            s["entries"] += 1
            a = _abertos.get((sub, name))
            if a is not None:
                a["n"] -= 1
                if a["n"] <= 0:
                    a["n"] = 0
                    s["wall_seconds"] += t1 - a["t0"]
        p = _pilha()
        if p and p[-1] == (name, sub):
            p.pop()
        if marcar:
            print(f"{STAGE_MARKER}END {name}", flush=True)


def stage(name: str):
    """Um estagio do pipeline: mede e move a barra de progresso.

    Reentrante e acumulativo: chamar o mesmo nome de novo soma ao total, que e o
    que se quer no laco de cortes (`05_06_render` roda uma vez por corte).

    O nome precisa estar em `app.PIPELINE_STAGES`, ou a barra volta ao inicio.
    Para medir por dentro de um estagio, use `substage`.
    """
    return _medir(name, sub=False, marcar=True)


def substage(name: str):
    """Um pedaco DENTRO de um estagio: mede sem mexer na barra.

    Existe para o laco de cortes, onde a barra tem de continuar dizendo
    "cortando e renderizando" enquanto a medicao separa o corte, o
    reenquadramento, o gancho e a legenda -- cada um um encode inteiro.

    Nao soma com os estagios: `snapshot` os devolve em `substages`, e somar as
    duas listas contaria o mesmo tempo duas vezes.
    """
    return _medir(name, sub=True, marcar=False)


def current_stage() -> Optional[str]:
    p = _pilha()
    return p[-1][0] if p else None


def add_llm(cost: Optional[dict]) -> None:
    """Credita uma chamada de LLM ao estagio aberto.

    `cost` e o dict que `main._run_gemini_stage` e `llm_backend.generate_json`
    ja devolvem -- nao ha formato novo a manter.
    """
    if not _job or not cost:
        return
    entrada = int(cost.get("input_tokens") or 0)
    saida = int(cost.get("output_tokens") or 0)
    prov = str(cost.get("provider") or cost.get("model") or "desconhecido")
    nome, sub = _aberto_agora()
    with _lock:
        s = _slot(nome, sub)
        s["calls"] += 1
        s["tokens_in"] += entrada
        s["tokens_out"] += saida
        p = s["providers"].setdefault(prov, {"calls": 0, "tokens": 0})
        p["calls"] += 1
        p["tokens"] += entrada + saida


def fact(key: str, value) -> None:
    with _lock:
        if _job:
            _job.setdefault("facts", {})[key] = value


def spoken_seconds_from(transcript: Optional[dict]) -> float:
    """Duracao **falada**, somando os segmentos -- nao a duracao do arquivo.

    E a grandeza que o §4 do plano diz governar o custo: "o custo de processar
    cresce com a duracao falada, nao com o tamanho do arquivo". Uma live de 4h
    com metade de silencio custa metade.
    """
    if not transcript:
        return 0.0
    total = 0.0
    for seg in transcript.get("segments") or []:
        try:
            total += max(0.0, float(seg["end"]) - float(seg["start"]))
        except (KeyError, TypeError, ValueError):
            continue
    return round(total, 1)


def totals() -> dict:
    """Os totais do job.

    `seconds` soma a PAREDE dos estagios, nao o ocupado: e o numero que se
    compara com `wall_seconds` para saber quanto do job ficou fora de estagio
    nenhum. O ocupado sai em `busy_seconds`, que num laco paralelo e maior.

    Chamadas e tokens somam estagios **e** substages -- um token gasto dentro
    do laco de cortes (o `hook_grounding` chama o Gemini por corte) e um token
    gasto, e omiti-lo aqui subestimaria a conta do job.
    """
    with _lock:
        st = list(_job.get("stages", {}).values())
        sub = list(_job.get("substages", {}).values())
    todos = st + sub
    return {
        "seconds": round(sum(s.get("wall_seconds", s["seconds"]) for s in st), 1),
        "busy_seconds": round(sum(s["seconds"] for s in st), 1),
        "calls": sum(s["calls"] for s in todos),
        "tokens": sum(s["tokens_in"] + s["tokens_out"] for s in todos),
    }


def _vista(slots: dict) -> dict:
    return {k: {"seconds": round(v["seconds"], 2),
                "wall_seconds": round(v.get("wall_seconds", v["seconds"]), 2),
                "entries": v.get("entries", 0),
                "calls": v["calls"],
                "tokens_in": v["tokens_in"], "tokens_out": v["tokens_out"],
                "providers": dict(v["providers"])}
            for k, v in slots.items()}


def snapshot() -> dict:
    """O dict que vai para o sidecar, e um dia para `jobs.timings_json`.

    Cada estagio traz `seconds` (ocupado) **e** `wall_seconds` (parede). Um
    sidecar anterior a esta mudanca so tem `seconds`, e quem le tem de cair
    para ele -- `timings_report` faz isso, porque os primeiros jobs medidos
    sao justamente os que ninguem tinha lido ainda.
    """
    if not _job:
        return {}
    with _lock:
        out = {
            "facts": dict(_job.get("facts", {})),
            "stages": _vista(_job.get("stages", {})),
            "substages": _vista(_job.get("substages", {})),
            "totals": totals(),
            "wall_seconds": round(time.time() - _job.get("started_at", time.time()), 1),
        }
    spoken = out["facts"].get("spoken_seconds")
    tokens = out["totals"]["tokens"]
    if spoken and tokens:
        # A razao que a Fase 1 vai usar para calibrar o pre-filtro: quantos
        # tokens cada minuto de fala custou neste job.
        out["totals"]["tokens_per_spoken_minute"] = round(tokens / (spoken / 60.0), 1)
    return out


def summary_line() -> str:
    """Uma linha por estagio, no stdout -- que e o log do job (ver Fase 0.2)."""
    if not _job:
        return ""
    snap = snapshot()

    def _linha(nome, s, recuo=""):
        # A parede e o que a pessoa esperou; o ocupado so aparece quando for
        # maior, que e o sinal de que aquele estagio rodou em paralelo.
        parte = f"   {recuo + nome:<20} {s['wall_seconds']:>8.1f}s"
        if s["seconds"] - s["wall_seconds"] > 0.5:
            parte += f" (ocupado {s['seconds']:.0f}s em {s['entries']}x)"
        if s["calls"]:
            tot = s["tokens_in"] + s["tokens_out"]
            quem = ", ".join(sorted(s["providers"]))
            parte += f"  {s['calls']} chamada(s)  {tot} tokens  [{quem}]"
        return parte

    linhas = ["📊 Custo deste job:"]
    for nome, s in sorted(snap["stages"].items()):
        linhas.append(_linha(nome, s))
    for nome, s in sorted(snap.get("substages", {}).items()):
        linhas.append(_linha(nome, s, recuo="└ "))
    t = snap["totals"]
    linhas.append(f"   {'TOTAL':<20} {snap['wall_seconds']:>8.1f}s"
                  f"  {t['calls']} chamada(s)  {t['tokens']} tokens")
    if t.get("tokens_per_spoken_minute"):
        fala = snap["facts"].get("spoken_seconds", 0) / 60.0
        linhas.append(f"   {fala:.1f} min de fala → "
                      f"{t['tokens_per_spoken_minute']:.0f} tokens/min falado")
    return "\n".join(linhas)


def write() -> Optional[str]:
    """Grava `<base>.timings.json` no diretorio do job. Melhor-esforco."""
    if not _job:
        return None
    path = os.path.join(_job.get("output_dir") or ".",
                        f"{_job.get('base_name') or 'job'}.timings.json")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(snapshot(), fh, indent=2, ensure_ascii=False)
        return path
    except OSError:
        return None      # medicao nunca quebra o job
