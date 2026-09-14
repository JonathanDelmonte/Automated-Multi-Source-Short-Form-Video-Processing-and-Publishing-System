"""Gravar a live da Twitch em blocos (Fase 1, bloco 1.5).

O teste que carrega o desenho é o do **limite**: um bloco tem teto, porque um
job sem teto quebra quatro coisas de uma vez — a vaga no semáforo da fila, o
batimento do manifesto de resume, o drain de 840s de um deploy, e a barra do
painel dizendo "recebendo o vídeo" a tarde inteira. Fatiar é o que evita
precisar de um worker de longa duração, não um detalhe dele.
"""
import subprocess

import pytest

import sources
from sources import twitch_live as tl


class TestDuracaoDoBloco:
    def test_padrao(self, monkeypatch):
        monkeypatch.delenv("TWITCH_LIVE_BLOCK_MINUTES", raising=False)
        assert tl.block_seconds() == tl.PADRAO_MINUTOS * 60

    def test_env_manda(self, monkeypatch):
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "5")
        assert tl.block_seconds() == 300

    def test_teto_de_duas_horas(self, monkeypatch):
        # Acima disso o job deixa de caber no drain de um deploy (840s de
        # DRAIN_TIMEOUT_SECONDS), que é um dos motivos de o fatiamento existir.
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "999")
        assert tl.block_seconds() == 2 * 3600

    def test_piso_de_um_minuto(self, monkeypatch):
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "0")
        assert tl.block_seconds() == 60

    @pytest.mark.parametrize("lixo", ["", "  ", "quinze", "15min", "-"])
    def test_valor_ruim_cai_no_padrao(self, monkeypatch, lixo):
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", lixo)
        assert tl.block_seconds() == tl.PADRAO_MINUTOS * 60


class TestComandoDeGravacao:
    def test_t_depois_do_i(self):
        cmd = tl.record_cmd("https://x/s.m3u8", "/o/b.mp4", 900)
        # `-t` DEPOIS de `-i` limita a saída. Antes do `-i` ele seria um seek no
        # início do stream, e numa live isso não fecha o arquivo nunca.
        assert cmd.index("-t") > cmd.index("-i")
        assert cmd[cmd.index("-t") + 1] == "900"

    def test_nao_recodifica(self):
        cmd = tl.record_cmd("u", "/o/b.mp4", 60)
        assert cmd[cmd.index("-c") + 1] == "copy", (
            "recodificar 1080p60 ao vivo custaria mais CPU que o resto do pipeline")

    def test_destino_e_o_ultimo(self):
        assert tl.record_cmd("u", "/o/b.mp4", 60)[-1] == "/o/b.mp4"

    def test_segundos_viram_inteiro(self):
        assert tl.record_cmd("u", "d", 90.7)[tl.record_cmd("u", "d", 90.7).index("-t") + 1] == "90"


class TestResolverOStream:
    def test_canal_fora_do_ar_levanta_com_saida(self):
        with pytest.raises(tl.LiveOffline) as exc:
            tl.resolve_live("https://twitch.tv/x", ydl=lambda u: {"is_live": False})
        msg = str(exc.value)
        assert "nao esta transmitindo" in msg
        assert "/videos/" in msg, "precisa dizer o que fazer no lugar"

    def test_no_ar_devolve_titulo_e_url(self):
        info = {"is_live": True, "title": "Live de teste", "url": "https://x/s.m3u8"}
        got = tl.resolve_live("https://twitch.tv/x", ydl=lambda u: info)
        assert got == {"title": "Live de teste", "stream_url": "https://x/s.m3u8"}

    def test_sem_url_resolvivel_explica_sub_only(self):
        with pytest.raises(tl.LiveOffline) as exc:
            tl.resolve_live("https://twitch.tv/x",
                            ydl=lambda u: {"is_live": True, "formats": []})
        assert "TWITCH_COOKIES" in str(exc.value)

    def test_resposta_vazia_nao_explode(self):
        with pytest.raises(tl.LiveOffline):
            tl.resolve_live("https://twitch.tv/x", ydl=lambda u: None)


class TestEscolhaDoFormato:
    def test_url_no_topo_ganha(self):
        assert tl.pick_stream_url({"url": "top", "formats": [{"url": "f"}]}) == "top"

    def test_ultimo_formato_e_o_melhor(self):
        # Convenção do yt-dlp: a lista vem da pior para a melhor qualidade.
        assert tl.pick_stream_url({"formats": [{"url": "ruim"}, {"url": "bom"}]}) == "bom"

    def test_formato_sem_url_e_ignorado(self):
        assert tl.pick_stream_url({"formats": [{"url": "a"}, {"vcodec": "x"}]}) == "a"

    @pytest.mark.parametrize("info", [{}, None, {"formats": []}, "texto"])
    def test_sem_nada_devolve_none(self, info):
        assert tl.pick_stream_url(info) is None


