"""canais e as suas ligacoes: channels, channel_accounts, channel_jobs

A Fase 7 poe o CANAL no centro (docs/PLANO-DA-PLATAFORMA.md): uma marca num
nicho, com as contas de cada plataforma ligadas a ela, e os projetos feitos para
ela.

**Tabelas novas, e nenhuma coluna em tabela que ja existe, de proposito.** O
motor cria o banco no boot com `create_all`, e ninguem roda esta migracao na
maquina de quem usa. O `create_all` cria tabela que falta, mas nunca acrescenta
coluna: um `accounts.channel_id` nao chegaria ao banco do autor, e a primeira
consulta que o lesse quebraria. Com a ligacao em tabela propria, o boot e esta
migracao chegam ao mesmo schema -- que e o que o
`test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata` confere.

Revision ID: b3d8f1a6c2e4
Revises: 7e3a9c4d15f8
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3d8f1a6c2e4'
down_revision: Union[str, Sequence[str], None] = '7e3a9c4d15f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _criado_em() -> sa.Column:
    return sa.Column('created_at', sa.DateTime(timezone=True),
                     server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False)


def upgrade() -> None:
    op.create_table('channels',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('niche', sa.String(length=80), nullable=True),
    sa.Column('avatar', sa.Text(), nullable=True),
    sa.Column('color', sa.String(length=16), nullable=True),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('requires_approval', sa.Boolean(), nullable=False),
    _criado_em(),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_channels_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_channels_tenant_name')
    )
    with op.batch_alter_table('channels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channels_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_channels_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('channel_accounts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    _criado_em(),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_channel_accounts_tenant', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_channel_accounts_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'account_id'], ['accounts.tenant_id', 'accounts.id'], name='fk_channel_accounts_account', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'account_id', name='uq_channel_accounts_tenant_account')
    )
    with op.batch_alter_table('channel_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channel_accounts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_channel_accounts_tenant_id_id', ['tenant_id', 'id'], unique=True)
        batch_op.create_index('ix_channel_accounts_tenant_channel', ['tenant_id', 'channel_id'], unique=False)

    op.create_table('channel_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    _criado_em(),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_channel_jobs_tenant', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_channel_jobs_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'job_id'], ['jobs.tenant_id', 'jobs.id'], name='fk_channel_jobs_job', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'job_id', name='uq_channel_jobs_tenant_job')
    )
    with op.batch_alter_table('channel_jobs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channel_jobs_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_channel_jobs_tenant_id_id', ['tenant_id', 'id'], unique=True)
        batch_op.create_index('ix_channel_jobs_tenant_channel', ['tenant_id', 'channel_id'], unique=False)


def downgrade() -> None:
    for tabela in ('channel_jobs', 'channel_accounts'):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{tabela}_tenant_channel')
            batch_op.drop_index(f'ix_{tabela}_tenant_id_id')
            batch_op.drop_index(batch_op.f(f'ix_{tabela}_tenant_id'))
        op.drop_table(tabela)
    with op.batch_alter_table('channels', schema=None) as batch_op:
        batch_op.drop_index('ix_channels_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_channels_tenant_id'))
    op.drop_table('channels')
