"""O limite de posts por conta da frota -- etapa 7.9 (ADR-016).

Cada conta que posta por um aparelho tem um limite por dia (3 de padrao, 15 de
teto duro: o menor das vias oficiais, o do TikTok). O contador mora em disco,
como o da cota do YouTube (`publishers/quota.py`), pelo mesmo motivo: sobrevive
a um reinicio, e o driver o le sem banco (ele roda numa thread, fora do laco
async).

**Debita ANTES de tocar no aparelho, e devolve quando nada aconteceu** (o
aparelho estava fora do ar, o video nao chegou). Contar so no fim deixaria o
contador abaixo da verdade justamente quando o post saiu e a confirmacao nao.

Vale para os dois drivers da frota: o de entrega tambem abre o app, e um laco
que abrisse cinquenta vezes seria o defeito que a 7.3a achou no agendador.

O dia e o de quem usa: o chamador passa a data (`frota.hoje_de`), porque o
fuso e por tenant e esta thread nao sabe de tenant nenhum.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Optional

ARQUIVO = os.path.join("frota", "limite.json")
#: Quantos dias de contagem ficam no arquivo: o de hoje e alguns para tras,
#: que a tela usa para mostrar o que a conta postou na semana.
DIAS_GUARDADOS = 8

_TRAVA = threading.Lock()


def _caminho() -> str:
    base = (os.environ.get("DATA_DIR") or "").strip() or "data"
    return os.path.join(base, ARQUIVO)


def _ler() -> dict:
    try:
        with open(_caminho(), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _gravar(dados: dict) -> None:
    caminho = _caminho()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, sort_keys=True)
    os.replace(temporario, caminho)


def usados(conta: str, dia: str) -> int:
    with _TRAVA:
        return int((_ler().get(conta) or {}).get(dia) or 0)


def cabe(conta: str, dia: str, limite: int) -> bool:
    return usados(conta, dia) < max(0, int(limite))


def debitar(conta: str, dia: str, limite: int) -> bool:
    """Reserva um post de hoje para a conta; False quando o limite ja foi.

    Ler e gravar sob a mesma trava: dois posts da mesma conta ao mesmo tempo (o
    agendador e um "publicar agora") nao passam os dois pelo ultimo lugar."""
    with _TRAVA:
        dados = _ler()
        da_conta = dados.setdefault(conta, {})
        atual = int(da_conta.get(dia) or 0)
        if atual >= max(0, int(limite)):
            return False
        da_conta[dia] = atual + 1
        for velho in sorted(da_conta)[:-DIAS_GUARDADOS]:
            da_conta.pop(velho, None)
        _gravar(dados)
        return True


def devolver(conta: str, dia: str) -> None:
    """Desfaz um `debitar` cujo post nem chegou ao aparelho."""
    with _TRAVA:
        dados = _ler()
        da_conta = dados.get(conta) or {}
        atual = int(da_conta.get(dia) or 0)
        if atual <= 0:
            return
        da_conta[dia] = atual - 1
        dados[conta] = da_conta
        _gravar(dados)


def semana(conta: str) -> dict:
    """{dia: posts} dos dias guardados, para a tela."""
    with _TRAVA:
        return dict(_ler().get(conta) or {})


def esquecer(conta: str) -> Optional[dict]:
    """A conta saiu da frota: a contagem dela sai junto."""
    with _TRAVA:
        dados = _ler()
        saiu = dados.pop(conta, None)
        if saiu is not None:
            _gravar(dados)
        return saiu
