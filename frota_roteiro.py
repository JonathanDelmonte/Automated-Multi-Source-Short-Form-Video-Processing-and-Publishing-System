"""O roteiro do automatico: ensinado pela pessoa, ensaiado e repetido -- etapa
7.9 (ADR-016).

**O motor nao adivinha a tela do app.** Os botoes do Instagram e do TikTok
mudam de lugar, de nome e de idioma; um roteiro escrito daqui, sem um celular,
seria um palpite que toca no lugar errado. Entao a pessoa ENSINA uma vez: pelo
painel, a tela do celular aparece com o que da para tocar; ela clica, o motor
toca no aparelho e anota o botao. No campo da legenda o motor digita. No botao
de publicar ela marca SEM tocar.

Depois, o **ensaio** refaz o roteiro com um video de teste e para antes de
publicar; o automatico so liga com ele passando. E na hora do post o motor so
toca no que foi ensinado: um botao que nao aparece, uma janela que ninguem
ensinou, a legenda que nao entrou -- ele para e o corte espera a pessoa.

O botao e reconhecido pelo que ele DIZ, nao por onde estava: o id do Android
(`resource-id`), o texto ou a descricao, e o texto de dentro dele. A posicao so
desempata, e o botao de publicar nunca e achado so pela posicao.

Funcoes puras sobre o XML do `uiautomator`, e o executor sobre um aparelho que
o chamador passa (o de verdade, ou o imitado dos testes).
"""
from __future__ import annotations

import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Optional

#: O formato do roteiro guardado. Um roteiro de outro formato nao roda: e
#: ensinado de novo.
VERSAO = 1

TIPOS = ("tocar", "legenda", "publicar")

#: Quanto o executor espera cada botao aparecer.
PRAZO_DO_PASSO_S = 20.0
#: Entre uma leitura da tela e a seguinte.
INTERVALO_S = 1.2
#: Depois do toque de publicar, quanto espera a tela mudar.
PRAZO_DEPOIS_DE_PUBLICAR_S = 45.0
#: Quantos caracteres do comeco da legenda tem de estar no campo depois de
#: digitar.
CONFERE_DA_LEGENDA = 20
#: Depois de um toque, quanto espera a tela mudar antes de procurar o botao
#: seguinte. O TikTok tem dois "Avancar" seguidos no mesmo lugar: sem esperar,
#: o segundo toque cairia ainda na primeira tela.
PRAZO_DA_TROCA_S = 5.0

_CAMPOS_DE_TEXTO = ("EditText", "AutoCompleteTextView")


def _dormir(segundos: float) -> None:
    """A espera entre um toque e a leitura seguinte. Um nome do modulo, e nao
    `time.sleep` direto, para o teste trocar por uma espera de mentira."""
    time.sleep(segundos)


def _norm(texto: str) -> str:
    """Para comparar o que a tela diz: sem acento de diferenca de
    normalizacao, sem caixa, sem espaco sobrando e sem reticencias."""
    t = unicodedata.normalize("NFC", texto or "").casefold()
    t = " ".join(t.split())
    return t.rstrip(".…").strip()


# --------------------------------------------------------------------------- #
# A tela
# --------------------------------------------------------------------------- #

@dataclass
class No:
    indice: int
    rid: str
    texto: str
    desc: str
    classe: str
    pacote: str
    tocavel: bool
    editavel: bool
    caixa: tuple
    rotulo: str = ""

    @property
    def centro(self) -> tuple:
        x1, y1, x2, y2 = self.caixa
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.caixa
        return max(0, x2 - x1) * max(0, y2 - y1)

    def contem(self, x: int, y: int) -> bool:
        x1, y1, x2, y2 = self.caixa
        return x1 <= x < x2 and y1 <= y < y2


def assinatura(tela) -> tuple:
    """O que da para tocar na tela, para saber se ela mudou."""
    return tuple((n.rid, _norm(n.rotulo), n.caixa) for n in tela.tocaveis())


@dataclass
class Tela:
    nos: list = field(default_factory=list)
    #: A janela da frente cobre a tela inteira (o app) ou e uma janela menor
    #: (um aviso, uma folha que sobe de baixo).
    cheia: bool = True
    pacote: str = ""

    def tocaveis(self) -> list:
        return [n for n in self.nos if (n.tocavel or n.editavel) and n.area > 0]


