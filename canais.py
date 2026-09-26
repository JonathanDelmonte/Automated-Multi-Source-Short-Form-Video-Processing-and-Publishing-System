"""Canais: a marca no centro da plataforma (Fase 7, etapa 7.1).

Um canal e o que a pessoa cria para um nicho -- "Canal infantil", "Financas em
1 minuto" -- com as contas de cada plataforma ligadas a ele: o mesmo canal no
YouTube, no TikTok e no Instagram e o caso comum (os "dois galhos" do autor).
Projetos, automacao, agenda e analises passam a ser DO canal. O desenho inteiro
esta em `docs/PLANO-DA-PLATAFORMA.md`.

**As ligacoes moram em tabelas proprias** (`channel_accounts`,
`channel_jobs`), e nao em colunas novas de `accounts` e `jobs`: o motor cria o
banco no boot com `create_all`, que cria tabela que falta mas nunca acrescenta
coluna. Um `accounts.channel_id` nao chegaria ao banco de quem ja usa.

**O canal de um projeto tem dois registros**, e cada um serve a uma metade: a
pasta do projeto (`.canal`, gravada pelo `app.py`), que e de onde a lista de
projetos le -- ela vem do disco --, e a linha de `channel_jobs`, para as
consultas do lado do banco (analises por canal). A linha falha aberto como todo
registro do pipeline (`ligar_job`); a pasta e quem manda.

O CRUD, ao contrario, **levanta**: criar ou editar um canal e acao de quem esta
na tela, e "o banco nao respondeu" e a resposta certa -- o painel mostra o 503.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

import db
import db_models
import publish_queue
import receitas


class CanalError(ValueError):
    """Pedido recusado por uma regra; o texto vai para a tela como esta."""


class CanalDuplicado(CanalError):
    """Nome repetido (409), ou outra gravacao na mesma hora."""


LIMITE_NOME = 80
LIMITE_NICHO = 80
#: Caracteres do data URL. O painel reduz a imagem a 256 px antes de mandar
#: (~20-40 mil caracteres); o teto so segura quem mandar a foto original. Ele
#: importa porque a imagem viaja DENTRO da lista de canais, que o painel pede
#: a cada tela.
LIMITE_AVATAR = 200_000
#: So formatos que todo navegador desenha, e so base64: um `data:image/svg+xml`
#: seria um documento com script, e a lista e desenhada num <img> de todo painel.
_AVATAR = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$")
_COR = re.compile(r"^#[0-9a-fA-F]{6}$")
#: "pt", "pt-BR", "en-US": o idioma em que o canal fala, para quando a IA
#: escrever titulo e roteiro por ele (7.5 e 7.7).
_IDIOMA = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")
#: Os ids do schema sao uuid4 em texto (`db_models.new_id`).
_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")

#: Os campos que viram coluna. `contas` e `novas_contas` sao ligacoes.
COLUNAS = ("name", "niche", "avatar", "color", "language", "requires_approval")


def id_valido(valor) -> bool:
    return isinstance(valor, str) and bool(_ID.match(valor))


def _texto(valor, campo: str, limite: int, obrigatorio: bool) -> Optional[str]:
    if valor is None:
        if obrigatorio:
            raise CanalError(f"falta o campo {campo}")
        return None
    if not isinstance(valor, str):
        raise CanalError(f"{campo} tem de ser texto")
    limpo = valor.strip()
    if _CONTROLE.search(limpo):
        raise CanalError(f"{campo} tem caractere de controle")
    if not limpo:
        if obrigatorio:
            raise CanalError(f"{campo} nao pode ficar vazio")
        return None
    if len(limpo) > limite:
        raise CanalError(f"{campo} passa de {limite} caracteres")
    return limpo


def validar(dados: dict, criando: bool) -> dict:
    """Os campos do pedido, limpos, so os presentes. Levanta `CanalError`.

    Editar e parcial: campo ausente fica como esta, e `None` ou "" apaga o que
    e opcional. Criar exige o nome e exige `requires_approval` -- quem decide se
    o canal espera aprovacao antes de postar e a pessoa, ao criar (decisao do
    autor, 26-set-2026), e um padrao aqui decidiria por ela sem ninguem ver.
    """
    if not isinstance(dados, dict):
        raise CanalError("o pedido tem de ser um objeto")
    saida: dict = {}
    if criando or "name" in dados:
        saida["name"] = _texto(dados.get("name"), "name", LIMITE_NOME, True)
    if "niche" in dados:
        saida["niche"] = _texto(dados["niche"], "niche", LIMITE_NICHO, False)
    if "avatar" in dados:
        avatar = dados["avatar"]
        if avatar in (None, ""):
            saida["avatar"] = None
        elif not isinstance(avatar, str):
            raise CanalError("avatar tem de ser uma imagem png, jpeg ou webp em data URL")
        elif len(avatar) > LIMITE_AVATAR:
            # Antes da expressao regular, que nao precisa percorrer megabytes
            # para recusar.
            raise CanalError("a imagem do canal e grande demais; use uma menor")
        elif not _AVATAR.match(avatar):
            raise CanalError("avatar tem de ser uma imagem png, jpeg ou webp em data URL")
        else:
            saida["avatar"] = avatar
    if "color" in dados:
        cor = dados["color"]
        if cor in (None, ""):
            saida["color"] = None
        elif not isinstance(cor, str) or not _COR.match(cor):
            raise CanalError("color tem de ser no formato #rrggbb")
        else:
            saida["color"] = cor.lower()
    if "language" in dados:
        idioma = dados["language"]
        if idioma in (None, ""):
            saida["language"] = None
        elif not isinstance(idioma, str) or not _IDIOMA.match(idioma):
            raise CanalError("language tem de ser como pt ou pt-BR")
        else:
            saida["language"] = idioma
    if criando or "requires_approval" in dados:
        aprovacao = dados.get("requires_approval")
        if not isinstance(aprovacao, bool):
            raise CanalError("diga se o canal espera aprovacao antes de postar "
                             "(requires_approval: true ou false)")
        saida["requires_approval"] = aprovacao
    if "contas" in dados:
        contas = dados["contas"]
        if contas is None:
            contas = []
        if not isinstance(contas, list) or not all(id_valido(c) for c in contas):
            raise CanalError("contas tem de ser uma lista de ids de conta")
        saida["contas"] = list(dict.fromkeys(contas))
    if "novas_contas" in dados:
        novas = dados["novas_contas"] or []
        if not isinstance(novas, list):
            raise CanalError("novas_contas tem de ser uma lista")
        limpas = []
        for nova in novas:
            if not isinstance(nova, dict):
                raise CanalError("cada conta nova tem plataforma e @")
            platform = nova.get("platform")
            handle = nova.get("handle")
            if not isinstance(platform, str) or not isinstance(handle, str):
                raise CanalError("cada conta nova tem plataforma e @")
            try:
                publish_queue.validar_conta(platform, handle)
            except publish_queue.FilaError as e:
                raise CanalError(str(e))
            limpas.append({"platform": platform, "handle": handle.strip()})
        saida["novas_contas"] = limpas
    if "ajustes" in dados:
        # So confere a forma aqui; o documento inteiro (com o que ja estava
        # gravado por baixo) e montado na hora de gravar.
        try:
            receitas.normalizar_ajustes(dados["ajustes"])
        except receitas.ReceitaInvalida as e:
            raise CanalError(str(e))
        saida["ajustes"] = dados["ajustes"]
    return saida


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #

def _conta_curta(conta) -> dict:
    return {"id": conta.id, "platform": conta.platform, "handle": conta.handle,
            "driver_pref": conta.driver_pref}


def _ajustes_json(canal, linha) -> dict:
    """Os ajustes como a tela os le: o que o canal escolheu, o que vale de
    fato (com os padroes da instalacao onde ele nao escolheu) e o "feito para
    criancas" com a origem do valor."""
    import scheduler

    ajustes = receitas.ajustes_gravados(getattr(linha, "settings_json", None))
    return {
        **ajustes,
        "agenda_efetiva": receitas.agenda_efetiva(
            ajustes, scheduler.janelas(), scheduler.por_dia()),
        "criancas": receitas.feito_para_criancas(ajustes, canal.niche),
    }


