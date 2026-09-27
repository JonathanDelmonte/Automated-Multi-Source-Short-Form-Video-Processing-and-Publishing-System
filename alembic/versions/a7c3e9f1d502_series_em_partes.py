"""series em partes: a serie, as partes, e a playlist do YouTube de cada uma

Etapa 7.6 (docs/PLANO-DA-PLATAFORMA.md): um video longo vira Parte 1, 2, 3...,
postadas em sequencia, e no YouTube uma playlist por serie. Quatro tabelas
novas e nenhuma coluna nova em tabela que ja existe -- a regra da Fase 7.

- `series`: a serie (nome, idioma, duracao das partes, quantas), do projeto
  que a cortou;
- `series_parts`: qual corte e qual parte. Um numero de parte existe uma vez
  por serie, e um corte e parte de uma serie so ("sem repeticao" tambem no
  banco);
- `series_playlists`: a playlist de uma serie numa conta do YouTube;
- `series_playlist_items`: as partes publicadas que ja entraram na playlist.

Revision ID: a7c3e9f1d502
Revises: f3a9c5e7b214
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7c3e9f1d502'
down_revision: Union[str, Sequence[str], None] = 'f3a9c5e7b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('series',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('part_seconds', sa.Float(), nullable=False),
    sa.Column('total_parts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint('part_seconds > 0', name='ck_series_part_seconds_positivo'),
    sa.CheckConstraint('total_parts >= 1', name='ck_series_total_parts_positivo'),
    sa.ForeignKeyConstraint(['tenant_id', 'job_id'], ['jobs.tenant_id', 'jobs.id'], name='fk_series_job', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_series_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_series_tenant_id_id', ['tenant_id', 'id'], unique=True)
        batch_op.create_index('ix_series_tenant_job', ['tenant_id', 'job_id'], unique=False)

    op.create_table('series_parts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('series_id', sa.String(length=36), nullable=False),
    sa.Column('clip_id', sa.String(length=36), nullable=False),
    sa.Column('part', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint('part >= 1', name='ck_series_parts_part_positiva'),
    sa.ForeignKeyConstraint(['tenant_id', 'clip_id'], ['clips.tenant_id', 'clips.id'], name='fk_series_parts_clip', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'series_id'], ['series.tenant_id', 'series.id'], name='fk_series_parts_series', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_series_parts_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'clip_id', name='uq_series_parts_tenant_clip'),
    sa.UniqueConstraint('tenant_id', 'series_id', 'part', name='uq_series_parts_tenant_series_part')
    )
    with op.batch_alter_table('series_parts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_parts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_series_parts_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('series_playlists',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('series_id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('playlist_id', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'account_id'], ['accounts.tenant_id', 'accounts.id'], name='fk_series_playlists_account', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'series_id'], ['series.tenant_id', 'series.id'], name='fk_series_playlists_series', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_series_playlists_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'series_id', 'account_id', name='uq_series_playlists_tenant_series_account')
    )
    with op.batch_alter_table('series_playlists', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_playlists_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_series_playlists_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('series_playlist_items',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('series_playlist_id', sa.String(length=36), nullable=False),
    sa.Column('publication_id', sa.String(length=36), nullable=False),
    sa.Column('item_id', sa.String(length=128), nullable=True),
    sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'publication_id'], ['publications.tenant_id', 'publications.id'], name='fk_series_playlist_items_publication', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'series_playlist_id'], ['series_playlists.tenant_id', 'series_playlists.id'], name='fk_series_playlist_items_playlist', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_series_playlist_items_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'publication_id', name='uq_series_playlist_items_tenant_publication')
    )
    with op.batch_alter_table('series_playlist_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_playlist_items_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_series_playlist_items_tenant_id_id', ['tenant_id', 'id'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('series_playlist_items', schema=None) as batch_op:
        batch_op.drop_index('ix_series_playlist_items_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_series_playlist_items_tenant_id'))

    op.drop_table('series_playlist_items')
    with op.batch_alter_table('series_playlists', schema=None) as batch_op:
        batch_op.drop_index('ix_series_playlists_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_series_playlists_tenant_id'))

    op.drop_table('series_playlists')
    with op.batch_alter_table('series_parts', schema=None) as batch_op:
        batch_op.drop_index('ix_series_parts_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_series_parts_tenant_id'))

    op.drop_table('series_parts')
    with op.batch_alter_table('series', schema=None) as batch_op:
        batch_op.drop_index('ix_series_tenant_job')
        batch_op.drop_index('ix_series_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_series_tenant_id'))

    op.drop_table('series')
