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
DRIVER_PREFS = ("auto", "manual", "youtube-api", "aggregator", "browser", "tiktok-api")

# As plataformas de uma conta. A mesma lista de `plataformas.IDS`, repetida aqui
# para que o schema nao dependa do resto do programa -- um teste compara as
# duas. As quatro chinesas entraram na etapa 7.10 (migracao `e2c7a5d9f184`).
PLATFORMS = ("youtube", "tiktok", "instagram",
             "douyin", "kuaishou", "bilibili", "xiaohongshu")


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
        # Derivado da tupla pelo mesmo motivo do `driver_pref` abaixo: a
        # migracao escreve sem espaco depois da virgula, e o teste compara.
        CheckConstraint(
            "platform in (%s)" % ",".join(f"'{p}'" for p in PLATFORMS),
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
        # `ia` (7.7): o video criado por IA nao tem video de origem -- a
        # fonte dele e a ideia, e o `input` guarda o texto dela. Entrou pela
        # migracao `b8d4f1a2c9e3` e, num banco que ja existe, pelo `db_acerto`.
        # `compilacao` (7.8): o video longo feito dos cortes de outros
        # projetos; o `input` diz quantos e de onde. Migracao `c5f0a8e2d417`.
        CheckConstraint(
            "adapter in ('youtube','youtube-channel','twitch-vod','twitch-live',"
            "'gdrive','upload','direct','ia','compilacao')", name="ck_sources_adapter"),
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

#: `tiktok-api` entrou na etapa 7.3. Um banco criado antes recebe o CHECK novo
#: pelo `db_acerto` no boot; sem ele, a primeira publicacao pelo TikTok morreria
#: no banco, DEPOIS do upload. Os dois da frota (`aparelho` e `aparelho-auto`)
#: entraram na 7.9 pelo mesmo caminho (migracao `d9e3a7c1f5b8`).
DRIVERS = ("manual", "youtube-api", "aggregator", "browser", "tiktok-api",
           "aparelho", "aparelho-auto")
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


class PublicationPost(Base, TenantScoped):
    """Quando e onde uma publicacao foi ao ar (Fase 7, etapa 7.3).

    Uma linha por publicacao que virou post de verdade: gravada pelo driver de
    API no fim do envio, ou pela pessoa no "ja publiquei" -- com o link que ela
    colou, que e o que deixa o post feito a mao ser medido. Publicacao na fila
    manual, esperando alguem, nao tem linha aqui.

    `posted_at` e o que a trava do agendador le: o espacamento minimo conta a
    partir do ultimo post de verdade da conta, e nao da hora que estava marcada.

    **Tabela nova, e nao colunas em `publications`**, pela regra da Fase 7: o
    `create_all` do boot nao acrescenta coluna a tabela que ja existe. O
    `db_acerto` refaria a tabela, mas refazer a tabela de publicacoes do autor
    no boot para guardar um fato que so existe para parte das linhas e trocar o
    simples pelo arriscado.
    """
    __tablename__ = "publication_posts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    publication_id: Mapped[str] = mapped_column(ID, nullable=False)
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    # O link do post na plataforma. Nulo quando a plataforma nao devolveu (um
    # post privado do TikTok nao tem endereco publico).
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_publication_posts_tenant"),
        ForeignKeyConstraint(["tenant_id", "publication_id"],
                             ["publications.tenant_id", "publications.id"],
                             ondelete="CASCADE", name="fk_publication_posts_publication"),
        # Uma publicacao vai ao ar uma vez; o "ja publiquei" repetido corrige o
        # link, nao cria um segundo post.
        UniqueConstraint("tenant_id", "publication_id",
                         name="uq_publication_posts_tenant_publication"),
        Index("ix_publication_posts_tenant_id_id", "tenant_id", "id", unique=True),
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


class MetricDetail(Base, TenantScoped):
    """O resto de uma leitura: curtidas, comentarios, compartilhamentos,
    salvamentos e o tempo medio assistido (Fase 7, etapa 7.4).

    `metrics` nasceu com views e retencao, que e o que o YouTube da e o que a
    calibracao cruza. O TikTok e o Instagram medem por engajamento -- e o
    TikTok nem tem retencao --, e as analises por canal mostram esses numeros.

    **Tabela nova, e nao colunas em `metrics`**, pela regra da Fase 7: o
    `create_all` do boot nao acrescenta coluna a tabela que ja existe. O
    `db_acerto` refaria a tabela, mas refazer no boot "a tabela mais valiosa do
    projeto" para guardar numeros que so parte das leituras tem e trocar o
    simples pelo arriscado -- o mesmo motivo do `publication_posts`.

    Uma linha por leitura, gravada na mesma transacao dela (1:1 com `metrics`),
    e so quando a plataforma deu algum destes numeros. **None nao e zero**,
    como em `metrics`: "o Instagram nao disse" nao e "ninguem salvou".
    """
    __tablename__ = "metric_details"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    metric_id: Mapped[str] = mapped_column(ID, nullable=False)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Segundos, sempre: o YouTube da em segundos e o Instagram em
    # MILISSEGUNDOS, e quem converte e o coletor de cada um.
    avg_watch_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_metric_details_tenant"),
        ForeignKeyConstraint(["tenant_id", "metric_id"],
                             ["metrics.tenant_id", "metrics.id"],
                             ondelete="CASCADE", name="fk_metric_details_metric"),
        UniqueConstraint("tenant_id", "metric_id", name="uq_metric_details_tenant_metric"),
        CheckConstraint("likes is null or likes >= 0", name="ck_metric_details_likes"),
        CheckConstraint("comments is null or comments >= 0", name="ck_metric_details_comments"),
        CheckConstraint("shares is null or shares >= 0", name="ck_metric_details_shares"),
        CheckConstraint("saves is null or saves >= 0", name="ck_metric_details_saves"),
        CheckConstraint("avg_watch_s is null or avg_watch_s >= 0",
                        name="ck_metric_details_avg_watch"),
        Index("ix_metric_details_tenant_id_id", "tenant_id", "id", unique=True),
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


# --------------------------------------------------------------------------- #
# 13-17. automacao por canal (Fase 7, etapa 7.5)
# --------------------------------------------------------------------------- #
#
# A mesma regra das tabelas dos canais: tudo o que e novo entra como tabela
# nova, porque o `create_all` do boot cria tabela que falta e nunca acrescenta
# coluna. E, dentro das tabelas novas, o que tende a crescer (a receita, os
# ajustes do canal) mora num documento JSON validado por um modulo puro
# (`receitas.py`) -- o mesmo desenho do `templates.spec_json`: campo novo de
# receita nao vira migracao.

class ChannelSettings(Base, TenantScoped):
    """Os ajustes de um canal que nao cabiam na linha de `channels`: a agenda
    (as janelas do dia e quantos posts por dia) e o "feito para criancas". Um
    documento por canal, validado por `receitas.normalizar_ajustes`.

    **As janelas valem no fuso de QUEM USA, e o fuso nao mora aqui**: ele e da
    pessoa, nao do canal, e fica por tenant em `DATA_DIR/fuso.json`
    (`fuso.py`), mandado pelo painel. O motor pode rodar em UTC (o container
    do Docker), e "postar as 11h" e uma frase sobre o relogio de quem usa.
    """
    __tablename__ = "channel_settings"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_channel_settings_tenant"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_channel_settings_channel"),
        UniqueConstraint("tenant_id", "channel_id", name="uq_channel_settings_tenant_channel"),
        Index("ix_channel_settings_tenant_id_id", "tenant_id", "id", unique=True),
    )