class TestGravacao:
    class _Proc:
        def __init__(self, rc=0, err=b""):
            self.returncode = rc
            self.stdout = b""
            self.stderr = err

    def test_grava_e_devolve_o_caminho(self, monkeypatch, tmp_path):
        destino = tmp_path / "b.mp4"

        def _run(cmd, **k):
            destino.write_bytes(b"\0" * 1024)
            return self._Proc()
        monkeypatch.setattr(tl.subprocess, "run", _run)
        assert tl.record_block("u", str(destino), 60, log=lambda *a: None) == str(destino)

    def test_ffmpeg_com_erro_levanta(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tl.subprocess, "run",
                            lambda *a, **k: self._Proc(rc=1, err=b"Server returned 403"))
        with pytest.raises(RuntimeError, match="403"):
            tl.record_block("u", str(tmp_path / "b.mp4"), 60, log=lambda *a: None)

    def test_arquivo_vazio_levanta(self, monkeypatch, tmp_path):
        destino = tmp_path / "b.mp4"

        def _run(cmd, **k):
            destino.write_bytes(b"")
            return self._Proc()
        monkeypatch.setattr(tl.subprocess, "run", _run)
        with pytest.raises(RuntimeError, match="vazia"):
            tl.record_block("u", str(destino), 60, log=lambda *a: None)

    def test_travou_levanta_com_a_causa_provavel(self, monkeypatch, tmp_path):
        def _run(*a, **k):
            raise subprocess.TimeoutExpired("ffmpeg", 1)
        monkeypatch.setattr(tl.subprocess, "run", _run)
        with pytest.raises(RuntimeError, match="caido no meio"):
            tl.record_block("u", str(tmp_path / "b.mp4"), 60, log=lambda *a: None)

    def test_timeout_tem_margem_sobre_o_bloco(self, monkeypatch, tmp_path):
        # Sem margem, uma live com engasgo seria morta pelo próprio timeout no
        # segundo exato em que terminaria.
        visto = {}
        destino = tmp_path / "b.mp4"

        def _run(cmd, **k):
            visto.update(k)
            destino.write_bytes(b"\0")
            return self._Proc()
        monkeypatch.setattr(tl.subprocess, "run", _run)
        tl.record_block("u", str(destino), 900, log=lambda *a: None)
        assert visto["timeout"] == 900 + tl.MARGEM_SEGUNDOS


class TestAdapter:
    def test_live_passa_no_portao_agora(self):
        a = sources.resolve("https://www.twitch.tv/gaules")
        assert a.id == "twitch-live"
        a.assert_fetchable("https://www.twitch.tv/gaules")   # não levanta

    def test_lista_do_canal_continua_recusada(self):
        # Não é um vídeo: o yt-dlp a trataria como playlist e baixaria o canal.
        url = "https://www.twitch.tv/gaules/videos"
        with pytest.raises(sources.SourceNotReady):
            sources.resolve(url).assert_fetchable(url)

    def test_probe_avisa_da_duracao_do_bloco(self, monkeypatch):
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "7")
        url = "https://www.twitch.tv/gaules"
        notas = " ".join(sources.resolve(url).probe(url).notes)
        assert "7 min" in notas

    def test_probe_nao_toca_a_rede(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        url = "https://www.twitch.tv/gaules"
        assert sources.resolve(url).probe(url).is_live is True

    def test_fetch_grava_um_bloco(self, monkeypatch, tmp_path):
        import sys
        import types

        fake_main = types.ModuleType("main")
        fake_main.sanitize_filename = lambda n: n.replace(" ", "_")
        monkeypatch.setitem(sys.modules, "main", fake_main)
        monkeypatch.setattr(tl, "resolve_live",
                            lambda url, cookiefile=None: {"title": "Live X",
                                                          "stream_url": "u"})
        gravou = {}

        def _record(stream_url, dest, seconds, log=print):
            gravou.update(url=stream_url, dest=dest, seconds=seconds)
            return dest
        monkeypatch.setattr(tl, "record_block", _record)
        monkeypatch.setenv("TWITCH_LIVE_BLOCK_MINUTES", "3")

        a = sources.resolve("https://www.twitch.tv/gaules")
        got = a.fetch("https://www.twitch.tv/gaules", str(tmp_path))

        assert gravou["seconds"] == 180
        assert got.kind == "twitch-live"
        assert got.meta["live"] is True
        assert got.path.startswith(str(tmp_path))
        assert got.title == "Live_X_bloco"

    def test_fetch_usa_o_pote_de_cookies_da_twitch(self, monkeypatch, tmp_path):
        import sys
        import types

        fake_main = types.ModuleType("main")
        fake_main.sanitize_filename = lambda n: n
        monkeypatch.setitem(sys.modules, "main", fake_main)
        visto = {}

        def _resolve(url, cookiefile=None):
            visto["cookiefile"] = cookiefile
            return {"title": "t", "stream_url": "u"}
        monkeypatch.setattr(tl, "resolve_live", _resolve)
        monkeypatch.setattr(tl, "record_block", lambda *a, **k: a[1])

        sources.resolve("https://www.twitch.tv/x").fetch("https://www.twitch.tv/x",
                                                        str(tmp_path))
        assert visto["cookiefile"] == "/app/cookies-twitch.txt"
