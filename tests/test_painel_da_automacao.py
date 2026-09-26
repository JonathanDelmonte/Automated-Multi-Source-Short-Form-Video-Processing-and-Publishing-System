"""O painel da automacao por canal (etapa 7.5).

As regras que a tela usa rodam no `node` de verdade (sem node, pulam), e as
listas da tela sao comparadas com as do motor: a tela que oferece uma fonte ou
um layout que o motor recusa so descobre na hora de salvar.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import db_models
import licencas
import receitas

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(arquivo, expressao, fuso="America/Sao_Paulo"):
    modulo = (SRC / "lib" / arquivo).as_uri()
    codigo = (f"import * as m from {json.dumps(modulo)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    ambiente = {**os.environ, "TZ": fuso}
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo], env=ambiente,
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return (SRC.joinpath(*partes)).read_text(encoding="utf-8")


_FUSOS_OBEDECIDOS: dict = {}


def _exigir_fuso(fuso):
    """Os testes de fuso rodam o `node` com `TZ`. Se o `node` desta maquina
    nao obedecer, eles mediriam o fuso da maquina, e nao a regra: pula, como
    o `precisa_node` pula sem node."""
    if fuso not in _FUSOS_OBEDECIDOS:
        saida = subprocess.run(
            [NODE, "-e", "console.log(Intl.DateTimeFormat().resolvedOptions().timeZone)"],
            env={**os.environ, "TZ": fuso}, capture_output=True, encoding="utf-8",
            timeout=60).stdout.strip()
        _FUSOS_OBEDECIDOS[fuso] = saida == fuso
    if not _FUSOS_OBEDECIDOS[fuso]:
        pytest.skip(f"o node desta maquina nao obedece TZ={fuso}")


# --------------------------------------------------------------------------- #
# A tela fala as mesmas listas do motor
# --------------------------------------------------------------------------- #

@precisa_node
def test_a_receita_padrao_e_a_do_motor():
    assert _js("receita.js", "m.RECEITA_PADRAO") == receitas.PADRAO


@precisa_node
def test_as_escolhas_sao_as_do_motor():
    assert [f["id"] for f in _js("receita.js", "m.FONTES")] == list(receitas.FONTES)
    assert [d["id"] for d in _js("receita.js", "m.DURACOES")] == list(receitas.DURACOES_DA_BUSCA)
    assert sorted(l["id"] for l in _js("receita.js", "m.LAYOUTS")) == sorted(receitas.LAYOUTS)


@precisa_node
def test_toda_licenca_e_todo_status_tem_nome():
    assert sorted(_js("receita.js", "Object.keys(m.LICENCAS)")) == sorted(licencas.LICENCAS)
    assert sorted(_js("receita.js", "Object.keys(m.STATUS_DOS_CANDIDATOS)")) == \
        sorted(db_models.CANDIDATE_STATUSES)
    for status in db_models.CANDIDATE_STATUSES:
        assert _js("receita.js", f"m.grupoDoCandidato({json.dumps(status)})") in ("fila", "cortados", "fora")


@precisa_node
def test_o_que_falta_para_ligar_e_a_regra_do_motor():
    exemplos = [
        {},
        {"fonte": {"tema": "desenho"}},
        {"fonte": {"tipo": "links", "links": ["https://youtu.be/dQw4w9WgXcQ"]}},
        {"fonte": {"tipo": "links", "links": ["https://youtu.be/dQw4w9WgXcQ"]}, "direitos": "2026-09-26"},
        {"fonte": {"tipo": "twitch", "twitch": "twitch.tv/x"}},
        {"fonte": {"tipo": "pasta"}},
    ]
    for exemplo in exemplos:
        spec = receitas.normalizar(exemplo)
        do_motor = receitas.pronta(spec)
        da_tela = _js("receita.js", f"m.faltaParaLigar({json.dumps(spec)})")
        assert (do_motor is None) == (da_tela is None), (exemplo, do_motor, da_tela)


# --------------------------------------------------------------------------- #
# As regras da tela
# --------------------------------------------------------------------------- #

@precisa_node
@pytest.mark.parametrize("nicho,modelo", [
    ("infantil", "infantil"), ("Canal Infantil", "infantil"), ("desenhos para crianças", "infantil"),
    ("finanças", "financas"), ("fatos desconhecidos", "curiosidades"), ("games", None), ("", None)])
def test_o_modelo_do_nicho(nicho, modelo):
    achado = _js("receita.js", f"m.modeloDoNicho({json.dumps(nicho)})")
    assert (achado or {}).get("id") == modelo


@precisa_node
def test_o_modelo_nao_passa_por_cima_do_tema_escrito():
    spec = _js("receita.js", "m.aplicarModelo({...m.RECEITA_PADRAO, fonte: {...m.RECEITA_PADRAO.fonte, "
                             "tema: 'meu tema'}}, m.MODELOS[0])")
    assert spec["fonte"]["tema"] == "meu tema"
    assert spec["edicao"]["cortes_por_video"] == 4
    vazio = _js("receita.js", "m.aplicarModelo(m.RECEITA_PADRAO, m.MODELOS[0])")
    assert vazio["fonte"]["tema"] == "desenho animado infantil"
    # O modelo so vale como ponto de partida: nenhum passa pelo motor com erro.
    for modelo in _js("receita.js", "m.MODELOS"):
        receitas.normalizar(_js("receita.js", f"m.aplicarModelo(m.RECEITA_PADRAO, {json.dumps(modelo)})"))


@precisa_node
def test_links_do_texto():
    assert _js("receita.js", "m.linksDoTexto('a\\n b , a\\n\\nc')") == ["a", "b", "c"]


@precisa_node
@pytest.mark.parametrize("segundos,texto", [
    (45, "45 s"), (1500, "25 min"), (3900, "1 h 05"), (None, ""), (0, "")])
def test_duracao_curta(segundos, texto):
    assert _js("receita.js", f"m.duracaoCurta({json.dumps(segundos)})") == texto


@precisa_node
def test_frases_de_agenda():
    assert _js("receita.js", "m.janelasEmTexto([11, 15, 19])") == "11h, 15h e 19h"
    assert _js("receita.js", "m.janelasEmTexto([9])") == "9h"
    assert _js("receita.js", "m.rotuloDoOffset(-180)") == "UTC−3"
    assert _js("receita.js", "m.rotuloDoOffset(330)") == "UTC+5:30"
    assert _js("receita.js", "m.rotuloDoOffset(0)") == "UTC"


@precisa_node
def test_o_fuso_do_navegador():
    _exigir_fuso("America/Sao_Paulo")
    assert _js("receita.js", "m.fusoDoNavegador(new Date('2026-09-26T12:00:00Z'))") == \
        {"nome": "America/Sao_Paulo", "offset_min": -180}


# --------------------------------------------------------------------------- #
# O "agendar" da Agenda descreve a agenda do destino
# --------------------------------------------------------------------------- #

@precisa_node
def test_o_canal_do_destino():
    contas = [{"id": "c1", "channel_id": "k1"}, {"id": "c2", "channel_id": None}]
    assert _js("publicacoes.js", "m.canalDoDestino('canal:k9', [])") == "k9"
    assert _js("publicacoes.js", f"m.canalDoDestino('conta:c1', {json.dumps(contas)})") == "k1"
    # Conta solta, conta que nao existe e destino vazio: a agenda da instalacao.
    assert _js("publicacoes.js", f"m.canalDoDestino('conta:c2', {json.dumps(contas)})") is None
    assert _js("publicacoes.js", f"m.canalDoDestino('conta:zz', {json.dumps(contas)})") is None
    assert _js("publicacoes.js", "m.canalDoDestino('', null)") is None
    assert _js("publicacoes.js", "m.canalDoDestino('outro:k1', [])") is None


@precisa_node
def test_o_caminho_da_agenda():
    assert _js("publicacoes.js", "m.caminhoDaAgenda(null)") == "/api/agenda"
    assert _js("publicacoes.js", "m.caminhoDaAgenda('k 1')") == "/api/agenda?canal=k+1"


def test_o_agendar_nao_descreve_a_agenda_da_instalacao_para_um_canal():
    """Com o destino num canal, o texto do "agendar" citava as janelas da
    instalacao (11h, 15h, 19h) mesmo com o canal nas dele -- e o horario que a
    tela promete antes do clique e o que o ADR-007 manda mostrar."""
    aba = _fonte("components", "PublicacoesTab.jsx")
    assert "apiFetch('/api/agenda')" not in aba
    assert "caminhoDaAgenda(canalDaAgenda)" in aba


# --------------------------------------------------------------------------- #
# O calendario
# --------------------------------------------------------------------------- #

@precisa_node
def test_a_semana_no_relogio_de_quem_olha():
    _exigir_fuso("America/Sao_Paulo")
    fila = [
        # 01:30 UTC do dia 27 e 22:30 do dia 26 em Brasilia.
        {"id": "a", "status": "scheduled", "scheduled_at": "2026-09-27T01:30:00+00:00"},
        {"id": "b", "status": "published", "scheduled_at": "2026-09-26T13:00:00+00:00",
         "posted_at": "2026-09-26T14:05:00+00:00"},
        {"id": "c", "status": "failed", "scheduled_at": "2026-09-26T15:00:00+00:00"},
        {"id": "d", "status": "scheduled", "scheduled_at": None},
        {"id": "e", "status": "scheduled", "scheduled_at": "2026-10-20T15:00:00+00:00"},
    ]
    dias = _js("calendario.js", f"m.semana({json.dumps(fila)}, new Date('2026-09-26T12:00:00Z'))")
    assert len(dias) == 7 and dias[0]["dia"] == "2026-09-26"
    assert [p["id"] for p in dias[0]["posts"]] == ["b", "a"]
    assert sum(len(d["posts"]) for d in dias) == 2


@precisa_node
def test_somar_dias_atravessa_a_troca_de_horario():
    """Em Nova York o relogio muda em 1-nov-2026: somar 24 h a meia-noite de
    31-out daria 23h do dia 31, e o calendario pularia um dia."""
    _exigir_fuso("America/New_York")
    dia = _js("calendario.js", "m.diaLocal(m.somarDias(new Date('2026-10-31T12:00:00Z'), 2))",
              fuso="America/New_York")
    assert dia == "2026-11-02"


# --------------------------------------------------------------------------- #
# Guardas na fonte
# --------------------------------------------------------------------------- #

def test_o_painel_manda_o_fuso_ao_motor():
    app = _fonte("App.jsx")
    assert "mandarFuso()" in app and "sessaoPronta" in app


def test_a_aba_automacao_nao_e_mais_em_breve():
    canal = _fonte("pages", "Canal.jsx")
    assert "<AutomacaoDoCanal canal={canal} />" in canal
    assert "etapa=\"7.5\"" not in canal
    assert "etapa=\"7.5\"" not in _fonte("pages", "Agenda.jsx")
    assert "<CalendarioDosCanais" in _fonte("pages", "Agenda.jsx")
    # Nem nas Ferramentas (a busca mora na receita do canal), nem no
    # formulario do canal, que prometia a automacao "na etapa 7.5".
    assert "etapa=\"7.5\"" not in _fonte("pages", "Ferramentas.jsx")
    assert "/automacao`" in _fonte("pages", "Ferramentas.jsx")
    assert "etapa 7.5" not in _fonte("components", "FormularioDoCanal.jsx")


def test_a_automacao_nao_manda_driver():
    """ADR-010: a tela nunca escolhe o driver; a automacao tambem nao."""
    for arquivo in ("automacao.js", "receita.js"):
        assert "driver" not in _fonte("lib", arquivo)


def test_o_editor_da_receita_nao_se_apaga_sozinho():
    """O recarregar periodico da aba nao pode apagar o que a pessoa digita: o
    editor nasce da receita gravada, remontado so quando ela e gravada."""
    aba = _fonte("components", "automacao", "AutomacaoDoCanal.jsx")
    assert "key={receita.updated_at || 'nova'}" in aba
    editor = _fonte("components", "automacao", "ReceitaDoCanal.jsx")
    assert "setSpec(receita.spec" not in editor
