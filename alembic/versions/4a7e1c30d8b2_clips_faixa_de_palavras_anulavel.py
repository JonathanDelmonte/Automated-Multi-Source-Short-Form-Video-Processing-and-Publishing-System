"""clips: a faixa de palavras passa a ser anulavel

A secao 2 do Plano Tecnico escolheu indice de palavra em vez de timestamp com
um argumento bom: "LLM erra aritmetica de tempo; nao erra contagem de item em
lista". A secao 7 gravou isso no schema como duas colunas NOT NULL.

O pipeline herdado, porem, faz o inverso: o prompt de deteccao pede `start` e
`end` em SEGUNDOS, e o indice de palavra e derivado da transcricao na hora de
gravar a linha (bloco 3.3). A derivacao e exata e a coluna continua
significando o que diz -- menos num caso.

**Video sem fala.** Ali o pipeline usa `get_visual_clips`, que escolhe por
imagem, e nao existe palavra nenhuma para indexar. Com as colunas NOT NULL, um
corte desses simplesmente nao podia ser gravado; e sem linha em `clips`, ele
tambem nao podia ser publicado pela fila, porque `publications` tem FK composta
para ca. Uma decisao sobre a forma do dado estava, sem querer, decidindo quais
videos o sistema publica.

Nulo aqui significa uma coisa so: **este corte nao veio de fala**. Os dois
CHECKs viraram um, condicional, porque dois CHECKs independentes deixariam
passar `start` preenchido com `end` nulo -- uma faixa pela metade, que e pior
que nenhuma.

Nao ha linha em `clips` ainda: o bloco 3.3 e o primeiro a escrever nela.

Revision ID: 4a7e1c30d8b2
Revises: 8c5d2e91b740
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '4a7e1c30d8b2'
down_revision: Union[str, Sequence[str], None] = '8c5d2e91b740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Os `is not null` do segundo ramo nao sao redundantes. Sem eles, uma faixa
# pela metade (`start` preenchido, `end` nulo) PASSA: `end > start` com `end`
# nulo vale NULL, o `and` vira NULL, e um CHECK so recusa quando o resultado e
# FALSE. Logica de tres valores -- apareceu ao rodar a migracao, nao ao ler o
# diff.
_CHECK_NOVO = ("(start_word_idx is null and end_word_idx is null) or "
               "(start_word_idx is not null and end_word_idx is not null "
               "and start_word_idx >= 0 and end_word_idx > start_word_idx)")


def _tabela(nulavel: bool) -> sa.Table:
    """A tabela como ela esta antes/depois. Repetida aqui, e nao importada de
    `db_models`, para que a migracao nao mude de significado junto com o
    modelo. Os indices entram porque o batch do SQLite recria a tabela a partir
    deste objeto e apaga o que nao estiver aqui."""
    if nulavel:
        checks = [sa.CheckConstraint(_CHECK_NOVO, name='ck_clips_faixa_de_palavras')]
    else:
        checks = [
            sa.CheckConstraint('start_word_idx >= 0',
                               name='ck_clips_start_nao_negativo'),
            sa.CheckConstraint('end_word_idx > start_word_idx',
                               name='ck_clips_fim_depois_do_inicio'),
        ]
    return sa.Table(
        'clips', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('start_word_idx', sa.Integer(), nullable=nulavel),
        sa.Column('end_word_idx', sa.Integer(), nullable=nulavel),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('rubric_json', sa.JSON(), nullable=True),
        sa.Column('render_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        *checks,
        sa.CheckConstraint('score is null or (score >= 0 and score <= 100)',
                           name='ck_clips_score_0_100'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_clips_tenant', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'job_id'],
                                ['jobs.tenant_id', 'jobs.id'],
                                name='fk_clips_job', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_clips_tenant_id', 'tenant_id'),
        sa.Index('ix_clips_tenant_id_id', 'tenant_id', 'id', unique=True),
        sa.Index('ix_clips_tenant_job', 'tenant_id', 'job_id'),
    )


def upgrade() -> None:
    with op.batch_alter_table('clips', copy_from=_tabela(False)) as batch_op:
        batch_op.drop_constraint('ck_clips_start_nao_negativo', type_='check')
        batch_op.drop_constraint('ck_clips_fim_depois_do_inicio', type_='check')
        batch_op.alter_column('start_word_idx', existing_type=sa.Integer(),
                              nullable=True)
        batch_op.alter_column('end_word_idx', existing_type=sa.Integer(),
                              nullable=True)
        batch_op.create_check_constraint('ck_clips_faixa_de_palavras', _CHECK_NOVO)


def downgrade() -> None:
    # Voltar a NOT NULL com linha nula seria erro na hora de recriar a tabela.
    # Um corte de video mudo nao tem faixa de palavras para inventar, entao a
    # volta o descarta -- e o preco de desfazer esta migracao.
    op.execute("delete from clips where start_word_idx is null "
               "or end_word_idx is null")
    with op.batch_alter_table('clips', copy_from=_tabela(True)) as batch_op:
        batch_op.drop_constraint('ck_clips_faixa_de_palavras', type_='check')
        batch_op.alter_column('start_word_idx', existing_type=sa.Integer(),
                              nullable=False)
        batch_op.alter_column('end_word_idx', existing_type=sa.Integer(),
                              nullable=False)
        batch_op.create_check_constraint('ck_clips_start_nao_negativo',
                                         'start_word_idx >= 0')
        batch_op.create_check_constraint('ck_clips_fim_depois_do_inicio',
                                         'end_word_idx > start_word_idx')