#: Os tipos de receita. A 7.5 so aceita `cortes` (a validacao mora em
#: `receitas.py`); `serie` (7.6) e `ia` (7.7) ja entram no CHECK para que as
#: proximas etapas nao precisem refazer a tabela no boot.
RECIPE_KINDS = ("cortes", "serie", "ia")


class Recipe(Base, TenantScoped):
    """A receita de um canal: de onde vem o video, como editar, e se esta
    ligada. Quando postar e a agenda do canal (`channel_settings`), e se espera
    aprovacao e o `channels.requires_approval` -- os dois valem para todo
    conteudo do canal, feito pela receita ou a mao.

    `spec_json` e o documento (`receitas.normalizar`); `state_json` e o que o
    laco da automacao anota para a tela (ultima busca, ultimo erro).
    """
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="cortes")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_recipes_tenant"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_recipes_channel"),
        # Uma receita de cada tipo por canal: a de cortes e, na 7.7, a de IA.
        UniqueConstraint("tenant_id", "channel_id", "kind", name="uq_recipes_tenant_channel_kind"),
        CheckConstraint(
            "kind in (%s)" % ",".join(f"'{k}'" for k in RECIPE_KINDS),
            name="ck_recipes_kind"),
        Index("ix_recipes_tenant_id_id", "tenant_id", "id", unique=True),
    )


