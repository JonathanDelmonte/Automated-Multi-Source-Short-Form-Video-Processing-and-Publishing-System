"""Central video-encoder selection for every ffmpeg encode call site.

FFMPEG_ENCODER env values:
  x264  (default) — CPU libx264, exact pre-GPU behavior
  nvenc           — force h264_nvenc; probed once and falls back to x264
                    (with a warning) if the GPU/driver is unavailable
  auto            — h264_nvenc when the probe succeeds, else x264

Only the codec/quality args live here; surrounding args (-movflags, -pix_fmt,
audio codecs, filters) stay at each call site.
"""
import os
import subprocess
import threading
import time

# Quality tiers pinning the historical libx264 settings.
QUALITY = "quality"            # was: -preset medium -crf 18
QUALITY_FAST = "quality_fast"  # was: -preset fast -crf 18
DELIVERY = "delivery"          # was: -preset fast -crf 22

_X264_ARGS = {
    QUALITY: ["-c:v", "libx264", "-preset", "medium", "-crf", "18"],
    QUALITY_FAST: ["-c:v", "libx264", "-preset", "fast", "-crf", "18"],
    DELIVERY: ["-c:v", "libx264", "-preset", "fast", "-crf", "22"],
}

# NVENC -cq is not 1:1 with x264 CRF: benchmarked on the prod GPU (RTX 4000
# Ada), cq ≈ crf + 7 lands in the same file-size ballpark, with vbr + AQ for
# quality. Presets p1-p7: p5 ≈ "medium", p4 ≈ "fast".
# -pix_fmt yuv420p is REQUIRED: with RGB input (the bgr24 rawvideo pipe from
# OpenCV) nvenc otherwise emits H.264 in gbrp/GBR colorspace, which ffmpeg
# reads fine but web players render as a magenta/green mess.
_NVENC_ARGS = {
    QUALITY: ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq",
              "-rc", "vbr", "-cq", "25", "-b:v", "0",
              "-spatial-aq", "1", "-temporal-aq", "1", "-pix_fmt", "yuv420p"],
    QUALITY_FAST: ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "hq",
                   "-rc", "vbr", "-cq", "25", "-b:v", "0", "-spatial-aq", "1",
                   "-pix_fmt", "yuv420p"],
    DELIVERY: ["-c:v", "h264_nvenc", "-preset", "p4",
               "-rc", "vbr", "-cq", "29", "-b:v", "0", "-spatial-aq", "1",
               "-pix_fmt", "yuv420p"],
}

# Output args that drop container/stream metadata carried over from the source
# — most notably YouTube's "produced by Google Inc." stream handler, which
# otherwise survives every re-encode (ffmpeg copies input metadata by default)
# and rides into the published clip. The per-stream specifiers are required:
# global -map_metadata -1 alone leaves the audio handler_name intact on a
# stream copy. Empty audio/video specifiers are harmless when a clip lacks that
# stream (ffmpeg ignores them, verified). Spliced in before the output filename
# at each final-artifact producer; kept out of video_encode_args() so that
# stays purely codec/quality args.
METADATA_SCRUB = ["-map_metadata", "-1", "-map_chapters", "-1",
                  "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1"]

# Loudness normalisation for the delivered clip.
#
# Without this the clip inherits whatever the source was mastered at, so a
# user's clips land anywhere: measured across real delivered clips on
# 26-jul-2026, from -13.8 LUFS on a loud upload down to -28 LUFS on a quiet
# talk. TikTok, Reels and Shorts all normalise playback to roughly -14 LUFS,
# which means the quiet ones just sound thin next to everything else in the
# feed — the loud ones aren't rewarded, the quiet ones are punished.
#
# I=-14 matches the platforms' target, LRA=11 is the usual allowance for speech.
# Applied at the clip cut, where the audio is being encoded to AAC anyway, so it
# costs nothing extra. AUDIO_NORMALIZE=0 turns it off.
#
# TP=-2.0, not the -1.5 that matches the platforms' own advice, because the
# ceiling is enforced BEFORE the AAC encode and the encoder then adds
# inter-sample peaks on top. Measured over 14 corpus clips (31-jul-2026):
#
#   TP=-1.5   peak reached +0.2 dBTP, 1 clip clipping,  8 above -1.0
#   TP=-2.0   peak reached -0.3 dBTP, 0 clipping,       5 above -1.0
#   TP=-3.0   peak reached -0.9 dBTP, 0 clipping,       1 above -1.0
#
# -3.0 also costs level: only 8 of 14 stayed inside -15..-13 LUFS versus 12 at
# -2.0, and level is what the listener notices. Two other fixes were tried and
# do NOT work, so don't reach for them again: an `alimiter` after loudnorm
# (limits sample peaks, not inter-sample, and measured WORSE at +0.7), and
# two-pass loudnorm with linear=true (+0.4, still clipping). The overshoot is
# the codec's, so the only lever is headroom.
LOUDNORM_FILTER = "loudnorm=I=-14:TP=-2.0:LRA=11"


