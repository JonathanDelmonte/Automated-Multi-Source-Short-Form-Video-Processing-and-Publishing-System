"""As plataformas no painel (etapa 7.10).

As regras puras de `lib/plataformas.js`, `lib/publicacoes.js` e
`lib/analises.js` rodam no `node` de verdade (sem node, pula) e sao conferidas
contra o motor (`plataformas.py`): a ordem, as que sao medidas, para onde vai o
video longo -- e o site novo falando com o programa de antes da 7.10, que so
conhece as tres de sempre.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import plataformas

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(expressao, modulo):
    caminho = (SRC / "lib" / modulo).as_uri()
    codigo = (f"import * as m from {json.dumps(caminho)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return SRC.joinpath(*partes).read_text(encoding="utf-8")


@precisa_node
def test_a_tela_e_o_motor_falam_das_mesmas_plataformas():
    assert _js("m.ORDEM_DAS_PLATAFORMAS", "plataformas.js") == list(plataformas.IDS)
    assert _js("m.MEDIDAS", "plataformas.js") == list(plataformas.MEDIDAS)
    assert _js("m.ORDEM", "analises.js") == list(plataformas.MEDIDAS)
    assert _js("m.PLATAFORMAS_DO_VIDEO_LONGO", "publicacoes.js") == list(plataformas.VIDEO_LONGO)
    nomes = _js("Object.fromEntries(Object.entries(m.PLATAFORMAS).map(([k, v]) => [k, v.nome]))",
                "plataformas.js")
    assert nomes == plataformas.NOMES
    chinesas = _js("Object.keys(m.PLATAFORMAS).filter((k) => m.PLATAFORMAS[k].chinesa)", "plataformas.js")
    assert chinesas == list(plataformas.TRADUZIDAS)
    # Toda chinesa diz o que o cadastro dela pede, na hora de ligar a conta.
    assert all(_js(f"m.PLATAFORMAS.{p}.exigencia.length > 40", "plataformas.js") for p in chinesas)


@precisa_node
@pytest.mark.parametrize("do_motor, esperado", [
    (None, ["youtube", "tiktok", "instagram"]),                       # sem a lista
    ([], ["youtube", "tiktok", "instagram"]),
    (["youtube", "tiktok", "instagram"], ["youtube", "tiktok", "instagram"]),   # programa da 7.9
    (list(plataformas.IDS), list(plataformas.IDS)),
    (["bilibili", "youtube", "plataforma-do-futuro"], ["youtube", "bilibili"]),
])
def test_o_site_novo_so_oferece_o_que_o_programa_conhece(do_motor, esperado):
    """Um programa de antes da 7.10 recusaria a conta do Douyin ao salvar: o
    site, publicado antes dele ser atualizado, nem a oferece."""
    assert _js(f"m.plataformasDoMotor({json.dumps(do_motor)})", "plataformas.js") == esperado


@precisa_node
def test_o_pacote_sem_conta_oferece_as_tres_de_sempre():
    assert _js("m.plataformasDoPacote([])", "publicacoes.js") == ["youtube", "tiktok", "instagram"]
    contas = [{"platform": "bilibili"}, {"platform": "tiktok"}]
    assert _js(f"m.plataformasDoPacote({json.dumps(contas)})", "publicacoes.js") == ["tiktok", "bilibili"]


@precisa_node
def test_conta_chinesa_nao_pede_conectar_para_medir():
    contas = [{"platform": "douyin", "medir": False}, {"platform": "tiktok", "medir": False},
              {"platform": "youtube", "medir": True}]
    assert _js(f"m.contasSemMedir({json.dumps(contas)}).map((c) => c.platform)", "analises.js") == ["tiktok"]


def test_toda_plataforma_tem_icone():
    fonte = _fonte("components", "ui", "IconePlataforma.jsx")
    desenhos = re.search(r"const DESENHOS = \{(.*?)\};", fonte, re.S).group(1)
    for p in plataformas.IDS:
        assert re.search(rf"\b{p}\s*:", desenhos), f"{p} sem icone"


def test_as_telas_perguntam_ao_programa():
    """As duas telas que criam conta usam a lista do motor, e nao a do site."""
    for tela in (("components", "PublicacoesTab.jsx"), ("components", "FormularioDoCanal.jsx")):
        fonte = _fonte(*tela)
        assert "plataformasDoMotor(data.plataformas)" in fonte, tela
        assert "ORDEM_DAS_PLATAFORMAS.map" not in fonte, tela
