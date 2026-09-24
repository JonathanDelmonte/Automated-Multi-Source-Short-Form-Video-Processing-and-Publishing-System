"""Cascata de provedores de LLM gratuitos para o detector de momentos.

Por que existe (ver docs/DECISOES.md, ADR-004 e ADR-005): nenhum free tier
aguenta o caso de uso alvo sozinho. O do Groq tem teto de 100.000 tokens/dia,
e uma live de 4h da Twitch, estimada em ~75.000 tokens com as janelas de 20%
de sobreposicao, consome de 60% a 75% desse orcamento num video so. O limite
de 1.000 requisicoes/dia nunca chega a ser tocado: quem morde e o token.

Duas consequencias, e sao as duas regras deste modulo:

1. **A ordem depende da duracao falada da fonte, nao e fixa.** Ordem fixa
   gastaria o recurso mais escasso no trabalho mais pesado. Fonte curta vai
   primeiro ao Groq, onde ~320 tok/s encurta o job e o custo em tokens e
   baixo; fonte longa vai primeiro ao Gemini Flash, pelo contexto de 1M e
   pelo orcamento diario maior.
2. **Checa o orcamento antes de chamar, nao depois de levar 429.** Um 429
   gasta uma requisicao e uma ida na rede para descobrir o que um contador
   local ja sabia.

O estado do orcamento vive **em disco**, nao em memoria, porque o `main.py`
roda como subprocesso novo a cada job (ver docs/MAPA-DOS-ESTAGIOS.md): um
contador em memoria zeraria entre videos e o teto diario nunca seria
respeitado. Fica em `output/.llm_budget.json`, junto dos outros arquivos de
estado que o caminho self-host ja mantem ali.

O Gemini **nao** e chamado por HTTP aqui. Ele entra na cascata como um
provedor cujo `call` e um callable que o chamador injeta, porque o caminho do
SDK que ja existe no `main.py` carrega duas coisas que nao da para reproduzir
por HTTP generico: `response_schema` server-side e o `GeminiBlockedError` que
o `_run_stage_split` usa para bissectar batch bloqueado por
PROHIBITED_CONTENT.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# Provedores
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Provider:
    """Um provedor da cascata.

    `base_url` None marca o Gemini, cuja chamada e injetada pelo chamador.
    Os tetos sao os do free tier e existem para o `available()` local; nao
    sao contrato, mudam sem aviso, e por isso cada um e sobrescrevivel por
    variavel de ambiente (`LLM_<ID>_TPD` e afins, com `-` virando `_`).

    Um id por (provedor, MODELO), e nao por provedor: o Groq conta a cota de
    cada modelo em separado, entao `groq` e `groq-qwen` sao dois baldes de
    8.000 tokens/minuto com a mesma chave (24-set-2026).
    """
    id: str
    label: str
    base_url: Optional[str]
    model: str
    key_env: str
    max_context: int
    tokens_per_day: Optional[int] = None
    calls_per_day: Optional[int] = None
    calls_per_minute: Optional[int] = None
    trains_on_data: bool = False      # free tier que usa o conteudo para treino
    model_env: str = ""               # a variavel que troca o modelo, para o aviso
    # Campos a mais no corpo do pedido, como pares (chave, valor) -- tupla e
    # nao dict porque o dataclass e congelado (e hashable). Hoje so o
    # `max_tokens` de quem corta a resposta curta demais sem ele.
    extra: tuple = ()

    def api_key(self) -> str:
        return (os.environ.get(self.key_env) or "").strip()

    def configured(self) -> bool:
        """Ollama nao pede chave, mas pede endereco; o Cloudflare pede chave E
        conta; os demais pedem chave."""
        if self.id == "ollama":
            return bool(_ollama_base())
        if self.id == "cloudflare":
            return bool(self.api_key()) and bool(_cloudflare_conta())
        return bool(self.api_key())


def _ollama_base() -> str:
    """Endereco do Ollama, ou vazio quando nao foi configurado.

    **Sem default para localhost, de proposito.** Adivinhar
    `http://localhost:11434/v1` colocaria o Ollama em toda cascata mesmo sem
    nada escutando ali, e cada job gastaria uma tentativa de conexao para
    descobrir isso. Pior: o plano chama o Ollama de "rede de seguranca que
    nunca falha", e isso so e verdade se ele estiver de fato rodando -- quem
    sabe disso e quem instalou. Entao e opt-in: `OLLAMA_BASE_URL`, tipicamente
    `http://localhost:11434/v1`.
    """
    return (os.environ.get("OLLAMA_BASE_URL") or "").strip().rstrip("/")


def _cloudflare_conta() -> str:
    """O id da conta do Cloudflare: o endereco do Workers AI e POR CONTA."""
    return (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()


def _modelo(env: str, padrao: str) -> str:
    return (os.environ.get(env) or "").strip() or padrao


# Limites divulgados em setembro de 2026. O Plano Tecnico manda reconfirmar
# antes de codar porque isso muda toda hora, e a auditoria ja encontrou uma
# tabela incompleta (o teto de tokens/dia do Groq estava ausente). A fonte de
# cada numero esta no ADR-011.
#
# So entra na cascata quem tem chave (ou endereco): cadastrar um provedor aqui
# nao custa nada a quem nao o usa.
_CATALOG = (
    Provider(
        id="groq", label="Groq", base_url="https://api.groq.com/openai/v1",
        # `llama-3.3-70b-versatile` foi aposentado pelo Groq em 16-ago-2026
        # (registro de modelos do LiteLLM, `deprecation_date`), e dali em
        # diante TODO job batia nele, levava 404 `model_not_found` e caia no
        # Gemini gratis -- mais lento e que treina com o conteudo. Visto no
        # log do autor em 22-set-2026, tres vezes por job. O `gpt-oss-120b` e
        # o modelo grande vivo do Groq, com 131k de contexto e saida em
        # json_schema. Teto de 200k tokens/dia: o publicado para ele em agosto
        # de 2026 (era 100k, herdado do modelo antigo).
        model=_modelo("GROQ_MODEL", "openai/gpt-oss-120b"), model_env="GROQ_MODEL",
        key_env="GROQ_API_KEY", max_context=128_000,
        tokens_per_day=200_000, calls_per_day=1_000, calls_per_minute=30,
    ),
    Provider(
        id="gemini", label="Gemini Flash", base_url=None,
        model=_modelo("GEMINI_MODEL", "gemini-3.1-flash-lite"), model_env="GEMINI_MODEL",
        key_env="GEMINI_API_KEY", max_context=1_000_000,
        # O free tier do Google nao publica RPD estavel; medicoes independentes
        # acharam de 20 a 1.500. Sem teto local: quem manda e o 429 dele.
        trains_on_data=True,
    ),
    # --- modelos a mais nas chaves que ja existem (24-set-2026) ------------
    # O Groq conta a cota POR MODELO: quando as duas chamadas de pontuacao
    # esgotam os 8.000 tokens/min do gpt-oss-120b, o Qwen tem os dele
    # intactos. Mesma chave, nada a configurar. Groq aposentou o qwen3-32b em
    # 17-jul-2026; o 3.8 e o sucessor, e ali nasce sem raciocinio
    # (`reasoning_effort` padrao "none").
    Provider(
        id="groq-qwen", label="Qwen (Groq)", base_url="https://api.groq.com/openai/v1",
        model=_modelo("GROQ_QWEN_MODEL", "qwen/qwen3.8-27b"), model_env="GROQ_QWEN_MODEL",
        key_env="GROQ_API_KEY", max_context=128_000,
        tokens_per_day=200_000, calls_per_day=1_000, calls_per_minute=30,
    ),
    # Outro modelo, outra fila no Google: o 503 "high demand" do log de 165 s
    # era do flash-lite 3.1. O 3.5 e o sucessor dele (o 3.1 sai em maio de
    # 2027) e tem a propria cota do free tier.
    Provider(
        id="gemini-lite", label="Gemini 3.5 Flash-Lite", base_url=None,
        model=_modelo("GEMINI_LITE_MODEL", "gemini-3.5-flash-lite"),
        model_env="GEMINI_LITE_MODEL",
        key_env="GEMINI_API_KEY", max_context=1_000_000, trains_on_data=True,
    ),
    # --- provedores gratuitos com cadastro, sem cartao ----------------------
    # NVIDIA: gratis com o NVIDIA Developer Program; 40/min e 10.000/dia por
    # modelo. O endpoint gratuito registra o uso "para melhorar produtos
    # NVIDIA", entao conta como quem treina com o conteudo.
    Provider(
        id="nvidia", label="Nemotron (NVIDIA)",
        base_url="https://integrate.api.nvidia.com/v1",
        model=_modelo("NVIDIA_MODEL", "nvidia/nemotron-3-super-120b-a12b"),
        model_env="NVIDIA_MODEL",
        key_env="NVIDIA_API_KEY", max_context=128_000,
        calls_per_day=10_000, calls_per_minute=40, trains_on_data=True,
        # O padrao de saida do NIM nao e documentado, e os exemplos dele
        # passam 1024: pouco para os detalhes de 6 cortes, ainda mais com o
        # raciocinio do Nemotron contando junto. JSON cortado no meio nao
        # parseia, e seriam tres tentativas iguais antes do proximo.
        extra=(("max_tokens", 8192),),
    ),
    # Mistral: modo gratuito por padrao, sem cartao (pede telefone); ~1
    # chamada/s. Treina com o conteudo a menos que se desligue no painel.
    Provider(
        id="mistral", label="Mistral", base_url="https://api.mistral.ai/v1",
        model=_modelo("MISTRAL_MODEL", "mistral-small-latest"), model_env="MISTRAL_MODEL",
        key_env="MISTRAL_API_KEY", max_context=128_000,
        calls_per_minute=60, trains_on_data=True,
    ),
    # Ollama Cloud: os modelos grandes da biblioteca do Ollama, hospedados;
    # gratis com limite por sessao (5 h) e por semana, sem numero publicado.
    # Chave PROPRIA: o `OLLAMA_API_KEY` e do Ollama local.
    Provider(
        id="ollama-cloud", label="Ollama Cloud", base_url="https://ollama.com/v1",
        model=_modelo("OLLAMA_CLOUD_MODEL", "gpt-oss:120b"), model_env="OLLAMA_CLOUD_MODEL",
        key_env="OLLAMA_CLOUD_API_KEY", max_context=128_000,
    ),
    # OpenRouter: o roteador `openrouter/free` sorteia um modelo gratuito que
    # aceite saida estruturada -- a lista de modelos gratis dele muda toda
    # semana, e um id fixo aqui apodreceria. 20/min, 50/dia sem credito
    # comprado (1.000/dia depois de US$ 10 uma vez: LLM_OPENROUTER_RPD=1000).
    Provider(
        id="openrouter", label="OpenRouter (gratis)",
        base_url="https://openrouter.ai/api/v1",
        model=_modelo("OPENROUTER_MODEL", "openrouter/free"), model_env="OPENROUTER_MODEL",
        key_env="OPENROUTER_API_KEY", max_context=128_000,
        calls_per_day=50, calls_per_minute=20, trains_on_data=True,
    ),
    # Cloudflare Workers AI: 10.000 "neurons"/dia gratis, divididos entre
    # todos os modelos -- algumas centenas de milhares de tokens. O endereco
    # leva o id da conta (CLOUDFLARE_ACCOUNT_ID). Nao treina com o conteudo.
    Provider(
        id="cloudflare", label="Cloudflare Workers AI", base_url=None,
        model=_modelo("CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-120b"),
        model_env="CLOUDFLARE_MODEL",
        key_env="CLOUDFLARE_API_TOKEN", max_context=128_000,
        # O Workers AI corta a saida em 256 tokens se o pedido nao disser.
        extra=(("max_tokens", 8192),),
    ),
    # Z.ai (Zhipu): GLM-4.7-Flash e gratis e permanente, uma chamada por vez.
    # Servidor na China; sem politica clara de treino, entao conta como quem
    # treina.
    Provider(
        id="zai", label="GLM (Z.ai)", base_url="https://api.z.ai/api/paas/v4",
        model=_modelo("ZAI_MODEL", "glm-4.7-flash"), model_env="ZAI_MODEL",
        key_env="ZAI_API_KEY", max_context=128_000, trains_on_data=True,
    ),
    # O gpt-oss-20b e o terceiro balde do Groq: menor, e por isso quase no fim.
    Provider(
        id="groq-20b", label="gpt-oss-20b (Groq)", base_url="https://api.groq.com/openai/v1",
        model=_modelo("GROQ_20B_MODEL", "openai/gpt-oss-20b"), model_env="GROQ_20B_MODEL",
        key_env="GROQ_API_KEY", max_context=128_000,
        tokens_per_day=200_000, calls_per_day=1_000, calls_per_minute=30,
    ),
    # --- pago, e local -------------------------------------------------------
    # Cerebras DEIXOU DE SER GRATIS: desde 21-jul-2026 conta nova ganha US$ 5
    # de credito unico, com cartao, que vence em 30 dias (as antigas migraram
    # em 17-ago-2026). E o `llama-3.3-70b`, que era o padrao aqui, foi
    # aposentado. Fica na lista para quem pagar; os tetos sao os do teste.
    Provider(
        id="cerebras", label="Cerebras (pago)", base_url="https://api.cerebras.ai/v1",
        model=_modelo("CEREBRAS_MODEL", "gpt-oss-120b"), model_env="CEREBRAS_MODEL",
        key_env="CEREBRAS_API_KEY", max_context=128_000,
        tokens_per_day=1_000_000, calls_per_minute=5,
    ),
    Provider(
        id="ollama", label="Ollama local", base_url=None,
        model=_modelo("OLLAMA_MODEL", "llama3.1:8b"), model_env="OLLAMA_MODEL",
        key_env="OLLAMA_API_KEY", max_context=8_192,
    ),
)

_BY_ID = {p.id: p for p in _CATALOG}

#: A ordem de cada caso (ADR-005 e ADR-011). Os dois primeiros de cada lista
#: sao os de sempre, e so eles atendem enquanto funcionam: tudo o que veio
#: depois so e chamado quando os dois falharem naquela chamada.
ORDEM_CURTA = ("groq", "gemini", "groq-qwen", "gemini-lite", "nvidia", "mistral",
               "ollama-cloud", "openrouter", "cloudflare", "zai", "groq-20b",
               "cerebras", "ollama")
ORDEM_LONGA = ("gemini", "gemini-lite", "groq", "groq-qwen", "nvidia", "mistral",
               "ollama-cloud", "openrouter", "cloudflare", "zai", "groq-20b",
               "cerebras", "ollama")


#: Quanto esperar a resposta de um provedor NA NUVEM antes de passar ao
#: proximo. O `LLM_TIMEOUT` de 600 s e do modelo local em CPU; herdado aqui,
#: um endpoint gratuito que aceita a conexao e nao responde prenderia o job
#: dez minutos com outros provedores prontos. O Groq responde em segundos e
#: um modelo que raciocina antes (Nemotron) em menos de um minuto.
TIMEOUT_NUVEM_S = 180.0


def timeout_para(p: Provider) -> Optional[float]:
    """O tempo maximo de uma chamada a `p`; None e o padrao do `llm_backend`."""
    if p.id == "ollama":
        return None
    raw = (os.environ.get("LLM_TIMEOUT_NUVEM") or "").strip()
    try:
        return float(raw) if raw else TIMEOUT_NUVEM_S
    except ValueError:
        return TIMEOUT_NUVEM_S


def _env_id(p: Provider) -> str:
    """O id do provedor como pedaco de nome de variavel: `groq-qwen` -> `GROQ_QWEN`."""
    return p.id.upper().replace("-", "_")


def _base_url(p: Provider) -> Optional[str]:
    if p.id == "ollama":
        return _ollama_base()
    if p.id == "cloudflare":
        conta = _cloudflare_conta()
        return (f"https://api.cloudflare.com/client/v4/accounts/{conta}/ai/v1"
                if conta else None)
    return p.base_url


def _with_env_overrides(p: Provider) -> Provider:
    """Tetos sobrescritos por env, para quando o provedor mudar os limites."""
    def _int(name: str, cur: Optional[int]) -> Optional[int]:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return cur
        try:
            v = int(raw)
        except ValueError:
            return cur
        return None if v <= 0 else v      # 0 ou negativo desliga o teto

    up = _env_id(p)
    return Provider(
        id=p.id, label=p.label, base_url=_base_url(p), model=p.model, key_env=p.key_env,
        max_context=_int(f"LLM_{up}_CONTEXT", p.max_context) or p.max_context,
        tokens_per_day=_int(f"LLM_{up}_TPD", p.tokens_per_day),
        calls_per_day=_int(f"LLM_{up}_RPD", p.calls_per_day),
        calls_per_minute=_int(f"LLM_{up}_RPM", p.calls_per_minute),
        trains_on_data=p.trains_on_data, model_env=p.model_env, extra=p.extra,
    )


# --------------------------------------------------------------------------- #
# Ordem: depende da duracao falada da fonte (ADR-005)
# --------------------------------------------------------------------------- #

LONG_SOURCE_SECONDS = 40 * 60     # ~40 min de fala; sobrescrevivel

def _long_threshold() -> int:
    raw = (os.environ.get("LLM_LONG_SOURCE_SECONDS") or "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return LONG_SOURCE_SECONDS


def cascade(duration_seconds: Optional[float] = None) -> list[Provider]:
    """Provedores configurados, na ordem em que devem ser tentados.

    `LLM_CASCADE` sobrescreve a ordem inteira (lista separada por virgula de
    ids). Sem ela, a ordem vem da duracao: fonte longa comeca no Gemini pelo
    contexto de 1M e pelo orcamento maior; fonte curta comeca no Groq, que e
    rapido e cujo teto de tokens aguenta bem video curto. Depois dos dois vem
    todo provedor gratuito que tiver chave (ADR-011). O Ollama e sempre o
    ultimo: nao tem limite e custa GPU, mas entra so quando
    `OLLAMA_BASE_URL` diz onde ele esta.
    """
    explicit = [s.strip().lower() for s in (os.environ.get("LLM_CASCADE") or "").split(",") if s.strip()]
    if explicit:
        order = [_BY_ID[i] for i in explicit if i in _BY_ID]
    else:
        is_long = duration_seconds is not None and duration_seconds >= _long_threshold()
        order = [_BY_ID[i] for i in (ORDEM_LONGA if is_long else ORDEM_CURTA)]
    return [q for q in (_with_env_overrides(p) for p in order) if q.configured()]


# --------------------------------------------------------------------------- #
# Orcamento diario, em disco
# --------------------------------------------------------------------------- #

def _budget_path() -> str:
    d = (os.environ.get("OUTPUT_DIR") or "output").strip() or "output"
    return os.path.join(d, ".llm_budget.json")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        with open(_budget_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"day": _today(), "providers": {}}
    if data.get("day") != _today():
        # Vira o dia em UTC, que e quando os free tiers zeram.
        return {"day": _today(), "providers": {}}
    data.setdefault("providers", {})
    return data


def _save(data: dict) -> None:
    path = _budget_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)          # troca atomica: dois jobs em paralelo
    except OSError:
        pass                            # orcamento e melhor-esforco, nunca quebra o job


def usage(provider_id: str) -> dict:
    return _load()["providers"].get(provider_id, {"calls": 0, "tokens": 0, "recent": []})


def record(provider_id: str, tokens: int = 0, calls: int = 1) -> None:
    """Soma uso ao orcamento do dia. Chamado depois de cada resposta."""
    data = _load()
    slot = data["providers"].setdefault(provider_id, {"calls": 0, "tokens": 0, "recent": []})
    slot["calls"] = int(slot.get("calls", 0)) + int(calls)
    slot["tokens"] = int(slot.get("tokens", 0)) + max(0, int(tokens))
    now = time.time()
    recent = [t for t in slot.get("recent", []) if now - t < 60]
    recent.append(now)
    slot["recent"] = recent[-120:]
    _save(data)


def estimate_tokens(prompt: str) -> int:
    """Estimativa grosseira de tokens do prompt.

    ~3,5 caracteres por token: o portugues tokeniza pior que o ingles, e aqui
    errar para cima e o lado seguro -- subestimar faz o `available()` liberar
    uma chamada que estoura o teto e volta 429.
    """
    return max(1, int(len(prompt) / 3.5))


def available(p: Provider, need_tokens: int = 0) -> tuple[bool, str]:
    """(pode chamar, motivo). Consulta o contador local, sem ir na rede."""
    u = usage(p.id)
    if p.calls_per_day is not None and u.get("calls", 0) >= p.calls_per_day:
        return False, f"teto de {p.calls_per_day} chamadas/dia atingido"
    if p.tokens_per_day is not None:
        spent = u.get("tokens", 0)
        if spent + need_tokens > p.tokens_per_day:
            return False, (f"teto de {p.tokens_per_day} tokens/dia: "
                           f"{spent} gastos, a chamada pede ~{need_tokens}")
    if p.calls_per_minute is not None:
        now = time.time()
        in_window = len([t for t in u.get("recent", []) if now - t < 60])
        if in_window >= p.calls_per_minute:
            return False, f"teto de {p.calls_per_minute} chamadas/min atingido"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Execucao
# --------------------------------------------------------------------------- #

class AllProvidersFailed(RuntimeError):
    """Nenhum provedor da cascata aceitou a chamada."""


#: Provedores cujo modelo o PROPRIO provedor disse nao existir, neste
#: processo. O `main.py` e um processo por job, entao isto vale por job.
#:
#: Existe por causa do 22-set-2026: com o modelo do Groq aposentado, cada
#: chamada do job tentava o Groq de novo, levava o mesmo 404 e escrevia a
#: mesma linha de erro -- tres vezes num video de 10 min, e uma ida a rede
#: a mais em cada uma. "O modelo nao existe" nao melhora em 5 segundos.
_MODELO_INEXISTENTE: dict = {}

#: Chaves que o provedor RECUSOU (401), por nome de variavel, neste processo.
#: Por variavel e nao por provedor: `groq`, `groq-qwen` e `groq-20b` usam a
#: mesma `GROQ_API_KEY`, e uma chave colada errada levaria tres 401 por
#: chamada -- um por modelo -- para dizer a mesma coisa.
_CHAVE_RECUSADA: dict = {}


def chave_recusada(erro) -> bool:
    """O provedor disse que a CHAVE nao vale (e nao que esta ocupado)?

    O 401 do caminho compativel com OpenAI, e o "API key not valid" do Gemini
    (que volta como 400). Um 403 fica de fora de proposito: ele tambem e
    "regiao nao atendida" ou "modelo sem acesso", e isso nao e a chave."""
    texto = str(erro).lower()
    if "api key not valid" in texto or "api_key_invalid" in texto:
        return True
    # O status do caminho compativel com OpenAI (`llm_backend`): um 401 ali e
    # autenticacao, diga o corpo o que disser ("User not found.", no OpenRouter).
    if re.search(r"llm server 401\b", texto):
        return True
    return bool(re.search(r"\b401\b", texto)) and any(
        t in texto for t in ("unauthorized", "invalid", "api key", "api_key",
                             "authentication", "incorrect"))


def modelo_inexistente(erro) -> bool:
    """O erro e o provedor dizendo que o MODELO pedido nao existe (ou que
    esta chave nao o alcanca)? Os dois casos pedem a mesma coisa: trocar o
    modelo no `.env`, e nao tentar de novo. Precisa do 404 junto para que um
    erro transitorio que so mencione "model" nao desligue um provedor bom."""
    texto = str(erro).lower()
    if "404" not in texto:
        return False
    return ("model_not_found" in texto or "does not exist" in texto
            or ("not found" in texto and "model" in texto))


# --------------------------------------------------------------------------- #
# Quanto esperar antes de repetir o mesmo provedor
# --------------------------------------------------------------------------- #

#: Folga sobre a espera que o servidor pede: o relogio dele e o daqui nao batem
#: ao milissegundo, e chegar 50 ms antes custa a tentativa inteira.
FOLGA_DA_DICA_S = 0.5

#: Quanto vale esperar pelo MESMO provedor quando outro pode responder agora.
#: No job de 213 s (23-set-2026) o Groq pediu 14,4 s, isso cabia na paciencia
#: de 15 s, e o job esperou -- quando o Gemini responde a mesma pergunta em
#: ~6 s. Esperar so compensa quando nao ha para onde ir.
ESPERA_MAXIMA_COM_ALTERNATIVA_S = 3.0

# Ha outro provedor pronto para atender se o desta chamada desistir? `run()`
# responde antes de cada chamada; fora da cascata (um provedor so) e False.
_HA_ALTERNATIVA: contextvars.ContextVar = contextvars.ContextVar(
    "llm_ha_alternativa", default=False)

# "Please try again in 20.4s" (Groq, em duracao do Go: 1m26.4s, 780ms, 2h3m4s)
# e "Please retry in 44.52s" (Gemini).
_DICA = re.compile(r"(?:try again|retry) in ((?:\d+(?:\.\d+)?(?:ms|us|µs|ns|h|m|s))+)",
                   re.IGNORECASE)
# O RetryInfo do Gemini: 'retryDelay': '44s'.
_RETRY_DELAY = re.compile(r"retryDelay\W+(\d+(?:\.\d+)?)s")
_UNIDADE_S = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 1e-3, "us": 1e-6,
              "µs": 1e-6, "ns": 1e-9}


def espera_sugerida(mensagem) -> Optional[float]:
    """Os segundos que o PROPRIO servidor mandou esperar, lidos do erro.

    None quando o erro nao diz: ai quem decide e a regra sem dica.
    """
    texto = str(mensagem)
    m = _DICA.search(texto)
    if m:
        partes = re.findall(r"(\d+(?:\.\d+)?)(ms|us|µs|ns|h|m|s)", m.group(1),
                            re.IGNORECASE)
        return sum(float(n) * _UNIDADE_S[u.lower()] for n, u in partes)
    m = _RETRY_DELAY.search(texto)
    if m:
        return float(m.group(1))
    return None


def espera_sem_dica(tentativa: int) -> float:
    """A regra de sempre: 5 s antes da 2a tentativa, 10 s antes da 3a."""
    return 5.0 * 2 ** (tentativa - 1)


#: O provedor esta OCUPADO (ou fora do ar), e nao errou a resposta. Repetir
#: um desses daqui a 5 s e apostar que a fila dele andou; ir ao proximo e ter
#: a resposta agora.
_CAPACIDADE = ("unavailable", "overloaded", "high demand", "resource_exhausted",
               "rate limit", "connecterror", "connecttimeout", "readtimeout",
               "remoteprotocolerror", "deadline", "timed out")
# Os codigos so como palavra inteira: "Requested 4535" ou um "1500" dentro de
# um erro de validacao nao sao um 500.
_CODIGO_DE_CAPACIDADE = re.compile(r"\b(?:429|500|502|503|504)\b")


def erro_de_capacidade(mensagem) -> bool:
    """O erro e de CAPACIDADE (fila cheia, fora do ar, rede)?

    O resto do que o `main.py` repete -- corpo vazio, JSON que nao parseia,
    campo faltando -- e o modelo errando a resposta, e ai repetir o MESMO
    provedor e o que recupera (o corpo vazio do Gemini voltou certo na segunda
    tentativa em todos os casos vistos em producao, 22-jul-2026)."""
    texto = str(mensagem).lower()
    return (any(t in texto for t in _CAPACIDADE)
            or bool(_CODIGO_DE_CAPACIDADE.search(texto)))


def espera_antes_de_repetir(mensagem, tentativa: int, ja_esperado: float,
                            tentativas: int) -> Optional[float]:
    """Quanto esperar antes de repetir o MESMO provedor, ou None para desistir
    dele agora -- e ai a cascata passa ao proximo.

    Existe por causa do 23-set-2026: o Groq devolveu 429 de tokens por minuto
    na terceira chamada de um video de 10 min (as duas primeiras ja tinham
    gastado 6.586 dos 8.000 do minuto), e a regra sem dica esperou 5 s, depois
    10 s, levou o mesmo 429 as tres vezes e so entao passou ao Gemini: 15 s
    jogados fora -- e que se repetiriam em todo video desse tamanho.

    Sem outro provedor pronto, a paciencia e a MESMA de antes -- a soma das
    esperas sem dica --, e a dica so muda como ela e gasta: se o que o servidor
    pede cabe no que resta, espera exatamente isso; se nao cabe, desiste ja, em
    vez de esperar para levar o mesmo "nao" que a dica anunciava.

    Com outro provedor pronto (`run()` sabe e avisa), a paciencia cai para
    `ESPERA_MAXIMA_COM_ALTERNATIVA_S`: esperar 14 s por um provedor enquanto
    outro responde em 6 s nao e fidelidade a ordem da cascata, e tempo perdido.
    Nos dois casos nunca espera mais do que a regra antiga esperaria.

    **Sem dica, com outro pronto, erro de capacidade passa ao proximo ja**
    (24-set-2026). No log de 165 s o Gemini respondeu "503 ... high demand",
    o job esperou 5 s, e a deteccao levou 21,6 s em vez de ~12. Um erro que o
    modelo cometeu (corpo vazio, JSON quebrado) continua com a regra de
    sempre: ali repetir o mesmo e o que funciona.
    """
    dica = espera_sugerida(mensagem)
    if dica is None:
        espera = espera_sem_dica(tentativa)
        if (_HA_ALTERNATIVA.get() and erro_de_capacidade(mensagem)
                and ja_esperado + espera > ESPERA_MAXIMA_COM_ALTERNATIVA_S):
            return None
        return espera
    paciencia = sum(espera_sem_dica(k) for k in range(1, tentativas))
    if _HA_ALTERNATIVA.get():
        paciencia = min(paciencia, ESPERA_MAXIMA_COM_ALTERNATIVA_S)
    espera = dica + FOLGA_DA_DICA_S
    if ja_esperado + espera > paciencia:
        return None
    return espera


def _pode_atender(p: Provider, need: int) -> bool:
    """O mesmo filtro que `run()` aplica antes de chamar, sem escrever no log."""
    return (p.id not in _MODELO_INEXISTENTE and p.key_env not in _CHAVE_RECUSADA
            and available(p, need)[0] and need <= p.max_context)


def run(prompt: str, schema, *, call: Callable[[str, object, Provider], tuple],
        duration_seconds: Optional[float] = None,
        log: Callable[[str], None] = print) -> tuple[dict, dict]:
    """Tenta os provedores em ordem e devolve `(parsed, cost)` do primeiro que responder.

    `call(prompt, schema, provider)` e injetado pelo chamador. Este modulo
    decide **ordem e orcamento** e nada mais: nao importa o SDK do Google nem
    cliente HTTP, e nao sabe a diferenca entre um provedor e outro alem do que
    esta no `Provider`. Quem sabe falar com cada um e o `main.py`, que ja
    tinha os dois caminhos.

    Um provedor e descartado por tres motivos, e os tres continuam a cascata:
    orcamento local esgotado (sem ida na rede), erro na chamada, ou resposta
    que nao valida no schema. O ultimo e o que justifica a cascata existir:
    modelo pequeno erra formato, e ai o proximo assume.
    """
    need = estimate_tokens(prompt)
    chain = cascade(duration_seconds)
    if not chain:
        raise AllProvidersFailed(
            "Nenhum provedor de LLM configurado. Defina ao menos uma chave gratuita "
            "(GROQ_API_KEY, GEMINI_API_KEY, NVIDIA_API_KEY, MISTRAL_API_KEY, "
            "OPENROUTER_API_KEY -- a lista inteira esta no .env.example) ou suba "
            "um Ollama local (OLLAMA_BASE_URL).")

    errors: list[str] = []
    for i, p in enumerate(chain):
        if p.id in _MODELO_INEXISTENTE:
            # Ja avisado na primeira vez, com o conserto; aqui so pula.
            errors.append(f"{p.id}: modelo {_MODELO_INEXISTENTE[p.id]} nao existe")
            continue
        if p.key_env in _CHAVE_RECUSADA:
            errors.append(f"{p.id}: {p.key_env} recusada")
            continue
        ok, why = available(p, need)
        if not ok:
            log(f"   ⏭️  {p.label}: {why}")
            errors.append(f"{p.id}: {why}")
            continue
        if need > p.max_context:
            log(f"   ⏭️  {p.label}: prompt de ~{need} tokens nao cabe em {p.max_context}")
            errors.append(f"{p.id}: contexto insuficiente")
            continue
        # Quem esta na chamada precisa saber se desistir custa o job ou so troca
        # de provedor: e o que decide quanto vale esperar por um 429.
        marca = _HA_ALTERNATIVA.set(
            any(_pode_atender(q, need) for q in chain[i + 1:]))
        try:
            parsed, cost = call(prompt, schema, p)
        except Exception as e:                      # noqa: BLE001 - a cascata existe para isso
            if chave_recusada(e):
                _CHAVE_RECUSADA[p.key_env] = p.label
                log(f"   ⚠️  {p.label}: a chave {p.key_env} foi recusada. Pulando "
                    f"quem usa essa chave no resto deste job -- confira o valor "
                    f"no .env.")
                errors.append(f"{p.id}: {p.key_env} recusada")
                continue
            if modelo_inexistente(e):
                _MODELO_INEXISTENTE[p.id] = p.model
                log(f"   ⚠️  {p.label}: o modelo `{p.model}` nao existe (ou esta "
                    f"chave nao tem acesso a ele). Pulando o {p.label} no resto "
                    f"deste job -- para volta-lo, ponha "
                    f"{p.model_env or _env_id(p) + '_MODEL'}=<modelo atual> no .env.")
                errors.append(f"{p.id}: modelo {p.model} nao existe")
                # Sem `record`: um 404 de modelo nao gasta cota nenhuma, e
                # somar tokens fantasmas encheria o teto diario de um
                # provedor que nem chegou a trabalhar.
                continue
            log(f"   ⚠️  {p.label} falhou ({type(e).__name__}: {e}); proximo provedor")
            errors.append(f"{p.id}: {type(e).__name__}: {e}")
            # Uma tentativa que falhou ainda consumiu cota no provedor.
            record(p.id, tokens=need, calls=1)
            continue
        finally:
            _HA_ALTERNATIVA.reset(marca)

        cost = dict(cost or {})
        spent = int(cost.get("input_tokens") or 0) + int(cost.get("output_tokens") or 0)
        record(p.id, tokens=spent or need, calls=1)
        cost["provider"] = p.id
        u = usage(p.id)
        if p.tokens_per_day:
            log(f"   🤖 {p.label}: {spent or need} tokens "
                f"({u['tokens']}/{p.tokens_per_day} hoje)")
        else:
            log(f"   🤖 {p.label}: {spent or need} tokens")
        return parsed, cost

    raise AllProvidersFailed("Cascata esgotada -- " + " | ".join(errors))


def batch_size_for(duration_seconds: Optional[float] = None) -> int:
    """Janelas de transcricao por chamada, pelo contexto de quem vai atender.

    O upstream fixava 8 para Gemini e 3 para "servidor compativel com OpenAI",
    o que era razoavel quando havia um provedor local so. Com a cascata, quem
    manda e o contexto do primeiro provedor da fila: 8 no Gemini (1M), 6 em
    Groq e Cerebras (128k), 3 no Ollama (8k, onde prompt truncado pontua lixo
    em silencio).
    """
    chain = cascade(duration_seconds)
    if not chain:
        return 3
    ctx = chain[0].max_context
    if ctx >= 1_000_000:
        return 8
    if ctx >= 100_000:
        return 6
    return 3


def has_text_provider() -> bool:
    """Ha algum provedor da cascata configurado para o estagio de transcricao?

    Usado pelo `app.py` para decidir se a requisicao precisa de chave do
    Gemini: uma cascata de Groq (ou Cerebras, ou Ollama) atende o detector
    sem chave do Google nenhuma.
    """
    return bool(cascade(None))


def describe(duration_seconds: Optional[float] = None) -> dict:
    """Estado da cascata, para log e para `/api/config`."""
    out = []
    for p in cascade(duration_seconds):
        u = usage(p.id)
        ok, why = available(p)
        out.append({"id": p.id, "label": p.label, "model": p.model,
                    "max_context": p.max_context, "ready": ok, "note": why,
                    "calls_today": u.get("calls", 0), "tokens_today": u.get("tokens", 0),
                    "tokens_per_day": p.tokens_per_day,
                    "trains_on_data": p.trains_on_data})
    return {"batch_size": batch_size_for(duration_seconds), "providers": out}
