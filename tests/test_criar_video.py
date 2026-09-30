"""A criacao de um video por IA como job (etapa 7.7), de ponta a ponta.

A rede das midias e imitada em `midia_ia._post` (a resposta como o Cloudflare
e o Gemini a descrevem), a IA de texto em `llm_cascade.run` e o whisper em
`transcribe_backends.transcribe_media`. O ffmpeg e de verdade: a montagem e o
que entrega o arquivo, e so ele diz se o grafo fecha.
"""
import base64
import io
import json
import os
import shutil
import wave

import pytest

import criar_video
import estilos
import job_metrics
import midia_ia

FALAS = ["Era uma vez a Lulu.", "Ela achou uma cenoura enorme.", "E dividiu com todo mundo."]


@pytest.fixture()
def ffmpeg(tmp_path_factory, monkeypatch):
    """Um `ffmpeg` no PATH: o do sistema, ou o do imageio-ffmpeg (CI)."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pytest.skip("sem ffmpeg nem imageio-ffmpeg")
    pasta = tmp_path_factory.mktemp("bin")
    destino = pasta / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        destino.symlink_to(exe)
    except OSError:
        shutil.copy(exe, destino)
    monkeypatch.setenv("PATH", f"{pasta}{os.pathsep}{os.environ.get('PATH', '')}")
    return "ffmpeg"


def _tem_libass():
    import subprocess
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True,
                           text=True, timeout=30)
    except Exception:
        return False
    return " ass " in r.stdout


def _png(cor):
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (192, 336), cor).save(saida, format="PNG")
    return saida.getvalue()


class Rede:
    """O Cloudflare e o Gemini de mentira: guarda cada pedido."""

    def __init__(self, segundos_de_voz=4.0):
        self.segundos = segundos_de_voz
        self.imagens = []
        self.vozes = []

    def __call__(self, url, *, headers, json_body=None, files=None, timeout=180.0):
        if "api.cloudflare.com" in url:
            self.imagens.append({"url": url, "files": files, "json": json_body})
            cor = (40 * len(self.imagens) % 255, 90, 160)
            return 200, "application/json", json.dumps(
                {"result": {"image": base64.b64encode(_png(cor)).decode()},
                 "success": True}).encode()
        self.vozes.append({"url": url, "json": json_body})
        pcm = b"\x00\x08" * int(24000 * self.segundos)
        return 200, "application/json", json.dumps({"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                            "data": base64.b64encode(pcm).decode()}}]}}]}).encode()


@pytest.fixture()
def ambiente(tmp_path, monkeypatch, ffmpeg):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "conta")
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    monkeypatch.setenv("FFMPEG_ENCODER", "x264")
    for var in ("CLOUDFLARE_IMAGE_MODEL", "GEMINI_TTS_MODEL", "CLOUDFLARE_IMAGE_NEURONS_DAILY",
                "GEMINI_TTS_CALLS_DAILY", "AUDIO_NORMALIZE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(midia_ia, "_SUMIRAM", set())
    monkeypatch.setattr(midia_ia.time, "sleep", lambda s: None)
    import ffmpeg_utils
    rapido = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "32"]
    monkeypatch.setattr(ffmpeg_utils, "video_encode_args", lambda tier=None: list(rapido))
    rede = Rede()
    monkeypatch.setattr(midia_ia, "_post", rede)

    roteiros = []

    def cascata(prompt, schema, *, call, duration_seconds=None, log=print):
        roteiros.append(prompt)
        return ({"titulo": "A Lulu e a cenoura", "descricao": "Uma historia de dividir.",
                 "hashtags": ["#historinha", "lulu"],
                 "cenas": [{"fala": FALAS[0], "imagem": "Lulu waves", "personagens": ["Lulu"]},
                           {"fala": FALAS[1], "imagem": "a huge carrot", "personagens": []},
                           {"fala": FALAS[2], "imagem": "Lulu shares the carrot",
                            "personagens": ["Lulu"]}]},
                {"provider": "groq", "input_tokens": 900, "output_tokens": 300})

    import llm_cascade
    monkeypatch.setattr(llm_cascade, "run", cascata)

    ouvidas = []

    def whisper(caminho):
        ouvidas.append(caminho)
        # O whisper erra o nome; a legenda tem de sair com o do roteiro.
        texto = " ".join(FALAS).replace("Lulu", "Lulú").split()
        passo = rede.segundos / len(texto)
        return {"language": "pt", "segments": [{"start": 0.0, "end": rede.segundos,
                                                "text": " ".join(texto), "words": [
            {"word": " " + w, "start": round(i * passo, 3),
             "end": round(i * passo + passo * 0.8, 3)} for i, w in enumerate(texto)]}]}

    import transcribe_backends
    monkeypatch.setattr(transcribe_backends, "transcribe_media", whisper)
    return {"rede": rede, "roteiros": roteiros, "ouvidas": ouvidas, "raiz": tmp_path}


def _pedido(pasta, legenda="karaoke_fill", com_referencia=True):
    doc = estilos.normalizar({
        "publico": "criancas", "cenas": 3, "duracao_s": 20,
        "visual": {"preset": "livro-infantil"},
        "legenda": {"preset": legenda},
        "personagens": [{"id": "0a1b2c3d", "nome": "Lulu", "descricao": "coelhinha branca"}]})
    os.makedirs(pasta / "referencias", exist_ok=True)
    referencias = {}
    if com_referencia:
        (pasta / "referencias" / "0a1b2c3d.png").write_bytes(_png((250, 250, 250)))
        referencias = {"0a1b2c3d": "referencias/0a1b2c3d.png"}
    (pasta / criar_video.ARQUIVO_DO_PEDIDO).write_text(json.dumps({
        "estilo": doc, "estilo_id": "e" * 8, "canal_id": None, "ideia": "a Lulu aprende a dividir",
        "idioma": "pt-BR", "referencias": referencias, "ja_feitos": ["A Lulu e a chuva"]}),
        encoding="utf-8")
    return doc


def _duracao(caminho):
    import subprocess
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", caminho], capture_output=True, text=True)
    import re
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def test_cria_o_video_de_ponta_a_ponta(ambiente, tmp_path, capsys):
    if not _tem_libass():
        pytest.skip("este ffmpeg nao tem libass")
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta)
    job_metrics.reset(str(pasta), criar_video.BASE)

    entregue = criar_video.criar(str(pasta))

    saida = capsys.readouterr().out
    assert entregue.startswith("subtitled_") and entregue.endswith("_criacao_clip_1.mp4")
    assert f"CLIP_READY 0 {entregue}" in saida
    assert (pasta / "criacao_clip_1.mp4").is_file() and (pasta / entregue).is_file()
    assert _duracao(str(pasta / entregue)) == pytest.approx(4.0, abs=0.2)
    # O roteiro pediu o estilo, a ideia e o que ja foi feito.
    prompt = ambiente["roteiros"][0]
    assert "a Lulu aprende a dividir" in prompt and "A Lulu e a chuva" in prompt
    # A referencia so vai nas cenas em que a Lulu aparece.
    rede = ambiente["rede"]
    com_ref = [any(nome.startswith("input_image_") for nome, _ in p["files"])
               for p in rede.imagens]
    assert com_ref == [True, False, True]
    assert "image 0 shows Lulu" in dict(rede.imagens[0]["files"])["prompt"][1]
    # A narracao e o roteiro inteiro, numa chamada so.
    assert len(rede.vozes) == 1
    falado = rede.vozes[0]["json"]["contents"][0]["parts"][0]["text"]
    assert all(f in falado for f in FALAS)
    # O metadata guarda a transcricao do ROTEIRO (o nome certo), um segmento por cena.
    meta = json.loads((pasta / "criacao_metadata.json").read_text(encoding="utf-8"))
    curto = meta["shorts"][0]
    assert curto["video_title_for_youtube_short"] == "A Lulu e a cenoura"
    assert curto["end"] == pytest.approx(4.0, abs=0.01)
    assert "#historinha" in curto["video_description_for_tiktok"]
    segmentos = meta["transcript"]["segments"]
    assert [s["text"] for s in segmentos] == FALAS
    assert "Lulu." in [w["word"].strip() for w in segmentos[0]["words"]]
    ass = (pasta / criar_video.ARQUIVO_DA_LEGENDA).read_text(encoding="utf-8").upper()
    assert "LULU" in ass and "LULÚ" not in ass         # o karaoke_fill e em maiusculas
    # O LLM e as imagens entram na conta do job.
    fatos = job_metrics.snapshot()
    assert fatos["facts"]["neurons"] > 0 and fatos["facts"]["spoken_seconds"] == 4.0


def test_o_metadata_vem_por_ultimo(ambiente, tmp_path, monkeypatch):
    """Para o app, metadata presente e job terminado: ele nao pode existir com a
    montagem falhando."""
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta, legenda="nenhuma")
    import montagem

    def quebra(*a, **k):
        raise RuntimeError("a montagem falhou: teste")

    monkeypatch.setattr(montagem, "montar", quebra)
    with pytest.raises(RuntimeError):
        criar_video.criar(str(pasta))
    assert not (pasta / "criacao_metadata.json").exists()


def test_a_retomada_nao_refaz_o_que_ja_esta_na_pasta(ambiente, tmp_path):
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta, legenda="nenhuma")
    criar_video.criar(str(pasta))
    rede = ambiente["rede"]
    assert (len(ambiente["roteiros"]), len(rede.imagens), len(rede.vozes)) == (1, 3, 1)

    # O motor caiu depois da segunda imagem: a terceira, o video e o metadata faltam.
    (pasta / "cena_03.png").unlink()
    (pasta / "criacao_clip_1.mp4").unlink()
    (pasta / "criacao_metadata.json").unlink()
    criar_video.criar(str(pasta))
    assert (len(ambiente["roteiros"]), len(rede.imagens), len(rede.vozes)) == (1, 4, 1)
    assert len(ambiente["ouvidas"]) == 1        # a transcricao tambem ficou na pasta
    assert (pasta / "criacao_metadata.json").is_file()


def test_sem_cota_para_as_imagens_nao_gasta_nenhuma(ambiente, tmp_path, monkeypatch):
    """Metade das imagens hoje e o resto amanha daria um video pela metade
    parado na fila: para antes de gastar."""
    monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "250")      # ~2 imagens
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta)
    with pytest.raises(criar_video.CriacaoFalhou, match="so da para 2 das 3"):
        criar_video.criar(str(pasta))
    assert ambiente["rede"].imagens == []
    assert (pasta / criar_video.ARQUIVO_DO_ROTEIRO).is_file()      # o roteiro fica


def test_sem_transcricao_o_video_sai_sem_legenda(ambiente, tmp_path, monkeypatch, capsys):
    import transcribe_backends

    def falha(caminho):
        raise RuntimeError("sem placa")

    monkeypatch.setattr(transcribe_backends, "transcribe_media", falha)
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta)
    entregue = criar_video.criar(str(pasta))
    saida = capsys.readouterr().out
    assert entregue == "criacao_clip_1.mp4"
    assert "nao foi transcrita" in saida and "sai sem legenda" in saida
    assert not any(n.startswith("subtitled_") for n in os.listdir(pasta))


def test_sem_a_referencia_o_personagem_vai_pela_descricao(ambiente, tmp_path):
    pasta = tmp_path / "job"
    pasta.mkdir()
    _pedido(pasta, legenda="nenhuma", com_referencia=False)
    criar_video.criar(str(pasta))
    assert not any(any(n.startswith("input_image_") for n, _ in p["files"])
                   for p in ambiente["rede"].imagens)


def test_main_diz_o_erro_e_sai_com_1(ambiente, tmp_path, capsys):
    pasta = tmp_path / "vazia"
    pasta.mkdir()
    assert criar_video.main(["--pasta", str(pasta)]) == 1
    assert "❌ O pedido da criacao" in capsys.readouterr().out


def test_os_estagios_sao_os_da_barra():
    import ast
    import pathlib
    arvore = ast.parse(pathlib.Path(criar_video.__file__).read_text(encoding="utf-8"))
    usados = [n.args[0].value for n in ast.walk(arvore)
              if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "stage"
              and n.args and isinstance(n.args[0], ast.Constant)]
    assert tuple(usados) == criar_video.ESTAGIOS
