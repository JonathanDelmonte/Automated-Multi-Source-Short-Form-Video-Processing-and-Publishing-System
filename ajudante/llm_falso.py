"""Um servidor de LLM de mentira, compativel com OpenAI, para o teste de ponta
a ponta do ajudante (``ponta_a_ponta.py``).

O CI nao tem chave de IA nenhuma -- e nem deve ter: o que se quer provar ali e
que o MOTOR roda no Windows, nao que o Groq responde. Entao a deteccao de
momentos fala com isto, pelo caminho que ja existe para LLM local
(``LLM_BASE_URL``, ``llm_backend.py``), e recebe respostas no formato exato que
o ``gemini_worker`` valida.

As respostas nao sao inventadas no vazio: as janelas vem do proprio prompt
(``windows_json``), entao o corte cai dentro do que foi transcrito, e o resto do
pipeline -- corte, reenquadramento, legenda -- trabalha em trecho de verdade.

Stdlib pura: sobe numa thread do proprio teste.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# `json.dumps` padrao do `main._payload`: {"id": "window_001", "start": 0.0, ...}
_JANELA = re.compile(
    r'\{"id": "(window_\d+)", "start": ([0-9.]+), "end": ([0-9.]+)')


def janelas_do_prompt(prompt: str) -> list:
    return [(i, float(a), float(b)) for i, a, b in _JANELA.findall(prompt)]


def resposta_de_nota(janelas: list) -> dict:
    return {"windows": [
        {"id": i, "start": a, "end": b, "score": 90 - n,
         "reason": "trecho de teste do ajudante"}
        for n, (i, a, b) in enumerate(janelas)]}


def resposta_de_detalhe(janelas: list, duracao_max: float = 25.0) -> dict:
    """Um corte por janela, comecando um segundo depois e com no maximo
    ``duracao_max``. Janela que nao rende 12 s fica de fora: o teste pede cortes
    de 10 s para cima, e um corte curto demais seria recusado pelo pipeline --
    o teste falharia medindo a resposta falsa, e nao o motor."""
    cortes = []
    for i, a, b in janelas:
        inicio = a + 1.0
        fim = min(b - 0.5, inicio + duracao_max)
        if fim - inicio < 12:
            continue
        cortes.append({
            "start": round(inicio, 2), "end": round(fim, 2),
            "source_window_id": i, "predicted_score": 88,
            "video_description_for_tiktok": "Teste do ajudante no Windows",
            "video_description_for_instagram": "Teste do ajudante no Windows",
            "video_title_for_youtube_short": "Teste do ajudante",
            "viral_hook_text": "Funciona no Windows",
        })
    return {"shorts": cortes}


def responder(corpo: dict) -> dict:
    """O que o servidor devolve para um pedido de ``/chat/completions``."""
    mensagens = corpo.get("messages") or []
    prompt = "\n".join(str(m.get("content") or "") for m in mensagens)
    formato = corpo.get("response_format") or {}
    nome = ((formato.get("json_schema") or {}).get("name") or "").lower()
    janelas = janelas_do_prompt(prompt)
    # Sem `response_format` (a terceira tentativa do llm_backend) decide pelo
    # proprio prompt: so o de detalhe pede `predicted_score`.
    if nome == "detailresponse" or (not nome and "predicted_score" in prompt):
        conteudo = resposta_de_detalhe(janelas)
    elif nome == "scoreresponse" or (not nome and janelas):
        conteudo = resposta_de_nota(janelas)
    else:
        conteudo = {}
    return {
        "id": "falso", "object": "chat.completion", "model": corpo.get("model"),
        "choices": [{"index": 0, "finish_reason": "stop",
                     "message": {"role": "assistant",
                                 "content": json.dumps(conteudo)}}],
        "usage": {"prompt_tokens": len(prompt) // 4, "completion_tokens": 50},
    }


class _Tratador(BaseHTTPRequestHandler):
    pedidos: list = []

    def do_POST(self):  # noqa: N802 (nome do http.server)
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
        _Tratador.pedidos.append(corpo)
        dados = json.dumps(responder(corpo)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *args):  # silencio: o log do teste e o do motor
        pass


def subir(porta: int = 8765) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), _Tratador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def pedidos() -> list:
    return list(_Tratador.pedidos)
