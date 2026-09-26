"""O banco que ja existe recebe as regras novas (`db_acerto`, etapa 7.3a).

O caso que importa e o do autor: um banco criado pelo `create_all` de uma
versao antiga, com dados, que o boot de uma versao nova tem de levar as regras
de agora sem perder uma linha. O teste constroi esse banco pela migracao mais
antiga do Alembic (a primeira revisao e o schema da Fase 0.5) e confere, no
fim, que o schema acertado e IDENTICO ao que um `create_all` novo faria.
"""
import asyncio
import glob
import os
import re
import sqlite3
import subprocess
import sys

import pytest
from contextlib import closing

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import db                                                    # noqa: E402
import db_acerto                                             # noqa: E402
import db_models                                             # noqa: E402
import db_seed                                               # noqa: E402

T = db.SELF_HOST_TENANT_ID
REVISAO_INICIAL = "10c39ad670de"


def _esquema(path):
    """Colunas, FKs, indices e CHECKs por tabela, sem depender da ordem."""
    c = sqlite3.connect(path)
    out = {}
    for (t,) in c.execute("select name from sqlite_master where type='table' "
                          "and name not like 'sqlite_%' and name <> 'alembic_version'"):
        cols = frozenset((r[1], r[2], r[3], r[5]) for r in c.execute(f"pragma table_info('{t}')"))
        fks = frozenset((r[2], r[3], r[4]) for r in c.execute(f"pragma foreign_key_list('{t}')"))
        idx = set()
        for r in c.execute(f"pragma index_list('{t}')"):
            colunas = tuple(x[2] for x in c.execute(f"pragma index_info('{r[1]}')"))
            idx.add((colunas, r[2]))
        sql = c.execute("select sql from sqlite_master where name=?", (t,)).fetchone()[0]
        out[t] = (cols, fks, frozenset(idx), frozenset(db_acerto.checks_da_ddl(sql).items()))
    c.close()
    return out


def _alembic(path, revisao):
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revisao],
        cwd=REPO, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{path}"})
    assert r.returncode == 0, f"alembic falhou:\n{r.stderr[-2000:]}"