def _caixa(texto: str) -> tuple:
    try:
        a, b = texto.strip("[]").split("][")
        x1, y1 = (int(v) for v in a.split(","))
        x2, y2 = (int(v) for v in b.split(","))
        return (x1, y1, x2, y2)
    except (ValueError, AttributeError):
        return (0, 0, 0, 0)


def _rotulo(el, tocavel: bool) -> str:
    """O que o elemento diz: o texto ou a descricao dele. Um botao sem os dois
    pega o texto de dentro (o "Avancar" costuma ser uma caixa tocavel com um
    texto dentro) -- mas so se dentro nao ha outro tocavel: ai ele e um grupo
    de botoes, e o texto de um deles nao e o nome do grupo."""
    for chave in ("text", "content-desc"):
        valor = (el.get(chave) or "").strip()
        if valor:
            return valor
    if not tocavel:
        return ""
    filhos = [f for f in el.iter("node") if f is not el]
    if any(f.get("clickable") == "true" for f in filhos):
        return ""
    for filho in filhos:
        for chave in ("text", "content-desc"):
            valor = (filho.get(chave) or "").strip()
            if valor:
                return valor
    return ""


def ler(xml: str) -> Tela:
    """O XML do `uiautomator dump`, lido."""
    raiz = ET.fromstring(xml)
    nos = []
    for el in raiz.iter("node"):
        classe = el.get("class") or ""
        editavel = any(classe.endswith(c) for c in _CAMPOS_DE_TEXTO)
        tocavel = el.get("clickable") == "true" or el.get("long-clickable") == "true"
        nos.append(No(
            indice=len(nos),
            rid=el.get("resource-id") or "",
            texto=el.get("text") or "",
            desc=el.get("content-desc") or "",
            classe=classe,
            pacote=el.get("package") or "",
            tocavel=tocavel,
            editavel=editavel,
            caixa=_caixa(el.get("bounds") or ""),
            rotulo=_rotulo(el, tocavel or editavel),
        ))
    cheia = True
    if nos:
        x1, y1, _x2, _y2 = nos[0].caixa
        cheia = x1 <= 2 and y1 <= 2
    return Tela(nos=nos, cheia=cheia, pacote=nos[0].pacote if nos else "")


def no_no_ponto(tela: Tela, x: int, y: int) -> Optional[No]:
    """O que se tocaria no ponto: o menor elemento tocavel que o contem; sem
    nenhum, o menor que diz alguma coisa."""
    tocaveis = [n for n in tela.tocaveis() if n.contem(x, y)]
    if tocaveis:
        return min(tocaveis, key=lambda n: n.area)
    com_rotulo = [n for n in tela.nos if n.rotulo and n.area > 0 and n.contem(x, y)]
    return min(com_rotulo, key=lambda n: n.area) if com_rotulo else None


# --------------------------------------------------------------------------- #
# O alvo de um passo
# --------------------------------------------------------------------------- #

def alvo_de(no: No) -> dict:
    """O que se guarda para achar o botao de novo. Do campo de texto nao se
    guarda o texto: ele e a legenda (ou a dica), e muda a cada post."""
    return {
        "rid": no.rid,
        "texto": "" if no.editavel else no.texto,
        "desc": no.desc,
        "rotulo": "" if no.editavel else no.rotulo,
        "classe": no.classe,
        "editavel": no.editavel,
        "caixa": list(no.caixa),
    }


def tem_identidade(alvo: dict) -> bool:
    """O alvo e reconhecivel por alguma coisa que nao a posicao."""
    return bool(alvo.get("rid") or alvo.get("rotulo") or alvo.get("desc")
                or alvo.get("texto"))


def descrever(alvo: dict) -> str:
    """Como o painel e o log chamam o botao."""
    if alvo.get("editavel"):
        return "o campo da legenda"
    nome = alvo.get("rotulo") or alvo.get("desc") or alvo.get("texto")
    if nome:
        return f"“{nome}”"
    rid = (alvo.get("rid") or "").rpartition("/")[2]
    return f"o botão {rid}" if rid else "um botão sem nome"


