"""sources aceita o adapter `direct`

A Fase 1 deu nome as fontes (`sources/`, interface da secao 4) e ao faze-lo
apareceu uma que a lista da secao 7 nao previa: a **URL de arquivo solta**. Um
mp4 num CDN, um link de tmpfiles que um agente subiu pelo MCP, um objeto no R2.
O fork ja ingere isso desde o upstream -- `plan_download_attempts(...,
youtube=False)` e o `file_hosts.py` existem exatamente para esse caso --, mas o
CHECK da coluna `adapter` recusaria a linha.

Grava-la como `upload` resolveria o erro e estragaria o dado: `upload` significa
arquivo que entrou pelo nosso endpoint e fica ate a limpeza; `direct` e um link
de terceiro que pode expirar em 60 minutos. Sao coisas diferentes e a coluna e
justamente o lugar de distingui-las.

Esta migracao roda antes de existir a primeira linha em `sources` (o pipeline so
passa a escrever nela nesta fase), entao a recriacao da tabela pelo batch do
SQLite nao move dado nenhum.

Revision ID: 2f1b7c4ae903
Revises: 10c39ad670de
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '2f1b7c4ae903'
down_revision: Union[str, Sequence[str], None] = '10c39ad670de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A tabela como o schema inicial a criou. Repetida aqui, e nao importada de
# `db_models`, porque uma migracao descreve o banco COMO ELE ESTAVA: importar o
# modelo faria esta migracao mudar de significado toda vez que o modelo
# mudasse, que e o oposto do que ela e. O batch do SQLite precisa dela para
# recriar a tabela (SQLite nao tem ALTER de CHECK).
_ADAPTER_ANTES = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                  "'twitch-live','gdrive','upload')")
_ADAPTER_DEPOIS = ("adapter in ('youtube','youtube-channel','twitch-vod',"
                   "'twitch-live','gdrive','upload','direct')")


def _tabela(check_adapter: str) -> sa.Table:
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
        # Os indices fazem parte da definicao, e nao sao enfeite: o batch do
        # SQLite recria a tabela a partir DESTE objeto, entao o que nao estiver
        # aqui e apagado junto. Sem eles a migracao rodava limpa e deixava o
        # banco pior do que achou -- `ix_sources_tenant_id_id` e UNIQUE e e a
        # chave que a FK composta de `jobs` referencia (`fk_jobs_source`), que
        # e o mecanismo inteiro do isolamento por tenant do ADR-008.
        sa.Index('ix_sources_tenant_id', 'tenant_id'),
        sa.Index('ix_sources_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def _troca(de: str, para: str) -> None:
    with op.batch_alter_table('sources', copy_from=_tabela(de)) as batch_op:
        batch_op.drop_constraint('ck_sources_adapter', type_='check')
        batch_op.create_check_constraint('ck_sources_adapter', para)


def upgrade() -> None:
    _troca(_ADAPTER_ANTES, _ADAPTER_DEPOIS)


def downgrade() -> None:
    _troca(_ADAPTER_DEPOIS, _ADAPTER_ANTES)
