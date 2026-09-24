"""A cascata ampliada: todo provedor gratuito com chave entra (ADR-011, 24-set-2026).

O que estes testes guardam:

* o caminho de sempre nao muda: os dois primeiros de cada ordem sao os de
  antes, e os novos so atendem quando eles falham;
* a mesma chave traz os modelos extras do mesmo provedor (cota por modelo no
  Groq, outra fila no Google), e nenhum provedor entra sem a sua chave;
* uma chave recusada desliga, no resto do job, todo mundo que a usa;
* os provedores novos nao apertam o pre-filtro;
* o Cerebras nao e mais tratado como gratuito, e nao usa o modelo aposentado.

Nenhum teste toca a rede.
"""
import os

import pytest
from pydantic import BaseModel

import llm_cascade
import prefilter


class Resposta(BaseModel):
    ok: bool


CHAVES = {
    "GROQ_API_KEY": "g", "GEMINI_API_KEY": "m", "NVIDIA_API_KEY": "n",
    "MISTRAL_API_KEY": "mi", "OLLAMA_CLOUD_API_KEY": "oc", "OPENROUTER_API_KEY": "or",
    "CLOUDFLARE_API_TOKEN": "cf", "CLOUDFLARE_ACCOUNT_ID": "conta123",
    "ZAI_API_KEY": "z", "CEREBRAS_API_KEY": "c",
}


@pytest.fixture(autouse=True)
def ambiente_limpo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("output", exist_ok=True)
    for var in list(os.environ):
        if var.startswith(("LLM_", "GROQ_", "CEREBRAS_", "GEMINI_", "OLLAMA_",
                           "NVIDIA_", "MISTRAL_", "OPENROUTER_", "CLOUDFLARE_",
                           "ZAI_", "PREFILTER_")):
            monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "")
    monkeypatch.setattr(llm_cascade, "_MODELO_INEXISTENTE", {})
    monkeypatch.setattr(llm_cascade, "_CHAVE_RECUSADA", {})


def _todas(monkeypatch):
    for k, v in CHAVES.items():
        monkeypatch.setenv(k, v)


def _ids(duracao=10 * 60):
    return [p.id for p in llm_cascade.cascade(duracao)]


class TestOrdem:
    def test_toda_entrada_do_catalogo_tem_lugar_nas_duas_ordens(self):
        ids = [p.id for p in llm_cascade._CATALOG]
        assert len(ids) == len(set(ids))
        assert sorted(llm_cascade.ORDEM_CURTA) == sorted(ids)
        assert sorted(llm_cascade.ORDEM_LONGA) == sorted(ids)

    def test_o_caminho_de_sempre_vem_primeiro(self, monkeypatch):
        _todas(monkeypatch)
        assert _ids(10 * 60)[:2] == ["groq", "gemini"]
        assert _ids(4 * 60 * 60)[:2] == ["gemini", "gemini-lite"]

    def test_com_tudo_configurado_entram_todos(self, monkeypatch):
        _todas(monkeypatch)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        assert _ids() == list(llm_cascade.ORDEM_CURTA)

    def test_pago_e_local_ficam_no_fim(self, monkeypatch):
        _todas(monkeypatch)
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        assert _ids()[-2:] == ["cerebras", "ollama"]
        assert _ids(4 * 60 * 60)[-2:] == ["cerebras", "ollama"]