# AI Act art. 50(2): a provider whose system generates synthetic audio or video
# has to mark the output in a machine-readable way. The regulation asks for the
# marking, not for a particular standard, and the cheap one that survives every
# player and every upload is a container tag: `ffprobe -show_format` reads it
# back, and TikTok/Reels/YouTube ignore it. Stamped by a stream copy, so it is
# a remux (no quality loss, ~0.2 s) and never a re-encode.
#
# Deliberately narrow: it goes on outputs where a machine actually synthesised
# voice or a person (dubbing, AI actors), not on an ordinary clip, whose audio
# and pixels are the user's own footage. Marking everything would make the tag
# mean nothing.
AI_DISCLOSURE = "AI-generated content produced with OpenShorts (openshorts.app)"


def mark_ai_generated(path, detail=""):
    """Stamp AI Act art. 50(2) machine-readable tags on a finished file.

    Returns True when the file now carries the tags. Never raises: a missing
    tag must not lose the user the video they just paid minutes for.
    """
    note = f"{AI_DISCLOSURE}: {detail}" if detail else AI_DISCLOSURE
    tmp = f"{path}.aitag.mp4"
    # `comment` and not a custom `ai_generated` key: mp4 only carries the
    # standard iTunes-style tags, and ffmpeg drops anything else without
    # warning (verified with ffprobe -show_entries format_tags).
    # -map 0 because ffmpeg's default picks one stream per type: a dubbed file
    # that ever ships two audio tracks would come back with one.
    cmd = ["ffmpeg", "-y", "-i", path, "-map", "0", "-c", "copy",
           "-metadata", f"comment={note}",
           "-movflags", "+faststart", tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            print(f"[ai-tag] skipped for {os.path.basename(path)}: {r.stderr[-300:]}")
            if os.path.exists(tmp):
                os.remove(tmp)
            return False
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[ai-tag] skipped for {os.path.basename(path)}: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False


def audio_encode_args():
    """AAC encode args for a delivered clip, with loudness normalisation."""
    args = ["-c:a", "aac"]
    if os.environ.get("AUDIO_NORMALIZE", "1").strip() != "0":
        args = ["-af", LOUDNORM_FILTER] + args
    return args

_probe_lock = threading.Lock()
_nvenc_ok = None  # None = not probed yet
_announced = False


def comando_da_sonda_nvenc():
    """O comando da sonda, para quem precisa reexecuta-lo e LER o erro.

    Existe para que haja uma definicao so. O `_probe_nvenc` abaixo descarta o
    stderr de proposito -- ele responde um booleano e nao pode poluir o log de
    todo job --, mas o `diagnostico.py` precisa do MOTIVO quando a resposta e
    nao, e "libnvidia-encode ausente" e "sem sessao livre na placa" pedem
    coisas diferentes. Duas copias do comando divergiriam no dia em que uma
    delas mudasse.
    """
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
        "-c:v", "h264_nvenc", "-f", "null", "-",
    ]


