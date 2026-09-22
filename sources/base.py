"""Contrato da camada de ingestao. Somente biblioteca padrao.

Ficar no stdlib nao e purismo: o `main.py` traz torch, mediapipe, scenedetect e
faster-whisper junto, e nem o CI nem a maquina de quem so quer rodar os testes
tem essa pilha instalada. Com este modulo limpo, os testes de roteamento -- que
sao a parte com regra de negocio -- rodam sempre.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse


class UnknownSource(ValueError):
    """Nenhum adapter reconheceu a entrada."""


class SourceNotReady(RuntimeError):
    """A fonte foi reconhecida, e buscar ESTE tipo dela ainda nao existe.

    Diferente de `UnknownSource`: aqui sabemos exatamente o que e, e a resposta
    certa e dizer o que fazer no lugar. Hoje so a live da Twitch (bloco 1.5).
    """


@dataclass(frozen=True)
class SourceInfo:
    """O que da para saber da fonte **sem tocar a rede**.

    O `probe` do §4 tambem preve duracao e tamanho, e esses custam uma ida na
    rede -- no YouTube, as vezes uma que o proxy por GB cobra. Esse probe caro
    ja existe e ja tem dono: `quality_probe.py`, e as regras de quando vale
    pagar por ele estao em `cloud/metering.probe_url_minutes`
    (`static_failure_warrants_paid`). Duplicar aquilo aqui seria reabrir uma
    conta que o repositorio ja fechou.

    Este e o barato: que tipo de coisa e esta entrada, ela expira, ela ainda
    esta acontecendo. E o que o log mostra antes de comecar a baixar.
    """
    kind: str
    label: str
    is_live: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Fetched:
    """O que todo adapter devolve, venha de onde vier: um arquivo em disco e um
    titulo. O resto do pipeline nao sabe a origem -- e o ponto da camada."""
    path: str
    title: str
    kind: str
    meta: dict = field(default_factory=dict)


class SourceAdapter:
    """Uma fonte.

    `matches` e de classe porque o registro pergunta antes de instanciar, e
    precisa ser barato e sem efeito colateral: e chamado uma vez por adapter,
    em ordem, para toda entrada.
    """

    id: str = ""
    label: str = ""

    # Qual pote de cookies esta fonte usa. E propriedade do adapter, e nao uma
    # tabela no `main.py`, porque quem sabe que a Twitch precisa de conta
    # inscrita e o adapter da Twitch -- e porque assim isto e testavel sem
    # importar o `main` (sem torch), que e o unico jeito de o CI exercitar.
    #
    # O jar de uma plataforma nao autentica na outra (formato Netscape e
    # escopado por dominio, entao mandar o errado nao vaza nada -- so nao
    # loga), e os ARQUIVOS sao separados porque ate a Fase 1 so havia uma
    # plataforma: dois jobs simultaneos, um de cada, se sobrescreveriam.
    cookie_env: str = "YOUTUBE_COOKIES"
    cookie_file: str = "/app/cookies.txt"
    #: Outros nomes que o jar desta fonte pode ter NA RAIZ DO REPOSITORIO.
    #: Existe por um motivo so: e o nome com que a extensao do navegador salva
    #: o arquivo. Obrigar a renomear e um passo a mais para errar.
    cookie_file_alt: tuple = ()

    @classmethod
    def matches(cls, raw: str) -> bool:
        raise NotImplementedError

    def probe(self, raw: str) -> SourceInfo:
        return SourceInfo(kind=self.id, label=self.label)

    def assert_fetchable(self, raw: str) -> None:
        """Levanta `SourceNotReady` se este tipo de fonte ainda nao tem como ser
        buscado. Barato e sem rede.

        Existe separado do `fetch` para que a recusa possa acontecer no submit,
        antes de subir o subprocesso do job: senao o erro vira um job vermelho
        no historico em vez de uma mensagem no formulario.
        """
        return None

    def fetch(self, raw: str, output_dir: str = ".") -> Fetched:
        # `output_dir` e onde gravar o que vier da rede. Tem padrao porque
        # nem toda fonte baixa: o arquivo local ja esta em disco e ignora.
        raise NotImplementedError


def modulo_main():
    """O modulo `main`, sem carrega-lo duas vezes.

    `python main.py` carrega o arquivo como `__main__`. Um `import main` la
    dentro **nao** devolve esse modulo: o Python nao encontra "main" em
    `sys.modules` e le o arquivo OUTRA VEZ, criando um segundo modulo com o
    topo reexecutado -- outro grafo do MediaPipe, outro `DETECT_LOCK`, outro
    conjunto de globais. Funciona por acidente e paga o preco em todo job, que
    e um subprocesso novo a cada video.

    A checagem e pelo atributo, e nao pelo `__file__`, porque e o que o chamador
    precisa de verdade. Sob o uvicorn (`app.py`), `__main__` e o entrypoint dele
    e nao tem o atributo, entao o `import main` normal acontece -- que ali e o
    certo, porque o `main` ja esta carregado uma vez so.
    """
    import sys

    atual = sys.modules.get("__main__")
    if hasattr(atual, "download_youtube_video"):
        return atual
    import main

    return main


def host_of(raw: str) -> str:
    """Host em minusculas, ou string vazia se a entrada nao for uma URL."""
    try:
        return (urlparse(raw).hostname or "").lower()
    except Exception:
        return ""


def is_http_url(raw: str) -> bool:
    """So http e https.

    Um caminho do Windows (`C:\\videos\\x.mp4`) tem `urlparse().scheme == 'c'`,
    entao testar "tem esquema" mandaria arquivo local para o caminho de rede.
    """
    try:
        return urlparse(raw).scheme in ("http", "https")
    except Exception:
        return False
