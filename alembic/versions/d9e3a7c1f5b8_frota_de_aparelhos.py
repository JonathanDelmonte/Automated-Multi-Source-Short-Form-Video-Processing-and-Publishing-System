"""a frota de aparelhos: quatro tabelas novas e os dois drivers dela

Etapa 7.9 (docs/PLANO-DA-PLATAFORMA.md, ADR-016). Quatro tabelas novas, pela
regra da Fase 7 (nenhuma coluna nova em tabela que ja existe):

- `fleet_settings`: se a frota esta ligada (nasce desligada);
- `devices`: os celulares, pelo serial do adb;
- `device_accounts`: a conta que mora em cada aparelho, o modo (entregar ou
  automatico), o limite por dia e a hora do consentimento -- com um CHECK que
  nao deixa o automatico sem ela;
- `device_scripts`: o roteiro que a pessoa ensinou para cada app, e o ensaio.

E uma regra que MUDA numa tabela que existe: `publications.driver` aceita
`aparelho` e `aparelho-auto`. No banco de quem usa, quem troca a regra no boot e
o `db_acerto`; aqui e o caminho do `alembic upgrade`.

Revision ID: d9e3a7c1f5b8
Revises: e2c7a5d9f184
Create Date: 2026-10-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd9e3a7c1f5b8'
down_revision: Union[str, Sequence[str], None] = 'e2c7a5d9f184'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A grafia e a do `db_models` (`f"driver in {DRIVERS}"`): o
# `test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata` compara o TEXTO.
_DRIVER_ANTES = "driver in ('manual', 'youtube-api', 'aggregator', 'browser', 'tiktok-api')"
_DRIVER_DEPOIS = ("driver in ('manual', 'youtube-api', 'aggregator', 'browser', 'tiktok-api', "
                  "'aparelho', 'aparelho-auto')")
_PLATAFORMAS = ("platform in ('youtube','tiktok','instagram','douyin','kuaishou',"
                "'bilibili','xiaohongshu')")


def _criado_em(nome: str = 'created_at') -> sa.Column:
    return sa.Column(nome, sa.DateTime(timezone=True),
                     server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False)


def _publicacoes(check_driver: str) -> sa.Table:
    """`publications` como esta antes desta migracao (a da `d4a8f2c6b913`): o
    batch do SQLite recria a tabela a partir deste objeto, e indice que nao
    estiver aqui e apagado junto."""
    return sa.Table(
        'publications', sa.MetaData(),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('clip_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('driver', sa.String(length=32), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('remote_id', sa.String(length=255), nullable=True),
        _criado_em(),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(check_driver, name='ck_publications_driver'),
        sa.CheckConstraint("status in ('scheduled', 'publishing', 'published', "
                           "'failed', 'cancelled')", name='ck_publications_status'),
        sa.ForeignKeyConstraint(['tenant_id', 'account_id'],
                                ['accounts.tenant_id', 'accounts.id'],
                                name='fk_publications_account', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id', 'clip_id'], ['clips.tenant_id', 'clips.id'],
                                name='fk_publications_clip', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'],
                                name='fk_publications_tenant', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'clip_id', 'account_id',
                            name='uq_publications_tenant_clip_account'),
        sa.Index('ix_publications_tenant_id', 'tenant_id'),
        sa.Index('ix_publications_tenant_id_id', 'tenant_id', 'id', unique=True),
        sa.Index('ix_publications_tenant_status_scheduled',
                 'tenant_id', 'status', 'scheduled_at'),
    )


def _troca_do_driver(de: str, para: str) -> None:
    with op.batch_alter_table('publications', copy_from=_publicacoes(de)) as batch_op:
        batch_op.drop_constraint('ck_publications_driver', type_='check')
        batch_op.create_check_constraint('ck_publications_driver', para)


def _indices(tabela: str) -> None:
    with op.batch_alter_table(tabela, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f'ix_{tabela}_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(f'ix_{tabela}_tenant_id_id', ['tenant_id', 'id'], unique=True)


def upgrade() -> None:
    _troca_do_driver(_DRIVER_ANTES, _DRIVER_DEPOIS)

    op.create_table('fleet_settings',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('settings_json', sa.JSON(), nullable=False),
    _criado_em('updated_at'),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_fleet_settings_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', name='uq_fleet_settings_tenant')
    )
    _indices('fleet_settings')

    op.create_table('devices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('serial', sa.String(length=200), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    _criado_em(),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("kind in ('cabo','rede','nuvem')", name='ck_devices_kind'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_devices_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'serial', name='uq_devices_tenant_serial')
    )
    _indices('devices')

    op.create_table('device_accounts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('device_id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('mode', sa.String(length=16), nullable=False),
    sa.Column('daily_limit', sa.Integer(), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=True),
    _criado_em(),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint("mode in ('entregar','automatico')", name='ck_device_accounts_mode'),
    sa.CheckConstraint('daily_limit >= 1 and daily_limit <= 15', name='ck_device_accounts_limite'),
    sa.CheckConstraint(_PLATAFORMAS, name='ck_device_accounts_platform'),
    sa.CheckConstraint("mode <> 'automatico' or consent_at is not null",
                       name='ck_device_accounts_consentimento'),
    sa.ForeignKeyConstraint(['tenant_id', 'account_id'], ['accounts.tenant_id', 'accounts.id'], name='fk_device_accounts_account', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id', 'device_id'], ['devices.tenant_id', 'devices.id'], name='fk_device_accounts_device', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_device_accounts_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'account_id', name='uq_device_accounts_tenant_account'),
    sa.UniqueConstraint('tenant_id', 'device_id', 'platform', name='uq_device_accounts_tenant_device_platform')
    )
    _indices('device_accounts')

    op.create_table('device_scripts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('device_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('app_package', sa.String(length=128), nullable=False),
    sa.Column('app_version', sa.String(length=64), nullable=True),
    sa.Column('component', sa.String(length=255), nullable=True),
    sa.Column('steps_json', sa.JSON(), nullable=False),
    _criado_em('taught_at'),
    sa.Column('rehearsed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rehearsal_ok', sa.Boolean(), nullable=True),
    sa.Column('rehearsal_detail', sa.Text(), nullable=True),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.CheckConstraint(_PLATAFORMAS, name='ck_device_scripts_platform'),
    sa.ForeignKeyConstraint(['tenant_id', 'device_id'], ['devices.tenant_id', 'devices.id'], name='fk_device_scripts_device', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], name='fk_device_scripts_tenant', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'device_id', 'platform', name='uq_device_scripts_tenant_device_platform')
    )
    _indices('device_scripts')


def downgrade() -> None:
    for tabela in ('device_scripts', 'device_accounts', 'devices', 'fleet_settings'):
        with op.batch_alter_table(tabela, schema=None) as batch_op:
            batch_op.drop_index(f'ix_{tabela}_tenant_id_id')
            batch_op.drop_index(batch_op.f(f'ix_{tabela}_tenant_id'))
        op.drop_table(tabela)
    # Voltar o CHECK sem tirar o que ja usa os ids novos deixaria linha
    # invalida: o que saiu pelo aparelho volta como fila manual.
    op.execute("update publications set driver = 'manual' "
               "where driver in ('aparelho', 'aparelho-auto')")
    _troca_do_driver(_DRIVER_DEPOIS, _DRIVER_ANTES)
