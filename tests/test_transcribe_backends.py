import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

import transcribe_backends as tb


class FakeFloat(float):
    """Stands in for numpy scalar types (float subclasses) from onnx-asr."""


def _seg(start, end, text, tokens, timestamps):
    return SimpleNamespace(
        start=FakeFloat(start), end=FakeFloat(end), text=text,
        tokens=tokens, timestamps=[FakeFloat(t) for t in timestamps],
    )


# --- token -> word reconstruction ------------------------------------------

def test_words_from_tokens_groups_by_leading_space():
    words = tb._words_from_tokens(
        [" T", "odo", " el", " mundo", "."],
        [0.0, 0.16, 0.32, 0.40, 0.60],
        seg_start=10.0, seg_end=12.0,
    )
    assert [w["word"] for w in words] == [" Todo", " el", " mundo."]
    # Absolute (segment-offset) start times.
    assert words[0]["start"] == pytest.approx(10.0)
    assert words[1]["start"] == pytest.approx(10.32)
    # End inferred from the next word's start; last word ends at segment end.
    assert words[0]["end"] == pytest.approx(10.32)
    assert words[2]["end"] == pytest.approx(11.0, abs=0.3)


def test_words_from_tokens_first_token_without_space_gets_one():
    words = tb._words_from_tokens([
        "Hola", " que", " tal"], [0.0, 0.5, 1.0], seg_start=0.0, seg_end=2.0)
    assert words[0]["word"] == " Hola"


def test_words_from_tokens_end_capped_after_long_silence():
    # Second word starts 5s later; first word's end must stay near its
    # own tokens (cap = last token + 0.6), not stretch across the gap.
    words = tb._words_from_tokens(
        [" uno", " dos"], [0.0, 5.0], seg_start=0.0, seg_end=6.0)
    assert words[0]["end"] <= 0.7


def test_words_from_tokens_all_floats_are_native():
    words = tb._words_from_tokens(
        [" a", "b", " c"], [0.0, 0.1, 0.2], seg_start=FakeFloat(1), seg_end=FakeFloat(2))
    for w in words:
        assert type(w["start"]) is float
        assert type(w["end"]) is float


# --- parakeet transcript assembly ------------------------------------------

@pytest.fixture
def fake_parakeet(monkeypatch):
    segs = [
        _seg(0.35, 2.43, "Todo el mundo habla.",
             [" Todo", " el", " mundo", " hab", "la", "."],
             [0.0, 0.32, 0.40, 0.56, 0.72, 0.80]),
        _seg(2.59, 5.57, "Pero, ¿qué es esto?",
             [" Pero", ",", " ¿", "qu", "é", " es", " esto", "?"],
             [0.0, 0.24, 0.32, 0.48, 0.64, 0.80, 1.04, 1.36]),
    ]
    model = SimpleNamespace(recognize=lambda path: iter(segs))
    monkeypatch.setattr(tb, "_get_parakeet_model", lambda: model)
    # (caminho, e_nosso_para_apagar) desde o bloco 1.3: o WAV do estagio 02
    # e reusado em vez de reextraido, e apaga-lo aqui deixaria o resto do
    # job sem audio.
    monkeypatch.setattr(tb, "_extract_wav", lambda path: ("/tmp/fake.wav", True))
    monkeypatch.setattr(tb.os, "remove", lambda path: None)
    return segs


def test_parakeet_transcript_matches_contract(fake_parakeet, monkeypatch):
    monkeypatch.setattr(tb, "_detect_language", lambda text: "es")
    t = tb._transcribe_with_parakeet("video.mp4")

    assert t["text"] == "Todo el mundo habla. Pero, ¿qué es esto?"
    assert t["language"] == "es"
    assert len(t["segments"]) == 2

    seg = t["segments"][1]
    assert type(seg["start"]) is float and type(seg["end"]) is float
    # Continuations (",", "qu", "é") merged; leading spaces preserved.
    assert [w["word"] for w in seg["words"]] == [" Pero,", " ¿qué", " es", " esto?"]
    # Segment offset applied to word times.
    assert seg["words"][0]["start"] == pytest.approx(2.59)
    # Whole transcript is JSON-serializable (metadata json.dump path).
    json.dumps(t)