def _json(canal, contas: list, ajustes=None) -> dict:
    return {
        "id": canal.id,
        "name": canal.name,
        "niche": canal.niche,
        "avatar": canal.avatar,
        "color": canal.color,
        "language": canal.language,
        "requires_approval": bool(canal.requires_approval),
        "created_at": canal.created_at.isoformat() if canal.created_at else None,
        # Na ordem das plataformas, que e a ordem dos icones na tela.
        "contas": sorted((_conta_curta(c) for c in contas),
                         key=lambda c: (publish_queue.PLATAFORMAS.index(c["platform"])
                                        if c["platform"] in publish_queue.PLATAFORMAS else 99,
                                        c["handle"].lower())),
        # A agenda do canal e o "feito para criancas" (7.5). Sempre presente:
        # um canal que nunca mexeu nos ajustes tem os padroes.
        "ajustes": _ajustes_json(canal, ajustes),
    }


async def _ajustes_por_canal(t) -> dict:
    return {a.channel_id: a for a in await t.all(db_models.ChannelSettings)}


async def _contas_por_canal(t) -> dict:
    """{channel_id: [linhas de accounts]} do tenant, numa consulta so por tabela."""
    ligacoes = await t.all(db_models.ChannelAccount)
    contas = {c.id: c for c in await t.all(db_models.Account)}
    por_canal: dict = {}
    for ligacao in ligacoes:
        conta = contas.get(ligacao.account_id)
        if conta is not None:
            por_canal.setdefault(ligacao.channel_id, []).append(conta)
    return por_canal