#: As licencas que o programa sabe dizer. `cc-by` e a Creative Commons do
#: YouTube; `youtube`, a licenca padrao (sem reuso); `dominio-publico` entra
#: para as series da 7.6; `propria` e `autorizada` sao declaracao de quem usa
#: (o video e dela, ou ela tem autorizacao); `desconhecida`, quando ninguem
#: disse.
LICENSES = ("cc-by", "dominio-publico", "youtube", "propria", "autorizada", "desconhecida")

#: O caminho de um video que a receita achou. `escolhido` e o que a pessoa
#: mandou cortar primeiro; `repetido`, o que outro canal ja usou.
CANDIDATE_STATUSES = ("novo", "escolhido", "recusado", "processando", "processado",
                      "falhou", "repetido")


class Candidate(Base, TenantScoped):
    """Um video que a receita achou, com a licenca, esperando a vez -- a
    caixa de entrada de fontes.

    `key` e a identidade do video entre fontes (`youtube:<id>`,
    `twitch-live:<canal>:<bloco>`, `pasta:<hash>`), e e por ela que "nao
    repetir" funciona: o mesmo video nao vira candidato duas vezes na mesma
    receita, e o que outro canal ja cortou e marcado `repetido`.
    """
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    recipe_id: Mapped[str] = mapped_column(ID, nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    # O que vai para o `/api/process`: a URL, ou -- na pasta -- o nome do
    # arquivo DENTRO da pasta do canal, nunca um caminho que venha de fora.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    thumbnail: Mapped[str | None] = mapped_column(Text, nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    license: Mapped[str] = mapped_column(String(16), nullable=False, default="desconhecida")
    # O texto da plataforma, como veio ("Creative Commons Attribution license
    # (reuse allowed)"): e a prova, se um dia alguem reclamar.
    license_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="novo")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # O projeto que o cortou. Sem FK: o job pode nao ter linha no banco (o
    # pipeline falha aberto), e a candidata continua dizendo qual foi.
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    found_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_candidates_tenant"),
        ForeignKeyConstraint(["tenant_id", "recipe_id"],
                             ["recipes.tenant_id", "recipes.id"],
                             ondelete="CASCADE", name="fk_candidates_recipe"),
        UniqueConstraint("tenant_id", "recipe_id", "key", name="uq_candidates_tenant_recipe_key"),
        CheckConstraint(
            "license in (%s)" % ",".join(f"'{l}'" for l in LICENSES),
            name="ck_candidates_license"),
        CheckConstraint(
            "status in (%s)" % ",".join(f"'{s}'" for s in CANDIDATE_STATUSES),
            name="ck_candidates_status"),
        CheckConstraint("duration_s is null or duration_s >= 0",
                        name="ck_candidates_duration_nao_negativa"),
        CheckConstraint("views is null or views >= 0", name="ck_candidates_views_nao_negativa"),
        Index("ix_candidates_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_candidates_tenant_key", "tenant_id", "key"),
        Index("ix_candidates_tenant_recipe_status", "tenant_id", "recipe_id", "status"),
    )


