"""As chaves de IA coladas nas Configuracoes do site (chaves_ia.py, 25-set-2026).

O que estes testes prendem, em ordem de importancia:

1. **a chave nunca sai inteira** -- nem no estado que vai ao site, nem no log;
2. **so as variaveis da lista entram no ambiente** do processo: o site escreve
   ali, e um nome livre trocaria `PATH` ou `OUTPUT_DIR`;
3. **a colada vence o `.env`, e tira-la devolve a do `.env`**;
4. **a recusada pelo provedor nao entra**, e o resto (fila cheia, sem rede)
   entra dizendo que nao deu para conferir;
5. a tela do painel, o motor e a cascata falam das MESMAS chaves.
"""
import asyncio
import json
import os
import re
from pathlib import Path

import httpx
import pytest

import chaves_ia as ci
import llm_cascade

RAIZ = Path(__file__).resolve().parent.parent

GROQ = "gsk_" + "A1b2C3d4E5f6G7h8I9j0" * 2
GEMINI_NOVA = "AQ.Ab8RN6" + "x" * 30
GEMINI_VELHA = "AIzaSy" + "B" * 33

# O que estes testes tocam no `os.environ`: as chaves, e o que mais faria a
# cascata achar uma IA configurada na maquina que roda o teste.
_NOMES = ci.VARIAVEIS + ("CEREBRAS_API_KEY", "OLLAMA_BASE_URL", "LLM_BASE_URL", "LLM_CASCADE")


def _foto():
    return {v: os.environ.get(v) for v in _NOMES}


def _devolver(foto):
    for v, valor in foto.items():
        if valor is None:
            os.environ.pop(v, None)
        else:
            os.environ[v] = valor


@pytest.fixture(autouse=True, scope="module")
def _nada_fica_para_os_outros_testes():
    """O alarme do vazamento de 25-set-2026 (ver o `ambiente`), e em TODO CI.
    Sem ele, so o do Windows via: e o unico onde o `main` importa, entao os
    testes que tropecavam na chave esquecida so rodavam la."""
    antes = _foto()
    yield
    ficou = sorted(v for v, valor in _foto().items() if valor != antes[v])
    _devolver(antes)
    assert not ficou, f"os testes das chaves deixaram no os.environ: {ficou}"


@pytest.fixture
def ambiente(monkeypatch):
    """Um ambiente sem nenhuma das chaves, devolvido como estava no fim.

    O monkeypatch sozinho NAO devolvia, e este docstring dizia o contrario.
    Para uma variavel que nao existia, o `delenv` nao guarda nada para
    desfazer, e a `Chaves` escreve direto no `os.environ`: a GROQ_API_KEY
    falsa ficava para os testes seguintes. No CI do Windows -- o unico onde o
    `main` importa -- os testes do `main` passaram a ir pela cascata em vez do
    caminho sem chave (25-set-2026). E o desfazer do monkeypatch, que roda
    DEPOIS deste fixture, poria de volta a chave que um `ambiente.delenv` no
    meio do teste tirou. Por isso: desfaz o monkeypatch aqui, e devolve a foto
    por ultimo.
    """
    foto = _foto()
    for v in _NOMES:
        monkeypatch.delenv(v, raising=False)
    yield monkeypatch
    monkeypatch.undo()
    _devolver(foto)


# --- o que se cola ------------------------------------------------------------------------

@pytest.mark.parametrize("variavel, colado", [
    ("GROQ_API_KEY", GROQ),
    ("GEMINI_API_KEY", GEMINI_NOVA),
    ("GEMINI_API_KEY", GEMINI_VELHA),
    ("NVIDIA_API_KEY", "nvapi-" + "Zz9_" * 10),
    ("OPENROUTER_API_KEY", "sk-or-v1-" + "0a" * 32),
    ("CLOUDFLARE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef"),
    ("CLOUDFLARE_API_TOKEN", "Ab_cd-EF" * 5),
    ("ZAI_API_KEY", "3f5a" * 8 + ".Qk9x" * 4),
])
def test_as_chaves_de_verdade_passam(variavel, colado):
    assert ci.limpar(variavel, colado) == colado


