"""A classificacao de cenas numa passada so decide EXATAMENTE como a antiga.

A troca (22-set-2026) mexe so em COMO os quadros sao lidos -- uma passada com
`grab`/`retrieve` em vez de um seek por quadro. A garantia de que nada mais
mudou e esta: o algoritmo antigo, copiado aqui como referencia, e o novo
recebem os mesmos clipes sorteados e tem de dar a mesma lista de TRACK/GENERAL.
"""
import ast
import os
import random

import numpy as np
import pytest

import amostragem_cenas as am

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Quadro:
    """O minimo que as duas versoes usam de um quadro: `.mean()`."""

    def __init__(self, idx, brilho):
        self.idx = idx
        self.brilho = brilho

    def mean(self):
        return self.brilho


class CapFalso:
    """Faz o papel do `cv2.VideoCapture`, contando o que cada versao pede."""

    def __init__(self, quadros, quebra_em=None):
        self.quadros = quadros
        self.quebra_em = quebra_em      # grab() falha a partir deste quadro
        self.pos = 0
        self.seeks = 0
        self.grabs = 0
        self.retrieves = 0
        self._atual = None

    # o caminho antigo
    def set(self, _prop, idx):
        self.seeks += 1
        self.pos = int(idx)

    def read(self):
        if 0 <= self.pos < len(self.quadros):
            q = self.quadros[self.pos]
            self.pos += 1
            return True, q
        return False, None

    # o caminho novo
    def grab(self):
        if self.quebra_em is not None and self.pos >= self.quebra_em:
            return False
        if self.pos >= len(self.quadros):
            return False
        self._atual = self.quadros[self.pos]
        self.pos += 1
        self.grabs += 1
        return True

    def retrieve(self):
        self.retrieves += 1
        return (self._atual is not None), self._atual


def _referencia(cap, faixas, detectar):
    """O corpo antigo do `main.analyze_scenes_strategy`, sem o tqdm."""
    estrategias = []
    for s_f, e_f in faixas:
        margin = min(2, max(0, (e_f - s_f - 1) // 2))
        frames_to_check = sorted(set(
            int(round(f)) for f in np.linspace(s_f + margin, e_f - 1 - margin, 5)))
        face_counts = []
        for f_idx in frames_to_check:
            cap.set(None, f_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            if frame.mean() < 16:
                continue
            face_counts.append(len(detectar(frame)))
        avg = sum(face_counts) / len(face_counts) if face_counts else 0
        estrategias.append('GENERAL' if (avg > 1.2 or avg < 0.5) else 'TRACK')
    return estrategias


def _sorteia_clipe(rng):
    total = rng.randint(1, 900)
    quadros = []
    rostos = {}
    for i in range(total):
        # ~10% de quadros escuros, o resto claro; 0 a 3 rostos
        brilho = rng.choice([3, 10, 15]) if rng.random() < 0.1 else rng.randint(16, 250)
        quadros.append(Quadro(i, brilho))
        rostos[i] = rng.choices([0, 1, 2, 3], weights=[3, 6, 2, 1])[0]
    cortes = sorted(rng.sample(range(1, total), min(total - 1, rng.randint(0, 40)))) if total > 1 else []
    limites = [0] + cortes + [total]
    faixas = list(zip(limites[:-1], limites[1:]))
    return quadros, faixas, rostos


@pytest.mark.parametrize("semente", range(300))
def test_decide_igual_ao_algoritmo_antigo(semente):
    rng = random.Random(semente)
    quadros, faixas, rostos = _sorteia_clipe(rng)
    detectar = lambda q: [None] * rostos[q.idx]

    antigo = _referencia(CapFalso(quadros), faixas, detectar)
    novo = [am.estrategia(c) for c in
            am.contar_rostos_por_cena(CapFalso(quadros), faixas, detectar)]
    assert novo == antigo


def test_nao_faz_seek_e_le_cada_quadro_uma_vez():
    quadros = [Quadro(i, 100) for i in range(300)]
    faixas = [(0, 100), (100, 200), (200, 300)]
    cap = CapFalso(quadros)
    am.contar_rostos_por_cena(cap, faixas, lambda q: [None])
    assert cap.seeks == 0
    pedidos = {q for a, b in faixas for q in am.quadros_da_cena(a, b)}
    assert cap.retrieves == len(pedidos)
    # para no ultimo quadro pedido: o fim do clipe nao e decodificado a toa
    assert cap.grabs == max(pedidos) + 1


def test_quadros_escuros_nao_contam():
    quadros = [Quadro(i, 5) for i in range(50)]      # tudo preto
    contagens = am.contar_rostos_por_cena(CapFalso(quadros), [(0, 50)], lambda q: [None])
    assert contagens == [[]]
    assert am.estrategia(contagens[0]) == "GENERAL"


def test_leitura_que_quebra_no_meio_deixa_o_resto_em_general():
    """Um clipe que para de ler no meio: as cenas depois do ponto ficam sem
    amostra e saem GENERAL -- o mesmo que o antigo decidia quando o `read`
    falhava em todos os quadros de uma cena."""
    quadros = [Quadro(i, 100) for i in range(200)]
    cap = CapFalso(quadros, quebra_em=90)
    contagens = am.contar_rostos_por_cena(cap, [(0, 80), (100, 200)], lambda q: [None])
    assert contagens[0] and not contagens[1]
    assert [am.estrategia(c) for c in contagens] == ["TRACK", "GENERAL"]


def test_sem_cenas_nao_le_nada():
    cap = CapFalso([Quadro(0, 100)])
    assert am.contar_rostos_por_cena(cap, [], lambda q: []) == []
    assert cap.grabs == 0


def test_a_amostra_nunca_pede_quadro_negativo():
    for inicio, fim in [(0, 0), (0, 1), (5, 5), (3, 4)]:
        assert all(q >= 0 for q in am.quadros_da_cena(inicio, fim))


def test_o_main_nao_volta_a_buscar_quadro_por_seek():
    """O defeito era `cap.set(cv2.CAP_PROP_POS_FRAMES, n)` dentro do laco das
    cenas. O `main.py` nao importa no CI (pede torch), entao a garantia e
    sobre a arvore sintatica."""
    arvore = ast.parse(open(os.path.join(RAIZ, "main.py"), encoding="utf-8").read())
    funcao = next(n for n in ast.walk(arvore)
                  if isinstance(n, ast.FunctionDef) and n.name == "analyze_scenes_strategy")
    fonte = ast.unparse(funcao)
    assert "CAP_PROP_POS_FRAMES" not in fonte
    assert "amostragem_cenas.contar_rostos_por_cena" in fonte
