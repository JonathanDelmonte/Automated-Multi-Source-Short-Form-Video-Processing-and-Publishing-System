"""O diagnostico de lentidao: medicao + ambiente na mesma frase (16-set-2026).

O relatorio do bloco 5.3 sabe dizer QUAL estagio dominou e termina mandando
conferir a GPU a mao. Aqui a conferencia e feita, e e a JUNCAO que vale: "a
transcricao e 70% do tempo" nao e defeito nenhum num video muito falado, e "o
whisper esta em CPU" e apenas verdade numa maquina sem placa. Juntas, as duas
viram um proximo passo.

O que estes testes guardam, acima de tudo: **"nao deu para saber" nunca pode
sair como "sim"**. As sondagens devolvem `None` fora do container (o
`ctranslate2` nao importa, o ffmpeg pode nao existir), e um `else` que tratasse
`None` junto com `True` afirmaria que a placa esta em uso justamente quando
ninguem olhou.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diagnostico
import timings_report


def _ambiente(**troca):
    base = {"whisper_model": "small", "whisper_device": "cpu",
            "whisper_compute": "int8", "cuda_para_o_whisper": None,
            "ffmpeg_encoder": "x264", "nvenc_usavel": None,
            "clip_workers": 3, "teto_de_cortes": 15}
    base.update(troca)
    return base


def _medido(transcribe=0.0, render=0.0, parede=1000.0, substages=None,
            inflado=False):
    estagios = {}
    if transcribe:
        estagios["03_transcribe"] = {"wall_seconds": parede * transcribe}
    if render:
        estagios["05_06_render"] = {"wall_seconds": parede * render}
    if inflado:
        # A assinatura do dado antigo: sem `wall_seconds` e somando mais que a
        # parede do job.
        estagios = {"05_06_render": {"seconds": parede * 3}}
    t = {"facts": {"source_seconds": 600.0, "spoken_seconds": 500.0},
         "wall_seconds": parede, "totals": {"tokens": 0, "calls": 0},
         "stages": estagios}
    if substages:
        t["substages"] = {n: {"wall_seconds": parede * f}
                          for n, f in substages.items()}
    return timings_report.agregar([t])


def _diz(frases, *pedacos):
    """Sem caixa: a frase comeca com maiuscula quando abre a sentenca."""
    baixo = [f.lower() for f in frases]
    return any(all(p.lower() in f for p in pedacos) for f in baixo)


class TestTranscricao:

    def test_cpu_com_placa_disponivel_manda_ligar(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cpu", cuda_para_o_whisper=True),
            _medido(transcribe=0.7))
        assert _diz(f, "WHISPER_DEVICE=cuda")
        # E diz por que o `--build-arg GPU=1` nao basta: sao dois passos, e
        # confundi-los e o erro que o CLAUDE.md ja registra.
        assert _diz(f, "GPU=1")

    def test_cpu_sem_placa_manda_para_o_compose(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cpu", cuda_para_o_whisper=False),
            _medido(transcribe=0.7))
        assert _diz(f, "docker-compose.gpu.yml")
        assert not _diz(f, "WHISPER_DEVICE=cuda WHISPER_COMPUTE")

    def test_cuda_pedido_e_placa_ausente_e_a_queda_silenciosa(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cuda", cuda_para_o_whisper=False),
            _medido(transcribe=0.7))
        assert _diz(f, "silenciosa")

    def test_ja_na_placa_fala_de_modelo_e_nao_de_device(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cuda", cuda_para_o_whisper=True),
            _medido(transcribe=0.7))
        assert _diz(f, "large-v3-turbo")

    @pytest.mark.parametrize("device", ["cpu", "cuda"])
    def test_placa_desconhecida_nunca_vira_afirmacao(self, device):
        """O caso que importa: rodar o diagnostico FORA do container. Nem
        "ligue o cuda" (pode nao haver placa) nem "ja esta na placa" (ninguem
        olhou) -- so o pedido de rodar onde da para saber."""
        f = diagnostico.conclusoes(
            _ambiente(whisper_device=device, cuda_para_o_whisper=None),
            _medido(transcribe=0.7))
        assert _diz(f, "nao deu para saber")
        assert not _diz(f, "ja com a placa em uso")
        assert not _diz(f, "docker-compose.gpu.yml")

    def test_transcricao_pequena_nao_gera_frase(self):
        """Ambiente "errado" sem medicao que o acuse nao e conclusao: e
        exatamente o chute que este projeto recusa."""
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cpu", cuda_para_o_whisper=True),
            _medido(transcribe=0.1, render=0.1))
        assert not _diz(f, "WHISPER_DEVICE=cuda")


class TestRender:

    def test_x264_com_nvenc_disponivel_manda_ligar(self):
        f = diagnostico.conclusoes(
            _ambiente(ffmpeg_encoder="x264", nvenc_usavel=True),
            _medido(render=0.6))
        assert _diz(f, "FFMPEG_ENCODER=auto")
        # E diz que o custo do encoder e multiplicado pela cadeia do corte.
        assert _diz(f, "encodes do MESMO clipe")

    def test_x264_sem_nvenc_fala_do_numero_de_cortes(self):
        f = diagnostico.conclusoes(
            _ambiente(ffmpeg_encoder="x264", nvenc_usavel=False),
            _medido(render=0.6))
        assert _diz(f, "CLIP_TARGET_MAX")
        assert not _diz(f, "FFMPEG_ENCODER=auto")

    def test_nvenc_desconhecido_nao_manda_ligar_nada(self):
        f = diagnostico.conclusoes(
            _ambiente(ffmpeg_encoder="x264", nvenc_usavel=None),
            _medido(render=0.6))
        assert not _diz(f, "FFMPEG_ENCODER=auto")
        assert _diz(f, "DENTRO do container")

    def test_o_passe_caro_do_render_aparece(self):
        f = diagnostico.conclusoes(
            _ambiente(), _medido(render=0.6, substages={"06_legenda": 0.3}))
        assert _diz(f, "06_legenda", "30%")


class TestGuardas:

    def test_sem_job_nao_conclui_nada(self):
        f = diagnostico.conclusoes(_ambiente(), timings_report.agregar([]))
        assert _diz(f, "Nenhum job medido")
        assert len(f) == 1

    def test_dado_inflado_e_avisado_antes_de_tudo(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cpu", cuda_para_o_whisper=True),
            _medido(inflado=True))
        assert "16-set-2026" in f[0]
        assert "Rode UM job novo" in f[0]

    def test_nada_obvio_e_dito_como_nada_obvio(self):
        f = diagnostico.conclusoes(
            _ambiente(whisper_device="cuda", cuda_para_o_whisper=True,
                      ffmpeg_encoder="auto", nvenc_usavel=True),
            _medido(transcribe=0.2, render=0.2))
        assert _diz(f, "Nenhum estagio domina")


class TestLeituraDeDisco:

    def test_le_os_sidecars_do_mais_recente_para_o_mais_antigo(self, tmp_path):
        for i, nome in enumerate(("job-a", "job-b")):
            pasta = tmp_path / nome
            pasta.mkdir()
            alvo = pasta / "video.timings.json"
            alvo.write_text(json.dumps({"wall_seconds": float(i)}))
            os.utime(alvo, (1000 + i, 1000 + i))
        lidos = diagnostico.sidecars(str(tmp_path))
        assert [d["wall_seconds"] for d in lidos] == [1.0, 0.0]

    def test_sidecar_quebrado_nao_derruba_o_diagnostico(self, tmp_path):
        pasta = tmp_path / "job-a"
        pasta.mkdir()
        (pasta / "meio.timings.json").write_text('{"wall_seconds": 1')
        (pasta / "bom.timings.json").write_text('{"wall_seconds": 9}')
        assert diagnostico.sidecars(str(tmp_path)) == [{"wall_seconds": 9}]

    def test_pasta_inexistente_devolve_lista_vazia(self, tmp_path):
        assert diagnostico.sidecars(str(tmp_path / "nao-existe")) == []


class TestSondagens:
    """Nenhuma pode levantar: um diagnostico que quebra na maquina de quem
    esta com problema e pior do que nao existir."""

    def test_nenhuma_sondagem_levanta(self):
        amb = diagnostico.fatos_do_ambiente()
        assert set(amb) == {"whisper_model", "whisper_device", "whisper_compute",
                            "cuda_para_o_whisper", "ffmpeg_encoder",
                            "nvenc_usavel", "clip_workers", "teto_de_cortes"}

    def test_o_whisper_vem_do_subtitles_e_nao_de_uma_copia(self, monkeypatch):
        """Reescrever os defaults aqui criaria uma segunda verdade que o dia da
        mudanca separaria em silencio."""
        import subtitles
        monkeypatch.setenv("WHISPER_MODEL", "large-v3-turbo")
        assert diagnostico.whisper_configurado()["model_size"] == \
            subtitles.get_whisper_config()["model_size"] == "large-v3-turbo"

    def test_numero_torto_no_ambiente_nao_quebra(self, monkeypatch):
        monkeypatch.setenv("CLIP_WORKERS", "tres")
        assert diagnostico.fatos_do_ambiente()["clip_workers"] == 3

    def test_o_texto_sai_inteiro_sem_medicao_nenhuma(self):
        saida = diagnostico.texto(_ambiente(), timings_report.agregar([]))
        assert "AMBIENTE" in saida and "O QUE ISSO QUER DIZER" in saida