@pytest.mark.parametrize("colado", [
    f"  {GROQ}  ",
    f'"{GROQ}"',
    f"'{GROQ}'",
    f"GROQ_API_KEY={GROQ}",
    f"GROQ_API_KEY=\"{GROQ}\"",
    f"Bearer {GROQ}",
    f"{GROQ}\n",
])
def test_os_jeitos_comuns_de_colar_errado_sao_consertados(colado):
    assert ci.limpar("GROQ_API_KEY", colado) == GROQ


@pytest.mark.parametrize("variavel, colado, codigo", [
    ("PATH", "/usr/bin:/bin", "desconhecida"),
    ("OUTPUT_DIR", "/tmp/outro", "desconhecida"),
    ("GROQ_API_KEY", "gsk_abc", "curta"),
    ("GROQ_API_KEY", "g" * 401, "longa"),
    ("GROQ_API_KEY", "gsk_abc def ghi jkl", "caracteres"),
    # Uma quebra de linha DENTRO da chave e um cabecalho HTTP injetado.
    ("GROQ_API_KEY", "gsk_abcdefgh\r\nX-Outro: 1", "caracteres"),
    ("GROQ_API_KEY", "gsk_ação" + "a" * 20, "caracteres"),
    ("GROQ_API_KEY", 12345678901234, "texto"),
])
def test_o_que_nao_e_chave_e_recusado(variavel, colado, codigo):
    with pytest.raises(ci.ChaveInvalida) as e:
        ci.limpar(variavel, colado)
    assert e.value.codigo == codigo and e.value.variavel == variavel


def test_o_pedido_e_conferido_inteiro_e_vazio_e_remover():
    assert ci.limpar_pedido({"GROQ_API_KEY": GROQ, "GEMINI_API_KEY": None,
                             "NVIDIA_API_KEY": "  "}) == {
        "GROQ_API_KEY": GROQ, "GEMINI_API_KEY": None, "NVIDIA_API_KEY": None}
    with pytest.raises(ci.ChaveInvalida):
        ci.limpar_pedido({"PATH": None})
    # Uma ruim derruba o pedido inteiro, antes de gravar qualquer coisa.
    with pytest.raises(ci.ChaveInvalida):
        ci.limpar_pedido({"GROQ_API_KEY": GROQ, "GEMINI_API_KEY": "curta"})


# --- guardar -------------------------------------------------------------------------------

def test_a_colada_vence_o_env_e_tirar_devolve_o_env(tmp_path, ambiente):
    ambiente.setenv("GROQ_API_KEY", "gsk_do_env_" + "x" * 20)
    chaves = ci.Chaves(tmp_path)
    assert chaves.estado()["GROQ_API_KEY"]["origem"] == "arquivo"

    chaves.trocar({"GROQ_API_KEY": GROQ})
    assert os.environ["GROQ_API_KEY"] == GROQ
    assert chaves.estado()["GROQ_API_KEY"]["origem"] == "site"

    chaves.trocar({"GROQ_API_KEY": None})
    assert os.environ["GROQ_API_KEY"] == "gsk_do_env_" + "x" * 20
    assert chaves.estado()["GROQ_API_KEY"]["origem"] == "arquivo"


def test_sem_env_tirar_tira_do_ambiente(tmp_path, ambiente):
    chaves = ci.Chaves(tmp_path)
    chaves.trocar({"GEMINI_API_KEY": GEMINI_NOVA})
    assert os.environ["GEMINI_API_KEY"] == GEMINI_NOVA
    chaves.trocar({"GEMINI_API_KEY": None})
    assert "GEMINI_API_KEY" not in os.environ
    assert chaves.estado()["GEMINI_API_KEY"] == {
        "configurada": False, "origem": None, "final": None}


def test_a_chave_guardada_volta_no_proximo_boot(tmp_path, ambiente):
    ci.Chaves(tmp_path).trocar({"GROQ_API_KEY": GROQ})
    ambiente.delenv("GROQ_API_KEY")
    ci.Chaves(tmp_path)  # o motor subindo de novo
    assert os.environ["GROQ_API_KEY"] == GROQ


def test_o_estado_nunca_leva_a_chave_inteira(tmp_path, ambiente):
    chaves = ci.Chaves(tmp_path)
    chaves.trocar({"GROQ_API_KEY": GROQ, "CLOUDFLARE_ACCOUNT_ID": "0123456789abcdef"})
    estado = chaves.estado()
    assert GROQ not in json.dumps(estado)
    assert estado["GROQ_API_KEY"]["final"] == GROQ[-4:]
    # Numa chave curta, 4 caracteres seriam boa parte do segredo.
    assert estado["CLOUDFLARE_ACCOUNT_ID"]["final"] == "cdef"
    assert ci.final_de("12345678") is None


