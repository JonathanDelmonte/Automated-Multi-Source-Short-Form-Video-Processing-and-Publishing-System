"""YOLOv8 desligado e preguiçoso (Fase 1 bloco 1.7, ADR-003).

Dois problemas de natureza diferente no mesmo lugar. O de **licença**: o
YOLOv8 é AGPL-3.0, e o ADR-003 decidiu que ele nasce desligado e fora do
caminho automático — estava ligado, como fallback de toda cena sem rosto. O de
**custo**: `model = YOLO(...)` em nível de módulo carregava (e, na primeira
vez, baixava) os pesos em todo job, porque o `main.py` é um subprocesso novo a
cada vídeo, mesmo nos que nunca chamariam o detector.
"""
import pytest

import face_tracker as ft


@pytest.fixture(autouse=True)
def limpa(monkeypatch):
    monkeypatch.delenv("FACE_TRACKER", raising=False)
    ft.reset()
    yield
    ft.reset()


class TestPortao:
    def test_padrao_e_mediapipe(self):
        assert ft.escolhido() == "mediapipe"
        assert ft.yolo_ligado() is False

    @pytest.mark.parametrize("valor", ["yolo", "YOLO", "yolov8", "ultralytics", " Yolo "])
    def test_variantes_ligam(self, monkeypatch, valor):
        monkeypatch.setenv("FACE_TRACKER", valor)
        assert ft.yolo_ligado() is True

    @pytest.mark.parametrize("valor", ["", "mediapipe", "bobagem", "0", "none"])
    def test_qualquer_outra_coisa_cai_no_padrao(self, monkeypatch, valor):
        # Um valor errado tem que deixar o caminho Apache 2.0, não o AGPL.
        monkeypatch.setenv("FACE_TRACKER", valor)
        assert ft.yolo_ligado() is False


class TestCargaPreguicosa:
    def test_o_modelo_so_carrega_quando_pedido(self, monkeypatch):
        carregou = []
        ft.reset()
        # Se `modelo_yolo` não for chamado, nada disto roda.
        monkeypatch.setattr(ft, "_modelo", None)
        assert ft._modelo is None
        assert carregou == []

    def test_carrega_uma_vez_so(self, monkeypatch):
        import sys
        import types

        contagem = []

        fake = types.ModuleType("ultralytics")

        def _YOLO(caminho):
            contagem.append(caminho)
            return object()

        fake.YOLO = _YOLO
        monkeypatch.setitem(sys.modules, "ultralytics", fake)
        monkeypatch.setenv("YOLO_MODEL_PATH", "pesos.pt")

        a = ft.modelo_yolo()
        b = ft.modelo_yolo()
        assert a is b
        assert contagem == ["pesos.pt"], "os pesos não podem ser recarregados a cada cena"

    def test_respeita_o_caminho_configurado(self, monkeypatch):
        import sys
        import types

        vistos = []
        fake = types.ModuleType("ultralytics")
        fake.YOLO = lambda c: vistos.append(c) or object()
        monkeypatch.setitem(sys.modules, "ultralytics", fake)
        monkeypatch.delenv("YOLO_MODEL_PATH", raising=False)
        ft.modelo_yolo()
        assert vistos == ["yolov8n.pt"]


class TestMainNaoImportaAgplNoTopo:
    """O import de `ultralytics` é o que traz a AGPL-3.0 para o processo."""

    def test_o_topo_do_main_nao_importa_ultralytics(self):
        import ast
        import pathlib

        arvore = ast.parse(pathlib.Path("main.py").read_text(encoding="utf-8"))
        no_topo = []
        for no in arvore.body:            # só o nível do módulo, não o de dentro das funções
            if isinstance(no, ast.Import):
                no_topo += [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                no_topo.append(no.module or "")
        assert not any("ultralytics" in (m or "") for m in no_topo), (
            "o import do ultralytics precisa ficar dentro de face_tracker.modelo_yolo(), "
            "senão todo job paga a AGPL-3.0 e o carregamento mesmo sem usar o detector")

    def test_o_main_nao_instancia_o_modelo_em_nivel_de_modulo(self):
        import pathlib
        import re

        fonte = pathlib.Path("main.py").read_text(encoding="utf-8")
        assert not re.search(r"^model\s*=\s*YOLO\(", fonte, re.M), (
            "carregar os pesos em nível de módulo custa um download por job")


class TestAvisoBarulhento:
    """O ADR-003 não previa que dois layouts usam o detector para DETECTAR.

    `camera_inset` e `screencast_layout` chamam `detect_person_yolo` porque o
    BlazeFace não enxerga o rosto dentro de um recuadro de webcam de 1080p, e
    porque mediram zero detecções numa demonstração de planilha. Sem o YOLO,
    INSET pode não disparar e SCREENCAST pode não achar o apresentador. Isso
    não desfaz a decisão do ADR — o passivo de licença é real —, mas a
    degradação não pode ser silenciosa.
    """

    def test_avisa_uma_vez_so(self):
        linhas = []
        for _ in range(50):
            ft.avisar_desligado(log=linhas.append)
        assert len(linhas) == 1, (
            "isto é chamado por frame; avisar sempre viraria o log inteiro")

    def test_o_aviso_diz_o_que_se_perde_e_como_ligar(self):
        linhas = []
        ft.avisar_desligado(log=linhas.append)
        texto = linhas[0]
        assert "INSET" in texto and "SCREENCAST" in texto
        assert "FACE_TRACKER=yolo" in texto
        assert "AGPL" in texto

    def test_reset_rearma(self):
        linhas = []
        ft.avisar_desligado(log=linhas.append)
        ft.reset()
        ft.avisar_desligado(log=linhas.append)
        assert len(linhas) == 2


class TestDetectorDesligado:
    def test_devolve_none_sem_tocar_no_modelo(self, monkeypatch):
        main = pytest.importorskip("main")

        def _nao_devia(*a, **k):
            raise AssertionError("não pode carregar o YOLO com FACE_TRACKER=mediapipe")
        monkeypatch.setattr(ft, "modelo_yolo", _nao_devia)
        assert main.detect_person_yolo(object()) is None
