"""Schema do projeto -- as nove tabelas da secao 7 do Plano Tecnico.

Por que existe (docs/DECISOES.md, ADR-008): o plano exige `tenant_id` em toda
tabela desde o primeiro commit, porque "adicionar auth sobre um schema que ja
tem tenant e um sabado de trabalho; adicionar tenant sobre um schema que nao
tem e uma migracao que quebra tudo". A Fase 0.1 mostrou que nao ha schema
herdado a migrar: todo o ORM pertencia ao modulo comercial `cloud/` e saiu com
ele. Entao as tabelas nascem escritas, com `tenant_id` na primeira delas.

**Auth nao entra aqui.** E a Fase 4. A tabela `users` existe e fica vazia
fora do seed; nada autentica ninguem ainda. O que esta pronto e o *lugar* onde
o tenant vai vir da sessao.

Tres decisoes de desenho que valem justificativa:

**Chave estrangeira composta com `tenant_id`.** Um `clips.job_id` que aponte
para `jobs.id` permite, por bug de consulta, um corte de um tenant referenciar
o job de outro. A FK composta `(tenant_id, job_id) -> jobs(tenant_id, id)`
torna isso **impossivel no banco**, nao apenas desencorajado. Custa um indice
unico por tabela-pai e e a diferenca entre multi-tenancy de verdade e uma
coluna decorativa.

**`credentials_ref` e referencia, nunca segredo.** A secao 7 e explicita: "aponta
pra um cofre, nunca guarda o token na linha". A coluna guarda algo como
`vault://local/youtube/canal-principal`; quem resolve isso e a camada de cofre,
que entra na Fase 3 junto do Publisher. `vault_ref()` monta a referencia para
que o caminho normal nao consiga produzir um token cru.

**Indices de palavra, nao timestamps, em `clips`.** `start_word_idx` e
`end_word_idx` vem da secao 2 do plano, do `autoclip`: "LLM erra aritmetica de
tempo; nao erra contagem de item em lista". O timestamp e derivado da palavra
na hora de cortar, e nao o contrario.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (CheckConstraint, DateTime, Float, ForeignKeyConstraint,
                        Index, Integer, String, Text, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #

class Base(DeclarativeBase):
    """Metadata de todas as tabelas. O alembic autogenerate le daqui."""
    type_annotation_map = {dict: JSON}


def new_id() -> str:
    """Id de linha. UUID em texto, e nao inteiro sequencial, por dois motivos:

    o `job_id` que o pipeline ja usa e um UUID (ver `_JOB_ID_RE` no `app.py`),
    entao `jobs.id` aceita o que o codigo existente gera sem conversao; e um id
    sequencial vaza volume entre tenants quando isto virar multi-inquilino de
    verdade.
    """
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


TENANT = String(36)
ID = String(36)


class TenantScoped:
    """Mixin que carrega a coluna obrigatoria de toda tabela do schema.

    `tests/test_db_schema.py` falha se um modelo novo nao a tiver -- e o mesmo
    padrao que o upstream usava em `test_account_erasure.py`, onde o teste
    quebra se uma tabela nova referencia `users.id` sem entrar na lista.
    Estrutura em vez de disciplina: e o que sobrevive a quem escreveu.
    """
    tenant_id: Mapped[str] = mapped_column(TENANT, nullable=False, index=True)


def vault_ref(backend: str, platform: str, handle: str) -> str:
    """Monta a referencia de credencial que `accounts.credentials_ref` guarda.

    O caminho normal passa por aqui justamente para nao conseguir produzir um
    token cru: o valor e um endereco (`vault://local/youtube/canal`), e quem o
    resolve e a camada de cofre da Fase 3.
    """
    return f"vault://{backend}/{platform}/{handle}"


# --------------------------------------------------------------------------- #
# 1. tenants -- a raiz. A unica tabela sem tenant_id, porque ela E o tenant.
# --------------------------------------------------------------------------- #

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="self_host")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        CheckConstraint("plan <> ''", name="ck_tenants_plan_nao_vazio"),
    )


# --------------------------------------------------------------------------- #
# 2. users -- existe desde agora, autentica so na Fase 4
# --------------------------------------------------------------------------- #

class User(Base, TenantScoped):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="owner")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_users_tenant"),
        # O mesmo e-mail pode existir em tenants diferentes; dentro de um, nao.
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint("role in ('owner','editor','viewer')", name="ck_users_role"),
        Index("ix_users_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 3. accounts -- uma conta de plataforma, com preferencia de driver (secao 6)
# --------------------------------------------------------------------------- #

class Account(Base, TenantScoped):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    # Endereco no cofre. NUNCA o token. Ver vault_ref().
    credentials_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Qual driver da secao 6 atende esta conta. `manual` e o default da fase 1;
    # `browser` existe na arquitetura mas nasce desligado (secao 1).
    driver_pref: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_accounts_tenant"),
        UniqueConstraint("tenant_id", "platform", "handle",
                         name="uq_accounts_tenant_platform_handle"),
        CheckConstraint("platform in ('youtube','tiktok','instagram')",
                        name="ck_accounts_platform"),
        CheckConstraint("driver_pref in ('manual','youtube-api','aggregator','browser')",
                        name="ck_accounts_driver_pref"),
        Index("ix_accounts_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 4. templates -- o documento de configuracao versionado da secao 5
# --------------------------------------------------------------------------- #

class Template(Base, TenantScoped):
    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # O JSON da secao 5: aspect, hook, captions, overlays, audio, cuts, safeArea.
    # Fica como documento e nao como colunas de proposito -- a secao 5 diz que
    # "nao e um editor de timeline, e um documento de configuracao versionado",
    # e colunas obrigariam migracao a cada campo novo de estilo.
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_templates_tenant"),
        # Versionado: o mesmo nome existe em varias versoes, cada par so uma vez.
        UniqueConstraint("tenant_id", "name", "version",
                         name="uq_templates_tenant_name_version"),
        CheckConstraint("version >= 1", name="ck_templates_version_positiva"),
        Index("ix_templates_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 5. sources -- o que entrou, pelo adapter que o resolveu (secao 4)
# --------------------------------------------------------------------------- #

class Source(Base, TenantScoped):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    # Os ids da interface SourceAdapter da secao 4.
    adapter: Mapped[str] = mapped_column(String(32), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)      # URL ou nome do upload
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_sources_tenant"),
        CheckConstraint(
            "adapter in ('youtube','youtube-channel','twitch-vod','twitch-live',"
            "'gdrive','upload')", name="ck_sources_adapter"),
        CheckConstraint("duration_ms is null or duration_ms >= 0",
                        name="ck_sources_duration_nao_negativa"),
        Index("ix_sources_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 6. jobs -- um passe do pipeline. timings_json vem do bloco 0.5.
# --------------------------------------------------------------------------- #

STAGES = ("ingest", "probe", "transcribe", "detect", "reframe", "compose", "publish")
JOB_STATUSES = ("queued", "running", "completed", "failed")


class Job(Base, TenantScoped):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ID, nullable=False)
    # Nome do estagio 01-07 da secao 4 em que o job esta (ou parou).
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="ingest")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Exatamente o dict que job_metrics.snapshot() devolve: segundos e tokens
    # por estagio, mais tokens por minuto falado. Hoje tambem vai para o
    # sidecar <base>.timings.json; quando esta tabela entrar no pipeline, o
    # sidecar passa a ser cache e a coluna a verdade.
    timings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_jobs_tenant"),
        # Composta: um job nao pode apontar para a fonte de outro tenant.
        ForeignKeyConstraint(["tenant_id", "source_id"], ["sources.tenant_id", "sources.id"],
                             ondelete="CASCADE", name="fk_jobs_source"),
        CheckConstraint(f"stage in {STAGES}", name="ck_jobs_stage"),
        CheckConstraint(f"status in {JOB_STATUSES}", name="ck_jobs_status"),
        Index("ix_jobs_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_jobs_tenant_status", "tenant_id", "status"),
    )


# --------------------------------------------------------------------------- #
# 7. clips -- indices de palavra, nao timestamps (secao 2)
# --------------------------------------------------------------------------- #

class Clip(Base, TenantScoped):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ID, nullable=False)
    # A decisao portada do autoclip: o LLM devolve contagem de item em lista,
    # nao aritmetica de tempo. O timestamp e derivado na hora de cortar.
    start_word_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    end_word_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # A rubrica que o LLM aplicou. E o lado esquerdo da calibracao da Fase 5:
    # cruzar isto com a retencao real de `metrics`.
    rubric_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    render_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_clips_tenant"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"],
                             ondelete="CASCADE", name="fk_clips_job"),
        CheckConstraint("start_word_idx >= 0", name="ck_clips_start_nao_negativo"),
        CheckConstraint("end_word_idx > start_word_idx", name="ck_clips_fim_depois_do_inicio"),
        CheckConstraint("score is null or (score >= 0 and score <= 100)",
                        name="ck_clips_score_0_100"),
        Index("ix_clips_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_clips_tenant_job", "tenant_id", "job_id"),
    )


# --------------------------------------------------------------------------- #
# 8. publications -- um corte entregue por um driver (secao 6)
# --------------------------------------------------------------------------- #

DRIVERS = ("manual", "youtube-api", "aggregator", "browser")
PUB_STATUSES = ("scheduled", "publishing", "published", "failed", "cancelled")


class Publication(Base, TenantScoped):
    __tablename__ = "publications"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    clip_id: Mapped[str] = mapped_column(ID, nullable=False)
    account_id: Mapped[str] = mapped_column(ID, nullable=False)
    driver: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    # O id do lado da plataforma, quando houver. O driver `manual` nao tem.
    remote_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_publications_tenant"),
        ForeignKeyConstraint(["tenant_id", "clip_id"], ["clips.tenant_id", "clips.id"],
                             ondelete="CASCADE", name="fk_publications_clip"),
        ForeignKeyConstraint(["tenant_id", "account_id"],
                             ["accounts.tenant_id", "accounts.id"],
                             ondelete="CASCADE", name="fk_publications_account"),
        # O mesmo corte na mesma conta uma vez so -- evita post duplicado por
        # reprocessamento ou por retomada de job.
        UniqueConstraint("tenant_id", "clip_id", "account_id",
                         name="uq_publications_tenant_clip_account"),
        CheckConstraint(f"driver in {DRIVERS}", name="ck_publications_driver"),
        CheckConstraint(f"status in {PUB_STATUSES}", name="ck_publications_status"),
        Index("ix_publications_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_publications_tenant_status_scheduled", "tenant_id", "status", "scheduled_at"),
    )


# --------------------------------------------------------------------------- #
# 9. metrics -- "parece superflua agora e e a tabela mais valiosa do projeto"
# --------------------------------------------------------------------------- #

class Metric(Base, TenantScoped):
    __tablename__ = "metrics"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(ID, nullable=False)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_metrics_tenant"),
        ForeignKeyConstraint(["tenant_id", "publication_id"],
                             ["publications.tenant_id", "publications.id"],
                             ondelete="CASCADE", name="fk_metrics_publication"),
        # Serie temporal: uma leitura por publicacao por instante de coleta.
        UniqueConstraint("tenant_id", "publication_id", "collected_at",
                         name="uq_metrics_tenant_publication_collected"),
        CheckConstraint("views is null or views >= 0", name="ck_metrics_views_nao_negativa"),
        CheckConstraint("retention_pct is null or (retention_pct >= 0 and retention_pct <= 100)",
                        name="ck_metrics_retention_0_100"),
        Index("ix_metrics_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_metrics_tenant_publication", "tenant_id", "publication_id"),
    )


#: Toda tabela do schema menos `tenants`, que E o tenant. O teste de estrutura
#: compara esta lista com o metadata e falha se um modelo novo ficar de fora.
TENANT_SCOPED_TABLES = (
    "users", "accounts", "templates", "sources", "jobs", "clips",
    "publications", "metrics",
)
