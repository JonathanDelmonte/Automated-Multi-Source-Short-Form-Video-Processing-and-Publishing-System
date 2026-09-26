"""Seed do schema: o tenant fixo do self-host e o template padrao.

A secao 7 do Plano Tecnico pede "um tenant fixo no seed". Fixo importa: um
UUID sorteado a cada execucao orfanaria toda linha ja gravada, entao o id vem
de `db.SELF_HOST_TENANT_ID`.

Idempotente de proposito -- roda no boot da API sem condicional, e rodar duas
vezes nao duplica nada.

Uso:
    python db_seed.py            # cria o schema (create_all) e semeia
    python db_seed.py --no-ddl   # so semeia, assumindo alembic ja aplicado
"""
from __future__ import annotations

import asyncio
import sys

import db
import db_acerto
import template
from db_models import Template, Tenant, User

#: O template semeado e o `template.PADRAO` -- uma fonte de verdade so, e nao
#: uma copia que diverge no primeiro campo novo.
#:
#: **Ele NAO e mais o exemplo da secao 5, e a troca foi deliberada** (bloco
#: 2.3). O exemplo de la referencia `logo.png`, `endcard.mp4` e `lofi_01.mp3`,
#: que nao existem, e liga `cuts.removeSilence`, que ninguem implementa ainda.
#: Como documentacao ele esta certo: mostra a forma do documento inteiro. Como
#: linha semeada num banco que o painel vai listar, ele seria um template que
#: promete o que nao faz -- e o usuario descobriria isso aplicando.
#:
#: O exemplo completo continua no `docs/PLANO-TECNICO.md`, secao 5, que e onde
#: exemplo deve morar.
TEMPLATE_PADRAO = template.PADRAO

SEED_EMAIL = "self-host@localhost"


async def seed(*, with_ddl: bool = True) -> dict:
    """Garante tenant, usuario dono e template v1. Devolve o que encontrou/criou."""
    if with_ddl:
        await db.create_all()
        # ANTES de semear: o seed consulta `users.password_hash`, que um banco
        # anterior a Fase 4 nao tem. Ver `db_acerto`.
        await acertar_tabelas_antigas()

    criado = {"tenant": False, "user": False, "template": False}
    async with db.tenant() as t:
        # O tenant nao passa pelo TenantScope: ele E o escopo.
        tenant_row = await t.session.get(Tenant, db.SELF_HOST_TENANT_ID)
        if tenant_row is None:
            t.session.add(Tenant(id=db.SELF_HOST_TENANT_ID, plan="self_host"))
            await t.flush()
            criado["tenant"] = True

        if not await t.all(User, User.email == SEED_EMAIL):
            t.add(User(email=SEED_EMAIL, role="owner"))
            criado["user"] = True

        nome = TEMPLATE_PADRAO["name"]
        if not await t.all(Template, Template.name == nome, Template.version == 1):
            t.add(Template(name=nome, spec_json=TEMPLATE_PADRAO, version=1))
            criado["template"] = True

        await t.commit()
    return criado


async def acertar_tabelas_antigas() -> dict:
    """Leva as tabelas de um SQLite que ja existia as regras do modelo.

    O `create_all` so cria o que falta; o `db_acerto` refaz o que ficou para
    tras. Numa thread, porque e `sqlite3` sincrono e roda no boot da API.
    """
    caminho = db_acerto.caminho_do_banco(db.database_url())
    if not caminho:
        return {}
    feito = await asyncio.to_thread(db_acerto.acertar, caminho)
    if feito.get("reconstruidas") or feito.get("indices"):
        # As conexoes do pool conheceram o schema de antes.
        await db.engine().dispose()
    return feito


def main(argv: list[str]) -> int:
    with_ddl = "--no-ddl" not in argv
    criado = asyncio.run(seed(with_ddl=with_ddl))
    print(f"banco: {db.database_url()}")
    for chave, novo in criado.items():
        print(f"   {chave:<10} {'criado' if novo else 'já existia'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
