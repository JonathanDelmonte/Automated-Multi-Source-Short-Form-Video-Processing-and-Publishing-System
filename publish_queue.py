"""A fila de publicacao: contas, publicar, e o que ja foi -- Fase 3, bloco 3.5.

Junta as tres metades que os blocos anteriores deixaram prontas: o resolvedor
da secao 6 (`publishers`), as linhas de `clips` que o pipeline passou a gravar
(`job_registry`) e as contas de plataforma do schema. O resultado e a linha de
`publications` -- que e onde "este corte foi para este canal por este driver"
passa a existir fora da cabeca de quem publicou.

**Quem escolhe o driver e o resolvedor, nunca o chamador.** O endpoint aceita
`account_id`, e nao `driver`: deixar o painel mandar o driver seria reabrir
por fora exatamente a porta que o ADR-010 fechou -- bastaria um `driver:
"browser"` num corpo de requisicao. A conta e um endereco; o driver e uma
consequencia.

**A linha nasce antes do upload e e fechada depois.** `publishing` enquanto
sobe; `published` ou `failed` no fim. Gravar so no sucesso deixaria um upload
que morreu no meio sem rastro nenhum -- e a unicidade `(clip, conta)` e o que
impede o retry de publicar duas vezes.

Tudo falha aberto **menos a publicacao em si**: sem banco nao ha como impedir
post duplicado, e um corte publicado duas vezes no mesmo canal e pior que um
corte nao publicado. Aqui, ao contrario do `job_registry`, o erro sobe.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import db
import db_models
import publishers


class FilaError(RuntimeError):
    """Erro que o painel mostra como texto: conta inexistente, corte sem
    arquivo, publicacao repetida."""


# --------------------------------------------------------------------------- #
# Contas
# --------------------------------------------------------------------------- #

def conta_para_driver(linha) -> publishers.Account:
    """A linha de `accounts` na forma que os drivers leem."""
    return publishers.Account(
        id=linha.id, platform=linha.platform, handle=linha.handle,
        credentials_ref=linha.credentials_ref, driver_pref=linha.driver_pref)


def _conta_json(linha, canal_id: Optional[str] = None) -> dict:
    conta = conta_para_driver(linha)
    return {
        "id": linha.id,
        "platform": linha.platform,
        "handle": linha.handle,
        "driver_pref": linha.driver_pref,
        # O endereco do cofre, nunca o segredo. Ver `db_models.vault_ref`.
        "credentials_ref": linha.credentials_ref,
        "driver_agora": publishers.resolve(linha.platform, conta).id,
        "capabilities": publishers.capabilities_de(conta),
        # O canal a que a conta pertence (Fase 7), ou None se esta solta.
        "channel_id": canal_id,
    }


async def listar_contas() -> list:
    async with db.tenant() as t:
        linhas = await t.all(db_models.Account)
        canal_de = {l.account_id: l.channel_id
                    for l in await t.all(db_models.ChannelAccount)}
    return [_conta_json(l, canal_de.get(l.id)) for l in linhas]


PLATAFORMAS = ("youtube", "tiktok", "instagram")


def validar_conta(platform: str, handle: str, driver_pref: str = "auto",
                  credentials_ref: Optional[str] = None) -> None:
    """As regras de uma conta nova, num lugar so: quem cria conta pela fila e
    quem cria pelo canal (`canais.py`) recusam exatamente as mesmas coisas."""
    if platform not in PLATAFORMAS:
        raise FilaError(f"plataforma desconhecida: {platform}")
    if driver_pref not in db_models.DRIVER_PREFS:
        raise FilaError(f"preferencia de driver desconhecida: {driver_pref}")
    if not (handle or "").strip():
        raise FilaError("a conta precisa de um handle")
    if credentials_ref:
        # Valida na criacao, e nao na hora de publicar: um endereco torto
        # descoberto no meio de um lote e um corte que nao subiu por um erro de
        # digitacao feito dias antes.
        import vault
        try:
            vault.partes(credentials_ref)
        except vault.VaultError as e:
            raise FilaError(str(e))


async def acrescentar_conta(t, platform: str, handle: str, driver_pref: str = "auto",
                            credentials_ref: Optional[str] = None):
    """Valida e acrescenta a conta DENTRO da sessao de quem chama, sem commit:
    o canal cria as contas dele e as ligacoes na mesma transacao."""
    validar_conta(platform, handle, driver_pref, credentials_ref)
    existentes = await t.all(db_models.Account,
                             db_models.Account.platform == platform,
                             db_models.Account.handle == handle.strip())
    if existentes:
        raise FilaError(f"ja existe uma conta {platform}/{handle}")
    return t.add(db_models.Account(
        platform=platform, handle=handle.strip(), driver_pref=driver_pref,
        credentials_ref=credentials_ref or db_models.vault_ref(
            "env", platform, handle.strip())))


async def criar_conta(platform: str, handle: str, driver_pref: str = "auto",
                      credentials_ref: Optional[str] = None) -> dict:
    async with db.tenant() as t:
        linha = await acrescentar_conta(t, platform, handle, driver_pref, credentials_ref)
        await t.commit()
        return _conta_json(linha)


async def apagar_conta(account_id: str) -> Optional[dict]:
    """Apaga a conta e devolve o que foi junto, ou None se nao existia.

    A FK de `publications` e `ON DELETE CASCADE` (secao 7), entao apagar uma
    conta leva o historico de publicacao dela. Isso e o desenho, mas quem clica
    precisa saber: o numero volta na resposta para o painel poder perguntar
    antes, como ja faz ao apagar um projeto (que leva os cortes junto).
    """
    async with db.tenant() as t:
        linha = await t.get(db_models.Account, account_id)
        if linha is None:
            return None
        publicacoes = await t.all(
            db_models.Publication,
            db_models.Publication.account_id == account_id)
        resumo = {"handle": linha.handle, "platform": linha.platform,
                  "publicacoes_apagadas": len(publicacoes)}
        await t.session.delete(linha)
        await t.commit()
        return resumo


# --------------------------------------------------------------------------- #
# Publicar
# --------------------------------------------------------------------------- #

async def publicar(clip_row, account_row, caminho_do_arquivo: str,
                   meta: publishers.PostMeta,
                   opts: Optional[publishers.PublishOptions] = None) -> dict:
    """Publica um corte numa conta e devolve a linha de `publications`.

    O driver sai de `publishers.resolve`, que so devolve driver de risco zero
    (ADR-010). O chamador nao escolhe.
    """
    opts = opts or publishers.PublishOptions()
    conta = conta_para_driver(account_row)
    driver = publishers.resolve(account_row.platform, conta)

    async with db.tenant() as t:
        repetida = await t.all(
            db_models.Publication,
            db_models.Publication.clip_id == clip_row.id,
            db_models.Publication.account_id == account_row.id)
        if repetida:
            anterior = repetida[0]
            raise FilaError(
                f"este corte ja foi para {account_row.platform}/"
                f"{account_row.handle} (status: {anterior.status})")
        linha = t.add(db_models.Publication(
            clip_id=clip_row.id, account_id=account_row.id,
            driver=driver.id, status="publishing",
            scheduled_at=None))
        await t.commit()
        pub_id = linha.id

    clip = publishers.RenderedClip(
        path=caminho_do_arquivo,
        job_id=clip_row.job_id,
        index=int((clip_row.rubric_json or {}).get("clip_index") or 0),
        title=meta.title,
        clip_id=clip_row.id)

    try:
        # `publish()` e sincrono de proposito (ADR-010) e sobe um arquivo pela
        # rede. Roda-lo no loop travaria o polling de todo mundo durante o
        # upload; o executor e o mesmo recurso que o ZIP do pacote usa.
        #
        # E so ELE vai para a thread: o resto desta funcao fala com o banco, e
        # o engine async esta preso ao loop que o criou -- um `asyncio.run`
        # dentro da thread criaria um segundo loop e a conexao pertenceria ao
        # errado.
        resultado = await asyncio.get_event_loop().run_in_executor(
            None, driver.publish, clip, meta, opts, conta)
    except publishers.PublisherError as e:
        await _fechar(pub_id, status="failed")
        raise FilaError(str(e))
    except Exception as e:
        await _fechar(pub_id, status="failed")
        raise FilaError(f"{type(e).__name__}: {e}")

    await _fechar(pub_id, status=resultado.status,
                  remote_id=resultado.remote_id)
    return {
        "id": pub_id,
        "driver": driver.id,
        "status": resultado.status,
        "ok": resultado.ok,
        "remote_id": resultado.remote_id,
        "url": resultado.url,
        "detail": resultado.detail,
        "artifacts": list(resultado.artifacts),
    }


# --------------------------------------------------------------------------- #
# Agendar (Fase 4, bloco 4.4)
# --------------------------------------------------------------------------- #

async def agendar(clip_row, account_row, quando) -> dict:
    """Enfileira um corte para publicar mais tarde, em vez de agora.

    A linha nasce `scheduled` com `scheduled_at` preenchido -- que e a coluna
    que a secao 7 poe ali exatamente para isto. **`scheduled_at` nulo continua
    significando "fila manual"**: o driver `manual` termina em `scheduled` sem
    data porque espera uma pessoa, e nao um horario. Duas esperas diferentes no
    mesmo status, distinguidas pela data, sem inventar um status novo.
    """
    async with db.tenant() as t:
        repetida = await t.all(
            db_models.Publication,
            db_models.Publication.clip_id == clip_row.id,
            db_models.Publication.account_id == account_row.id)
        if repetida:
            raise FilaError(
                f"este corte ja esta na fila para {account_row.platform}/"
                f"{account_row.handle} (status: {repetida[0].status})")
        conta = conta_para_driver(account_row)
        driver = publishers.resolve(account_row.platform, conta)
        linha = t.add(db_models.Publication(
            clip_id=clip_row.id, account_id=account_row.id,
            driver=driver.id, status="scheduled", scheduled_at=quando))
        await t.commit()
        return {"id": linha.id, "driver": driver.id,
                "scheduled_at": quando.isoformat()}


async def devidas(agora) -> list:
    """As publicacoes agendadas cuja hora chegou, da mais antiga para a mais
    nova.

    **Atravessa os tenants de proposito** (`db.session`, nao `db.tenant()`): o
    laco e do servidor, nao de uma requisicao, e nao ha sessao de onde tirar um
    escopo. Quem devolve cada linha ao tenant dela e o chamador, antes de
    publicar -- e e por isso que o `tenant_id` volta junto.
    """
    from sqlalchemy import select as _select
    async with db.session() as s:
        achadas = await s.execute(
            _select(db_models.Publication)
            .where(db_models.Publication.status == "scheduled")
            .where(db_models.Publication.scheduled_at.is_not(None))
            .where(db_models.Publication.scheduled_at <= agora)
            .order_by(db_models.Publication.scheduled_at))
        return [{"id": p.id, "tenant_id": p.tenant_id, "clip_id": p.clip_id,
                 "account_id": p.account_id, "driver": p.driver}
                for p in achadas.scalars().all()]


async def reservar(pub_id: str) -> bool:
    """Marca a publicacao como `publishing` **so se ainda estava `scheduled`**.

    E um UPDATE condicional, e nao um leia-e-escreva, porque durante um deploy
    ha DUAS instancias com o mesmo banco e o mesmo laco. Quem conseguir mudar a
    linha publica; a outra recebe zero linhas afetadas e segue. Sem isto o mesmo
    corte subiria duas vezes -- e a unicidade `(corte, conta)` nao pega esse
    caso, porque a linha e a mesma.
    """
    from sqlalchemy import update as _update
    async with db.session() as s:
        r = await s.execute(
            _update(db_models.Publication)
            .where(db_models.Publication.id == pub_id)
            .where(db_models.Publication.status == "scheduled")
            .values(status="publishing"))
        await s.commit()
        return (r.rowcount or 0) > 0


async def publicar_reservada(pub_id: str, clip_row, account_row,
                             caminho_do_arquivo: str,
                             meta: publishers.PostMeta,
                             opts: Optional[publishers.PublishOptions] = None) -> dict:
    """Executa uma publicacao que `reservar()` ja marcou como `publishing`.

    Nao cria linha nem confere repeticao: as duas coisas aconteceram no
    `agendar()`, dias antes. O que resta e chamar o driver e fechar a linha.
    """
    opts = opts or publishers.PublishOptions()
    conta = conta_para_driver(account_row)
    driver = publishers.resolve(account_row.platform, conta)
    clip = publishers.RenderedClip(
        path=caminho_do_arquivo, job_id=clip_row.job_id,
        index=int((clip_row.rubric_json or {}).get("clip_index") or 0),
        title=meta.title, clip_id=clip_row.id)
    try:
        resultado = await asyncio.get_event_loop().run_in_executor(
            None, driver.publish, clip, meta, opts, conta)
    except publishers.PublisherError as e:
        await _fechar(pub_id, status="failed")
        raise FilaError(str(e))
    except Exception as e:
        await _fechar(pub_id, status="failed")
        raise FilaError(f"{type(e).__name__}: {e}")
    await _fechar(pub_id, status=resultado.status,
                  remote_id=resultado.remote_id)
    return {"id": pub_id, "driver": driver.id, "status": resultado.status,
            "ok": resultado.ok, "url": resultado.url, "detail": resultado.detail}


async def _fechar(pub_id: str, status: str,
                  remote_id: Optional[str] = None) -> None:
    async with db.tenant() as t:
        linha = await t.get(db_models.Publication, pub_id)
        if linha is None:
            return
        linha.status = status if status in db_models.PUB_STATUSES else "failed"
        if remote_id:
            linha.remote_id = remote_id
        await t.commit()


async def marcar_publicado(pub_id: str, remote_id: Optional[str] = None) -> bool:
    """O botao "ja publiquei" da fila manual.

    O driver `manual` termina em `scheduled` porque nao tem como saber que a
    pessoa apertou publicar. Este e o unico caminho que move a linha para
    `published`, e ele e humano de proposito.
    """
    async with db.tenant() as t:
        linha = await t.get(db_models.Publication, pub_id)
        if linha is None:
            return False
        linha.status = "published"
        if remote_id:
            linha.remote_id = remote_id
        await t.commit()
        return True


async def cancelar(pub_id: str) -> bool:
    async with db.tenant() as t:
        linha = await t.get(db_models.Publication, pub_id)
        if linha is None:
            return False
        if linha.status == "published":
            raise FilaError("o que ja foi publicado nao volta para a fila; "
                            "apague o post na plataforma")
        linha.status = "cancelled"
        await t.commit()
        return True


# --------------------------------------------------------------------------- #
# Metricas (Fase 5)
# --------------------------------------------------------------------------- #

async def publicadas_com_remote_id() -> list:
    """As publicacoes que existem na plataforma e podem ser medidas.

    **Atravessa os tenants** (`db.session`), como `devidas()`: o coletor e do
    servidor e nao tem sessao de onde tirar escopo. O `tenant_id` volta junto
    para quem chamar devolver cada linha ao tenant dela antes de gravar.

    So `published` e so com `remote_id`: uma linha na fila manual nao tem video
    do outro lado para medir, e medir o que nao foi publicado registraria zero
    views como se fosse resultado.
    """
    from sqlalchemy import select as _select
    async with db.session() as s:
        achadas = await s.execute(
            _select(db_models.Publication)
            .where(db_models.Publication.status == "published")
            .where(db_models.Publication.remote_id.is_not(None)))
        return [{"id": p.id, "tenant_id": p.tenant_id, "driver": p.driver,
                 "remote_id": p.remote_id, "account_id": p.account_id}
                for p in achadas.scalars().all()]


async def gravar_metrica(publication_id: str, views=None,
                         retention_pct=None) -> Optional[str]:
    """Acrescenta uma leitura. **Nunca atualiza a anterior.**

    `metrics` e serie temporal, nao cache: retencao matura em dias, e o valor de
    24 h depois e uma informacao diferente do de uma semana depois. A secao 7 poe
    `collected_at` na tabela e NAO poe unicidade por publicacao exatamente por
    isso -- sobrescrever jogaria fora a unica dimensao que torna a tabela util.

    Uma leitura sem nenhum numero nao vira linha: ela nao diz nada e sujaria a
    media com uma amostra vazia.
    """
    if views is None and retention_pct is None:
        return None
    async with db.tenant() as t:
        linha = t.add(db_models.Metric(publication_id=publication_id,
                                       views=views, retention_pct=retention_pct))
        await t.commit()
        return linha.id


async def cruzamento() -> list:
    """Um item por corte PUBLICADO e medido: o que o modelo previu e o que deu.

    Junta `clips` (score e rubrica), `publications` (o elo) e `metrics` (o
    resultado). Tres tabelas, uma volta ao banco cada -- e nao uma consulta por
    corte, que com algumas centenas de cortes seria o relatorio inteiro travando
    o loop.

    **Vale a leitura MAIS RECENTE de cada publicacao**, porque `metrics` e serie
    temporal: somar todas as leituras contaria o mesmo video uma vez por coleta
    e daria peso maior ao que foi publicado ha mais tempo.
    """
    async with db.tenant() as t:
        publicacoes = await t.all(db_models.Publication)
        cortes = {c.id: c for c in await t.all(db_models.Clip)}
        leituras = await t.all(db_models.Metric)

    recente: dict = {}
    for m in leituras:
        atual = recente.get(m.publication_id)
        if atual is None or (m.collected_at and atual.collected_at
                             and m.collected_at > atual.collected_at):
            recente[m.publication_id] = m

    saida = []
    for pub in publicacoes:
        corte = cortes.get(pub.clip_id)
        if corte is None:
            continue
        medida = recente.get(pub.id)
        rubrica = corte.rubric_json or {}
        saida.append({
            "publication_id": pub.id,
            "clip_id": corte.id,
            "job_id": corte.job_id,
            "titulo": rubrica.get("video_title_for_youtube_short"),
            "score": corte.score,
            "visual": rubrica.get("visual"),
            "status": pub.status,
            "views": medida.views if medida else None,
            "retention_pct": medida.retention_pct if medida else None,
            "medido_em": (medida.collected_at.isoformat()
                          if medida and medida.collected_at else None),
        })
    return saida


async def historico(publication_id: Optional[str] = None) -> list:
    """As leituras, da mais recente para a mais antiga."""
    async with db.tenant() as t:
        if publication_id:
            linhas = await t.all(
                db_models.Metric,
                db_models.Metric.publication_id == publication_id)
        else:
            linhas = await t.all(db_models.Metric)
    saida = [{"id": m.id, "publication_id": m.publication_id, "views": m.views,
              "retention_pct": m.retention_pct,
              "collected_at": m.collected_at.isoformat() if m.collected_at else None}
             for m in linhas]
    saida.sort(key=lambda m: m.get("collected_at") or "", reverse=True)
    return saida


# --------------------------------------------------------------------------- #
# Listar
# --------------------------------------------------------------------------- #

async def listar(status: Optional[str] = None) -> list:
    """As publicacoes, da mais recente para a mais antiga.

    Junta o corte e a conta na mesma linha porque e sempre assim que o painel
    vai desenhar -- tres consultas separadas para montar uma lista seriam tres
    idas ao banco por render.
    """
    async with db.tenant() as t:
        linhas = await t.all(db_models.Publication)
        cortes = {c.id: c for c in await t.all(db_models.Clip)}
        contas = {a.id: a for a in await t.all(db_models.Account)}

    saida = []
    for linha in linhas:
        if status and linha.status != status:
            continue
        corte = cortes.get(linha.clip_id)
        conta = contas.get(linha.account_id)
        rubrica = (corte.rubric_json or {}) if corte else {}
        saida.append({
            "id": linha.id,
            "status": linha.status,
            "driver": linha.driver,
            "remote_id": linha.remote_id,
            "created_at": linha.created_at.isoformat() if linha.created_at else None,
            # Nulo aqui significa "fila manual, esperando uma pessoa"; com data,
            # "agendada, esperando a hora". Ver `agendar()`.
            "scheduled_at": (linha.scheduled_at.isoformat()
                             if linha.scheduled_at else None),
            "clip": {
                "id": linha.clip_id,
                "job_id": corte.job_id if corte else None,
                "index": rubrica.get("clip_index"),
                "title": rubrica.get("video_title_for_youtube_short"),
                "score": corte.score if corte else None,
                "render_key": corte.render_key if corte else None,
            },
            "account": {
                "id": linha.account_id,
                "platform": conta.platform if conta else None,
                "handle": conta.handle if conta else None,
            },
        })
    saida.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return saida