class TestChaves:
    def test_a_chave_do_gemini_traz_o_segundo_modelo(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        assert _ids() == ["gemini", "gemini-lite"]

    @pytest.mark.parametrize("chave,provedor", [
        ("NVIDIA_API_KEY", "nvidia"), ("MISTRAL_API_KEY", "mistral"),
        ("OLLAMA_CLOUD_API_KEY", "ollama-cloud"), ("OPENROUTER_API_KEY", "openrouter"),
        ("ZAI_API_KEY", "zai"), ("CEREBRAS_API_KEY", "cerebras"),
    ])
    def test_cada_provedor_entra_so_com_a_propria_chave(self, monkeypatch, chave, provedor):
        monkeypatch.setenv(chave, "x")
        assert _ids() == [provedor]

    def test_a_chave_do_ollama_local_nao_liga_o_ollama_cloud(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "local")
        assert _ids() == []

    def test_cloudflare_precisa_da_chave_e_da_conta(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf")
        assert _ids() == [], "sem conta nao ha endereco"
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "conta123")
        (cf,) = llm_cascade.cascade(60)
        assert cf.base_url == ("https://api.cloudflare.com/client/v4/accounts/"
                               "conta123/ai/v1")

    def test_teto_de_modelo_extra_se_ajusta_por_env(self, monkeypatch):
        # `groq-qwen` vira `GROQ_QWEN` no nome da variavel: hifen nao vale ali.
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("LLM_GROQ_QWEN_TPD", "12345")
        qwen = next(p for p in llm_cascade.cascade(60) if p.id == "groq-qwen")
        assert qwen.tokens_per_day == 12345
        groq = next(p for p in llm_cascade.cascade(60) if p.id == "groq")
        assert groq.tokens_per_day == 200_000

    def test_openrouter_com_credito_comprado_sobe_o_teto_diario(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or")
        assert llm_cascade.cascade(60)[0].calls_per_day == 50
        monkeypatch.setenv("LLM_OPENROUTER_RPD", "1000")
        assert llm_cascade.cascade(60)[0].calls_per_day == 1000


class TestModelos:
    def test_cerebras_nao_usa_o_modelo_aposentado_e_se_diz_pago(self):
        cerebras = llm_cascade._BY_ID["cerebras"]
        assert cerebras.model != "llama-3.3-70b"
        assert "pago" in cerebras.label.lower()

    def test_o_qwen_do_groq_nao_e_o_aposentado(self):
        # qwen/qwen3-32b saiu do Groq em 17-jul-2026.
        assert llm_cascade._BY_ID["groq-qwen"].model != "qwen/qwen3-32b"

    def test_max_tokens_so_onde_a_resposta_seria_cortada(self):
        """NVIDIA e Cloudflare cortam a saida curta sem `max_tokens`. No Groq
        e o contrario: o pedido conta contra os 8.000 tokens/min (o 429 do log
        dizia "Requested 4535"), e um `max_tokens` alto faria todo pedido
        estourar a cota."""
        com = {p.id for p in llm_cascade._CATALOG if dict(p.extra).get("max_tokens")}
        assert com == {"nvidia", "cloudflare"}

    def test_quem_treina_com_o_conteudo_esta_marcado(self):
        treinam = {p.id for p in llm_cascade._CATALOG if p.trains_on_data}
        assert {"gemini", "gemini-lite", "nvidia", "mistral", "openrouter",
                "zai"} <= treinam
        assert not ({"groq", "groq-qwen", "groq-20b", "cloudflare"} & treinam)

    def test_todo_provedor_diz_qual_variavel_troca_o_modelo(self):
        for p in llm_cascade._CATALOG:
            assert p.model_env.endswith("_MODEL"), p.id

    def test_aviso_de_modelo_inexistente_nomeia_a_variavel_certa(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("LLM_CASCADE", "groq-qwen,groq")
        log = []

        def call(prompt, schema, provider):
            if provider.id == "groq-qwen":
                raise RuntimeError("LLM server 404 from x: model_not_found")
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60, log=log.append)
        aviso = next(linha for linha in log if "nao existe" in linha)
        assert "GROQ_QWEN_MODEL=" in aviso


class TestChaveRecusada:
    ERRO_401 = ('LLM server 401 from https://api.groq.com/openai/v1/chat/completions: '
                '{"error":{"message":"Invalid API Key","type":"invalid_request_error",'
                '"code":"invalid_api_key"}}')

    @pytest.mark.parametrize("texto", [
        ERRO_401,
        "400 INVALID_ARGUMENT. {'error': {'message': 'API key not valid. Please pass a valid API key.'}}",
        'LLM server 401 from https://openrouter.ai/api/v1/chat/completions: '
        '{"error":{"message":"User not found.","code":401}}',
    ])
    def test_reconhece_chave_recusada(self, texto):
        assert llm_cascade.chave_recusada(texto)

    @pytest.mark.parametrize("texto", [
        "LLM server 429 from x: rate limit", "503 UNAVAILABLE",
        "LLM server 404 from x: model_not_found",
        "LLM server 403 from x: region not supported",
        "validation error: 401 is not a valid start",
    ])
    def test_nao_confunde_com_outros_erros(self, texto):
        assert not llm_cascade.chave_recusada(texto)

    def test_desliga_todos_os_modelos_daquela_chave(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "errada")
        monkeypatch.setenv("NVIDIA_API_KEY", "n")
        chamados = []

        def call(prompt, schema, provider):
            chamados.append(provider.id)
            if provider.key_env == "GROQ_API_KEY":
                raise RuntimeError(self.ERRO_401)
            return {"ok": True}, {}

        log = []
        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60, log=log.append)
        # Um 401 so: o Qwen e o 20b do Groq nao gastam uma ida cada para
        # ouvir o mesmo "chave invalida".
        assert chamados == ["groq", "nvidia"]
        assert any("GROQ_API_KEY foi recusada" in linha for linha in log)
        # E nas chamadas seguintes do mesmo job, nem o Groq e tentado.
        chamados.clear()
        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60, log=log.append)
        assert chamados == ["nvidia"]

    def test_chave_recusada_nao_gasta_cota(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "errada")
        monkeypatch.setenv("NVIDIA_API_KEY", "n")

        def call(prompt, schema, provider):
            if provider.id == "groq":
                raise RuntimeError(self.ERRO_401)
            return {"ok": True}, {}

        llm_cascade.run("oi", Resposta, call=call, duration_seconds=60, log=lambda _m: None)
        assert llm_cascade.usage("groq")["calls"] == 0


