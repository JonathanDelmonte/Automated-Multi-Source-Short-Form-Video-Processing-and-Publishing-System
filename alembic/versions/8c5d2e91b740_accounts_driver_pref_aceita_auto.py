"""accounts.driver_pref aceita `auto`, e passa a nascer assim

A coluna nasceu com default `manual`. Parecia inofensivo -- `manual` e mesmo o
default da fase 1 na secao 6 --, mas a cascata da secao 6 respeita a
preferencia da conta, e uma preferencia gravada em toda linha nao e
preferencia: e um pino. Com `manual` ali, o `youtube-api` nunca seria escolhido
por conta nenhuma, por mais quota que sobrasse, e a camada de publicacao
inteira entregaria sempre o mesmo resultado. Um teste do bloco 3.1
(`test_preferencia_reordena_mas_nao_amplia`) foi quem mostrou.

`auto` e a ausencia de preferencia: deixa a cascata decidir, o que na pratica
continua sendo a fila manual ate existir credencial de plataforma configurada
-- entao o comportamento observavel nao muda hoje. O que muda e o significado
de `manual` na coluna, que volta a ser uma escolha de verdade: "esta conta eu
publico a mao, nao automatize".

Nao ha linha em `accounts` ainda (nada cria conta antes da Fase 3), entao a
recriacao da tabela pelo batch do SQLite nao move dado. A clausula de UPDATE
existe mesmo assim: um seed local de quem foi mais rapido que o plano.

Revision ID: 8c5d2e91b740
Revises: 2f1b7c4ae903
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8c5d2e91b740'
down_revision: Union[str, Sequence[str], None] = '2f1b7c4ae903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PREF_ANTES = "driver_pref in ('manual','youtube-api','aggregator','browser')"
_PREF_DEPOIS = ("driver_pref in ('auto','manual','youtube-api','aggregator',"
                "'browser')")


def _tabela(check_pref: str, default_pref: str) -> sa.Table:
    """A tabela como o schema inicial a criou.

    Repetida aqui em vez de importada de `db_models` pelo mesmo motivo da
    migracao anterior: uma migracao descreve o banco COMO ELE ESTAVA, e
    importar o modelo faria o significado dela mudar junto com o modelo.

    Os indices fazem parte da definicao. O batch do SQLite recria a tabela a
    partir deste objeto, entao o que nao estiver aqui e apagado -- e
    `ix_accounts_tenant_id_id` e UNIQUE e e a chave que a FK composta de
    `publications` referencia (`fk_publications_account`).
    """
    return sa.Table(
        'accounts', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('handle', sa.String(length=255), nullable=False),
        sa.Column('credentials_ref', sa.String(length=512), nullable=True),
        sa.Column('driver_pref', sa.String(length=32), nullable=False,
                  server_default=sa.text(f"'{default_pref}'")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint("platform in ('youtube','tiktok','instagram')",
                           name='ck_accounts_platform'),
        sa.CheckConstraint(check_pref, name='ck_accounts_driver_pref'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_accounts_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'platform', 'handle',
                            name='uq_accounts_tenant_platform_handle'),
        sa.Index('ix_accounts_tenant_id', 'tenant_id'),
        sa.Index('ix_accounts_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def upgrade() -> None:
    with op.batch_alter_table('accounts',
                              copy_from=_tabela(_PREF_ANTES, 'manual')) as batch_op:
        batch_op.drop_constraint('ck_accounts_driver_pref', type_='check')
        batch_op.create_check_constraint('ck_accounts_driver_pref', _PREF_DEPOIS)
        batch_op.alter_column('driver_pref', server_default=sa.text("'auto'"))


def downgrade() -> None:
    # Voltar o CHECK sem traduzir `auto` deixaria linha invalida para tras.
    op.execute("update accounts set driver_pref = 'manual' "
               "where driver_pref = 'auto'")
    with op.batch_alter_table('accounts',
                              copy_from=_tabela(_PREF_DEPOIS, 'auto')) as batch_op:
        batch_op.drop_constraint('ck_accounts_driver_pref', type_='check')
        batch_op.create_check_constraint('ck_accounts_driver_pref', _PREF_ANTES)
        batch_op.alter_column('driver_pref', server_default=sa.text("'manual'"))
