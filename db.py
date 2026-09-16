"""Conexao e escopo de tenant.

**Stack: SQLAlchemy 2.x async, SQLite por padrao, Postgres por `DATABASE_URL`.**

SQLite porque o escopo declarado e uso pessoal self-hosted: zero operacao, sem
container, um arquivo em disco -- consistente com todo o resto do caminho
self-host, que ja mantem estado em disco (ver docs/MAPA-DOS-ESTAGIOS.md). O
`.env.example` documenta como apontar para Postgres, e a secao 3 do Plano
Tecnico admite os dois. O codigo evita construcao exclusiva de SQLite, entao
trocar e configuracao, nao reescrita.

Async porque o `app.py` e async de ponta a ponta: uma consulta bloqueante
dentro de um handler `async def` trava o event loop e, com o semaforo de jobs
do upstream, isso para a fila inteira.

> Nota sobre a Fase 0.3: `sqlalchemy` e `alembic` foram removidos do
> `requirements.txt` naquela fase porque pertenciam ao modulo comercial
> `cloud/` e nada mais os usava. Voltam agora como dependencia **deste**
> schema. Nao e contradicao: e a diferenca entre herdar um ORM de terceiros e
> escrever o proprio.

## A pegadinha do SQLite

O SQLite ignora chave estrangeira por padrao. Sem `PRAGMA foreign_keys=ON` em
**cada conexao**, as FKs compostas do `db_models` -- que sao o que torna
vazamento entre tenants impossivel -- viram decoracao: o banco aceitaria um
`clips.job_id` apontando para o job de outro tenant sem reclamar. O listener
abaixo liga o pragma em toda conexao nova, e
`tests/test_db_schema.py::TestIsolamentoEntreTenants` falha se isso for
desfeito.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, Optional, Sequence, TypeVar

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession, async_sessionmaker,
                                    create_async_engine)

from contextvars import ContextVar

from db_models import Base, TenantScoped

T = TypeVar("T")

#: Tenant do modo self-host. Enquanto nenhum usuario tiver senha (ver `auth.py`)
#: todo dado e deste tenant, e o `db_seed` o cria com este id fixo para que as
#: linhas sejam estaveis entre execucoes (um UUID sorteado a cada seed
#: orfanaria tudo).
SELF_HOST_TENANT_ID = "00000000-0000-0000-0000-000000000001"

#: O tenant da requisicao em curso (Fase 4, bloco 4.2).
#:
#: **E um `ContextVar` e nao um parametro, e isso foi decidido contando.** Havia
#: 22 chamadas de `db.tenant()` espalhadas por `app.py`, `publish_queue.py` e
#: `job_registry.py`. Enfiar um `tenant_id` em todas significaria 22 lugares
#: para acertar e, pior, 22 lugares onde ESQUECER nao da erro: a chamada
#: esquecida continua compilando, continua respondendo, e passa a ler o tenant
#: errado em silencio -- que e a falha exata que a Fase 0.5 gastou uma fase
#: inteira para tornar impossivel no banco.
#:
#: Com a variavel de contexto, o default de `tenant()` **e** o tenant da sessao,
#: entao o sitio esquecido fica certo por omissao. O proprio docstring de
#: `tenant()` ja previa isto desde a Fase 0.5: "o resto do codigo nao muda".
#:
#: `contextvars` e por tarefa asyncio, entao duas requisicoes simultaneas nao se
#: enxergam. O que NAO herda o contexto e uma tarefa criada fora da requisicao
#: -- e o caso do worker da fila, que roda o job muito depois de a resposta ter
#: ido embora. La o tenant vem gravado no proprio job. Ver `_rodar_no_tenant`.
_tenant_atual: ContextVar[str] = ContextVar("tenant_atual",
                                            default=SELF_HOST_TENANT_ID)


def tenant_atual() -> str:
    """O tenant que vale agora, sem abrir sessao."""
    return _tenant_atual.get()


def usar_tenant(tenant_id: str):
    """Passa a valer `tenant_id` daqui para a frente neste contexto.

    Devolve o `Token` do `contextvars` para quem precisar desfazer -- o que so
    importa em codigo que compartilha contexto, como o worker da fila.
    """
    return _tenant_atual.set(tenant_id or SELF_HOST_TENANT_ID)


def restaurar_tenant(token) -> None:
    try:
        _tenant_atual.reset(token)
    except (ValueError, LookupError):
        # Token de outro contexto: acontece se alguem guardou o token e o usou
        # noutra tarefa. Nao ha o que restaurar, e levantar aqui esconderia o
        # erro de verdade la atras.
        pass

_engine: Optional[AsyncEngine] = None
_sessions: Optional[async_sessionmaker[AsyncSession]] = None


def database_url() -> str:
    """`DATABASE_URL`, ou um SQLite no diretorio de trabalho do projeto."""
    raw = (os.environ.get("DATABASE_URL") or "").strip()
    if raw:
        # Aceita a forma sincrona por conveniencia e converte para o driver
        # async: quem copia uma URL de Postgres de outro lugar nao deveria ter
        # de saber o nome do driver.
        if raw.startswith("postgres://"):
            raw = raw.replace("postgres://", "postgresql+asyncpg://", 1)
        elif raw.startswith("postgresql://"):
            raw = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif raw.startswith("sqlite:///"):
            raw = raw.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return raw
    return f"sqlite+aiosqlite:///{os.path.join(data_dir(), 'cortes.db')}"


def data_dir() -> str:
    """Onde o banco mora. `DATA_DIR`, ou `data/`.

    **Fora de `output/`, de proposito.** O `output/` e barrido de duas formas
    pelo `app.py`: a limpeza por idade (`cleanup_jobs`) e o teto de tamanho
    (`_enforce_output_size_cap`). Hoje as duas so apagam *diretorios*
    (`os.path.isdir`), entao um arquivo de banco ali sobreviveria -- mas
    sobreviveria por causa de um detalhe de codigo herdado, que um
    `git fetch upstream` pode mudar sem aviso. Guardar o banco em outro lugar
    troca "sobrevive porque testei" por "nao esta no caminho da vassoura".
    """
    return (os.environ.get("DATA_DIR") or "data").strip() or "data"


def is_sqlite(url: Optional[str] = None) -> bool:
    return (url or database_url()).startswith("sqlite")


def _liga_fk_no_sqlite(eng: AsyncEngine) -> None:
    """Liga a verificacao de FK em toda conexao SQLite nova deste engine.

    Sem isto as chaves compostas do schema nao sao verificadas e o isolamento
    entre tenants deixa de existir no banco -- ele aceitaria um `clips.job_id`
    apontando para o job de outro tenant sem reclamar.

    **Ligado ao engine e pelo nome do dialeto, nao por tipo de conexao.** A
    primeira versao farejava `type(conn).__module__.startswith(("sqlite3",
    "aiosqlite"))`, e com aiosqlite o que chega ao evento e um
    `sqlalchemy.dialects.sqlite.aiosqlite.AsyncAdapt_aiosqlite_connection` --
    a checagem dava False, o pragma nunca rodava, e um teste de isolamento
    mostrou o vazamento passando. O dialeto do engine e deterministico.
    """
    if eng.dialect.name != "sqlite":
        return

    @event.listens_for(eng.sync_engine, "connect")
    def _pragma(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA foreign_keys=ON")
        finally:
            cur.close()


def engine() -> AsyncEngine:
    global _engine, _sessions
    if _engine is None:
        url = database_url()
        if is_sqlite(url):
            path = url.split("///", 1)[-1]
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
        _engine = create_async_engine(url, future=True, pool_pre_ping=True)
        _liga_fk_no_sqlite(_engine)
        _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Descarta engine e fabrica de sessoes. Para testes e troca de URL."""
    global _engine, _sessions
    _engine = None
    _sessions = None