async def listar() -> list:
    async with db.tenant() as t:
        canais = await t.all(db_models.Channel)
        por_canal = await _contas_por_canal(t)
        ajustes = await _ajustes_por_canal(t)
    canais = sorted(canais, key=lambda c: c.name.lower())
    return [_json(c, por_canal.get(c.id, []), ajustes.get(c.id)) for c in canais]


async def obter(canal_id: str) -> Optional[dict]:
    if not id_valido(canal_id):
        return None
    async with db.tenant() as t:
        canal = await t.get(db_models.Channel, canal_id)
        if canal is None:
            return None
        por_canal = await _contas_por_canal(t)
        ajustes = await _ajustes_por_canal(t)
    return _json(canal, por_canal.get(canal.id, []), ajustes.get(canal.id))


async def idioma(canal_id: Optional[str]) -> Optional[str]:
    """O idioma do canal (o do credito da licenca), ou None. Falha aberto."""
    if not id_valido(canal_id):
        return None
    try:
        async with db.tenant() as t:
            canal = await t.get(db_models.Channel, canal_id)
            return canal.language if canal is not None else None
    except Exception as e:
        print(f"⚠️  Banco (idioma do canal {canal_id}): {e}")
        return None


async def existe(canal_id: str) -> Optional[bool]:
    """True/False; None quando o banco nao respondeu -- quem chama decide se
    isso bloqueia (mover um projeto) ou passa (processar um video)."""
    if not id_valido(canal_id):
        return False
    try:
        async with db.tenant() as t:
            return await t.get(db_models.Channel, canal_id) is not None
    except Exception as e:
        print(f"⚠️  Banco (conferir canal {canal_id}): {e}")
        return None


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #

async def _nome_em_uso(t, nome: str, fora: Optional[str] = None) -> bool:
    """Sem diferenca de maiuscula: "Canal Infantil" e "canal infantil" seriam
    dois lugares para o mesmo trabalho. A unicidade do schema e exata, e fica
    de rede para dois pedidos ao mesmo tempo."""
    iguais = await t.all(db_models.Channel,
                         func.lower(db_models.Channel.name) == nome.lower())
    return any(c.id != fora for c in iguais)


async def _ligar_contas(t, canal_id: str, campos: dict) -> None:
    """Poe o canal com exatamente as contas pedidas (`contas`, quando veio) mais
    as criadas agora (`novas_contas`).

    Uma conta pertence a um canal so: pedir aqui uma conta ligada a outro canal
    a MOVE -- o painel diz isso antes de mandar. Conta que sai do canal nao e
    apagada: fica solta, com o historico de publicacao dela.
    """
    atuais = await t.all(db_models.ChannelAccount,
                         db_models.ChannelAccount.channel_id == canal_id)
    queridas: Optional[list] = campos.get("contas")
    if queridas is not None:
        existentes = {c.id for c in await t.all(
            db_models.Account, db_models.Account.id.in_(queridas))}
        faltando = [c for c in queridas if c not in existentes]
        if faltando:
            raise CanalError(f"conta nao encontrada: {faltando[0]}")
        for ligacao in atuais:
            if ligacao.account_id not in queridas:
                await t.session.delete(ligacao)
        ja_aqui = {l.account_id for l in atuais}
        a_ligar = [c for c in queridas if c not in ja_aqui]
    else:
        a_ligar = []

    for nova in campos.get("novas_contas") or []:
        try:
            conta = await publish_queue.acrescentar_conta(
                t, nova["platform"], nova["handle"])
        except publish_queue.FilaError as e:
            raise CanalError(str(e))
        await t.flush()
        a_ligar.append(conta.id)

    if a_ligar:
        # A ligacao antiga sai ANTES de a nova entrar: a unicidade e por conta.
        for antiga in await t.all(db_models.ChannelAccount,
                                  db_models.ChannelAccount.account_id.in_(a_ligar)):
            await t.session.delete(antiga)
        await t.flush()
        for conta_id in a_ligar:
            t.add(db_models.ChannelAccount(channel_id=canal_id, account_id=conta_id))