def _distancia(caixa_a, caixa_b) -> float:
    ax = (caixa_a[0] + caixa_a[2]) / 2
    ay = (caixa_a[1] + caixa_a[3]) / 2
    bx = (caixa_b[0] + caixa_b[2]) / 2
    by = (caixa_b[1] + caixa_b[3]) / 2
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _sobreposicao(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    uniao = ((a[2] - a[0]) * (a[3] - a[1])) + ((b[2] - b[0]) * (b[3] - b[1])) - inter
    return inter / uniao if uniao > 0 else 0.0


def achar(tela: Tela, alvo: dict, so_por_identidade: bool = False) -> Optional[No]:
    """O elemento da tela que e o alvo ensinado, ou None.

    O id do Android manda quando existe; senao, o que o botao diz. Entre
    iguais, o mais perto de onde estava. So pela posicao (um icone sem nome nem
    id) vale para os passos do meio, e nunca para o de publicar
    (`so_por_identidade`)."""
    candidatos = [n for n in tela.nos if n.area > 0
                  and (n.tocavel or n.editavel or n.rotulo)]
    if alvo.get("editavel"):
        candidatos = [n for n in candidatos if n.editavel]
    caixa = tuple(alvo.get("caixa") or (0, 0, 0, 0))
    rid = alvo.get("rid") or ""
    rotulo = _norm(alvo.get("rotulo") or "")
    desc = _norm(alvo.get("desc") or "")
    if rid:
        iguais = [n for n in candidatos if n.rid == rid]
        if rotulo and not alvo.get("editavel"):
            com_rotulo = [n for n in iguais if _norm(n.rotulo) == rotulo]
            iguais = com_rotulo or iguais
    elif rotulo or desc:
        iguais = [n for n in candidatos
                  if (rotulo and _norm(n.rotulo) == rotulo) or (desc and _norm(n.desc) == desc)]
    elif alvo.get("editavel"):
        iguais = candidatos
    else:
        if so_por_identidade:
            return None
        iguais = [n for n in candidatos if n.classe == alvo.get("classe")
                  and _sobreposicao(n.caixa, caixa) >= 0.6]
    if not iguais:
        return None
    # Do mesmo id, o tocavel antes do que so tem texto: o toque cai nele.
    return min(iguais, key=lambda n: (not (n.tocavel or n.editavel), _distancia(n.caixa, caixa)))


def validar(passos: list) -> list:
    """O roteiro como o painel o mandou, conferido: tipos conhecidos, um so
    passo de publicar e no fim, e o de publicar reconhecivel por identidade."""
    if not isinstance(passos, list) or not passos:
        raise ValueError("o roteiro está vazio")
    limpos = []
    for i, p in enumerate(passos):
        if not isinstance(p, dict) or p.get("tipo") not in TIPOS or not isinstance(p.get("alvo"), dict):
            raise ValueError(f"o passo {i + 1} está torto")
        limpos.append({"tipo": p["tipo"], "alvo": p["alvo"]})
    tipos = [p["tipo"] for p in limpos]
    if tipos.count("publicar") != 1 or tipos[-1] != "publicar":
        raise ValueError("o roteiro termina no botão de publicar, e só nele")
    if not tem_identidade(limpos[-1]["alvo"]):
        raise ValueError("o botão de publicar precisa ter nome ou id: só a posição não basta")
    if len(limpos) > 30:
        raise ValueError("roteiro longo demais (mais de 30 passos)")
    return limpos


# --------------------------------------------------------------------------- #
# O executor: ensaio e post
# --------------------------------------------------------------------------- #

@dataclass
class Resultado:
    ok: bool
    publicado: bool = False
    parou_em: Optional[int] = None
    motivo: str = ""
    passos_feitos: int = 0
    #: A tela depois do toque de publicar nao confirmou nem negou: a pessoa
    #: confere no app.
    duvida: bool = False


class Executor:
    """Repete o roteiro no aparelho. `aparelho` tem `ler_tela()`, `tela_png()`,
    `tocar(x, y)`, `digitar(texto)` e `limpar_campo()`. Com `ensaio`, para no
    botao de publicar sem tocar."""

    def __init__(self, aparelho, passos: list, legenda: str = "", ensaio: bool = False,
                 guardar: Optional[Callable[[str, bytes], None]] = None,
                 log: Callable[[str], None] = print,
                 relogio: Callable[[], float] = time.monotonic,
                 dormir: Optional[Callable[[float], None]] = None,
                 prazo_s: float = PRAZO_DO_PASSO_S,
                 prazo_depois_s: float = PRAZO_DEPOIS_DE_PUBLICAR_S):
        self.ap = aparelho
        self.passos = passos
        self.legenda = legenda or ""
        self.ensaio = ensaio
        self.guardar = guardar
        self.log = log
        self.relogio = relogio
        self.dormir = dormir or (lambda s: _dormir(s))
        self.prazo_s = prazo_s
        self.prazo_depois_s = prazo_depois_s

    def _foto(self, nome: str) -> None:
        if not self.guardar:
            return
        try:
            self.guardar(nome, self.ap.tela_png())
        except Exception as e:  # a foto e evidencia, nunca o motivo de parar
            self.log(f"   (sem a foto de {nome}: {e})")

    def _esperar(self, alvo: dict, publicar: bool, proximo: Optional[dict]):
        """(no, tela, pular): o elemento quando ele aparece; ou `pular` quando o
        PROXIMO passo ja esta na tela (este era um aviso que so apareceu no dia
        do ensino); ou (None, ultima_tela, False) no fim do prazo."""
        limite = self.relogio() + self.prazo_s
        tela = None
        while True:
            tela = ler(self.ap.ler_tela())
            no = achar(tela, alvo, so_por_identidade=publicar)
            if no is not None:
                return no, tela, False
            if proximo is not None and achar(tela, proximo, so_por_identidade=False):
                return None, tela, True
            if self.relogio() >= limite:
                return None, tela, False
            self.dormir(INTERVALO_S)

    def rodar(self) -> Resultado:
        feitos = 0
        for i, passo in enumerate(self.passos):
            tipo, alvo = passo["tipo"], passo["alvo"]
            publicar = tipo == "publicar"
            proximo = (self.passos[i + 1]["alvo"] if tipo == "tocar" and i + 1 < len(self.passos)
                       else None)
            no, tela, pular = self._esperar(alvo, publicar, proximo)
            if pular:
                self.log(f"   passo {i + 1}: {descrever(alvo)} não apareceu, e o seguinte "
                         "já está na tela: seguindo")
                continue
            if no is None:
                self._foto(f"passo-{i + 1}-parou")
                motivo = (f"o passo {i + 1} ({descrever(alvo)}) não apareceu em "
                          f"{int(self.prazo_s)} s")
                if tela is not None and not tela.cheia:
                    motivo += "; uma janela que ninguém ensinou está na frente"
                return Resultado(False, parou_em=i, motivo=motivo, passos_feitos=feitos)
            self._foto(f"passo-{i + 1}-{tipo}")
            if publicar and self.ensaio:
                self.log(f"   ensaio: o botão de publicar ({descrever(alvo)}) está na tela; "
                         "não toquei")
                return Resultado(True, publicado=False, passos_feitos=feitos)
            x, y = no.centro
            self.ap.tocar(x, y)
            if tipo == "legenda":
                self.dormir(0.8)
                resultado = self._digitar(i, alvo)
                if resultado is not None:
                    return resultado
            elif publicar:
                return self._depois_de_publicar(i, alvo, feitos)
            else:
                self._esperar_trocar(tela)
            feitos += 1
        return Resultado(False, motivo="o roteiro acabou sem o botão de publicar",
                         passos_feitos=feitos)

    def _esperar_trocar(self, antes) -> None:
        """Espera a tela mudar depois do toque, ate `PRAZO_DA_TROCA_S`. Um
        toque que nao muda a tela (uma chave que liga e desliga) segue depois
        do prazo."""
        marca = assinatura(antes)
        limite = self.relogio() + PRAZO_DA_TROCA_S
        while self.relogio() < limite:
            self.dormir(0.5)
            try:
                if assinatura(ler(self.ap.ler_tela())) != marca:
                    return
            except Exception:
                return

    def _digitar(self, i: int, alvo: dict) -> Optional[Resultado]:
        self.ap.limpar_campo()
        self.ap.digitar(self.legenda)
        self.dormir(0.6)
        tela = ler(self.ap.ler_tela())
        campo = achar(tela, alvo)
        esperado = "".join(_norm(self.legenda).split())[:CONFERE_DA_LEGENDA]
        if campo is None or esperado not in "".join(_norm(campo.texto).split()):
            self._foto(f"passo-{i + 1}-legenda-nao-entrou")
            return Resultado(False, parou_em=i,
                             motivo="a legenda não entrou no campo (o ADBKeyBoard está instalado?)")
        return None

    def _depois_de_publicar(self, i: int, alvo: dict, feitos: int) -> Resultado:
        """"Saiu" e o botao sumir com a tela inteira do app na frente. Uma
        janela no lugar e duvida -- talvez um aviso, talvez uma pergunta -- e
        duvida espera a pessoa."""
        limite = self.relogio() + self.prazo_depois_s
        while True:
            self.dormir(INTERVALO_S)
            try:
                tela = ler(self.ap.ler_tela())
            except Exception:
                tela = None
            if tela is not None and achar(tela, alvo, so_por_identidade=True) is None:
                self._foto("depois-de-publicar")
                if tela.cheia:
                    return Resultado(True, publicado=True, passos_feitos=feitos + 1)
                return Resultado(False, parou_em=i, duvida=True, passos_feitos=feitos + 1,
                                 motivo="toquei em publicar e uma janela apareceu: "
                                        "confira no app se o post saiu")
            if self.relogio() >= limite:
                self._foto("depois-de-publicar")
                return Resultado(False, parou_em=i, duvida=True, passos_feitos=feitos + 1,
                                 motivo=f"toquei em publicar e a tela não mudou em "
                                        f"{int(self.prazo_depois_s)} s: confira no app")


# --------------------------------------------------------------------------- #
# O ensino
# --------------------------------------------------------------------------- #

#: A legenda que o ensino digita no campo, para a tela seguir como num post.
LEGENDA_DE_TESTE = "Teste do Virtu Clips: este vídeo não é para publicar"


class Ensino:
    """A pessoa mostra o caminho uma vez, pelo painel.

    Cada `tocar` recebe um ponto da imagem da tela (0 a 1 nos dois eixos), acha
    o elemento ali, toca nele no aparelho e anota o passo. Num campo de texto, o
    motor digita a `LEGENDA_DE_TESTE` (quando ha o ADBKeyBoard). `publicar`
    anota o botao de publicar SEM tocar, e encerra."""

    def __init__(self, aparelho, tamanho: tuple, digitar: bool = True,
                 dormir: Optional[Callable[[float], None]] = None):
        self.ap = aparelho
        self.largura, self.altura = tamanho
        self.digitar = digitar
        self.dormir = dormir or (lambda s: _dormir(s))
        self.passos: list = []
        self.tela: Optional[Tela] = None
        self.pronto = False

    def atualizar(self) -> Tela:
        self.tela = ler(self.ap.ler_tela())
        return self.tela

    def _ponto(self, fx: float, fy: float) -> tuple:
        fx = min(max(float(fx), 0.0), 1.0)
        fy = min(max(float(fy), 0.0), 1.0)
        return int(fx * (self.largura - 1)), int(fy * (self.altura - 1))

    def _no(self, fx: float, fy: float) -> No:
        if self.tela is None:
            self.atualizar()
        x, y = self._ponto(fx, fy)
        no = no_no_ponto(self.tela, x, y)
        if no is None:
            raise ValueError("aí não há nada para tocar")
        return no

    def tocar(self, fx: float, fy: float) -> dict:
        if self.pronto:
            raise ValueError("o ensino já terminou")
        no = self._no(fx, fy)
        passo = {"tipo": "legenda" if no.editavel else "tocar", "alvo": alvo_de(no)}
        if passo["tipo"] == "legenda" and any(p["tipo"] == "legenda" for p in self.passos):
            raise ValueError("o campo da legenda já foi ensinado")
        x, y = no.centro
        self.ap.tocar(x, y)
        if passo["tipo"] == "legenda" and self.digitar:
            self.dormir(0.8)
            self.ap.limpar_campo()
            self.ap.digitar(LEGENDA_DE_TESTE)
        self.passos.append(passo)
        self.dormir(1.5)
        self.atualizar()
        return passo

    def publicar(self, fx: float, fy: float) -> dict:
        if self.pronto:
            raise ValueError("o ensino já terminou")
        no = self._no(fx, fy)
        alvo = alvo_de(no)
        if no.editavel:
            raise ValueError("isso é um campo de texto, não o botão de publicar")
        if not tem_identidade(alvo):
            raise ValueError("esse botão não tem nome nem id: o motor não o reconheceria "
                             "de novo só pela posição")
        passo = {"tipo": "publicar", "alvo": alvo}
        self.passos.append(passo)
        self.pronto = True
        return passo

    def desfazer(self) -> Optional[dict]:
        """Tira o ultimo passo da lista. No aparelho nao volta nada: para isso
        ha a tecla voltar, que nao entra no roteiro."""
        if not self.passos:
            return None
        self.pronto = False
        return self.passos.pop()

    def roteiro(self) -> list:
        return validar(self.passos)
