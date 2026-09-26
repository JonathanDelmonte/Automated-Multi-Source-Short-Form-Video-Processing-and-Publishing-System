"""O cadastro de aplicativo de cada pessoa, colado no site (Fase 7, etapa 7.3).

Decisao do autor (26-set-2026): **cada pessoa usa o proprio cadastro** -- o
projeto dela no Google Cloud, o app dela no TikTok --, como ja faz com as
chaves de IA. Aqui mora a metade "do aplicativo": o Client ID e o segredo que o
Google da quando se cria um "ID do cliente OAuth" do tipo **App para
computador**. A metade "da conta" (o refresh token de cada canal) nasce no
"Conectar YouTube" (`conexoes.py`) e vai para o cofre (`vault.py`).

- **Um arquivo so, `DATA_DIR/aplicativos.json`**, 0600 desde a criacao, como o
  `chaves.json`: fora do git e da imagem do Docker, e sobrevive a reinstalar o
  ajudante (`dados\\` fica).
- **O `.env` continua valendo** (`YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`,
  os nomes que o `youtube_oauth.py` sempre usou), e o colado no site vence: e o
  gesto mais recente e explicito.
- **O segredo nunca sai**: o estado diz se ha cadastro, de onde veio e o Client
  ID (que nao e segredo -- ele viaja na URL de consentimento).
- **O Google e perguntado antes de guardar**, sem ninguem clicar em nada: um
  pedido de token com um codigo de mentira. Cliente errado responde
  `invalid_client`; cliente certo, `invalid_grant` (o codigo e que e falso). E
  um cliente do tipo errado -- "Aplicativo da Web" em vez de "App para
  computador" -- responde `redirect_uri_mismatch`, que e o erro que a pessoa
  so veria depois, no meio do consentimento.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable, MutableMapping, Optional

ARQUIVO = "aplicativos.json"

#: Os campos de cada cadastro, e de que variavel do ambiente cada um cai.
PLATAFORMAS = {
    "google": {"client_id": "YOUTUBE_CLIENT_ID", "client_secret": "YOUTUBE_CLIENT_SECRET"},
    # O app de desenvolvedor do TikTok (developers.tiktok.com), com o Login
    # Kit e o Content Posting API. O TikTok chama o id do app de `client_key`.
    "tiktok": {"client_key": "TIKTOK_CLIENT_KEY", "client_secret": "TIKTOK_CLIENT_SECRET"},
}

_FORMATOS = {
    ("google", "client_id"): re.compile(r"\d{4,30}-[A-Za-z0-9_]{8,80}\.apps\.googleusercontent\.com"),
    ("google", "client_secret"): re.compile(r"[A-Za-z0-9_-]{16,100}"),
    # `aw...` em producao, `sbaw...` no sandbox. Folgado de proposito: uma
    # chave errada o TikTok recusa na hora de conectar, e um formato apertado
    # demais trancaria uma chave certa sem saida nenhuma.
    ("tiktok", "client_key"): re.compile(r"[A-Za-z0-9]{8,64}"),
    ("tiktok", "client_secret"): re.compile(r"[A-Za-z0-9_-]{16,100}"),
}

TOKEN_GOOGLE = "https://oauth2.googleapis.com/token"


class AplicativoInvalido(ValueError):
    """`codigo`: plataforma | campo | vazio | formato | cliente | tipo."""

    def __init__(self, codigo: str, campo: Optional[str] = None):
        super().__init__(f"{campo or ''}: {codigo}")
        self.codigo = codigo
        self.campo = campo


def do_json_do_google(texto: str) -> Optional[dict]:
    """Os dois campos do JSON que o Google oferece para baixar, se foi isso
    que a pessoa colou (`{"installed": {"client_id": ..., ...}}`)."""
    if not isinstance(texto, str) or not texto.strip().startswith("{"):
        return None
    try:
        dados = json.loads(texto)
    except ValueError:
        return None
    if not isinstance(dados, dict):
        return None
    corpo = dados.get("installed") or dados.get("web") or dados
    if not isinstance(corpo, dict):
        return None
    campos = {c: corpo.get(c) for c in ("client_id", "client_secret")}
    if not all(isinstance(v, str) and v for v in campos.values()):
        return None
    if "web" in dados:
        # O tipo errado: um cliente da Web nao aceita a volta por localhost.
        raise AplicativoInvalido("tipo", "client_id")
    return campos


def limpar(plataforma: str, campo: str, valor) -> str:
    """O campo como deve ser guardado, ou `AplicativoInvalido`."""
    if plataforma not in PLATAFORMAS:
        raise AplicativoInvalido("plataforma")
    if campo not in PLATAFORMAS[plataforma]:
        raise AplicativoInvalido("campo", campo)
    if not isinstance(valor, str) or not valor.strip():
        raise AplicativoInvalido("vazio", campo)
    v = valor.strip()
    variavel = PLATAFORMAS[plataforma][campo]
    if v.startswith(f"{variavel}="):
        v = v[len(variavel) + 1:].strip()
    v = v.strip("\"'").strip()
    if not _FORMATOS[(plataforma, campo)].fullmatch(v):
        raise AplicativoInvalido("formato", campo)
    return v


class Aplicativos:
    """Os cadastros deste motor: os colados no site por cima dos do ambiente."""

    def __init__(self, data_dir, environ: MutableMapping = os.environ):
        self.arquivo = Path(data_dir) / ARQUIVO
        self.environ = environ
        self.salvos = self._ler()

    def _ler(self) -> dict:
        try:
            dados = json.loads(self.arquivo.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            # Sem o conteudo no log: o arquivo e de segredos.
            print(f"⚠️ [aplicativos] {self.arquivo} ilegivel ({type(e).__name__}).",
                  flush=True)
            return {}
        saida = {}
        for plataforma, campos in PLATAFORMAS.items():
            bloco = dados.get(plataforma) if isinstance(dados, dict) else None
            if not isinstance(bloco, dict):
                continue
            try:
                saida[plataforma] = {c: limpar(plataforma, c, bloco.get(c)) for c in campos}
            except AplicativoInvalido:
                continue
        return saida

    def _gravar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_name(self.arquivo.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.salvos, f, indent=2, sort_keys=True)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.arquivo)

    def _do_ambiente(self, plataforma: str) -> Optional[dict]:
        campos = {c: (self.environ.get(v) or "").strip()
                  for c, v in PLATAFORMAS[plataforma].items()}
        return campos if all(campos.values()) else None

    def credenciais(self, plataforma: str) -> Optional[dict]:
        """O cadastro que vale agora: o do site, ou o do ambiente, ou None."""
        return self.salvos.get(plataforma) or self._do_ambiente(plataforma)

    def estado(self) -> dict:
        saida = {}
        for plataforma in PLATAFORMAS:
            if plataforma in self.salvos:
                origem, dados = "site", self.salvos[plataforma]
            elif self._do_ambiente(plataforma):
                origem, dados = "arquivo", self._do_ambiente(plataforma)
            else:
                origem, dados = None, None
            saida[plataforma] = {
                "configurado": dados is not None,
                "origem": origem,
                # O id do app nao e segredo (viaja na URL de consentimento), e
                # e o que a pessoa reconhece. O segredo nunca sai.
                "client_id": (dados.get("client_id") or dados.get("client_key")) if dados else None,
            }
        return saida

    def trocar(self, plataforma: str, campos: Optional[dict]) -> None:
        """Grava o cadastro (ja limpo) ou tira (None). Sem gravar o arquivo,
        nada muda."""
        if plataforma not in PLATAFORMAS:
            raise AplicativoInvalido("plataforma")
        novos = dict(self.salvos)
        if campos:
            novos[plataforma] = dict(campos)
        else:
            novos.pop(plataforma, None)
        antigos, self.salvos = self.salvos, novos
        try:
            self._gravar()
        except OSError:
            self.salvos = antigos
            raise


def limpar_pedido(corpo) -> tuple:
    """`(plataforma, campos | None)` do corpo do `POST /api/aplicativos`.

    `remover: true` tira o cadastro. O JSON baixado do Google pode vir colado
    no campo do Client ID, e os dois campos saem dele."""
    if not isinstance(corpo, dict):
        raise AplicativoInvalido("vazio")
    plataforma = corpo.get("plataforma")
    if plataforma not in PLATAFORMAS:
        raise AplicativoInvalido("plataforma")
    if corpo.get("remover") is True:
        return plataforma, None
    bruto = {c: corpo.get(c) for c in PLATAFORMAS[plataforma]}
    if plataforma == "google":
        do_json = do_json_do_google(bruto.get("client_id") or "")
        if do_json:
            bruto = do_json
    return plataforma, {c: limpar(plataforma, c, v) for c, v in bruto.items()}


# --- conferir com o Google -------------------------------------------------------------

def classificar_google(status: int, corpo: str = "") -> str:
    """`ok` (o cliente existe e o segredo bate: so o codigo e falso);
    `cliente` (Client ID ou segredo errado); `tipo` (cliente da Web, que nao
    aceita a volta por localhost); `incerto` (qualquer outra coisa)."""
    try:
        erro = (json.loads(corpo or "{}") or {}).get("error") or ""
    except ValueError:
        erro = ""
    if erro == "invalid_grant":
        return "ok"
    if erro in ("invalid_client", "unauthorized_client"):
        return "cliente"
    if erro == "redirect_uri_mismatch":
        return "tipo"
    return "incerto"


def testar_google(campos: dict, cliente: Optional[Callable] = None,
                  timeout: float = 12.0) -> str:
    """Pergunta ao Google se o cadastro vale. Nunca levanta: sem rede, `incerto`."""
    if cliente is None:
        import httpx

        def cliente():
            return httpx.Client(timeout=timeout)
    try:
        with cliente() as c:
            r = c.post(TOKEN_GOOGLE, data={
                "client_id": campos["client_id"],
                "client_secret": campos["client_secret"],
                "code": "virtu-clips-conferencia",
                "grant_type": "authorization_code",
                "redirect_uri": "http://127.0.0.1",
            })
    except Exception:
        return "incerto"
    return classificar_google(r.status_code, r.text or "")
