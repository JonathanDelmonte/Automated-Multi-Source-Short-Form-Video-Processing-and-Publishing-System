"""As pecas do ajudante que dao para conferir daqui, sem Windows (Fase 6.2).

O teste de verdade e o `windows.yml`: instala o motor inteiro no Windows e
processa um video. Estes pegam antes, e no CI de sempre, o que faria aquela
volta de 15 minutos falhar por bobagem -- ou, pior, passar medindo outra coisa.
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
AJUDANTE = RAIZ / "ajudante"
sys.path.insert(0, str(AJUDANTE))

import llm_falso  # noqa: E402


def _pinos(caminho):
    pinos = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha or linha.startswith("-"):
            continue
        nome = re.split(r"[<>=!~\[; ]", linha, 1)[0].lower()
        pinos[nome] = linha
    return pinos


def test_as_versoes_do_windows_sao_as_do_docker():
    """Duas listas divergem no dia em que uma delas muda. O ajudante rodando
    outra versao de faster-whisper que o Docker seria um bug que so aparece
    no computador de um amigo."""
    docker = _pinos(RAIZ / "requirements.txt")
    windows = _pinos(AJUDANTE / "requirements-windows.txt")
    fora = {"ultralytics", "torchvision"}
    assert not (fora & set(windows)), "o YOLO (AGPL) nao vai para o computador de ninguem"
    faltando = set(docker) - fora - set(windows)
    assert not faltando, f"o requirements.txt tem e o do Windows nao: {sorted(faltando)}"
    for nome, linha in windows.items():
        if nome == "yt-dlp":
            continue  # sem pino nos dois; no Windows com o [default]
        assert docker.get(nome) == linha, f"{nome}: Docker {docker.get(nome)!r} x Windows {linha!r}"


# --- o LLM falso responde no formato que o pipeline valida -------------------

gemini_worker = pytest.importorskip("gemini_worker")
JANELAS = [{"id": "window_001", "start": 0.0, "end": 38.4, "text": "hello there"},
           {"id": "window_002", "start": 30.0, "end": 41.0, "text": "bye"}]


def _prompt(modelo, **extra):
    return modelo.format(video_duration=41, language="en",
                         windows_json=json.dumps(JANELAS, ensure_ascii=False), **extra)


def test_as_janelas_saem_do_prompt_de_verdade():
    prompt = _prompt(gemini_worker.SCORE_PROMPT_TEMPLATE)
    assert llm_falso.janelas_do_prompt(prompt) == [
        ("window_001", 0.0, 38.4), ("window_002", 30.0, 41.0)]


def _responde(prompt, schema, com_formato=True):
    corpo = {"messages": [{"role": "user", "content": prompt}]}
    if com_formato:
        corpo["response_format"] = {"type": "json_schema",
                                    "json_schema": {"name": schema.__name__.lower()}}
    conteudo = llm_falso.responder(corpo)["choices"][0]["message"]["content"]
    return schema.model_validate(json.loads(conteudo))


@pytest.mark.parametrize("com_formato", [True, False])
def test_nota_valida_no_schema(com_formato):
    r = _responde(_prompt(gemini_worker.SCORE_PROMPT_TEMPLATE),
                  gemini_worker.ScoreResponse, com_formato)
    assert [w.id for w in r.windows] == ["window_001", "window_002"]


@pytest.mark.parametrize("com_formato", [True, False])
def test_detalhe_valido_e_dentro_da_janela(com_formato):
    prompt = _prompt(gemini_worker.DETAIL_PROMPT_TEMPLATE, min_clips=1, max_clips=3,
                     min_secs=15, max_secs=60)
    r = _responde(prompt, gemini_worker.DetailResponse, com_formato)
    # A janela 2 tem 11 s: menos de 12 s de corte depois das folgas, fica de fora.
    assert len(r.shorts) == 1
    corte = r.shorts[0]
    assert corte.source_window_id == "window_001"
    assert 0.0 <= corte.start < corte.end <= 38.4
    assert 15 <= corte.end - corte.start <= 60


def test_o_texto_da_fala_cabe_nas_aspas_do_powershell():
    """A frase vai entre aspas simples no comando do SAPI: um apostrofo ali
    fecha a string e o sintetizador recebe metade -- ou nada."""
    fonte = (AJUDANTE / "ponta_a_ponta.py").read_text(encoding="utf-8")
    m = re.search(r"TEXTO = \((.*?)\n\)", fonte, re.S)
    texto = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    assert "'" not in texto
    assert len(texto.split()) >= 70, "fala curta demais para um corte de 15 s"


def test_o_windows_do_github_roda_o_video_de_ponta_a_ponta():
    fluxo = (RAIZ / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in fluxo
    assert "python ajudante/ponta_a_ponta.py" in fluxo
    assert "ajudante/requirements-windows.txt" in fluxo