@asynccontextmanager
async def session():
    """Sessao crua. Prefira `tenant()`, que nao deixa esquecer o filtro."""
    engine()
    assert _sessions is not None
    async with _sessions() as s:
        yield s


async def create_all() -> None:
    """Cria o schema direto do metadata, sem alembic.

    Para teste e para o primeiro `up` de quem nao quer rodar migracao. O
    caminho de producao e `alembic upgrade head`, que e o unico que sabe
    evoluir um banco que ja tem dados.
    """
    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# --------------------------------------------------------------------------- #
# Escopo de tenant
# --------------------------------------------------------------------------- #

class TenantScope:
    """A forma sancionada de ler e escrever: o `tenant_id` vem de graca.

    O critério de pronto da Fase 0.5 e "nenhuma consulta do codigo ignora a
    coluna". Isso nao se consegue por disciplina -- se consegue tornando o
    caminho facil tambem o caminho correto. Daqui:

        async with db.tenant() as t:            # tenant do self-host
            jobs = await t.all(Job)             # ja filtrado
            t.add(Job(source_id=src.id, ...))   # tenant_id preenchido
            await t.commit()

    Quem precisa de SQL que isto nao cobre usa `db.session()` direto, e ai a
    responsabilidade e explicita em vez de acidental.
    """

    def __init__(self, sess: AsyncSession, tenant_id: str):
        self.session = sess
        self.tenant_id = tenant_id

    def select(self, model: type[T]):
        """`select(model)` ja restrito a este tenant."""
        stmt = select(model)
        if issubclass(model, TenantScoped):
            stmt = stmt.where(model.tenant_id == self.tenant_id)
        return stmt

    async def all(self, model: type[T], *where) -> Sequence[T]:
        stmt = self.select(model)
        for w in where:
            stmt = stmt.where(w)
        return (await self.session.execute(stmt)).scalars().all()

    async def get(self, model: type[T], row_id: str) -> Optional[T]:
        """Busca por id **dentro** do tenant -- id de outro tenant da None."""
        stmt = self.select(model).where(model.id == row_id)
        return (await self.session.execute(stmt)).scalars().first()

    def add(self, obj: Any) -> Any:
        """Insere preenchendo `tenant_id`; recusa objeto de outro tenant.

        A recusa e de proposito: passar `tenant_id` diferente do escopo e
        sempre bug, e falhar alto aqui e melhor que gravar a linha no inquilino
        errado.
        """
        if isinstance(obj, TenantScoped):
            atual = getattr(obj, "tenant_id", None)
            if atual and atual != self.tenant_id:
                raise ValueError(
                    f"objeto do tenant {atual} adicionado no escopo de {self.tenant_id}")
            obj.tenant_id = self.tenant_id
        self.session.add(obj)
        return obj

    async def commit(self) -> None:
        await self.session.commit()

    async def flush(self) -> None:
        await self.session.flush()


@asynccontextmanager
async def tenant(tenant_id: Optional[str] = None):
    """Escopo de tenant. Sem argumento, **o tenant da requisicao em curso**.

    Era o tenant fixo do self-host ate o bloco 4.2; agora o default e o
    `ContextVar` acima, que a tranca do `app.py` preenche a partir da sessao. O
    fixo continua valendo quando ninguem preencheu -- instalacao sem auth,
    script de linha de comando, worker sem job. E o "sabado de trabalho" que a
    secao 7 previu: o resto do codigo nao mudou.

    Passar o id explicitamente continua valendo e e o certo quando a resposta
    NAO pode depender do ambiente -- resolver de quem e uma sessao, por exemplo.
    """
    async with session() as s:
        yield TenantScope(s, tenant_id or tenant_atual())
