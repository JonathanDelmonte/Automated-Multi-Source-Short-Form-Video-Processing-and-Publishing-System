"""Driver `aggregator` -- stub. Fase 3, bloco 3.1.

Um agregador (Upload-Post, Blotato e afins) publica na plataforma por voce
atraves do contrato *deles*, e a Fase 0.3 removeu exatamente essa integracao do
fork -- 10 uploads gratis/mes contra ~90/mes necessarios, que e o que motivou
esta camada existir.

Ele entra na cascata automatica (risco zero: quem responde pelo acesso e o
agregador, e a conta nao ve automacao nenhuma), mas so **quando assinado**. E,
como a restricao travada do projeto e custo zero, "assinado" e hoje sempre
falso. O stub existe para que o lugar dele na ordem esteja escrito e testado
antes de haver mensalidade que o justifique.
"""
from __future__ import annotations

import os

from .base import Account, Cost, DriverDesligado, Publisher


def assinado() -> bool:
    """Ha uma assinatura de agregador configurada nesta instalacao."""
    return os.environ.get("PUBLISHER_AGGREGATOR") == "1"


class AggregatorPublisher(Publisher):
    id = "aggregator"
    label = "agregador"
    platforms = ("youtube", "tiktok", "instagram")

    def disponivel(self, account: Account) -> bool:
        return assinado() and account.platform in self.platforms

    def capability(self, account: Account) -> str:
        if not self.disponivel(account):
            return "none"
        # O plano do agregador e quem decide, e nao da para saber sem falar com
        # ele. Quando o driver existir, isto vira uma consulta.
        return "public"

    def cost(self, n: int) -> Cost:
        # `usd` e zero **por corte**: a mensalidade nao e custo marginal. Nao e
        # o mesmo que ser gratis, e e por isso que `assinado()` e a porta.
        return Cost(risk_score=0.0, usd=0.0)

    def publish(self, clip, meta, opts, account):
        raise DriverDesligado(
            "O driver 'aggregator' ainda nao foi implementado: ele so faz "
            "sentido quando o projeto aceitar uma mensalidade (secao 6). "
            "Use 'manual' ou 'youtube-api'.")