def test_parakeet_words_survive_merge_continuation_words(fake_parakeet, monkeypatch):
    from subtitles import merge_continuation_words
    monkeypatch.setattr(tb, "_detect_language", lambda text: "es")
    t = tb._transcribe_with_parakeet("video.mp4")
    for seg in t["segments"]:
        assert merge_continuation_words(seg["words"]) == seg["words"]


# --- fallback policy --------------------------------------------------------

def _valid_transcript(n_words=200, duration=120.0, language="es"):
    words = [
        {"word": f" w{i}", "start": i * duration / n_words,
         "end": (i + 1) * duration / n_words}
        for i in range(n_words)
    ]
    return {"text": "x " * n_words, "language": language,
            "segments": [{"start": 0.0, "end": duration, "text": "x", "words": words}]}


def test_fallback_reason_none_for_good_result():
    assert tb._parakeet_fallback_reason(_valid_transcript()) is None


def test_fallback_when_no_words():
    t = {"text": "", "language": "es",
         "segments": [{"start": 0, "end": 5, "text": "x", "words": []}]}
    assert "no words" in tb._parakeet_fallback_reason(t)


def test_fallback_when_language_unsupported():
    assert "outside" in tb._parakeet_fallback_reason(
        _valid_transcript(language="ja"))


def test_fallback_when_word_rate_absurdly_low():
    assert tb._parakeet_fallback_reason(
        _valid_transcript(n_words=5, duration=600.0)) is not None


def test_transcribe_media_falls_back_on_parakeet_exception(monkeypatch):
    def boom(path):
        raise RuntimeError("onnx exploded")

    sentinel = {"text": "ok", "language": "en", "segments": []}
    monkeypatch.setenv("TRANSCRIBE_BACKEND", "parakeet")
    monkeypatch.setattr(tb, "_has_audio_stream", lambda path: True)
    monkeypatch.setattr(tb, "_transcribe_with_parakeet", boom)
    monkeypatch.setattr(tb, "_transcribe_with_whisper", lambda path: sentinel)
    assert tb.transcribe_media("video.mp4") is sentinel


def test_transcribe_media_default_is_whisper(monkeypatch):
    sentinel = {"text": "ok", "language": "en", "segments": []}
    monkeypatch.delenv("TRANSCRIBE_BACKEND", raising=False)
    monkeypatch.setattr(tb, "_has_audio_stream", lambda path: True)
    monkeypatch.setattr(
        tb, "_transcribe_with_parakeet",
        lambda path: (_ for _ in ()).throw(AssertionError("should not run")))
    monkeypatch.setattr(tb, "_transcribe_with_whisper", lambda path: sentinel)
    assert tb.transcribe_media("video.mp4") is sentinel


def test_transcribe_media_raises_on_silent_video(monkeypatch):
    monkeypatch.setattr(tb, "_has_audio_stream", lambda path: False)
    with pytest.raises(tb.NoAudioError):
        tb.transcribe_media("silent.mp4")


# --- whisper singleton ------------------------------------------------------

@pytest.fixture
def fake_faster_whisper(monkeypatch):
    created = []

    class FakeModel:
        def __init__(self, model_size, device=None, compute_type=None):
            self.model_size = model_size
            self.device = device
            created.append(self)

        def transcribe(self, path, **params):
            segs = (s for s in [SimpleNamespace(
                start=0.0, end=1.0, text=" hola", words=None)])
            return segs, SimpleNamespace(language="es")

    fake_module = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    monkeypatch.setattr(tb, "_whisper_model", None)
    monkeypatch.setattr(tb, "_whisper_key", None)
    return created


def test_whisper_model_is_singleton(fake_faster_whisper, monkeypatch):
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    a, _ = tb._get_whisper_model()
    b, _ = tb._get_whisper_model()
    assert a is b
    assert len(fake_faster_whisper) == 1


def test_whisper_model_rebuilds_when_env_changes(fake_faster_whisper, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "small")
    a, _ = tb._get_whisper_model()
    monkeypatch.setenv("WHISPER_MODEL", "large-v3-turbo")
    b, _ = tb._get_whisper_model()
    assert a is not b
    assert b.model_size == "large-v3-turbo"


def test_run_whisper_transcription_materializes_segments(fake_faster_whisper, monkeypatch):
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    segments, info = tb.run_whisper_transcription("video.mp4")
    assert isinstance(segments, list)
    assert info.language == "es"


