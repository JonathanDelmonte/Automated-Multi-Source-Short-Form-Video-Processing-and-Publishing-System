"""Quem o servidor deixa ler as respostas (`origens.py`, Fase 6, 24-set-2026).

Ate o painel ganhar endereco publico, o CORS refletia qualquer origem com
credenciais: qualquer site aberto no mesmo navegador lia os projetos, os logs e
os videos de `localhost:8000`. Agora so o site oficial (e as URLs de versao
dele) e as paginas da propria maquina.

O erro que estes testes existem para pegar tem dois lados, e os dois sao
silenciosos: aberto demais, nada quebra e a protecao some; fechado demais, o
site fica em "conectando ao servidor" para sempre, sem erro no servidor --
quem recusa a resposta e o navegador.
"""
import asyncio
import re
from pathlib import Path

import httpx
import pytest
from fastapi.middleware.cors import CORSMiddleware

import origens

RAIZ = Path(__file__).resolve().parent.parent
SITE = origens.SITE_OFICIAL
REGEX_PADRAO = origens.regex_das_origens(origens.origens_do_painel({}))


@pytest.mark.parametrize("origem", [
    SITE,
    # URL de versao, que o Cloudflare da a cada deploy: mesma conta.
    "https://9e8b7e80-virtu-clips.zirtuno.workers.dev",
    "http://localhost:5175",
    "http://localhost:5173",
    "http://localhost",
    "http://127.0.0.1:8000",
    "http://[::1]:5175",
])
def test_aceita_o_site_e_a_propria_maquina(origem):
    assert origens.permitida(origem, REGEX_PADRAO)


@pytest.mark.parametrize("origem", [
    "https://site-qualquer.com",
    "null",
    # Sufixo e prefixo: o `fullmatch` e o que barra os dois.
    "https://virtu-clips.zirtuno.workers.dev.site-qualquer.com",
    "https://virtu-clips.zirtuno.workers.dev:444",
    "http://localhost.site-qualquer.com",
    "http://localhost:5175.site-qualquer.com",
    # Mesmo nome, outra conta do Cloudflare: qualquer um cria.
    "https://virtu-clips.outra-conta.workers.dev",
    # http no lugar de https: o workers.dev so serve https.
    "http://virtu-clips.zirtuno.workers.dev",
    # Um IP da rede nao e a propria maquina.
    "http://192.168.0.10:5175",
])
def test_recusa_o_resto(origem):
    assert not origens.permitida(origem, REGEX_PADRAO)


def test_sem_variavel_vale_o_site_oficial():
    assert origens.origens_do_painel({}) == [SITE]


@pytest.mark.parametrize("bruto", ["", "   ", ",", " , ,"])
def test_variavel_em_branco_nao_tranca_o_painel(bruto):
    """Uma lista vazia deixaria o site publicado sem servidor, sem erro nenhum."""
    assert origens.origens_do_painel({"ORIGENS_DO_PAINEL": bruto}) == [SITE]


def test_variavel_troca_a_lista():
    env = {"ORIGENS_DO_PAINEL": " https://cortes.exemplo.com/ , https://outro.exemplo.com"}
    lista = origens.origens_do_painel(env)
    assert lista == ["https://cortes.exemplo.com", "https://outro.exemplo.com"]
    regex = origens.regex_das_origens(lista)
    assert origens.permitida("https://cortes.exemplo.com", regex)
    assert not origens.permitida(SITE, regex)
    # O ponto do endereco e literal, nao "qualquer caractere".
    assert not origens.permitida("https://cortesXexemplo.com", regex)
    # As locais continuam.
    assert origens.permitida("http://localhost:5175", regex)


def test_o_site_oficial_e_o_nome_do_wrangler():
    """Renomear o projeto no Cloudflare sem trocar `SITE_OFICIAL` trancaria o
    site novo para fora do servidor -- e o sintoma seria so o painel girando."""
    fonte = (RAIZ / "dashboard" / "wrangler.jsonc").read_text(encoding="utf-8")
    nome = re.search(r'"name":\s*"([^"]+)"', fonte).group(1)
    assert SITE.startswith(f"https://{nome}.")