@pytest.mark.skipif(os.name == "nt", reason="permissao de arquivo e do POSIX")
def test_o_arquivo_nasce_so_para_o_dono(tmp_path, ambiente):
    chaves = ci.Chaves(tmp_path)
    chaves.trocar({"GROQ_API_KEY": GROQ})
    assert (chaves.arquivo.stat().st_mode & 0o777) == 0o600
    assert json.loads(chaves.arquivo.read_text()) == {"GROQ_API_KEY": GROQ}


def test_arquivo_estragado_nao_derruba_e_nao_vaza(tmp_path, ambiente, capsys):
    (tmp_path / ci.ARQUIVO).write_text('{"GROQ_API_KEY": "' + GROQ + '", ', encoding="utf-8")
    chaves = ci.Chaves(tmp_path)
    assert chaves.salvas == {}
    assert GROQ not in capsys.readouterr().out


def test_do_arquivo_so_entra_o_que_a_lista_conhece(tmp_path, ambiente):
    (tmp_path / ci.ARQUIVO).write_text(json.dumps({
        "PATH": "/tmp/malicioso", "GROQ_API_KEY": GROQ, "NVIDIA_API_KEY": "com espaco no meio"}),
        encoding="utf-8")
    caminho = os.environ.get("PATH")
    chaves = ci.Chaves(tmp_path)
    assert chaves.salvas == {"GROQ_API_KEY": GROQ}
    assert os.environ.get("PATH") == caminho


def test_se_o_disco_recusa_nada_muda(tmp_path, ambiente):
    chaves = ci.Chaves(tmp_path / "data")
    (tmp_path / "data").write_text("sou um arquivo, nao uma pasta")
    with pytest.raises(OSError):
        chaves.trocar({"GROQ_API_KEY": GROQ})
    assert chaves.salvas == {} and "GROQ_API_KEY" not in os.environ


# --- conferir com o provedor ------------------------------------------------------------------

def _cliente(responder):
    pedidos = []

    def transporte(pedido):
        pedidos.append(pedido)
        return responder(pedido)

    def fabrica():
        return httpx.Client(transport=httpx.MockTransport(transporte))
    fabrica.pedidos = pedidos
    return fabrica


def test_o_gemini_e_conferido_no_endpoint_nativo_sem_gastar_cota():
    """As chaves `AQ.` dao 401 no caminho compativel com OpenAI (.env.example)."""
    fab = _cliente(lambda p: httpx.Response(200, json={"models": []}))
    r = ci.testar("GEMINI_API_KEY", {"GEMINI_API_KEY": GEMINI_NOVA}, cliente=fab)
    assert r == {"resultado": "ok", "status": 200}
    (pedido,) = fab.pedidos
    assert pedido.method == "GET" and "generativelanguage.googleapis.com/v1beta/models" in str(pedido.url)
    assert pedido.headers["x-goog-api-key"] == GEMINI_NOVA
    assert "openai" not in str(pedido.url) and "authorization" not in pedido.headers


def test_os_outros_sao_conferidos_como_a_cascata_vai_chamar():
    fab = _cliente(lambda p: httpx.Response(200, json={"choices": []}))
    ci.testar("GROQ_API_KEY", {"GROQ_API_KEY": GROQ}, cliente=fab)
    (pedido,) = fab.pedidos
    groq = next(p for p in llm_cascade._CATALOG if p.id == "groq")
    assert str(pedido.url) == f"{groq.base_url}/chat/completions"
    assert pedido.headers["authorization"] == f"Bearer {GROQ}"
    assert json.loads(pedido.content)["model"] == groq.model


def test_o_cloudflare_precisa_da_conta_e_vai_ao_endereco_dela(monkeypatch):
    fab = _cliente(lambda p: httpx.Response(200, json={}))
    token = "Ab_cd-EF" * 5
    sem_conta = ci.testar("CLOUDFLARE_API_TOKEN", {"CLOUDFLARE_API_TOKEN": token}, cliente=fab)
    assert sem_conta["resultado"] == "incompleto" and fab.pedidos == []

    conta = "0123456789abcdef0123456789abcdef"
    ci.testar("CLOUDFLARE_API_TOKEN", {"CLOUDFLARE_API_TOKEN": token,
                                       "CLOUDFLARE_ACCOUNT_ID": conta}, cliente=fab)
    # O mesmo endereco que a cascata monta.
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", conta)
    cf = next(p for p in llm_cascade._CATALOG if p.id == "cloudflare")
    assert str(fab.pedidos[0].url) == f"{llm_cascade._base_url(cf)}/chat/completions"


