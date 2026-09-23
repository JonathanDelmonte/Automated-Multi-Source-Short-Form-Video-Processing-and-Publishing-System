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
        def __init__(self, model_size, device=None, compute_type=None, **kwargs):
            self.model_size = model_size
            self.device = device
            self.kwargs = kwargs
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


def test_o_whisper_nao_carrega_em_thread_de_fundo():
    """Carregar o whisper numa thread de fundo, durante o download, TRAVOU a
    transcricao na maquina do autor (23-set-2026): o modelo subiu, a thread
    acabou e a primeira chamada a placa nunca voltou -- sem erro e sem log.
    O CI nao tem placa para reproduzir isso, entao a guarda e de forma: nem o
    modulo abre thread, nem o `main.py` pede o modelo por fora da transcricao.
    Ver o docstring de `_get_whisper_model` antes de mudar qualquer um dos dois.
    """
    import ast
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def chamadas(arquivo):
        arvore = ast.parse(open(os.path.join(raiz, arquivo), encoding="utf-8").read())
        for n in ast.walk(arvore):
            if isinstance(n, ast.Call):
                f = n.func
                yield f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")

    assert "Thread" not in set(chamadas("transcribe_backends.py"))
    do_main = set(chamadas("main.py"))
    assert "pre_carregar_whisper" not in do_main
    assert "_get_whisper_model" not in do_main


class TestTranscricaoEmLotes:
    """Na placa o whisper decodifica varios trechos de uma vez (23-set-2026).

    No job de 213 s a transcricao eram 37 s de decodificacao, um trecho por
    vez. O faster-whisper tem o modo em lotes desde a 1.1, e a config deste
    projeto ja era a que ele exige: VAD ligado e sem condicionar no texto
    anterior. A rede e o modo antigo, que continua a um passo.
    """

    @pytest.fixture
    def modelos(self, monkeypatch):
        chamadas = []

        class Segmentos:
            def __init__(self, quem, falha_no_meio=False):
                self.quem, self.falha_no_meio = quem, falha_no_meio

            def __iter__(self):
                yield SimpleNamespace(start=0.0, end=1.0, text=f" {self.quem}", words=None)
                if self.falha_no_meio:
                    raise RuntimeError("batch decode blew up mid-way")

        class Modelo:
            def __init__(self, model_size, device=None, compute_type=None, **kwargs):
                self.kwargs = kwargs

            def transcribe(self, path, **params):
                chamadas.append(("sequencial", params))
                return Segmentos("seq"), SimpleNamespace(language="pt", duration=1.0)

        class Lotes:
            falhar = None          # None | "na_chamada" | "no_meio"

            def __init__(self, model):
                self.model = model

            def transcribe(self, path, **params):
                chamadas.append(("lotes", params))
                if Lotes.falhar == "na_chamada":
                    raise RuntimeError("CUDA failed with error out of memory")
                return (Segmentos("lote", Lotes.falhar == "no_meio"),
                        SimpleNamespace(language="pt", duration=1.0))

        monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(
            WhisperModel=Modelo, BatchedInferencePipeline=Lotes))
        monkeypatch.setattr(tb, "_whisper_model", None)
        monkeypatch.setattr(tb, "_whisper_key", None)
        monkeypatch.setattr(tb, "_whisper_force_cpu", False)
        monkeypatch.setenv("WHISPER_DEVICE", "cuda")
        monkeypatch.setenv("WHISPER_COMPUTE", "float16")
        monkeypatch.delenv("WHISPER_BATCH_SIZE", raising=False)
        return chamadas, Lotes

    def test_na_placa_decodifica_em_lotes(self, modelos):
        chamadas, _ = modelos
        segmentos, _info = tb._run_whisper_once("a.wav", beam_size=5, vad_filter=True)
        assert [c[0] for c in chamadas] == ["lotes"]
        params = chamadas[0][1]
        assert params["batch_size"] == 8
        # Segmentos do tamanho de uma frase, como no sequencial: as janelas
        # da deteccao de momentos se alinham a eles.
        assert params["without_timestamps"] is False
        assert params["beam_size"] == 5 and params["vad_filter"] is True
        assert segmentos[0].text == " lote"

    def test_em_cpu_continua_sequencial(self, modelos, monkeypatch):
        chamadas, _ = modelos
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")
        tb._run_whisper_once("a.wav", beam_size=5)
        assert [c[0] for c in chamadas] == ["sequencial"]

    @pytest.mark.parametrize("valor", ["0", "1"])
    def test_a_variavel_desliga(self, modelos, monkeypatch, valor):
        chamadas, _ = modelos
        monkeypatch.setenv("WHISPER_BATCH_SIZE", valor)
        tb._run_whisper_once("a.wav", beam_size=5)
        assert [c[0] for c in chamadas] == ["sequencial"]

    @pytest.mark.parametrize("modo", ["na_chamada", "no_meio"])
    def test_falha_em_lotes_refaz_no_sequencial(self, modelos, capsys, monkeypatch, modo):
        # "no_meio": o gerador e lazy, entao a falha pode vir durante a
        # iteracao -- e o que ja tinha saido nao pode sobrar na resposta.
        chamadas, Lotes = modelos
        monkeypatch.setattr(Lotes, "falhar", modo)
        segmentos, _info = tb._run_whisper_once("a.wav", beam_size=5)
        assert [c[0] for c in chamadas] == ["lotes", "sequencial"]
        assert [s.text for s in segmentos] == [" seq"]
        assert "refazendo no modo sequencial" in capsys.readouterr().out


