"""A compilacao dos cortes (etapa 7.8): um video horizontal longo para o
YouTube, feito dos cortes que a pessoa escolheu -- "os melhores momentos".

Cada trecho sai do VIDEO DE ORIGEM, deitado como foi gravado: o corte vertical
jogou fora os lados do quadro, e a compilacao e para a tela deitada. Quando a
origem nao esta mais no disco (um upload que a limpeza por tamanho levou, ou um
video criado por IA, que nao tem origem), o trecho e o proprio corte vertical,
no meio do quadro, sobre uma copia desfocada e ampliada dele.

- **Um ffmpeg so**: cada trecho entra com `-ss`/`-t` (o ffmpeg pula direto
  para o trecho, sem decodificar a fonte inteira) e passa pelo mesmo grafo --
  ajustar ao quadro 1920x1080 sem cortar nada, com o fundo desfocado atras
  (`fundo`); um trecho que ja e 16:9 cobre o fundo inteiro. Entre um trecho e outro, meio
  segundo de escuro (a imagem e o som somem e voltam): o corte seco de um
  assunto para outro soaria como defeito.
- **Os capitulos sao os cortes**: cada trecho abre um capitulo com o titulo do
  corte (`capitulos.validos` aplica as regras do YouTube).
- **A legenda e a do projeto de origem**: as palavras da transcricao de cada
  trecho, no tempo da compilacao, e o preset deitado
  (`montagem.legenda_horizontal`). Saem dois arquivos do mesmo grafo, o limpo e
  o legendado, como num corte.

O que decide e puro (o plano, os capitulos, a transcricao e o comando); a
sonda e o ffmpeg ficam em duas funcoes pequenas. O teste roda o ffmpeg de
verdade quando ele existe.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import List, Optional, Sequence

import capitulos
import ffmpeg_utils
import montagem

ARQUIVO_DO_PEDIDO = "compilacao.json"
#: Nome neutro, pelo mesmo motivo do `criar_video.BASE`: ele entra num filtro.
BASE = "compilacao"
#: Os estagios, na ordem; o `app.py` desenha a barra com esta lista
#: (`COMPILACAO_STAGES`), e ha teste comparando.
ESTAGIOS = ("k1_trechos", "k2_legenda", "k3_montagem")

TRECHOS_MIN, TRECHOS_MAX = 2, 60
#: Uma hora: o YouTube aceita mais, mas passar disso e outro produto (e um
#: render de horas numa maquina sem placa).
DURACAO_MAX_S = 3600
TRECHO_MINIMO_S = 1.0
LARGURA, ALTURA = montagem.LARGURA_HORIZONTAL, montagem.ALTURA_HORIZONTAL
QUADROS_POR_SEGUNDO = 30
#: O escurecer entre dois trechos: some em 0,25 s e volta em 0,25 s.
TRANSICAO_S = 0.25
#: O desfoque do fundo, na escala da saida (o GENERAL usa 12; aqui o fundo
#: aparece mais, entao desfoca mais).
DESFOQUE = 20
TITULO_MAX = 100
DESCRICAO_MAX = 1500


class CompilacaoInvalida(ValueError):
    """A frase vai para a tela (400) ou para o log do job."""


# --------------------------------------------------------------------------- #
# O plano
# --------------------------------------------------------------------------- #

def _numero(valor, nome: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise CompilacaoInvalida(f"{nome}: esperava um número")


def planejar(trechos: Sequence[dict]) -> List[dict]:
    """Os trechos na ordem, cada um com a `duracao` e o `inicio_no_video` (onde
    ele comeca na compilacao). Cada trecho e `{arquivo, corte_inicio,
    corte_fim, titulo, palavras}`, com as palavras ja no tempo do trecho (0 e
    o comeco dele). Levanta `CompilacaoInvalida` com o trecho e o motivo."""
    if len(trechos) < TRECHOS_MIN:
        raise CompilacaoInvalida(f"Escolha pelo menos {TRECHOS_MIN} cortes.")
    if len(trechos) > TRECHOS_MAX:
        raise CompilacaoInvalida(f"No máximo {TRECHOS_MAX} cortes numa compilação.")
    plano, inicio = [], 0.0
    for k, t in enumerate(trechos):
        corte_inicio = max(0.0, _numero(t.get("corte_inicio"), f"trecho {k + 1}"))
        corte_fim = _numero(t.get("corte_fim"), f"trecho {k + 1}")
        duracao = round(corte_fim - corte_inicio, 3)
        if duracao < TRECHO_MINIMO_S:
            raise CompilacaoInvalida(f"O trecho {k + 1} tem menos de {TRECHO_MINIMO_S:g} s.")
        plano.append({**t, "corte_inicio": corte_inicio, "corte_fim": corte_fim,
                      "duracao": duracao, "inicio_no_video": round(inicio, 3),
                      "titulo": re.sub(r"\s+", " ", str(t.get("titulo") or "")).strip()})
        inicio += duracao
    if inicio > DURACAO_MAX_S:
        raise CompilacaoInvalida(
            f"A compilação passaria de {DURACAO_MAX_S // 60} minutos "
            f"({int(inicio // 60)} min). Escolha menos cortes.")
    return plano


def duracao_total(plano: Sequence[dict]) -> float:
    return round(sum(t["duracao"] for t in plano), 3)


def capitulos_do_plano(plano: Sequence[dict]) -> list:
    """Um capitulo por trecho, com o titulo do corte (o que nao tem titulo nao
    abre capitulo), dentro das regras do YouTube."""
    return capitulos.validos([(t["inicio_no_video"], t["titulo"]) for t in plano],
                             duracao_total(plano))


def transcricao_do_plano(plano: Sequence[dict], idioma: str = "") -> dict:
    """As palavras de cada trecho no tempo da compilacao, um segmento por
    trecho. E dela que sai a legenda -- agora e numa troca de estilo pelo
    painel, que le o metadata."""
    segmentos = []
    for t in plano:
        palavras = []
        for w in t.get("palavras") or []:
            try:
                ini, fim = float(w["start"]), float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if ini < 0 or ini >= t["duracao"]:
                continue
            fim = min(max(fim, ini), t["duracao"])
            palavras.append({"word": w.get("word") or "",
                             "start": round(t["inicio_no_video"] + ini, 3),
                             "end": round(t["inicio_no_video"] + fim, 3)})
        if palavras:
            segmentos.append({"start": palavras[0]["start"], "end": palavras[-1]["end"],
                              "text": "".join(w["word"] for w in palavras).strip(),
                              "words": palavras})
    return {"language": idioma or "", "segments": segmentos}


# --------------------------------------------------------------------------- #
# O comando
# --------------------------------------------------------------------------- #

def fundo(largura: int, altura: int) -> str:
    """O fundo desfocado de um trecho: o meio do quadro no formato da saida
    (cobrindo, como um `object-fit: cover`), borrado a 1/4 da resolucao como o
    `ffmpeg_utils.fundo_desfocado`. Aquele corta so a largura -- serve ao
    video em pe, e esticaria um corte vertical tres vezes para o lado."""
    divisor = ffmpeg_utils.FUNDO_DIVISOR
    w = max(2, largura // divisor)
    h = max(2, altura // divisor)
    w -= w % 2
    h -= h % 2
    return (f"crop=w=min(iw\\,ih*{largura}/{altura}):h=min(ih\\,iw*{altura}/{largura}),"
            f"scale={w}:{h},gblur=sigma={DESFOQUE / divisor:g},"
            f"scale={largura}:{altura}:flags=bilinear")


def _grafo_do_trecho(k: int, trecho: dict, largura: int, altura: int) -> list:
    d = trecho["duracao"]
    fade = min(TRANSICAO_S, d / 4)
    saida_fade = max(0.0, d - fade)
    video = (
        f"[{k}:v]fps={QUADROS_POR_SEGUNDO},setpts=PTS-STARTPTS,split=2[f{k}][b{k}]",
        f"[b{k}]{fundo(largura, altura)},setsar=1[bg{k}]",
        f"[f{k}]scale={largura}:{altura}:force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1[fg{k}]",
        f"[bg{k}][fg{k}]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p,"
        f"trim=duration={d:.3f},"
        f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={saida_fade:.3f}:d={fade:.3f}[v{k}]",
    )
    if trecho.get("tem_audio", True):
        audio = (f"[{k}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"asetpts=PTS-STARTPTS,apad,atrim=duration={d:.3f},"
                 f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={saida_fade:.3f}:d={fade:.3f}[a{k}]")
    else:
        # Sem trilha de audio (raro, mas o concat exige uma por trecho): silencio.
        audio = (f"anullsrc=r=48000:cl=stereo,atrim=duration={d:.3f},"
                 f"aformat=sample_fmts=fltp:channel_layouts=stereo[a{k}]")
    return [*video, audio]


def _filtro_de_audio(audio_args: Optional[list]) -> tuple:
    """Separa o `-af` dos argumentos de audio (`ffmpeg_utils.audio_encode_args`
    traz o `loudnorm`): o ffmpeg nao aceita filtro simples num audio que sai de
    um grafo complexo, entao o filtro entra no grafo."""
    args = list(audio_args or [])
    if "-af" in args:
        i = args.index("-af")
        if i + 1 < len(args):
            return args[i + 1], args[:i] + args[i + 2:]
    return None, args


def _saida(video: str, audio: str, video_args: Optional[list], audio_args: Optional[list],
           arquivo: str) -> list:
    return (["-map", f"[{video}]", "-map", f"[{audio}]"]
            + list(video_args or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
            + ["-pix_fmt", "yuv420p", "-r", str(QUADROS_POR_SEGUNDO)]
            + list(audio_args or ["-c:a", "aac", "-b:a", "160k"])
            + ["-movflags", "+faststart", arquivo])


def comando(plano: Sequence[dict], saida: str, legenda: Optional[str] = None,
            saida_legendada: Optional[str] = None, video_args: Optional[list] = None,
            video_args_legendada: Optional[list] = None, audio_args: Optional[list] = None,
            largura: int = LARGURA, altura: int = ALTURA) -> list:
    """O comando do ffmpeg da compilacao inteira. Com `legenda` e
    `saida_legendada`, saem dois arquivos do mesmo grafo."""
    if not plano:
        raise CompilacaoInvalida("nenhum trecho")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for t in plano:
        cmd += ["-ss", f"{t['corte_inicio']:.3f}", "-t", f"{t['duracao']:.3f}",
                "-i", t["arquivo"]]
    partes = []
    for k, t in enumerate(plano):
        partes += _grafo_do_trecho(k, t, largura, altura)
    pares = "".join(f"[v{k}][a{k}]" for k in range(len(plano)))
    filtro_de_audio, audio_args = _filtro_de_audio(audio_args)
    if filtro_de_audio:
        partes.append(f"{pares}concat=n={len(plano)}:v=1:a=1[vc][ab]")
        partes.append(f"[ab]{filtro_de_audio}[ac]")
    else:
        partes.append(f"{pares}concat=n={len(plano)}:v=1:a=1[vc][ac]")
    if legenda and saida_legendada:
        queimar = (f"ass=filename='{montagem._escapar(legenda)}':"
                   f"fontsdir='{montagem._escapar(montagem._pasta_de_fontes())}'")
        partes.append("[vc]split=2[vs][vq]")
        partes.append(f"[vq]{queimar}[vl]")
        # O audio sai do grafo, e um rotulo so pode ir para uma saida.
        partes.append("[ac]asplit=2[as][al]")
        return (cmd + ["-filter_complex", ";".join(partes)]
                + _saida("vs", "as", video_args, audio_args, saida)
                + _saida("vl", "al", video_args_legendada or video_args, audio_args,
                         saida_legendada))
    return (cmd + ["-filter_complex", ";".join(partes)]
            + _saida("vc", "ac", video_args, audio_args, saida))


def montar(plano: Sequence[dict], saida: str, legenda: Optional[str] = None,
           saida_legendada: Optional[str] = None, video_args: Optional[list] = None,
           video_args_legendada: Optional[list] = None, audio_args: Optional[list] = None,
           timeout: Optional[float] = None) -> None:
    """Roda a compilacao. Levanta RuntimeError com o fim do erro do ffmpeg."""
    cmd = comando(plano, saida, legenda, saida_legendada, video_args,
                  video_args_legendada, audio_args)
    prazo = timeout or max(1800.0, duracao_total(plano) * 8)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=prazo)
    saidas = [saida] + ([saida_legendada] if legenda and saida_legendada else [])
    if r.returncode != 0 or any(not os.path.exists(a) or os.path.getsize(a) < 1024
                                for a in saidas):
        raise RuntimeError(f"a compilação falhou: {(r.stderr or '').strip()[-600:]}")


# --------------------------------------------------------------------------- #
# A sonda (so o ffmpeg: o ffprobe nem sempre vem junto)
# --------------------------------------------------------------------------- #

def ler_sonda(texto: str) -> dict:
    """A duracao e se ha trilha de audio, do que o `ffmpeg -i` escreve."""
    achou = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", texto or "")
    duracao = None
    if achou:
        h, m, s = achou.groups()
        duracao = int(h) * 3600 + int(m) * 60 + float(s)
    return {"duracao": duracao,
            "tem_video": bool(re.search(r"Stream #\S+.*?: Video:", texto or "")),
            "tem_audio": bool(re.search(r"Stream #\S+.*?: Audio:", texto or ""))}


def sondar(caminho: str) -> dict:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", caminho], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ler_sonda("")
    return ler_sonda(r.stderr)