class TestReusoDoWavDoPipeline:
    """Bloco 1.3: o estágio 02 já entrega o WAV 16k mono pronto.

    Reextraí-lo seria decodificar de novo o que acabou de ser decodificado, e —
    pior — apagá-lo no `finally` deixaria o resto do job sem áudio, porque quem
    o criou ainda o usa.
    """

    def _probe_diz(self, monkeypatch, e_o_nosso):
        import audio_probe
        monkeypatch.setattr(audio_probe, "probe", lambda p, **k: {})
        monkeypatch.setattr(audio_probe, "ja_e_wav_do_pipeline",
                            lambda info: e_o_nosso)

    def test_wav_do_pipeline_e_reusado_e_nao_e_nosso(self, monkeypatch, tmp_path):
        self._probe_diz(monkeypatch, True)
        wav = tmp_path / ".audio16k.wav"
        wav.write_bytes(b"\0" * 100)

        chamou_ffmpeg = []
        monkeypatch.setattr(tb.subprocess, "run",
                            lambda *a, **k: chamou_ffmpeg.append(a))

        caminho, e_nosso = tb._extract_wav(str(wav))
        assert caminho == str(wav)
        assert e_nosso is False
        assert chamou_ffmpeg == [], "não pode reextrair o que já está pronto"

    def test_wav_de_terceiro_ainda_e_convertido(self, monkeypatch, tmp_path):
        # Um .wav qualquer (44.1kHz estéreo, por exemplo) não serve ao Parakeet.
        self._probe_diz(monkeypatch, False)
        monkeypatch.setattr(tb.subprocess, "run", lambda *a, **k: None)
        caminho, e_nosso = tb._extract_wav(str(tmp_path / "outro.wav"))
        assert e_nosso is True
        assert caminho != str(tmp_path / "outro.wav")

    def test_mp4_nao_paga_ffprobe(self, monkeypatch, tmp_path):
        # O caso normal decide pela extensão: nenhum processo extra.
        import audio_probe

        def _nao_devia(*a, **k):
            raise AssertionError("ffprobe não deveria ser chamado para um mp4")
        monkeypatch.setattr(audio_probe, "probe", _nao_devia)
        monkeypatch.setattr(tb.subprocess, "run", lambda *a, **k: None)
        caminho, e_nosso = tb._extract_wav(str(tmp_path / "video.mp4"))
        assert e_nosso is True
        # Ao lado da mídia, e não no /tmp do container (22-set-2026): lá dentro
        # o arquivo ocupa o disco do Docker, que no Windows não encolhe.
        assert os.path.dirname(caminho) == str(tmp_path)

    def test_parakeet_nao_apaga_o_wav_do_pipeline(self, monkeypatch, tmp_path):
        wav = tmp_path / ".audio16k.wav"
        wav.write_bytes(b"\0" * 32000)

        monkeypatch.setattr(tb, "_extract_wav", lambda path: (str(wav), False))
        monkeypatch.setattr(tb, "_get_parakeet_model",
                            lambda: SimpleNamespace(recognize=lambda p: iter([])))
        monkeypatch.setattr(tb, "_detect_language", lambda text: "pt")
        tb._transcribe_with_parakeet(str(wav))

        assert wav.exists(), (
            "apagar o WAV do estágio 02 deixaria o resto do job sem áudio")


# --- qual whisper rodou (22-set-2026) ----------------------------------------

class TestLinhaDoWhisper:
    """O log do job tem de dizer qual whisper rodou.

    Sem o overlay de GPU o `WHISPER_DEVICE` nem chega a ser `cuda`: o padrao
    (`small` em CPU) roda sem erro e sem linha nenhuma. Um video de 10 min
    levou 5 min so para transcrever numa maquina com RTX 3060, e o log colado
    nao tinha como mostrar o motivo.
    """

    def test_em_cpu_a_linha_aponta_o_diagnostico(self):
        linha = tb.linha_do_whisper("small", "cpu", "int8")
        assert "small" in linha and "CPU" in linha and "int8" in linha
        assert "diagnostico.bat" in linha

    def test_em_cpu_a_frase_e_condicional(self):
        """O container nao sabe se a maquina tem placa: afirmar que ela
        "devia estar aqui" seria errado numa maquina sem nenhuma."""
        assert "Se esta maquina tem placa" in tb.linha_do_whisper("small", "cpu", "int8")

    def test_na_placa_nao_ha_o_que_consertar(self):
        linha = tb.linha_do_whisper("large-v3-turbo", "cuda", "float16")
        assert "large-v3-turbo" in linha and "cuda" in linha
        assert "diagnostico" not in linha

    def test_a_linha_sai_no_log_da_transcricao(self, fake_faster_whisper,
                                               monkeypatch, capsys):
        monkeypatch.setenv("WHISPER_MODEL", "small")
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")
        monkeypatch.setenv("WHISPER_COMPUTE", "int8")
        monkeypatch.setattr(tb, "_whisper_force_cpu", False)
        tb.run_whisper_transcription("video.mp4")
        assert "whisper small em CPU (int8)" in capsys.readouterr().out


