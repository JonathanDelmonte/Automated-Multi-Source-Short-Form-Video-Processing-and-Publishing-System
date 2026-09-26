"""Agendador de publicacao -- Fase 4, bloco 4.4, ADR-007.

Fecha a decisao em aberto §10.2 ("quantos posts por dia e em quais horarios"),
que o ADR-007 adiou de proposito para esta fase por falta de informacao. O que
ha de informacao, e de onde vem:

* **3 por dia.** Nao e chute: o §1 faz a conta ("3 videos/dia gastam 4.800 e
  sobra metade para listagem e reprocessamento") e o ADR-007 repete o numero
  como ponto de partida. O teto duro e outro -- o contador de quota do YouTube
  (100 envios/dia desde jun-2026; eram 6 pela regra antiga) -- e o agendador
  nunca o ultrapassa.
* **Espacamento minimo de 3 h e jitter de ±25 min**, os numeros que o ADR-007
  propos. Sao **defaults**, nao verdades: calibrar horario de publicacao exige
  retencao real, que e a tabela `metrics` e a Fase 5. Estao em variaveis de
  ambiente para que a calibracao nao precise de deploy.

**O jitter e requisito de desenho e nao opcao**, e o ADR-007 e explicito: o §1
lista "postagens em horarios regulares demais" entre os sinais que a deteccao
de automacao cruza, e um agendador que publica 12:00:00 todo dia produz
exatamente essa assinatura. Por isso `JITTER_MINIMO` existe: pedir zero nao
desliga o jitter, so o reduz ao piso, com uma linha no log dizendo por que.
Vale para todos os drivers, inclusive os de risco zero -- custa nada e evita
retrofit no dia em que o `browser` for ligado a mao.

**A agenda e por conta** (etapa 7.3). Cada conta tem os horarios dela, e
um horario novo respeita os que a conta ja tem -- os posts recentes e os
agendados --, entao agendar dois projetos no mesmo canal nao poe dois posts na
mesma janela.

**A trava do post atrasado** (`triar_vencidas`, etapa 7.3, pedido do autor em
26-set-2026: "posta quando o PC voltar, mas nunca varios de uma vez"). Com o
PC desligado na hora marcada, varios posts vencem juntos; o laco publicava
todos, um atras do outro, no primeiro minuto em que o motor voltava. Agora, por
conta, sai no maximo o primeiro -- se o espacamento desde o ultimo post e o
teto do dia deixarem -- e os outros sao reespalhados nas janelas seguintes,
com o mesmo jitter.

Modulo de biblioteca padrao: as funcoes sao puras e recebem `agora` e o
sorteador, entao o CI exercita o calculo inteiro sem relogio e sem banco.
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from datetime import datetime, time as _time, timedelta, timezone, tzinfo
from typing import Callable, Iterable, Optional, Sequence

#: Quantos cortes por dia, por padrao. A conta do §1.
POR_DIA_PADRAO = 3

#: As janelas do dia, em hora local do servidor. Tres, espacadas, cobrindo
#: manha, tarde e noite -- o suficiente para o espacamento minimo caber.
JANELAS_PADRAO = (11, 15, 19)

#: Espacamento minimo entre dois posts, em minutos.
ESPACAMENTO_PADRAO_MIN = 180

#: Amplitude do jitter, em minutos (±).
JITTER_PADRAO_MIN = 25

#: Piso do jitter. **Nao e configuravel de proposito** (ADR-007): zero produz a
#: assinatura que o §1 manda evitar, e um agendador que aceita zero e um
#: agendador que um dia roda com zero.
JITTER_MINIMO_MIN = 5


class AgendaInvalida(ValueError):
    """Configuracao que nao produz agenda nenhuma."""


def _inteiro_do_ambiente(nome: str, padrao: int) -> int:
    try:
        valor = int(os.environ.get(nome) or padrao)
    except (TypeError, ValueError):
        return padrao
    return valor


def por_dia() -> int:
    return max(1, _inteiro_do_ambiente("SCHEDULE_PER_DAY", POR_DIA_PADRAO))


def janelas() -> tuple:
    """As horas do dia em que se publica. `SCHEDULE_WINDOWS=9,13,18`."""
    bruto = (os.environ.get("SCHEDULE_WINDOWS") or "").strip()
    if not bruto:
        return JANELAS_PADRAO
    horas = []
    for pedaco in bruto.split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        try:
            hora = int(pedaco)
        except ValueError:
            continue
        if 0 <= hora <= 23:
            horas.append(hora)
    return tuple(sorted(set(horas))) or JANELAS_PADRAO


def espacamento_minimo() -> timedelta:
    return timedelta(minutes=max(
        0, _inteiro_do_ambiente("SCHEDULE_MIN_GAP_MINUTES",
                                ESPACAMENTO_PADRAO_MIN)))


def jitter_minutos() -> int:
    """A amplitude do jitter, nunca abaixo do piso.

    Pedir zero **nao desliga**: o ADR-007 trata isto como requisito de desenho,
    e um agendador que aceita zero e um agendador que um dia roda com zero.
    """
    pedido = _inteiro_do_ambiente("SCHEDULE_JITTER_MINUTES", JITTER_PADRAO_MIN)
    if pedido < JITTER_MINIMO_MIN:
        print(f"⏰ jitter pedido ({pedido} min) abaixo do piso; usando "
              f"{JITTER_MINIMO_MIN} min. Horario exato todo dia e um dos sinais "
              "que a deteccao de automacao cruza (ADR-007).")
        return JITTER_MINIMO_MIN
    return pedido


def _com_fuso(quando: datetime) -> datetime:
    """O banco SQLite devolve datetime sem fuso, e o que vai para ele e UTC."""
    return quando if quando.tzinfo else quando.replace(tzinfo=timezone.utc)


def proximos_horarios(quantos: int, agora: Optional[datetime] = None,
                      *, sorteador: Optional[Callable[[int, int], int]] = None,
                      horas: Optional[Sequence[int]] = None,
                      jitter: Optional[int] = None,
                      gap: Optional[timedelta] = None,
                      teto_por_dia: Optional[int] = None,
                      ocupados: Iterable[datetime] = ()) -> list:
    """`quantos` horarios futuros, com jitter e espacamento respeitados.

    Devolve datetimes **com fuso**, no fuso local do servidor -- a mesma escolha
    de `publishers.pacote.dia_de`, e pelo mesmo motivo: "publicar as 11h" e uma
    frase sobre o dia de quem publica.

    `ocupados` sao os horarios que a conta ja tem: posts recentes e agendados.
    Contam para o espacamento e para o teto do dia.

    As regras, e a ordem entre elas importa:

    1. **jitter primeiro**, sobre a hora cheia da janela;
    2. **espacamento depois**, empurrando para a frente o que ficou perto
       demais do horario ANTERIOR. Ao contrario, duas janelas a uma hora de
       distancia com jitter de -25 e +25 minutos terminariam a 10 minutos uma
       da outra -- o jitter destruindo justamente a regra que o espacamento
       existe para manter;
    3. **janela tomada fica para a proxima**: perto demais de um horario
       POSTERIOR que a conta ja tem, a janela e pulada em vez de empurrada.
       Empurrar para depois do ocupado daria posts a exatamente 3 h um do
       outro, dia apos dia -- o relogio regular que o jitter existe para
       apagar;
    4. **nada no passado**: uma janela que ja passou hoje vai para amanha, com
       jitter proprio. Agendar para tras publicaria tudo de uma vez no primeiro
       tique do laco, que e o oposto de espacar.
    """
    if quantos <= 0:
        return []
    agora = agora or datetime.now().astimezone()
    if agora.tzinfo is None:
        agora = agora.astimezone()
    horas = tuple(horas) if horas is not None else janelas()
    if not horas:
        raise AgendaInvalida("nenhuma janela de publicacao configurada")
    amplitude = jitter_minutos() if jitter is None else max(0, int(jitter))
    gap = espacamento_minimo() if gap is None else gap
    teto = por_dia() if teto_por_dia is None else max(1, int(teto_por_dia))
    sorteia = sorteador or (lambda a, b: random.randint(a, b))

    tomados = sorted(_com_fuso(o).astimezone(agora.tzinfo) for o in ocupados)
    por_dia_ocupado: dict = {}
    for o in tomados:
        por_dia_ocupado[o.date()] = por_dia_ocupado.get(o.date(), 0) + 1

    escolhidos: list = []
    dia = agora.date()
    # Teto de dias para nao girar para sempre se a configuracao for absurda
    # (janela unica e espacamento de 20 h, por exemplo).
    for _ in range(366):
        usados_no_dia = por_dia_ocupado.get(dia, 0)
        for hora in horas:
            if len(escolhidos) >= quantos:
                return escolhidos
            if usados_no_dia >= teto:
                break
            base = datetime.combine(dia, _time(hour=hora),
                                    tzinfo=agora.tzinfo)
            quando = base + timedelta(minutes=sorteia(-amplitude, amplitude))
            todos = sorted(tomados + escolhidos)
            antes = [t for t in todos if t <= quando]
            if antes and quando - antes[-1] < gap:
                quando = antes[-1] + gap
            if any(t > quando - gap and t < quando + gap for t in todos):
                continue        # janela tomada: a proxima
            if quando <= agora:
                continue
            escolhidos.append(quando)
            usados_no_dia += 1
        dia = dia + timedelta(days=1)
    return escolhidos


@dataclass
class Triagem:
    """O que fazer com as publicacoes vencidas de uma volta do laco."""
    #: Os ids que saem agora -- no maximo um por conta.
    agora: list = field(default_factory=list)
    #: {id: novo horario} das que ficam para depois.
    reagendar: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AgendaDaConta:
    """As regras de UMA conta: as janelas e o teto do canal dela, e o fuso em
    que as janelas valem (etapa 7.5). `None` e "o padrao da instalacao"."""
    horas: Optional[tuple] = None
    teto: Optional[int] = None
    fuso: Optional[tzinfo] = None


def triar_vencidas(vencidas: Sequence[dict], agora: datetime,
                   ocupados_por_conta: Optional[dict] = None, *,
                   sorteador: Optional[Callable[[int, int], int]] = None,
                   horas: Optional[Sequence[int]] = None,
                   jitter: Optional[int] = None,
                   gap: Optional[timedelta] = None,
                   teto_por_dia: Optional[int] = None,
                   agendas: Optional[dict] = None) -> Triagem:
    """A trava do post atrasado: por conta, sai no maximo UM, e o resto espera.

    `vencidas` sao dicts com `id`, `account_id` e `scheduled_at`.
    `ocupados_por_conta` e `{conta: [horarios]}` com os posts recentes de
    verdade (e os que estao subindo agora) e os agendados que ainda nao
    venceram. `agendas` e `{conta: AgendaDaConta}`: as janelas, o teto e o fuso
    do canal de cada conta (7.5); a conta que nao estiver ali segue `horas`,
    `teto_por_dia` e o fuso do processo.

    Por conta, a vencida mais antiga sai agora se as duas regras deixarem: o
    espacamento minimo desde o ultimo post da conta e o teto do dia. As outras
    -- e a primeira, se ela nao puder -- ganham horarios novos pelas mesmas
    regras de `proximos_horarios`, respeitando o que a conta ja tem marcado.

    No dia normal nao muda nada: cada janela vence sozinha, com o espacamento
    ja respeitado desde o agendamento. A trava so atua quando varios vencem
    juntos -- o PC que ficou desligado --, e ai e ela que impede a rajada.
    """
    agora = _com_fuso(agora)
    gap = espacamento_minimo() if gap is None else gap
    teto_padrao = por_dia() if teto_por_dia is None else max(1, int(teto_por_dia))
    ocupados_por_conta = ocupados_por_conta or {}
    agendas = agendas or {}

    por_conta: dict = {}
    for item in vencidas:
        por_conta.setdefault(item["account_id"], []).append(item)

    triagem = Triagem()
    for conta, itens in por_conta.items():
        agenda = agendas.get(conta) or AgendaDaConta()
        # O "hoje" do teto e o dia de quem usa, e as janelas do reagendamento
        # sao as dela: no Docker o processo esta em UTC.
        local = agora.astimezone(agenda.fuso) if agenda.fuso else agora.astimezone()
        teto = max(1, int(agenda.teto)) if agenda.teto else teto_padrao
        horas_da_conta = agenda.horas if agenda.horas else horas
        itens = sorted(itens, key=lambda i: (_com_fuso(i["scheduled_at"]), i["id"]))
        tomados = sorted(_com_fuso(o).astimezone(local.tzinfo)
                         for o in ocupados_por_conta.get(conta, ()))
        passados = [t for t in tomados if t <= local]
        hoje = sum(1 for t in passados if t.date() == local.date())
        folga = not passados or local - passados[-1] >= gap
        if folga and hoje < teto:
            triagem.agora.append(itens[0]["id"])
            tomados.append(local)
            resto = itens[1:]
        else:
            resto = itens
        if not resto:
            continue
        horarios = proximos_horarios(
            len(resto), local, sorteador=sorteador, horas=horas_da_conta, jitter=jitter,
            gap=gap, teto_por_dia=teto, ocupados=tomados)
        for item, quando in zip(resto, horarios):
            triagem.reagendar[item["id"]] = quando
    return triagem


def descricao(agenda: Optional[AgendaDaConta] = None) -> dict:
    """A agenda em vigor, para o painel explicar o que vai acontecer. Com
    `agenda`, a de um canal: as janelas e o teto dele no lugar dos padroes."""
    agenda = agenda or AgendaDaConta()
    return {
        "por_dia": int(agenda.teto) if agenda.teto else por_dia(),
        "janelas": list(agenda.horas) if agenda.horas else list(janelas()),
        "espacamento_min": int(espacamento_minimo().total_seconds() // 60),
        "jitter_min": jitter_minutos(),
        "jitter_piso_min": JITTER_MINIMO_MIN,
    }


def para_utc(quando: datetime) -> datetime:
    """O que vai para o banco. `scheduled_at` e comparado com `now()` do laco,
    entao os dois precisam estar no mesmo fuso -- e UTC e o unico que nao muda
    de significado com o servidor."""
    if quando.tzinfo is None:
        quando = quando.astimezone()
    return quando.astimezone(timezone.utc)