async def _gravar_ajustes(t, canal_id: str, dados: Optional[dict]):
    """Os ajustes do canal com `dados` por cima do que ja estava. Devolve a
    linha (nova ou a de sempre)."""
    linha = (await t.all(db_models.ChannelSettings,
                         db_models.ChannelSettings.channel_id == canal_id) or [None])[0]
    base = receitas.ajustes_gravados(linha.settings_json) if linha is not None else None
    try:
        documento = receitas.normalizar_ajustes(dados, base=base)
    except receitas.ReceitaInvalida as e:
        raise CanalError(str(e))
    if linha is None:
        linha = t.add(db_models.ChannelSettings(channel_id=canal_id, settings_json=documento))
    else:
        # Atribuir um dict NOVO: o SQLAlchemy nao percebe mudanca dentro do
        # mesmo objeto de uma coluna JSON.
        linha.settings_json = documento
        linha.updated_at = datetime.now(timezone.utc)
    return linha


def _conflito(e: IntegrityError) -> CanalDuplicado:
    """A unicidade do schema pegou o que a conferencia de antes nao viu: dois
    pedidos ao mesmo tempo. O SQLite nomeia as colunas; o Postgres, a regra."""
    texto = str(e.orig)
    if "uq_channels_tenant_name" in texto or "channels.name" in texto:
        return CanalDuplicado("ja existe um canal com esse nome")
    return CanalDuplicado("outra gravacao mexeu no mesmo canal ou nas mesmas "
                          "contas agora; recarregue e tente de novo")


async def criar(dados: dict) -> dict:
    campos = validar(dados, criando=True)
    async with db.tenant() as t:
        if await _nome_em_uso(t, campos["name"]):
            raise CanalDuplicado("ja existe um canal com esse nome")
        try:
            canal = t.add(db_models.Channel(
                **{k: campos[k] for k in COLUNAS if k in campos}))
            await t.flush()
            await _ligar_contas(t, canal.id, campos)
            ajustes = None
            if "ajustes" in campos:
                ajustes = await _gravar_ajustes(t, canal.id, campos["ajustes"])
            await t.commit()
        except IntegrityError as e:
            await t.session.rollback()
            raise _conflito(e)
        por_canal = await _contas_por_canal(t)
        return _json(canal, por_canal.get(canal.id, []), ajustes)


async def atualizar(canal_id: str, dados: dict) -> Optional[dict]:
    """None quando o canal nao existe (neste tenant)."""
    campos = validar(dados, criando=False)
    if not id_valido(canal_id):
        return None
    async with db.tenant() as t:
        canal = await t.get(db_models.Channel, canal_id)
        if canal is None:
            return None
        if "name" in campos and await _nome_em_uso(t, campos["name"], fora=canal.id):
            raise CanalDuplicado("ja existe um canal com esse nome")
        try:
            for coluna in COLUNAS:
                if coluna in campos:
                    setattr(canal, coluna, campos[coluna])
            await _ligar_contas(t, canal.id, campos)
            if "ajustes" in campos:
                await _gravar_ajustes(t, canal.id, campos["ajustes"])
            await t.commit()
        except IntegrityError as e:
            await t.session.rollback()
            raise _conflito(e)
        por_canal = await _contas_por_canal(t)
        ajustes = await _ajustes_por_canal(t)
        return _json(canal, por_canal.get(canal.id, []), ajustes.get(canal.id))