def _probe_nvenc():
    """One tiny lavfi encode to prove h264_nvenc works end-to-end.

    NVENC rejects frames smaller than ~145px, so the probe uses 256x256.
    Any failure (no ffmpeg binary, no GPU, no driver libs) means False.
    """
    try:
        result = subprocess.run(
            comando_da_sonda_nvenc(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def nvenc_available():
    """Probe h264_nvenc once and cache the verdict (thread-safe)."""
    global _nvenc_ok
    if _nvenc_ok is None:
        with _probe_lock:
            if _nvenc_ok is None:
                _nvenc_ok = _probe_nvenc()
    return _nvenc_ok


def reset_encoder_cache():
    """Test hook: forget the cached probe result."""
    global _nvenc_ok, _announced
    with _probe_lock:
        _nvenc_ok = None
        _announced = False


def modo_do_encoder():
    """O FFMPEG_ENCODER pedido: `x264` (padrao), `nvenc` ou `auto`.

    Uma definicao so, porque o `aquecimento.py` tambem precisa saber se a sonda
    do NVENC vai rodar -- com `x264` ela nunca roda, e aquecer seria gastar um
    processo com placa numa escolha que ninguem fez.
    """
    return os.environ.get("FFMPEG_ENCODER", "x264").strip().lower()


def video_encode_args(tier=QUALITY):
    """Return the codec/quality args for one encode, honoring FFMPEG_ENCODER."""
    global _announced
    if tier not in _X264_ARGS:
        raise ValueError(f"Unknown encode tier: {tier!r}")

    mode = modo_do_encoder()
    use_nvenc = False
    if mode in ("nvenc", "auto"):
        use_nvenc = nvenc_available()
        if mode == "nvenc" and not use_nvenc:
            print("⚠️ [Encoder] FFMPEG_ENCODER=nvenc but h264_nvenc is not "
                  "usable here — falling back to libx264")

    if not _announced:
        _announced = True
        print(f"🎞️ [Encoder] video encoder: {'h264_nvenc' if use_nvenc else 'libx264'} "
              f"(FFMPEG_ENCODER={mode})")

    return list((_NVENC_ARGS if use_nvenc else _X264_ARGS)[tier])


def escape_filter_value(value):
    r"""Escape a path/value for use inside a quoted FFmpeg filter argument.

    Windows absolute paths are why this exists: ``:`` separates filter options,
    so an interpolated ``C:/x/y.txt`` makes the parser look for an option named
    ``/x/y.txt`` and the whole filtergraph fails to build.

    NOTE: an apostrophe in the path cannot be made safe here. ffmpeg's
    filtergraph parser is not a shell -- the shell idiom ``'\''`` was tried on
    29-jul-2026 and is worse than doing nothing: it drops the apostrophe AND
    swallows the following option, so ``ass='...Earth'\''s.ass':fontsdir='...'``
    resolved to a filename of "...Earths.ass:fontsdir=..." and failed to open.

    The only reliable answer is to keep apostrophes OUT of any path that is
    interpolated into a filter. Callers generate their own filenames, so they
    control this: use a neutral name, never one derived from a video title.
    """
    return value.replace('\\', '/').replace(':', '\\:').replace("'", "\\'")


# An mp4 that ffmpeg abandoned before writing the moov atom is a few dozen
# bytes of ftyp, or nothing at all. Anything a real cut produces is orders of
# magnitude larger, so this only ever catches a failed encode.
MIN_CUT_BYTES = 1024

# Retries of a failed cut, on the SAME encoder, and how long to wait before
# each one. Deliberately not a fallback to libx264: the clip has to come out
# of the GPU like every other one, and a CPU re-encode of a 1080p cut on a box
# that is already busy enough to have failed the first attempt is the wrong
# trade. Waiting is the whole mechanism — whatever the GPU could not give this
# encode, another job finishes and gives back.
CUT_RETRY_WAITS = (3, 9)


def cut_clip(input_video, clip_temp_path, start, end, clip_number):
    """Cut [start, end] out of the source into ``clip_temp_path``.

    Raises RuntimeError with ffmpeg's own stderr when the cut does not produce
    a playable file. That report is the point: since dec-2025 the cut ran with
    its return code ignored and stderr captured into a pipe nobody read, so a
    failed cut handed an empty file to the reframer and the job's only visible
    error was "moov atom not found" three layers downstream — from ffmpeg,
    TransNetV2 and PySceneDetect in turn, each naming the temp file rather
    than the encode that never wrote it (prod, 9-sep-2026: three clips of one
    job lost, cause unrecoverable because the stderr had been discarded).

    A failed cut is retried on the same encoder after a wait. The failure this
    exists for is transient: the same command, on the same source file, cut
    fine by hand minutes later, and the nvenc probe is a 256x256 lavfi frame
    cached for the life of the process, so it stays true while a real 1080p
    session cannot allocate on a GPU that other jobs are filling.
    """
    encode_args = video_encode_args(QUALITY_FAST)
    command = [
        'ffmpeg', '-y',
        '-ss', str(start),
        '-to', str(end),
        '-i', input_video,
        *encode_args,
        *audio_encode_args(),
        clip_temp_path
    ]

    def _run():
        result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, errors="replace")
        # ffmpeg has been seen exiting 0 having written nothing, so the file
        # itself is the verdict, not just the return code.
        size = os.path.getsize(clip_temp_path) if os.path.exists(clip_temp_path) else 0
        ok = result.returncode == 0 and size >= MIN_CUT_BYTES
        return ok, f"exit {result.returncode}, {size} bytes\n{(result.stderr or '').strip()[-800:]}"

    for attempt, wait in enumerate(CUT_RETRY_WAITS + (None,), start=1):
        ok, report = _run()
        if ok:
            if attempt > 1:
                print(f"   ✅ Clip {clip_number} cut on attempt {attempt}.")
            return
        if wait is None:
            break
        print(f"   ⚠️ Cut of clip {clip_number} failed ({report}) — "
              f"retrying in {wait}s.")
        time.sleep(wait)

    raise RuntimeError(
        f"ffmpeg could not cut clip {clip_number} ({start}s-{end}s) from "
        f"{os.path.basename(input_video)} in {len(CUT_RETRY_WAITS) + 1} "
        f"attempts: {report}")




# O fundo desfocado do GENERAL e do INSET e desfocado em 1/4 da resolucao
# (23-set-2026). A cadeia de antes ampliava o quadro INTEIRO da fonte ate a
# altura da saida -- 1920x1080 virava 3413x1920, 6,5 milhoes de pixels por
# quadro em bicubico -- para jogar dois tercos fora no `crop` e depois borrar
# 1080x1920 com sigma 12. Era o filtro mais caro do render, e o resultado e um
# borrao: nenhum detalhe daquela resolucao sobrevive ao desfoque.
#
# Agora recorta primeiro (na fonte, a fatia com o formato da saida), reduz a
# 1/4, borra com sigma/4 -- o mesmo desfoque, medido na escala da saida -- e
# amplia. O renderizador v1 do upstream ja fazia exatamente isso em OpenCV
# ("visually identical for a defocused backdrop", `main.py`); o v2 em ffmpeg e
# que tinha voltado ao desfoque em resolucao cheia.
#
# Medido contra a cadeia antiga numa CPU de 4 nucleos: o grafo GENERAL inteiro,
# decodificacao incluida, foi de 105 para 206 quadros/s. SSIM do fundo sozinho:
# 0,9993 num video comum e 0,989 num zone plate, o pior caso de serrilhado.
#
# **A reducao nao pode ser `fast_bilinear`**, e foi a primeira tentativa: ela
# nao alarga o filtro ao reduzir, entao textura fina (listra de camisa, telao
# de LED) dobra em frequencia baixa, que o desfoque NAO remove. Nos testes
# ela caiu para SSIM 0,955 no zone plate, e numa textura fina em movimento o
# fundo passou a tremer 44% mais entre quadros. O padrao do `scale` (bicubico)
# alarga o filtro e nao treme; a ampliacao, de uma imagem ja borrada, e
# bilinear sem perda visivel.
FUNDO_DIVISOR = 4


def fundo_desfocado(out_w, out_h, sigma):
    """A cadeia do fundo, de um `[entrada]` a um `[saida]` que quem chama poe.

    ``sigma`` e o desfoque na escala da SAIDA (12 no GENERAL, 14 no INSET),
    como era antes; a divisao pela reducao fica aqui dentro.

    O `crop` usa o formato da saida sobre a altura inteira da fonte: e a mesma
    fatia central que a cadeia antiga pegava depois de ampliar. Numa fonte mais
    estreita que a saida o `min` a deixa inteira, e o `scale` a estica, como o
    `scale={out_w}:{out_h}` de antes tambem esticava.
    """
    w = max(2, out_w // FUNDO_DIVISOR)
    h = max(2, out_h // FUNDO_DIVISOR)
    w -= w % 2
    h -= h % 2
    return (f"crop=w=min(iw\\,ih*{out_w}/{out_h}):h=ih,"
            f"scale={w}:{h},"
            f"gblur=sigma={sigma / FUNDO_DIVISOR:g},"
            f"scale={out_w}:{out_h}:flags=bilinear")
