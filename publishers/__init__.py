"""Camada de publicacao: o registro e o resolvedor da secao 6.

A cascata do plano:

    resolve(platform, account) =>
      youtubeApi.ifQuotaLeft() ?? aggregator.ifSubscribed() ?? manualQueue
      // browser NUNCA entra aqui automaticamente

**O "NUNCA" nao esta escrito como uma excecao pelo nome.** Um `if driver.id ==
"browser": continue` funcionaria hoje e falharia no dia em que existir um
segundo driver arriscado -- porque ninguem se lembra de uma lista de excecoes
ao adicionar coisa nova. A regra e sobre a propriedade, nao sobre o nome: **a
cascata automatica so aceita driver de risco zero**, e o `risk_score` que a
secao 6 ja pedia na assinatura de `cost()` e o que responde. O `browser` sai
por ter 1.0; um driver arriscado futuro sai pelo mesmo motivo, sem que ninguem
precise ter lembrado dele aqui.

Sao tres camadas de protecao, e nenhuma depende das outras:

1. o `risk_score` acima do teto tira o driver da cascata;
2. o `manual` responde `disponivel()` sempre e **encerra** a cascata -- nada
   registrado depois dele e alcancavel por `resolve()`, e o `browser` esta
   depois dele;
3. o proprio `browser.disponivel()` exige `PUBLISHER_BROWSER=1`, entao mesmo o
   caminho explicito (`driver_por_id`) so responde numa instalacao que ligou.

`driver_pref` da conta e uma **preferencia dentro do que a cascata ja aceita**,
nunca uma ampliacao: preferir um driver arriscado nao o torna elegivel. E o que
impede um clique errado no painel de virar uma conta banida. O padrao e `auto`
-- nenhuma preferencia, vale a ordem do registro. Ver a nota em
`db_models.DRIVER_PREFS` para o motivo de `auto` existir: o default anterior
(`manual`) transformava toda conta numa decisao que ninguem tomou.

**A porta do consentimento (etapa 7.9, ADR-016).** O plano previa a frota "com
a mesma trava: risco acima de zero, entao nunca entra na cascata automatica sem
a conta ter pedido". O pedido e o `Account.consentimentos`, que so o banco
preenche (`device_accounts.consent_at`, com um CHECK); e so vale para driver
que declara `aceita_consentimento` -- o `browser` nao declara. O teto continua
zero para todo o resto, e a preferencia continua sem ampliar nada.
"""
from __future__ import annotations

from typing import Optional

# Os submodulos entram no namespace de proposito: o `app.py` faz apenas
# `import publishers` e usa `publishers.pacote.Item` / `publishers.quota`. Sem
# esta linha isso e `AttributeError` em producao e passa no teste, porque o
# arquivo de teste do pacote importa `from publishers import pacote` e o import
# de la deixa o atributo posto para todo mundo.
from . import pacote, quota
from .aggregator import AggregatorPublisher
from .base import (CAPABILITIES, DRIVER_IDS, Account, AparelhoDaConta, Cost,
                   DriverDesligado, PostMeta, PublishOptions, PublishResult,
                   Publisher, PublisherError, QuotaEsgotada, RenderedClip)
from .aparelho import AparelhoAutoPublisher, AparelhoPublisher
from .browser import BrowserPublisher
from .manual import ManualPublisher
from .tiktok_api import TikTokApiPublisher
from .youtube_api import YouTubeApiPublisher

# O teto de risco da cascata automatica. Zero, e nao "baixo": nao existe risco
# de conta aceitavel para ganhar automacao que a fila manual ja resolve.
RISCO_MAXIMO_AUTOMATICO = 0.0

