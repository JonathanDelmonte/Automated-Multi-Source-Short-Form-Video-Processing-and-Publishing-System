"""A frota no painel (etapa 7.9): as regras puras de `lib/frota.js` no `node` de
verdade (sem node, pula), conferidas contra o motor -- o limite, o que fazer
quando o adb nao responde, quando o automatico pode ligar -- e o que a pagina
promete: os limites na tela, ligar so com a caixa marcada, o consentimento na
hora de ligar o automatico.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import db_models
import frota

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(expressao):
    caminho = (SRC / "lib" / "frota.js").as_uri()
    codigo = (f"import * as m from {json.dumps(caminho)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return SRC.joinpath(*partes).read_text(encoding="utf-8")


@precisa_node
def test_o_limite_e_o_do_motor():
    assert _js("[m.LIMITE_PADRAO, m.LIMITE_MAXIMO]") == [
        db_models.LIMITE_DIARIO_PADRAO, db_models.LIMITE_DIARIO_MAXIMO]
    assert set(_js("Object.keys(m.TIPOS)")) == set(db_models.DEVICE_KINDS)


@precisa_node
@pytest.mark.parametrize("adb,trecho", [
    ({"alcancado": False, "docker": True}, "celulares.bat"),
    ({"alcancado": False, "docker": False, "adb_nesta_maquina": True}, "adb start-server"),
    ({"alcancado": False, "docker": False, "adb_nesta_maquina": False}, "winget install"),
])
def test_ajuda_do_adb_conforme_onde_o_motor_roda(adb, trecho):
    ajuda = _js(f"m.ajudaDoAdb({json.dumps(adb)})")
    assert trecho in " ".join(ajuda["passos"])
    assert _js('m.ajudaDoAdb({"alcancado": true})') is None


@precisa_node
def test_resumo_do_estado():
    assert _js('m.resumoDoEstado({"no_ar": false})') == [{"texto": "fora do ar", "tipo": "erro"}]
    resumo = _js('m.resumoDoEstado({"no_ar": true, "bateria": {"nivel": 12, "carregando": false},'
                 ' "bloqueado": true, "espaco_livre_mb": 300, "adbkeyboard": false})')
    assert [r["texto"] for r in resumo] == ["12%", "tela bloqueada", "pouco espaço", "sem ADBKeyBoard"]
    assert resumo[0]["tipo"] == "aviso"
    assert _js('m.resumoDoEstado({"no_ar": true, "bateria": {"nivel": 12, "carregando": true}})')[0] == {
        "texto": "12% carregando", "tipo": "ok"}


@precisa_node
@pytest.mark.parametrize("roteiros,pode,trecho", [
    ({}, False, "ensine"),
    ({"instagram": {"ensaio_ok": None}}, False, "ensaie"),
    ({"instagram": {"ensaio_ok": False}}, False, "não passou"),
    ({"instagram": {"ensaio_ok": True}}, True, ""),
])
def test_quando_o_automatico_pode_ligar(roteiros, pode, trecho):
    r = _js(f"m.situacaoDoAutomatico({json.dumps({'roteiros': roteiros})}, 'instagram')")
    assert r["pode"] is pode and trecho in r["motivo"]


@precisa_node
def test_contas_para_ligar():
    aparelho = {"contas": [{"account_id": "a", "platform": "instagram"}]}
    contas = [{"id": "a", "platform": "instagram"}, {"id": "b", "platform": "instagram"},
              {"id": "c", "platform": "tiktok"}, {"id": "d", "platform": "orkut"}]
    plataformas = ["youtube", "tiktok", "instagram"]
    r = _js(f"m.contasParaLigar({json.dumps(contas)}, {json.dumps(plataformas)}, {json.dumps(aparelho)})")
    assert [c["id"] for c in r] == ["c"]


@precisa_node
def test_ponto_na_imagem_fica_dentro():
    assert _js("m.pontoNaImagem(150, 300, {left: 100, top: 100, width: 200, height: 400})") == {
        "x": 0.25, "y": 0.5}
    assert _js("m.pontoNaImagem(0, 9999, {left: 100, top: 100, width: 200, height: 400})") == {
        "x": 0, "y": 1}


@precisa_node
def test_toda_situacao_do_motor_tem_frase():
    """As situacoes que o motor grava no historico (`frota_registro`) tem frase
    na tela -- uma nova sem frase apareceria crua."""
    motor = set()
    padrao = re.compile(r'registro\.fechar\(\s*"([a-z-]+)"(?:\s+if\s+[^,]+?\s+else\s+"([a-z-]+)")?')
    for arquivo in ("frota.py", "publishers/aparelho.py"):
        for a, b in padrao.findall((RAIZ / arquivo).read_text(encoding="utf-8")):
            motor |= {a, b} - {""}
    assert {"entregue", "publicado", "parou", "duvida", "nao-saiu", "passou", "falhou"} <= motor
    for situacao in motor:
        assert _js(f"m.situacaoDaExecucao({json.dumps(situacao)}).tipo") != "info", situacao


def test_a_pagina_mostra_os_limites_e_pede_para_ligar():
    pagina = _fonte("pages", "Frota.jsx")
    assert "EmBreve" not in pagina
    assert "LimitesDaFrota" in pagina and "LigarFrota" in pagina
    limites = _fonte("components", "frota", "LimitesDaFrota.jsx")
    for frase in ("não curte", "não muda a identidade do aparelho", "proxy ou VPN", "imita gente"):
        assert frase in limites
    ligar = _fonte("components", "frota", "LigarFrota.jsx")
    assert "disabled={!entendi || ligando}" in ligar


def test_o_automatico_pede_consentimento_na_hora():
    contas = _fonte("components", "frota", "ContasDoAparelho.jsx")
    assert "consentimento" in contas
    assert "disabled={salvando || (pedeConsentimento && !consentimento)}" in contas


def test_o_ensino_marca_o_botao_de_publicar_sem_tocar():
    ensino = _fonte("components", "frota", "EnsinoDoApp.jsx")
    assert "marcar o botão de publicar" in ensino
    assert "acaoNoEnsino(aparelhoId, modo === 'publicar' ? 'publicar' : 'tocar', ponto)" in ensino


def test_a_legenda_do_ensaio_tem_o_que_o_input_text_nao_digita():
    """O ensaio existe para provar que o ADBKeyBoard digita acento e emoji."""
    assert re.search(r"[çãé]", frota.LEGENDA_DO_ENSAIO)
    assert any(ord(ch) > 0xFFFF for ch in frota.LEGENDA_DO_ENSAIO)
