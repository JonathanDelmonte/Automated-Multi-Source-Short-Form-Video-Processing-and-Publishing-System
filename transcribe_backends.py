"""Transcription backends: NVIDIA Parakeet (onnx-asr) with faster-whisper fallback.

Every caller goes through transcribe_media(), which returns the transcript
contract the whole pipeline depends on:

    {
      "text": str,          # full punctuated transcript
      "language": str,      # whisper-style short code ("es", "en", ...)
      "segments": [
        {"start": float, "end": float, "text": str,
         "words": [{"word": str, "start": float, "end": float}, ...]},
      ],
    }

Invariants the consumers rely on (clip cutting, karaoke subtitles, Remotion):
  - word["word"] carries a LEADING SPACE on true word starts; continuation
    fragments are merged into their base word (merge_continuation_words).
  - all numerics are native Python floats (json.dump of the transcript).
  - words sorted by start, segments chronological, absolute file timestamps.

TRANSCRIBE_BACKEND env: "whisper" (default) | "parakeet".
The parakeet path falls back to whisper automatically when the model errors,
produces no usable words, or the detected language is outside its 25
supported European languages (e.g. Japanese/Chinese/Arabic uploads).
GPU whisper in turn falls back to CPU whisper on CUDA errors (VRAM is shared
with other models on the host, so loads can OOM under load).
"""
import os
import subprocess
import tempfile
import threading
import time

from subtitles import (
    get_whisper_config,
    WHISPER_TRANSCRIBE_PARAMS,
    merge_continuation_words,
)

PARAKEET_MODEL_ID = "nemo-parakeet-tdt-0.6b-v3"

# The 25 European languages parakeet-tdt-0.6b-v3 supports (ISO 639-1).
PARAKEET_LANGS = {
    "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hu",
    "it", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "es", "sv", "ru",
    "uk",
}

# Serializes GPU transcription across concurrent jobs so N jobs can't stack
# N model contexts / decode batches in VRAM. CPU whisper stays ungated
# (CTranslate2 models are thread-safe and that matches the old behavior).
_ASR_GATE = threading.Semaphore(int(os.environ.get("ASR_GPU_CONCURRENCY", "1")))


class _NullGate:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NULL_GATE = _NullGate()


class _TranscribeProgress:
    """Emits '🎙️ Transcribing… NN% (Xs)' lines at 25% steps.

    These are the only transcription lines cloud users see (log_view keeps
    them), so they must stay free of technical detail.
    """

    def __init__(self, total_seconds):
        self.total = max(float(total_seconds or 0), 0.0)
        self.started = time.time()
        self.next_pct = 25

    def update(self, position_seconds):
        if self.total <= 0:
            return
        pct = min(int(position_seconds / self.total * 100), 100)
        while pct >= self.next_pct and self.next_pct <= 100:
            elapsed = int(time.time() - self.started)
            print(f"🎙️ Transcribing… {self.next_pct}% ({elapsed}s)", flush=True)
            self.next_pct += 25

# --- whisper singleton ------------------------------------------------------

_whisper_model = None
_whisper_key = None
_whisper_lock = threading.Lock()
# Set after a CUDA failure (e.g. VRAM exhausted by other models on the GPU)
# so every later transcription goes straight to CPU instead of re-failing.
_whisper_force_cpu = False
# Segundos da ultima carga do modelo, para a linha do log; None quando o
# modelo desta transcricao ja estava carregado.
_whisper_carga_s = None


