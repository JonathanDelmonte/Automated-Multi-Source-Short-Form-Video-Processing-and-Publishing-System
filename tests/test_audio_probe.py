"""Estágio 02: o áudio dirige, o vídeo obedece (Fase 1, bloco 1.3).

Os construtores de comando são puros e testados literalmente — a receita
`-vn -ac 1 -ar 16000 -c:a pcm_s16le` é a decisão do §4, e uma flag perdida aqui
não quebra nada visivelmente: só volta a custar o tamanho do arquivo em vez da
duração falada.

O resto testa o comportamento que importa quando o mundo falha: **tudo falha
aberto**. ffprobe que não roda, extração que sai vazia, container sem duração —
todos devolvem "não consegui" e o pipeline segue pelo caminho antigo.
"""
import json
import subprocess

import pytest

import audio_probe as ap


class TestComandos:
    def test_extracao_e_a_receita_do_plano(self):
        cmd = ap.extract_wav_cmd("/in.mp4", "/out.wav")
        assert cmd[:6] == ["ffmpeg", "-y", "-loglevel", "error", "-i", "/in.mp4"]
        # -vn descarta o vídeo ANTES de decodificar qualquer quadro: é daí que
        # vem a economia num arquivo de 10GB.
        assert "-vn" in cmd
        assert cmd[cmd.index("-ac") + 1] == "1"
        assert cmd[cmd.index("-ar") + 1] == "16000"
        assert cmd[cmd.index("-c:a") + 1] == "pcm_s16le"
        assert cmd[-1] == "/out.wav"

    def test_receita_identica_a_que_ja_existia_no_parakeet(self):
        # O MAPA-DOS-ESTAGIOS registrou que a linha já estava escrita, no lugar
        # errado da árvore. Se divergirem, uma das duas está errada.
        nossa = ap.extract_wav_cmd("X", "Y")
        do_parakeet = ["ffmpeg", "-y", "-loglevel", "error", "-i", "X",
                       "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "Y"]
        assert nossa == do_parakeet

    def test_ffprobe_pede_formato_e_streams_de_uma_vez(self):
        cmd = ap.ffprobe_cmd("/in.mp4")
        assert "-show_format" in cmd and "-show_streams" in cmd
        assert cmd[cmd.index("-print_format") + 1] == "json"
        assert cmd[-1] == "/in.mp4"


def _saida(duration="600.5", size="123456789", audio=True, video=True,
           sample_rate="48000", channels="2", acodec="aac", vcodec="h264"):
    streams = []
    if video:
        streams.append({"codec_type": "video", "codec_name": vcodec,
                        "width": 1920, "height": 1080})
    if audio:
        streams.append({"codec_type": "audio", "codec_name": acodec,
                        "sample_rate": sample_rate, "channels": channels})
    fmt = {"size": size}
    if duration is not None:
        fmt["duration"] = duration
    return json.dumps({"format": fmt, "streams": streams})


class TestLeituraDoProbe:
    def test_arquivo_normal(self):
        info = ap.parse_probe(_saida())
        assert info["duration_s"] == pytest.approx(600.5)
        assert (info["width"], info["height"]) == (1920, 1080)
        assert info["has_audio"] is True
        assert info["audio_codec"] == "aac"
        assert info["size_bytes"] == 123456789

    def test_sem_trilha_de_audio(self):
        info = ap.parse_probe(_saida(audio=False))
        assert info["has_audio"] is False
        assert info["audio_codec"] is None

    def test_container_sem_duracao_cai_na_do_stream(self):
        bruto = json.loads(_saida(duration=None))
        bruto["streams"][1]["duration"] = "42.0"
        assert ap.parse_probe(json.dumps(bruto))["duration_s"] == pytest.approx(42.0)

    def test_duracao_zero_e_ausencia_de_duracao(self):
        # Live e HLS às vezes declaram 0; tratar como número faria o cálculo de
        # "tokens por minuto falado" dividir por zero lá na frente.
        assert ap.parse_probe(_saida(duration="0"))["duration_s"] is None
        assert ap.parse_probe(_saida(duration="N/A"))["duration_s"] is None

    @pytest.mark.parametrize("bruto", ["", "não é json", "{}", "null", "[]"])
    def test_saida_ilegivel_nao_levanta(self, bruto):
        info = ap.parse_probe(bruto)
        assert info["duration_s"] is None and info["has_audio"] is False

    def test_campos_nao_numericos_viram_none(self):
        bruto = json.dumps({"format": {"duration": "abc", "size": "xyz"},
                            "streams": [{"codec_type": "video", "width": "?"}]})
        info = ap.parse_probe(bruto)
        assert info["duration_s"] is None
        assert info["size_bytes"] is None
        assert info["width"] is None


class TestReconhecerOProprioWav:
    def test_o_wav_do_pipeline(self):
        info = ap.parse_probe(_saida(video=False, acodec="pcm_s16le",
                                     sample_rate="16000", channels="1"))
        assert ap.ja_e_wav_do_pipeline(info) is True

    @pytest.mark.parametrize("kwargs", [
        {"sample_rate": "44100"},               # taxa errada
        {"channels": "2"},                      # estéreo
        {"acodec": "mp3"},                      # não é PCM
    ])
    def test_wav_parecido_nao_conta(self, kwargs):
        base = dict(video=False, acodec="pcm_s16le", sample_rate="16000", channels="1")
        base.update(kwargs)
        assert ap.ja_e_wav_do_pipeline(ap.parse_probe(_saida(**base))) is False

    def test_video_com_audio_16k_ainda_precisa_de_extracao(self):
        # Um mp4 cuja trilha já é 16k mono continua sendo um mp4: entregá-lo ao
        # modelo faria decodificar o vídeo junto, que é o que o estágio evita.
        info = ap.parse_probe(_saida(acodec="pcm_s16le", sample_rate="16000",
                                     channels="1"))
        assert ap.ja_e_wav_do_pipeline(info) is False


class TestFalhaAberta:
    def test_probe_sem_ffprobe_instalado(self, monkeypatch):
        def _boom(*a, **k):
            raise FileNotFoundError("ffprobe")
        monkeypatch.setattr(ap.subprocess, "run", _boom)
        assert ap.probe("/x.mp4")["duration_s"] is None

    def test_probe_com_timeout(self, monkeypatch):
        def _boom(*a, **k):
            raise subprocess.TimeoutExpired("ffprobe", 60)
        monkeypatch.setattr(ap.subprocess, "run", _boom)
        assert ap.probe("/x.mp4") == ap.parse_probe("")

    def test_extracao_com_erro_devolve_none(self, monkeypatch, tmp_path):
        class _Proc:
            returncode = 1
            stdout = b""
            stderr = b"Invalid data found"
        monkeypatch.setattr(ap.subprocess, "run", lambda *a, **k: _Proc())
        assert ap.extract_wav("/x.mp4", str(tmp_path / "o.wav")) is None

    def test_extracao_vazia_devolve_none(self, monkeypatch, tmp_path):
        destino = tmp_path / "o.wav"

        class _Proc:
            returncode = 0
            stdout = b""
            stderr = b""

        def _run(*a, **k):
            destino.write_bytes(b"")       # ffmpeg saiu 0 e não escreveu nada
            return _Proc()
        monkeypatch.setattr(ap.subprocess, "run", _run)
        assert ap.extract_wav("/x.mp4", str(destino)) is None

    def test_extracao_boa_devolve_o_caminho(self, monkeypatch, tmp_path):
        destino = tmp_path / "o.wav"

        class _Proc:
            returncode = 0
            stdout = b""
            stderr = b""

        def _run(*a, **k):
            destino.write_bytes(b"\0" * 64000)
            return _Proc()
        monkeypatch.setattr(ap.subprocess, "run", _run)
        assert ap.extract_wav("/x.mp4", str(destino)) == str(destino)

    def test_extracao_sem_ffmpeg_instalado(self, monkeypatch, tmp_path):
        def _boom(*a, **k):
            raise FileNotFoundError("ffmpeg")
        monkeypatch.setattr(ap.subprocess, "run", _boom)
        assert ap.extract_wav("/x.mp4", str(tmp_path / "o.wav")) is None


class TestDuracaoPeloTamanho:
    def test_byte_e_tempo(self, tmp_path):
        # PCM 16k mono s16le tem taxa constante: 32000 bytes por segundo.
        f = tmp_path / "a.wav"
        f.write_bytes(b"\0" * (44 + 32000 * 10))
        assert ap.wav_seconds(str(f)) == pytest.approx(10.0)

    def test_arquivo_ausente(self):
        assert ap.wav_seconds("/nao/existe.wav") is None

    def test_nunca_negativo(self, tmp_path):
        f = tmp_path / "a.wav"
        f.write_bytes(b"\0" * 10)            # menor que o cabeçalho RIFF
        assert ap.wav_seconds(str(f)) == 0.0


class TestNomeDoArquivo:
    def test_e_dotfile(self):
        # O diretório do job é servido como arquivo estático em /videos/<job>/,
        # e este é estado intermediário — mesma convenção do
        # .transcript_checkpoint.json e do .resume.json.
        assert ap.WAV_NAME.startswith(".")
        assert ap.WAV_NAME.endswith(".wav")
