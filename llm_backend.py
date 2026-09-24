"""Text-only LLM backend for the moment picker: any OpenAI-compatible server.

Ollama, LM Studio, vLLM, llama.cpp's server, LocalAI and OpenRouter all speak
``POST {base}/chat/completions``. When ``LLM_BASE_URL`` is set (or
``LLM_PROVIDER=openai``), the transcript scoring and detail passes in
``main.get_viral_clips`` go here instead of Gemini, so a self-hosted install
can run the whole pipeline without a Google key.

What stays on Gemini, because it needs a model that can look at frames or a
video file: the layout picker (``layout_picker.py``), the on-screen content
detector (``screencast_layout.py``) and the silent-video path
(``main.get_visual_clips``). Without a Gemini key those degrade the way they
already did: the first two return "none", the third fails the job with a clear
message. Nothing in this module is imported by them.

Structured output: the prompts already spell out the exact JSON shape, so a
plain ``json_object`` mode is enough for most models. The request first asks
for ``json_schema`` (Ollama, vLLM, llama.cpp and LM Studio enforce it); a
server that rejects that field gets the same request again with
``json_object``, then with no ``response_format`` at all. Whatever comes back
is validated with the same pydantic model Gemini's ``response_schema`` uses,
so ``main.py`` sees one shape regardless of provider.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional, Tuple, Type

import httpx
from pydantic import BaseModel

DEFAULT_MODEL = "llama3.1:8b"
DEFAULT_TIMEOUT = 600.0  # local models on CPU are slow; a scoring batch can take minutes


def provider() -> str:
    """``"openai"`` when a compatible endpoint is configured, else ``"gemini"``."""
    explicit = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("openai", "ollama", "local", "openai-compatible"):
        return "openai"
    if explicit == "gemini":
        return "gemini"
    return "openai" if base_url() else "gemini"


def base_url() -> str:
    return (os.environ.get("LLM_BASE_URL") or "").strip().rstrip("/")


def model_name() -> str:
    return (os.environ.get("LLM_MODEL") or "").strip() or DEFAULT_MODEL


def active() -> bool:
    """True when the moment picker should call the OpenAI-compatible server."""
    return provider() == "openai" and bool(base_url())


def describe() -> Optional[dict]:
    """What ``/api/config`` tells the dashboard, or ``None`` when inactive."""
    if not active():
        return None
    return {"provider": "openai", "model": model_name(), "baseUrl": base_url()}


def _timeout() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        return DEFAULT_TIMEOUT


def _headers(api_key: Optional[str] = None) -> dict:
    # Ollama ignores the key but the OpenAI client convention (and vLLM with
    # --api-key) wants the header present; "ollama" is the documented placeholder.
    key = (api_key or os.environ.get("LLM_API_KEY") or "ollama").strip() or "ollama"
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _client(timeout: Optional[float] = None, **kwargs) -> httpx.Client:
    """Factory so tests can swap in ``httpx.MockTransport``."""
    return httpx.Client(timeout=timeout or _timeout(), **kwargs)


def _response_formats(schema: Type[BaseModel]):
    name = getattr(schema, "__name__", "response").lower()
    yield {"type": "json_schema",
           "json_schema": {"name": name, "schema": schema.model_json_schema()}}
    yield {"type": "json_object"}
    yield None


def _is_format_rejection(resp: httpx.Response) -> bool:
    """Um 400/422 a um pedido COM `response_format` passa ao formato seguinte.

    Ate 24-set-2026 so contava se o corpo falasse em "format". Com a cascata
    ampliada (ADR-011) cada provedor recusa com palavras proprias -- o
    Cloudflare fala em "JSON Mode", o Z.ai devolve um codigo com mensagem em
    chines --, e ai o provedor inteiro falhava em vez de tentar o formato mais
    simples. Se o motivo era outro (contexto estourado, parametro invalido), a
    ultima volta vai sem `response_format` e devolve o erro de verdade.
    """
    return resp.status_code in (400, 422)


# O raciocinio que alguns modelos escrevem ANTES da resposta (Qwen, GLM,
# Nemotron em modo de pensar). O JSON vem depois; e dentro do raciocinio pode
# haver chaves soltas, que confundiriam quem procura o primeiro "{".
_RACIOCINIO = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _sem_raciocinio(texto: str) -> str:
    return _RACIOCINIO.sub("", texto)


def generate_json(prompt: str, schema: Type[BaseModel], model: Optional[str] = None,
                  base_url_override: Optional[str] = None,
                  api_key: Optional[str] = None,
                  timeout: Optional[float] = None,
                  extra_body: Optional[dict] = None,
                  ) -> Tuple[dict, Optional[dict]]:
    """One chat completion that must come back as JSON matching ``schema``.

    Returns ``(parsed_dict, cost_analysis)`` in the exact shape
    ``main._run_gemini_stage`` returns, so the caller does not branch on the
    provider. Raises on HTTP errors, empty bodies and schema violations; the
    retry policy lives in the caller, same as for Gemini.

    ``base_url_override`` e ``api_key`` existem para a cascata
    (``llm_cascade``), que precisa falar com um provedor por chamada em vez do
    unico endpoint global de ``LLM_BASE_URL``. Sem eles o comportamento e o
    de antes: le o env. ``timeout`` tambem: os 600 s do ``LLM_TIMEOUT`` sao
    para modelo local em CPU, e um provedor na nuvem que trava nao pode
    prender o job dez minutos com outros na fila (``llm_cascade.timeout_para``).
    ``extra_body`` entra no corpo de cada tentativa (``Provider.extra``: o
    ``max_tokens`` de quem corta a resposta curta demais sem ele).
    """
    import gemini_worker  # local import: keeps this module free of the google SDK

    base = (base_url_override or base_url() or "").rstrip("/")
    if not base:
        raise RuntimeError("Nenhum endpoint compativel com OpenAI configurado")
    url = f"{base}/chat/completions"
    model = model or model_name()
    messages = [
        {"role": "system", "content": "You answer with a single JSON object and nothing else."},
        {"role": "user", "content": prompt},
    ]
    last_rejection: Optional[str] = None
    with _client(timeout=timeout) as client:
        for fmt in _response_formats(schema):
            body = {"model": model, "messages": messages, "temperature": 0.2, "stream": False,
                    **(extra_body or {})}
            if fmt is not None:
                body["response_format"] = fmt
            resp = client.post(url, json=body, headers=_headers(api_key))
            if fmt is not None and _is_format_rejection(resp):
                # The server does not know this response_format flavour; the
                # next loop iteration asks for a looser one.
                last_rejection = resp.text[:200]
                continue
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"LLM server {resp.status_code} from {url}: {resp.text[:300]}")
            data = resp.json()
            break
        else:
            raise RuntimeError(
                f"LLM server rejected every response_format variant: {last_rejection}")

    choices = data.get("choices") or []
    text = ""
    if choices:
        msg = choices[0].get("message") or {}
        text = msg.get("content") or ""
        if isinstance(text, list):  # some servers return content parts
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    parsed = gemini_worker._parse_json_response_text(_sem_raciocinio(text))
    # Validate against the same schema Gemini enforces server-side, so a
    # local model that drops a field fails here with a readable error
    # (retried by the caller) instead of deep inside the clip pipeline.
    validated = schema.model_validate(parsed).model_dump()

    usage = data.get("usage") or {}
    cost = {
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "thinking_tokens": 0,
        "input_cost": 0.0,
        "output_cost": 0.0,
        "total_cost": 0.0,
        "model": model,
        "price_estimated": False,
        "local": True,
    }
    return validated, cost
