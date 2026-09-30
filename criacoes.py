"""O video criado por IA do lado do banco e do disco (etapa 7.7, ADR-013).

- **O estilo do canal** (`creation_styles`): o documento de `estilos.py`, um
  por canal. As imagens dos personagens moram em disco,
  `DATA_DIR/estilos/<id do estilo>/`, e o documento guarda so o nome de cada
  arquivo -- quem monta o caminho e este modulo, nunca o que veio da tela.
- **Cada video criado** (`creations`): o job, a ideia e o roteiro. A automacao
  le daqui os temas ja feitos para nao repetir.

O CRUD do estilo **levanta**, como o dos canais: e acao de quem esta na tela,
e "o banco nao respondeu" e a resposta certa (o painel mostra o 503). O
registro das criacoes falha aberto, como o do pipeline: o video nao depende
dele.

**As imagens vao ao painel como miniatura em data URL**, e nao por uma rota de
arquivo: um `<img src>` nao manda o cabecalho da sessao, e a miniatura (192 px,
~10 KB) cabe na resposta do estilo como o avatar do canal cabe na lista.
"""
from __future__ import annotations

import base64
import io
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

import db
import db_models
import estilos
import midia_ia

#: Uma imagem enviada pela pessoa entra com no maximo este lado (a referencia
#: que vai ao modelo e reduzida de novo, a 512, na hora de criar).
LADO_MAXIMO_ENVIADO = 1024
LIMITE_DO_ENVIO = 8 * 1024 * 1024
LADO_DA_MINIATURA = 192

_ID = re.compile(r"^[0-9a-fA-F-]{36}$")
_ARQUIVO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{6}\.png$")