class SourceLicense(Base, TenantScoped):
    """A origem e a licenca de uma fonte processada: quem fez, com que licenca,
    onde esta. Responde reclamacao e strike, e e dela que sai o credito que a
    licenca Creative Commons exige na descricao.

    Uma linha por fonte. **A pasta do projeto tem a mesma informacao**
    (`.origem.json`), e e dali que o credito sai na hora de publicar -- a lista
    de projetos e o pacote do dia vem do disco, e o banco falha aberto. Esta
    tabela serve as consultas (a origem de tudo o que um canal postou) e o "nao
    repetir" (`key`).
    """
    __tablename__ = "source_licenses"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ID, nullable=False)
    key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    license: Mapped[str] = mapped_column(String(16), nullable=False, default="desconhecida")
    license_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Quem disse a licenca: a `plataforma` (o YouTube marcou Creative Commons)
    # ou a `pessoa` (o video e dela, ou ela tem autorizacao).
    declared_by: Mapped[str] = mapped_column(String(16), nullable=False, default="plataforma")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_source_licenses_tenant"),
        ForeignKeyConstraint(["tenant_id", "source_id"], ["sources.tenant_id", "sources.id"],
                             ondelete="CASCADE", name="fk_source_licenses_source"),
        UniqueConstraint("tenant_id", "source_id", name="uq_source_licenses_tenant_source"),
        CheckConstraint(
            "license in (%s)" % ",".join(f"'{l}'" for l in LICENSES),
            name="ck_source_licenses_license"),
        CheckConstraint("declared_by in ('plataforma','pessoa')",
                        name="ck_source_licenses_declared_by"),
        Index("ix_source_licenses_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_source_licenses_tenant_key", "tenant_id", "key"),
    )


APPROVAL_STATUSES = ("esperando", "aprovado", "recusado")


class ClipApproval(Base, TenantScoped):
    """Um corte da automacao esperando a pessoa -- a caixa de aprovacao, nos
    canais que pedem aprovacao antes de postar.

    Aprovado, o corte ganha os galhos nas janelas do canal, como qualquer
    agendamento; recusado, fica no projeto e nao vai ao ar.
    """
    __tablename__ = "clip_approvals"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    clip_id: Mapped[str] = mapped_column(ID, nullable=False)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="esperando")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_clip_approvals_tenant"),
        ForeignKeyConstraint(["tenant_id", "clip_id"], ["clips.tenant_id", "clips.id"],
                             ondelete="CASCADE", name="fk_clip_approvals_clip"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_clip_approvals_channel"),
        UniqueConstraint("tenant_id", "clip_id", name="uq_clip_approvals_tenant_clip"),
        CheckConstraint(
            "status in (%s)" % ",".join(f"'{s}'" for s in APPROVAL_STATUSES),
            name="ck_clip_approvals_status"),
        Index("ix_clip_approvals_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_clip_approvals_tenant_channel_status", "tenant_id", "channel_id", "status"),
    )


# --------------------------------------------------------------------------- #
# 18-21. series em partes (Fase 7, etapa 7.6)
# --------------------------------------------------------------------------- #
#
# "Um video longo vira Parte 1, 2, 3..., postadas em sequencia; no YouTube, uma
# playlist por serie." A regra de sempre da Fase 7: tudo em tabela nova.

class Series(Base, TenantScoped):
    """Uma serie em partes: um video longo cortado em pedacos de cerca de um
    minuto, na ordem. O `id` nasce no pedido (vai no `serie.json` da pasta do
    job, que o `main.py` le) e a linha e gravada no fim do job, com as partes.

    `job_id` e o projeto que a cortou. Hoje uma serie e um projeto; a tabela
    separada existe para que a serie tenha identidade propria -- e dela que a
    playlist do YouTube e as partes penduram.
    """
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ID, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    part_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    total_parts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_series_tenant"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"],
                             ondelete="CASCADE", name="fk_series_job"),
        CheckConstraint("total_parts >= 1", name="ck_series_total_parts_positivo"),
        CheckConstraint("part_seconds > 0", name="ck_series_part_seconds_positivo"),
        Index("ix_series_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_series_tenant_job", "tenant_id", "job_id"),
    )


