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

**O que muda na pratica com o padrao, e o ADR-003 nao previa isto.** O ADR fala
so de qualidade de enquadramento -- "o MediaPipe resolve rosto bem, e o YOLOv8
resolve melhor deteccao de pessoa quando o rosto esta virado". Mas o detector
nao e usado so para enquadrar: **dois layouts dependem dele para DETECTAR**, e
os dois documentam medicao no proprio codigo.

| Quem | O que perde sem o YOLO |
|---|---|
| TRACK | cena sem rosto segura o ultimo alvo em vez de procurar um corpo |
| **INSET** (`camera_inset`) | pode **nao disparar**: o rosto dentro de um recuadro de webcam de 1080p costuma ser pequeno demais para o BlazeFace, e o detector exige 3 amostras |
| **SCREENCAST** (`screencast_layout`) | pode **nao achar o apresentador**: medido zero deteccao do BlazeFace numa demonstracao de planilha em que a pessoa esta visivel |

Nao e motivo para desfazer a decisao do ADR-003 -- o passivo de licenca e real e
a decisao e do autor --, mas e motivo para a degradacao ser **barulhenta**. Por
isso `avisar_desligado()` imprime uma linha por job na primeira vez que alguem
pede o detector e ele esta off: perder um layout em silencio seria pior que
perde-lo.

Quem quiser os dois de volta liga `FACE_TRACKER=yolo` e aceita a AGPL-3.0.
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


_avisado = False


def avisar_desligado(log=print) -> None:
    """Uma linha por processo, na primeira vez que o detector e pedido e esta off.

    Uma por processo, e nao por chamada, porque isto e chamado por frame: o
    aviso viraria o log inteiro. E o `main.py` e um subprocesso novo a cada
    job, entao "uma por processo" e "uma por video".
    """
    global _avisado
    if _avisado:
        return
    _avisado = True
    log("🔌 Detector de pessoa desligado (FACE_TRACKER=mediapipe, ADR-003). "
        "Cena sem rosto detectavel segue com o enquadramento anterior, e os "
        "layouts INSET e SCREENCAST podem nao disparar. FACE_TRACKER=yolo liga "
        "(YOLOv8, AGPL-3.0).")


def reset() -> None:
    """Esquece o modelo carregado e o aviso. Para teste."""
    global _modelo, _avisado
    with _lock:
        _modelo = None
    _avisado = False
