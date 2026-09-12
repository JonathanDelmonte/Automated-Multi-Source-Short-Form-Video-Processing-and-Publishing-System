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
from db_models import Template, Tenant, User

#: O template da secao 5, palavra por palavra. Fica aqui e nao num JSON solto
#: porque o seed precisa dele para criar a versao 1, e duplicar o arquivo
#: garantiria divergencia. `safeArea` nao e enfeite: o TikTok cobre 12% em cima
#: e 18% embaixo, e legenda fora dessa faixa e o erro no 1 de quem automatiza.
TEMPLATE_PADRAO = {
    "name": "Padrão Cortes v3",
    "aspect": "9:16",
    "hook": {"mode": "text_punch", "durationMs": 1200, "font": "Anton",
             "from": "clip.title"},
    "captions": {"preset": "karaoke_fill", "font": "Anton", "sizePt": 84,
                 "yAnchor": 0.72, "highlight": "#FFD400", "strokePx": 6,
                 "maxWords": 3},
    "overlays": [
        {"asset": "logo.png", "anchor": "top-right", "marginPx": 48, "opacity": 0.9},
        {"asset": "endcard.mp4", "anchor": "full", "atEnd": True, "durationMs": 2000},
    ],
    "audio": {"bgm": "lofi_01.mp3", "gainDb": -22, "ducking": "sidechain"},
    "cuts": {"removeSilence": True, "thresholdDb": -35, "maxGapMs": 400},
    "safeArea": {"topPct": 12, "bottomPct": 18},
}

SEED_EMAIL = "self-host@localhost"


async def seed(*, with_ddl: bool = True) -> dict:
    """Garante tenant, usuario dono e template v1. Devolve o que encontrou/criou."""
    if with_ddl:
        await db.create_all()

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


def main(argv: list[str]) -> int:
    with_ddl = "--no-ddl" not in argv
    criado = asyncio.run(seed(with_ddl=with_ddl))
    print(f"banco: {db.database_url()}")
    for chave, novo in criado.items():
        print(f"   {chave:<10} {'criado' if novo else 'já existia'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
