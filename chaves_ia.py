"""As chaves de IA, coladas no site e guardadas no motor deste computador (25-set-2026).

O pedido do autor: um campo para cada IA gratuita nas Configuracoes, em
portugues, com o botao que abre a pagina onde se cria a chave -- "o mais facil
possivel", sem ninguem editar arquivo. Havia dois caminhos, e nenhum servia ao
amigo dele: o `.env` (um arquivo na pasta do projeto, ou `dados\\.env` do
ajudante) e a chave do Gemini guardada no NAVEGADOR, mandada a cada pedido pelo
`X-Gemini-Key` -- que so cobria o Gemini e sumia ao trocar de navegador.

**A chave mora no motor, e nao no navegador.** O site e so a tela; quem chama a
IA e o motor -- inclusive num job retomado depois de um reinicio, quando nao ha
navegador nenhum mandando cabecalho. Colada uma vez, vale para todo navegador
desta maquina e sobrevive a limpar os dados do site, a atualizar e a reinstalar
o ajudante (`dados\\` fica).

- **Um arquivo so**, `DATA_DIR/chaves.json`: fora do git e fora da imagem do
  Docker (os dois ignoram `data/`), e 0600 onde isso existe.
- **Entra no ambiente do processo** (`Chaves._aplicar`): a cascata, o
  `resolve_gemini` e o `/api/config` ja leem `os.environ`, e o `main.py` de cada
  job o herda (`env = os.environ.copy()`). Nada de enfiar a chave em vinte
  lugares.
- **A colada no site vence a do `.env`**: e o gesto mais recente e explicito.
  Tirar a colada devolve a do `.env`, se havia (`originais`).
- **Nunca sai inteira**: o estado diz se ha chave, de onde veio e os ultimos 4
  caracteres, e nenhum log a ve.
- **So as variaveis da lista** (`VARIAVEIS`): o site escreve no ambiente do
  PROCESSO, e um nome livre o deixaria trocar `PATH` ou `OUTPUT_DIR`.
- **Os erros saem como codigo**, e o painel escreve a frase: e ele que fala
  portugues com acento.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Optional

ARQUIVO = "chaves.json"

#: As chaves da cascata gratuita (llm_cascade, ADR-011). O Cerebras ficou de
#: fora porque deixou de ser gratis, e o Ollama local nao tem chave, tem
#: endereco -- os dois continuam valendo pelo `.env`. Um teste compara esta
#: lista com o catalogo da cascata e com a tela do painel.
VARIAVEIS = (
    "GEMINI_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "MISTRAL_API_KEY",
    "OLLAMA_CLOUD_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID", "ZAI_API_KEY",
)

# Sem espaco, quebra de linha nem aspas: a chave vai parar num cabecalho HTTP
# (`Authorization: Bearer ...`), e uma quebra de linha ali e cabecalho injetado.
_FORMATO = re.compile(r"[A-Za-z0-9._~+/=:-]+")
_MINIMO, _MAXIMO = 8, 400


class ChaveInvalida(ValueError):
    """`codigo`: desconhecida | curta | longa | caracteres | texto."""

    def __init__(self, codigo: str, variavel: Optional[str] = None):
        super().__init__(f"{variavel}: {codigo}")
        self.codigo = codigo
        self.variavel = variavel


def limpar(variavel: str, valor) -> str:
    """A chave como deve ser guardada, ou `ChaveInvalida`.

    Aceita os jeitos comuns de colar errado: espacos em volta, entre aspas, a
    linha inteira do `.env` (`GROQ_API_KEY=gsk_...`) ou com o `Bearer ` da
    documentacao na frente."""
    if variavel not in VARIAVEIS:
        raise ChaveInvalida("desconhecida", variavel)
    if not isinstance(valor, str):
        raise ChaveInvalida("texto", variavel)
    v = valor.strip()
    if v.startswith(f"{variavel}="):
        v = v[len(variavel) + 1:].strip()
    v = v.strip("\"'").strip()
    if v.lower().startswith("bearer "):
        v = v[7:].strip()
    if len(v) < _MINIMO:
        raise ChaveInvalida("curta", variavel)
    if len(v) > _MAXIMO:
        raise ChaveInvalida("longa", variavel)
    if not _FORMATO.fullmatch(v):
        raise ChaveInvalida("caracteres", variavel)
    return v


def final_de(valor: str) -> Optional[str]:
    """Os ultimos 4 caracteres, para a pessoa reconhecer qual chave e. So de
    chave comprida: numa curta, 4 caracteres seriam boa parte do segredo."""
    return valor[-4:] if len(valor) >= 16 else None


class Chaves:
    """As chaves de um motor: as coladas no site por cima das do ambiente com
    que o processo nasceu (o `.env`, ou o que o ajudante passou)."""

    def __init__(self, data_dir, environ: MutableMapping = os.environ):
        self.arquivo = Path(data_dir) / ARQUIVO
        self.environ = environ
        # O que o processo tinha ANTES do site: e para onde a variavel volta
        # quando a chave colada e removida.
        self.originais = {v: (environ.get(v) or "").strip() for v in VARIAVEIS}
        self.salvas = self._ler()
        self._aplicar()

    def _ler(self) -> dict:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            # Sem o conteudo no log: o arquivo e de segredos.
            print(f"⚠️ [chaves] {self.arquivo} ilegivel ({type(e).__name__}); "
                  f"seguindo com as chaves do .env.", flush=True)
            return {}
        if not isinstance(dados, dict):
            return {}
        saida = {}
        for v in VARIAVEIS:
            if not dados.get(v):
                continue
            try:
                saida[v] = limpar(v, dados[v])
            except ChaveInvalida:
                continue
        return saida

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_name(self.arquivo.name + ".tmp")
        # 0600 desde o nascimento: um `chmod` depois deixaria um instante em
        # que o arquivo existe legivel por todos.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.salvas, f, indent=2, sort_keys=True)
        try:
            os.chmod(tmp, 0o600)  # um .tmp que sobrou de antes guarda a permissao velha
        except OSError:
            pass
        os.replace(tmp, self.arquivo)

    def _aplicar(self) -> None:
        for v in VARIAVEIS:
            valor = self.salvas.get(v) or self.originais.get(v)
            if valor:
                self.environ[v] = valor
            else:
                self.environ.pop(v, None)

    def estado(self) -> dict:
        saida = {}
        for v in VARIAVEIS:
            if self.salvas.get(v):
                saida[v] = {"configurada": True, "origem": "site",
                            "final": final_de(self.salvas[v])}
            elif self.originais.get(v):
                saida[v] = {"configurada": True, "origem": "arquivo",
                            "final": final_de(self.originais[v])}
            else:
                saida[v] = {"configurada": False, "origem": None, "final": None}
        return saida

    def valor(self, variavel: str) -> str:
        return self.salvas.get(variavel) or self.originais.get(variavel) or ""

    def trocar(self, limpas: Mapping[str, Optional[str]]) -> None:
        """Grava as chaves (ja passadas por `limpar`) e tira as que vierem
        None. Ou tudo, ou nada: sem gravar o arquivo, o ambiente nao muda."""
        novas = dict(self.salvas)
        for v, valor in limpas.items():
            if v not in VARIAVEIS:
                raise ChaveInvalida("desconhecida", v)
            if valor:
                novas[v] = valor
            else:
                novas.pop(v, None)
        antigas, self.salvas = self.salvas, novas
        try:
            self._gravar()
        except OSError:
            self.salvas = antigas
            raise
        self._aplicar()


def limpar_pedido(mudancas: Mapping) -> dict:
    """O corpo do `POST /api/chaves`, conferido INTEIRO antes de qualquer
    gravacao: metade de uma troca do Cloudflare (o token sem a conta) seria um
    provedor que nunca funciona. Texto vazio ou None e remover."""
    limpas = {}
    for v, valor in mudancas.items():
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            if v not in VARIAVEIS:
                raise ChaveInvalida("desconhecida", v)
            limpas[v] = None
        else:
            limpas[v] = limpar(v, valor)
    return limpas


# --- conferir a chave com o provedor ---------------------------------------------------

#: O Gemini pelo endpoint NATIVO, listando modelos: as chaves novas do AI
#: Studio (`AQ.`) dao 401 no caminho compativel com OpenAI (.env.example), e a
#: listagem nao gasta cota.
GEMINI_MODELOS = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
CLOUDFLARE_BASE = "https://api.cloudflare.com/client/v4/accounts/{conta}/ai/v1"


def _provedor_de(variavel: str):
    """O primeiro provedor da cascata que usa a variavel (a do Groq serve a
    tres modelos: basta conferir um)."""
    import llm_cascade
    chave = "CLOUDFLARE_API_TOKEN" if variavel == "CLOUDFLARE_ACCOUNT_ID" else variavel
    return next((p for p in llm_cascade._CATALOG if p.key_env == chave), None)


def provedores_a_testar(limpas: Mapping[str, Optional[str]]) -> list:
    """Uma variavel por provedor que ganhou chave nova (a conta e o token do
    Cloudflare sao um teste so)."""
    vistos, saida = set(), []
    for v, valor in limpas.items():
        if not valor:
            continue
        p = _provedor_de(v)
        if p is None or p.id in vistos:
            continue
        vistos.add(p.id)
        saida.append("CLOUDFLARE_API_TOKEN" if p.id == "cloudflare" else p.key_env)
    return saida


def classificar(status: int, corpo: str = "") -> dict:
    """`ok`; `recusada` (401, ou o "API key not valid" do Google -- a mesma
    regra do `llm_cascade.chave_recusada`); `ocupado` (429: a chave passou, a
    fila e que esta cheia); `sem_resposta` (5xx); `incerto` (outra resposta,
    que nao recusa a chave mas tambem nao a confirma)."""
    import llm_cascade
    if 200 <= status < 300:
        resultado = "ok"
    elif status == 401 or llm_cascade.chave_recusada(f"llm server {status} {corpo[:300]}"):
        resultado = "recusada"
    elif status == 429:
        resultado = "ocupado"
    elif status >= 500:
        resultado = "sem_resposta"
    else:
        resultado = "incerto"
    return {"resultado": resultado, "status": status}


def testar(variavel: str, valores: Mapping[str, str],
           cliente: Optional[Callable] = None, timeout: float = 12.0) -> dict:
    """Pergunta ao provedor se a chave vale. Nunca levanta.

    Fora o Gemini, e uma pergunta de uma palavra ao MESMO endereco e modelo
    que a cascata vai chamar: o teste mais fiel que existe, porque o que passa
    aqui e o que o job vai usar. `valores` sao as chaves como vao ficar (as do
    motor com as novas por cima)."""
    p = _provedor_de(variavel)
    chave = (valores.get(p.key_env) or "").strip() if p else ""
    if p is None or not chave:
        return {"resultado": "incompleto", "status": None}
    if p.id == "cloudflare":
        conta = (valores.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
        if not conta:
            return {"resultado": "incompleto", "status": None}
        base = CLOUDFLARE_BASE.format(conta=conta)
    else:
        base = p.base_url
    if cliente is None:
        import httpx

        def cliente():
            return httpx.Client(timeout=timeout)
    try:
        with cliente() as c:
            if p.key_env == "GEMINI_API_KEY":
                r = c.get(GEMINI_MODELOS, headers={"x-goog-api-key": chave})
            else:
                r = c.post(f"{base.rstrip('/')}/chat/completions",
                           headers={"Authorization": f"Bearer {chave}"},
                           json={"model": p.model, "max_tokens": 16,
                                 "messages": [{"role": "user",
                                               "content": "Responda apenas: ok"}]})
    except Exception:  # rede, DNS, timeout: nao deu para saber
        return {"resultado": "sem_resposta", "status": None}
    return classificar(r.status_code, r.text or "")
