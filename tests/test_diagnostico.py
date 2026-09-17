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
            "libs_de_cuda_na_imagem": None, "driver_no_container": None,
            "ffmpeg_encoder": "x264", "nvenc_usavel": None,
            "motivo_do_nvenc": None,
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
                            "cuda_para_o_whisper", "libs_de_cuda_na_imagem",
                            "driver_no_container", "ffmpeg_encoder",
                            "nvenc_usavel", "motivo_do_nvenc",
                            "clip_workers", "teto_de_cortes"}

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


class TestCaminhoDaGpu:
    """Onde a corrente da GPU arrebentou -- e nao apenas que ela arrebentou.

    As duas causas dao o MESMO `nao` em `placa p/ o whisper` e a correcao e
    outra: imagem sem as libs pede uma reconstrucao de 15 a 40 minutos, placa
    nao reservada pede um `up` de segundos. Sem separar, escolher entre as duas
    e cara ou coroa -- e a coroa custa 40 minutos da pessoa.
    """

    def test_imagem_sem_as_libs_manda_reconstruir(self):
        f = diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=False,
                      driver_no_container=False))
        assert _diz(f, "reconstruir-gpu.bat")
        assert _diz(f, "15 a 40 minutos")
        assert not _diz(f, "subir-gpu.bat")

    def test_libs_presentes_e_placa_nao_reservada_manda_subir(self):
        """O segundo dos dois passos que o CLAUDE.md ja avisava faltar: a
        imagem com CUDA nao faz o container enxergar a placa."""
        f = diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=True,
                      driver_no_container=False))
        assert _diz(f, "subir-gpu.bat")
        assert _diz(f, "segundos")
        assert not _diz(f, "reconstruir-gpu.bat")

    def test_reconstruir_vence_quando_faltam_as_libs_mesmo_com_driver(self):
        """Placa reservada numa imagem CPU: o `up` ja esta certo, o que falta e
        a imagem. Mandar subir de novo seria mandar repetir o que funcionou."""
        f = diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=False,
                      driver_no_container=True))
        assert _diz(f, "reconstruir-gpu.bat")
        assert not _diz(f, "subir-gpu.bat")

    def test_as_duas_metades_no_lugar_deixa_de_ser_configuracao(self):
        f = diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=True,
                      driver_no_container=True))
        assert _diz(f, "nao e configuracao")
        assert not _diz(f, ".bat")

    def test_placa_em_uso_nao_diz_nada(self):
        assert diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=True, libs_de_cuda_na_imagem=True,
                      driver_no_container=True)) == []

    def test_fora_do_container_nao_afirma_nada(self):
        """Sem o `LD_LIBRARY_PATH` do Dockerfile nao ha o que sondar, e "nao
        deu para saber" continua nao podendo sair como "nao"."""
        assert diagnostico.caminho_da_gpu(
            _ambiente(cuda_para_o_whisper=None,
                      libs_de_cuda_na_imagem=None)) == []

    def test_o_achado_aparece_mesmo_sem_job_medido(self):
        """A mudanca de comportamento que motivou isto: com zero jobs, a versao
        anterior respondia SO "rode um video e volte" -- mandando esperar uma
        medicao para descobrir o que ja estava na tela."""
        f = diagnostico.conclusoes(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=False,
                      driver_no_container=False),
            timings_report.agregar([]))
        assert _diz(f, "reconstruir-gpu.bat")
        assert _diz(f, "nenhum job medido")

    def test_os_dois_elos_aparecem_no_texto_so_quando_a_placa_falta(self):
        sem = diagnostico.texto(
            _ambiente(cuda_para_o_whisper=False, libs_de_cuda_na_imagem=False,
                      driver_no_container=False), timings_report.agregar([]))
        assert "libs de CUDA na imagem" in sem and "driver no container" in sem
        com = diagnostico.texto(
            _ambiente(cuda_para_o_whisper=True, libs_de_cuda_na_imagem=True,
                      driver_no_container=True), timings_report.agregar([]))
        assert "libs de CUDA na imagem" not in com


