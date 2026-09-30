"""A midia gratis do video de IA (etapa 7.7, ADR-013): a imagem de cada cena e
a voz da narracao.

- **Imagem: Cloudflare Workers AI.** O FLUX.2 [klein] 4B aceita ate 4 imagens
  de referencia -- e e isso que mantem o personagem igual de uma cena para a
  outra e de um video para o outro. O FLUX.1 [schnell] fica de reserva, sem
  referencia (a consistencia cai para o texto, e o log diz).
- **Voz: Gemini TTS.** Uma chamada faz a narracao inteira, com a voz e o tom do
  estilo.

As regras da cascata de texto (`llm_cascade`) valem aqui tambem:

- so entra quem tem chave, e as chaves sao as MESMAS da cascata
  (`CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`, `GEMINI_API_KEY`);
- o modelo que o provedor diz nao existir passa ao proximo e nao e tentado de
  novo neste processo (os padroes de modelo apodrecem);
- a chave recusada para tudo, dizendo QUAL variavel conferir;
- a cota gratis do dia e contada em disco ANTES de gastar: a criacao para
  dizendo "a cota de hoje acabou", em vez de levar 429 no meio de um video.

A rede mora em `_post`; o que decide -- medidas, custo em neurons, o corpo do
pedido, a leitura da resposta, o WAV -- e puro, e o CI o exercita sem rede.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

URL_CLOUDFLARE = "https://api.cloudflare.com/client/v4/accounts/{conta}/ai/run/{modelo}"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"

MODELO_IMAGEM_PADRAO = "@cf/black-forest-labs/flux-2-klein-4b"
MODELO_IMAGEM_RESERVA = "@cf/black-forest-labs/flux-1-schnell"
MODELO_VOZ_PADRAO = "gemini-3.1-flash-tts-preview"
MODELOS_VOZ_RESERVA = ("gemini-2.5-flash-preview-tts",)

#: 9:16, perto de 1 megapixel: 4 blocos de 512x512 na conta do Cloudflare. A
#: montagem leva a 1080x1920, e o movimento lento esconde a ampliacao.
LARGURA, ALTURA = 768, 1344
#: O episodio longo (7.8) e deitado: as mesmas medidas trocadas, entao a mesma
#: conta de blocos -- a imagem horizontal custa o mesmo que a vertical.
LARGURA_HORIZONTAL, ALTURA_HORIZONTAL = ALTURA, LARGURA
#: O Workers AI so aceita referencia de ate 512x512, e no maximo 4.
LADO_DA_REFERENCIA = 512
MAX_REFERENCIAS = 4

#: Dos 10.000 neurons gratis do dia, 2.000 ficam para a cascata de texto, que
#: usa a mesma conta do Cloudflare. `CLOUDFLARE_IMAGE_NEURONS_DAILY` troca.
NEURONS_POR_DIA_PADRAO = 8000

# O custo em neurons, pelo levantamento do ADR-013. Errar para cima e o lado
# seguro: subestimar libera uma imagem que estoura a cota no meio do video.
KLEIN_ENTRADA_POR_BLOCO = 5.37
KLEIN_SAIDA_POR_BLOCO = 26.05
SCHNELL_POR_BLOCO = 4.80
SCHNELL_POR_PASSO = 9.60
SCHNELL_PASSOS = 4
#: Modelo que nao e nenhum dos dois conhecidos (trocado por variavel).
CUSTO_DESCONHECIDO = 150.0

#: As 30 vozes do Gemini TTS, com o jeito de cada uma. A tela as oferece com a
#: descricao; o motor so aceita nome desta lista.
VOZES = (
    ("Zephyr", "clara"), ("Puck", "animada"), ("Charon", "informativa"),
    ("Kore", "firme"), ("Fenrir", "empolgada"), ("Leda", "jovem"),
    ("Orus", "firme"), ("Aoede", "leve"), ("Callirrhoe", "tranquila"),
    ("Autonoe", "clara"), ("Enceladus", "sussurrada"), ("Iapetus", "nítida"),
    ("Umbriel", "tranquila"), ("Algieba", "suave"), ("Despina", "suave"),
    ("Erinome", "nítida"), ("Algenib", "rouca"), ("Rasalgethi", "informativa"),
    ("Laomedeia", "animada"), ("Achernar", "macia"), ("Alnilam", "firme"),
    ("Schedar", "equilibrada"), ("Gacrux", "madura"), ("Pulcherrima", "direta"),
    ("Achird", "amigável"), ("Zubenelgenubi", "casual"),
    ("Vindemiatrix", "gentil"), ("Sadachbia", "viva"),
    ("Sadaltager", "sábia"), ("Sulafat", "acolhedora"),
)
NOMES_DAS_VOZES = tuple(nome for nome, _ in VOZES)
VOZ_PADRAO = "Kore"


# --------------------------------------------------------------------------- #
# Erros
# --------------------------------------------------------------------------- #

class MidiaIndisponivel(RuntimeError):
    """A imagem ou a voz nao saiu. A mensagem e para a pessoa ler."""


class SemChave(MidiaIndisponivel):
    pass


class ChaveRecusada(MidiaIndisponivel):
    pass


class CotaEsgotada(MidiaIndisponivel):
    """A cota gratis do dia acabou (a nossa conta ou a do provedor)."""


# --------------------------------------------------------------------------- #
# Chaves
# --------------------------------------------------------------------------- #

def credenciais_cloudflare() -> tuple[str, str]:
    return ((os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip(),
            (os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "").strip())


def chave_gemini() -> str:
    return (os.environ.get("GEMINI_API_KEY") or "").strip()


def disponivel() -> dict:
    """O que este motor consegue criar agora, sem ir a rede."""
    token, conta = credenciais_cloudflare()
    return {"imagem": bool(token and conta), "voz": bool(chave_gemini())}


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

#: Modelos que o provedor disse nao existir, neste processo (um job = um
#: processo). Como o `_MODELO_INEXISTENTE` da cascata.
_SUMIRAM: set = set()


def modelos_de_imagem() -> list:
    padrao = (os.environ.get("CLOUDFLARE_IMAGE_MODEL") or "").strip() or MODELO_IMAGEM_PADRAO
    lista = [padrao] if padrao == MODELO_IMAGEM_RESERVA else [padrao, MODELO_IMAGEM_RESERVA]
    return [m for m in lista if m not in _SUMIRAM]


def modelos_de_voz() -> list:
    padrao = (os.environ.get("GEMINI_TTS_MODEL") or "").strip() or MODELO_VOZ_PADRAO
    lista = [padrao] + [m for m in MODELOS_VOZ_RESERVA if m != padrao]
    return [m for m in lista if m not in _SUMIRAM]


def aceita_referencia(modelo: str) -> bool:
    """So a familia FLUX.2 aceita imagem de referencia no Workers AI."""
    return "/flux-2" in modelo


def blocos(largura: int, altura: int) -> int:
    """Quantos blocos de 512x512 a imagem ocupa, arredondado para cima."""
    return max(1, math.ceil((max(1, largura) * max(1, altura)) / (512 * 512)))


def custo_em_neurons(modelo: str, largura: int = LARGURA, altura: int = ALTURA,
                     referencias: int = 0) -> float:
    if aceita_referencia(modelo) and "klein" in modelo:
        return round(KLEIN_SAIDA_POR_BLOCO * blocos(largura, altura)
                     + KLEIN_ENTRADA_POR_BLOCO * max(0, referencias), 2)
    if "flux-1-schnell" in modelo:
        # O schnell sai quadrado (1024x1024): 4 blocos, 4 passos.
        return round(SCHNELL_POR_BLOCO * 4 + SCHNELL_POR_PASSO * SCHNELL_PASSOS, 2)
    return CUSTO_DESCONHECIDO


# --------------------------------------------------------------------------- #
# A cota do dia, em disco (um processo por job, como o orcamento da cascata)
# --------------------------------------------------------------------------- #

def _caminho_da_cota() -> str:
    pasta = (os.environ.get("OUTPUT_DIR") or "output").strip() or "output"
    return os.path.join(pasta, ".midia_budget.json")


def dia_utc(agora: Optional[datetime] = None) -> str:
    """O Workers AI zera os neurons a meia-noite UTC."""
    return (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m-%d")


def dia_do_google(agora: Optional[datetime] = None) -> str:
    """O Gemini zera a cota a meia-noite do Pacifico. Sem a base de fusos, o
    UTC-8 fixo: o horario mais tarde, que erra para o lado de segurar."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return agora.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        return (agora - timedelta(hours=8)).strftime("%Y-%m-%d")


