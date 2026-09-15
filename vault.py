"""O cofre que resolve `accounts.credentials_ref` -- Fase 3, bloco 3.4.

A secao 7 e explicita: *"`credentials_ref` aponta pra um cofre, nunca guarda o
token na linha"*, e o `db_models.vault_ref()` ja montava o endereco
(`vault://local/youtube/canal-principal`) para que o caminho normal nao
conseguisse produzir um token cru. Faltava quem resolvesse o endereco.

**O cofre nao e uma tabela nova.** Dois backends, os dois sem banco:

- `env` -- as variaveis de ambiente, que e como um `docker compose` entrega
  segredo e o que o autor vai usar de verdade com uma conta so;
- `local` -- um JSON por conta em `<DATA_DIR>/vault/<plataforma>/<handle>.json`,
  criado com permissao 0600, para quando houver mais de uma conta.

**Segredo nunca entra em log, mensagem de erro ou excecao.** Todas as funcoes
daqui falam por NOME de campo ("falta refresh_token"), nunca por valor, e ha um
teste que varre as mensagens. Um token vazado no log de um job e um token
vazado -- o log do job e mostrado no painel e copiado para o WhatsApp quando
alguem pede ajuda.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

PREFIXO = "vault://"
BACKENDS = ("env", "local")

#: Os campos de um segredo de plataforma. Nomear a lista permite dizer o que
#: falta sem nunca mostrar o que tem.
CAMPOS = ("client_id", "client_secret", "refresh_token")


class VaultError(RuntimeError):
    """Endereco invalido, backend desconhecido ou credencial ausente.

    Carrega o que FALTA, nunca o que existe.
    """


def _dir_de_dados() -> str:
    return (os.environ.get("DATA_DIR") or "data").strip() or "data"


def partes(ref: str):
    """`vault://local/youtube/canal` -> `("local", "youtube", "canal")`."""
    if not isinstance(ref, str) or not ref.startswith(PREFIXO):
        raise VaultError(f"referencia de cofre invalida: {ref!r}")
    resto = ref[len(PREFIXO):]
    pedacos = resto.split("/")
    if len(pedacos) != 3 or not all(pedacos):
        raise VaultError(f"referencia de cofre invalida: {ref!r}")
    backend, plataforma, handle = pedacos
    if backend not in BACKENDS:
        raise VaultError(f"backend de cofre desconhecido: {backend!r} "
                         f"(conhecidos: {', '.join(BACKENDS)})")
    return backend, plataforma, handle


def _slug_de_env(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (texto or "").upper()).strip("_")


def _do_env(plataforma: str, handle: str) -> dict:
    """`YOUTUBE_CLIENT_ID` para a conta padrao, `YOUTUBE_CANAL2_CLIENT_ID` para
    uma segunda.

    O nome sem handle existe porque o caso real do projeto e **uma** conta, e
    obrigar `YOUTUBE_CANAL_PRINCIPAL_CLIENT_ID` para ela seria cerimonia. O
    nome com handle vence quando existe.
    """
    base = _slug_de_env(plataforma)
    com_handle = f"{base}_{_slug_de_env(handle)}"
    segredo = {}
    for campo in CAMPOS:
        sufixo = campo.upper()
        valor = (os.environ.get(f"{com_handle}_{sufixo}")
                 or os.environ.get(f"{base}_{sufixo}") or "")
        if valor.strip():
            segredo[campo] = valor.strip()
    return segredo


def caminho_local(plataforma: str, handle: str) -> str:
    seguro = re.sub(r"[^A-Za-z0-9_.-]+", "_", handle or "conta")
    return os.path.join(_dir_de_dados(), "vault", plataforma, f"{seguro}.json")


def _do_arquivo(plataforma: str, handle: str) -> dict:
    caminho = caminho_local(plataforma, handle)
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            dados = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(dados, dict):
        return {}
    return {k: v for k, v in dados.items()
            if isinstance(v, str) and v.strip()}


def resolve(ref: Optional[str], exigir: tuple = ()) -> dict:
    """O segredo por tras de um endereco de cofre.

    `exigir` lista os campos sem os quais nao vale a pena tentar. A falta
    levanta `VaultError` **nomeando os campos**, porque "credencial invalida"
    manda a pessoa adivinhar qual metade faltou.
    """
    if not ref:
        raise VaultError("esta conta nao tem credencial configurada "
                         "(accounts.credentials_ref esta vazio)")
    backend, plataforma, handle = partes(ref)
    segredo = _do_env(plataforma, handle) if backend == "env" \
        else _do_arquivo(plataforma, handle)
    faltando = [campo for campo in exigir if not segredo.get(campo)]
    if faltando:
        raise VaultError(
            f"credencial incompleta em {backend}/{plataforma}/{handle}: "
            f"falta {', '.join(faltando)}")
    return segredo


def existe(ref: Optional[str], exigir: tuple = ()) -> bool:
    """Se `resolve` responderia. Sem rede e sem levantar -- e o que o
    `capability()` de um driver chama a cada publicacao."""
    try:
        resolve(ref, exigir)
        return True
    except VaultError:
        return False


def gravar(ref: str, segredo: dict) -> str:
    """Grava um segredo no backend `local`, com permissao 0600.

    O backend `env` nao e gravavel de proposito: escrever variavel de ambiente
    de dentro do processo nao sobrevive ao restart, e gravar num `.env` a
    revelia de quem o mantem e pior que nao gravar.
    """
    backend, plataforma, handle = partes(ref)
    if backend != "local":
        raise VaultError(f"o backend {backend!r} e somente leitura; "
                         "use vault://local/... para gravar")
    limpo = {k: v for k, v in (segredo or {}).items()
             if isinstance(v, str) and v.strip()}
    if not limpo:
        raise VaultError("nao ha nada para gravar")
    caminho = caminho_local(plataforma, handle)
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    # Abre com 0600 desde a criacao: gravar e depois arrumar a permissao deixa
    # uma janela em que o arquivo esta legivel para todo mundo.
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(limpo, fh)
    return caminho