class TestCargaDoModelo:
    """O modelo sai do disco sem perguntar ao Hugging Face (23-set-2026)."""

    @pytest.fixture
    def criados(self, monkeypatch):
        tentativas = []

        class Modelo:
            nao_esta_no_disco = False
            erro_de_placa = False

            def __init__(self, model_size, device=None, compute_type=None, **kwargs):
                tentativas.append(kwargs)
                if Modelo.erro_de_placa:
                    raise RuntimeError("CUDA failed with error out of memory")
                if kwargs.get("local_files_only") and Modelo.nao_esta_no_disco:
                    class LocalEntryNotFoundError(FileNotFoundError):
                        pass
                    raise LocalEntryNotFoundError("Cannot find an appropriate cached snapshot")

        monkeypatch.setitem(sys.modules, "faster_whisper",
                            types.SimpleNamespace(WhisperModel=Modelo))
        monkeypatch.setattr(tb, "_whisper_model", None)
        monkeypatch.setattr(tb, "_whisper_key", None)
        monkeypatch.setattr(tb, "_whisper_carga_s", None)
        monkeypatch.setattr(tb, "_whisper_force_cpu", False)
        return tentativas, Modelo

    def test_modelo_ja_baixado_nao_vai_a_rede(self, criados):
        tentativas, _ = criados
        tb._get_whisper_model()
        assert tentativas == [{"local_files_only": True}]

    def test_primeira_vez_baixa(self, criados, monkeypatch):
        tentativas, Modelo = criados
        monkeypatch.setattr(Modelo, "nao_esta_no_disco", True)
        tb._get_whisper_model()
        assert tentativas == [{"local_files_only": True}, {}]

    def test_erro_de_placa_nao_repete_a_carga(self, criados, monkeypatch):
        # A queda para CPU mora no `run_whisper_transcription`; carregar de
        # novo pela rede so dobraria a espera ate ela.
        tentativas, Modelo = criados
        monkeypatch.setattr(Modelo, "erro_de_placa", True)
        with pytest.raises(RuntimeError, match="CUDA"):
            tb._get_whisper_model()
        assert len(tentativas) == 1

    def test_o_log_diz_quanto_a_carga_levou_uma_vez_so(self, criados, monkeypatch, capsys):
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")
        monkeypatch.setattr(tb, "_transcrever", lambda *a, **k: ([], None))
        tb._run_whisper_once("a.wav")
        tb._run_whisper_once("a.wav")
        saida = capsys.readouterr().out
        assert saida.count("modelo carregado em") == 1
