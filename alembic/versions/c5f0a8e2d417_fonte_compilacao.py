"""a fonte `compilacao`: o video longo feito dos cortes

Etapa 7.8 (docs/PLANO-DA-PLATAFORMA.md): a compilacao horizontal dos cortes de
outros projetos e um job como os outros, e todo job no banco tem uma fonte. A
dela nao e um video nem uma ideia: sao os cortes escolhidos, e o `input` diz
quantos e de onde.

E uma regra que MUDA numa tabela que existe: `sources.adapter` passa a aceitar
`compilacao`. Num banco que ja existe na maquina de quem usa, quem troca a
regra no boot e o `db_acerto`; aqui e o caminho do `alembic upgrade`, pelo
batch do SQLite, como a `b8d4f1a2c9e3` (a que trouxe o `ia`).

Revision ID: c5f0a8e2d417
Revises: b8d4f1a2c9e3
Create Date: 2026-09-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5f0a8e2d417'
down_revision: Union[str, Sequence[str], None] = 'b8d4f1a2c9e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ADAPTER_ANTES = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                  "'twitch-live','gdrive','upload','direct','ia')")
_ADAPTER_DEPOIS = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                   "'twitch-live','gdrive','upload','direct','ia','compilacao')")


def _sources(check_adapter: str) -> sa.Table:
    """`sources` como ela esta antes desta migracao, repetida pelo motivo da
    `b8d4f1a2c9e3`: o batch do SQLite recria a tabela a partir deste objeto."""
    return sa.Table(
        'sources', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('adapter', sa.String(length=32), nullable=False),
        sa.Column('input', sa.Text(), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(check_adapter, name='ck_sources_adapter'),
        sa.CheckConstraint('duration_ms is null or duration_ms >= 0',
                           name='ck_sources_duration_nao_negativa'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_sources_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_sources_tenant_id', 'tenant_id'),
        sa.Index('ix_sources_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def _troca_do_adapter(de: str, para: str) -> None:
    with op.batch_alter_table('sources', copy_from=_sources(de)) as batch_op:
        batch_op.drop_constraint('ck_sources_adapter', type_='check')
        batch_op.create_check_constraint('ck_sources_adapter', para)


def upgrade() -> None:
    _troca_do_adapter(_ADAPTER_ANTES, _ADAPTER_DEPOIS)


def downgrade() -> None:
    _troca_do_adapter(_ADAPTER_DEPOIS, _ADAPTER_ANTES)
