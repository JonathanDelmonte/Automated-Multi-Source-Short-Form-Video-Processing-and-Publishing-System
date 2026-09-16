"""users ganha password_hash e token_version

A secao 7 adiou a auth para a Fase 4 de proposito -- "adicionar auth sobre um
schema que ja tem tenant e um sabado de trabalho". Este e o sabado: duas colunas
na tabela que ja existia vazia.

`password_hash` e ANULAVEL, e o nulo significa algo: **este usuario ainda nao
pode entrar**. E o estado do `self-host@localhost` que o seed cria, dono de tudo
o que existe hoje e incapaz de autenticar ninguem. Enquanto nenhum usuario tiver
senha, a instalacao segue aberta -- exatamente como era antes desta fase --, e o
bootstrap da Fase 4 nao cria conta nova: da senha e e-mail de verdade ao usuario
que JA e o dono. Nada se move, nada orfana.

`token_version` existe para que a revogacao seja possivel sem tabela de sessao.
O token e assinado e stateless: quem o tem, entra, ate expirar. Bumpar a versao
invalida todos os daquele usuario de uma vez, que e o que a troca de senha e o
"sair de todos os aparelhos" precisam fazer. Uma coluna inteira em vez de uma
decima tabela.

Nao ha linha em `users` alem do seed, e o seed nasce sem senha de qualquer
jeito, entao a recriacao da tabela pelo batch do SQLite nao move dado.

Revision ID: 7e3a9c4d15f8
Revises: 6d9f4b12e0c7
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7e3a9c4d15f8'
down_revision: Union[str, Sequence[str], None] = '6d9f4b12e0c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A grafia SEM espaco depois da virgula e a da migracao inicial desta tabela, e
# `test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata` compara o TEXTO do
# CHECK. O batch do SQLite recria a tabela a partir do objeto abaixo, entao um
# espaco a mais aqui reescreveria o CHECK e deixaria o teste vermelho -- foi o
# que aconteceu na primeira tentativa. Cada tabela segue a grafia da sua propria
# migracao inicial.
_ROLE = "role in ('owner','editor','viewer')"


def _tabela(com_senha: bool) -> sa.Table:
    """A tabela como esta. Repetida, e nao importada de `db_models`, para nao
    mudar de significado junto com o modelo.

    Os indices entram porque o batch do SQLite recria a tabela a partir deste
    objeto e apaga o que faltar -- `ix_users_tenant_id_id` e UNIQUE.
    """
    colunas = [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
    ]
    restricoes = [
        sa.CheckConstraint(_ROLE, name='ck_users_role'),
    ]
    if com_senha:
        colunas += [
            sa.Column('password_hash', sa.String(length=255), nullable=True),
            sa.Column('token_version', sa.Integer(), nullable=False,
                      server_default=sa.text('1')),
        ]
        restricoes.append(sa.CheckConstraint('token_version >= 1',
                                             name='ck_users_token_version'))
    colunas += [
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
    ]
    return sa.Table(
        'users', sa.MetaData(), *colunas, *restricoes,
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_users_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'email', name='uq_users_tenant_email'),
        sa.Index('ix_users_tenant_id', 'tenant_id'),
        sa.Index('ix_users_tenant_id_id', 'tenant_id', 'id', unique=True),
    )


def upgrade() -> None:
    with op.batch_alter_table('users', copy_from=_tabela(False)) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255),
                                      nullable=True))
        batch_op.add_column(sa.Column('token_version', sa.Integer(),
                                      nullable=False,
                                      server_default=sa.text('1')))
        batch_op.create_check_constraint('ck_users_token_version',
                                         'token_version >= 1')


def downgrade() -> None:
    # Voltar apaga as senhas, e com elas a auth: a instalacao volta a ser aberta.
    # Nao ha para onde salvar um hash de senha numa tabela que nao tem a coluna.
    with op.batch_alter_table('users', copy_from=_tabela(True)) as batch_op:
        batch_op.drop_constraint('ck_users_token_version', type_='check')
        batch_op.drop_column('token_version')
        batch_op.drop_column('password_hash')
