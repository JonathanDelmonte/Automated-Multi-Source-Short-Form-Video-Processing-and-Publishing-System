"""De que paginas este servidor aceita conversa (Fase 6, 24-set-2026).

O painel publicado no Cloudflare mora noutra origem que o servidor
(``https://virtu-clips.zirtuno.workers.dev`` x ``http://localhost:8000``), e o
navegador so entrega a resposta a pagina se o CORS disser que aquela origem
pode le-la. Ate aqui o CORS refletia QUALQUER origem, com credenciais: com o
servidor em localhost, qualquer site aberto no mesmo navegador podia ler a
lista de projetos, os logs e os videos, e mandar processar. A permissao de rede
local do Chrome barra isso para quem a nega -- mas nem todo navegador pergunta,
e um "Permitir" dado ao site errado a desfaz.

Quem pode:

- o site oficial, e as URLs de versao dele (``<id>-virtu-clips.zirtuno...``),
  que so a conta que publica o site consegue criar;
- qualquer pagina servida pela propria maquina (``localhost``, ``127.0.0.1``,
  ``[::1]``), em qualquer porta: o ``npm run dev``, o e2e.

O painel do Docker (5175) nem passa por aqui: o proxy do Vite faz a pagina e a
API serem a MESMA origem para o navegador, entao o CORS nao entra -- inclusive
quando ele e aberto de outro aparelho da rede.

``ORIGENS_DO_PAINEL`` troca a lista (virgula), para quem publicar o painel
noutro endereco. Em branco, ou so com virgulas, vale o site oficial: uma lista
vazia trancaria o painel publicado sem uma linha de erro -- ele so ficaria em
"conectando ao servidor".

Stdlib pura, e o ``app.py`` so le o resultado: a regra roda no CI sem subir a
API, e o ajudante (Fase 6.2) vai precisar da mesma.
"""
from __future__ import annotations

import os
import re
from typing import Iterable, List, Mapping, Optional

SITE_OFICIAL = "https://virtu-clips.zirtuno.workers.dev"

# Paginas da propria maquina. `localhost` sozinho, sem sufixo: um
# `localhost.algum-dominio.com` e um site qualquer.
_LOCAL = r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?"

_WORKERS_DEV = re.compile(r"https://([a-z0-9-]+)\.([a-z0-9-]+)\.workers\.dev")


def origens_do_painel(env: Optional[Mapping[str, str]] = None) -> List[str]:
    """As origens publicas que podem usar este servidor, alem das locais."""
    env = os.environ if env is None else env
    bruto = env.get("ORIGENS_DO_PAINEL") or ""
    origens = [o.strip().rstrip("/") for o in bruto.split(",") if o.strip()]
    return origens or [SITE_OFICIAL]


def regex_das_origens(origens: Iterable[str]) -> str:
    """O ``allow_origin_regex`` do CORS: as locais mais as de ``origens``.

    O Starlette compara com ``fullmatch``, e o teste confere com a mesma
    funcao, entao um sufixo (``...workers.dev.site-qualquer.com``) nao passa.
    """
    partes = [_LOCAL]
    for origem in origens:
        m = _WORKERS_DEV.fullmatch(origem)
        if m:
            # A URL de cada versao publicada (`<id>-<nome>.<conta>.workers.dev`)
            # e da mesma conta: so quem publica o site cria uma.
            nome, conta = re.escape(m[1]), re.escape(m[2])
            partes.append(rf"https://(?:[a-z0-9-]+-)?{nome}\.{conta}\.workers\.dev")
        else:
            partes.append(re.escape(origem))
    return "|".join(f"(?:{p})" for p in partes)


def permitida(origem: str, regex: str) -> bool:
    """O que o CORS decide para ``origem`` -- a mesma comparacao do Starlette."""
    return re.fullmatch(regex, origem) is not None