class SeriesPart(Base, TenantScoped):
    """Qual corte e qual parte de qual serie. E daqui que a trava do agendador
    sabe a ordem: a parte seguinte nao sai enquanto uma anterior, na mesma
    conta, ainda vai sair, esta subindo ou falhou (`series.seguradas`).

    **"Sem repeticao" tambem e regra do banco**: um numero de parte existe uma
    vez por serie, e um corte e parte de uma serie so.
    """
    __tablename__ = "series_parts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    series_id: Mapped[str] = mapped_column(ID, nullable=False)
    clip_id: Mapped[str] = mapped_column(ID, nullable=False)
    part: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_series_parts_tenant"),
        ForeignKeyConstraint(["tenant_id", "series_id"], ["series.tenant_id", "series.id"],
                             ondelete="CASCADE", name="fk_series_parts_series"),
        ForeignKeyConstraint(["tenant_id", "clip_id"], ["clips.tenant_id", "clips.id"],
                             ondelete="CASCADE", name="fk_series_parts_clip"),
        UniqueConstraint("tenant_id", "clip_id", name="uq_series_parts_tenant_clip"),
        UniqueConstraint("tenant_id", "series_id", "part", name="uq_series_parts_tenant_series_part"),
        CheckConstraint("part >= 1", name="ck_series_parts_part_positiva"),
        Index("ix_series_parts_tenant_id_id", "tenant_id", "id", unique=True),
    )


class SeriesPlaylist(Base, TenantScoped):
    """A playlist do YouTube de uma serie numa conta: uma por serie e conta,
    criada quando a primeira parte vai ao ar e a conta esta conectada para
    organizar (`conexoes`, tipo `organizar`)."""
    __tablename__ = "series_playlists"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    series_id: Mapped[str] = mapped_column(ID, nullable=False)
    account_id: Mapped[str] = mapped_column(ID, nullable=False)
    playlist_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_series_playlists_tenant"),
        ForeignKeyConstraint(["tenant_id", "series_id"], ["series.tenant_id", "series.id"],
                             ondelete="CASCADE", name="fk_series_playlists_series"),
        ForeignKeyConstraint(["tenant_id", "account_id"],
                             ["accounts.tenant_id", "accounts.id"],
                             ondelete="CASCADE", name="fk_series_playlists_account"),
        UniqueConstraint("tenant_id", "series_id", "account_id",
                         name="uq_series_playlists_tenant_series_account"),
        Index("ix_series_playlists_tenant_id_id", "tenant_id", "id", unique=True),
    )


class SeriesPlaylistItem(Base, TenantScoped):
    """Uma parte publicada que ja entrou na playlist. Sem linha aqui, o laco
    do agendador ainda vai coloca-la -- e a unicidade por publicacao e o que
    impede a mesma parte de entrar duas vezes."""
    __tablename__ = "series_playlist_items"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    series_playlist_id: Mapped[str] = mapped_column(ID, nullable=False)
    publication_id: Mapped[str] = mapped_column(ID, nullable=False)
    item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_series_playlist_items_tenant"),
        ForeignKeyConstraint(["tenant_id", "series_playlist_id"],
                             ["series_playlists.tenant_id", "series_playlists.id"],
                             ondelete="CASCADE", name="fk_series_playlist_items_playlist"),
        ForeignKeyConstraint(["tenant_id", "publication_id"],
                             ["publications.tenant_id", "publications.id"],
                             ondelete="CASCADE", name="fk_series_playlist_items_publication"),
        UniqueConstraint("tenant_id", "publication_id",
                         name="uq_series_playlist_items_tenant_publication"),
        Index("ix_series_playlist_items_tenant_id_id", "tenant_id", "id", unique=True),
    )


# --------------------------------------------------------------------------- #
# 22-23. video criado por IA (Fase 7, etapa 7.7)
# --------------------------------------------------------------------------- #

