"""jobs.status aceita `cancelled`

A lista da secao 7 e `queued, running, completed, failed`. Ela nao previa
cancelamento -- e `publications` ja previa (`PUB_STATUSES` tem `cancelled`
desde o schema inicial), o que mostra que foi esquecimento e nao decisao.

Apareceu quando o bloco 3.3 foi gravar o primeiro job de verdade: o `app.py`
tem cancelamento desde 13-set-2026, e ele **recusa explicitamente** chamar um
job cancelado de falho, com o motivo escrito no proprio codigo ("um processo
morto por sinal volta com codigo != 0"). Gravar `failed` no banco seria contar
no registro permanente a mentira que a memoria se recusa a contar -- e
justamente o registro permanente e o que a Fase 5 vai ler para calibrar.

Sem linha em `jobs` ainda: este bloco e o primeiro a escrever nela.

Revision ID: 6d9f4b12e0c7
Revises: 4a7e1c30d8b2
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '6d9f4b12e0c7'
down_revision: Union[str, Sequence[str], None] = '4a7e1c30d8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A grafia COM espaco depois da virgula nao e estilo: o schema inicial escreveu
# assim (porque o modelo monta o CHECK com `f"... in {tupla}"`, e o repr de uma
# tupla Python tem esse espaco), e `test_alembic_upgrade_produz_o_mesmo_schema
# _que_o_metadata` compara o TEXTO do CHECK. Um espaco a menos aqui e um teste
# vermelho. Cada tabela segue a grafia da sua propria migracao inicial -- em
# `sources` e `accounts` e sem espaco, aqui e com.
_STAGES = ("stage in ('ingest', 'probe', 'transcribe', 'detect', 'reframe', "
           "'compose', 'publish')")
_STATUS_ANTES = "status in ('queued', 'running', 'completed', 'failed')"
_STATUS_DEPOIS = ("status in ('queued', 'running', 'completed', 'failed', "
                  "'cancelled')")


def _tabela(check_status: str) -> sa.Table:
    """A tabela como esta. Repetida, nao importada de `db_models`, para nao
    mudar de significado junto com o modelo. Os indices entram porque o batch
    do SQLite recria a tabela a partir deste objeto e apaga o que faltar --
    `ix_jobs_tenant_id_id` e UNIQUE e e a chave que `fk_clips_job` referencia.
    """
    return sa.Table(
        'jobs', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('source_id', sa.String(length=36), nullable=False),
        sa.Column('stage', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('timings_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(_STAGES, name='ck_jobs_stage'),
        sa.CheckConstraint(check_status, name='ck_jobs_status'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_jobs_tenant', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'source_id'],
                                ['sources.tenant_id', 'sources.id'],
                                name='fk_jobs_source', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_jobs_tenant_id', 'tenant_id'),
        sa.Index('ix_jobs_tenant_id_id', 'tenant_id', 'id', unique=True),
        sa.Index('ix_jobs_tenant_status', 'tenant_id', 'status'),
    )


def _troca(de: str, para: str) -> None:
    with op.batch_alter_table('jobs', copy_from=_tabela(de)) as batch_op:
        batch_op.drop_constraint('ck_jobs_status', type_='check')
        batch_op.create_check_constraint('ck_jobs_status', para)


def upgrade() -> None:
    _troca(_STATUS_ANTES, _STATUS_DEPOIS)


def downgrade() -> None:
    # Um job cancelado nao tem para onde voltar: `failed` e o unico valor da
    # lista antiga que descreve "terminou sem entregar". A volta perde a
    # distincao, que e o preco de desfazer esta migracao.
    op.execute("update jobs set status = 'failed' where status = 'cancelled'")
    _troca(_STATUS_DEPOIS, _STATUS_ANTES)
