"""O video criado por IA no painel (etapa 7.7).

As regras puras de `lib/criacao.js` rodam no `node` de verdade (sem node,
pula) e sao conferidas contra o motor: as escolhas do editor do estilo sao as
que o `estilos.py` aceita, o estilo novo da tela e o do motor, e a ideia que a
tela preve para o proximo video e a que o `receitas.py` escolhe. O resto e a
forma das telas, lida na fonte.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import estilos
import midia_ia
import receitas

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(expressao, modulo="criacao.js"):
    caminho = (SRC / "lib" / modulo).as_uri()
    codigo = (f"import * as m from {json.dumps(caminho)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return SRC.joinpath(*partes).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# A tela e o motor falam das mesmas coisas
# --------------------------------------------------------------------------- #

@precisa_node
def test_as_escolhas_do_editor_sao_as_do_motor():
    assert [f["id"] for f in _js("m.FORMATOS")] == list(estilos.FORMATOS)
    assert [v["id"] for v in _js("m.VISUAIS")] == list(estilos.PRESETS_VISUAIS)
    assert [l["id"] for l in _js("m.LEGENDAS")] == list(estilos.LEGENDAS)
    assert _js("m.DURACAO") == {"min": estilos.DURACAO_MIN, "max": estilos.DURACAO_MAX}
    assert _js("m.CENAS") == {"min": estilos.CENAS_MIN, "max": estilos.CENAS_MAX}
    assert _js("m.MAX_PERSONAGENS") == estilos.MAX_PERSONAGENS
    assert _js("m.MAX_IDEIAS") == receitas.MAX_IDEIAS


@precisa_node
def test_o_estilo_novo_da_tela_e_o_do_motor():
    do_motor = estilos.padrao()
    del do_motor["semente"]
    assert _js("m.ESTILO_PADRAO") == do_motor
    # E ele passa no motor como esta.
    estilos.normalizar(_js("m.ESTILO_PADRAO"), vozes=midia_ia.NOMES_DAS_VOZES)


@precisa_node
def test_as_ideias_saem_como_o_motor_as_guarda():
    texto = "A Lulu e a chuva\n\n   a lulu e a CHUVA!  \nO Bento  no   mar\nÁgua é vida\nagua e vida"
    da_tela = _js(f"m.ideiasDoTexto({json.dumps(texto)})")
    assert da_tela == receitas.normalizar_ia({"ideias": texto})["ideias"]
    for ideia in ("Ação e Reação!", "  o  BENTO ", "Pão-de-queijo"):
        assert _js(f"m.chaveDaIdeia({json.dumps(ideia)})") == receitas.chave_da_ideia(ideia)


@precisa_node
@pytest.mark.parametrize("feitas,puladas", [([], []), (["um"], []), (["UM"], ["dois"]),
                                            (["um", "dois", "tres"], [])])
def test_a_proxima_ideia_da_tela_e_a_do_motor(feitas, puladas):
    for tema in ("animais", ""):
        spec = receitas.normalizar_ia({"ideias": ["um", "dois", "tres"], "tema": tema})
        ideia, da_lista = receitas.proxima_ideia(spec, feitas, puladas)
        vista = _js(f"m.proximaIdeia({json.dumps(spec)}, {json.dumps(feitas)}, {json.dumps(puladas)})")
        assert vista == {"ideia": ideia, "daLista": da_lista}


@precisa_node
def test_as_frases_da_cota():
    volta = "à meia-noite UTC (21:00 no seu horário)"
    assert _js(f"m.fraseDaCota({{imagens_hoje: 70, imagem_volta: {json.dumps(volta)}}}, 8)") == \
        "Hoje ainda cabem 70 imagens na cota grátis: dá para 8 vídeos de 8 cenas."
    assert _js("m.fraseDaCota({imagens_hoje: 5}, 8)") == \
        "Hoje ainda cabem 5 imagens na cota grátis: não dá para um vídeo inteiro de 8 cenas."
    assert _js(f"m.fraseDaCota({{imagens_hoje: 0, imagem_volta: {json.dumps(volta)}}}, 8)") == \
        f"A cota grátis de imagem de hoje acabou. Ela volta {volta}."
    assert _js("m.videosQueCabem({imagens_hoje: 17}, 8)") == 2


@precisa_node
def test_o_resumo_do_estilo_e_o_pedido():
    spec = estilos.normalizar({"visual": {"preset": "aquarela"}, "cenas": 6, "duracao_s": 45,
                               "voz": {"nome": "Sulafat"},
                               "personagens": [{"nome": "Lulu"}, {"nome": "Bento"}]})
    assert _js(f"m.resumoDoEstilo({json.dumps(spec)})") == \
        "história · 45 s · 6 cenas · aquarela · voz Sulafat · Lulu, Bento"
    assert _js("m.corpoDaCriacao({canalId: 'c1', ideia: '  a Lulu   e a chuva '})") == \
        {"channel_id": "c1", "ideia": "a Lulu e a chuva"}
    assert _js("m.situacaoDaCriacao({configCarregada: true, criacaoNoMotor: false})") == "motor-antigo"
    assert _js("m.situacaoDaCriacao({configCarregada: false, criacaoNoMotor: false})") == "carregando"


# --------------------------------------------------------------------------- #
# As telas
# --------------------------------------------------------------------------- #

def test_o_video_de_ia_deixou_de_ser_em_breve():
    tipos = _fonte("components", "TiposDeCriacao.jsx")
    bloco = tipos[tipos.index("id: 'ia'"):tipos.index("id: 'serie'")]
    assert "etapa" not in bloco
    criar = _fonte("pages", "Criar.jsx")
    assert "ia: { titulo" not in criar and "tipo === 'ia'" in criar
    assert "<CriarVideoDeIA" in criar


def test_o_site_novo_com_o_programa_velho_manda_atualizar():
    """Um motor de antes da 7.7 responde 404 no /api/criacoes: a tela diz para
    atualizar ANTES do clique, pela marca do /api/config."""
    assert "criacaoNoMotor: config.criacao === true" in _fonte("contexts", "AuthContext.jsx")
    tela = _fonte("components", "criacao", "CriarVideoDeIA.jsx")
    assert "situacaoDaCriacao" in tela and "data-aviso-criacao-motor" in tela
    assert "motorAntigo" in _fonte("lib", "criacaoNoMotor.js")


def test_o_estilo_mora_na_aba_criar_do_canal_e_a_receita_na_automacao():
    canal = _fonte("pages", "Canal.jsx")
    assert "<EstiloDoCanal" in canal
    aba = canal[canal.index("case 'criar':"):canal.index("case 'automacao':")]
    assert "EstiloDoCanal" in aba
    automacao = _fonte("components", "automacao", "AutomacaoDoCanal.jsx")
    assert "<ReceitaDeIA" in automacao
    receita = _fonte("components", "criacao", "ReceitaDeIA.jsx")
    assert "lerReceita(canal.id, 'ia')" in receita and "rodarAgora(canal.id, 'ia')" in receita
    assert "'ia')" in receita[receita.index("salvarReceita("):]


def test_as_mensagens_do_motor_apontam_a_aba_que_existe():
    import app  # noqa: F401  -- as frases moram no app
    fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
    assert "aba Criação" not in fonte and "aba Criar do canal" in fonte
    rotulos = _fonte("pages", "Canal.jsx")
    assert "{ id: 'criar', rotulo: 'Criar' }" in rotulos


def test_o_projeto_de_ia_continua_de_onde_parou():
    projeto = _fonte("pages", "Projeto.jsx")
    assert "continuarCriacao(jobId)" in projeto and "data-continuar-criacao" in projeto
    # Sem video de origem, a previa nao tenta abrir o /api/source.
    assert "midia && !criacao" in projeto


def test_a_imagem_do_personagem_vai_como_json():
    """Multipart de outra origem passaria sem o preflight do CORS: o motor so
    aceita a imagem em JSON (data URL), e a tela manda assim."""
    motor = _fonte("lib", "criacaoNoMotor.js")
    assert "{ imagem: dataUrl }" in motor
    assert "FormData" not in motor


def test_o_inicio_mostra_as_duas_receitas_do_mesmo_canal():
    """Com a de cortes e a de IA ligadas no mesmo canal, a chave do React por
    canal repetia -- uma das duas linhas sumia do Inicio."""
    inicio = _fonte("components", "automacao", "AutomacaoNoInicio.jsx")
    assert "key={`receita-${r.channel_id}-${r.kind || 'cortes'}`}" in inicio
    assert "vídeos de IA: " in inicio