class CreationStyle(Base, TenantScoped):
    """O estilo de criacao de um canal: o documento de `estilos.py` --
    personagens com a imagem de referencia, visual, voz, ritmo e legenda. Um
    por canal: e a "secao de video de IA" dele, e todo video dali segue o
    estilo. As imagens dos personagens moram em disco
    (`DATA_DIR/estilos/<id>/`), e o documento guarda so o nome do arquivo."""
    __tablename__ = "creation_styles"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    channel_id: Mapped[str] = mapped_column(ID, nullable=False)
    spec_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_creation_styles_tenant"),
        ForeignKeyConstraint(["tenant_id", "channel_id"],
                             ["channels.tenant_id", "channels.id"],
                             ondelete="CASCADE", name="fk_creation_styles_channel"),
        UniqueConstraint("tenant_id", "channel_id", name="uq_creation_styles_tenant_channel"),
        Index("ix_creation_styles_tenant_id_id", "tenant_id", "id", unique=True),
    )


class Creation(Base, TenantScoped):
    """Um video criado por IA: o job que o fez, a ideia e o roteiro. E daqui
    que a automacao le os temas ja feitos para nao repetir.

    `channel_id` sem FK, de proposito: apagar o canal solta os projetos dele
    (7.1), e o registro do que o projeto foi fica. Com FK composta, o "set
    null" apagaria tambem o `tenant_id`."""
    __tablename__ = "creations"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ID, nullable=False)
    channel_id: Mapped[str | None] = mapped_column(ID, nullable=True)
    idea: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    script_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_creations_tenant"),
        ForeignKeyConstraint(["tenant_id", "job_id"], ["jobs.tenant_id", "jobs.id"],
                             ondelete="CASCADE", name="fk_creations_job"),
        UniqueConstraint("tenant_id", "job_id", name="uq_creations_tenant_job"),
        Index("ix_creations_tenant_id_id", "tenant_id", "id", unique=True),
        Index("ix_creations_tenant_channel", "tenant_id", "channel_id"),
    )


# --------------------------------------------------------------------------- #
# 26-29. a frota de aparelhos (Fase 7, etapa 7.9, ADR-016)
# --------------------------------------------------------------------------- #
#
# A regra da Fase 7 de sempre: tudo novo, e nada em tabela que ja existe. A
# conta de plataforma continua em `accounts`; o que a frota sabe dela (em que
# aparelho mora, como posta, quanto por dia) mora em `device_accounts`.

class FleetSettings(Base, TenantScoped):
    """Se a frota esta ligada. **Nasce desligada**: ligar e a pessoa dizer que
    leu os limites (ADR-016). Um documento por tenant, como os ajustes do
    canal, para que o proximo campo nao vire migracao."""
    __tablename__ = "fleet_settings"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_fleet_settings_tenant"),
        UniqueConstraint("tenant_id", name="uq_fleet_settings_tenant"),
        Index("ix_fleet_settings_tenant_id_id", "tenant_id", "id", unique=True),
    )


#: Como o aparelho chega ao computador: pelo cabo, pela rede de casa, ou e um
#: celular em nuvem (um endereco de adb na internet).
DEVICE_KINDS = ("cabo", "rede", "nuvem")


class Device(Base, TenantScoped):
    """Um celular da frota, pelo serial que o servidor do adb da a ele (o do
    cabo, `ip:porta` na rede, ou o nome do pareamento do Android 11+)."""
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    serial: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="cabo")
    # `ip:porta` para reconectar quando a rede cai; nulo no cabo.
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_devices_tenant"),
        UniqueConstraint("tenant_id", "serial", name="uq_devices_tenant_serial"),
        CheckConstraint("kind in ('cabo','rede','nuvem')", name="ck_devices_kind"),
        Index("ix_devices_tenant_id_id", "tenant_id", "id", unique=True),
    )


#: `entregar`: o video vai para o app e a pessoa toca em publicar (risco zero).
#: `automatico`: o motor toca, pelo roteiro ensinado e ensaiado (risco 0,5, so
#: com o consentimento da conta).
FLEET_MODES = ("entregar", "automatico")
#: O teto duro de posts por dia por conta: o menor das vias oficiais, o do
#: TikTok (ADR-016). O padrao e 3, o do agendador.
LIMITE_DIARIO_PADRAO = 3
LIMITE_DIARIO_MAXIMO = 15


