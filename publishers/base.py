"""Contrato da camada de publicacao -- a secao 6 do Plano Tecnico.

Somente biblioteca padrao, pelo mesmo motivo do `sources/`: a regra de negocio
desta camada e *qual driver atende*, e essa pergunta tem de ser testavel sem
subir o `app.py` inteiro, sem banco e sem cliente HTTP de plataforma nenhuma.
O driver que fala com a rede importa o que precisa dentro do metodo.

**A assinatura da secao 6 e TypeScript, e `Promise<...>` ali descreve o formato
do contrato, nao o modelo de concorrencia.** Aqui `publish` e `capability` sao
sincronos de proposito: o upload do YouTube e uma subida em blocos com uma
biblioteca sincrona, e o pacote do driver `manual` e trabalho de disco. Os dois
rodam num executor a partir do `app.py` -- que e o que o `download_all_clips`
ja faz com o ZIP dele. Prometer `async` aqui so adicionaria uma camada que
envolveria trabalho bloqueante de qualquer jeito.

A regra que sustenta a camada inteira esta em `resolve()`, e nao neste arquivo:
**a cascata automatica so aceita driver de risco zero**. Ver o `__init__.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Os quatro ids da secao 6, mais o do TikTok (etapa 7.3). Mesma lista de
# `db_models.DRIVERS`, repetida aqui para que este modulo nao dependa do
# SQLAlchemy -- um teste compara as duas.
DRIVER_IDS = ("manual", "youtube-api", "aggregator", "browser", "tiktok-api")

# O que `capability()` pode responder, da secao 6.
CAPABILITIES = ("public", "private_only", "draft", "none")


class PublisherError(RuntimeError):
    """Falha esperada de um driver: quota estourada, credencial ausente,
    plataforma recusando. Distinta de um bug, e o que o painel mostra."""


class DriverDesligado(PublisherError):
    """O driver existe e esta desligado nesta instalacao.

    O `browser` nasce assim (secao 1) e e o unico caso em que "desligado" e a
    decisao, nao a ausencia de configuracao.
    """


class QuotaEsgotada(PublisherError):
    """Nao ha unidade de quota para mais um upload hoje.

    E o sinal que tira o `youtube-api` da cascata e faz o corte cair na fila
    manual -- que e o comportamento desejado, nao uma falha do job.
    """


@dataclass(frozen=True)
class Account:
    """A conta de destino: uma linha de `accounts` reduzida ao que o driver le.

    Existe como dataclass, e nao como o modelo do ORM, para manter esta camada
    sem SQLAlchemy -- e porque o driver nao tem o que fazer com a linha inteira.
    `credentials_ref` e endereco de cofre (`vault://...`), nunca o segredo: a
    secao 7 e explicita, e quem resolve o endereco e a camada de cofre.
    """
    id: str
    platform: str
    handle: str
    credentials_ref: Optional[str] = None
    # `auto` e a ausencia de preferencia, e e o padrao da coluna. Ver a nota em
    # `db_models.DRIVER_PREFS`: com `manual` ali, toda conta nasceria presa na
    # fila manual e a cascata da secao 6 nunca escolheria nada.
    driver_pref: str = "auto"


@dataclass(frozen=True)
class RenderedClip:
    """O que o pipeline entrega: um arquivo pronto em disco.

    `job_id` e `index` sao a identidade do corte para o resto do sistema (o
    painel, a pasta, o `clips.render_key`), e por isso viajam junto do caminho:
    sem eles o resultado da publicacao nao tem onde ser gravado de volta.
    """
    path: str
    job_id: str
    index: int
    title: str = ""
    duration_s: float = 0.0
    clip_id: Optional[str] = None


@dataclass(frozen=True)
class PostMeta:
    """Titulo, descricao e hashtags -- ja gerados pelo passo de deteccao.

    A descricao e **por plataforma** porque o `main.py` ja as gera separadas
    (`video_description_for_tiktok`, `..._for_instagram`), e juntar as duas
    numa so perderia o trabalho que o LLM ja fez. `description_for()` escolhe,
    com queda para a primeira que existir -- nao ter descricao para a
    plataforma nao pode impedir a publicacao.
    """
    title: str = ""
    descriptions: dict = field(default_factory=dict)
    hashtags: tuple[str, ...] = ()
    language: str = ""

    def description_for(self, platform: str) -> str:
        texto = (self.descriptions.get(platform) or "").strip()
        if texto:
            return texto
        for valor in self.descriptions.values():
            if (valor or "").strip():
                return valor.strip()
        return ""


@dataclass(frozen=True)
class PublishOptions:
    """Como publicar. `visibility` fica limitada pelo `capability()` da conta:
    pedir `public` numa conta que so consegue `private_only` nao e erro do
    usuario, e o driver quem rebaixa e diz que rebaixou no `detail`.

    Onde publicar nao entra aqui -- e a `Account`, parametro proprio de
    `publish()`. Ver a nota na assinatura.
    """
    visibility: str = "private"
    scheduled_at: Optional[str] = None   # ISO-8601 UTC, ou None para agora
    dry_run: bool = False


@dataclass(frozen=True)
class Cost:
    """O custo de publicar `n` cortes, na forma da secao 6.

    `risk_score` e o campo que importa e o unico sem valor padrao seguro: e ele
    que o resolvedor le para decidir se um driver pode entrar na cascata
    automatica. Escala 0..1, onde 1 e "pode custar a conta".
    """
    risk_score: float
    quota_units: int = 0
    usd: float = 0.0


@dataclass(frozen=True)
class PublishResult:
    """O que aconteceu. `status` usa o vocabulario de `db_models.PUB_STATUSES`
    para que a linha de `publications` seja escrita sem traducao.

    O driver `manual` termina em `scheduled`, e nao em `published`: ele entregou
    o pacote, e quem aperta publicar e a pessoa. Dizer `published` ali seria a
    unica mentira capaz de fazer o sistema contar como postado um corte que
    ninguem postou.
    """
    ok: bool
    driver: str
    status: str = "scheduled"
    remote_id: Optional[str] = None
    url: Optional[str] = None
    detail: str = ""
    artifacts: tuple[str, ...] = ()


class Publisher:
    """Um destino de publicacao.

    `disponivel()` e o acrescimo a secao 6: ela escreve `youtubeApi.ifQuotaLeft()
    ?? aggregator.ifSubscribed()`, duas perguntas com nomes diferentes que o
    resolvedor faz no mesmo lugar e pelo mesmo motivo -- "este driver atende
    agora?". Um nome so, porque um driver novo nao deveria precisar ensinar ao
    resolvedor o nome da sua propria condicao.
    """

    id: str = ""
    label: str = ""
    platforms: tuple[str, ...] = ()

    def disponivel(self, account: Account) -> bool:
        """Se este driver pode assumir uma publicacao agora. Barato e sem rede:
        e chamado por driver, em ordem, para toda publicacao."""
        return False

    def capability(self, account: Account) -> str:
        """Ate onde este driver consegue publicar nesta conta (secao 6)."""
        return "none"

    def cost(self, n: int) -> Cost:
        raise NotImplementedError

    def publish(self, clip: RenderedClip, meta: PostMeta,
                opts: PublishOptions, account: Account) -> PublishResult:
        """Publica um corte.

        **A `account` e um parametro a mais do que a secao 6 escreve**, e a
        ausencia dela la e um descuido do pseudocodigo: o `resolve(platform,
        account)` e o `capability(account)` da mesma secao mostram que a conta
        faz parte do endereco, e nenhum driver funciona sem ela -- o `manual`
        precisa da plataforma para escolher o texto, o `youtube-api` precisa do
        `credentials_ref` para achar o token. Ela vem separada das `opts`
        porque nao e uma opcao: e para onde vai.
        """
        raise NotImplementedError