class TestPreCargaDoWhisper:
    """O whisper carrega numa thread enquanto o video baixa (23-set-2026).

    No job de 343 s a carga levou 17 s e so comecava depois dos 40 s de
    download. As duas esperas sao independentes -- rede de um lado, disco e
    placa do outro --, entao a carga cabe dentro do download.
    """

    def test_a_transcricao_espera_a_carga_e_nao_carrega_de_novo(self, monkeypatch):
        import threading
        import time as _time
        criados = []
        comecou = threading.Event()

        class ModeloLento:
            def __init__(self, model_size, device=None, compute_type=None):
                comecou.set()
                _time.sleep(0.3)          # a leitura dos pesos
                criados.append(self)

        monkeypatch.setitem(sys.modules, "faster_whisper",
                            types.SimpleNamespace(WhisperModel=ModeloLento))
        monkeypatch.setattr(tb, "_whisper_model", None)
        monkeypatch.setattr(tb, "_whisper_key", None)
        monkeypatch.setattr(tb, "_whisper_force_cpu", False)
        monkeypatch.delenv("TRANSCRIBE_BACKEND", raising=False)

        thread = tb.pre_carregar_whisper()
        assert comecou.wait(2)            # a carga esta EM CURSO...
        modelo, _ = tb._get_whisper_model()   # ...quando a transcricao pede
        thread.join(2)
        assert len(criados) == 1          # um modelo so, o da pre-carga
        assert modelo is criados[0]

    def test_so_o_whisper_e_pre_carregado(self, monkeypatch):
        monkeypatch.setenv("TRANSCRIBE_BACKEND", "parakeet")
        chamadas = []
        monkeypatch.setattr(tb, "_get_whisper_model", lambda: chamadas.append(1))
        assert tb.pre_carregar_whisper() is None
        assert chamadas == []

    def test_falha_na_pre_carga_vira_uma_linha_e_nao_derruba(self, monkeypatch, capsys):
        monkeypatch.delenv("TRANSCRIBE_BACKEND", raising=False)

        def sem_placa():
            raise RuntimeError("CUDA failed with error out of memory")

        monkeypatch.setattr(tb, "_get_whisper_model", sem_placa)
        tb.pre_carregar_whisper().join(2)
        saida = capsys.readouterr().out
        assert "pre-carga do whisper falhou" in saida
        assert "carrega na hora de transcrever" in saida


def test_o_main_pre_carrega_antes_do_download():
    """`main.py` so importa com torch, entao o CI le a arvore: a pre-carga tem
    de vir ANTES do estagio 01_ingest, e so quando algo vai ser transcrito."""
    import ast
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "main.py")
    arvore = ast.parse(open(caminho, encoding="utf-8").read())

    chamada = next(n for n in ast.walk(arvore)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "pre_carregar_whisper")
    ingest = next(n for n in ast.walk(arvore)
                  if isinstance(n, ast.With) and "01_ingest" in ast.unparse(n.items[0]))
    assert chamada.lineno < ingest.lineno

    # O `if` mais de dentro que envolve a chamada (o de fora e o `__main__`).
    guarda = max((n for n in ast.walk(arvore)
                  if isinstance(n, ast.If) and chamada in list(ast.walk(n))),
                 key=lambda n: n.lineno)
    condicao = ast.unparse(guarda.test)
    for termo in ("args.skip_analysis", "args.transcript", "TRANSCRIPT_CHECKPOINT"):
        assert termo in condicao
