"""Aquecer o render enquanto a deteccao espera o LLM (24-set-2026).

No log de 165 s, a primeira rodada de cortes levou 49 s e a segunda, 36 s. A
diferenca e custo que so se paga uma vez por processo, e caia inteiro no
primeiro corte -- o primeiro video que a pessoa ve aparecer:

- a sonda do NVENC (~2 s): um ffmpeg com placa antes do primeiro encode;
- a subida da placa para o detector de cenas (~5 s): o contexto de CUDA deste
  processo, os pesos do TransNetV2 e os kernels carregados na primeira
  inferencia. E os tres cortes da rodada carregavam cada um o seu modelo, ao
  mesmo tempo (ver `scene_detection._TN2_CARGA`).

Durante a deteccao (`04_detect`) este processo so espera a resposta do
Groq/Gemini: 12 a 22 s parado. O aquecimento usa esse tempo. Mesmo modelo,
mesmos parametros, mesmo resultado -- so muda a hora em que o custo e pago.

**A placa so sobe depois do download terminar.** A pre-carga do whisper que
travou em 23-set-2026 subia o CUDA enquanto o yt-dlp fazia fork. Aqui a
thread espera o download antes de tudo; dali em diante ela faz o que o
primeiro corte ja fazia -- numa thread que nao e a principal, com outras
threads abrindo ffmpeg --, so que mais cedo.

**Nunca levanta e nunca prende o job.** Uma falha vira uma linha de log e o
primeiro corte carrega como antes. Quem chegar no meio do aquecimento espera
por ele nas travas que ja existem (`ffmpeg_utils._probe_lock`,
`scene_detection._TN2_CARGA`) em vez de repetir o trabalho.

`AQUECER_RENDER=0` desliga.

Stdlib puro no topo: o `ffmpeg_utils` e o `scene_detection` (que traz cv2 e
scenedetect) so sao importados dentro da thread, entao o CI exercita a ordem
e as quedas sem nenhum dos dois.
"""
import os
import threading
import time


def ligado():
    return os.environ.get("AQUECER_RENDER", "1").strip() != "0"


def iniciar(esperar_download=None):
    """Comeca o aquecimento numa thread e a devolve; None se desligado.

    `esperar_download` e o `DownloadEmParalelo.esperar_terminar` quando o video
    ainda esta chegando, e None quando ele ja esta em disco.
    """
    if not ligado():
        return None
    t = threading.Thread(target=aquecer, args=(esperar_download,),
                         name="aquecer-render", daemon=True)
    t.start()
    return t


def aquecer(esperar_download=None):
    """O aquecimento, na thread de quem chamar. Devolve a lista do que aqueceu."""
    if esperar_download is not None:
        try:
            esperar_download()
        except BaseException:  # noqa: BLE001 - o erro do download e de quem espera o video
            pass
    t0 = time.monotonic()
    feito = []
    try:
        import ffmpeg_utils
        # Com `x264` a sonda nunca roda; aquecer seria abrir um processo com
        # placa para uma escolha que ninguem fez.
        if ffmpeg_utils.modo_do_encoder() in ("nvenc", "auto"):
            ffmpeg_utils.nvenc_available()
            feito.append("NVENC")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ Aquecimento: a sonda do NVENC falhou ({type(e).__name__}: {e}); "
              f"o primeiro corte sonda como antes.", flush=True)
    try:
        import scene_detection
        if scene_detection.aquecer():
            feito.append("detector de cenas")
    except Exception as e:  # noqa: BLE001
        print(f"   ⚠️ Aquecimento: o detector de cenas nao subiu ({type(e).__name__}: {e}); "
              f"o primeiro corte carrega como antes.", flush=True)
    if feito:
        print(f"   🔥 Render aquecido em {time.monotonic() - t0:.1f}s "
              f"({' + '.join(feito)}) enquanto a deteccao roda.", flush=True)
    return feito
