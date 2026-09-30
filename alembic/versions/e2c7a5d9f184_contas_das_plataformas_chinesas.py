"""contas das plataformas chinesas: accounts.platform aceita as quatro

Etapa 7.10 (docs/PLANO-DA-PLATAFORMA.md, ADR-015): Douyin, Kuaishou, Bilibili e
Xiaohongshu entram como plataformas de conta, publicadas pela fila manual (o
pacote do dia com o texto em chines e o "ja publiquei" com o link).

E uma regra que MUDA numa tabela que existe. Num banco que ja existe na maquina
de quem usa, quem troca a regra no boot e o `db_acerto`; aqui e o caminho do
`alembic upgrade`, pelo batch do SQLite, como a `d4a8f2c6b913` (o driver do
TikTok, no CHECK vizinho desta mesma tabela).

Revision ID: e2c7a5d9f184
Revises: c5f0a8e2d417
Create Date: 2026-09-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e2c7a5d9f184'
down_revision: Union[str, Sequence[str], None] = 'c5f0a8e2d417'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A grafia de cada CHECK e a do `db_models` (sem espaco depois da virgula): o
# `test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata` compara o TEXTO.
_PLATAFORMA_ANTES = "platform in ('youtube','tiktok','instagram')"
_PLATAFORMA_DEPOIS = ("platform in ('youtube','tiktok','instagram','douyin',"
                      "'kuaishou','bilibili','xiaohongshu')")
_PREF = ("driver_pref in ('auto','manual','youtube-api','aggregator',"
         "'browser','tiktok-api')")


def _contas(check_plataforma: str) -> sa.Table:
    """`accounts` como ela esta antes desta migracao, repetida pelo motivo da
    `d4a8f2c6b913`: o batch do SQLite recria a tabela a partir deste objeto, e
    o que nao estiver aqui (os indices UNIQUE que as FKs compostas referenciam)
    seria apagado."""
    return sa.Table(
        'accounts', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('handle', sa.String(length=255), nullable=False),
        sa.Column('credentials_ref', sa.String(length=512), nullable=True),
        sa.Column('driver_pref', sa.String(length=32), nullable=False,
                  server_default=sa.text("'auto'")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(check_plataforma, name='ck_accounts_platform'),
        sa.CheckConstraint(_PREF, name='ck_accounts_driver_pref'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_accounts_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'handle',
                            name='uq_accounts_tenant_platform_handle'),
        sa.Index('ix_accounts_tenant_id', 'tenant_id'),
        sa.Index('ix_accounts_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def _troca_da_plataforma(de: str, para: str) -> None:
    with op.batch_alter_table('accounts', copy_from=_contas(de)) as batch_op:
        batch_op.drop_constraint('ck_accounts_platform', type_='check')
        batch_op.create_check_constraint('ck_accounts_platform', para)


def upgrade() -> None:
    _troca_da_plataforma(_PLATAFORMA_ANTES, _PLATAFORMA_DEPOIS)


def downgrade() -> None:
    # Voltar o CHECK com uma conta chinesa na tabela deixaria linha invalida, e
    # apaga-la levaria o historico de publicacao dela. Quem volta decide: a
    # migracao recusa e diz o que apagar antes.
    contas = op.get_bind().execute(sa.text(
        "select count(*) from accounts where platform in "
        "('douyin','kuaishou','bilibili','xiaohongshu')")).scalar()
    if contas:
        raise RuntimeError(
            f"ha {contas} conta(s) de Douyin, Kuaishou, Bilibili ou Xiaohongshu; "
            "apague-as pelo painel antes de voltar esta migracao")
    _troca_da_plataforma(_PLATAFORMA_DEPOIS, _PLATAFORMA_ANTES)