class TestOcupado:
    """O 503 do log de 165 s: com outro provedor atras, nao se espera."""

    @pytest.mark.parametrize("texto", [
        "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}",
        "LLM server 429 from https://openrouter.ai/api/v1/chat/completions: Rate limit exceeded",
        "500 INTERNAL", "LLM server 502 from x: bad gateway", "The read operation timed out",
    ])
    def test_erros_de_capacidade(self, texto):
        assert llm_cascade.erro_de_capacidade(texto)

    @pytest.mark.parametrize("texto", [
        "Gemini returned an empty response body.",
        "Gemini response did not contain a JSON object.",
        "1 validation error for ScoreResponse: score less than 1500",
        "Rate limit reached ... Requested 4535",  # "rate limit" conta; o numero nao
    ])
    def test_codigo_so_como_palavra_inteira(self, texto):
        esperado = "rate limit" in texto.lower()
        assert llm_cascade.erro_de_capacidade(texto) is esperado

    def test_o_gemini_ganha_alternativa_com_a_cascata_ampliada(self, monkeypatch):
        """Com so Groq e Gemini, o Gemini era o ultimo e esperava; com as
        mesmas duas chaves, agora o Qwen e o 3.5 Flash-Lite estao atras dele."""
        monkeypatch.setenv("GROQ_API_KEY", "g")
        monkeypatch.setenv("GEMINI_API_KEY", "m")
        visto = {}

        def call(prompt, schema, provider):
            visto[provider.id] = llm_cascade._HA_ALTERNATIVA.get()
            if provider.id in ("groq", "gemini"):
                raise RuntimeError("503 UNAVAILABLE")
            return {"ok": True}, {}

        _, custo = llm_cascade.run("oi", Resposta, call=call, duration_seconds=60,
                                   log=lambda _m: None)
        assert visto == {"groq": True, "gemini": True, "groq-qwen": True}
        assert custo["provider"] == "groq-qwen"


class TestTimeout:
    def test_nuvem_nao_herda_os_dez_minutos_do_modelo_local(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "n")
        (nvidia,) = llm_cascade.cascade(60)
        assert llm_cascade.timeout_para(nvidia) == llm_cascade.TIMEOUT_NUVEM_S < 600
        monkeypatch.setenv("LLM_TIMEOUT_NUVEM", "45")
        assert llm_cascade.timeout_para(nvidia) == 45

    def test_ollama_local_fica_com_o_padrao_do_backend(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        (local,) = llm_cascade.cascade(60)
        assert llm_cascade.timeout_para(local) is None


class TestPrefiltro:
    def test_os_novos_nao_apertam_o_orcamento(self, monkeypatch):
        """O pre-filtro corta pelo MENOR teto de tokens/dia publicado da
        cadeia. Os provedores novos publicam teto de CHAMADAS (ou nenhum), e
        os modelos extras do Groq tem o mesmo teto do principal: com tudo
        ligado, o orcamento e o mesmo de so ter o Groq."""
        monkeypatch.setenv("GROQ_API_KEY", "g")
        so_groq = prefilter.tokens_disponiveis_hoje(llm_cascade.cascade(60))
        _todas(monkeypatch)
        monkeypatch.delenv("CEREBRAS_API_KEY")          # pago: fora da conta
        tudo = prefilter.tokens_disponiveis_hoje(llm_cascade.cascade(60))
        assert so_groq == tudo == 200_000


def test_o_main_passa_o_timeout_e_sabe_pular_sem_dica():
    """O `main.py` so importa com torch; o CI le a arvore. A chamada por
    provedor leva o timeout da nuvem, e o aviso de pular nao pode formatar
    uma dica que nao existe (o 503 do Gemini nao traz "retry in")."""
    import ast
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
    arvore = ast.parse(open(caminho, encoding="utf-8").read())
    funcao = next(n for n in ast.walk(arvore)
                  if isinstance(n, ast.FunctionDef) and n.name == "_run_gemini_stage")
    fonte = ast.unparse(funcao)
    assert "timeout=llm_cascade.timeout_para(provider)" in fonte
    assert "extra_body=dict(provider.extra) or None" in fonte
    assert "if dica is None:" in fonte
    assert "llm_cascade.espera_sugerida(msg):.0f" not in fonte