# --- a API de verdade -------------------------------------------------------

def _pedir(metodo, caminho, cabecalhos):
    from app import app

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as c:
            return await c.request(metodo, caminho, headers=cabecalhos)
    return asyncio.run(_run())


def test_a_api_responde_ao_site():
    r = _pedir("GET", "/api/config", {"Origin": SITE})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == SITE


def test_a_api_nao_entrega_a_resposta_a_outro_site():
    """O pedido chega (CORS nao e firewall), mas sem o cabecalho o navegador
    nao deixa a pagina ler a resposta."""
    r = _pedir("GET", "/api/config", {"Origin": "https://site-qualquer.com"})
    assert "access-control-allow-origin" not in r.headers


def test_preflight_do_site_passa_e_o_de_outro_nao():
    pedido = {"Access-Control-Request-Method": "POST",
              "Access-Control-Request-Headers": "authorization, content-type"}
    ok = _pedir("OPTIONS", "/api/process", {"Origin": SITE, **pedido})
    assert ok.status_code == 200
    assert ok.headers.get("access-control-allow-origin") == SITE
    # Sem preflight aprovado o navegador nem manda o POST com JSON ou o DELETE.
    fora = _pedir("OPTIONS", "/api/process", {"Origin": "https://site-qualquer.com", **pedido})
    assert fora.status_code == 400


@pytest.mark.skipif(
    "allow_private_network" not in __import__("inspect").signature(CORSMiddleware.__init__).parameters,
    reason="Starlette sem suporte ao preflight de rede privada")
def test_preflight_de_rede_privada_do_site_passa():
    r = _pedir("OPTIONS", "/api/config", {
        "Origin": SITE,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Private-Network": "true",
    })
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-private-network") == "true"


# --- origem estrita: quem MANDA pedido que altera algo (ajudante, Fase 6.2) ----

@pytest.fixture
def estrita(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "_ORIGEM_ESTRITA", True)


def test_formulario_de_outro_site_nao_dispara_nada(estrita):
    """O ataque que o CORS nao pega: um POST simples, sem preflight. Ele
    chegava ao endpoint -- a pagina so nao lia a resposta, e o job rodava."""
    r = _pedir("POST", "/api/jobs/qualquer/cancel", {"Origin": "https://site-qualquer.com"})
    assert r.status_code == 403
    r = _pedir("DELETE", "/api/jobs/qualquer", {"Origin": "null"})  # iframe isolado, file://
    assert r.status_code == 403


@pytest.mark.parametrize("cabecalhos", [
    {"Origin": SITE},
    {"Origin": "http://localhost:5175"},
    {},  # sem Origin e programa (o ajudante, curl, MCP), nao navegador
])
def test_o_site_a_maquina_e_os_programas_passam(estrita, cabecalhos):
    r = _pedir("POST", "/api/jobs/nao-existe/cancel", cabecalhos)
    assert r.status_code != 403


def test_leitura_continua_com_o_cors(estrita):
    r = _pedir("GET", "/api/config", {"Origin": "https://site-qualquer.com"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers


def test_sem_a_origem_estrita_nada_muda():
    """O Docker nao liga: o painel aberto de outro aparelho da rede chega pelo
    proxy do Vite com a origem daquele aparelho."""
    import app as app_module
    assert app_module._ORIGEM_ESTRITA is False
    r = _pedir("POST", "/api/jobs/nao-existe/cancel", {"Origin": "http://192.168.0.10:5175"})
    assert r.status_code != 403


def test_o_ajudante_liga_a_origem_estrita(tmp_path):
    import sys
    sys.path.insert(0, str(RAIZ / "ajudante"))
    import ajudante
    env = ajudante.ambiente_do_motor(ajudante.Caminhos(tmp_path), False, {})
    assert env["CORTES_ORIGEM_ESTRITA"] == "1"
