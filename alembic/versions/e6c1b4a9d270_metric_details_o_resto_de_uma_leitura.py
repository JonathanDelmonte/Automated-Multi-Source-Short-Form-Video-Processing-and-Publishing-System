"""metric_details: curtidas, comentarios, compartilhamentos e o resto de uma leitura

Etapa 7.4 (docs/PLANO-DA-PLATAFORMA.md). `metrics` nasceu com views e retencao,
que e o que o YouTube da e o que a calibracao cruza. O TikTok e o Instagram
medem por engajamento -- e o TikTok nem tem retencao --, e as analises por canal
mostram esses numeros.

Tabela nova, e nao colunas em `metrics`, pela regra da Fase 7: o `create_all`
do boot nao acrescenta coluna a tabela que ja existe.

Revision ID: e6c1b4a9d270
Revises: d4a8f2c6b913
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e6c1b4a9d270'
down_revision: Union[str, Sequence[str], None] = 'd4a8f2c6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('metric_details',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('metric_id', sa.String(length=36), nullable=False),
    sa.Column('likes', sa.Integer(), nullable=True),
    sa.Column('comments', sa.Integer(), nullable=True),
    sa.Column('shares', sa.Integer(), nullable=True),
    sa.Column('saves', sa.Integer(), nullable=True),
    sa.Column('avg_watch_s', sa.Float(), nullable=True),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint('avg_watch_s is null or avg_watch_s >= 0', name='ck_metric_details_avg_watch'),
    sa.CheckConstraint('comments is null or comments >= 0', name='ck_metric_details_comments'),
    sa.CheckConstraint('likes is null or likes >= 0', name='ck_metric_details_likes'),
    sa.CheckConstraint('saves is null or saves >= 0', name='ck_metric_details_saves'),
    sa.CheckConstraint('shares is null or shares >= 0', name='ck_metric_details_shares'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_metric_details_tenant', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'metric_id'], ['metrics.tenant_id', 'metrics.id'], name='fk_metric_details_metric', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'metric_id', name='uq_metric_details_tenant_metric')
    )
    with op.batch_alter_table('metric_details', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_metric_details_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_metric_details_tenant_id_id', ['tenant_id', 'id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('metric_details', schema=None) as batch_op:
        batch_op.drop_index('ix_metric_details_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_metric_details_tenant_id'))
    op.drop_table('metric_details')
