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
import time
from contextlib import contextmanager
from typing import Optional

_job: dict = {}
_stack: list[str] = []


def reset(output_dir: str = ".", base_name: str = "job") -> None:
    """Zera o coletor para um job novo."""
    global _job, _stack
    _job = {
        "base_name": base_name,
        "output_dir": output_dir,
        "started_at": time.time(),
        "stages": {},     # nome -> {seconds, calls, tokens_in, tokens_out, providers}
        "facts": {},      # duracao da fonte, duracao falada, n de cortes...
    }
    _stack = []


def set_destination(output_dir: str, base_name: str) -> None:
    """Onde gravar o sidecar, depois que o job resolveu isso.

    Separado do `reset` de proposito: o estagio 01 (ingest) e medido antes de
    `output_dir` e do titulo existirem, e um reset ali apagaria a medicao.
    """
    if _job:
        _job["output_dir"] = output_dir or "."
        _job["base_name"] = base_name or "job"


def _slot(name: str) -> dict:
    return _job.setdefault("stages", {}).setdefault(
        name, {"seconds": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0,
               "providers": {}})


@contextmanager
def stage(name: str):
    """Mede o tempo de parede de um estagio e o empilha para atribuicao de tokens.

    Reentrante e acumulativo: chamar o mesmo nome de novo soma ao total, que e o
    que se quer no laco de cortes (`05_06_render` roda uma vez por corte).
    """
    if not _job:
        reset()
    _stack.append(name)
    t0 = time.time()
    try:
        yield
    finally:
        _slot(name)["seconds"] += time.time() - t0
        if _stack and _stack[-1] == name:
            _stack.pop()


def current_stage() -> Optional[str]:
    return _stack[-1] if _stack else None


def add_llm(cost: Optional[dict]) -> None:
    """Credita uma chamada de LLM ao estagio aberto.

    `cost` e o dict que `main._run_gemini_stage` e `llm_backend.generate_json`
    ja devolvem -- nao ha formato novo a manter.
    """
    if not _job or not cost:
        return
    s = _slot(current_stage() or "sem_estagio")
    s["calls"] += 1
    s["tokens_in"] += int(cost.get("input_tokens") or 0)
    s["tokens_out"] += int(cost.get("output_tokens") or 0)
    prov = str(cost.get("provider") or cost.get("model") or "desconhecido")
    p = s["providers"].setdefault(prov, {"calls": 0, "tokens": 0})
    p["calls"] += 1
    p["tokens"] += int(cost.get("input_tokens") or 0) + int(cost.get("output_tokens") or 0)


def fact(key: str, value) -> None:
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
    st = _job.get("stages", {})
    return {
        "seconds": round(sum(s["seconds"] for s in st.values()), 1),
        "calls": sum(s["calls"] for s in st.values()),
        "tokens": sum(s["tokens_in"] + s["tokens_out"] for s in st.values()),
    }


def snapshot() -> dict:
    """O dict que vai para o sidecar, e um dia para `jobs.timings_json`."""
    if not _job:
        return {}
    out = {
        "facts": dict(_job.get("facts", {})),
        "stages": {k: {"seconds": round(v["seconds"], 2), "calls": v["calls"],
                       "tokens_in": v["tokens_in"], "tokens_out": v["tokens_out"],
                       "providers": v["providers"]}
                   for k, v in _job.get("stages", {}).items()},
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
    linhas = ["📊 Custo deste job:"]
    for nome, s in sorted(snap["stages"].items()):
        parte = f"   {nome:<18} {s['seconds']:>8.1f}s"
        if s["calls"]:
            tot = s["tokens_in"] + s["tokens_out"]
            quem = ", ".join(sorted(s["providers"]))
            parte += f"  {s['calls']:>3} chamada(s)  {tot:>7} tokens  [{quem}]"
        linhas.append(parte)
    t = snap["totals"]
    linhas.append(f"   {'TOTAL':<18} {snap['wall_seconds']:>8.1f}s"
                  f"  {t['calls']:>3} chamada(s)  {t['tokens']:>7} tokens")
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