def _get_whisper_model():
    """Process-wide WhisperModel singleton, rebuilt if the env config changes.

    Keeping the model resident avoids a full reload per transcription (which
    on GPU would also mean re-allocating a couple of GB of VRAM per job).

    **Carregar numa thread de fundo travou a transcricao** (23-set-2026). A
    ideia era esconder os ~17 s de carga dentro do download: uma thread
    carregava o modelo enquanto o yt-dlp baixava. O modelo subiu inteiro, a
    thread terminou, e a primeira transcricao ficou parada para sempre na
    placa -- sem erro, sem log, na maquina do autor (RTX 3060, WSL 2). Duas
    diferencas em relacao ao caminho que sempre funcionou, e nenhuma isolada:
    a thread que criou o modelo (e os recursos de CUDA por thread do
    ctranslate2) ja tinha acabado quando ele foi usado, e o CUDA subiu ao
    mesmo tempo em que o processo fazia fork para o yt-dlp, o deno e o ffmpeg.
    Nao voltar a carregar o whisper fora da thread que transcreve sem
    reproduzir na maquina dele antes -- aqui nao ha placa para ver.
    """
    global _whisper_model, _whisper_key, _whisper_carga_s
    cfg = get_whisper_config()
    if _whisper_force_cpu:
        cfg["device"] = "cpu"
        cfg["compute_type"] = "int8"
    key = (cfg["model_size"], cfg["device"], cfg["compute_type"])
    with _whisper_lock:
        if _whisper_model is None or _whisper_key != key:
            from faster_whisper import WhisperModel
            inicio = time.time()
            try:
                # Do disco primeiro. Sem isto o `snapshot_download` pergunta ao
                # Hugging Face pela revisao do modelo em TODO job, mesmo com os
                # 1,6 GB ja baixados -- uma ida a rede antes de cada transcricao.
                _whisper_model = WhisperModel(key[0], device=key[1],
                                              compute_type=key[2],
                                              local_files_only=True)
            except Exception as e:  # noqa: BLE001 - so o "nao esta no disco" segue
                if not _nao_esta_no_disco(e):
                    raise
                _whisper_model = WhisperModel(key[0], device=key[1],
                                              compute_type=key[2])
            _whisper_key = key
            _whisper_carga_s = time.time() - inicio
    return _whisper_model, cfg["device"]


def _nao_esta_no_disco(erro):
    """O erro e o `local_files_only` dizendo que o modelo ainda nao foi baixado?

    E o unico caso em que vale tentar de novo pela rede. Um erro de CUDA na
    mesma chamada (placa sem memoria) tem de subir como antes, para a queda
    para CPU do `run_whisper_transcription` -- repetir a carga so dobraria a
    espera ate ela.
    """
    return (isinstance(erro, FileNotFoundError)
            or "LocalEntryNotFound" in type(erro).__name__
            or "local_files_only" in str(erro)
            or "outgoing traffic has been disabled" in str(erro))


def linha_do_whisper(model_size, device, compute_type):
    """A linha de log que diz QUAL whisper vai rodar.

    Existe porque a pior queda deste modulo nao era a que levanta: sem o
    `docker-compose.gpu.yml` o `WHISPER_DEVICE` nem chega a ser `cuda`, e o
    padrao (`small` em CPU, int8) roda sem erro e sem uma linha sequer. Em
    22-set-2026 um video de 10 min levou 5 min so para transcrever numa maquina
    com RTX 3060, e o log colado nao tinha como mostrar por que.

    Em CPU a frase e CONDICIONAL, pela mesma regra do `diagnostico.py`: o
    container nao sabe se a maquina tem placa, sabe so que ela nao esta aqui.
    """
    if str(device).lower() == "cpu":
        return (f"🎙️ [ASR] whisper {model_size} em CPU ({compute_type}). Se esta "
                f"maquina tem placa NVIDIA, ela nao chegou ao container: "
                f"atalhos\\diagnostico.bat diz onde parou.")
    return f"🎙️ [ASR] whisper {model_size} em {device} ({compute_type})"


