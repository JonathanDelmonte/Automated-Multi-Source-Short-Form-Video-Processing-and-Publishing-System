"""A automacao por canal: a receita, a caixa de entrada e a de aprovacao (7.5).

"O canal infantil, com o PC ligado e ninguem mexendo, acha um video com
licenca, corta, espera a aprovacao (ou nao, se o canal estiver assim) e posta
nos horarios dele, com o credito na descricao" -- o "pronto quando" da etapa.

Este modulo e a metade que fala com o banco: a receita de cada canal, os
videos que ela achou (`candidates`), o que ja foi usado (o "nao repetir"), o
estoque de cortes esperando a vez e a caixa de aprovacao. A outra metade -- o
laco, a busca na rede e a criacao do job -- mora no `app.py`, que e quem tem a
fila de jobs e o `/api/process`.

As regras que moram aqui, e por que:

- **Um video de cada vez por receita.** O job e o recurso caro (placa,
  transcricao, cota de IA); a receita espera o dela terminar antes do proximo.
- **O estoque manda, nao o relogio.** Com cortes suficientes para os proximos
  `DIAS_DE_ESTOQUE` dias (agendados + esperando aprovacao), a receita nao corta
  mais nada. Sem isso, um canal que posta 3 por dia e corta 5 por video
  acumularia uma pilha que ninguem vai postar -- e no canal com aprovacao, a
  pilha seria de coisas esperando a pessoa.
- **Nao repetir, nem entre canais.** O mesmo video (a mesma `key`) nao e cortado
  duas vezes pela automacao, venha de que receita vier; e o que alguem ja
  cortou a mao tambem conta.
- **O CRUD levanta, o laco nao.** Salvar a receita e acao de quem esta na tela
  (erro vira 400/503 com o motivo); o que o laco faz sozinho falha aberto e
  anota o erro no estado da receita, para a tela mostrar.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from datetime import datetime, time as _time, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func, select as _select, update as _update

import db
import db_models
import licencas
import receitas

#: Quantos dias de posts o estoque segura antes de a receita parar de cortar.
DIAS_DE_ESTOQUE = 2
#: De quanto em quanto tempo a receita busca video novo, no maximo, quando a
#: caixa de entrada esvaziou. A busca pela API gasta uma das 100 do dia, e a
#: do yt-dlp, uma pagina por video conferido.
HORAS_ENTRE_BUSCAS_PADRAO = 6
EXTENSOES_DE_VIDEO = (".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi")
#: Arquivo mais novo que isto na pasta pode estar sendo copiado ainda.
IDADE_MINIMA_DO_ARQUIVO_S = 120
#: O quanto de cada ponta do arquivo entra na chave dele: o conteudo, e nao o
#: nome, e o que diz que dois arquivos sao o mesmo video.
_BYTES_DA_CHAVE = 1024 * 1024

#: Status em que a fonte ja foi (ou esta sendo) usada.
USADOS = ("processando", "processado")
#: Status que esperam a vez, na ordem de prioridade.
NA_FILA = ("escolhido", "novo")


class AutomacaoError(ValueError):
    """Pedido recusado por uma regra; o texto vai para a tela como esta."""


def horas_entre_buscas() -> int:
    try:
        return max(1, int(os.environ.get("AUTOMACAO_BUSCA_HORAS") or HORAS_ENTRE_BUSCAS_PADRAO))
    except ValueError:
        return HORAS_ENTRE_BUSCAS_PADRAO


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(quando: Optional[datetime]) -> Optional[str]:
    if quando is None:
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return quando.isoformat()


# --------------------------------------------------------------------------- #
# A receita
# --------------------------------------------------------------------------- #

def _receita_json(linha, canal_id: str) -> dict:
    if linha is None:
        spec = receitas.normalizar(None)
        return {"id": None, "channel_id": canal_id, "kind": "cortes", "ativa": False,
                "spec": spec, "estado": {}, "pronta": receitas.pronta(spec),
                "precisa_de_direitos": receitas.precisa_de_direitos(spec),
                "pasta": None, "updated_at": None}
    try:
        spec = receitas.normalizar(linha.spec_json)
    except receitas.ReceitaInvalida:
        spec = receitas.normalizar(None)
    estado = dict(linha.state_json or {})
    return {"id": linha.id, "channel_id": canal_id, "kind": linha.kind,
            "ativa": bool(linha.active), "spec": spec, "estado": estado,
            "pronta": receitas.pronta(spec),
            "precisa_de_direitos": receitas.precisa_de_direitos(spec),
            "pasta": _descricao_da_pasta(estado.get("pasta")),
            "updated_at": _iso(linha.updated_at)}


async def _linha_da_receita(t, canal_id: str, kind: str = "cortes"):
    achadas = await t.all(db_models.Recipe, db_models.Recipe.channel_id == canal_id,
                          db_models.Recipe.kind == kind)
    return achadas[0] if achadas else None


async def obter_receita(canal_id: str) -> Optional[dict]:
    """A receita do canal (a padrao, desligada, se ainda nao ha), ou None se o
    canal nao existe."""
    async with db.tenant() as t:
        canal = await t.get(db_models.Channel, canal_id)
        if canal is None:
            return None
        return _receita_json(await _linha_da_receita(t, canal_id), canal_id)


async def salvar_receita(canal_id: str, spec: Optional[dict], ativa: Optional[bool] = None,
                         confirmar_direitos: bool = False) -> Optional[dict]:
    """Grava a receita e devolve como a tela a le. None: canal nao existe.

    **A confirmacao de direitos e sobre a fonte que estava na tela.** Trocar os
    links, o canal da Twitch ou o tipo da fonte apaga a confirmacao anterior:
    quem confirmou os direitos sobre uma lista nao confirmou sobre a proxima.
    """
    async with db.tenant() as t:
        canal = await t.get(db_models.Channel, canal_id)
        if canal is None:
            return None
        linha = await _linha_da_receita(t, canal_id)
        base = None
        if linha is not None:
            try:
                base = receitas.normalizar(linha.spec_json)
            except receitas.ReceitaInvalida:
                base = None
        try:
            novo = receitas.normalizar(spec, base=base)
        except receitas.ReceitaInvalida as e:
            raise AutomacaoError(str(e))
        if confirmar_direitos:
            novo["direitos"] = _agora().isoformat(timespec="seconds")
        elif base is None or not receitas.mesma_fonte(base, novo):
            novo["direitos"] = None
        else:
            novo["direitos"] = base.get("direitos")
        template_id = novo["edicao"].get("template_id")
        if template_id and await t.get(db_models.Template, template_id) is None:
            raise AutomacaoError("o template escolhido não existe mais")
        ligar = bool(linha.active) if (ativa is None and linha is not None) else bool(ativa)
        if ligar:
            falta = receitas.pronta(novo)
            if falta:
                raise AutomacaoError(f"a receita não pode ser ligada: {falta}")
        if linha is None:
            linha = t.add(db_models.Recipe(channel_id=canal_id, kind="cortes",
                                           active=ligar, spec_json=novo, state_json={}))
        else:
            linha.spec_json = novo
            linha.active = ligar
            linha.updated_at = _agora()
        if novo["fonte"]["tipo"] == "pasta":
            estado = dict(linha.state_json or {})
            if not estado.get("pasta"):
                estado["pasta"] = _nova_pasta(canal.name)
                linha.state_json = estado
            _criar_pasta(estado["pasta"])
        await t.commit()
        return _receita_json(linha, canal_id)


async def receitas_ativas() -> list:
    """`[{id, tenant_id, channel_id}]` de todas as receitas ligadas.

    **Sessao crua, atravessando os tenants**, como `publish_queue.devidas`: o
    laco e do servidor. Quem cuida de cada receita repoe o tenant dela antes.
    """
    async with db.session() as s:
        linhas = (await s.execute(
            _select(db_models.Recipe.id, db_models.Recipe.tenant_id,
                    db_models.Recipe.channel_id)
            .where(db_models.Recipe.active.is_(True))
            .order_by(db_models.Recipe.created_at))).all()
    return [{"id": i, "tenant_id": t, "channel_id": c} for i, t, c in linhas]


async def receita_por_id(recipe_id: str):
    async with db.tenant() as t:
        return await t.get(db_models.Recipe, recipe_id)


async def anotar(recipe_id: str, **campos) -> None:
    """Acrescenta ao estado da receita o que o laco quer que a tela veja.
    Nunca levanta: anotar e o que se faz quando alguma coisa ja deu errado."""
    try:
        async with db.tenant() as t:
            linha = await t.get(db_models.Recipe, recipe_id)
            if linha is None:
                return
            estado = dict(linha.state_json or {})
            estado.update(campos)
            linha.state_json = estado
            await t.commit()
    except Exception as e:
        print(f"⚠️  Automacao: nao consegui anotar na receita {recipe_id} ({e})")


# --------------------------------------------------------------------------- #
# A pasta de entrada do canal
# --------------------------------------------------------------------------- #

def raiz_das_pastas() -> str:
    base = (os.environ.get("DATA_DIR") or "").strip() or "data"
    return os.path.join(base, "entrada")


def _slug(nome: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", nome or "")
                         if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return slug[:40] or "canal"


def _nova_pasta(nome_do_canal: str) -> str:
    """Um nome de pasta que ainda nao existe. Fica no ESTADO da receita, e nao
    no nome do canal: renomear o canal nao pode mudar a pasta de lugar."""
    raiz = raiz_das_pastas()
    base = _slug(nome_do_canal)
    nome, n = base, 2
    while os.path.exists(os.path.join(raiz, nome)):
        nome, n = f"{base}-{n}", n + 1
    return nome


def _pasta_segura(nome: Optional[str]) -> Optional[str]:
    """O caminho da pasta, so se o nome for um que o programa daria."""
    if not isinstance(nome, str) or not re.match(r"^[a-z0-9][a-z0-9-]{0,50}$", nome):
        return None
    return os.path.join(raiz_das_pastas(), nome)


def _criar_pasta(nome: str) -> None:
    caminho = _pasta_segura(nome)
    if caminho:
        try:
            os.makedirs(caminho, exist_ok=True)
        except OSError as e:
            print(f"⚠️  Nao consegui criar a pasta de entrada {caminho}: {e}")


def _descricao_da_pasta(nome: Optional[str]) -> Optional[dict]:
    """Para a tela: o nome e o caminho. No Docker o caminho e o de dentro do
    container (`/app/data/entrada/...`), e a tela traduz para a pasta do
    projeto no Windows; no ajudante e o caminho do Windows mesmo."""
    caminho = _pasta_segura(nome)
    if not caminho:
        return None
    return {"nome": nome, "caminho": os.path.abspath(caminho),
            "relativo": os.path.join("data", "entrada", nome)}


def chave_do_arquivo(caminho: str) -> Optional[str]:
    """`pasta:<hash>` pelo CONTEUDO (tamanho e as duas pontas), nao pelo nome:
    o mesmo video posto de novo com outro nome continua sendo o mesmo."""
    try:
        tamanho = os.path.getsize(caminho)
        h = hashlib.sha1(str(tamanho).encode())
        with open(caminho, "rb") as f:
            h.update(f.read(_BYTES_DA_CHAVE))
            if tamanho > 2 * _BYTES_DA_CHAVE:
                f.seek(-_BYTES_DA_CHAVE, os.SEEK_END)
                h.update(f.read(_BYTES_DA_CHAVE))
    except OSError:
        return None
    return "pasta:" + h.hexdigest()[:24]


def arquivos_da_pasta(nome: Optional[str], agora: Optional[float] = None) -> list:
    """Os videos prontos na pasta: `[{nome, caminho, tamanho, chave}]`.

    Pronto = tamanho maior que zero e sem mudanca ha `IDADE_MINIMA_DO_ARQUIVO_S`
    -- um arquivo que o Windows ainda esta copiando para ca nao e cortado pela
    metade.
    """
    import time as _t

    caminho = _pasta_segura(nome)
    if not caminho or not os.path.isdir(caminho):
        return []
    agora = agora or _t.time()
    saida = []
    for entrada in sorted(os.scandir(caminho), key=lambda e: e.name.lower()):
        if not entrada.is_file() or not entrada.name.lower().endswith(EXTENSOES_DE_VIDEO):
            continue
        try:
            info = entrada.stat()
        except OSError:
            continue
        if info.st_size <= 0 or agora - info.st_mtime < IDADE_MINIMA_DO_ARQUIVO_S:
            continue
        chave = chave_do_arquivo(entrada.path)
        if chave:
            saida.append({"nome": entrada.name, "caminho": entrada.path,
                          "tamanho": info.st_size, "chave": chave})
    return saida


def caminho_do_arquivo(nome_da_pasta: Optional[str], nome_do_arquivo: str) -> Optional[str]:
    """O caminho de um arquivo DENTRO da pasta do canal, ou None -- o nome vem
    do banco, e nunca vira caminho fora dela."""
    pasta = _pasta_segura(nome_da_pasta)
    if not pasta or not nome_do_arquivo or os.path.basename(nome_do_arquivo) != nome_do_arquivo:
        return None
    caminho = os.path.join(pasta, nome_do_arquivo)
    return caminho if os.path.isfile(caminho) else None


# --------------------------------------------------------------------------- #
# Os candidatos -- a caixa de entrada de fontes
# --------------------------------------------------------------------------- #

def _candidato_json(c) -> dict:
    return {
        "id": c.id, "recipe_id": c.recipe_id, "key": c.key, "url": c.url,
        "title": c.title, "author": c.author, "author_url": c.author_url,
        "duration_s": c.duration_s, "published_at": _iso(c.published_at),
        "thumbnail": c.thumbnail, "views": c.views, "license": c.license,
        "license_text": c.license_text, "status": c.status, "reason": c.reason,
        "job_id": c.job_id, "found_at": _iso(c.found_at), "decided_at": _iso(c.decided_at),
        "credito": licencas.credito({"license": c.license, "title": c.title,
                                     "author": c.author, "url": c.url,
                                     "published_at": c.published_at}),
    }


async def chaves_usadas(t) -> set:
    """Toda chave de video que ja foi cortado neste tenant: pela automacao (em
    qualquer receita), ou a mao (a origem gravada e a URL das fontes)."""
    usadas = set()
    for (chave,) in (await t.session.execute(
            _select(db_models.Candidate.key)
            .where(db_models.Candidate.tenant_id == t.tenant_id)
            .where(db_models.Candidate.status.in_(USADOS)))).all():
        usadas.add(chave)
    for (chave,) in (await t.session.execute(
            _select(db_models.SourceLicense.key)
            .where(db_models.SourceLicense.tenant_id == t.tenant_id)
            .where(db_models.SourceLicense.key.is_not(None)))).all():
        usadas.add(chave)
    for (entrada,) in (await t.session.execute(
            _select(db_models.Source.input)
            .where(db_models.Source.tenant_id == t.tenant_id)
            .where(db_models.Source.adapter != "upload"))).all():
        chave = licencas.chave(entrada)
        if chave:
            usadas.add(chave)
    return usadas


async def chaves_conhecidas(recipe_id: str) -> set:
    """As chaves que a busca desta receita nao precisa conferir de novo: as
    candidatas dela (inclusive as recusadas) e tudo o que ja foi usado."""
    async with db.tenant() as t:
        daqui = {k for (k,) in (await t.session.execute(
            _select(db_models.Candidate.key)
            .where(db_models.Candidate.tenant_id == t.tenant_id)
            .where(db_models.Candidate.recipe_id == recipe_id))).all()}
        return daqui | await chaves_usadas(t)


def _data(valor) -> Optional[datetime]:
    dia = licencas._data(valor)
    return datetime(dia.year, dia.month, dia.day, tzinfo=timezone.utc) if dia else None


async def acrescentar_candidatos(recipe_id: str, achados: Iterable[dict],
                                 recusados: Iterable[dict] = ()) -> int:
    """Grava os videos novos que a busca achou. Devolve quantos entraram na
    fila (os recusados entram como `recusado`, com o motivo, para a busca nao
    os conferir de novo amanha e a tela poder mostrar por que ficaram de fora).
    """
    novos = 0
    async with db.tenant() as t:
        existentes = {k for (k,) in (await t.session.execute(
            _select(db_models.Candidate.key)
            .where(db_models.Candidate.tenant_id == t.tenant_id)
            .where(db_models.Candidate.recipe_id == recipe_id))).all()}
        usadas = await chaves_usadas(t)
        for achado, recusado in [(a, False) for a in achados] + [(r, True) for r in recusados]:
            chave = (achado or {}).get("key")
            url = (achado or {}).get("url")
            if not chave or not url or chave in existentes:
                continue
            existentes.add(chave)
            status, motivo = "novo", None
            if recusado:
                status, motivo = "recusado", achado.get("motivo") or "ficou de fora da busca"
            elif chave in usadas:
                status, motivo = "repetido", "já foi cortado antes (neste ou em outro canal)"
            t.add(db_models.Candidate(
                recipe_id=recipe_id, key=chave[:255], url=url,
                title=(achado.get("title") or "")[:300] or None,
                author=(achado.get("author") or "")[:200] or None,
                author_url=achado.get("author_url"),
                duration_s=achado.get("duration_s") if isinstance(achado.get("duration_s"), int) else None,
                published_at=_data(achado.get("published_at")),
                thumbnail=achado.get("thumbnail"),
                views=achado.get("views") if isinstance(achado.get("views"), int) else None,
                license=licencas.normalizar(achado.get("license")),
                license_text=(achado.get("license_text") or "")[:200] or None,
                status=status, reason=motivo,
                decided_at=_agora() if status != "novo" else None))
            if status == "novo":
                novos += 1
        await t.commit()
    return novos


async def listar_candidatos(canal_id: str, status: Optional[str] = None,
                            limite: int = 200) -> Optional[list]:
    """A caixa de entrada do canal, da mais nova para a mais antiga. None se o
    canal nao existe."""
    async with db.tenant() as t:
        if await t.get(db_models.Channel, canal_id) is None:
            return None
        receita = await _linha_da_receita(t, canal_id)
        if receita is None:
            return []
        filtros = [db_models.Candidate.recipe_id == receita.id]
        if status:
            filtros.append(db_models.Candidate.status == status)
        linhas = await t.all(db_models.Candidate, *filtros)
    linhas = sorted(linhas, key=lambda c: (c.found_at or _agora()), reverse=True)
    return [_candidato_json(c) for c in linhas[:max(1, min(500, int(limite)))]]


#: O que a pessoa pode fazer com um candidato, e de onde para onde.
_ACOES = {
    "escolher": (("novo", "recusado", "falhou"), "escolhido"),
    "recusar": (("novo", "escolhido", "falhou"), "recusado"),
    "voltar": (("escolhido", "recusado", "falhou"), "novo"),
}


async def decidir_candidato(candidato_id: str, acao: str) -> Optional[dict]:
    """`escolher` (cortar este antes dos outros), `recusar` ou `voltar`.

    **Escolher um video que a busca recusou nao passa por cima da licenca.**
    A busca recusou porque o YouTube nao confirmou a licenca livre; se a pessoa
    escolhe assim mesmo, o video entra como os links: sob a confirmacao de
    direitos dela, que a receita de busca nao tem. Por isso so vale para o que
    a receita recusou por duracao ou por ja ter sido usado -- licenca nao
    conferida continua recusada.
    """
    if acao not in _ACOES:
        raise AutomacaoError("ação tem de ser escolher, recusar ou voltar")
    de, para = _ACOES[acao]
    async with db.tenant() as t:
        c = await t.get(db_models.Candidate, candidato_id)
        if c is None:
            return None
        if c.status not in de:
            raise AutomacaoError(f"este vídeo está {c.status}; não dá para {acao}")
        if para in NA_FILA and c.license not in licencas.LIVRES:
            receita = await t.get(db_models.Recipe, c.recipe_id)
            tipo = ((receita.spec_json or {}).get("fonte") or {}).get("tipo") if receita else None
            if tipo == "busca":
                raise AutomacaoError(
                    "o YouTube não confirmou a licença livre deste vídeo; a busca só "
                    "corta vídeo com licença conferida")
        if para in NA_FILA and c.key in await chaves_usadas(t):
            raise AutomacaoError("este vídeo já foi cortado antes (neste ou em outro canal)")
        c.status = para
        c.reason = "escolhido por você" if para == "escolhido" else (
            "recusado por você" if para == "recusado" else None)
        c.decided_at = _agora()
        await t.commit()
        return _candidato_json(c)


async def proximo_candidato(recipe_id: str):
    """O proximo da fila (os escolhidos primeiro, depois os mais antigos), ja
    conferido contra o "nao repetir". O que outro canal usou nesse meio tempo
    vira `repetido` aqui mesmo."""
    async with db.tenant() as t:
        usadas = await chaves_usadas(t)
        fila = await t.all(db_models.Candidate,
                           db_models.Candidate.recipe_id == recipe_id,
                           db_models.Candidate.status.in_(NA_FILA))
        fila.sort(key=lambda c: (0 if c.status == "escolhido" else 1,
                                 c.decided_at or c.found_at or _agora(),
                                 c.found_at or _agora()))
        escolhido = None
        for c in fila:
            if c.key in usadas:
                c.status, c.reason, c.decided_at = (
                    "repetido", "já foi cortado antes (neste ou em outro canal)", _agora())
                continue
            escolhido = c
            break
        await t.commit()
        return escolhido


async def marcar_candidato(candidato_id: str, status: str, *, job_id: Optional[str] = None,
                           motivo: Optional[str] = None) -> None:
    async with db.tenant() as t:
        c = await t.get(db_models.Candidate, candidato_id)
        if c is None:
            return
        c.status = status
        if job_id:
            c.job_id = job_id
        c.reason = (motivo or "")[:1000] or None
        c.decided_at = _agora()
        await t.commit()


async def candidato_do_job(job_id: str):
    async with db.tenant() as t:
        achados = await t.all(db_models.Candidate, db_models.Candidate.job_id == job_id)
        return achados[0] if achados else None


async def em_andamento(recipe_id: str):
    async with db.tenant() as t:
        achados = await t.all(db_models.Candidate,
                              db_models.Candidate.recipe_id == recipe_id,
                              db_models.Candidate.status == "processando")
        return achados[0] if achados else None


async def cortados_hoje(recipe_id: str, fuso, agora: Optional[datetime] = None) -> int:
    """Quantos videos esta receita mandou cortar hoje, no dia de quem usa."""
    agora = (agora or _agora()).astimezone(fuso)
    comeco = datetime.combine(agora.date(), _time(0), tzinfo=fuso).astimezone(timezone.utc)
    async with db.tenant() as t:
        return len(await t.all(
            db_models.Candidate, db_models.Candidate.recipe_id == recipe_id,
            db_models.Candidate.status.in_(USADOS + ("falhou",)),
            db_models.Candidate.job_id.is_not(None),
            db_models.Candidate.decided_at >= comeco))


# --------------------------------------------------------------------------- #
# O estoque do canal
# --------------------------------------------------------------------------- #

async def estoque_do_canal(canal_id: str, agora: Optional[datetime] = None) -> dict:
    """`{"agendados", "esperando_aprovacao", "total"}`: os cortes do canal que
    ainda vao ao ar. Agendados contam pela conta que mais tem -- num canal com
    YouTube e TikTok, um corte e dois galhos, e o que importa e quantos dias de
    post ha pela frente."""
    agora = agora or _agora()
    async with db.tenant() as t:
        contas = [l.account_id for l in await t.all(
            db_models.ChannelAccount, db_models.ChannelAccount.channel_id == canal_id)]
        por_conta: dict = {}
        if contas:
            for (conta, n) in (await t.session.execute(
                    _select(db_models.Publication.account_id, func.count())
                    .where(db_models.Publication.tenant_id == t.tenant_id)
                    .where(db_models.Publication.account_id.in_(contas))
                    .where(db_models.Publication.status == "scheduled")
                    .where(db_models.Publication.scheduled_at.is_not(None))
                    .where(db_models.Publication.scheduled_at > agora)
                    .group_by(db_models.Publication.account_id))).all():
                por_conta[conta] = int(n)
        esperando = len(await t.all(
            db_models.ClipApproval, db_models.ClipApproval.channel_id == canal_id,
            db_models.ClipApproval.status == "esperando"))
    agendados = max(por_conta.values()) if por_conta else 0
    return {"agendados": agendados, "esperando_aprovacao": esperando,
            "total": agendados + esperando}


# --------------------------------------------------------------------------- #
# A caixa de aprovacao
# --------------------------------------------------------------------------- #

async def criar_aprovacoes(canal_id: str, clip_ids: Iterable[str]) -> int:
    """Poe os cortes na caixa de aprovacao do canal. Idempotente por corte."""
    criadas = 0
    async with db.tenant() as t:
        ja = {a.clip_id for a in await t.all(db_models.ClipApproval)}
        for clip_id in dict.fromkeys(clip_ids):
            if clip_id in ja:
                continue
            t.add(db_models.ClipApproval(clip_id=clip_id, channel_id=canal_id,
                                         status="esperando"))
            criadas += 1
        await t.commit()
    return criadas


def _na_ordem_da_caixa(aprovacoes: list, cortes: dict) -> list:
    """O projeto mais novo primeiro e, dentro dele, na ordem dos cortes
    (corte 1, 2...). As aprovacoes de um mesmo job nascem com microssegundos
    de diferenca: ordenar so pela hora as punha ao contrario, o corte 4 antes
    do 1."""
    def instante(quando):
        if quando is None:
            return _agora().timestamp()
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone.utc)
        return quando.timestamp()

    def job_de(a):
        corte = cortes.get(a.clip_id)
        return corte.job_id if corte else ""

    def indice_de(a):
        corte = cortes.get(a.clip_id)
        try:
            return int(((corte.rubric_json or {}) if corte else {}).get("clip_index") or 0)
        except (TypeError, ValueError):
            return 0

    mais_nova = {}
    for a in aprovacoes:
        job = job_de(a)
        mais_nova[job] = max(mais_nova.get(job, float("-inf")), instante(a.created_at))
    return sorted(aprovacoes, key=lambda a: (-mais_nova[job_de(a)], job_de(a), indice_de(a)))


async def listar_aprovacoes(canal_id: Optional[str] = None,
                            status: Optional[str] = "esperando") -> list:
    """As aprovacoes (do canal, ou de todos), com o corte de cada uma."""
    async with db.tenant() as t:
        filtros = []
        if canal_id:
            filtros.append(db_models.ClipApproval.channel_id == canal_id)
        if status:
            filtros.append(db_models.ClipApproval.status == status)
        aprovacoes = await t.all(db_models.ClipApproval, *filtros)
        cortes = {c.id: c for c in await t.all(
            db_models.Clip, db_models.Clip.id.in_([a.clip_id for a in aprovacoes]))} if aprovacoes else {}
    saida = []
    for a in _na_ordem_da_caixa(aprovacoes, cortes):
        corte = cortes.get(a.clip_id)
        rubrica = (corte.rubric_json or {}) if corte else {}
        duracao = None
        if "start_s" in rubrica and "end_s" in rubrica:
            duracao = max(0.0, float(rubrica["end_s"]) - float(rubrica["start_s"]))
        saida.append({
            "id": a.id, "status": a.status, "channel_id": a.channel_id,
            "created_at": _iso(a.created_at), "decided_at": _iso(a.decided_at),
            "clip": {"id": a.clip_id,
                     "job_id": corte.job_id if corte else None,
                     "clip_index": int(rubrica.get("clip_index") or 0),
                     "titulo": rubrica.get("video_title_for_youtube_short")
                               or rubrica.get("viral_hook_text"),
                     "score": corte.score if corte else None,
                     "duracao_s": duracao,
                     "render_key": corte.render_key if corte else None},
        })
    return saida


async def decidir_aprovacoes(ids: Iterable[str], decisao: str) -> list:
    """Marca as aprovacoes e devolve as que MUDARAM (`[{id, clip_id,
    channel_id}]`) -- so as que estavam esperando. Quem chama agenda as
    aprovadas: agendar e com o `app.py`, que conhece os arquivos."""
    if decisao not in ("aprovar", "recusar"):
        raise AutomacaoError("decisão tem de ser aprovar ou recusar")
    status = "aprovado" if decisao == "aprovar" else "recusado"
    mudadas = []
    async with db.tenant() as t:
        for aprovacao in await t.all(db_models.ClipApproval,
                                     db_models.ClipApproval.id.in_(list(ids))):
            if aprovacao.status != "esperando":
                continue
            aprovacao.status = status
            aprovacao.decided_at = _agora()
            mudadas.append({"id": aprovacao.id, "clip_id": aprovacao.clip_id,
                            "channel_id": aprovacao.channel_id})
        await t.commit()
    return mudadas


async def voltar_aprovacao(aprovacao_id: str) -> None:
    """Desfaz uma aprovacao cujo agendamento falhou: ela volta a esperar."""
    async with db.session() as s:
        await s.execute(_update(db_models.ClipApproval)
                        .where(db_models.ClipApproval.id == aprovacao_id)
                        .values(status="esperando", decided_at=None))
        await s.commit()


async def esperando_por_canal() -> dict:
    """`{canal: quantos cortes esperam aprovacao}`, para o Inicio e a lista."""
    async with db.tenant() as t:
        linhas = (await t.session.execute(
            _select(db_models.ClipApproval.channel_id, func.count())
            .where(db_models.ClipApproval.tenant_id == t.tenant_id)
            .where(db_models.ClipApproval.status == "esperando")
            .group_by(db_models.ClipApproval.channel_id))).all()
    return {canal: int(n) for canal, n in linhas}
