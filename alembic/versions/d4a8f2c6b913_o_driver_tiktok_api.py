"""o driver tiktok-api: publications.driver e accounts.driver_pref aceitam

Etapa 7.3 (docs/PLANO-DA-PLATAFORMA.md): o TikTok passa a publicar pela API
oficial (Content Posting API), e os dois CHECKs que listam drivers ganham o id
novo. Um banco criado pelo `create_all` antes disto recebe a mesma regra pelo
`db_acerto` no boot; esta migracao e o caminho de producao.

As tabelas sao repetidas aqui, e nao importadas de `db_models`: uma migracao
descreve o banco COMO ELE ESTAVA, e o batch do SQLite recria a tabela a partir
deste objeto -- o que nao estiver aqui (os indices UNIQUE que as FKs compostas
referenciam) seria apagado.

Revision ID: d4a8f2c6b913
Revises: c7e2a9d41f06
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4a8f2c6b913'
down_revision: Union[str, Sequence[str], None] = 'c7e2a9d41f06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A grafia de cada CHECK e a da sua migracao inicial: o
# `test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata` compara o TEXTO.
_DRIVER_ANTES = "driver in ('manual', 'youtube-api', 'aggregator', 'browser')"
_DRIVER_DEPOIS = "driver in ('manual', 'youtube-api', 'aggregator', 'browser', 'tiktok-api')"
_PREF_ANTES = "driver_pref in ('auto','manual','youtube-api','aggregator','browser')"
_PREF_DEPOIS = ("driver_pref in ('auto','manual','youtube-api','aggregator',"
                "'browser','tiktok-api')")


def _criado_em() -> sa.Column:
    return sa.Column('created_at', sa.DateTime(timezone=True),
                     server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False)


def _publicacoes(check_driver: str) -> sa.Table:
    return sa.Table(
        'publications', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('clip_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('driver', sa.String(length=32), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('remote_id', sa.String(length=255), nullable=True),
        _criado_em(),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(check_driver, name='ck_publications_driver'),
        sa.CheckConstraint("status in ('scheduled', 'publishing', 'published', "
                           "'failed', 'cancelled')", name='ck_publications_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'account_id'],
                                ['accounts.tenant_id', 'accounts.id'],
                                name='fk_publications_account', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'clip_id'], ['clips.tenant_id', 'clips.id'],
                                name='fk_publications_clip', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_publications_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'clip_id', 'account_id',
                            name='uq_publications_tenant_clip_account'),
        sa.Index('ix_publications_tenant_id', 'tenant_id'),
        sa.Index('ix_publications_tenant_id_id', 'tenant_id', 'id', unique=True),
        sa.Index('ix_publications_tenant_status_scheduled',
                 'tenant_id', 'status', 'scheduled_at'),
    )


def _contas(check_pref: str) -> sa.Table:
    return sa.Table(
        'accounts', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('handle', sa.String(length=255), nullable=False),
        sa.Column('credentials_ref', sa.String(length=512), nullable=True),
        sa.Column('driver_pref', sa.String(length=32), nullable=False,
                  server_default=sa.text("'auto'")),
        _criado_em(),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint("platform in ('youtube','tiktok','instagram')",
                           name='ck_accounts_platform'),
        sa.CheckConstraint(check_pref, name='ck_accounts_driver_pref'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_accounts_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'handle',
                            name='uq_accounts_tenant_platform_handle'),
        sa.Index('ix_accounts_tenant_id', 'tenant_id'),
        sa.Index('ix_accounts_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def upgrade() -> None:
    with op.batch_alter_table('publications',
                              copy_from=_publicacoes(_DRIVER_ANTES)) as batch_op:
        batch_op.drop_constraint('ck_publications_driver', type_='check')
        batch_op.create_check_constraint('ck_publications_driver', _DRIVER_DEPOIS)
    with op.batch_alter_table('accounts', copy_from=_contas(_PREF_ANTES)) as batch_op:
        batch_op.drop_constraint('ck_accounts_driver_pref', type_='check')
        batch_op.create_check_constraint('ck_accounts_driver_pref', _PREF_DEPOIS)


def downgrade() -> None:
    # Voltar o CHECK sem tirar o que ja usa o id novo deixaria linha invalida.
    op.execute("update accounts set driver_pref = 'auto' where driver_pref = 'tiktok-api'")
    op.execute("update publications set driver = 'manual' where driver = 'tiktok-api'")
    with op.batch_alter_table('accounts', copy_from=_contas(_PREF_DEPOIS)) as batch_op:
        batch_op.drop_constraint('ck_accounts_driver_pref', type_='check')
        batch_op.create_check_constraint('ck_accounts_driver_pref', _PREF_ANTES)
    with op.batch_alter_table('publications',
                              copy_from=_publicacoes(_DRIVER_DEPOIS)) as batch_op:
        batch_op.drop_constraint('ck_publications_driver', type_='check')
        batch_op.create_check_constraint('ck_publications_driver', _DRIVER_ANTES)