def tamanho_do_lote():
    """Quantos trechos de ate 30 s a placa decodifica de uma vez.

    **Desligado por padrao** (0 = sequencial). O modo em lotes foi o padrao
    por um job, e o log dele (23-set-2026, o video de 10,5 min de sempre) mediu
    o que custava: a decodificacao caiu so de ~38 s para 33 s, e a transcricao
    PERDEU FALA -- terminou em 536 s, quando a sequencial ia ate 602 s, com 7%
    menos palavras e uma frase repetida. O modo em lotes nao refaz com
    temperatura maior o trecho que saiu ruim; o sequencial refaz, e e isso que
    salva o trecho barulhento (gritaria, musica por baixo). Cinco segundos nao
    pagam legenda faltando no fim do video.

    `WHISPER_BATCH_SIZE` > 1 liga, para quem quiser medir de novo. Em CPU o
    lote nunca e usado: la nao ha paralelismo sobrando para ele ganhar.
    """
    try:
        return max(0, int(os.environ.get("WHISPER_BATCH_SIZE", "0")))
    except ValueError:
        return 0


def _pipeline_em_lotes(model):
    from faster_whisper import BatchedInferencePipeline
    return BatchedInferencePipeline(model=model)


def _transcrever(motor, media_path, params):
    """Roda `motor.transcribe` e MATERIALIZA os segmentos (o gerador e lazy:
    a decodificacao acontece enquanto se itera, entao a falha tambem)."""
    segments, info = motor.transcribe(media_path, **params)
    progress = _TranscribeProgress(getattr(info, "duration", 0))
    materialized = []
    for segment in segments:
        materialized.append(segment)
        progress.update(segment.end)
    # VAD trims trailing silence, so the last segment can end short of the
    # media duration — force the 100% line.
    progress.update(progress.total)
    return materialized, info


def _run_whisper_once(media_path, **params):
    global _whisper_carga_s
    model, device = _get_whisper_model()
    if _whisper_key:
        print(linha_do_whisper(*_whisper_key), flush=True)
    if _whisper_carga_s is not None:
        # Quanto custa subir o modelo: e o numero que decide se vale levar o
        # `.cache/` do disco do Windows para um volume do Docker.
        print(f"   ⏱️ [ASR] modelo carregado em {_whisper_carga_s:.1f}s", flush=True)
        _whisper_carga_s = None
    gate = _ASR_GATE if device != "cpu" else _NULL_GATE
    lote = tamanho_do_lote() if device != "cpu" else 0
    with gate:
        if lote > 1:
            # Em lotes, so quando pedido (ver `tamanho_do_lote`): o VAD corta
            # o audio em trechos de ate 30 s e a placa decodifica `lote` deles
            # de uma vez, em vez de um por um. O `without_timestamps=False`
            # mantem os segmentos do tamanho de uma frase, como no modo
            # sequencial: as janelas da deteccao de momentos se alinham a eles.
            try:
                return _transcrever(
                    _pipeline_em_lotes(model), media_path,
                    dict(params, batch_size=lote, without_timestamps=False))
            except Exception as e:  # noqa: BLE001 - o modo antigo e a rede
                print(f"⚠️ [ASR] transcricao em lotes falhou ({type(e).__name__}: "
                      f"{e}) — refazendo no modo sequencial.", flush=True)
        return _transcrever(model, media_path, params)


def run_whisper_transcription(media_path, **params):
    """Transcribe and FULLY materialize the segments inside the GPU gate.

    faster-whisper returns a lazy generator — decoding happens while
    iterating, so the gate must wrap list(segments), not just transcribe().
    Returns (segments_list, info).

    A CUDA failure (model load OOM or mid-decode) retries once on CPU and
    pins CPU for the rest of the process — the GPU is shared with other
    models, so a job must degrade instead of dying when VRAM runs out.
    """
    global _whisper_model, _whisper_force_cpu
    try:
        return _run_whisper_once(media_path, **params)
    except RuntimeError as e:
        if _whisper_force_cpu or "cuda" not in str(e).lower():
            raise
        print(f"⚠️ [ASR] whisper GPU failed ({e}) — retrying on CPU", flush=True)
        _whisper_force_cpu = True
        with _whisper_lock:
            _whisper_model = None  # drop the GPU model to release its VRAM
        return _run_whisper_once(media_path, **params)


