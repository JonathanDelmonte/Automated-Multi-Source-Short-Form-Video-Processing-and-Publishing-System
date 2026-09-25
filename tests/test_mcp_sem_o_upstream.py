"""O que o agente ve do motor (25-set-2026): o nome, os links e o quadro.

Tres heranças do produto em nuvem do upstream, que so apareciam para quem
ligasse um agente ao Virtu Clips:

1. o motor se apresentava como "OpenShorts" e dizia ao agente que o video era
   analisado "nos servidores dele" -- aqui e o computador de quem usa, e o
   agente repete o que le;
2. os links dos cortes saiam relativos ("/videos/..."), porque so o
   `PUBLIC_API_URL` da nuvem os tornava absolutos: o agente entregava um link
   que ninguem abre;
3. o quadro de cortes tinha um botao de publicar que chamava `publish_clip`,
   ferramenta que saiu na Fase 0.3.
"""
import ast
import asyncio
import json
import re
from pathlib import Path

import httpx
from starlette.requests import Request

import app as app_module
import mcp_server
import mcp_ui
from app import app

RAIZ = Path(__file__).resolve().parent.parent


def test_o_agente_conhece_o_virtu_clips_e_nao_o_upstream():
    texto = json.dumps([mcp_server.SERVER_INFO, mcp_server.INSTRUCTIONS,
                        mcp_server.TOOLS, mcp_ui.RESOURCES, mcp_ui.clip_picker_html()],
                       ensure_ascii=False).lower()
    # O cabecalho da assinatura do webhook fica: e contrato de quem recebe o
    # aviso, e renomea-lo quebraria a conferencia do outro lado sem ninguem ver.
    texto = texto.replace("x-openshorts-signature", "")
    assert "openshorts" not in texto
    assert mcp_server.SERVER_INFO["name"] == "virtu-clips"
    assert "own servers" not in mcp_server.INSTRUCTIONS
    assert "user's own computer" in mcp_server.INSTRUCTIONS


def test_o_quadro_so_chama_ferramenta_que_o_motor_tem():
    nomes = {t["name"] for t in mcp_server.TOOLS}
    chamadas = re.findall(r"callTool\(\s*['\"](\w+)['\"]", mcp_ui._TEMPLATE)
    assert set(chamadas) <= nomes, f"o quadro chama o que nao existe: {set(chamadas) - nomes}"


def _link_do_corte(monkeypatch, base_url, public_api_url=None):
    if public_api_url is None:
        monkeypatch.delenv("PUBLIC_API_URL", raising=False)
    else:
        monkeypatch.setenv("PUBLIC_API_URL", public_api_url)
    app_module.jobs["mcp-link-job"] = {
        "status": "completed", "logs": [],
        "result": {"clips": [{"title": "A", "video_url": "/videos/mcp-link-job/c1.mp4",
                              "start": 0.0, "end": 10.0}]},
    }

    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=base_url) as client:
            return await client.post("/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "get_job_status", "arguments": {"job_id": "mcp-link-job"}}})
    try:
        resp = asyncio.run(_run())
    finally:
        app_module.jobs.pop("mcp-link-job", None)
    return resp.json()["result"]["structuredContent"]["clips"][0]["video_url"]


def test_o_link_do_corte_e_o_endereco_por_onde_o_agente_chegou(monkeypatch):
    assert (_link_do_corte(monkeypatch, "http://localhost:8000")
            == "http://localhost:8000/videos/mcp-link-job/c1.mp4")
    # O ajudante atende na 8001: o link segue quem chamou, nao uma porta fixa.
    assert (_link_do_corte(monkeypatch, "http://localhost:8001")
            == "http://localhost:8001/videos/mcp-link-job/c1.mp4")


def test_o_public_api_url_continua_vencendo(monkeypatch):
    assert (_link_do_corte(monkeypatch, "http://localhost:8000", "https://cortes.exemplo/")
            == "https://cortes.exemplo/videos/mcp-link-job/c1.mp4")


def test_no_stdio_o_link_fica_relativo():
    # Sem servidor web nao ha quem sirva o arquivo, e o endereco do escopo do
    # stdio e de mentira: por ele o link viraria "http://openshorts.internal/...".
    escopo = {"type": "http", "scheme": "http", "server": ("openshorts.internal", 80),
              "path": "/mcp", "headers": [], "mcp_stdio": True}
    assert mcp_server._base_de(Request(escopo)) == ""
    sem_marca = {k: v for k, v in escopo.items() if k != "mcp_stdio"}
    assert mcp_server._base_de(Request(sem_marca)) == "http://openshorts.internal"


def test_o_stdio_marca_o_proprio_escopo():
    # Importar o mcp_stdio aqui trocaria o stdout do proprio pytest (ele faz
    # isso ao carregar); le-se a fonte.
    arvore = ast.parse((RAIZ / "mcp_stdio.py").read_text(encoding="utf-8"))
    funcao = next(n for n in arvore.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_request")
    chaves = {k.value for d in ast.walk(funcao) if isinstance(d, ast.Dict)
              for k in d.keys if isinstance(k, ast.Constant)}
    assert "mcp_stdio" in chaves