async def apagar(canal_id: str) -> Optional[dict]:
    """Apaga o canal e devolve o que ficou solto, ou None se nao existia.

    As contas e os projetos NAO vao junto: so as ligacoes (por cascata do
    schema). Apagar um canal e reorganizar; apagar uma conta leva o historico
    de publicacao dela, e isso e outra decisao, com outro botao.
    """
    if not id_valido(canal_id):
        return None
    async with db.tenant() as t:
        canal = await t.get(db_models.Channel, canal_id)
        if canal is None:
            return None
        contas = await t.all(db_models.ChannelAccount,
                             db_models.ChannelAccount.channel_id == canal_id)
        projetos = await t.all(db_models.ChannelJob,
                               db_models.ChannelJob.channel_id == canal_id)
        resumo = {"name": canal.name, "contas_desligadas": len(contas),
                  "projetos_desligados": len(projetos)}
        await t.session.delete(canal)
        await t.commit()
        return resumo


# --------------------------------------------------------------------------- #
# O projeto e o canal
# --------------------------------------------------------------------------- #

async def ligar_job(job_id: str, canal_id: Optional[str]) -> bool:
    """Poe (ou tira, com None) o projeto no canal, do lado do banco.

    Falha aberto, como o `job_registry`: o projeto guarda o canal na propria
    pasta, e e dali que a lista le. Sem a linha de `jobs` (banco fora do ar no
    submit, ou projeto anterior ao bloco 3.3) a FK recusa, e isso e so um aviso.
    """
    try:
        async with db.tenant() as t:
            for antiga in await t.all(db_models.ChannelJob,
                                      db_models.ChannelJob.job_id == job_id):
                await t.session.delete(antiga)
            if canal_id:
                await t.flush()
                t.add(db_models.ChannelJob(channel_id=canal_id, job_id=job_id))
            await t.commit()
            return True
    except Exception as e:
        print(f"⚠️  Banco (ligar projeto {job_id} ao canal {canal_id}): {e}")
        return False



# --------------------------------------------------------------------------- #
# A agenda de cada conta (7.5)
# --------------------------------------------------------------------------- #

async def canal_da_conta(account_id: Optional[str]) -> Optional[str]:
    """O canal a que a conta esta ligada, ou None (conta solta).

    **Levanta se o banco nao responde**, ao contrario de `idioma`: quem chama
    e o "feito para criancas" do envio, e na duvida o envio nao sai marcado
    errado.
    """
    if not id_valido(account_id):
        return None
    async with db.tenant() as t:
        ligacoes = await t.all(db_models.ChannelAccount,
                               db_models.ChannelAccount.account_id == account_id)
    return ligacoes[0].channel_id if ligacoes else None


async def agendas_das_contas(conta_ids, tenant_id: Optional[str] = None) -> dict:
    """`{conta: scheduler.AgendaDaConta}`: as janelas e o teto do canal de cada
    conta, e o fuso de quem usa.

    **Sessao crua**, como `publish_queue.ocupados_das_contas`: o laco do
    agendador e do servidor e atravessa os tenants, e o fuso vem do tenant de
    cada conta. Conta sem canal (ou canal sem ajustes) fica com as janelas da
    instalacao -- mas no fuso de quem usa, que e o conserto desta etapa.
    """
    import fuso
    import scheduler
    from sqlalchemy import select as _select

    ids = [c for c in dict.fromkeys(conta_ids or ()) if c]
    if not ids:
        return {}
    A, L, S = db_models.Account, db_models.ChannelAccount, db_models.ChannelSettings
    consulta = (_select(A.id, A.tenant_id, S.settings_json)
                .select_from(A)
                .join(L, (L.account_id == A.id) & (L.tenant_id == A.tenant_id), isouter=True)
                .join(S, (S.channel_id == L.channel_id) & (S.tenant_id == A.tenant_id),
                      isouter=True)
                .where(A.id.in_(ids)))
    if tenant_id:
        consulta = consulta.where(A.tenant_id == tenant_id)
    async with db.session() as s:
        linhas = (await s.execute(consulta)).all()
    fusos: dict = {}
    agendas: dict = {}
    for conta_id, dono, documento in linhas:
        if dono not in fusos:
            fusos[dono] = fuso.tz_do_tenant(dono)
        agenda = receitas.ajustes_gravados(documento).get("agenda") or {}
        janelas = agenda.get("janelas")
        agendas[conta_id] = scheduler.AgendaDaConta(
            horas=tuple(janelas) if janelas else None,
            teto=agenda.get("por_dia") or None,
            fuso=fusos[dono])
    return agendas
