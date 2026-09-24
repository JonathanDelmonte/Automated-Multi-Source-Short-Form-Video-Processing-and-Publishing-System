"""O render se aquece durante a deteccao (`aquecimento.py`, 24-set-2026).

Duas coisas importam aqui, e as duas sao ordem: a placa so sobe DEPOIS do
download (a pre-carga do whisper que travou em 23-set subia o CUDA com o
yt-dlp fazendo fork), e nada do que falha no aquecimento chega ao job.

A outra metade -- o detector de cenas carregado uma vez so, mesmo com tres
cortes pedindo ao mesmo tempo -- e do `scene_detection`, testado com imitacoes
de scenedetect, torch e transnetv2_pytorch, que o CI nao instala.
"""
import contextlib
import importlib
import sys
import threading
import time
import types

import pytest

import aquecimento
import ffmpeg_utils


@pytest.fixture
def registro(monkeypatch):
    """Troca a sonda do NVENC e o detector de cenas por quem anota a ordem."""
    eventos = []
    monkeypatch.setenv("FFMPEG_ENCODER", "auto")
    monkeypatch.delenv("AQUECER_RENDER", raising=False)
    monkeypatch.setattr(ffmpeg_utils, "nvenc_available",
                        lambda: eventos.append("nvenc") or True)
    cenas = types.SimpleNamespace(aquecer=lambda: eventos.append("cenas") or True)
    monkeypatch.setitem(sys.modules, "scene_detection", cenas)
    return types.SimpleNamespace(eventos=eventos, cenas=cenas)


def test_a_placa_so_sobe_depois_do_download(registro, capsys):
    feito = aquecimento.aquecer(lambda: registro.eventos.append("download"))
    assert registro.eventos == ["download", "nvenc", "cenas"]
    assert feito == ["NVENC", "detector de cenas"]
    assert "Render aquecido" in capsys.readouterr().out


def test_com_x264_a_sonda_do_nvenc_nao_roda(registro, monkeypatch):
    monkeypatch.setenv("FFMPEG_ENCODER", "x264")
    assert aquecimento.aquecer() == ["detector de cenas"]
    assert registro.eventos == ["cenas"]


def test_x264_e_o_padrao_do_encoder(registro, monkeypatch):
    monkeypatch.delenv("FFMPEG_ENCODER")
    aquecimento.aquecer()
    assert "nvenc" not in registro.eventos


def test_download_que_falhou_nao_derruba_o_aquecimento(registro):
    def cai():
        raise SystemExit(1)                 # o `exit(1)` do caminho de erro
    assert aquecimento.aquecer(cai) == ["NVENC", "detector de cenas"]


def test_falha_na_sonda_vira_uma_linha_e_o_resto_segue(registro, monkeypatch, capsys):
    def explode():
        raise OSError("sem ffmpeg")
    monkeypatch.setattr(ffmpeg_utils, "nvenc_available", explode)
    assert aquecimento.aquecer() == ["detector de cenas"]
    out = capsys.readouterr().out
    assert "sonda do NVENC falhou" in out and "sem ffmpeg" in out


def test_falha_no_detector_vira_uma_linha(registro, capsys):
    def explode():
        raise RuntimeError("CUDA out of memory")
    registro.cenas.aquecer = explode
    assert aquecimento.aquecer() == ["NVENC"]
    assert "detector de cenas nao subiu" in capsys.readouterr().out


def test_sem_nada_aquecido_nao_anuncia(registro, monkeypatch, capsys):
    monkeypatch.setenv("FFMPEG_ENCODER", "x264")
    registro.cenas.aquecer = lambda: False           # SCENE_ENGINE=pyscenedetect
    assert aquecimento.aquecer() == []
    assert "Render aquecido" not in capsys.readouterr().out


def test_desligado_nao_abre_thread(registro, monkeypatch):
    monkeypatch.setenv("AQUECER_RENDER", "0")
    assert aquecimento.iniciar(lambda: registro.eventos.append("download")) is None
    assert registro.eventos == []


def test_iniciar_devolve_uma_thread_que_nao_prende_o_processo(registro):
    t = aquecimento.iniciar()
    assert t.daemon, "uma thread nao-daemon seguraria o processo depois do job"
    t.join(5)
    assert registro.eventos == ["nvenc", "cenas"]


# --- scene_detection: um modelo so --------------------------------------------

@pytest.fixture
def cenas_reais(monkeypatch):
    """O `scene_detection` de verdade, com o que o CI nao tem trocado por imitacoes."""
    sd = types.ModuleType("scenedetect")
    sd.open_video = sd.SceneManager = sd.FrameTimecode = object
    det = types.ModuleType("scenedetect.detectors")
    det.ContentDetector = object
    monkeypatch.setitem(sys.modules, "scenedetect", sd)
    monkeypatch.setitem(sys.modules, "scenedetect.detectors", det)

    criados, janelas = [], []

    class TransNetV2:
        def __init__(self, device="auto"):
            time.sleep(0.2)                  # a carga demora: os tres chegam juntos
            criados.append(self)
            self.device = "cuda"

        def eval(self):
            return self

        def predict_frames(self, quadros, quiet=False):
            janelas.append((quadros.shape, quadros.device, quiet,
                            sys.modules["scene_detection"]._TN2_LOCK.locked()))
            return None, None

    tn2 = types.ModuleType("transnetv2_pytorch")
    tn2.TransNetV2 = TransNetV2
    monkeypatch.setitem(sys.modules, "transnetv2_pytorch", tn2)
    torch = types.ModuleType("torch")
    torch.no_grad = contextlib.nullcontext
    torch.uint8 = "uint8"
    torch.zeros = lambda forma, dtype=None, device=None: types.SimpleNamespace(
        shape=forma, dtype=dtype, device=device)
    monkeypatch.setitem(sys.modules, "torch", torch)

    monkeypatch.delitem(sys.modules, "scene_detection", raising=False)
    modulo = importlib.import_module("scene_detection")
    yield types.SimpleNamespace(modulo=modulo, criados=criados, janelas=janelas)
    sys.modules.pop("scene_detection", None)


def test_tres_cortes_juntos_carregam_um_modelo_so(cenas_reais):
    sd = cenas_reais.modulo
    modelos = []
    threads = [threading.Thread(target=lambda: modelos.append(sd._get_tn2_model()))
               for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert len(cenas_reais.criados) == 1, "cada corte carregou o seu modelo"
    assert len({id(m) for m in modelos}) == 1


def test_aquecer_roda_uma_janela_do_tamanho_real_na_placa(cenas_reais, monkeypatch):
    monkeypatch.delenv("SCENE_ENGINE", raising=False)
    sd = cenas_reais.modulo
    assert sd.aquecer() is True
    # 50 quadros + 25 de enchimento de cada lado = uma janela de 100, a forma
    # que o uso real tem; na placa do modelo e sob a trava da inferencia.
    assert cenas_reais.janelas == [((50, 27, 48, 3), "cuda", True, True)]
    assert len(cenas_reais.criados) == 1


def test_o_motor_antigo_nao_aquece_nada(cenas_reais, monkeypatch):
    monkeypatch.setenv("SCENE_ENGINE", "pyscenedetect")
    assert cenas_reais.modulo.aquecer() is False
    assert cenas_reais.criados == [] and cenas_reais.janelas == []
