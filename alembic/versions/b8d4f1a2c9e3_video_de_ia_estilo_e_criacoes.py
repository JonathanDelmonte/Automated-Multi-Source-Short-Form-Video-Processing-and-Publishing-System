"""video de IA: o estilo de criacao do canal, as criacoes e a fonte `ia`

Etapa 7.7 (docs/PLANO-DA-PLATAFORMA.md, ADR-013): um canal com um estilo salvo
cria videos curtos por IA -- roteiro, imagem, voz e legenda. Duas tabelas novas,
pela regra da Fase 7 (nenhuma coluna nova em tabela que ja existe):

- `creation_styles`: o estilo de criacao de um canal (o documento de
  `estilos.py`), um por canal;
- `creations`: cada video criado -- o job, a ideia e o roteiro --, que e de
  onde a automacao le os temas ja feitos para nao repetir.

E uma regra que MUDA numa tabela que existe: `sources.adapter` passa a aceitar
`ia`, porque o video criado nao tem video de origem e a fonte dele e a ideia.
Num banco que ja existe na maquina de quem usa, quem troca a regra no boot e o
`db_acerto`; aqui e o caminho do `alembic upgrade`, pelo batch do SQLite, como
a migracao `2f1b7c4ae903` (a que trouxe o `direct`).

Revision ID: b8d4f1a2c9e3
Revises: a7c3e9f1d502
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d4f1a2c9e3'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f1d502'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# `sources` como ela esta ANTES desta migracao (a da `2f1b7c4ae903`), repetida
# aqui pelo mesmo motivo de la: a migracao descreve o banco como ele estava, e
# o batch do SQLite recria a tabela a partir deste objeto -- indice que nao
# estiver aqui e apagado junto.
_ADAPTER_ANTES = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                  "'twitch-live','gdrive','upload','direct')")
_ADAPTER_DEPOIS = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                   "'twitch-live','gdrive','upload','direct','ia')")


def _sources(check_adapter: str) -> sa.Table:
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
    op.create_table('creation_styles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=False),
    sa.Column('spec_json', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'channel_id'], ['channels.tenant_id', 'channels.id'], name='fk_creation_styles_channel', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_creation_styles_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'channel_id', name='uq_creation_styles_tenant_channel')
    )
    with op.batch_alter_table('creation_styles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_creation_styles_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_creation_styles_tenant_id_id', ['tenant_id', 'id'], unique=True)

    op.create_table('creations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('job_id', sa.String(length=36), nullable=False),
    sa.Column('channel_id', sa.String(length=36), nullable=True),
    sa.Column('idea', sa.Text(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=True),
    sa.Column('script_json', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id', 'job_id'], ['jobs.tenant_id', 'jobs.id'], name='fk_creations_job', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_creations_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'job_id', name='uq_creations_tenant_job')
    )
    with op.batch_alter_table('creations', schema=None) as batch_op:
        batch_op.create_index('ix_creations_tenant_channel', ['tenant_id', 'channel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_creations_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_creations_tenant_id_id', ['tenant_id', 'id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('creations', schema=None) as batch_op:
        batch_op.drop_index('ix_creations_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_creations_tenant_id'))
        batch_op.drop_index('ix_creations_tenant_channel')

    op.drop_table('creations')
    with op.batch_alter_table('creation_styles', schema=None) as batch_op:
        batch_op.drop_index('ix_creation_styles_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_creation_styles_tenant_id'))

    op.drop_table('creation_styles')
    _troca_do_adapter(_ADAPTER_DEPOIS, _ADAPTER_ANTES)
