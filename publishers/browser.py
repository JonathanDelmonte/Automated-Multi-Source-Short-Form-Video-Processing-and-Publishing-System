"""Driver `browser` -- stub, e o unico que nasce desligado por decisao. Bloco 3.1.

A secao 1 do Plano Tecnico e direta sobre por que ele existe e por que nao se
usa: automacao de navegador contorna a falta de API publica, e **a punicao por
deteccao nao e um erro HTTP tratavel** -- e shadowban ou perda da conta. Num
projeto de cortes, a conta e o ativo. Nao ha retry que recupere isso.

Duas travas independentes, e as duas precisam ceder:

1. `resolve()` nunca chega ate aqui. Nao porque o resolvedor conheca este
   arquivo pelo nome, mas porque `cost().risk_score` e 1.0 e a cascata
   automatica so aceita risco zero. Trocar o numero e a unica forma de entrar,
   e um teste falha se alguem trocar.
2. Mesmo escolhido a mao (`accounts.driver_pref = 'browser'`), so responde com
   `PUBLISHER_BROWSER=1` no ambiente. Uma preferencia gravada numa linha pode
   virar um clique errado no painel; a variavel e a instalacao dizendo que
   sabe.
"""
from __future__ import annotations

import os

from .base import Account, Cost, DriverDesligado, Publisher

# 1.0 na escala 0..1 de `Cost`: "pode custar a conta". E este numero, e nao uma
# lista de nomes no resolvedor, que mantem o driver fora da cascata automatica.
RISCO = 1.0


def ligado_a_mao() -> bool:
    return os.environ.get("PUBLISHER_BROWSER") == "1"


class BrowserPublisher(Publisher):
    id = "browser"
    label = "navegador"
    platforms = ("youtube", "tiktok", "instagram")

    def disponivel(self, account: Account) -> bool:
        return (ligado_a_mao()
                and account.driver_pref == "browser"
                and account.platform in self.platforms)

    def capability(self, account: Account) -> str:
        if not self.disponivel(account):
            return "none"
        return "public"

    def cost(self, n: int) -> Cost:
        return Cost(risk_score=RISCO)

    def publish(self, clip, meta, opts, account):
        raise DriverDesligado(
            "O driver 'browser' nao foi implementado e nasce desligado de "
            "proposito (secao 1): a punicao por deteccao e shadowban ou perda "
            "da conta, nao um erro que da para tentar de novo.")