class EstiloError(ValueError):
    """Pedido recusado por uma regra; o texto vai para a tela como esta."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def pasta_de_dados() -> str:
    return (os.environ.get("DATA_DIR") or "data").strip() or "data"


def pasta_do_estilo(estilo_id: str) -> str:
    if not _ID.match(estilo_id or ""):
        raise EstiloError("estilo invalido")
    return os.path.join(pasta_de_dados(), "estilos", estilo_id)


def caminho_da_imagem(estilo_id: str, arquivo: Optional[str]) -> Optional[str]:
    """O caminho da imagem de um personagem, se o nome e um que este modulo
    grava e o arquivo existe."""
    if not arquivo or not _ARQUIVO.match(arquivo):
        return None
    caminho = os.path.join(pasta_do_estilo(estilo_id), arquivo)
    return caminho if os.path.isfile(caminho) else None


def miniatura(caminho: str) -> Optional[str]:
    try:
        from PIL import Image
        with Image.open(caminho) as img:
            img = img.convert("RGB")
            img.thumbnail((LADO_DA_MINIATURA, LADO_DA_MINIATURA))
            saida = io.BytesIO()
            img.save(saida, format="JPEG", quality=82)
    except Exception:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(saida.getvalue()).decode()


def _json(linha: db_models.CreationStyle) -> dict:
    spec = estilos.normalizar(linha.spec_json or {})
    imagens = {}
    for p in spec["personagens"]:
        caminho = caminho_da_imagem(linha.id, p.get("imagem"))
        if caminho is None:
            p["imagem"] = None
        else:
            imagens[p["id"]] = miniatura(caminho)
    atualizado = linha.updated_at
    if atualizado is not None and atualizado.tzinfo is None:
        atualizado = atualizado.replace(tzinfo=timezone.utc)
    return {
        "id": linha.id,
        "channel_id": linha.channel_id,
        "spec": spec,
        "imagens": imagens,
        "falta": estilos.falta_para_criar(spec),
        "sem_imagem": estilos.personagens_sem_imagem(spec),
        "updated_at": atualizado.isoformat() if atualizado else None,
    }


async def _linha_do_canal(t, canal_id: str) -> Optional[db_models.CreationStyle]:
    linhas = await t.all(db_models.CreationStyle,
                         db_models.CreationStyle.channel_id == canal_id)
    return linhas[0] if linhas else None


async def estilo_do_canal(canal_id: str) -> Optional[dict]:
    """O estilo do canal, ou None (o canal ainda nao tem). Levanta com o banco
    fora do ar."""
    if not _ID.match(canal_id or ""):
        return None
    async with db.tenant() as t:
        linha = await _linha_do_canal(t, canal_id)
        return _json(linha) if linha else None


async def salvar_estilo(canal_id: str, spec) -> dict:
    """Cria ou atualiza o estilo do canal. O nome de imagem de um personagem so
    fica se o arquivo existe na pasta DESTE estilo (quem manda a imagem e o
    `gerar_personagem`/`enviar_personagem`, nunca o corpo do PUT)."""
    if not _ID.match(canal_id or ""):
        raise EstiloError("canal invalido")
    try:
        doc = estilos.normalizar(spec, vozes=midia_ia.NOMES_DAS_VOZES)
    except estilos.EstiloInvalido as e:
        raise EstiloError(str(e))
    async with db.tenant() as t:
        if await t.get(db_models.Channel, canal_id) is None:
            raise EstiloError("esse canal nao existe")
        linha = await _linha_do_canal(t, canal_id)
        if linha is None:
            linha = t.add(db_models.CreationStyle(channel_id=canal_id, spec_json={}))
            await t.flush()
        else:
            # A semente e do estilo: o PUT da tela nao a troca por engano.
            doc["semente"] = (linha.spec_json or {}).get("semente") or doc["semente"]
        for p in doc["personagens"]:
            if caminho_da_imagem(linha.id, p.get("imagem")) is None:
                p["imagem"] = None
        linha.spec_json = doc
        linha.updated_at = _agora()
        await t.commit()
        return _json(linha)


def _gravar_imagem(estilo_id: str, personagem_id: str, png: bytes) -> str:
    """Grava a imagem nova do personagem e apaga as anteriores dele. O nome
    muda a cada versao: a miniatura antiga nao fica presa em cache nenhum."""
    pasta = pasta_do_estilo(estilo_id)
    os.makedirs(pasta, exist_ok=True)
    nome = f"{personagem_id}-{secrets.token_hex(3)}.png"
    temporario = os.path.join(pasta, nome + ".tmp")
    with open(temporario, "wb") as f:
        f.write(png)
    os.replace(temporario, os.path.join(pasta, nome))
    for antigo in os.listdir(pasta):
        if antigo.startswith(f"{personagem_id}-") and antigo != nome:
            try:
                os.remove(os.path.join(pasta, antigo))
            except OSError:
                pass
    return nome


def normalizar_envio(dados: bytes) -> bytes:
    """A imagem que a pessoa mandou, como PNG de ate 1024 de lado. Recusa o que
    nao e imagem (o navegador manda o que a pessoa escolher)."""
    if not dados or len(dados) > LIMITE_DO_ENVIO:
        raise EstiloError("mande uma imagem de ate 8 MB")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(dados)) as img:
            img.load()
            img = img.convert("RGBA")
            img.thumbnail((LADO_MAXIMO_ENVIADO, LADO_MAXIMO_ENVIADO))
            fundo = Image.new("RGB", img.size, (255, 255, 255))
            fundo.paste(img, mask=img.split()[3])
            saida = io.BytesIO()
            fundo.save(saida, format="PNG", optimize=True)
            return saida.getvalue()
    except EstiloError:
        raise
    except Exception:
        raise EstiloError("isso nao parece uma imagem (PNG, JPEG ou WebP)")


async def _por_imagem(canal_id: str, personagem_id: str, png: bytes) -> dict:
    async with db.tenant() as t:
        linha = await _linha_do_canal(t, canal_id)
        if linha is None:
            raise EstiloError("salve o estilo antes de dar imagem aos personagens")
        doc = estilos.normalizar(linha.spec_json or {})
        alvo = next((p for p in doc["personagens"] if p["id"] == personagem_id), None)
        if alvo is None:
            raise EstiloError("esse personagem nao esta no estilo salvo")
        alvo["imagem"] = _gravar_imagem(linha.id, personagem_id, png)
        linha.spec_json = doc
        linha.updated_at = _agora()
        await t.commit()
        return _json(linha)


async def personagem_e_estilo(canal_id: str, personagem_id: str) -> tuple:
    """(estilo, personagem) do estilo salvo, para gerar a ficha."""
    async with db.tenant() as t:
        linha = await _linha_do_canal(t, canal_id)
        if linha is None:
            raise EstiloError("salve o estilo antes de gerar os personagens")
        doc = estilos.normalizar(linha.spec_json or {})
    alvo = next((p for p in doc["personagens"] if p["id"] == personagem_id), None)
    if alvo is None:
        raise EstiloError("esse personagem nao esta no estilo salvo")
    if not alvo.get("descricao"):
        raise EstiloError(f"descreva como {alvo['nome']} e antes de gerar a imagem")
    return doc, alvo


def gerar_ficha(doc: dict, personagem: dict) -> bytes:
    """A imagem de referencia do personagem, pelo modelo de imagem (bloqueante:
    quem chama roda numa thread). Levanta `midia_ia.MidiaIndisponivel`."""
    img = midia_ia.gerar_imagem(estilos.prompt_do_personagem(doc, personagem),
                                semente=doc.get("semente"), largura=768, altura=768)
    return normalizar_envio(img.dados)


async def guardar_ficha(canal_id: str, personagem_id: str, png: bytes) -> dict:
    return await _por_imagem(canal_id, personagem_id, png)


async def enviar_personagem(canal_id: str, personagem_id: str, dados: bytes) -> dict:
    return await _por_imagem(canal_id, personagem_id, normalizar_envio(dados))


def referencias(estilo_id: str, doc: dict) -> dict:
    """`{id do personagem: caminho da imagem}` dos que tem imagem -- o que a
    criacao copia para a pasta do job."""
    saida = {}
    for p in doc.get("personagens") or []:
        caminho = caminho_da_imagem(estilo_id, p.get("imagem"))
        if caminho:
            saida[p["id"]] = caminho
    return saida


# --------------------------------------------------------------------------- #
# Cada video criado (falha aberto)
# --------------------------------------------------------------------------- #

async def registrar_criacao(job_id: str, canal_id: Optional[str], ideia: Optional[str],
                            titulo: Optional[str] = None,
                            roteiro: Optional[dict] = None) -> bool:
    """Cria (ou completa) a linha do video criado. Idempotente por job."""
    try:
        async with db.tenant() as t:
            linhas = await t.all(db_models.Creation, db_models.Creation.job_id == job_id)
            linha = linhas[0] if linhas else t.add(db_models.Creation(
                job_id=job_id, channel_id=canal_id, idea=(ideia or None)))
            if titulo:
                linha.title = titulo[:300]
            if roteiro:
                linha.script_json = roteiro
            await t.commit()
            return True
    except Exception as e:
        print(f"⚠️  Banco (registrar a criacao {job_id}): {e}")
        return False


async def temas_do_canal(canal_id: Optional[str], limite: int = 30) -> list:
    """Os titulos (ou as ideias) dos ultimos videos criados no canal, do mais
    recente para o mais antigo. Falha aberto: sem banco, lista vazia."""
    if not _ID.match(canal_id or ""):
        return []
    try:
        async with db.tenant() as t:
            linhas = await t.all(db_models.Creation, db_models.Creation.channel_id == canal_id)
    except Exception as e:
        print(f"⚠️  Banco (temas do canal {canal_id}): {e}")
        return []
    linhas = sorted(linhas, key=lambda l: (l.created_at.replace(tzinfo=None)
                                           if l.created_at else datetime.min),
                    reverse=True)
    return [(l.title or l.idea or "").strip() for l in linhas[:limite] if (l.title or l.idea)]