@pytest.mark.parametrize("status, corpo, resultado", [
    (200, "{}", "ok"),
    (401, '{"error": "invalid_api_key"}', "recusada"),
    (400, '{"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}',
     "recusada"),
    (400, '{"error": {"message": "API key not valid. Please pass a valid API key."}}', "recusada"),
    # 403 tambem e "regiao nao atendida" ou "modelo sem acesso": nao e a chave.
    (403, '{"error": "forbidden"}', "incerto"),
    (404, '{"error": "model_not_found"}', "incerto"),
    (429, '{"error": "rate_limit"}', "ocupado"),
    (503, "high demand", "sem_resposta"),
])
def test_a_resposta_do_provedor(status, corpo, resultado):
    fab = _cliente(lambda p: httpx.Response(status, text=corpo))
    assert ci.testar("GROQ_API_KEY", {"GROQ_API_KEY": GROQ}, cliente=fab) == {
        "resultado": resultado, "status": status}


def test_sem_rede_nao_da_para_saber():
    def cai(_pedido):
        raise httpx.ConnectError("sem rede")
    r = ci.testar("GROQ_API_KEY", {"GROQ_API_KEY": GROQ}, cliente=_cliente(cai))
    assert r == {"resultado": "sem_resposta", "status": None}


def test_um_teste_por_provedor_que_ganhou_chave():
    assert ci.provedores_a_testar({
        "GROQ_API_KEY": GROQ, "GEMINI_API_KEY": None,
        "CLOUDFLARE_API_TOKEN": "t" * 20, "CLOUDFLARE_ACCOUNT_ID": "c" * 32,
    }) == ["GROQ_API_KEY", "CLOUDFLARE_API_TOKEN"]


# --- a tela, o motor e a cascata falam das mesmas chaves ---------------------------------------

#: Fora da tela de proposito: o Cerebras deixou de ser gratis, e o Ollama local
#: tem endereco, nao chave. Os dois continuam valendo pelo .env.
FORA_DA_TELA = {"cerebras", "ollama"}


def test_toda_chave_da_cascata_gratuita_tem_campo():
    da_cascata = {p.key_env for p in llm_cascade._CATALOG if p.id not in FORA_DA_TELA}
    assert da_cascata | {"CLOUDFLARE_ACCOUNT_ID"} == set(ci.VARIAVEIS)


def _provedores_do_painel():
    texto = (RAIZ / "dashboard" / "src" / "lib" / "provedoresDeIA.js").read_text(encoding="utf-8")
    blocos = re.split(r"\n  \{\n", texto)[1:]
    saida = []
    for b in blocos:
        saida.append({
            "id": re.search(r"id: '([^']+)'", b).group(1),
            "variaveis": re.findall(r"variavel: '([^']+)'", b),
            "treina": re.search(r"treina: (true|false)", b).group(1) == "true",
            "link": re.search(r"link: '([^']+)'", b).group(1),
        })
    return saida


def test_a_tela_do_painel_tem_as_mesmas_chaves_do_motor():
    painel = _provedores_do_painel()
    assert len(painel) == 8
    assert sorted(v for p in painel for v in p["variaveis"]) == sorted(ci.VARIAVEIS)


def test_o_aviso_de_treino_da_tela_e_o_da_cascata():
    """O painel diz quem usa o conteudo para treinar a IA; quem sabe e a cascata."""
    for p in _provedores_do_painel():
        treina = {q.trains_on_data for q in llm_cascade._CATALOG
                  if q.key_env in p["variaveis"] and q.id not in FORA_DA_TELA}
        assert treina == {p["treina"]}, p["id"]


def test_os_links_da_tela_sao_os_do_env_example():
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    for p in _provedores_do_painel():
        assert p["link"] in exemplo, p["id"]


# --- as rotas -------------------------------------------------------------------------------------

import app as app_module  # noqa: E402


