"""O banco que ja existe recebe as regras novas das tabelas (Fase 7, etapa 7.3a).

O boot cria o banco com `create_all` (`db_seed.seed()`), e ninguem roda
`alembic upgrade` na maquina de quem usa. O `create_all` cria a tabela que
falta e **nunca toca numa que ja existe**: coluna nova, coluna que passou a
aceitar nulo, CHECK que ganhou um valor -- tudo isso fica so no modelo, e o
banco de quem instalou antes continua com a regra velha. O erro aparece longe
da causa, e quase sempre engolido pelo "falha aberto" de quem grava:

- `users` ganhou `password_hash` na Fase 4, e o seed consulta a coluna logo no
  boot. Num banco anterior a isso, o seed inteiro falhava -- e com ele os
  templates, a auth e a fila;
- `clips` passou a aceitar corte sem faixa de palavras (video mudo), `jobs`
  passou a aceitar `cancelled`, `accounts` passou a nascer `auto` e `sources`
  ganhou o adapter `direct`. Num banco antigo, cada uma dessas gravacoes era
  recusada pelo CHECK velho, e o `job_registry` so escrevia um aviso;
- e a Fase 7 vai acrescentar drivers de publicacao (TikTok) ao CHECK de
  `publications`. Sem este acerto, a primeira publicacao pelo TikTok morreria
  no banco do autor, depois do upload.

**O conserto e o procedimento que o proprio SQLite documenta** para o que o
`ALTER TABLE` nao alcanca ("Making Other Kinds Of Table Schema Changes", os
doze passos): com as chaves estrangeiras desligadas, criar a tabela nova com a
regra nova, copiar as linhas, apagar a velha, dar o nome dela a nova, recriar
os indices e conferir as chaves. Tudo numa transacao so -- ou todas as tabelas
ficam novas, ou nenhuma muda.

- **Detecta pelo que importa, nao pelo texto inteiro.** Coluna que falta,
  coluna que passou a aceitar nulo e CHECK com outro conteudo (comparado sem
  espaco, porque a migracao e o `create_all` escrevem a mesma regra com
  espacos diferentes). Comparar o `CREATE TABLE` inteiro reconstruiria tabela
  a cada versao do SQLAlchemy que mudasse a formatacao.
- **Nunca aperta.** Coluna que deixou de aceitar nulo nao dispara nada: se ha
  nulo gravado, a copia falharia e a tabela ficaria como esta. Quem aperta uma
  regra escreve a migracao que decide o que fazer com o dado antigo.
- **Indice que falta e criado sem reconstruir** (`CREATE INDEX IF NOT EXISTS`):
  as FKs compostas apontam para os indices unicos `(tenant_id, id)`.
- **Copia de seguranca antes**, pelo backup do proprio SQLite, ao lado do banco
  (`cortes.db.antes-do-acerto-<quando>`). So quando ha o que reconstruir.
- **Falha fechado na tabela, aberto no boot.** Qualquer erro desfaz a
  transacao inteira e o banco fica exatamente como estava; o motor sobe do
  mesmo jeito e o aviso diz qual tabela e por que.
- **So SQLite.** Postgres e o caminho de producao, e la quem evolui o schema e
  o `alembic upgrade`.

Usa o `sqlite3` da biblioteca padrao, e nao o engine async: o `PRAGMA
foreign_keys` so muda FORA de transacao, e o controle de transacao do driver
por baixo do SQLAlchemy abre uma sozinho antes de certos comandos. Com
`isolation_level=None`, quem abre e fecha e este arquivo.
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Callable, Optional

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import sqlite as _dialeto_sqlite
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateIndex, CreateTable

from db_models import Base

#: Prefixo da tabela nova durante a troca. Se sobrar uma (processo morto no
#: meio), a transacao nao foi confirmada e ela nao existe -- o SQLite desfaz.
PREFIXO_TEMPORARIO = "_acerto_"

_DIALETO = _dialeto_sqlite.dialect()


def caminho_do_banco(url: str) -> Optional[str]:
    """O arquivo de um `sqlite+aiosqlite:///...`, ou None (Postgres, memoria)."""
    if not url.startswith("sqlite"):
        return None
    banco = make_url(url).database
    if not banco or banco == ":memory:" or banco.startswith("file::memory:"):
        return None
    return banco


# --------------------------------------------------------------------------- #
# O que mudou -- funcoes puras sobre o texto do schema
# --------------------------------------------------------------------------- #

def sem_espacos(texto: str) -> str:
    """O texto sem espaco FORA de aspas. `in ('a', 'b')` e `in ('a','b')` sao
    a mesma regra; `'a b'` e `'ab'` nao sao."""
    saida = []
    dentro = False
    for ch in texto:
        if ch == "'":
            dentro = not dentro
        if ch.isspace() and not dentro:
            continue
        saida.append(ch)
    return "".join(saida)


def _fecha_parentese(texto: str, abre: int) -> int:
    """O indice do `)` que fecha o `(` em `abre`, respeitando aspas."""
    nivel = 0
    dentro = False
    for i in range(abre, len(texto)):
        ch = texto[i]
        if ch == "'":
            dentro = not dentro
        elif not dentro and ch == "(":
            nivel += 1
        elif not dentro and ch == ")":
            nivel -= 1
            if nivel == 0:
                return i
    return -1


def checks_da_ddl(sql: str) -> dict:
    """Os CHECK com nome de um `CREATE TABLE`, como {nome: regra sem espacos}."""
    achados = {}
    for m in re.finditer(r"CONSTRAINT\s+\"?(\w+)\"?\s+CHECK\s*\(", sql, re.IGNORECASE):
        abre = m.end() - 1
        fecha = _fecha_parentese(sql, abre)
        if fecha < 0:
            continue
        achados[m.group(1)] = sem_espacos(sql[abre + 1:fecha])
    return achados


def checks_do_modelo(tabela) -> dict:
    return {c.name: sem_espacos(str(c.sqltext))
            for c in tabela.constraints
            if isinstance(c, CheckConstraint) and isinstance(c.name, str) and c.name}


def o_que_mudou(colunas_no_banco: dict, sql_no_banco: str, tabela) -> list:
    """Por que esta tabela precisa ser refeita, ou lista vazia.

    `colunas_no_banco` e {nome: notnull} do `PRAGMA table_info`. Funcao pura:
    e o que decide, e o teste a alcanca sem banco nenhum.
    """
    motivos = []
    for coluna in tabela.columns:
        if coluna.name not in colunas_no_banco:
            motivos.append(f"coluna nova {coluna.name}")
        elif (coluna.nullable and not coluna.primary_key
              and colunas_no_banco[coluna.name]):
            motivos.append(f"{coluna.name} passou a aceitar nulo")
    no_banco = checks_da_ddl(sql_no_banco or "")
    no_modelo = checks_do_modelo(tabela)
    for nome, regra in sorted(no_modelo.items()):
        if nome not in no_banco:
            motivos.append(f"regra nova {nome}")
        elif no_banco[nome] != regra:
            motivos.append(f"regra {nome} mudou")
    for nome in sorted(set(no_banco) - set(no_modelo)):
        motivos.append(f"regra {nome} saiu")
    return motivos


def ddl_temporaria(tabela) -> str:
    """O `CREATE TABLE` do modelo, com o nome temporario."""
    ddl = str(CreateTable(tabela).compile(dialect=_DIALETO))
    novo, trocas = re.subn(
        r"^\s*CREATE TABLE\s+(\"?)" + re.escape(tabela.name) + r"\1\s*\(",
        f'CREATE TABLE "{PREFIXO_TEMPORARIO}{tabela.name}" (', ddl, count=1)
    if trocas != 1:
        raise RuntimeError(f"nao reconheci o CREATE TABLE de {tabela.name}")
    return novo


# --------------------------------------------------------------------------- #
# O acerto
# --------------------------------------------------------------------------- #

def _colunas(con, nome: str) -> dict:
    return {linha[1]: bool(linha[3])
            for linha in con.execute(f'PRAGMA table_info("{nome}")')}


def _sql_da_tabela(con, nome: str) -> Optional[str]:
    linha = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (nome,)).fetchone()
    return linha[0] if linha else None


def _indices_existentes(con) -> set:
    return {linha[0] for linha in
            con.execute("SELECT name FROM sqlite_master WHERE type='index'")}


def _problemas_de_fk(con) -> set:
    return {tuple(linha) for linha in con.execute("PRAGMA foreign_key_check")}


def diagnosticar(con) -> dict:
    """{tabela: [motivos]} das tabelas do modelo que existem e ficaram para tras."""
    atrasadas = {}
    for tabela in Base.metadata.sorted_tables:
        sql = _sql_da_tabela(con, tabela.name)
        if sql is None:
            continue            # o `create_all` cria
        motivos = o_que_mudou(_colunas(con, tabela.name), sql, tabela)
        if motivos:
            atrasadas[tabela.name] = motivos
    return atrasadas


def _copia_de_seguranca(con, caminho: str) -> str:
    destino = f"{caminho}.antes-do-acerto-{time.strftime('%Y%m%d-%H%M%S')}"
    alvo = sqlite3.connect(destino)
    try:
        con.backup(alvo)
    finally:
        alvo.close()
    return destino


def _reconstruir(con, tabela, colunas_antigas: dict) -> None:
    temporaria = f"{PREFIXO_TEMPORARIO}{tabela.name}"
    con.execute(f'DROP TABLE IF EXISTS "{temporaria}"')
    con.execute(ddl_temporaria(tabela))
    comuns = [c.name for c in tabela.columns if c.name in colunas_antigas]
    lista = ", ".join(f'"{c}"' for c in comuns)
    con.execute(f'INSERT INTO "{temporaria}" ({lista}) SELECT {lista} FROM "{tabela.name}"')
    con.execute(f'DROP TABLE "{tabela.name}"')
    con.execute(f'ALTER TABLE "{temporaria}" RENAME TO "{tabela.name}"')
    for indice in tabela.indexes:
        con.execute(str(CreateIndex(indice).compile(dialect=_DIALETO)))


def acertar(caminho: str, log: Callable[[str], None] = print) -> dict:
    """Leva as tabelas deste banco SQLite as regras do modelo.

    Devolve o que fez: `{"reconstruidas": {tabela: motivos}, "indices": [...],
    "copia": caminho_da_copia_ou_None, "erro": texto_ou_None}`. Nunca levanta:
    quem chama e o boot, e o motor tem de subir mesmo com o banco torto.
    """
    feito = {"reconstruidas": {}, "indices": [], "copia": None, "erro": None}
    if not caminho or not os.path.exists(caminho):
        return feito
    try:
        con = sqlite3.connect(caminho, timeout=30, isolation_level=None)
    except sqlite3.Error as e:
        feito["erro"] = f"nao abri o banco: {e}"
        log(f"⚠️  Acerto do banco: {feito['erro']}")
        return feito
    try:
        atrasadas = diagnosticar(con)
        if atrasadas:
            try:
                feito["copia"] = _copia_de_seguranca(con, caminho)
            except (sqlite3.Error, OSError) as e:
                # Sem copia, nao mexe: e o dado de quem usa.
                feito["erro"] = f"nao consegui fazer a copia de seguranca ({e})"
                log(f"⚠️  Acerto do banco: {feito['erro']}; nada foi mudado.")
                return feito
            # FORA de transacao: dentro dela o pragma e ignorado em silencio, e
            # o DROP TABLE de uma tabela-mae apagaria as filhas pelo CASCADE.
            con.execute("PRAGMA foreign_keys=OFF")
            try:
                con.execute("BEGIN IMMEDIATE")
                antes = _problemas_de_fk(con)
                for tabela in Base.metadata.sorted_tables:
                    if tabela.name in atrasadas:
                        _reconstruir(con, tabela, _colunas(con, tabela.name))
                novos = _problemas_de_fk(con) - antes
                if novos:
                    raise RuntimeError(f"a troca quebraria {len(novos)} referencia(s) "
                                       f"entre tabelas, ex.: {sorted(novos)[0]}")
                con.execute("COMMIT")
                feito["reconstruidas"] = atrasadas
            except Exception as e:
                try:
                    con.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                feito["erro"] = f"{type(e).__name__}: {e}"
                log(f"⚠️  Acerto do banco: desfeito, nada mudou ({feito['erro']}). "
                    f"Tabelas que ficaram para tras: {', '.join(sorted(atrasadas))}. "
                    f"Copia de seguranca: {feito['copia']}")
                return feito
            finally:
                con.execute("PRAGMA foreign_keys=ON")
            for nome, motivos in atrasadas.items():
                log(f"🔧 Banco: tabela {nome} refeita com as regras novas "
                    f"({'; '.join(motivos)})")
            log(f"🔧 Banco: copia de antes do acerto em {feito['copia']}")

        existentes = _indices_existentes(con)
        for tabela in Base.metadata.sorted_tables:
            if _sql_da_tabela(con, tabela.name) is None:
                continue
            for indice in tabela.indexes:
                if indice.name in existentes:
                    continue
                ddl = str(CreateIndex(indice, if_not_exists=True).compile(dialect=_DIALETO))
                try:
                    con.execute(ddl)
                    feito["indices"].append(indice.name)
                except sqlite3.Error as e:
                    # Um unico que ja tem duplicata: o dado decide, nao o boot.
                    log(f"⚠️  Acerto do banco: nao criei o indice {indice.name} ({e})")
        if feito["indices"]:
            log(f"🔧 Banco: indice(s) que faltavam: {', '.join(feito['indices'])}")
    except sqlite3.Error as e:
        feito["erro"] = f"{type(e).__name__}: {e}"
        log(f"⚠️  Acerto do banco: {feito['erro']}")
    finally:
        con.close()
    return feito
