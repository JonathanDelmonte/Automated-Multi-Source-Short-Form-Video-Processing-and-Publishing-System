"""O que cada aparelho fez, com a tela de cada passo -- etapa 7.9 (ADR-016).

"O que ele posta" (o plano, 7.9) e a resposta para "por que este post nao
saiu?": cada entrega, ensaio e post automatico vira uma execucao, com o
resultado e uma foto da tela em cada passo. Mora no disco do motor
(`DATA_DIR/frota/<aparelho>/`), e nao no banco: e evidencia, nao estado, e as
fotos nao cabem numa linha.

As fotos sao reduzidas antes de gravar (`LARGURA`, em JPEG): a tela de um
celular em PNG passa de 1 MB, e o painel so precisa ver o que estava escrito.
Ficam as ultimas `MAXIMO` execucoes de cada aparelho.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from typing import Optional

MAXIMO = 50
LARGURA = 360

_ID = re.compile(r"^[0-9a-f]{12}$")
_NOME = re.compile(r"^[0-9]{2}-[a-z0-9-]{1,40}\.(jpg|png)$")


def _base() -> str:
    return os.path.join((os.environ.get("DATA_DIR") or "").strip() or "data", "frota")


def pasta_do_aparelho(device_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f-]{36}", device_id or ""):
        raise ValueError("aparelho inválido")
    return os.path.join(_base(), device_id)


def reduzir(png: bytes, largura: int = LARGURA) -> tuple[bytes, str]:
    """A tela em JPEG pequeno; sem o Pillow, o PNG como veio."""
    try:
        from PIL import Image
        imagem = Image.open(io.BytesIO(png)).convert("RGB")
        if imagem.width > largura:
            altura = max(1, round(imagem.height * largura / imagem.width))
            imagem = imagem.resize((largura, altura))
        saida = io.BytesIO()
        imagem.save(saida, "JPEG", quality=72)
        return saida.getvalue(), "jpg"
    except Exception:
        return png, "png"


def data_url(dados: bytes, extensao: str) -> str:
    tipo = "image/jpeg" if extensao == "jpg" else "image/png"
    return f"data:{tipo};base64," + base64.b64encode(dados).decode("ascii")


class Execucao:
    """Uma execucao em curso: as fotos vao sendo gravadas, e `fechar` escreve o
    resumo e o acrescenta ao historico do aparelho."""

    def __init__(self, device_id: str, tipo: str, plataforma: str = "",
                 conta: str = "", corte: str = ""):
        self.device_id = device_id
        self.id = uuid.uuid4().hex[:12]
        self.pasta = os.path.join(pasta_do_aparelho(device_id), "execucoes", self.id)
        os.makedirs(self.pasta, exist_ok=True)
        self.resumo = {
            "id": self.id, "tipo": tipo, "plataforma": plataforma, "conta": conta,
            "corte": corte, "inicio": datetime.now(timezone.utc).isoformat(),
            "fotos": [],
        }

    def guardar(self, nome: str, png: bytes) -> None:
        nome = re.sub(r"[^a-z0-9-]+", "-", (nome or "tela").lower()).strip("-")[:40] or "tela"
        dados, extensao = reduzir(png)
        arquivo = f"{len(self.resumo['fotos']) + 1:02d}-{nome}.{extensao}"
        with open(os.path.join(self.pasta, arquivo), "wb") as f:
            f.write(dados)
        self.resumo["fotos"].append(arquivo)

    def fechar(self, situacao: str, detalhe: str = "", **extra) -> dict:
        self.resumo.update(extra)
        self.resumo["situacao"] = situacao
        self.resumo["detalhe"] = detalhe
        self.resumo["fim"] = datetime.now(timezone.utc).isoformat()
        with open(os.path.join(self.pasta, "resumo.json"), "w", encoding="utf-8") as f:
            json.dump(self.resumo, f, ensure_ascii=False)
        historico = os.path.join(pasta_do_aparelho(self.device_id), "execucoes.jsonl")
        with open(historico, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.resumo, ensure_ascii=False) + "\n")
        _podar(self.device_id)
        return self.resumo


def _podar(device_id: str) -> None:
    """Ficam as ultimas `MAXIMO` execucoes, no historico e no disco."""
    historico = os.path.join(pasta_do_aparelho(device_id), "execucoes.jsonl")
    try:
        with open(historico, encoding="utf-8") as f:
            linhas = f.readlines()
    except OSError:
        return
    if len(linhas) <= MAXIMO:
        return
    saem, ficam = linhas[:-MAXIMO], linhas[-MAXIMO:]
    with open(historico, "w", encoding="utf-8") as f:
        f.writelines(ficam)
    for linha in saem:
        try:
            run = json.loads(linha).get("id") or ""
        except ValueError:
            continue
        if _ID.match(run):
            shutil.rmtree(os.path.join(pasta_do_aparelho(device_id), "execucoes", run),
                          ignore_errors=True)


def ultimas(device_id: str, n: int = 20) -> list[dict]:
    """As execucoes mais recentes primeiro."""
    historico = os.path.join(pasta_do_aparelho(device_id), "execucoes.jsonl")
    try:
        with open(historico, encoding="utf-8") as f:
            linhas = f.readlines()
    except OSError:
        return []
    saida = []
    for linha in reversed(linhas[-max(1, n):]):
        try:
            saida.append(json.loads(linha))
        except ValueError:
            continue
    return saida


def fotos(device_id: str, execucao: str) -> list[dict]:
    """As fotos de uma execucao, prontas para a tela (`data:` URL). O id e o
    nome do arquivo vem da URL: os dois sao conferidos antes de virar caminho."""
    if not _ID.match(execucao or ""):
        raise ValueError("execução inválida")
    pasta = os.path.join(pasta_do_aparelho(device_id), "execucoes", execucao)
    try:
        with open(os.path.join(pasta, "resumo.json"), encoding="utf-8") as f:
            resumo = json.load(f)
    except (OSError, ValueError):
        return []
    saida = []
    for nome in resumo.get("fotos") or []:
        if not _NOME.match(nome):
            continue
        try:
            with open(os.path.join(pasta, nome), "rb") as f:
                saida.append({"nome": nome, "imagem": data_url(f.read(), nome.rsplit(".", 1)[1])})
        except OSError:
            continue
    return saida


def apagar(device_id: str) -> None:
    shutil.rmtree(pasta_do_aparelho(device_id), ignore_errors=True)