def _pedir(metodo, caminho, corpo=None, tipo="application/json"):
    async def _run():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            cabecalhos = {"Content-Type": tipo} if tipo else {}
            conteudo = json.dumps(corpo) if corpo is not None else None
            return await c.request(metodo, caminho, content=conteudo, headers=cabecalhos)
    return asyncio.run(_run())


@pytest.fixture
def motor(tmp_path, ambiente):
    """O `CHAVES` do app com um arquivo so do teste, e o teste de chave falso."""
    ambiente.setattr(app_module, "CHAVES", ci.Chaves(tmp_path))
    respostas = {}
    ambiente.setattr(ci, "testar", lambda variavel, valores: respostas.get(
        variavel, {"resultado": "ok", "status": 200}))
    return respostas


def test_ver_as_chaves_nao_traz_a_chave(motor):
    app_module.CHAVES.trocar({"GROQ_API_KEY": GROQ})
    r = _pedir("GET", "/api/chaves", tipo=None)
    assert r.status_code == 200 and GROQ not in r.text
    assert r.json()["variaveis"]["GROQ_API_KEY"] == {
        "configurada": True, "origem": "site", "final": GROQ[-4:]}


@pytest.mark.parametrize("tipo", [None, "text/plain"])
def test_trocar_so_aceita_json(motor, tipo):
    r = _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": GROQ}}, tipo=tipo)
    assert r.status_code == 415 and "GROQ_API_KEY" not in os.environ


def test_colar_a_chave_liga_a_cascata(motor, capsys):
    """O ponto inteiro: depois de colar, o painel para de pedir chave."""
    assert _pedir("GET", "/api/config", tipo=None).json()["localLlm"] is None
    r = _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": f"  {GROQ} "}})
    assert r.status_code == 200
    assert r.json()["testes"] == {"GROQ_API_KEY": {"resultado": "ok", "status": 200}}
    assert os.environ["GROQ_API_KEY"] == GROQ
    config = _pedir("GET", "/api/config", tipo=None).json()
    assert config["localLlm"] is not None and config["geminiNoMotor"] is False
    assert GROQ not in capsys.readouterr().out, "a chave nunca vai para o log"


def test_a_chave_do_gemini_no_motor_destrava_o_studio(motor):
    _pedir("POST", "/api/chaves", {"chaves": {"GEMINI_API_KEY": GEMINI_NOVA}})
    assert _pedir("GET", "/api/config", tipo=None).json()["geminiNoMotor"] is True


def test_a_recusada_nao_entra(motor):
    motor["GROQ_API_KEY"] = {"resultado": "recusada", "status": 401}
    r = _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": GROQ}})
    assert r.status_code == 422
    assert r.json()["detail"] == {"erro": "recusada", "variavel": "GROQ_API_KEY", "status": 401}
    assert "GROQ_API_KEY" not in os.environ and not app_module.CHAVES.arquivo.exists()


@pytest.mark.parametrize("resultado", ["sem_resposta", "ocupado", "incerto"])
def test_sem_poder_conferir_guarda_e_diz(motor, resultado):
    motor["GROQ_API_KEY"] = {"resultado": resultado, "status": None}
    r = _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": GROQ}})
    assert r.status_code == 200 and os.environ["GROQ_API_KEY"] == GROQ
    assert r.json()["testes"]["GROQ_API_KEY"]["resultado"] == resultado


@pytest.mark.parametrize("corpo, erro", [
    ({"chaves": {"PATH": "/tmp/malicioso"}}, "desconhecida"),
    ({"chaves": {"GROQ_API_KEY": "gsk abc def ghi"}}, "caracteres"),
    ({"chaves": {}}, "vazio"),
    ({"outra": 1}, "vazio"),
])
def test_o_que_nao_e_chave_volta_com_o_motivo(motor, corpo, erro):
    caminho = os.environ.get("PATH")
    r = _pedir("POST", "/api/chaves", corpo)
    assert r.status_code == 422 and r.json()["detail"]["erro"] == erro
    assert os.environ.get("PATH") == caminho


def test_remover_pelo_site(motor):
    _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": GROQ}})
    r = _pedir("POST", "/api/chaves", {"chaves": {"GROQ_API_KEY": None}})
    assert r.status_code == 200 and r.json()["testes"] == {}
    assert "GROQ_API_KEY" not in os.environ
    assert r.json()["variaveis"]["GROQ_API_KEY"]["configurada"] is False
