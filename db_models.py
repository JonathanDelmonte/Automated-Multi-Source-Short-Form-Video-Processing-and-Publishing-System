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

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float,
                        ForeignKeyConstraint, Index, Integer, String, Text,
                        UniqueConstraint, func)
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
    # `scrypt$n$r$p$sal$hash` (ver `auth.hash_de_senha`), nunca a senha. NULO
    # significa "este usuario ainda nao pode entrar" -- e o estado do
    # `self-host@localhost` que o seed cria, que e dono de tudo e nao autentica
    # ninguem. **Enquanto NENHUM usuario tiver senha, a instalacao esta aberta**,
    # que e o comportamento anterior a Fase 4 e o motivo do aviso de LAN.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Sobe de um a cada troca de senha ou "sair de todos os aparelhos", e o token
    # carrega o numero. E a revogacao possivel sem tabela de sessao: token
    # assinado e stateless, entao quem o tem entra ate expirar -- a menos que a
    # versao nao bata mais.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                               server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_users_tenant"),
        CheckConstraint("token_version >= 1", name="ck_users_token_version"),
        # O mesmo e-mail pode existir em tenants diferentes; dentro de um, nao.
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint("role in ('owner','editor','viewer')", name="ck_users_role"),
        Index("ix_users_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 3. accounts -- uma conta de plataforma, com preferencia de driver (secao 6)
# --------------------------------------------------------------------------- #

# `auto` nao e um driver: e a ausencia de preferencia, e o padrao. Sem ele a
# coluna nascia valendo `manual`, e como a cascata da secao 6 respeita a
# preferencia da conta, TODA conta nasceria presa na fila manual -- o
# `youtube-api` nunca seria escolhido, por mais quota que sobrasse. Foi um
# teste do bloco 3.1 que mostrou isso: um valor default virou, sem querer, uma
# decisao. Com `auto` no lugar, `manual` na coluna volta a significar o que
# parece significar: "esta conta eu publico a mao, nao automatize".
DRIVER_PREFS = ("auto", "manual", "youtube-api", "aggregator", "browser")


class Account(Base, TenantScoped):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    handle: Mapped[str] = mapped_column(String(255), nullable=False)
    # Endereco no cofre. NUNCA o token. Ver vault_ref().
    credentials_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Qual driver da secao 6 atende esta conta. `auto` e o padrao: deixa a
    # cascata decidir, que na pratica e a fila manual ate haver credencial de
    # plataforma configurada. `browser` existe na arquitetura mas nasce
    # desligado (secao 1) e nunca e escolhido pela cascata.
    driver_pref: Mapped[str] = mapped_column(String(32), nullable=False, default="auto")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_accounts_tenant"),
        UniqueConstraint("tenant_id", "platform", "handle",
                         name="uq_accounts_tenant_platform_handle"),
        CheckConstraint("platform in ('youtube','tiktok','instagram')",
                        name="ck_accounts_platform"),
        # A grafia importa: `test_alembic_upgrade_produz_o_mesmo_schema_que_o
        # _metadata` compara o TEXTO do CHECK entre a migracao e o metadata, e
        # `f"... in {tupla}"` sairia com espaco depois da virgula enquanto a
        # migracao escreve sem. Derivado da tupla assim, os dois nao divergem
        # nem por valor nem por formato.
        CheckConstraint(
            "driver_pref in (%s)" % ",".join(f"'{p}'" for p in DRIVER_PREFS),
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
        # Os ids da secao 4, mais `direct`. A lista da secao 4 nao previu uma
        # URL de arquivo solta -- um mp4 num CDN, um link de tmpfiles que um
        # agente subiu pelo MCP, um objeto no R2 --, mas o fork ingere isso
        # desde o upstream (`plan_download_attempts(..., youtube=False)` e o
        # `file_hosts.py` existem so para esse caso). Gravar essas como
        # `upload` seria mentira na linha: `upload` e arquivo que entrou pelo
        # nosso endpoint, e a diferenca importa -- uma expira em 60 minutos.
        # Ver `sources/direct.py`.
        CheckConstraint(
            "adapter in ('youtube','youtube-channel','twitch-vod','twitch-live',"
            "'gdrive','upload','direct')", name="ck_sources_adapter"),
        CheckConstraint("duration_ms is null or duration_ms >= 0",
                        name="ck_sources_duration_nao_negativa"),
        Index("ix_sources_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 6. jobs -- um passe do pipeline. timings_json vem do bloco 0.5.
# --------------------------------------------------------------------------- #

STAGES = ("ingest", "probe", "transcribe", "detect", "reframe", "compose", "publish")
# `cancelled` entrou na migracao `6d9f4b12e0c7`, quando o bloco 3.3 foi gravar o
# primeiro job de verdade. A lista da secao 7 nao o previa, e `publications` ja
# o tinha -- foi esquecimento, nao decisao. Registrar um job cancelado como
# `failed` seria a mesma mentira que o `app.py` ja recusa contar em memoria
# ("cancelado nao e failed: um processo morto por sinal volta com codigo != 0").
JOB_STATUSES = ("queued", "running", "completed", "failed", "cancelled")


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
    #
    # **Anulaveis desde o bloco 3.3, e o motivo importa.** O pipeline herdado
    # faz o inverso do que a secao 2 desenhou: o LLM devolve segundos e o
    # indice de palavra e derivado da transcricao na hora de gravar a linha.
    # Isso funciona -- e a derivacao e exata -- menos num caso: **video sem
    # fala**. Ali `get_visual_clips` escolhe por imagem, nao ha palavra
    # nenhuma, e a faixa de palavras nao existe. As colunas nasceram NOT NULL e
    # a consequencia era que um corte de video mudo nao podia ser gravado, e
    # entao nao podia ser publicado pela fila. Nulo aqui significa exatamente
    # isso: este corte nao veio de fala. Ver a migracao `4a7e1c30d8b2`.
    start_word_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_word_idx: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        # Um CHECK so, e nao dois, porque a regra virou condicional: ou os dois
        # sao nulos (corte de video mudo) ou formam uma faixa valida. Dois
        # CHECKs independentes deixariam passar `start` preenchido com `end`
        # nulo, que e uma faixa pela metade.
        #
        # Os `is not null` no segundo ramo nao sao redundantes, e a primeira
        # versao disto sem eles deixava a faixa pela metade passar: com
        # `end_word_idx` nulo, `end_word_idx > start_word_idx` vale NULL, o
        # `and` inteiro vira NULL, e **CHECK so recusa quando o resultado e
        # FALSE** -- NULL passa. Logica de tres valores, e o banco estava certo.
        # Descoberto rodando a migracao, nao lendo o diff.
        CheckConstraint(
            "(start_word_idx is null and end_word_idx is null) or "
            "(start_word_idx is not null and end_word_idx is not null "
            "and start_word_idx >= 0 and end_word_idx > start_word_idx)",
            name="ck_clips_faixa_de_palavras"),
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


# --------------------------------------------------------------------------- #
# 10-12. canais -- o centro da Fase 7 (docs/PLANO-DA-PLATAFORMA.md)
# --------------------------------------------------------------------------- #
#
# **Por que tres tabelas, e nao uma coluna `channel_id` em `accounts` e em
# `jobs`.** O motor cria o banco no boot com `create_all` (`db_seed.seed()`), e
# ninguem roda `alembic upgrade` na maquina de quem usa. O `create_all` cria
# tabela que falta, mas NUNCA acrescenta coluna a tabela que ja existe: uma
# coluna nova em `accounts` nao chegaria ao banco do autor, e a primeira
# consulta que a lesse quebraria. Tabela nova chega sozinha. Entao a ligacao
# mora em tabela propria, e a regra vale para o que vier: campo novo em tabela
# existente, tabela nova.

class Channel(Base, TenantScoped):
    """Um canal: a marca que publica num nicho, com as contas de cada
    plataforma ligadas a ele. O mesmo canal no YouTube e no TikTok e o caso
    mais comum -- e o que faz dele o centro, e nao a conta."""
    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # A imagem do canal como data URL, ja reduzida no navegador. Na linha e nao
    # num arquivo: o painel a recebe junto do canal, sem mais uma rota de
    # arquivo que precisaria do token de midia para abrir num <img>.
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Espera aprovacao antes de postar? E escolha de quem usa, feita ao criar o
    # canal (decisao do autor, 26-set-2026) -- por isso nao anulavel.
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_channels_tenant"),
        # Dois "Canal infantil" no mesmo painel seriam dois lugares para o mesmo
        # trabalho, e a pessoa nunca saberia em qual olhar.
        UniqueConstraint("tenant_id", "name", name="uq_channels_tenant_name"),
        Index("ix_channels_tenant_id_id", "tenant_id", "id", unique=True),
    )


class ChannelAccount(Base, TenantScoped):
    """Liga uma conta de plataforma a um canal. Uma conta pertence a no maximo
    um canal; conta sem linha aqui e conta solta, e continua publicando."""
    __tablename__ = "channel_accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    account_id: Mapped[str] = mapped_column(ID, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_channel_accounts_tenant"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_channel_accounts_channel"),
        ForeignKeyConstraint(["tenant_id", "account_id"],
                             ["accounts.tenant_id", "accounts.id"],
                             ondelete="CASCADE", name="fk_channel_accounts_account"),
        UniqueConstraint("tenant_id", "account_id",
                         name="uq_channel_accounts_tenant_account"),
        Index("ix_channel_accounts_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_channel_accounts_tenant_channel", "tenant_id", "channel_id"),
    )


class ChannelJob(Base, TenantScoped):
    """Liga um projeto a um canal. Sem linha, o projeto foi feito sem canal.

    O projeto tambem guarda o canal na propria pasta (`.canal`, ao lado do
    `.tenant`): a lista de projetos vem do disco e o banco falha aberto, entao
    esta tabela serve as consultas do lado do banco, e a pasta, a lista."""
    __tablename__ = "channel_jobs"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    job_id: Mapped[str] = mapped_column(ID, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_channel_jobs_tenant"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_channel_jobs_channel"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"],
                             ondelete="CASCADE", name="fk_channel_jobs_job"),
        UniqueConstraint("tenant_id", "job_id", name="uq_channel_jobs_tenant_job"),
        Index("ix_channel_jobs_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_channel_jobs_tenant_channel", "tenant_id", "channel_id"),
    )


#: Toda tabela do schema menos `tenants`, que E o tenant. O teste de estrutura
#: compara esta lista com o metadata e falha se um modelo novo ficar de fora.
TENANT_SCOPED_TABLES = (
    "users", "accounts", "templates", "sources", "jobs", "clips",
    "publications", "metrics", "channels", "channel_accounts", "channel_jobs",
)
