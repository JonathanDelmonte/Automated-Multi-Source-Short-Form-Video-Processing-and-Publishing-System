"""Cascata de provedores de LLM gratuitos (llm_cascade).

Nenhum teste aqui toca a rede: a chamada ao provedor e injetada em
`llm_cascade.run`, que e exatamente por que o modulo foi desenhado assim.
"""
import json
import os
import sys

import pytest
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm_cascade


class Resposta(BaseModel):
    ok: bool


@pytest.fixture(autouse=True)
def ambiente_limpo(tmp_path, monkeypatch):
    """Cada teste comeca sem chaves, sem overrides e com orcamento vazio."""
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    for var in list(os.environ):
        if var.startswith(("LLM_", "GROQ_", "CEREBRAS_", "GEMINI_", "OLLAMA_")):
            monkeypatch.delenv(var, raising=False)
    # Sem OLLAMA_BASE_URL o default aponta para localhost e o Ollama entraria
    # em toda cascata; os testes que o querem ligam de proposito.
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    # A lista de modelos inexistentes vale por processo (um job); entre testes
    # ela tem de voltar vazia, ou um teste desligaria o Groq do seguinte.
    monkeypatch.setattr(llm_cascade, "_MODELO_INEXISTENTE", {})
    return tmp_path


def _todos(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("CEREBRAS_API_KEY", "c")


class TestOrdem:
    def test_fonte_curta_comeca_no_groq(self, monkeypatch):
        _todos(monkeypatch)
        ids = [p.id for p in llm_cascade.cascade(duration_seconds=10 * 60)]
        assert ids[0] == "groq"

    def test_fonte_longa_comeca_no_gemini(self, monkeypatch):
        # O teto de 100k tokens/dia do Groq nao aguenta uma live de 4h, e o
        # contexto de 1M do Gemini aguenta: e a razao de ser do ADR-005.
        _todos(monkeypatch)
        ids = [p.id for p in llm_cascade.cascade(duration_seconds=4 * 60 * 60)]
        assert ids[0] == "gemini"

    def test_limiar_de_fonte_longa_e_configuravel(self, monkeypatch):
        _todos(monkeypatch)
        monkeypatch.setenv("LLM_LONG_SOURCE_SECONDS", "60")
        assert llm_cascade.cascade(duration_seconds=120)[0].id == "gemini"
        assert llm_cascade.cascade(duration_seconds=30)[0].id == "groq"

    def test_duracao_desconhecida_trata_como_curta(self, monkeypatch):
        _todos(monkeypatch)
        assert llm_cascade.cascade(None)[0].id == "groq"

    def test_LLM_CASCADE_sobrescreve_a_ordem(self, monkeypatch):
        _todos(monkeypatch)
        monkeypatch.setenv("LLM_CASCADE", "cerebras,groq")
        assert [p.id for p in llm_cascade.cascade(10)] == ["cerebras", "groq"]

    def test_so_entra_provedor_configurado(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        assert [p.id for p in llm_cascade.cascade(10)] == ["groq"]

    def test_sem_nada_configurado_a_cascata_e_vazia(self):
        assert llm_cascade.cascade(10) == []

    def test_ollama_entra_sem_chave(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        assert [p.id for p in llm_cascade.cascade(10)] == ["ollama"]


class TestOrcamento:
    def test_tokens_por_dia_bloqueiam_antes_de_chamar(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        groq = llm_cascade.cascade(10)[0]
        llm_cascade.record("groq", tokens=99_000)
        ok, motivo = llm_cascade.available(groq, need_tokens=5_000)
        assert not ok and "tokens/dia" in motivo

    def test_uma_chamada_que_cabe_e_liberada(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        groq = llm_cascade.cascade(10)[0]
        llm_cascade.record("groq", tokens=50_000)
        assert llm_cascade.available(groq, need_tokens=1_000)[0]

    def test_chamadas_por_dia_bloqueiam(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("LLM_GROQ_RPD", "2")
        groq = llm_cascade.cascade(10)[0]
        llm_cascade.record("groq", tokens=1, calls=2)
        ok, motivo = llm_cascade.available(groq)
        assert not ok and "chamadas/dia" in motivo

    def test_chamadas_por_minuto_bloqueiam(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("LLM_GROQ_RPM", "2")
        groq = llm_cascade.cascade(10)[0]
        llm_cascade.record("groq", tokens=1)
        llm_cascade.record("groq", tokens=1)
        ok, motivo = llm_cascade.available(groq)
        assert not ok and "chamadas/min" in motivo

    def test_teto_zerado_desliga_a_checagem(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("LLM_GROQ_TPD", "0")
        groq = llm_cascade.cascade(10)[0]
        llm_cascade.record("groq", tokens=10_000_000)
        assert llm_cascade.available(groq, need_tokens=1_000)[0]

    def test_orcamento_sobrevive_ao_processo(self, monkeypatch, tmp_path):
        # O main.py roda como subprocesso novo a cada job: um contador em
        # memoria zeraria entre videos e o teto diario nunca valeria.
        monkeypatch.setenv("GROQ_API_KEY", "g")
        llm_cascade.record("groq", tokens=1_234)
        assert (tmp_path / "output" / ".llm_budget.json").exists()
        assert llm_cascade.usage("groq")["tokens"] == 1_234

    def test_orcamento_zera_quando_o_dia_vira(self, monkeypatch, tmp_path):
        llm_cascade.record("groq", tokens=90_000)
        caminho = tmp_path / "output" / ".llm_budget.json"
        dados = json.loads(caminho.read_text())
        dados["day"] = "2000-01-01"
        caminho.write_text(json.dumps(dados))
        assert llm_cascade.usage("groq")["tokens"] == 0

    def test_arquivo_corrompido_nao_quebra_o_job(self, monkeypatch, tmp_path):
        (tmp_path / "output" / ".llm_budget.json").write_text("{ isso nao e json")
        assert llm_cascade.usage("groq")["tokens"] == 0

    def test_estimativa_de_tokens_erra_para_cima(self):
        # Subestimar libera uma chamada que estoura o teto e volta 429.
        texto = "a" * 3500
        assert llm_cascade.estimate_tokens(texto) >= 1000


class TestExecucao:
    def test_o_primeiro_que_responde_ganha(self, monkeypatch):
        _todos(monkeypatch)
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            return {"ok": True}, {"input_tokens": 10, "output_tokens": 5}

        parsed, cost = llm_cascade.run("oi", Resposta, call=call,
                                       duration_seconds=60, log=lambda _m: None)
        assert parsed == {"ok": True}
        assert vistos == ["groq"]
        assert cost["provider"] == "groq"

    def test_falha_cai_para_o_proximo(self, monkeypatch):
        _todos(monkeypatch)
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            if provider.id == "groq":
                raise RuntimeError("429 rate limited")
            return {"ok": True}, {}

        parsed, _ = llm_cascade.run("oi", Resposta, call=call,
                                    duration_seconds=60, log=lambda _m: None)
        assert parsed == {"ok": True}
        assert vistos == ["groq", "gemini"]

    def test_resposta_invalida_tambem_cai_para_o_proximo(self, monkeypatch):
        # E o caso que justifica a cascata: modelo pequeno erra o formato.
        _todos(monkeypatch)
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            if provider.id == "groq":
                raise ValueError("1 validation error for Resposta")
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                        log=lambda _m: None)
        assert vistos == ["groq", "gemini"]

    def test_orcamento_esgotado_pula_sem_ir_na_rede(self, monkeypatch):
        _todos(monkeypatch)
        llm_cascade.record("groq", tokens=100_000)
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                        log=lambda _m: None)
        assert "groq" not in vistos, "o provedor esgotado nao deve ser chamado"
        assert vistos[0] == "gemini"

    def test_tentativa_que_falhou_ainda_consome_cota(self, monkeypatch):
        _todos(monkeypatch)

        def call(prompt, schema, provider):
            if provider.id == "groq":
                raise RuntimeError("500")
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                        log=lambda _m: None)
        assert llm_cascade.usage("groq")["calls"] == 1

    def test_prompt_maior_que_o_contexto_pula_o_provedor(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        monkeypatch.setenv("LLM_GROQ_CONTEXT", "100")
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            return {"ok": True}, {}

        llm_cascade.run("x" * 10_000, Resposta, call=call, duration_seconds=60,
                        log=lambda _m: None)
        assert vistos == ["gemini"]

    def test_cascata_vazia_levanta_erro_explicativo(self):
        with pytest.raises(llm_cascade.AllProvidersFailed) as e:
            llm_cascade.run("oi", Resposta, call=lambda *_a: ({}, {}),
                            log=lambda _m: None)
        assert "GROQ_API_KEY" in str(e.value)

    def test_todos_falharem_levanta_com_os_motivos(self, monkeypatch):
        _todos(monkeypatch)

        def call(prompt, schema, provider):
            raise RuntimeError(f"{provider.id} caiu")

        with pytest.raises(llm_cascade.AllProvidersFailed) as e:
            llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                            log=lambda _m: None)
        msg = str(e.value)
        assert "groq" in msg and "gemini" in msg and "cerebras" in msg


class TestTamanhoDeLote:
    def test_gemini_cabe_oito_janelas(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        assert llm_cascade.batch_size_for(10) == 8

    def test_groq_cabe_seis(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        assert llm_cascade.batch_size_for(10) == 6

    def test_ollama_cabe_tres(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        assert llm_cascade.batch_size_for(10) == 3

    def test_o_lote_segue_o_primeiro_da_fila(self, monkeypatch):
        # Mesma cascata, duracoes diferentes: fonte longa comeca no Gemini e
        # cabe mais janela por chamada.
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        assert llm_cascade.batch_size_for(10 * 60) == 6
        assert llm_cascade.batch_size_for(4 * 60 * 60) == 8


class TestDescribe:
    def test_descreve_o_estado_de_cada_provedor(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        llm_cascade.record("groq", tokens=2_000)
        d = llm_cascade.describe(10)
        assert d["batch_size"] == 6
        groq = next(p for p in d["providers"] if p["id"] == "groq")
        assert groq["tokens_today"] == 2_000
        assert groq["tokens_per_day"] == 100_000
        assert groq["ready"] is True

    def test_marca_o_provedor_que_treina_com_os_dados(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        d = llm_cascade.describe(10)
        assert next(p for p in d["providers"] if p["id"] == "gemini")["trains_on_data"]



# --------------------------------------------------------------------------- #
# Modelo que nao existe mais (22-set-2026)
# --------------------------------------------------------------------------- #

ERRO_DO_GROQ = (
    'LLM server 404 from https://api.groq.com/openai/v1/chat/completions: '
    '{"error":{"message":"The model `llama-3.3-70b-versatile` does not exist or '
    'you do not have access to it.","type":"invalid_request_error",'
    '"code":"model_not_found"}}')


class TestModeloInexistente:
    """O `llama-3.3-70b-versatile` foi aposentado pelo Groq em 16-ago-2026, e
    dali em diante toda chamada de todo job tentava o Groq, levava 404 e caia
    no Gemini -- tres vezes num video de 10 min, com a mesma linha de erro."""

    def test_o_padrao_do_groq_nao_e_o_modelo_aposentado(self):
        groq = next(p for p in llm_cascade._CATALOG if p.id == "groq")
        assert groq.model != "llama-3.3-70b-versatile"

    def test_reconhece_o_erro_real_do_log(self):
        assert llm_cascade.modelo_inexistente(RuntimeError(ERRO_DO_GROQ))

    @pytest.mark.parametrize("texto", [
        "429 rate limited",
        "503 UNAVAILABLE. This model is currently experiencing high demand",
        "500 internal error",
        "1 validation error for Resposta",
    ])
    def test_erro_passageiro_nao_desliga_o_provedor(self, texto):
        assert not llm_cascade.modelo_inexistente(RuntimeError(texto))

    def test_depois_do_404_o_job_nao_tenta_o_groq_de_novo(self, monkeypatch):
        _todos(monkeypatch)
        vistos = []
        avisos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            if provider.id == "groq":
                raise RuntimeError(ERRO_DO_GROQ)
            return {"ok": True}, {}

        for _ in range(3):              # as tres chamadas de um job
            llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                            log=avisos.append)
        assert vistos == ["groq", "gemini", "gemini", "gemini"]
        # um aviso so, e ele diz o que fazer
        sobre_o_modelo = [a for a in avisos if "nao existe" in a]
        assert len(sobre_o_modelo) == 1
        assert "GROQ_MODEL=" in sobre_o_modelo[0]

    def test_404_de_modelo_nao_gasta_cota_fantasma(self, monkeypatch):
        """Um 404 de modelo nao consome nada no provedor; somar tokens ali
        encheria o teto diario de quem nem chegou a trabalhar."""
        _todos(monkeypatch)

        def call(prompt, schema, provider):
            if provider.id == "groq":
                raise RuntimeError(ERRO_DO_GROQ)
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                        log=lambda _m: None)
        assert llm_cascade.usage("groq")["calls"] == 0

    def test_erro_passageiro_continua_tentando_na_proxima_chamada(self, monkeypatch):
        """So o modelo inexistente desliga o provedor: um 429 hoje pode ser um
        200 daqui a 10 segundos."""
        _todos(monkeypatch)
        vistos = []

        def call(prompt, schema, provider):
            vistos.append(provider.id)
            if provider.id == "groq":
                raise RuntimeError("429 rate limited")
            return {"ok": True}, {}

        for _ in range(2):
            llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                            log=lambda _m: None)
        assert vistos == ["groq", "gemini", "groq", "gemini"]


# --------------------------------------------------------------------------- #
# 429 com a espera que o proprio servidor pede (23-set-2026)
# --------------------------------------------------------------------------- #

# O corpo como o `llm_backend` o entrega: cortado em 300 caracteres. A dica
# tem de sobreviver ao corte, senao a regra nova nunca teria o que ler.
_CORPO_429 = (
    '{"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in '
    'organization `org_01m2bq0m83e1tvq443x51kxymk` service tier `on_demand` on '
    'tokens per minute (TPM): Limit 8000, Used 6586, Requested 4123. Please try '
    'again in 20.4095s. Need more tokens? Upgrade to Dev Tier today at '
    'https://console.groq.com/settings/billing","type":"tokens",'
    '"code":"rate_limit_exceeded"}}')
ERRO_429_DO_GROQ = ('LLM server 429 from https://api.groq.com/openai/v1/chat/'
                    'completions: ' + _CORPO_429[:300])


class TestEsperaDo429:
    """No job de 23-set-2026 o Groq devolveu 429 de tokens por minuto na
    terceira chamada, e a regra antiga esperou 5 s e 10 s para levar o mesmo
    429 as tres vezes: 15 s jogados fora antes de passar ao Gemini."""

    def test_le_a_dica_do_groq_depois_do_corte(self):
        assert llm_cascade.espera_sugerida(ERRO_429_DO_GROQ) == pytest.approx(20.4095)

    @pytest.mark.parametrize("texto,segundos", [
        ("Please try again in 6.55s. Need more tokens?", 6.55),
        ("Please try again in 1m26.4s.", 86.4),         # duracao do Go
        ("Please try again in 780ms.", 0.78),
        ("Please try again in 2h3m4.5s.", 7384.5),      # teto diario
        ("429 RESOURCE_EXHAUSTED ... Please retry in 44.52s.", 44.52),  # Gemini
        ("'details': [{'retryDelay': '44s'}]", 44.0),   # RetryInfo do Gemini
    ])
    def test_formatos_de_dica(self, texto, segundos):
        assert llm_cascade.espera_sugerida(texto) == pytest.approx(segundos)

    @pytest.mark.parametrize("texto", [
        "429 rate limited", "503 UNAVAILABLE", "please try again later",
        "ReadTimeout", "1 validation error for Resposta",
    ])
    def test_sem_dica_e_none(self, texto):
        assert llm_cascade.espera_sugerida(texto) is None

    def test_sem_dica_a_regra_e_a_de_sempre(self):
        assert llm_cascade.espera_antes_de_repetir("503", 1, 0.0, 3) == 5
        assert llm_cascade.espera_antes_de_repetir("503", 2, 5.0, 3) == 10

    def test_o_caso_do_log_desiste_ja(self):
        # 20 s pedidos contra 15 s de paciencia: esperar seria levar o mesmo
        # "nao" tres vezes. A cascata passa ao proximo no mesmo instante.
        assert llm_cascade.espera_antes_de_repetir(ERRO_429_DO_GROQ, 1, 0.0, 3) is None

    def test_dica_que_cabe_e_esperada_com_folga(self):
        espera = llm_cascade.espera_antes_de_repetir(
            "Please try again in 3s.", 1, 0.0, 3)
        assert espera == pytest.approx(3 + llm_cascade.FOLGA_DA_DICA_S)

    def test_a_paciencia_e_a_soma_do_que_ja_se_esperou(self):
        # 3,5 s ja gastos; pedir mais 12 passaria dos 15 da regra antiga.
        assert llm_cascade.espera_antes_de_repetir(
            "Please try again in 12s.", 2, 3.5, 3) is None
        # Na fronteira ainda espera: e o que a regra antiga alcancaria.
        assert llm_cascade.espera_antes_de_repetir(
            "Please try again in 14.5s.", 1, 0.0, 3) == pytest.approx(15.0)

    @pytest.mark.parametrize("dicas", [
        (0.2, 0.2), (3, 9), (4.4, 9.9), (14.5, 1), (0, 0), (7, 7),
    ])
    def test_nunca_espera_mais_que_a_regra_antiga(self, dicas):
        esperado = 0.0
        for tentativa, dica in enumerate(dicas, start=1):
            espera = llm_cascade.espera_antes_de_repetir(
                f"Please try again in {dica}s.", tentativa, esperado, 3)
            if espera is None:
                break
            esperado += espera
        assert esperado <= 5 + 10


def test_o_main_pergunta_a_espera_a_cascata():
    """O `main.py` so importa com torch, entao o CI le a arvore: o laco de
    tentativas tem de perguntar a espera ao `llm_cascade`, e nao voltar ao
    `5 * 2 ** (attempt - 1)` que ignorava a dica."""
    import ast
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
    arvore = ast.parse(open(caminho, encoding="utf-8").read())
    funcao = next(n for n in ast.walk(arvore)
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_gemini_stage")
    fonte = ast.unparse(funcao)
    assert "llm_cascade.espera_antes_de_repetir(" in fonte
    assert "2 ** (attempt - 1)" not in fonte