def _ler_cota() -> dict:
    try:
        with open(_caminho_da_cota(), encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar_cota(dados: dict) -> None:
    caminho = _caminho_da_cota()
    try:
        os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
        temporario = f"{caminho}.tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        os.replace(temporario, caminho)
    except OSError:
        pass                    # melhor esforco: a conta nunca derruba o video


def neurons_por_dia() -> float:
    try:
        return float(os.environ.get("CLOUDFLARE_IMAGE_NEURONS_DAILY") or NEURONS_POR_DIA_PADRAO)
    except ValueError:
        return float(NEURONS_POR_DIA_PADRAO)


def uso(agora: Optional[datetime] = None) -> dict:
    """O que o dia ja gastou: `{"neurons", "imagens", "vozes"}`."""
    dados = _ler_cota()
    img = dados.get("imagem") if dados.get("imagem", {}).get("dia") == dia_utc(agora) else {}
    voz = dados.get("voz") if dados.get("voz", {}).get("dia") == dia_do_google(agora) else {}
    return {"neurons": float(img.get("neurons") or 0), "imagens": int(img.get("imagens") or 0),
            "vozes": int(voz.get("chamadas") or 0),
            "neurons_por_dia": neurons_por_dia()}


def cabe_neurons(custo: float, agora: Optional[datetime] = None) -> bool:
    return uso(agora)["neurons"] + custo <= neurons_por_dia()


def imagens_que_cabem(modelo: str = MODELO_IMAGEM_PADRAO, referencias: int = 2,
                      agora: Optional[datetime] = None) -> int:
    """Quantas imagens ainda cabem hoje -- a tela e a criacao perguntam antes."""
    sobra = neurons_por_dia() - uso(agora)["neurons"]
    return max(0, int(sobra // custo_em_neurons(modelo, referencias=referencias)))


def registrar_neurons(custo: float, agora: Optional[datetime] = None, imagens: int = 1) -> None:
    dados = _ler_cota()
    dia = dia_utc(agora)
    img = dados.get("imagem") if dados.get("imagem", {}).get("dia") == dia else {"dia": dia}
    img["neurons"] = round(float(img.get("neurons") or 0) + custo, 2)
    img["imagens"] = max(0, int(img.get("imagens") or 0) + imagens)
    dados["imagem"] = img
    _gravar_cota(dados)


def registrar_voz(agora: Optional[datetime] = None) -> None:
    dados = _ler_cota()
    dia = dia_do_google(agora)
    voz = dados.get("voz") if dados.get("voz", {}).get("dia") == dia else {"dia": dia}
    voz["chamadas"] = int(voz.get("chamadas") or 0) + 1
    dados["voz"] = voz
    _gravar_cota(dados)


def vozes_por_dia() -> Optional[int]:
    """Teto proprio de chamadas de voz por dia. Sem a variavel, nenhum: a cota
    do Google nao e publicada por modelo, e o 429 dele e quem diz."""
    try:
        valor = int(os.environ.get("GEMINI_TTS_CALLS_DAILY") or 0)
    except ValueError:
        return None
    return valor if valor > 0 else None


# --------------------------------------------------------------------------- #
# A rede, isolada
# --------------------------------------------------------------------------- #

def _post(url: str, *, headers: dict, json_body=None, files=None,
          timeout: float = 180.0) -> tuple[int, str, bytes]:
    """(status, content-type, corpo). A unica funcao que vai a rede."""
    import httpx
    with httpx.Client(timeout=timeout) as cliente:
        resposta = cliente.post(url, headers=headers, json=json_body, files=files)
    return resposta.status_code, resposta.headers.get("content-type", ""), resposta.content


def _texto(corpo: bytes) -> str:
    try:
        return corpo.decode("utf-8", "replace")[:600]
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Imagem
# --------------------------------------------------------------------------- #

@dataclass
class Imagem:
    dados: bytes
    modelo: str
    referencias: int
    neurons: float

    @property
    def extensao(self) -> str:
        return ".png" if self.dados[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"


def preparar_referencia(dados: bytes) -> bytes:
    """A referencia do jeito que o Workers AI aceita: PNG de ate 512 de lado,
    sem transparencia (o fundo transparente vira preto em alguns modelos)."""
    from PIL import Image as _PIL
    with _PIL.open(io.BytesIO(dados)) as img:
        img = img.convert("RGBA")
        fundo = _PIL.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.split()[3])
        fundo.thumbnail((LADO_DA_REFERENCIA, LADO_DA_REFERENCIA))
        saida = io.BytesIO()
        fundo.save(saida, format="PNG", optimize=True)
        return saida.getvalue()


def pedido_de_imagem(modelo: str, prompt: str, referencias: Sequence[bytes] = (),
                     semente: Optional[int] = None, largura: int = LARGURA,
                     altura: int = ALTURA) -> dict:
    """Os argumentos de `_post` para o modelo: o FLUX.2 so aceita multipart
    (mesmo sem imagem), o FLUX.1 so aceita JSON."""
    if aceita_referencia(modelo):
        campos = [("prompt", (None, prompt[:2048])),
                  ("width", (None, str(int(largura)))),
                  ("height", (None, str(int(altura))))]
        if semente is not None:
            campos.append(("seed", (None, str(int(semente)))))
        for i, ref in enumerate(list(referencias)[:MAX_REFERENCIAS]):
            campos.append((f"input_image_{i}", (f"referencia_{i}.png", ref, "image/png")))
        return {"files": campos}
    corpo = {"prompt": prompt[:2048], "steps": SCHNELL_PASSOS}
    if semente is not None:
        corpo["seed"] = int(semente)
    return {"json_body": corpo}


def ler_imagem(tipo: str, corpo: bytes) -> bytes:
    """A imagem da resposta: bytes crus, ou `result.image` em base64."""
    if tipo.startswith("image/"):
        return corpo
    try:
        dados = json.loads(corpo)
    except ValueError:
        raise MidiaIndisponivel("o provedor de imagem respondeu algo que nao e imagem")
    resultado = dados.get("result") if isinstance(dados, dict) else None
    b64 = (resultado or {}).get("image") if isinstance(resultado, dict) else None
    if not b64:
        raise MidiaIndisponivel("o provedor de imagem respondeu sem a imagem")
    if b64.startswith("data:"):
        b64 = b64.split(",", 1)[-1]
    return base64.b64decode(b64)


_SEM_MODELO = re.compile(r"no such model|model not found|unknown model|not found", re.I)
_COTA = re.compile(r"neurons|allocation|quota|rate limit|too many requests|resource_exhausted", re.I)


def classificar_erro(status: int, corpo: str) -> str:
    """`modelo` (sumiu), `chave`, `cota`, `capacidade` (tente depois) ou
    `pedido` (o nosso pedido esta errado)."""
    if status in (401,) or (status == 403 and re.search(r"auth|token|key|permission", corpo, re.I)):
        return "chave"
    if "api key not valid" in corpo.lower() or "api_key_invalid" in corpo.lower():
        return "chave"
    if status == 429 or (status in (400, 403) and _COTA.search(corpo) and "neurons" in corpo.lower()):
        return "cota"
    if status == 404 or (status == 400 and _SEM_MODELO.search(corpo)):
        return "modelo"
    if status >= 500 or status in (408, 409):
        return "capacidade"
    return "pedido"


def gerar_imagem(prompt: str, *, referencias: Sequence[bytes] = (),
                 semente: Optional[int] = None, largura: int = LARGURA,
                 altura: int = ALTURA, tentativas: int = 3,
                 espera: float = 4.0) -> Imagem:
    """Uma imagem, pelo primeiro modelo que responder. Levanta
    `MidiaIndisponivel` (e as filhas) com a frase para a pessoa."""
    token, conta = credenciais_cloudflare()
    if not token or not conta:
        raise SemChave("Falta a chave do Cloudflare (CLOUDFLARE_API_TOKEN e "
                       "CLOUDFLARE_ACCOUNT_ID): e ela que faz as imagens gratis.")
    ultimo = "nenhum modelo de imagem respondeu"
    for modelo in modelos_de_imagem():
        refs = [r for r in referencias if r][:MAX_REFERENCIAS] if aceita_referencia(modelo) else []
        if referencias and not refs:
            print(f"   ⚠️ [imagem] {modelo} nao aceita referencia: o personagem so "
                  "vai pela descricao nesta cena.")
        custo = custo_em_neurons(modelo, largura, altura, len(refs))
        if not cabe_neurons(custo):
            raise CotaEsgotada(
                f"A cota gratis de imagem de hoje acabou ({int(uso()['neurons'])} de "
                f"{int(neurons_por_dia())} neurons). Ela volta a meia-noite UTC.")
        url = URL_CLOUDFLARE.format(conta=conta, modelo=modelo)
        for tentativa in range(1, max(1, tentativas) + 1):
            registrar_neurons(custo)
            try:
                status, tipo, corpo = _post(
                    url, headers={"Authorization": f"Bearer {token}"},
                    **pedido_de_imagem(modelo, prompt, refs, semente, largura, altura))
            except Exception as e:           # rede, timeout
                status, tipo, corpo = 0, "", str(e).encode("utf-8", "replace")
            if status == 200:
                return Imagem(dados=ler_imagem(tipo, corpo), modelo=modelo,
                              referencias=len(refs), neurons=custo)
            texto = _texto(corpo)
            tipo_de_erro = classificar_erro(status, texto) if status else "capacidade"
            if tipo_de_erro in ("modelo", "pedido", "chave"):
                # Nada foi gerado: o custo volta para a conta do dia.
                registrar_neurons(-custo, imagens=-1)
            if tipo_de_erro == "chave":
                raise ChaveRecusada("O Cloudflare recusou a chave (CLOUDFLARE_API_TOKEN). "
                                    "Confira o token e o id da conta nas Configuracoes.")
            if tipo_de_erro == "cota":
                raise CotaEsgotada("O Cloudflare disse que a cota gratis de hoje acabou. "
                                   "Ela volta a meia-noite UTC.")
            if tipo_de_erro == "modelo":
                _SUMIRAM.add(modelo)
                print(f"   ⚠️ [imagem] o Cloudflare nao tem mais o {modelo}; "
                      "CLOUDFLARE_IMAGE_MODEL troca o padrao.")
                ultimo = f"o modelo {modelo} nao existe mais"
                break
            if tipo_de_erro == "pedido":
                ultimo = f"o {modelo} recusou o pedido ({status}: {texto[:160]})"
                break
            ultimo = f"o {modelo} nao respondeu ({status or 'rede'}: {texto[:160]})"
            if tentativa < tentativas:
                time.sleep(espera * tentativa)
    raise MidiaIndisponivel(f"A imagem nao saiu: {ultimo}.")


# --------------------------------------------------------------------------- #
# Voz
# --------------------------------------------------------------------------- #

@dataclass
class Audio:
    wav: bytes
    modelo: str
    voz: str

    @property
    def segundos(self) -> float:
        with wave.open(io.BytesIO(self.wav)) as w:
            return w.getnframes() / float(w.getframerate() or 1)


def texto_para_falar(texto: str, instrucao: str = "") -> str:
    """O pedido do Gemini TTS: o tom em texto, antes do que se fala -- e o
    jeito documentado de pedir estilo ("Diga com alegria: ..."), que ele nao le
    em voz alta."""
    texto = (texto or "").strip()
    instrucao = re.sub(r"\s+", " ", (instrucao or "")).strip().rstrip(":")
    return f"{instrucao}:\n\n{texto}" if instrucao else texto


def pedido_de_voz(texto: str, voz: str, instrucao: str = "") -> dict:
    return {
        "contents": [{"parts": [{"text": texto_para_falar(texto, instrucao)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}},
        },
    }


def pcm_para_wav(pcm: bytes, taxa: int = 24000, canais: int = 1, largura: int = 2) -> bytes:
    saida = io.BytesIO()
    with wave.open(saida, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(largura)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return saida.getvalue()


def ler_voz(corpo: bytes) -> bytes:
    """O WAV da resposta do Gemini: o PCM em base64, com a taxa no mimeType
    ("audio/L16;codec=pcm;rate=24000")."""
    try:
        dados = json.loads(corpo)
        parte = dados["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise MidiaIndisponivel("o Gemini respondeu sem o audio da narracao")
    tipo = parte.get("mimeType") or ""
    pcm = base64.b64decode(parte.get("data") or "")
    if not pcm:
        raise MidiaIndisponivel("o Gemini respondeu um audio vazio")
    if "wav" in tipo:
        return pcm
    achou = re.search(r"rate=(\d+)", tipo)
    return pcm_para_wav(pcm, taxa=int(achou.group(1)) if achou else 24000)


def narrar(texto: str, *, voz: str = VOZ_PADRAO, instrucao: str = "",
           tentativas: int = 3, espera: float = 5.0) -> Audio:
    """A narracao inteira numa chamada. Levanta `MidiaIndisponivel`."""
    chave = chave_gemini()
    if not chave:
        raise SemChave("Falta a chave do Gemini (GEMINI_API_KEY): e ela que faz a voz gratis.")
    if voz not in NOMES_DAS_VOZES:
        voz = VOZ_PADRAO
    teto = vozes_por_dia()
    if teto is not None and uso()["vozes"] >= teto:
        raise CotaEsgotada(f"O teto de {teto} narracoes por dia (GEMINI_TTS_CALLS_DAILY) "
                           "ja foi usado hoje.")
    ultimo = "nenhum modelo de voz respondeu"
    for modelo in modelos_de_voz():
        url = URL_GEMINI.format(modelo=modelo)
        for tentativa in range(1, max(1, tentativas) + 1):
            try:
                status, _tipo, corpo = _post(url, headers={"x-goog-api-key": chave},
                                             json_body=pedido_de_voz(texto, voz, instrucao))
            except Exception as e:
                status, corpo = 0, str(e).encode("utf-8", "replace")
            if status == 200:
                registrar_voz()
                return Audio(wav=ler_voz(corpo), modelo=modelo, voz=voz)
            texto_do_erro = _texto(corpo)
            tipo_de_erro = classificar_erro(status, texto_do_erro) if status else "capacidade"
            if tipo_de_erro == "chave":
                raise ChaveRecusada("O Google recusou a chave do Gemini (GEMINI_API_KEY). "
                                    "Confira a chave nas Configuracoes.")
            if tipo_de_erro == "cota":
                raise CotaEsgotada("A cota gratis de voz do Gemini de hoje acabou. Ela volta "
                                   "a meia-noite do Pacifico (4h ou 5h da manha no Brasil).")
            if tipo_de_erro == "modelo":
                _SUMIRAM.add(modelo)
                print(f"   ⚠️ [voz] o Gemini nao tem mais o {modelo}; GEMINI_TTS_MODEL troca "
                      "o padrao.")
                ultimo = f"o modelo {modelo} nao existe mais"
                break
            if tipo_de_erro == "pedido":
                ultimo = f"o {modelo} recusou o pedido ({status}: {texto_do_erro[:160]})"
                break
            ultimo = f"o {modelo} nao respondeu ({status or 'rede'}: {texto_do_erro[:160]})"
            if tentativa < tentativas:
                time.sleep(espera * tentativa)
    raise MidiaIndisponivel(f"A voz nao saiu: {ultimo}.")
