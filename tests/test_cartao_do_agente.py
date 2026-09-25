"""O cartao "Conectar um agente de IA" (McpConnectCard.jsx, 25-set-2026).

O herdado era o do produto em nuvem do upstream: prometia "8 tools", com uma
de publicar que saiu na Fase 0.3, e apontava para o servico pago deles. Estes
testes prendem o cartao ao que o motor DE FATO oferece.
"""
import re
from pathlib import Path

import mcp_server

RAIZ = Path(__file__).resolve().parent.parent
CARTAO = (RAIZ / "dashboard/src/components/McpConnectCard.jsx").read_text(encoding="utf-8")


def _ferramentas_do_cartao():
    bloco = CARTAO.split("const FERRAMENTAS = [", 1)[1].split("];", 1)[0]
    return re.findall(r"\['(\w+)',", bloco)


def test_o_cartao_lista_as_ferramentas_que_o_motor_tem():
    # Na mesma ordem: e a ordem em que o agente as recebe no tools/list.
    assert _ferramentas_do_cartao() == [t["name"] for t in mcp_server.TOOLS]


def test_o_cartao_so_conhece_o_motor_deste_computador():
    # Nem a URL do servico pago do upstream, nem o nome antigo nos comandos
    # que a pessoa cola no agente.
    assert "openshorts" not in CARTAO.lower()
    assert "https://" not in CARTAO
