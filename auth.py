"""Auth propria -- Fase 4, bloco 4.1.

A secao 7 do Plano Tecnico deixou a auth para esta fase de proposito: "adicionar
auth sobre um schema que ja tem tenant e um sabado de trabalho". O schema esta
pronto desde a Fase 0.5; falta quem autentique.

**Nao ha dependencia nova, e isso e decisao.** O upstream autenticava por
magic-link (servico de e-mail) e Google OAuth, e os dois sairam com o `cloud/`
no ADR-001. Trazer qualquer um de volta significaria um servico pago ou um
projeto no Google Cloud com tela de consentimento -- para o autor entrar na
propria ferramenta, na propria maquina. E a mesma desproporcao que o
`sources/gdrive.py` recusou. Aqui e **e-mail e senha**, com `hashlib.scrypt` da
biblioteca padrao, que e um KDF de verdade (memoria dura, ~57 ms por
verificacao nesta maquina) e nao um `sha256(senha)` disfarcado.

**O token e assinado, nao e um JWT.** Um JWT traria uma biblioteca para
negociar algoritmo -- e e exatamente ai que moram os furos conhecidos
(`alg: none`, confusao de HS256 com RS256). Aqui ha **um** algoritmo,
codificado no verificador, sem campo que o chamador possa mudar. O payload e
`{u, t, v, exp}`: usuario, tenant, versao do token e expiracao.

**`token_version` e o que torna a revogacao possivel sem tabela de sessao.**
Token assinado e stateless: quem o tem, entra, ate expirar. Bumpar a versao do
usuario invalida todos os dele de uma vez -- e o que "sair de todos os
aparelhos" e a troca de senha precisam fazer.

### Quando a auth liga

Ela nao tem flag. **Liga quando algum usuario ganha uma senha.**

O seed ja cria `self-host@localhost` como dono do tenant fixo, e e esse usuario
que ja possui tudo o que existe hoje -- jobs, templates, contas, publicacoes.
Entao o bootstrap nao cria conta nenhuma: ele **da uma senha (e o e-mail de
verdade) ao usuario que ja e o dono**. Nada se move, nada orfana, e a
instalacao de quem nunca quis auth continua exatamente como era.

Enquanto nenhum usuario tiver senha, a instalacao esta **aberta** -- que e o
comportamento de hoje e o motivo de o plano avisar, ate esta fase, para nao
expor a ferramenta a internet publica. O `app.py` grita isso no boot.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

# --------------------------------------------------------------------------- #
# Senha
# --------------------------------------------------------------------------- #

#: Parametros do scrypt. `n=2**14` e o ajuste "interativo" classico: 16 MB de
#: memoria e dezenas de milissegundos, que e caro para quem tenta milhoes e
#: imperceptivel para quem tenta uma.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

#: Tamanho minimo. Dez, e nao oito, porque depois desta fase esta senha e a
#: unica coisa entre a internet e a ferramenta -- e porque quem escolhe a senha
#: aqui e uma pessoa so, que nao vai reclamar de dois caracteres.
MIN_SENHA = 10


class AuthError(Exception):
    """Falha de autenticacao que o painel mostra como texto."""


def _b64e(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def _b64d(texto: str) -> bytes:
    resto = len(texto) % 4
    if resto:
        texto += "=" * (4 - resto)
    return base64.urlsafe_b64decode(texto.encode("ascii"))


def hash_de_senha(senha: str) -> str:
    """`scrypt$n$r$p$salt$hash`, com o sal por senha dentro da propria string.

    Guardar os parametros junto e o que permite endurece-los depois sem
    invalidar as senhas ja gravadas: a verificacao le os que foram usados na
    hora, nao os de hoje.
    """
    if not isinstance(senha, str) or len(senha) < MIN_SENHA:
        raise AuthError(f"a senha precisa de pelo menos {MIN_SENHA} caracteres")
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=SCRYPT_N,
                              r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64e(sal)}${_b64e(derivada)}"


def senha_confere(senha: str, guardado: Optional[str]) -> bool:
    """Comparacao em tempo constante. Nunca levanta -- formato torto e `False`.

    `hmac.compare_digest` e nao `==`: a comparacao ingenua vaza, pelo tempo,
    quantos bytes iniciais batem, e com isso da para descobrir o hash byte a
    byte. Custa a mesma linha.
    """
    if not senha or not guardado:
        return False
    try:
        algo, n, r, p, sal, esperado = guardado.split("$")
        if algo != "scrypt":
            return False
        derivada = hashlib.scrypt(senha.encode("utf-8"), salt=_b64d(sal),
                                  n=int(n), r=int(r), p=int(p),
                                  dklen=len(_b64d(esperado)))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(derivada, _b64d(esperado))


# --------------------------------------------------------------------------- #
# Segredo de assinatura
# --------------------------------------------------------------------------- #

ARQUIVO_SEGREDO = ".session_secret"

_segredo_em_memoria: Optional[bytes] = None


def _caminho_do_segredo() -> str:
    base = (os.environ.get("DATA_DIR") or "data").strip() or "data"
    return os.path.join(base, ARQUIVO_SEGREDO)


def segredo_de_sessao() -> bytes:
    """A chave que assina os tokens.

    `SESSION_SECRET` no ambiente manda. Sem ela, um arquivo em `DATA_DIR` com
    permissao 0600, criado na primeira vez.

    **Precisa persistir**, e por isso nao e sorteado na memoria: um segredo novo
    a cada restart desconectaria todo mundo a cada deploy. E fica em `DATA_DIR`
    (um volume), e nao em `output/`, porque `output/` e varrido pela limpeza por
    idade -- mesmo motivo de o banco morar la.
    """
    global _segredo_em_memoria
    do_ambiente = (os.environ.get("SESSION_SECRET") or "").strip()
    if do_ambiente:
        return do_ambiente.encode("utf-8")
    if _segredo_em_memoria is not None:
        return _segredo_em_memoria
    caminho = _caminho_do_segredo()
    try:
        with open(caminho, "rb") as fh:
            guardado = fh.read().strip()
        if guardado:
            _segredo_em_memoria = guardado
            return guardado
    except OSError:
        pass
    novo = secrets.token_bytes(32)
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        # 0600 desde a criacao: gravar e so depois arrumar a permissao deixa uma
        # janela em que o segredo esta legivel para todo mundo no container.
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(novo)
    except OSError as e:
        # Sem disco gravavel o token ainda funciona nesta instancia; o preco e
        # que um restart desloga. Melhor que recusar login.
        print(f"⚠️  Nao consegui gravar {caminho} ({e}); a sessao nao sobrevive "
              "a um restart. Defina SESSION_SECRET no ambiente.")
    _segredo_em_memoria = novo
    return novo


def segredo_texto() -> str:
    """O mesmo segredo em ASCII, para quem exige `str`.

    **Nao usar `segredo_de_sessao().decode("utf-8", "ignore")`.** Os 32 bytes
    sao aleatorios, e decodificar com `ignore` DESCARTA os que nao formam UTF-8
    valido: medido, sobram de 13 a 21 caracteres, e sempre os mesmos tipos de
    byte. A chave encolhe e enviesa sem aviso -- nao quebra nada, so protege
    menos do que parece. Base64 preserva os 32 bytes inteiros.
    """
    return _b64e(segredo_de_sessao())


def esquecer_segredo() -> None:
    """So para teste: descarta o segredo em memoria."""
    global _segredo_em_memoria
    _segredo_em_memoria = None


# --------------------------------------------------------------------------- #
# Token
# --------------------------------------------------------------------------- #

#: Trinta dias. E ferramenta pessoal: obrigar login toda semana so ensina a
#: pessoa a escolher senha curta. A revogacao real e `token_version`.
TTL_PADRAO = 30 * 24 * 3600


def gerar_token(user_id: str, tenant_id: str, token_version: int = 1,
                ttl: int = TTL_PADRAO) -> str:
    payload = {"u": user_id, "t": tenant_id, "v": int(token_version),
               "exp": int(time.time()) + int(ttl)}
    corpo = _b64e(json.dumps(payload, separators=(",", ":"),
                             sort_keys=True).encode("utf-8"))
    assinatura = hmac.new(segredo_de_sessao(), corpo.encode("ascii"),
                          hashlib.sha256).digest()
    return f"{corpo}.{_b64e(assinatura)}"


def ler_token(token: Optional[str]) -> Optional[dict]:
    """O payload, ou None se a assinatura nao bate ou o prazo passou.

    **A assinatura e conferida ANTES de o payload ser lido como JSON.** Ao
    contrario, um payload torto de quem nao tem o segredo ja teria conseguido
    fazer o servidor interpretar dado dele.
    """
    if not token or not isinstance(token, str) or "." not in token:
        return None
    corpo, _, assinatura = token.partition(".")
    try:
        esperada = hmac.new(segredo_de_sessao(), corpo.encode("ascii"),
                            hashlib.sha256).digest()
        if not hmac.compare_digest(esperada, _b64d(assinatura)):
            return None
        payload = json.loads(_b64d(corpo))
    except (ValueError, TypeError, UnicodeEncodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        if int(payload.get("exp", 0)) <= time.time():
            return None
    except (TypeError, ValueError):
        return None
    if not payload.get("u") or not payload.get("t"):
        return None
    return payload


def token_do_header(authorization: Optional[str]) -> Optional[str]:
    """`Authorization: Bearer <token>` -> o token. O painel ja manda assim."""
    if not authorization:
        return None
    partes = authorization.split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1].strip() or None


# --------------------------------------------------------------------------- #
# Forca bruta
# --------------------------------------------------------------------------- #

#: Tentativas erradas antes de travar, e por quanto tempo. Em memoria: sao duas
#: instancias durante um deploy, entao o teto real e o dobro por alguns minutos.
#: Contar no banco transformaria toda tentativa de login numa escrita, e o que
#: isto precisa impedir e mil tentativas por minuto, nao dez.
MAX_TENTATIVAS = 8
TRAVA_SEGUNDOS = 300

_tentativas: dict = {}


def registrar_falha(chave: str) -> int:
    agora = time.time()
    recentes = [t for t in _tentativas.get(chave, []) if agora - t < TRAVA_SEGUNDOS]
    recentes.append(agora)
    _tentativas[chave] = recentes[-MAX_TENTATIVAS * 2:]
    return len(recentes)


def esta_travado(chave: str) -> bool:
    agora = time.time()
    recentes = [t for t in _tentativas.get(chave, []) if agora - t < TRAVA_SEGUNDOS]
    _tentativas[chave] = recentes
    return len(recentes) >= MAX_TENTATIVAS


def limpar_tentativas(chave: Optional[str] = None) -> None:
    if chave is None:
        _tentativas.clear()
    else:
        _tentativas.pop(chave, None)
