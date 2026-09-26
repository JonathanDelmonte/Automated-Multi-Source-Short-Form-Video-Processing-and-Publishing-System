"""O fuso de quem usa, guardado no motor (Fase 7, etapa 7.5).

**O defeito que isto conserta, achado na 7.4:** o agendador calculava as
janelas no fuso do PROCESSO, e no Docker o container roda em UTC -- as 11h,
15h e 19h viravam 8h, 12h e 16h em Brasilia. "Postar as 11h" e uma frase sobre
o relogio de quem usa, e o processo nao tem como saber qual e.

Quem sabe e o navegador. O painel manda, a cada vez que abre, o nome do fuso
(`America/Sao_Paulo`) e a diferenca para UTC naquele momento, e o motor guarda
os dois por tenant em `DATA_DIR/fuso.json`. O laco da automacao e a trava do
agendador rodam sem ninguem olhando -- e por isso o fuso tem de estar no motor,
e nao so no pedido.

**Por que o motor guarda tambem a diferenca em minutos.** O nome e o certo (ele
sabe do horario de verao), mas so vale com a base de fusos (`zoneinfo`), que o
Python do Windows nao traz e a imagem do Docker pode nao trazer -- o Debian
trixie deixou de instalar o `tzdata` por padrao. Sem a base, a diferenca de
agora e a melhor resposta que ha: exata no Brasil (sem horario de verao desde
2019) e, onde ha, certa ate a proxima troca -- e o painel a renova toda vez que
abre.

**Sem nada guardado vale o fuso do processo**, que e o comportamento de antes:
no ajudante e a hora do Windows, que e a certa; no Docker, UTC, que era o
defeito -- e que some na primeira vez que alguem abre o painel.

Stdlib pura: o CI exercita a conta sem banco.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional

ARQUIVO = "fuso.json"

#: `America/Sao_Paulo`, `Europe/Lisbon`, `UTC`, `Etc/GMT+3`. O nome vai para o
#: `zoneinfo`, que abriria um arquivo com esse nome: nada de `..` nem barra no
#: comeco.
_NOME = re.compile(r"^[A-Za-z][A-Za-z0-9_+\-]*(/[A-Za-z0-9_+\-]+){0,2}$")
#: O mundo vai de UTC-12 a UTC+14.
OFFSET_MINIMO = -12 * 60
OFFSET_MAXIMO = 14 * 60

_trava = threading.Lock()


class FusoInvalido(ValueError):
    pass


def validar(nome, offset_min) -> tuple:
    """`(nome, offset_min)` limpos, ou `FusoInvalido`."""
    if not isinstance(nome, str) or not _NOME.match(nome.strip()) or ".." in nome:
        raise FusoInvalido("fuso tem de ser um nome como America/Sao_Paulo")
    if isinstance(offset_min, bool) or not isinstance(offset_min, (int, float)):
        raise FusoInvalido("offset_min tem de ser um numero de minutos")
    offset = int(round(offset_min))
    if not OFFSET_MINIMO <= offset <= OFFSET_MAXIMO:
        raise FusoInvalido("offset_min fora do que existe (-720 a 840)")
    return nome.strip(), offset


def tz_de(nome: Optional[str], offset_min: Optional[int] = None) -> Optional[tzinfo]:
    """O fuso pelo nome, ou a diferenca fixa quando nao ha base de fusos."""
    if nome:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(nome)
        except Exception:
            pass
    if offset_min is not None:
        try:
            return timezone(timedelta(minutes=int(offset_min)))
        except (TypeError, ValueError):
            return None
    return None


def _caminho(data_dir: Optional[str] = None) -> str:
    base = data_dir or (os.environ.get("DATA_DIR") or "").strip() or "data"
    return os.path.join(base, ARQUIVO)


def _ler(data_dir: Optional[str] = None) -> dict:
    try:
        with open(_caminho(data_dir), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def guardar(tenant_id: str, nome, offset_min, data_dir: Optional[str] = None) -> dict:
    """Guarda o fuso do tenant. Levanta `FusoInvalido`."""
    nome, offset = validar(nome, offset_min)
    registro = {"nome": nome, "offset_min": offset,
                "visto_em": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _trava:
        dados = _ler(data_dir)
        dados[str(tenant_id)] = registro
        caminho = _caminho(data_dir)
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(temporario, caminho)
    return registro


def do_tenant(tenant_id: str, data_dir: Optional[str] = None) -> Optional[dict]:
    """`{"nome", "offset_min", "visto_em"}`, ou None se ninguem mandou ainda."""
    registro = _ler(data_dir).get(str(tenant_id))
    if not isinstance(registro, dict):
        return None
    try:
        nome, offset = validar(registro.get("nome"), registro.get("offset_min"))
    except FusoInvalido:
        return None
    return {"nome": nome, "offset_min": offset, "visto_em": registro.get("visto_em")}


def tz_do_tenant(tenant_id: str, data_dir: Optional[str] = None) -> tzinfo:
    """O fuso em que as janelas deste tenant valem. Nunca None: sem nada
    guardado, o do processo -- o comportamento de antes desta etapa."""
    registro = do_tenant(tenant_id, data_dir)
    if registro:
        tz = tz_de(registro["nome"], registro["offset_min"])
        if tz is not None:
            return tz
    return datetime.now().astimezone().tzinfo


def descricao(tenant_id: str, data_dir: Optional[str] = None) -> dict:
    """Para a tela: qual fuso vale e de onde ele veio."""
    registro = do_tenant(tenant_id, data_dir)
    if registro:
        return {"nome": registro["nome"], "offset_min": registro["offset_min"],
                "origem": "painel"}
    agora = datetime.now().astimezone()
    offset = agora.utcoffset() or timedelta(0)
    return {"nome": None, "offset_min": int(offset.total_seconds() // 60),
            "origem": "processo"}
