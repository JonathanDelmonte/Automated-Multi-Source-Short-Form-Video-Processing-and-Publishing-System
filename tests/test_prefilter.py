"""Pré-filtro heurístico das janelas de pontuação (ADR-004, Fase 1 bloco 1.4).

O teste que mais importa aqui é o que garante que ele **não faz nada** quando
tudo cabe: é isso que torna seguro deixá-lo ligado. Um filtro que corta por
qualidade, com pesos inventados, descartaria o melhor momento de um vídeo de
10 minutos sem que ninguém notasse. Este corta por orçamento.
"""
from dataclasses import dataclass

import pytest

import prefilter as pf


@dataclass
class _Prov:
    id: str
    tokens_per_day: int | None


def _janelas(n, texto="palavra " * 150, passo=60.0, dur=90.0):
    return [{"id": f"w{i:03d}", "start": i * passo, "end": i * passo + dur,
             "text": texto} for i in range(n)]


def _palavras(total_s, por_segundo=2.5):
    n = int(total_s * por_segundo)
    passo = 1.0 / por_segundo
    return [{"w": "x", "s": i * passo, "e": i * passo + passo * 0.6} for i in range(n)]


def _estimador(texto):
    return max(1, len(texto) // 4)


class TestNaoAtuaQuandoCabe:
    def test_video_curto_passa_inteiro(self):
        janelas = _janelas(10)
        chain = [_Prov("groq", 100_000)]
        assert pf.apply(janelas, _palavras(600), chain=chain,
                        estimador=_estimador) == janelas

    def test_sem_provedor_com_teto_publicado_nao_corta(self):
        # Só Gemini (não publica teto estável) e Ollama (não tem): sem número
        # divulgado, cortar seria o achismo que o ADR-004 manda evitar.
        janelas = _janelas(500)
        chain = [_Prov("gemini", None), _Prov("ollama", None)]
        assert len(pf.apply(janelas, _palavras(30000), chain=chain,
                            estimador=_estimador)) == 500

    def test_sem_cascata_nenhuma_nao_corta(self):
        janelas = _janelas(500)
        assert len(pf.apply(janelas, _palavras(30000), chain=None,
                            estimador=_estimador)) == 500

    def test_lista_vazia(self):
        assert pf.apply([], [], chain=[_Prov("groq", 100_000)]) == []


class TestCortePorOrcamento:
    def test_live_de_4h_passa_a_caber(self):
        # O caso do ADR-004: 4h viram ~240 janelas e ~80k tokens só na
        # pontuação, contra os 100k/dia do Groq.
        janelas = _janelas(240)
        chain = [_Prov("gemini", None), _Prov("groq", 100_000)]
        mantidas = pf.apply(janelas, _palavras(14400), chain=chain,
                            estimador=_estimador, log=lambda *a: None)
        custo = sum(_estimador(j["text"]) for j in mantidas)
        assert len(mantidas) < 240
        assert custo <= 100_000 * pf.FRACAO_DO_ORCAMENTO

    def test_ordem_cronologica_e_preservada(self):
        # O passe de detalhe e o corte dependem de start crescente.
        janelas = _janelas(240)
        mantidas = pf.apply(janelas, _palavras(14400),
                            chain=[_Prov("groq", 100_000)],
                            estimador=_estimador, log=lambda *a: None)
        assert mantidas == sorted(mantidas, key=lambda j: j["start"])

    def test_orcamento_ja_gasto_aperta_mais(self, monkeypatch):
        import llm_cascade
        monkeypatch.setattr(llm_cascade, "usage",
                            lambda pid: {"tokens": 90_000, "calls": 0})
        janelas = _janelas(240)
        chain = [_Prov("groq", 100_000)]
        mantidas = pf.apply(janelas, _palavras(14400), chain=chain,
                            estimador=_estimador, log=lambda *a: None)
        assert len(mantidas) < 60, "com 90k já gastos hoje, sobra pouco"

    def test_nunca_desce_abaixo_do_minimo(self, monkeypatch):
        import llm_cascade
        monkeypatch.setattr(llm_cascade, "usage",
                            lambda pid: {"tokens": 99_999, "calls": 0})
        mantidas = pf.apply(_janelas(240), _palavras(14400),
                            chain=[_Prov("groq", 100_000)],
                            estimador=_estimador, log=lambda *a: None)
        assert len(mantidas) >= pf.MINIMO_DE_JANELAS, (
            "menos que isto não é um pré-filtro, é outro vídeo")

    def test_env_manda_em_tudo(self, monkeypatch):
        monkeypatch.setenv("PREFILTER_MAX_WINDOWS", "5")
        mantidas = pf.apply(_janelas(50), _palavras(3000), chain=None,
                            estimador=_estimador, log=lambda *a: None)
        assert len(mantidas) == 5

    def test_env_invalido_e_ignorado(self, monkeypatch):
        monkeypatch.setenv("PREFILTER_MAX_WINDOWS", "muitas")
        assert len(pf.apply(_janelas(10), _palavras(600), chain=None,
                            estimador=_estimador)) == 10


class TestOrcamentoDaCadeia:
    def test_pega_o_provedor_mais_apertado_nao_o_primeiro(self):
        # Pelo ADR-005 uma fonte longa começa no Gemini, que não publica teto.
        # Olhar só o primeiro deixaria a live de 4h passar sem filtro — o vídeo
        # que este módulo existe para viabilizar.
        chain = [_Prov("gemini", None), _Prov("groq", 100_000),
                 _Prov("cerebras", 1_000_000)]
        assert pf.tokens_disponiveis_hoje(chain) == 100_000

    def test_desconta_o_que_ja_foi_gasto_hoje(self, monkeypatch):
        import llm_cascade
        monkeypatch.setattr(llm_cascade, "usage",
                            lambda pid: {"tokens": 30_000, "calls": 0})
        assert pf.tokens_disponiveis_hoje([_Prov("groq", 100_000)]) == 70_000

    def test_nunca_negativo(self, monkeypatch):
        import llm_cascade
        monkeypatch.setattr(llm_cascade, "usage",
                            lambda pid: {"tokens": 500_000, "calls": 0})
        assert pf.tokens_disponiveis_hoje([_Prov("groq", 100_000)]) == 0


class TestSinais:
    def _janela(self, ini, fim):
        return {"id": "w", "start": ini, "end": fim, "text": "x"}

    def test_densidade(self):
        words = [{"w": "a", "s": i * 0.5, "e": i * 0.5 + 0.3} for i in range(20)]
        f = pf.features_for(self._janela(0, 10), words)
        assert f["words"] == 20
        assert f["words_per_second"] == pytest.approx(2.0)

    def test_silencio_prolongado(self):
        # Fala nos 2 primeiros segundos, depois 8s de nada.
        words = [{"w": "a", "s": 0.0, "e": 1.0}, {"w": "b", "s": 1.0, "e": 2.0}]
        f = pf.features_for(self._janela(0, 10), words)
        assert f["longest_silence"] == pytest.approx(8.0)
        assert f["silence_ratio"] == pytest.approx(0.8)

    def test_janela_muda_conta_turnos(self):
        words = [{"w": "a", "s": 0.0, "e": 0.5},
                 {"w": "b", "s": 3.0, "e": 3.5},     # pausa de 2,5s
                 {"w": "c", "s": 3.6, "e": 4.0}]     # respiração, não turno
        assert pf.features_for(self._janela(0, 10), words)["turns"] == 1

    def test_janela_vazia_nao_divide_por_zero(self):
        f = pf.features_for(self._janela(5, 5), [])
        assert f["words_per_second"] == 0.0 and f["silence_ratio"] == 1.0

    def test_so_conta_palavra_dentro_da_janela(self):
        words = [{"w": "fora", "s": 0.0, "e": 1.0},
                 {"w": "dentro", "s": 12.0, "e": 12.5}]
        assert pf.features_for(self._janela(10, 20), words)["words"] == 1


class TestRanking:
    def test_janela_densa_ganha_da_vazia(self):
        densa = {"id": "densa", "start": 0.0, "end": 10.0, "text": "t"}
        vazia = {"id": "vazia", "start": 10.0, "end": 20.0, "text": "t"}
        words = ([{"w": "x", "s": i * 0.4, "e": i * 0.4 + 0.3} for i in range(25)]
                 + [{"w": "y", "s": 15.0, "e": 15.2}])
        ordenadas = pf.rank([densa, vazia], words)
        assert ordenadas[0]["window"]["id"] == "densa"

    def test_normalizacao_e_relativa_ao_video(self):
        # Todas iguais -> ninguém é melhor que ninguém; nada de um limiar fixo
        # decidir que um podcast calmo inteiro é descartável.
        janelas = _janelas(5)
        words = _palavras(600)
        notas = {r["score"] for r in pf.rank(janelas, words)}
        assert len(notas) == 1

    def test_energia_entra_quando_ha_envelope(self):
        janelas = [{"id": "a", "start": 0.0, "end": 10.0, "text": "t"},
                   {"id": "b", "start": 10.0, "end": 20.0, "text": "t"}]
        words = _palavras(20)
        envelope = [100.0] * 10 + [5000.0] * 10
        com = pf.rank(janelas, words, envelope=envelope)
        assert com[0]["window"]["id"] == "b"
        assert com[0]["features"]["energy"] is not None

    def test_sem_envelope_a_energia_e_none(self):
        r = pf.rank(_janelas(3), _palavras(300))
        assert all(x["features"]["energy"] is None for x in r)


class TestEnvelope:
    def test_le_wav_16k_mono(self, tmp_path):
        import struct
        import wave
        caminho = tmp_path / "a.wav"
        with wave.open(str(caminho), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            # 1s baixo, 1s alto
            wf.writeframes(struct.pack("<16000h", *([100] * 16000)))
            wf.writeframes(struct.pack("<16000h", *([10000] * 16000)))
        env = pf.envelope_from_wav(str(caminho), window_s=1.0)
        assert len(env) == 2
        assert env[1] > env[0] * 10

    def test_arquivo_ausente_devolve_vazio(self):
        assert pf.envelope_from_wav("/nao/existe.wav") == []

    def test_estereo_devolve_vazio(self, tmp_path):
        import wave
        caminho = tmp_path / "s.wav"
        with wave.open(str(caminho), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\0" * 6400)
        # A energia é um sinal entre quatro: some sem derrubar nada.
        assert pf.envelope_from_wav(str(caminho)) == []

    def test_nao_e_wav(self, tmp_path):
        f = tmp_path / "x.wav"
        f.write_bytes(b"isto nao e um wav")
        assert pf.envelope_from_wav(str(f)) == []