# A ordem E a cascata da secao 6, na letra:
#
#     youtubeApi.ifQuotaLeft() ?? aggregator.ifSubscribed() ?? manualQueue
#
# O `manual` e o piso e termina a busca; o `browser` fica depois dele de
# proposito, para que nem um erro no teto de risco o torne alcancavel.
REGISTRY: tuple[type[Publisher], ...] = (
    # A frota (7.9) vem antes das APIs: ligar uma conta a um aparelho e dizer
    # "esta conta posta por aqui" -- e, antes das auditorias, a API do YouTube
    # so sobe privado e a do TikTok so `SELF_ONLY`. Conta sem aparelho nao muda
    # nada: os dois respondem `disponivel()` falso para ela.
    AparelhoAutoPublisher,
    AparelhoPublisher,
    YouTubeApiPublisher,
    # O TikTok pela API oficial (etapa 7.3): risco zero como o do YouTube, e
    # antes do agregador e do piso pela mesma razao.
    TikTokApiPublisher,
    AggregatorPublisher,
    ManualPublisher,
    BrowserPublisher,
)

__all__ = [
    "Account", "AparelhoDaConta", "CAPABILITIES", "Cost", "DRIVER_IDS", "DriverDesligado",
    "PostMeta", "PublishOptions", "PublishResult", "Publisher",
    "PublisherError", "QuotaEsgotada", "REGISTRY", "RenderedClip",
    "RISCO_MAXIMO_AUTOMATICO", "capabilities_de", "consentiu", "driver_por_id",
    "driver_ids", "entra_na_cascata", "pacote", "quota", "resolve",
]


def driver_ids() -> tuple[str, ...]:
    """Os ids registrados, na ordem da cascata. `db_models.DRIVERS` e a mesma
    lista do lado do banco -- um teste compara as duas, porque um id que o
    `CHECK` da coluna nao conhece so falharia ao gravar a publicacao, depois do
    upload inteiro."""
    return tuple(cls.id for cls in REGISTRY)


def entra_na_cascata(driver: Publisher) -> bool:
    """Se este driver pode ser escolhido sem intervencao humana."""
    return driver.cost(1).risk_score <= RISCO_MAXIMO_AUTOMATICO


def consentiu(account: Account, driver: Publisher) -> bool:
    """A conta pediu ESTE driver arriscado, e ele aceita ser pedido (ADR-016).
    Os dois lados precisam ceder: o consentimento vem do banco, e o atributo e
    do proprio driver -- o `browser` nao o declara, e nenhum consentimento o
    alcanca."""
    return (bool(getattr(driver, "aceita_consentimento", False))
            and driver.id in (account.consentimentos or frozenset()))


def driver_por_id(driver_id: str) -> Publisher:
    """O driver com este id, arriscado ou nao.

    E por aqui, e so por aqui, que o `browser` e alcancavel -- o caminho
    "ligado a mao" da secao 6. Quem chama esta dizendo o nome.
    """
    for cls in REGISTRY:
        if cls.id == driver_id:
            return cls()
    raise KeyError(f"driver desconhecido: {driver_id!r}")


def resolve(platform: str, account: Account) -> Publisher:
    """O driver que atende esta conta agora.

    Sempre devolve alguma coisa: o `manual` e o piso, e nao ter para onde
    publicar nao e um estado possivel. E isso que torna a cascata segura de
    deixar automatica -- a alternativa a um driver indisponivel e a fila
    manual, nunca um job vermelho.
    """
    elegiveis = []
    for cls in REGISTRY:
        driver = cls()
        if not entra_na_cascata(driver) and not consentiu(account, driver):
            continue
        if platform not in driver.platforms:
            continue
        if not driver.disponivel(account):
            continue
        elegiveis.append(driver)
        if driver.id == "manual":
            # O piso responde sempre; o que vier depois e inalcancavel.
            break

    if not elegiveis:
        return ManualPublisher()

    # `auto` nao casa com id de driver nenhum, entao cai na ordem do registro.
    preferido = account.driver_pref
    for driver in elegiveis:
        if driver.id == preferido:
            return driver
    return elegiveis[0]


def capabilities_de(account: Account) -> dict:
    """O que cada driver consegue nesta conta. E o que o painel desenha para
    explicar por que um corte caiu na fila manual em vez de subir sozinho."""
    return {cls.id: cls().capability(account) for cls in REGISTRY}