class TestSondagensDaGpu:

    def test_sem_ld_library_path_nao_afirma(self, monkeypatch):
        monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
        assert diagnostico.libs_de_cuda_na_imagem() is None

    def test_pasta_vazia_conta_como_ausente(self, monkeypatch, tmp_path):
        """O `pip install` das libs cria a pasta COM arquivos. Uma pasta vazia
        no caminho nao e uma imagem de GPU."""
        vazia = tmp_path / "nvidia" / "cudnn" / "lib"
        vazia.mkdir(parents=True)
        monkeypatch.setenv("LD_LIBRARY_PATH", str(vazia))
        assert diagnostico.libs_de_cuda_na_imagem() is False

    def test_pasta_com_lib_conta_como_presente(self, monkeypatch, tmp_path):
        cheia = tmp_path / "nvidia" / "cudnn" / "lib"
        cheia.mkdir(parents=True)
        (cheia / "libcudnn.so.9").write_text("")
        monkeypatch.setenv("LD_LIBRARY_PATH", str(cheia))
        assert diagnostico.libs_de_cuda_na_imagem() is True

    def test_caminho_alheio_a_cuda_e_ignorado(self, monkeypatch):
        """O `LD_LIBRARY_PATH` pode ter entradas que nada tem a ver com CUDA.

        Caminho LITERAL, e nao um `tmp_path`: o diretorio que o pytest cria e
        nomeado a partir do teste, entao a primeira versao disto -- chamada
        `test_caminho_sem_nvidia_e_ignorado` -- punha a palavra "nvidia" no
        proprio caminho que deveria ser ignorado, e falhava por isso."""
        monkeypatch.setenv("LD_LIBRARY_PATH", "/usr/lib/qualquer-outra-coisa")
        assert diagnostico.libs_de_cuda_na_imagem() is None

    def test_o_driver_e_falso_de_verdade_quando_nada_existe(self):
        """Ausencia do `nvidia-smi` E dos tres nos de dispositivo e ausencia
        observada, nao "nao deu para saber" -- sao os caminhos que o runtime da
        NVIDIA cria quando injeta o driver."""
        assert diagnostico.driver_no_container() in (True, False)


class TestNvencPedidoENaoAtendido:
    """`FFMPEG_ENCODER=auto` com o h264_nvenc recusando abrir.

    Nao e falha -- o `ffmpeg_utils` cai para libx264 sozinho e o job roda --,
    mas e uma expectativa que nao se cumpre em silencio, e o preco dela e todo
    encode da cadeia de um corte na CPU.
    """

    def _amb(self, **t):
        base = dict(_ambiente(), cuda_para_o_whisper=True,
                    libs_de_cuda_na_imagem=True, driver_no_container=True,
                    ffmpeg_encoder="auto", nvenc_usavel=False,
                    motivo_do_nvenc="cannot load libnvidia-encode")
        base.update(t)
        return base

    def test_cobra_o_encoder_que_foi_pedido(self):
        f = diagnostico.caminho_da_gpu(self._amb())
        assert _diz(f, "h264_nvenc nao abre")
        assert _diz(f, "nao quebra nada")

    def test_nao_cobra_quem_nunca_pediu_nvenc(self):
        """Com `FFMPEG_ENCODER=x264` o libx264 e a escolha, nao a queda."""
        assert diagnostico.caminho_da_gpu(self._amb(ffmpeg_encoder="x264")) == []

    def test_nao_cobra_quando_o_nvenc_abre(self):
        assert diagnostico.caminho_da_gpu(self._amb(nvenc_usavel=True)) == []

    def test_desconhecido_nao_vira_acusacao(self):
        """`None` e o diagnostico rodando onde nao ha ffmpeg."""
        assert diagnostico.caminho_da_gpu(self._amb(nvenc_usavel=None)) == []

    def test_o_motivo_sai_uma_vez_so(self):
        """Ele e detalhe do bloco de ambiente; a conclusao so aponta para ele.
        Repetir daria o mesmo paragrafo duas vezes na mesma tela."""
        amb = self._amb(motivo_do_nvenc="o container nao recebeu as libs")
        saida = diagnostico.texto(amb, timings_report.agregar([]))
        assert saida.count("o container nao recebeu as libs") == 1
        assert "porque:" in saida

    def test_a_sonda_do_motivo_usa_o_comando_do_ffmpeg_utils(self):
        """Uma definicao so: duas copias do comando divergem no dia em que uma
        delas mudar, e ai o motivo passa a explicar outra coisa."""
        import ffmpeg_utils
        cmd = ffmpeg_utils.comando_da_sonda_nvenc()
        assert cmd[0] == "ffmpeg" and "h264_nvenc" in cmd
        import inspect
        fonte = inspect.getsource(diagnostico.motivo_do_nvenc)
        assert "comando_da_sonda_nvenc()" in fonte

    @pytest.mark.parametrize("erro,esperado", [
        ("Cannot load libnvidia-encode.so.1", "libs de ENCODE"),
        ("No capable devices found", "nao achou placa"),
        ("OpenEncodeSessionEx failed: out of memory", "sem memoria"),
        ("Unknown encoder 'h264_nvenc'", "compilado sem"),
    ])
    def test_traduz_os_erros_conhecidos(self, erro, esperado, monkeypatch):
        import subprocess

        class _R:
            returncode = 1
            stderr = erro.encode()

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
        assert esperado.lower() in (diagnostico.motivo_do_nvenc() or "").lower()

    def test_erro_desconhecido_sai_cru_e_nao_inventado(self, monkeypatch):
        """Explicar um erro que ninguem viu e o oposto do que este modulo faz.
        Sai a ultima linha do ffmpeg, como ela e."""
        import subprocess

        class _R:
            returncode = 1
            stderr = b"linha de cima\nalgo que ninguem previu aqui\n"

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
        assert diagnostico.motivo_do_nvenc() == "algo que ninguem previu aqui"

    def test_sonda_bem_sucedida_nao_tem_motivo(self, monkeypatch):
        import subprocess

        class _R:
            returncode = 0
            stderr = b""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
        assert diagnostico.motivo_do_nvenc() is None
