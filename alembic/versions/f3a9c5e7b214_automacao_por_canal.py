"""automacao por canal: receitas, candidatas, licencas, aprovacoes e ajustes do canal

Etapa 7.5 (docs/PLANO-DA-PLATAFORMA.md). Cinco tabelas novas, e nenhuma coluna
nova em tabela que ja existe -- a regra da Fase 7: o `create_all` do boot cria
tabela que falta e nunca acrescenta coluna.

- `channel_settings`: a agenda do canal (as janelas e quantos por dia, que
  valem no fuso de quem usa, guardado a parte em `DATA_DIR/fuso.json`) e o
  "feito para criancas";
- `recipes`: a receita do canal (de onde vem o video e como editar);
- `candidates`: os videos que a receita achou, com a licenca -- a caixa de
  entrada de fontes;
- `source_licenses`: a origem e a licenca de cada fonte processada;
- `clip_approvals`: os cortes da automacao esperando a pessoa.

Revision ID: f3a9c5e7b214
Revises: e6c1b4a9d270
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f3a9c5e7b214'
down_revision: Union[str, Sequence[str], None] = 'e6c1b4a9d270'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('channel_settings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('settings_json', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_channel_settings_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_channel_settings_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'channel_id', name='uq_channel_settings_tenant_channel')
    )
    with op.batch_alter_table('channel_settings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_channel_settings_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_channel_settings_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('recipes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('spec_json', sa.JSON(), nullable=False),
    sa.Column('state_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("kind in ('cortes','serie','ia')", name='ck_recipes_kind'),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_recipes_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_recipes_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'channel_id', 'kind', name='uq_recipes_tenant_channel_kind')
    )
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recipes_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_recipes_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('source_licenses',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=True),
    sa.Column('license', sa.String(length=16), nullable=False),
    sa.Column('license_text', sa.String(length=200), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('author', sa.String(length=200), nullable=True),
    sa.Column('author_url', sa.Text(), nullable=True),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('declared_by', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("declared_by in ('plataforma','pessoa')", name='ck_source_licenses_declared_by'),
    sa.CheckConstraint("license in ('cc-by','dominio-publico','youtube','propria','autorizada','desconhecida')", name='ck_source_licenses_license'),
    sa.ForeignKeyConstraint(['tenant_id', 'source_id'], ['sources.tenant_id', 'sources.id'], name='fk_source_licenses_source', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_source_licenses_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'source_id', name='uq_source_licenses_tenant_source')
    )
    with op.batch_alter_table('source_licenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_source_licenses_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_source_licenses_tenant_id_id', ['tenant_id', 'id'], unique=True)
        batch_op.create_index('ix_source_licenses_tenant_key', ['tenant_id', 'key'], unique=False)

    op.create_table('candidates',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('recipe_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('url', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('author', sa.String(length=200), nullable=True),
    sa.Column('author_url', sa.Text(), nullable=True),
    sa.Column('duration_s', sa.Integer(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('thumbnail', sa.Text(), nullable=True),
    sa.Column('views', sa.Integer(), nullable=True),
    sa.Column('license', sa.String(length=16), nullable=False),
    sa.Column('license_text', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('job_id', sa.String(length=36), nullable=True),
    sa.Column('found_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("license in ('cc-by','dominio-publico','youtube','propria','autorizada','desconhecida')", name='ck_candidates_license'),
    sa.CheckConstraint("status in ('novo','escolhido','recusado','processando','processado','falhou','repetido')", name='ck_candidates_status'),
    sa.CheckConstraint('duration_s is null or duration_s >= 0', name='ck_candidates_duration_nao_negativa'),
    sa.CheckConstraint('views is null or views >= 0', name='ck_candidates_views_nao_negativa'),
    sa.ForeignKeyConstraint(['tenant_id', 'recipe_id'], ['recipes.tenant_id', 'recipes.id'], name='fk_candidates_recipe', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_candidates_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'recipe_id', 'key', name='uq_candidates_tenant_recipe_key')
    )
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_candidates_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_candidates_tenant_id_id', ['tenant_id', 'id'], unique=True)
        batch_op.create_index('ix_candidates_tenant_key', ['tenant_id', 'key'], unique=False)
        batch_op.create_index('ix_candidates_tenant_recipe_status', ['tenant_id', 'recipe_id', 'status'], unique=False)

    op.create_table('clip_approvals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('clip_id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("status in ('esperando','aprovado','recusado')", name='ck_clip_approvals_status'),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_clip_approvals_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'clip_id'], ['clips.tenant_id', 'clips.id'], name='fk_clip_approvals_clip', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_clip_approvals_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'clip_id', name='uq_clip_approvals_tenant_clip')
    )
    with op.batch_alter_table('clip_approvals', schema=None) as batch_op:
        batch_op.create_index('ix_clip_approvals_tenant_channel_status', ['tenant_id', 'channel_id', 'status'], unique=False)
        batch_op.create_index(batch_op.f('ix_clip_approvals_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_clip_approvals_tenant_id_id', ['tenant_id', 'id'], unique=True)



def downgrade() -> None:
    with op.batch_alter_table('clip_approvals', schema=None) as batch_op:
        batch_op.drop_index('ix_clip_approvals_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_clip_approvals_tenant_id'))
        batch_op.drop_index('ix_clip_approvals_tenant_channel_status')

    op.drop_table('clip_approvals')
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_index('ix_candidates_tenant_recipe_status')
        batch_op.drop_index('ix_candidates_tenant_key')
        batch_op.drop_index('ix_candidates_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_candidates_tenant_id'))

    op.drop_table('candidates')
    with op.batch_alter_table('source_licenses', schema=None) as batch_op:
        batch_op.drop_index('ix_source_licenses_tenant_key')
        batch_op.drop_index('ix_source_licenses_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_source_licenses_tenant_id'))

    op.drop_table('source_licenses')
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_index('ix_recipes_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_recipes_tenant_id'))

    op.drop_table('recipes')
    with op.batch_alter_table('channel_settings', schema=None) as batch_op:
        batch_op.drop_index('ix_channel_settings_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_channel_settings_tenant_id'))

    op.drop_table('channel_settings')