class DeviceAccount(Base, TenantScoped):
    """Uma conta morando num aparelho. Uma conta, um aparelho; um aparelho, no
    maximo uma conta por plataforma -- trocar de conta dentro do app seria um
    toque as cegas, e postar na conta errada e pior que nao postar.

    **O banco guarda metade do consentimento**: modo automatico sem a hora do
    consentimento nao entra (o CHECK abaixo). A outra metade e a cascata
    (`publishers.consentiu`)."""
    __tablename__ = "device_accounts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ID, nullable=False)
    account_id: Mapped[str] = mapped_column(ID, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="entregar")
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False,
                                             default=LIMITE_DIARIO_PADRAO)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_device_accounts_tenant"),
        ForeignKeyConstraint(["tenant_id", "device_id"], ["devices.tenant_id", "devices.id"],
                             ondelete="CASCADE", name="fk_device_accounts_device"),
        ForeignKeyConstraint(["tenant_id", "account_id"],
                             ["accounts.tenant_id", "accounts.id"],
                             ondelete="CASCADE", name="fk_device_accounts_account"),
        UniqueConstraint("tenant_id", "account_id", name="uq_device_accounts_tenant_account"),
        UniqueConstraint("tenant_id", "device_id", "platform",
                         name="uq_device_accounts_tenant_device_platform"),
        CheckConstraint("mode in ('entregar','automatico')", name="ck_device_accounts_mode"),
        CheckConstraint("daily_limit >= 1 and daily_limit <= 15",
                        name="ck_device_accounts_limite"),
        CheckConstraint("platform in (%s)" % ",".join(f"'{p}'" for p in PLATFORMS),
                        name="ck_device_accounts_platform"),
        CheckConstraint("mode <> 'automatico' or consent_at is not null",
                        name="ck_device_accounts_consentimento"),
        Index("ix_device_accounts_tenant_id_id", "tenant_id", "id", unique=True),
    )


class DeviceScript(Base, TenantScoped):
    """O roteiro de um app num aparelho: o que a pessoa ensinou
    (`frota_roteiro`), a versao do app em que ensinou, e o ultimo ensaio. O
    automatico so roda com o ensaio passando e o app na mesma versao."""
    __tablename__ = "device_scripts"

    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ID, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    app_package: Mapped[str] = mapped_column(String(128), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # A tela do app que recebe o video (`pacote/classe`); nulo e o Android
    # perguntando, e com ele o automatico nao roda.
    component: Mapped[str | None] = mapped_column(String(255), nullable=True)
    steps_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    taught_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, server_default=func.now())
    rehearsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rehearsal_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rehearsal_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE",
                             name="fk_device_scripts_tenant"),
        ForeignKeyConstraint(["tenant_id", "device_id"], ["devices.tenant_id", "devices.id"],
                             ondelete="CASCADE", name="fk_device_scripts_device"),
        UniqueConstraint("tenant_id", "device_id", "platform",
                         name="uq_device_scripts_tenant_device_platform"),
        CheckConstraint("platform in (%s)" % ",".join(f"'{p}'" for p in PLATFORMS),
                        name="ck_device_scripts_platform"),
        Index("ix_device_scripts_tenant_id_id", "tenant_id", "id", unique=True),
    )


#: Toda tabela do schema menos `tenants`, que E o tenant. O teste de estrutura
#: compara esta lista com o metadata e falha se um modelo novo ficar de fora.
TENANT_SCOPED_TABLES = (
    "users", "accounts", "templates", "sources", "jobs", "clips",
    "publications", "publication_posts", "metrics", "metric_details",
    "channels", "channel_accounts", "channel_jobs",
    "channel_settings", "recipes", "candidates", "source_licenses", "clip_approvals",
    "series", "series_parts", "series_playlists", "series_playlist_items",
    "creation_styles", "creations",
    "fleet_settings", "devices", "device_accounts", "device_scripts",
)
