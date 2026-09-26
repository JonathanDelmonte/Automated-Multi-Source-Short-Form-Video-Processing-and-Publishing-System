"""publication_posts: quando e onde uma publicacao foi ao ar

Etapa 7.3 (docs/PLANO-DA-PLATAFORMA.md). Duas coisas precisavam do mesmo fato:

- a trava do agendador conta o espacamento minimo a partir do ultimo post DE
  VERDADE da conta, e `publications` so sabia a hora marcada;
- o "ja publiquei" passou a pedir o link do post, e sem ele o que se posta a
  mao nunca e medido.

Tabela nova, e nao colunas em `publications`, pela regra da Fase 7: o
`create_all` do boot nao acrescenta coluna a tabela que ja existe.

Revision ID: c7e2a9d41f06
Revises: b3d8f1a6c2e4
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e2a9d41f06'
down_revision: Union[str, Sequence[str], None] = 'b3d8f1a6c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('publication_posts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('publication_id', sa.String(length=36), nullable=False),
    sa.Column('posted_at', sa.DateTime(timezone=True),
              server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('url', sa.String(length=512), nullable=True),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_publication_posts_tenant', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'publication_id'], ['publications.tenant_id', 'publications.id'], name='fk_publication_posts_publication', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'publication_id', name='uq_publication_posts_tenant_publication')
    )
    with op.batch_alter_table('publication_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_publication_posts_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_publication_posts_tenant_id_id', ['tenant_id', 'id'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('publication_posts', schema=None) as batch_op:
        batch_op.drop_index('ix_publication_posts_tenant_id_id')
        batch_op.drop_index(batch_op.f('ix_publication_posts_tenant_id'))
    op.drop_table('publication_posts')
