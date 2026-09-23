"""O painel so afirma "falta chave de LLM" depois de ouvir o servidor.

Logo depois do `atualizar.bat` o painel volta antes do backend. O `/api/config`
era pedido UMA vez; a falha virava a config padrao, sem `localLlm`, e o painel
concluia que nao havia chave: aparecia "gemini api key required", e um F5
"consertava" porque ai o backend ja tinha subido (22-set-2026).

JS nao roda no CI; estes guardas leem a fonte, como os de `test_log_com_hora`.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AUTH = RAIZ / "dashboard" / "src" / "contexts" / "AuthContext.jsx"
APP = RAIZ / "dashboard" / "src" / "App.jsx"


def test_a_config_e_pedida_ate_o_servidor_responder():
    fonte = AUTH.read_text(encoding="utf-8")
    assert "for (let tentativa = 0; vivo && !cfg; tentativa += 1)" in fonte
    # A falha silenciosa de antes: um catch que seguia com a config padrao.
    assert "config fetch failed — stay in BYOK" not in fonte
    assert "configCarregada," in fonte


def test_falta_de_chave_so_vale_com_a_config_carregada():
    fonte = APP.read_text(encoding="utf-8")
    assert "const keysMissing = !billingEnabled && configCarregada && !geminiOk;" in fonte


def test_enquanto_espera_o_painel_diz_o_que_esta_fazendo():
    """Esperar a config com a tela vazia seria o painel em preto de novo."""
    fonte = APP.read_text(encoding="utf-8")
    assert "return <EsperandoServidor />;" in fonte
    assert "conectando ao servidor" in fonte