def _seed(monkeypatch, path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    db.reset_engine()
    try:
        return asyncio.run(db_seed.seed())
    finally:
        db.reset_engine()


def _povoar_banco_antigo(path):
    """Uma linha em cada tabela, com os valores que o schema antigo aceitava."""
    c = sqlite3.connect(path)
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(f"""
        INSERT INTO tenants (id, plan) VALUES ('{T}', 'self_host');
        INSERT INTO users (id, email, role, tenant_id)
            VALUES ('u1', 'self-host@localhost', 'owner', '{T}');
        INSERT INTO accounts (id, platform, handle, credentials_ref, driver_pref, tenant_id)
            VALUES ('a1', 'youtube', 'canal', 'vault://env/youtube/canal', 'manual', '{T}');
        INSERT INTO sources (id, adapter, input, tenant_id)
            VALUES ('s1', 'youtube', 'https://youtu.be/x', '{T}');
        INSERT INTO jobs (id, source_id, stage, status, tenant_id)
            VALUES ('j1', 's1', 'publish', 'completed', '{T}');
        INSERT INTO clips (id, job_id, start_word_idx, end_word_idx, score, rubric_json, tenant_id)
            VALUES ('c1', 'j1', 3, 40, 81.5, '{{"clip_index": 0}}', '{T}');
        INSERT INTO publications (id, clip_id, account_id, driver, status, remote_id, tenant_id)
            VALUES ('p1', 'c1', 'a1', 'manual', 'published', 'abcdefghijk', '{T}');
        INSERT INTO metrics (id, publication_id, views, retention_pct, tenant_id)
            VALUES ('m1', 'p1', 1234, 41.5, '{T}');
    """)
    c.commit()
    c.close()


# --------------------------------------------------------------------------- #
# O que decide -- sem banco
# --------------------------------------------------------------------------- #

class TestLeituraDoSchema:
    def test_espaco_fora_de_aspas_nao_e_diferenca(self):
        assert db_acerto.sem_espacos("driver in ('a', 'b')") == \
            db_acerto.sem_espacos("driver in ('a','b')")

    def test_espaco_dentro_de_aspas_e(self):
        assert db_acerto.sem_espacos("x = 'a b'") != db_acerto.sem_espacos("x = 'ab'")

    def test_le_check_com_parenteses_dentro(self):
        sql = ("CREATE TABLE clips (id INT, "
               "CONSTRAINT ck_x CHECK ((a is null and b is null) or (a >= 0 and b > a)), "
               "CONSTRAINT ck_y CHECK (score is null or (score >= 0 and score <= 100)))")
        achados = db_acerto.checks_da_ddl(sql)
        assert achados == {
            "ck_x": "(aisnullandbisnull)or(a>=0andb>a)",
            "ck_y": "scoreisnullor(score>=0andscore<=100)",
        }

    def test_parentese_dentro_de_aspas_nao_fecha_a_regra(self):
        sql = "CONSTRAINT ck_z CHECK (nome <> ')' and nome <> '(')"
        assert db_acerto.checks_da_ddl(sql) == {"ck_z": "nome<>')'andnome<>'('"}

    def test_modelo_e_banco_novo_nao_divergem_em_nada(self):
        for tabela in db_models.Base.metadata.sorted_tables:
            ddl = str(db_acerto.CreateTable(tabela).compile(dialect=db_acerto._DIALETO))
            colunas = {c.name: not c.nullable or c.primary_key for c in tabela.columns}
            assert db_acerto.o_que_mudou(colunas, ddl, tabela) == [], tabela.name

    def test_valor_novo_no_check_e_mudanca(self):
        tabela = db_models.Base.metadata.tables["publications"]
        ddl = str(db_acerto.CreateTable(tabela).compile(dialect=db_acerto._DIALETO))
        velho = ddl.replace("'browser'", "'browser', 'fax'")
        colunas = {c.name: not c.nullable or c.primary_key for c in tabela.columns}
        assert db_acerto.o_que_mudou(colunas, velho, tabela) == \
            ["regra ck_publications_driver mudou"]

    def test_apertar_nulo_nao_dispara_reconstrucao(self):
        """Quem aperta uma regra decide o que fazer com o dado antigo, numa
        migracao. Reconstruir aqui falharia na copia do primeiro nulo."""
        tabela = db_models.Base.metadata.tables["publications"]
        ddl = str(db_acerto.CreateTable(tabela).compile(dialect=db_acerto._DIALETO))
        colunas = {c.name: False for c in tabela.columns}
        assert db_acerto.o_que_mudou(colunas, ddl, tabela) == []

    def test_o_nome_temporario_so_troca_o_da_tabela(self):
        tabela = db_models.Base.metadata.tables["publications"]
        ddl = db_acerto.ddl_temporaria(tabela)
        assert ddl.lstrip().startswith('CREATE TABLE "_acerto_publications" (')
        # As referencias as outras tabelas ficam: e a tabela-mae de verdade.
        assert "REFERENCES clips (tenant_id, id)" in ddl

    @pytest.mark.parametrize("url, esperado", [
        ("sqlite+aiosqlite:///data/cortes.db", "data/cortes.db"),
        ("sqlite+aiosqlite:////abs/x.db", "/abs/x.db"),
        ("sqlite+aiosqlite://", None),
        ("sqlite+aiosqlite:///:memory:", None),
        ("postgresql+asyncpg://u:s@h/db", None),
    ])
    def test_so_arquivo_sqlite(self, url, esperado):
        assert db_acerto.caminho_do_banco(url) == esperado


# --------------------------------------------------------------------------- #
# O banco de verdade
# --------------------------------------------------------------------------- #

class TestBancoNovoNaoMuda:
    def test_create_all_de_agora_nao_e_tocado(self, tmp_path, monkeypatch):
        banco = tmp_path / "novo.db"
        _seed(monkeypatch, banco)
        antes = _esquema(banco)
        feito = db_acerto.acertar(str(banco), log=lambda *_: None)
        assert feito == {"reconstruidas": {}, "indices": [], "copia": None, "erro": None}
        assert _esquema(banco) == antes
        assert not glob.glob(f"{banco}.antes-do-acerto-*")

    def test_banco_pelo_alembic_tambem_nao(self, tmp_path):
        """O caminho de producao escreve os CHECKs com outros espacos; nao e
        motivo para reconstruir nada."""
        banco = tmp_path / "alembic.db"
        _alembic(banco, "head")
        feito = db_acerto.acertar(str(banco), log=lambda *_: None)
        assert feito["reconstruidas"] == {} and feito["erro"] is None


class TestBancoAntigo:
    @pytest.fixture
    def antigo(self, tmp_path):
        banco = tmp_path / "cortes.db"
        _alembic(banco, REVISAO_INICIAL)
        _povoar_banco_antigo(banco)
        return banco

    def test_o_boot_sobe_e_o_schema_fica_igual_ao_de_agora(self, antigo, tmp_path, monkeypatch):
        # Sem o acerto, o seed morre em `users.password_hash`.
        _seed(monkeypatch, antigo)
        novo = tmp_path / "referencia.db"
        _seed(monkeypatch, novo)
        a, b = _esquema(antigo), _esquema(novo)
        assert set(a) == set(b)
        for tabela in sorted(a):
            assert a[tabela] == b[tabela], f"{tabela} ficou diferente do modelo"

    def test_nenhuma_linha_se_perde(self, antigo, monkeypatch):
        _seed(monkeypatch, antigo)
        with closing(sqlite3.connect(antigo)) as c:
            self._confere_linhas(c)

    def _confere_linhas(self, c):
        assert c.execute("select driver_pref, credentials_ref from accounts where id='a1'").fetchone() \
            == ("manual", "vault://env/youtube/canal")
        assert c.execute("select start_word_idx, end_word_idx, score from clips where id='c1'").fetchone() \
            == (3, 40, 81.5)
        assert c.execute("select remote_id, status from publications where id='p1'").fetchone() \
            == ("abcdefghijk", "published")
        assert c.execute("select views, retention_pct from metrics where id='m1'").fetchone() \
            == (1234, 41.5)
        # A coluna nova nasce com o padrao dela, e a senha, vazia.
        assert c.execute("select password_hash, token_version from users where id='u1'").fetchone() \
            == (None, 1)
        assert c.execute("pragma foreign_key_check").fetchall() == []
        assert c.execute("pragma integrity_check").fetchone() == ("ok",)

    def test_as_regras_novas_valem(self, antigo, monkeypatch):
        _seed(monkeypatch, antigo)
        with closing(sqlite3.connect(antigo)) as c:
            self._regras_novas(c)

    def _regras_novas(self, c):
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("UPDATE jobs SET status='cancelled' WHERE id='j1'")
        c.execute("INSERT INTO sources (id, adapter, input, tenant_id) "
                  f"VALUES ('s2', 'direct', 'https://x/y.mp4', '{T}')")
        c.execute("INSERT INTO accounts (id, platform, handle, driver_pref, tenant_id) "
                  f"VALUES ('a2', 'tiktok', 'outro', 'auto', '{T}')")
        c.execute("INSERT INTO clips (id, job_id, start_word_idx, end_word_idx, tenant_id) "
                  f"VALUES ('c2', 'j1', NULL, NULL, '{T}')")
        c.execute("INSERT INTO publications (id, clip_id, account_id, driver, status, tenant_id) "
                  f"VALUES ('p2', 'c2', 'a2', 'tiktok-api', 'published', '{T}')")
        c.commit()

    def test_as_chaves_entre_tabelas_continuam_valendo(self, antigo, monkeypatch):
        """A troca e feita com as FKs desligadas; se a tabela nova nascesse
        sem elas, o isolamento entre tenants viraria decoracao."""
        _seed(monkeypatch, antigo)
        with closing(sqlite3.connect(antigo)) as c:
            self._chaves(c)

    def _chaves(self, c):
        c.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO publications (id, clip_id, account_id, driver, status, tenant_id) "
                      f"VALUES ('p2', 'nao-existe', 'a1', 'manual', 'scheduled', '{T}')")
        # E o CASCADE da tabela refeita ainda desce ate as filhas.
        c.execute("DELETE FROM clips WHERE id='c1'")
        assert c.execute("select count(*) from publications").fetchone() == (0,)
        assert c.execute("select count(*) from metrics").fetchone() == (0,)

    def test_faz_copia_antes_e_nao_repete(self, antigo, monkeypatch):
        _seed(monkeypatch, antigo)
        copias = glob.glob(f"{antigo}.antes-do-acerto-*")
        assert len(copias) == 1
        # A copia e o banco de antes, inteiro.
        with closing(sqlite3.connect(copias[0])) as velho:
            assert velho.execute("select count(*) from publications").fetchone() == (1,)
            colunas = {r[1] for r in velho.execute("pragma table_info('users')")}
        assert "password_hash" not in colunas
        feito = db_acerto.acertar(str(antigo), log=lambda *_: None)
        assert feito["reconstruidas"] == {} and feito["copia"] is None

    def test_diz_o_que_refez(self, antigo):
        linhas = []
        feito = db_acerto.acertar(str(antigo), log=linhas.append)
        assert feito["erro"] is None
        assert set(feito["reconstruidas"]) == {"users", "accounts", "sources", "jobs", "clips",
                                               "publications"}
        assert "coluna nova password_hash" in feito["reconstruidas"]["users"]
        # O caso que motivou o acerto: o driver do TikTok (etapa 7.3).
        assert "regra ck_publications_driver mudou" in feito["reconstruidas"]["publications"]
        assert "start_word_idx passou a aceitar nulo" in feito["reconstruidas"]["clips"]
        assert "regra ck_jobs_status mudou" in feito["reconstruidas"]["jobs"]
        assert any("tabela users refeita" in l for l in linhas)


