"""Detector de pessoa atras de interface, com o YOLOv8 desligado (ADR-003).

O ADR-003 decidiu aplicar ao tracker o mesmo padrao do §1 para o driver de
navegador: *existe na arquitetura, nasce desligado por padrao e fora do caminho
automatico*. O motivo e de licenca. O YOLOv8 (Ultralytics) e **AGPL-3.0**, e o
fork o herdou do upstream sem decisao; com ele no caminho padrao, a virada para
SaaS vira reescrita em vez de mudanca de configuracao.

O que estava no codigo ate o bloco 1.7 era o oposto do que o ADR decidiu:

- `model = YOLO(...)` em **nivel de modulo**, entao todo job carregava (e, na
  primeira vez, baixava) os pesos -- mesmo os que nunca chamariam o detector.
  Como o `main.py` e subprocesso novo a cada job, isso era por video.
- O detector era o fallback **automatico** de toda cena em que o MediaPipe nao
  achasse rosto. Ligado por padrao, exatamente o que o ADR mandou nao fazer.

Agora:

- `FACE_TRACKER` escolhe a implementacao: `mediapipe` (padrao, Apache 2.0, sem
  fallback de pessoa) ou `yolo` (opt-in, AGPL-3.0).
- O import do `ultralytics` e a carga dos pesos acontecem **dentro** da
  implementacao do YOLO, na primeira chamada. Com o padrao, nada de AGPL e
  importado nem baixado.

**O que muda na pratica com o padrao:** numa cena em que o MediaPipe nao acha
rosto, a camera segura o ultimo alvo em vez de procurar um corpo. Perde-se
enquadramento em cena de rosto virado; em compensacao, o classificador ja manda
cena sem rosto (slide, gravacao de tela) para GENERAL, que nao usa este
caminho. Quem quiser a qualidade extra liga `FACE_TRACKER=yolo` e aceita a
AGPL.
"""
from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_modelo = None


def escolhido() -> str:
    """`mediapipe` (padrao) ou `yolo`."""
    valor = (os.environ.get("FACE_TRACKER") or "mediapipe").strip().lower()
    return "yolo" if valor in ("yolo", "yolov8", "ultralytics") else "mediapipe"


def yolo_ligado() -> bool:
    return escolhido() == "yolo"


def modelo_yolo():
    """Os pesos, carregados na primeira chamada e nunca antes.

    Carga preguicosa e com trava: o `main.py` renderiza clipes em paralelo, e
    duas threads entrando aqui ao mesmo tempo instanciariam dois modelos --
    e nenhum dos dois seria util antes de ambos terem baixado os pesos.
    """
    global _modelo
    if _modelo is None:
        with _lock:
            if _modelo is None:
                # Import aqui dentro, nao no topo: e este import que traz a
                # AGPL-3.0 para o processo, e com `FACE_TRACKER=mediapipe` ele
                # nunca acontece.
                from ultralytics import YOLO
                caminho = os.environ.get("YOLO_MODEL_PATH", "yolov8n.pt")
                print(f"🧠 Carregando YOLOv8 ({caminho}) — AGPL-3.0, ligado por FACE_TRACKER=yolo.")
                _modelo = YOLO(caminho)
    return _modelo


def reset() -> None:
    """Esquece o modelo carregado. Para teste."""
    global _modelo
    with _lock:
        _modelo = None
