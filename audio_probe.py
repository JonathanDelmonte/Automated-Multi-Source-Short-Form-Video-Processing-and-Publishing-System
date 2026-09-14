"""Estagio 02 Probe: o audio dirige, o video obedece (§4 do Plano Tecnico).

A decisao mais importante do projeto, nas palavras do proprio plano, e esta: um
video de 10GB vira ~100MB de WAV 16k mono, e transcricao e deteccao rodam **so
nisso**. O arquivo grande so e tocado no estagio 05/06, e mesmo ali so nos
trechos escolhidos. A consequencia e a que sustenta o alvo de 10GB: o custo de
processar passa a crescer com a **duracao falada**, nao com o tamanho do
arquivo -- um MOV 4K de 10GB e um MP4 720p de 800MB com a mesma live dentro
custam quase o mesmo.

A receita de extracao nao e nova; ela ja estava escrita no repositorio, dentro
do backend Parakeet (`transcribe_backends._extract_wav`), como wav temporario
so daquele caminho. O `MAPA-DOS-ESTAGIOS` registrou isso na Fase 0.2: "a linha
ja esta escrita, so esta no lugar errado da arvore". Este modulo e o lugar
certo.

**Tudo aqui falha aberto.** Um probe que nao roda ou uma extracao que nao sai
devolvem None e o pipeline segue pelo caminho antigo, entregando o video ao
modelo como antes. Esta camada e otimizacao de custo, e otimizacao que derruba
job nao e otimizacao.

So biblioteca padrao: os construtores de comando sao puros e testaveis sem
ffmpeg instalado, que e o que o CI tem.
"""
from __future__ import annotations

import json
import os
import subprocess

#: Nome do WAV dentro do diretorio do job. Dotfile pela mesma razao que
#: `.transcript_checkpoint.json` e `.resume.json`: e estado intermediario, nao
#: entregavel, e o diretorio do job e servido como arquivo estatico em
#: `/videos/<job>/`.
WAV_NAME = ".audio16k.wav"

SAMPLE_RATE = 16000
CHANNELS = 1
#: 16000 amostras/s x 2 bytes = 32000 bytes por segundo de audio.
BYTES_PER_SECOND = SAMPLE_RATE * 2


def ffprobe_cmd(path: str) -> list[str]:
    """Uma chamada so, devolvendo formato e streams em JSON."""
    return ["ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path]


def extract_wav_cmd(src: str, dest: str) -> list[str]:
    """A receita do §4, identica a que o Parakeet ja usava.

    `-vn` descarta o video antes de decodificar qualquer quadro, que e de onde
    vem a economia: num arquivo de 10GB o ffmpeg le o container inteiro mas so
    decodifica a trilha de audio.
    """
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le", dest]


def parse_probe(raw: str) -> dict:
    """Saida do ffprobe -> o dicionario que o pipeline usa. Pura.

    Campos ausentes viram None em vez de levantar: um container exotico pode
    nao declarar duracao, e isso nao e motivo para derrubar o job.
    """
    vazio = {"duration_s": None, "size_bytes": None, "width": None,
             "height": None, "has_audio": False, "audio_codec": None,
             "video_codec": None, "sample_rate": None, "channels": None}
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return vazio
    # JSON valido nao quer dizer objeto: `null` e `[]` passam pelo `loads` e
    # explodem no primeiro `.get`. O ffprobe nao devolve isso, mas quem chama
    # este parser em teste ou com a saida de outro binario, sim.
    if not isinstance(data, dict):
        return vazio

    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video"), None)

    def _num(valor, conv):
        try:
            return conv(valor)
        except (TypeError, ValueError):
            return None

    duracao = _num(fmt.get("duration"), float)
    if duracao is None and audio is not None:
        duracao = _num(audio.get("duration"), float)
    if duracao is not None and duracao <= 0:
        duracao = None

    return {
        "duration_s": duracao,
        "size_bytes": _num(fmt.get("size"), int),
        "width": _num((video or {}).get("width"), int),
        "height": _num((video or {}).get("height"), int),
        "has_audio": audio is not None,
        "audio_codec": (audio or {}).get("codec_name"),
        "video_codec": (video or {}).get("codec_name"),
        "sample_rate": _num((audio or {}).get("sample_rate"), int),
        "channels": _num((audio or {}).get("channels"), int),
    }


def probe(path: str, timeout: int = 60) -> dict:
    """Metadados do arquivo. Nunca levanta: o dicionario vazio significa
    "nao consegui perguntar", e quem chama segue pelo caminho antigo."""
    try:
        proc = subprocess.run(ffprobe_cmd(path), capture_output=True,
                              timeout=timeout)
        return parse_probe(proc.stdout.decode(errors="replace"))
    except (subprocess.SubprocessError, OSError) as e:
        print(f"⚠️  ffprobe falhou ({e}); seguindo sem os metadados da fonte.")
        return parse_probe("")


def ja_e_wav_do_pipeline(info: dict) -> bool:
    """Este arquivo ja E o WAV 16k mono? Evita extrair de novo o que ja foi
    extraido -- o caminho do Parakeet reextraia o proprio WAV que recebeu."""
    return bool(info.get("audio_codec") == "pcm_s16le"
                and info.get("sample_rate") == SAMPLE_RATE
                and info.get("channels") == CHANNELS
                and not info.get("video_codec"))


def extract_wav(src: str, dest: str, timeout: int = 3600) -> str | None:
    """Extrai o WAV 16k mono. Devolve o caminho, ou None se nao deu.

    None nao e erro: quem chama entrega o video ao modelo como antes. Uma
    fonte sem trilha de audio tambem devolve None, e ai o pipeline cai no
    caminho de analise visual, que ja existia.
    """
    try:
        proc = subprocess.run(extract_wav_cmd(src, dest), capture_output=True,
                              timeout=timeout)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"⚠️  Extracao de audio falhou ({e}); o modelo vai ler o video.")
        return None
    if proc.returncode != 0:
        erro = proc.stderr.decode(errors="replace").strip()[:200]
        print(f"⚠️  Extracao de audio falhou ({erro}); o modelo vai ler o video.")
        return None
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        print("⚠️  Extracao de audio saiu vazia; o modelo vai ler o video.")
        return None
    return dest


def wav_seconds(path: str) -> float | None:
    """Duracao do WAV pelo tamanho do arquivo, sem chamar ffprobe.

    PCM 16k mono s16le tem taxa constante, entao byte e tempo. Serve para o
    log e para conferir a extracao contra a duracao do container.
    """
    try:
        tamanho = os.path.getsize(path)
    except OSError:
        return None
    # 44 bytes de cabecalho RIFF; irrelevante em minutos, mas nao em 1s.
    return max(0.0, (tamanho - 44) / BYTES_PER_SECOND)
