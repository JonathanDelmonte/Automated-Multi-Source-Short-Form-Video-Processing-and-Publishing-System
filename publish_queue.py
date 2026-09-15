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


def _conta_json(linha) -> dict:
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
    }


async def listar_contas() -> list:
    async with db.tenant() as t:
        linhas = await t.all(db_models.Account)
    return [_conta_json(l) for l in linhas]


async def criar_conta(platform: str, handle: str, driver_pref: str = "auto",
                      credentials_ref: Optional[str] = None) -> dict:
    if platform not in ("youtube", "tiktok", "instagram"):
        raise FilaError(f"plataforma desconhecida: {platform}")
    if driver_pref not in db_models.DRIVER_PREFS:
        raise FilaError(f"preferencia de driver desconhecida: {driver_pref}")
    if not (handle or "").strip():
        raise FilaError("a conta precisa de um handle")
    async with db.tenant() as t:
        existentes = await t.all(db_models.Account,
                                 db_models.Account.platform == platform,
                                 db_models.Account.handle == handle.strip())
        if existentes:
            raise FilaError(f"ja existe uma conta {platform}/{handle}")
        linha = t.add(db_models.Account(
            platform=platform, handle=handle.strip(), driver_pref=driver_pref,
            credentials_ref=credentials_ref or db_models.vault_ref(
                "env", platform, handle.strip())))
        await t.commit()
        return _conta_json(linha)


async def apagar_conta(account_id: str) -> bool:
    async with db.tenant() as t:
        linha = await t.get(db_models.Account, account_id)
        if linha is None:
            return False
        await t.session.delete(linha)
        await t.commit()
        return True


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
