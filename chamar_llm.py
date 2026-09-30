"""Uma tentativa num provedor da cascata de texto, fora do `main.py`.

O `llm_cascade` decide ordem e orcamento e nao fala com ninguem: quem fala e a
funcao `call` que o chamador passa. O `main.py` tem a dele, mas so importa com
torch; esta e a dos subprocessos leves -- a criacao de video (7.7) e a traducao
do texto do post (7.10). Era o `criar_video._chamar_provedor`; saiu de la
quando o segundo chamador apareceu, para que os dois nao divirjam.
"""
from __future__ import annotations


def chamar_provedor(prompt, schema, provider):
    """Uma tentativa num provedor da cascata (o mesmo desenho do
    `main._run_gemini_stage`, sem o resto do `main.py`)."""
    import llm_backend
    import llm_cascade
    if provider.base_url is not None:
        return llm_backend.generate_json(
            prompt, schema, model=provider.model, base_url_override=provider.base_url,
            api_key=provider.api_key(), timeout=llm_cascade.timeout_para(provider),
            extra_body=dict(provider.extra) or None)
    import gemini_worker
    from google import genai
    from google.genai import types as genai_types
    cliente = genai.Client(api_key=provider.api_key())
    resposta = cliente.models.generate_content(
        model=provider.model, contents=prompt,
        config=genai_types.GenerateContentConfig(response_mime_type="application/json",
                                                 response_schema=schema))
    gemini_worker.raise_if_blocked(resposta)
    objeto = getattr(resposta, "parsed", None)
    if objeto is not None:
        dados = objeto.model_dump() if hasattr(objeto, "model_dump") else objeto
    else:
        dados = gemini_worker._parse_json_response_text(gemini_worker._get_response_text(resposta))
    return dados, gemini_worker._calculate_cost_analysis(resposta, provider.model)
