"""O schema da secao 7: tenant em toda tabela, e isolamento garantido pelo banco.

Sem `pytest-asyncio` de proposito: os testes async rodam por `asyncio.run`, para
nao acrescentar dependencia ao conjunto enxuto que o `ci.yml` instala.
"""
import asyncio
import os
import re
import sqlite3
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import db                                                    # noqa: E402
import db_models                                             # noqa: E402
import db_seed                                               # noqa: E402
from db_models import (Account, Base, Clip, Job, Metric, Publication, Source,
                       Template, Tenant, TenantScoped, User)  # noqa: E402

OUTRO_TENANT = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def banco(tmp_path, monkeypatch):
    """Um SQLite novo por teste, com o schema criado e semeado."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    db.reset_engine()
    asyncio.run(db_seed.seed())
    yield tmp_path
    db.reset_engine()


def corre(coro_fn):
    """Roda uma corrotina, criando um loop por chamada."""
    return asyncio.run(coro_fn())


# --------------------------------------------------------------------------- #
# A guarda estrutural: e ela que faz valer o critério de pronto da fase
# --------------------------------------------------------------------------- #

class TestTenantEmTodaTabela:
    def test_toda_tabela_menos_tenants_tem_tenant_id(self):
        """O criterio da Fase 0.5 e "nenhuma consulta ignora a coluna".

        Isso se garante por estrutura, nao por disciplina: se um modelo novo
        nascer sem `tenant_id`, este teste quebra. Mesmo padrao que o upstream
        usava em `test_account_erasure.py`.
        """
        faltando = [
            nome for nome, tabela in Base.metadata.tables.items()
            if nome != "tenants" and "tenant_id" not in tabela.c
        ]
        assert not faltando, (
            f"tabela(s) sem tenant_id: {faltando}. Herde de TenantScoped.")

    def test_a_lista_TENANT_SCOPED_TABLES_acompanha_o_metadata(self):
        # Se alguem acrescentar uma tabela e esquecer a lista, quebra aqui em
        # vez de silenciosamente ficar de fora de futuras varreduras.
        do_metadata = {n for n in Base.metadata.tables if n != "tenants"}
        assert set(db_models.TENANT_SCOPED_TABLES) == do_metadata

    def test_todo_modelo_com_tenant_herda_de_TenantScoped(self):
        # O mixin e o que o TenantScope usa para decidir se filtra.
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            if cls.__tablename__ == "tenants":
                continue
            assert issubclass(cls, TenantScoped), f"{cls.__name__} sem o mixin"

    def test_as_nove_tabelas_da_secao_7_e_as_dos_canais_existem(self):
        esperadas = {"tenants", "users", "accounts", "templates", "sources",
                     "jobs", "clips", "publications", "metrics",
                     # Fase 7 (7.1): o canal e as duas ligacoes dele. Tabelas
                     # novas, e nao colunas: o boot usa create_all, que nunca
                     # acrescenta coluna a tabela existente.
                     "channels", "channel_accounts", "channel_jobs",
                     # 7.3: quando e onde a publicacao foi ao ar.
                     "publication_posts",
                     # 7.4: curtidas, comentarios e o resto de uma leitura.
                     "metric_details",
                     # 7.5: a automacao por canal -- os ajustes do canal, a
                     # receita, os videos que ela achou, a licenca de cada
                     # fonte e a caixa de aprovacao.
                     "channel_settings", "recipes", "candidates",
                     "source_licenses", "clip_approvals"}
        assert set(Base.metadata.tables) == esperadas

    def test_tenant_id_e_indexado_em_toda_tabela(self):
        # Sem indice, toda consulta com filtro de tenant varre a tabela.
        for nome, tabela in Base.metadata.tables.items():
            if nome == "tenants":
                continue
            indexados = {c.name for idx in tabela.indexes for c in idx.columns}
            assert "tenant_id" in indexados, f"{nome}: tenant_id sem indice"


# --------------------------------------------------------------------------- #
# Isolamento: garantido pelo banco, nao pela boa intencao do chamador
# --------------------------------------------------------------------------- #

class TestIsolamentoEntreTenants:
    def test_o_pragma_de_fk_do_sqlite_esta_ligado(self, banco):
        """Sem `PRAGMA foreign_keys=ON` as FKs compostas sao decoracao.

        A primeira versao do listener farejava o tipo da conexao e nao pegava o
        wrapper do aiosqlite: o pragma nunca rodava e o vazamento passava. Este
        teste e o que impede aquilo de voltar.
        """
        from sqlalchemy import text

        async def _t():
            async with db.session() as s:
                return (await s.execute(text("PRAGMA foreign_keys"))).scalar()
        assert corre(_t) == 1

    def test_um_tenant_nao_le_a_linha_do_outro(self, banco):
        async def _t():
            async with db.session() as s:
                s.add(Tenant(id=OUTRO_TENANT, plan="self_host"))
                await s.commit()
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="do_A.mp4"))
                await t.commit()
                meu = src.id
            async with db.tenant() as t:
                proprio = await t.get(Source, meu)
            async with db.tenant(OUTRO_TENANT) as t:
                alheio = await t.get(Source, meu)
            return proprio, alheio
        proprio, alheio = corre(_t)
        assert proprio is not None
        assert alheio is None, "vazamento de leitura entre tenants"

    def test_o_banco_recusa_referencia_cruzada(self, banco):
        """A FK composta `(tenant_id, source_id)` e o que torna isso impossivel.

        Com FK simples em `sources.id`, um job do tenant B poderia apontar para
        a fonte do tenant A e o banco aceitaria.
        """
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.session() as s:
                s.add(Tenant(id=OUTRO_TENANT, plan="self_host"))
                await s.commit()
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="do_A.mp4"))
                await t.commit()
                meu = src.id
            async with db.tenant(OUTRO_TENANT) as t:
                t.add(Job(source_id=meu))
                try:
                    await t.commit()
                    return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"

    def test_o_caminho_legitimo_continua_funcionando(self, banco):
        # Uma guarda que tambem bloqueia o uso correto nao serve.
        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="meu.mp4"))
                await t.flush()
                t.add(Job(source_id=src.id))
                await t.commit()
                return len(await t.all(Job))
        assert corre(_t) == 1

    def test_o_escopo_recusa_objeto_de_outro_tenant(self, banco):
        async def _t():
            async with db.tenant() as t:
                try:
                    t.add(Source(tenant_id=OUTRO_TENANT, adapter="upload", input="x"))
                    return None
                except ValueError as e:
                    return str(e)
        erro = corre(_t)
        assert erro and OUTRO_TENANT in erro

    def test_apagar_o_tenant_leva_as_linhas(self, banco):
        # ON DELETE CASCADE em toda FK de tenant: e o que faz o apagamento de
        # conta da Fase 4 ser uma transacao, nao uma varredura.
        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                t.add(Job(source_id=src.id))
                await t.commit()
            async with db.session() as s:
                tenant = await s.get(Tenant, db.SELF_HOST_TENANT_ID)
                await s.delete(tenant)
                await s.commit()
            async with db.tenant() as t:
                return len(await t.all(Job)), len(await t.all(Source))
        assert corre(_t) == (0, 0)


# --------------------------------------------------------------------------- #
# Constraints: o schema recusa dado invalido
# --------------------------------------------------------------------------- #

class TestConstraints:
    @pytest.mark.parametrize("campo,valor", [
        ("stage", "estagio_inventado"),
        ("status", "status_inventado"),
    ])
    def test_jobs_recusa_estagio_e_status_fora_da_lista(self, banco, campo, valor):
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                t.add(Job(source_id=src.id, **{campo: valor}))
                try:
                    await t.commit()
                    return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"

    def test_sources_recusa_adapter_fora_da_interface(self, banco):
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                t.add(Source(adapter="vhs", input="x"))
                try:
                    await t.commit(); return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"

    def test_sources_aceita_todo_adapter_registrado(self, banco):
        """O CHECK da coluna e a lista de adapters de verdade nao podem divergir.

        Sao dois lugares que dizem a mesma coisa em linguagens diferentes -- um
        CHECK em SQL e um REGISTRY em Python --, e quem acrescentar um adapter
        novo vai mexer so no segundo. O erro so apareceria na primeira linha
        gravada com a fonte nova, que e depois do download inteiro.
        """
        import sources

        async def _t():
            async with db.tenant() as t:
                for adapter_id in sources.adapter_ids():
                    t.add(Source(adapter=adapter_id, input=f"entrada de {adapter_id}"))
                await t.commit()
                return "aceitou"
        assert corre(_t) == "aceitou", (
            "algum adapter de sources/ nao passa no CHECK de sources.adapter -- "
            "acrescente-o em db_models.Source e crie a migracao")

    def test_clips_recusa_fim_antes_do_inicio(self, banco):
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                job = t.add(Job(source_id=src.id))
                await t.flush()
                t.add(Clip(job_id=job.id, start_word_idx=500, end_word_idx=100))
                try:
                    await t.commit(); return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"

    @pytest.mark.parametrize("inicio,fim,aceita", [
        (0, 10, True),          # faixa normal
        (None, None, True),     # corte de video mudo: nao ha palavra a indexar
        (5, None, False),       # faixa pela metade
        (None, 5, False),       # idem, do outro lado
        (-1, 5, False),         # indice negativo
        (7, 7, False),          # faixa vazia
    ])
    def test_clips_faixa_de_palavras(self, banco, inicio, fim, aceita):
        """As duas metades da faixa andam juntas, ou nenhuma existe.

        O caso `(5, None)` e o que motivou este teste ser por tabela: a
        primeira versao do CHECK o deixava passar, porque `end > start` com
        `end` nulo vale NULL e **CHECK so recusa quando o resultado e FALSE**.
        O banco estava certo; a expressao e que estava incompleta.
        """
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                job = t.add(Job(source_id=src.id))
                await t.flush()
                t.add(Clip(job_id=job.id, start_word_idx=inicio, end_word_idx=fim))
                try:
                    await t.commit(); return True
                except IntegrityError:
                    return False
        assert corre(_t) is aceita

    def test_o_mesmo_corte_na_mesma_conta_uma_vez_so(self, banco):
        """Evita post duplicado por reprocessamento ou retomada de job."""
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                job = t.add(Job(source_id=src.id))
                await t.flush()
                clip = t.add(Clip(job_id=job.id, start_word_idx=0, end_word_idx=50))
                conta = t.add(Account(platform="youtube", handle="canal"))
                await t.flush()
                t.add(Publication(clip_id=clip.id, account_id=conta.id))
                await t.commit()
                t.add(Publication(clip_id=clip.id, account_id=conta.id))
                try:
                    await t.commit(); return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"

    def test_metrics_recusa_retencao_fora_de_0_100(self, banco):
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                src = t.add(Source(adapter="upload", input="x.mp4"))
                await t.flush()
                job = t.add(Job(source_id=src.id)); await t.flush()
                clip = t.add(Clip(job_id=job.id, start_word_idx=0, end_word_idx=9))
                conta = t.add(Account(platform="youtube", handle="c")); await t.flush()
                pub = t.add(Publication(clip_id=clip.id, account_id=conta.id))
                await t.flush()
                t.add(Metric(publication_id=pub.id, views=10, retention_pct=180.0))
                try:
                    await t.commit(); return "aceitou"
                except IntegrityError:
                    return "recusou"
        assert corre(_t) == "recusou"


class TestCredenciais:
    def test_credentials_ref_e_endereco_nao_segredo(self):
        """A secao 7: "aponta pra um cofre, nunca guarda o token na linha"."""
        ref = db_models.vault_ref("local", "youtube", "canal-principal")
        assert ref == "vault://local/youtube/canal-principal"
        assert not re.search(r"(sk-|gsk_|ya29\.|Bearer )", ref)

    def test_conta_nasce_sem_credencial_e_sem_preferencia(self, banco):
        """`auto`, e nao `manual`.

        A coluna nasceu valendo `manual` -- que e mesmo o default da fase 1 na
        secao 6 --, e isso estava errado por um motivo que so apareceu quando a
        cascata do bloco 3.1 foi escrita: ela respeita a preferencia da conta, e
        uma preferencia gravada em TODA linha nao e preferencia, e um pino. Com
        `manual` ali, o `youtube-api` nunca seria escolhido, por mais quota que
        sobrasse. `auto` e a ausencia de preferencia; o default da fase 1
        continua sendo manual, so que por ser o piso da cascata (que e onde
        essa decisao mora) em vez de por estar escrito em cada conta.
        """
        async def _t():
            async with db.tenant() as t:
                c = t.add(Account(platform="youtube", handle="canal"))
                await t.commit()
                return c.credentials_ref, c.driver_pref
        ref, driver = corre(_t)
        assert ref is None
        assert driver == "auto"

    def test_preferencia_invalida_e_recusada_pelo_banco(self, banco):
        from sqlalchemy.exc import IntegrityError

        async def _t():
            async with db.tenant() as t:
                t.add(Account(platform="youtube", handle="c", driver_pref="ftp"))
                await t.commit()
        with pytest.raises(IntegrityError):
            corre(_t)


# --------------------------------------------------------------------------- #
# Seed
# --------------------------------------------------------------------------- #

class TestSeed:
    def test_cria_tenant_usuario_e_template(self, banco):
        async def _t():
            async with db.tenant() as t:
                tenant = await t.session.get(Tenant, db.SELF_HOST_TENANT_ID)
                return tenant, await t.all(User), await t.all(Template)
        tenant, users, templates = corre(_t)
        assert tenant is not None and tenant.plan == "self_host"
        assert len(users) == 1 and users[0].role == "owner"
        assert len(templates) == 1 and templates[0].version == 1

    def test_e_idempotente(self, banco):
        criado = asyncio.run(db_seed.seed())
        assert criado == {"tenant": False, "user": False, "template": False}

        async def _t():
            async with db.tenant() as t:
                return len(await t.all(User)), len(await t.all(Template))
        assert corre(_t) == (1, 1)

    def test_o_tenant_do_self_host_tem_id_fixo(self):
        # Um UUID sorteado a cada seed orfanaria toda linha ja gravada.
        assert db.SELF_HOST_TENANT_ID == "00000000-0000-0000-0000-000000000001"

    def _spec_semeado(self):
        async def _t():
            async with db.tenant() as t:
                return (await t.all(Template))[0].spec_json
        return corre(_t)

    def test_o_template_padrao_respeita_a_area_segura(self, banco):
        """12% em cima e 18% embaixo: o erro no 1 de quem automatiza corte."""
        spec = self._spec_semeado()
        assert spec["safeArea"] == {"topPct": 12, "bottomPct": 18}
        assert spec["aspect"] == "9:16"

    def test_o_template_semeado_faz_o_que_promete(self, banco):
        """Ate o bloco 2.3 o seed gravava o EXEMPLO da secao 5, que referencia
        `logo.png`, `endcard.mp4` e `lofi_01.mp3` -- nenhum existe -- e liga
        `cuts.removeSilence`, que ninguem implementa. Como documentacao esta
        certo; como linha que o painel vai listar e um template que promete o
        que nao faz, e o usuario descobriria aplicando."""
        spec = self._spec_semeado()
        assert spec["overlays"] == [], "sem sobreposicao que aponte para arquivo inexistente"
        assert spec["audio"]["bgm"] is None
        assert spec["cuts"]["removeSilence"] is False

    def test_o_seed_nao_tem_copia_propria_do_documento(self, banco):
        import db_seed
        import template
        assert db_seed.TEMPLATE_PADRAO is template.PADRAO, (
            "duas copias divergem no primeiro campo novo")


# --------------------------------------------------------------------------- #
# URL do banco
# --------------------------------------------------------------------------- #

class TestUrlDoBanco:
    def test_sem_DATABASE_URL_usa_sqlite_em_data(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATA_DIR", raising=False)
        assert db.database_url() == "sqlite+aiosqlite:///data/cortes.db"

    def test_o_banco_nao_mora_dentro_de_output(self, monkeypatch):
        """O `output/` e barrido pela limpeza por idade e pelo teto de tamanho.

        Hoje as duas so apagam diretorios, entao um arquivo ali sobreviveria --
        mas por um detalhe de codigo herdado que um `git fetch upstream` pode
        mudar. O banco fica fora do caminho da vassoura.
        """
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATA_DIR", raising=False)
        monkeypatch.setenv("OUTPUT_DIR", "output")
        assert "output" not in db.database_url()

    def test_DATA_DIR_sobrescreve(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DATA_DIR", "/var/lib/cortes")
        assert db.database_url() == "sqlite+aiosqlite:////var/lib/cortes/cortes.db"

    @pytest.mark.parametrize("entrada,esperado", [
        ("postgres://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        ("postgresql://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
        ("sqlite:///x.db", "sqlite+aiosqlite:///x.db"),
        ("postgresql+asyncpg://u:p@h/d", "postgresql+asyncpg://u:p@h/d"),
    ])
    def test_converte_a_forma_sincrona_para_o_driver_async(self, monkeypatch, entrada, esperado):
        # Quem copia uma URL de Postgres de outro lugar nao deveria ter de
        # saber o nome do driver async.
        monkeypatch.setenv("DATABASE_URL", entrada)
        assert db.database_url() == esperado

    def test_reconhece_sqlite(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/d")
        assert not db.is_sqlite()


# --------------------------------------------------------------------------- #
# Migracao
# --------------------------------------------------------------------------- #

def _fatos(path):
    """Colunas, FKs, indices e checks por tabela -- como conjuntos, para
    comparar schemas ignorando a ordem em que o DDL foi emitido."""
    c = sqlite3.connect(path)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' "
                          "and name not like 'sqlite_%' and name <> 'alembic_version'"):
        cols = frozenset((r[1], r[2], r[3], r[5]) for r in c.execute(f"pragma table_info({t})"))
        fks = frozenset((r[2], r[3], r[4]) for r in c.execute(f"pragma foreign_key_list({t})"))
        idx = set()
        for r in c.execute(f"pragma index_list({t})"):
            colunas = tuple(x[2] for x in c.execute(f"pragma index_info({r[1]})"))
            idx.add((colunas, r[2]))
        sql = c.execute("select sql from sqlite_master where name=?", (t,)).fetchone()[0]
        checks = frozenset(m.strip() for m in re.findall(r"CHECK \((.*?)\)\)", sql + ")"))
        out[t] = (cols, fks, frozenset(idx), checks)
    return out


class TestMigracao:
    def test_alembic_upgrade_produz_o_mesmo_schema_que_o_metadata(self, tmp_path, monkeypatch):
        """A migracao que fica no repo tem de ser a que o metadata descreve.

        Sem este teste, `create_all` (usado em teste) e `alembic upgrade`
        (usado em producao) divergem em silencio, e o bug aparece no deploy.
        """
        via_alembic = tmp_path / "alembic.db"
        via_metadata = tmp_path / "metadata.db"

        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO, capture_output=True, text=True,
            env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{via_alembic}"})
        assert r.returncode == 0, f"alembic falhou:\n{r.stderr[-2000:]}"

        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{via_metadata}")
        db.reset_engine()
        asyncio.run(db.create_all())
        db.reset_engine()

        a, b = _fatos(str(via_alembic)), _fatos(str(via_metadata))
        assert set(a) == set(b), "conjunto de tabelas difere"
        for t in sorted(a):
            assert a[t] == b[t], f"{t}: migracao e metadata divergem"