class TestQuandoNaoDa:
    def test_copia_que_falha_desfaz_tudo(self, tmp_path, monkeypatch):
        """Uma linha que a regra nova recusa: a troca inteira volta atras, e
        a tabela fica como estava -- com a linha."""
        banco = tmp_path / "cortes.db"
        _seed(monkeypatch, banco)
        c = sqlite3.connect(banco)
        c.executescript("""
            PRAGMA foreign_keys=OFF;
            ALTER TABLE accounts RENAME TO accounts_velha;
        """)
        ddl = c.execute("select sql from sqlite_master where name='accounts_velha'").fetchone()[0]
        ddl = ddl.replace('"accounts_velha"', "accounts").replace("accounts_velha", "accounts")
        ddl = ddl.replace("'youtube','tiktok','instagram'", "'youtube','tiktok','instagram','orkut'")
        c.executescript(f"""
            {ddl};
            INSERT INTO accounts SELECT * FROM accounts_velha;
            DROP TABLE accounts_velha;
        """)
        c.execute("INSERT INTO accounts (id, platform, handle, driver_pref, tenant_id) "
                  f"VALUES ('a9', 'orkut', 'saudade', 'auto', '{T}')")
        c.commit()
        c.close()

        linhas = []
        feito = db_acerto.acertar(str(banco), log=linhas.append)
        assert feito["reconstruidas"] == {}
        assert "CHECK" in feito["erro"] or "constraint" in feito["erro"].lower()
        assert any("desfeito" in l for l in linhas)
        with closing(sqlite3.connect(banco)) as c:
            assert c.execute("select platform from accounts where id='a9'").fetchone() == ("orkut",)
            assert "'orkut'" in c.execute(
                "select sql from sqlite_master where name='accounts'").fetchone()[0]

    def test_indice_que_falta_e_criado_sem_refazer_a_tabela(self, tmp_path, monkeypatch):
        banco = tmp_path / "cortes.db"
        _seed(monkeypatch, banco)
        c = sqlite3.connect(banco)
        c.execute("DROP INDEX ix_publications_tenant_status_scheduled")
        c.commit()
        c.close()
        feito = db_acerto.acertar(str(banco), log=lambda *_: None)
        assert feito["indices"] == ["ix_publications_tenant_status_scheduled"]
        assert feito["reconstruidas"] == {} and feito["copia"] is None
        with closing(sqlite3.connect(banco)) as c:
            nomes = {r[0] for r in c.execute("select name from sqlite_master where type='index'")}
        assert "ix_publications_tenant_status_scheduled" in nomes

    def test_banco_que_nao_existe_nao_e_criado(self, tmp_path):
        feito = db_acerto.acertar(str(tmp_path / "nada.db"), log=lambda *_: None)
        assert feito["erro"] is None and not (tmp_path / "nada.db").exists()


def test_o_seed_chama_o_acerto_antes_de_semear():
    """A ordem e o conserto: o seed consulta `users.password_hash`."""
    fonte = open(os.path.join(REPO, "db_seed.py"), encoding="utf-8").read()
    corpo = fonte[fonte.index("async def seed("):fonte.index("criado = {")]
    assert corpo.index("create_all()") < corpo.index("acertar_tabelas_antigas()")
    assert re.search(r"acertar_tabelas_antigas\(\)", corpo)