def _transcribe_with_whisper(media_path):
    segments, info = run_whisper_transcription(media_path, **WHISPER_TRANSCRIBE_PARAMS)

    out_segments = []
    text_parts = []
    for segment in segments:
        words = [
            {"word": w.word, "start": float(w.start), "end": float(w.end)}
            for w in (segment.words or [])
        ]
        out_segments.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text,
            "words": merge_continuation_words(words),
        })
        text_parts.append(segment.text.strip())

    return {
        "text": " ".join(part for part in text_parts if part),
        "language": info.language,
        "segments": out_segments,
    }


# --- parakeet ---------------------------------------------------------------

_parakeet_model = None
_parakeet_lock = threading.Lock()


def _get_parakeet_model():
    global _parakeet_model
    with _parakeet_lock:
        if _parakeet_model is None:
            import onnx_asr
            model = onnx_asr.load_model(
                PARAKEET_MODEL_ID,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            vad = onnx_asr.load_vad("silero")
            _parakeet_model = model.with_vad(vad).with_timestamps()
    return _parakeet_model


def _extract_wav(media_path):
    """Parakeet wants 16kHz mono PCM wav. Returns ``(path, is_temp)``.

    Desde o estagio 02 (Fase 1, bloco 1.3) o pipeline ja entrega esse WAV
    pronto, e reextrai-lo seria decodificar outra vez o que acabou de ser
    decodificado. ``is_temp`` diz se o arquivo e nosso para apagar: o do
    pipeline **nao** e -- quem o criou tambem o remove, e apaga-lo aqui
    deixaria o resto do job sem audio.

    A confirmacao so custa um ffprobe quando a entrada ja e `.wav`; no caso
    normal (um mp4) a comparacao de extensao decide sozinha.
    """
    if media_path.lower().endswith(".wav"):
        import audio_probe
        if audio_probe.ja_e_wav_do_pipeline(audio_probe.probe(media_path)):
            return media_path, False

    # Ao lado da midia, e nao no /tmp do container (ver `reframe_v2.render`).
    fd, wav_path = tempfile.mkstemp(
        suffix=".wav", prefix="asr_",
        dir=os.path.dirname(os.path.abspath(media_path)))
    os.close(fd)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", media_path,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav_path,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE, timeout=1800)
    return wav_path, True


def _words_from_tokens(tokens, timestamps, seg_start, seg_end):
    """Group parakeet BPE tokens into words with absolute timestamps.

    Verified on the prod model: tokens already carry the leading-space
    word-start convention (" T", "odo", " el", ...) and timestamps are token
    START times in seconds relative to the VAD segment. A token without a
    leading space (subword continuations, punctuation like ",") belongs to
    the previous word — same semantics merge_continuation_words expects.
    Word end is inferred: next word's start, capped near the word's last
    token so a long inter-word silence doesn't stretch the highlight.
    """
    words = []
    last_token_ts = []
    for token, ts in zip(tokens, timestamps):
        if not token:
            continue
        abs_ts = float(ts) + seg_start
        if token.startswith(" ") or not words:
            words.append({
                "word": token if token.startswith(" ") else " " + token,
                "start": abs_ts,
            })
            last_token_ts.append(abs_ts)
        else:
            words[-1]["word"] += token
            last_token_ts[-1] = abs_ts

    for i, word in enumerate(words):
        next_start = words[i + 1]["start"] if i + 1 < len(words) else seg_end
        cap = last_token_ts[i] + 0.6
        word["end"] = float(max(word["start"] + 0.05, min(next_start, cap)))

    return words


def _transcribe_with_parakeet(media_path):
    model = _get_parakeet_model()
    wav_path, wav_e_nosso = _extract_wav(media_path)
    try:
        # 16kHz mono s16le wav -> 32000 bytes per second of audio.
        try:
            duration = os.path.getsize(wav_path) / 32000.0
        except OSError:
            duration = 0.0
        with _ASR_GATE:
            progress = _TranscribeProgress(duration)
            results = []
            for seg in model.recognize(wav_path):
                results.append(seg)
                progress.update(float(seg.end))
            progress.update(progress.total)
    finally:
        if wav_e_nosso:
            try:
                os.remove(wav_path)
            except OSError:
                pass

    out_segments = []
    text_parts = []
    for seg in results:
        seg_start = float(seg.start)
        seg_end = float(seg.end)
        seg_text = str(seg.text or "").strip()
        if not seg_text:
            continue
        out_segments.append({
            "start": seg_start,
            "end": seg_end,
            "text": seg_text,
            "words": _words_from_tokens(
                list(seg.tokens or []), list(seg.timestamps or []),
                seg_start, seg_end,
            ),
        })
        text_parts.append(seg_text)

    text = " ".join(text_parts)
    return {
        "text": text,
        "language": _detect_language(text),
        "segments": out_segments,
    }


def _detect_language(text):
    """Parakeet doesn't report a language; classify the transcribed text.

    py3langid is pure-Python and returns ISO 639-1 codes compatible with the
    whisper codes the pipeline expects (thumbnail titles, Gemini prompts).
    """
    sample = (text or "").strip()
    if len(sample) < 20:
        return "en"
    try:
        import py3langid
        lang, _score = py3langid.classify(sample[:4000])
        return lang
    except Exception:
        return "en"


def _parakeet_fallback_reason(transcript, duration_hint=None):
    """Return why the parakeet result is untrustworthy, or None if it's fine."""
    segments = transcript.get("segments") or []
    total_words = sum(len(s.get("words") or []) for s in segments)
    if total_words == 0:
        return "no words recognized"
    language = transcript.get("language")
    if language not in PARAKEET_LANGS:
        return f"language '{language}' outside parakeet's supported set"
    duration = duration_hint or (segments[-1]["end"] if segments else 0)
    # Real speech averages >100 wpm; under ~12 wpm on a long video means the
    # audio was mostly not recognized (e.g. unsupported language or music).
    if duration > 60 and total_words < duration * 0.2:
        return f"only {total_words} words in {duration:.0f}s of audio"
    return None


# --- public entry point -----------------------------------------------------

class NoAudioError(Exception):
    """The media has no audio track — nothing to transcribe."""


def _has_audio_stream(media_path) -> bool:
    """True if the file has at least one audio stream (ffprobe)."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", media_path],
            capture_output=True, text=True, timeout=60,
        )
        return bool(out.stdout.strip())
    except Exception:
        return True  # probe failed — don't block, let the backend try


def transcribe_media(media_path):
    """Transcribe with the configured backend, falling back to whisper."""
    # Silent videos (AI-generated clips, muted screen recordings) have no audio
    # stream; every ASR backend then crashes deep inside libav with an opaque
    # "tuple index out of range". Detect it up front and fail with a clear,
    # actionable reason instead.
    if not _has_audio_stream(media_path):
        raise NoAudioError(
            "This video has no audio track. OpenShorts finds viral moments from "
            "speech, so it needs a video with audio.")

    backend = os.environ.get("TRANSCRIBE_BACKEND", "whisper").strip().lower()

    if backend == "parakeet":
        try:
            transcript = _transcribe_with_parakeet(media_path)
            reason = _parakeet_fallback_reason(transcript)
            if reason is None:
                print(f"🎙️ [ASR] parakeet ok: lang={transcript['language']} "
                      f"segments={len(transcript['segments'])}")
                return transcript
            print(f"⚠️ [ASR] parakeet result rejected ({reason}) — "
                  f"falling back to whisper")
        except Exception as e:
            print(f"⚠️ [ASR] parakeet failed ({type(e).__name__}: {e}) — "
                  f"falling back to whisper")

    return _transcribe_with_whisper(media_path)
