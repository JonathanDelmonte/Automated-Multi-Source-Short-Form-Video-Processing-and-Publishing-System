"""A midia gratis do video de IA (etapa 7.7, ADR-013).

A rede e imitada em `midia_ia._post`: o que se testa e o que decide -- o custo
em neurons, o pedido de cada modelo, a leitura da resposta, a queda para o
modelo de reserva, a cota do dia e as frases de cada erro.
"""
import base64
import io
import json
import wave
from datetime import datetime, timezone

import pytest

import midia_ia

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture(autouse=True)
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "conta")
    monkeypatch.setenv("GEMINI_API_KEY", "gem")
    for var in ("CLOUDFLARE_IMAGE_MODEL", "GEMINI_TTS_MODEL", "CLOUDFLARE_IMAGE_NEURONS_DAILY",
                "GEMINI_TTS_CALLS_DAILY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(midia_ia, "_SUMIRAM", set())
    monkeypatch.setattr(midia_ia.time, "sleep", lambda s: None)
    return tmp_path


class Rede:
    """Respostas em fila; guarda cada pedido."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def __call__(self, url, *, headers, json_body=None, files=None, timeout=180.0):
        self.pedidos.append({"url": url, "headers": headers, "json": json_body, "files": files})
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _imagem_ok(dados=PNG_1PX):
    return 200, "application/json", json.dumps(
        {"result": {"image": base64.b64encode(dados).decode()}, "success": True}).encode()


def _voz_ok(segundos=1.0, taxa=24000):
    pcm = b"\x00\x00" * int(taxa * segundos)
    return 200, "application/json", json.dumps({"candidates": [{"content": {"parts": [
        {"inlineData": {"mimeType": f"audio/L16;codec=pcm;rate={taxa}",
                        "data": base64.b64encode(pcm).decode()}}]}}]}).encode()


# --------------------------------------------------------------------------- #
# O que decide
# --------------------------------------------------------------------------- #

def test_blocos_e_custo():
    assert midia_ia.blocos(768, 1344) == 4
    assert midia_ia.blocos(1080, 1920) == 8
    assert midia_ia.custo_em_neurons(midia_ia.MODELO_IMAGEM_PADRAO, 768, 1344, 2) == \
        pytest.approx(26.05 * 4 + 5.37 * 2)
    assert midia_ia.custo_em_neurons(midia_ia.MODELO_IMAGEM_RESERVA) == \
        pytest.approx(4.8 * 4 + 9.6 * 4)
    assert midia_ia.custo_em_neurons("@cf/outro/modelo") == midia_ia.CUSTO_DESCONHECIDO


def test_so_o_flux_2_leva_referencia():
    assert midia_ia.aceita_referencia(midia_ia.MODELO_IMAGEM_PADRAO)
    assert not midia_ia.aceita_referencia(midia_ia.MODELO_IMAGEM_RESERVA)


def test_o_flux_2_vai_em_multipart_mesmo_sem_imagem():
    pedido = midia_ia.pedido_de_imagem(midia_ia.MODELO_IMAGEM_PADRAO, "um gato", semente=7)
    campos = dict((nome, valor) for nome, valor in pedido["files"])
    assert campos["prompt"] == (None, "um gato") and campos["seed"] == (None, "7")
    assert campos["width"] == (None, "768") and campos["height"] == (None, "1344")
    com_refs = midia_ia.pedido_de_imagem(midia_ia.MODELO_IMAGEM_PADRAO, "x",
                                         referencias=[b"a", b"b", b"c", b"d", b"e"])
    nomes = [nome for nome, _ in com_refs["files"]]
    assert nomes[-4:] == ["input_image_0", "input_image_1", "input_image_2", "input_image_3"]
    schnell = midia_ia.pedido_de_imagem(midia_ia.MODELO_IMAGEM_RESERVA, "x", semente=3)
    assert schnell == {"json_body": {"prompt": "x", "steps": 4, "seed": 3}}


def test_ler_imagem():
    assert midia_ia.ler_imagem(*_imagem_ok()[1:]) == PNG_1PX
    data_url = json.dumps({"result": {"image": "data:image/png;base64,"
                                      + base64.b64encode(PNG_1PX).decode()}}).encode()
    assert midia_ia.ler_imagem("application/json", data_url) == PNG_1PX
    assert midia_ia.ler_imagem("image/jpeg", b"\xff\xd8crua") == b"\xff\xd8crua"
    with pytest.raises(midia_ia.MidiaIndisponivel):
        midia_ia.ler_imagem("application/json", b'{"result": {}}')


@pytest.mark.parametrize("status,corpo,esperado", [
    (401, "Authentication error", "chave"),
    (400, "API key not valid. Please pass a valid API key.", "chave"),
    (429, "you have used up your daily free allocation of 10,000 neurons", "cota"),
    (404, "models/x is not found for API version v1beta", "modelo"),
    (400, "No such model @cf/black-forest-labs/flux-9", "modelo"),
    (503, "The model is overloaded", "capacidade"),
    (400, "prompt too long", "pedido"),
])
def test_classificar_erro(status, corpo, esperado):
    assert midia_ia.classificar_erro(status, corpo) == esperado


def test_a_referencia_vira_png_de_ate_512_sem_transparencia():
    from PIL import Image
    grande = Image.new("RGBA", (1600, 900), (10, 20, 30, 0))
    saida = io.BytesIO()
    grande.save(saida, format="PNG")
    ref = midia_ia.preparar_referencia(saida.getvalue())
    with Image.open(io.BytesIO(ref)) as img:
        assert img.format == "PNG" and img.mode == "RGB"
        assert max(img.size) == 512 and img.size == (512, 288)
        assert img.getpixel((0, 0)) == (255, 255, 255)


def test_a_conta_do_dia_vira_no_dia_de_cada_provedor():
    noite = datetime(2026, 9, 27, 23, 30, tzinfo=timezone.utc)
    midia_ia.registrar_neurons(100, noite)
    midia_ia.registrar_voz(noite)
    assert midia_ia.uso(noite)["neurons"] == 100 and midia_ia.uso(noite)["vozes"] == 1
    # Meia-noite e meia UTC: o Cloudflare zerou, o Google (Pacifico) ainda nao.
    depois = datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)
    assert midia_ia.uso(depois)["neurons"] == 0 and midia_ia.uso(depois)["vozes"] == 1


# --------------------------------------------------------------------------- #
# A imagem
# --------------------------------------------------------------------------- #

def test_a_imagem_sai_com_as_referencias_e_gasta_os_neurons(monkeypatch):
    rede = Rede(_imagem_ok())
    monkeypatch.setattr(midia_ia, "_post", rede)
    img = midia_ia.gerar_imagem("uma menina de vestido azul", referencias=[b"r1", b"r2"], semente=5)
    assert img.dados == PNG_1PX and img.extensao == ".png" and img.referencias == 2
    pedido = rede.pedidos[0]
    assert pedido["url"].endswith("/accounts/conta/ai/run/@cf/black-forest-labs/flux-2-klein-4b")
    assert pedido["headers"] == {"Authorization": "Bearer tok"}
    assert midia_ia.uso()["neurons"] == pytest.approx(img.neurons)
    assert midia_ia.uso()["imagens"] == 1


def test_o_modelo_que_sumiu_cai_para_o_schnell_sem_referencia(monkeypatch, capsys):
    rede = Rede((400, "application/json", b'{"errors":[{"message":"No such model"}]}'), _imagem_ok())
    monkeypatch.setattr(midia_ia, "_post", rede)
    img = midia_ia.gerar_imagem("x", referencias=[b"r1"])
    assert img.modelo == midia_ia.MODELO_IMAGEM_RESERVA and img.referencias == 0
    assert rede.pedidos[1]["json"]["prompt"] == "x"
    saida = capsys.readouterr().out
    assert "CLOUDFLARE_IMAGE_MODEL" in saida and "nao aceita referencia" in saida
    # O custo do que nao saiu volta: so o schnell fica na conta.
    assert midia_ia.uso()["neurons"] == pytest.approx(img.neurons)
    # E o modelo sumido nao e tentado de novo no processo.
    assert midia_ia.modelos_de_imagem() == [midia_ia.MODELO_IMAGEM_RESERVA]


def test_sem_cota_nao_chama_ninguem(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_IMAGE_NEURONS_DAILY", "100")
    rede = Rede()
    monkeypatch.setattr(midia_ia, "_post", rede)
    assert midia_ia.imagens_que_cabem() == 0
    with pytest.raises(midia_ia.CotaEsgotada, match="volta a meia-noite UTC"):
        midia_ia.gerar_imagem("x")
    assert rede.pedidos == []


@pytest.mark.parametrize("resposta,erro", [
    ((429, "application/json", b'{"errors":[{"message":"daily free allocation of neurons"}]}'),
     midia_ia.CotaEsgotada),
    ((401, "application/json", b'{"errors":[{"message":"Authentication error"}]}'),
     midia_ia.ChaveRecusada),
])
def test_cota_e_chave_do_provedor(monkeypatch, resposta, erro):
    monkeypatch.setattr(midia_ia, "_post", Rede(resposta))
    with pytest.raises(erro):
        midia_ia.gerar_imagem("x")


def test_sem_chave_diz_qual(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID")
    with pytest.raises(midia_ia.SemChave, match="CLOUDFLARE_ACCOUNT_ID"):
        midia_ia.gerar_imagem("x")
    assert midia_ia.disponivel() == {"imagem": False, "voz": True}


def test_fora_do_ar_tenta_de_novo_e_depois_o_reserva(monkeypatch):
    rede = Rede((503, "text/plain", b"busy"), (503, "text/plain", b"busy"),
                (503, "text/plain", b"busy"), _imagem_ok())
    monkeypatch.setattr(midia_ia, "_post", rede)
    img = midia_ia.gerar_imagem("x", tentativas=3)
    assert img.modelo == midia_ia.MODELO_IMAGEM_RESERVA and len(rede.pedidos) == 4


# --------------------------------------------------------------------------- #
# A voz
# --------------------------------------------------------------------------- #

def test_o_pedido_de_voz_leva_o_tom_antes_do_texto():
    pedido = midia_ia.pedido_de_voz("Era uma vez.", "Sulafat", "Conte como uma avó carinhosa")
    assert pedido["contents"][0]["parts"][0]["text"] == \
        "Conte como uma avó carinhosa:\n\nEra uma vez."
    config = pedido["generationConfig"]
    assert config["responseModalities"] == ["AUDIO"]
    assert config["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Sulafat"
    assert midia_ia.texto_para_falar("Oi.") == "Oi."


def test_a_voz_vira_wav_na_taxa_que_o_gemini_disse(monkeypatch):
    rede = Rede(_voz_ok(segundos=2.0, taxa=24000))
    monkeypatch.setattr(midia_ia, "_post", rede)
    audio = midia_ia.narrar("Era uma vez.", voz="Kore")
    with wave.open(io.BytesIO(audio.wav)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getsampwidth() == 2
    assert audio.segundos == pytest.approx(2.0)
    assert rede.pedidos[0]["headers"] == {"x-goog-api-key": "gem"}
    assert rede.pedidos[0]["url"].endswith(f"/models/{midia_ia.MODELO_VOZ_PADRAO}:generateContent")
    assert midia_ia.uso()["vozes"] == 1


def test_voz_fora_da_lista_vira_a_padrao(monkeypatch):
    rede = Rede(_voz_ok())
    monkeypatch.setattr(midia_ia, "_post", rede)
    audio = midia_ia.narrar("x", voz="Inventada")
    assert audio.voz == midia_ia.VOZ_PADRAO


def test_modelo_de_voz_que_sumiu_passa_ao_proximo(monkeypatch):
    rede = Rede((404, "application/json", b'{"error":{"message":"is not found"}}'), _voz_ok())
    monkeypatch.setattr(midia_ia, "_post", rede)
    audio = midia_ia.narrar("x")
    assert audio.modelo == midia_ia.MODELOS_VOZ_RESERVA[0]


def test_a_cota_da_voz_diz_quando_volta(monkeypatch):
    monkeypatch.setattr(midia_ia, "_post", Rede(
        (429, "application/json", b'{"error":{"status":"RESOURCE_EXHAUSTED"}}')))
    with pytest.raises(midia_ia.CotaEsgotada, match="meia-noite do Pacifico"):
        midia_ia.narrar("x")


def test_teto_proprio_de_vozes(monkeypatch):
    monkeypatch.setenv("GEMINI_TTS_CALLS_DAILY", "1")
    midia_ia.registrar_voz()
    rede = Rede()
    monkeypatch.setattr(midia_ia, "_post", rede)
    with pytest.raises(midia_ia.CotaEsgotada, match="GEMINI_TTS_CALLS_DAILY"):
        midia_ia.narrar("x")
    assert rede.pedidos == []


def test_as_trinta_vozes():
    assert len(midia_ia.VOZES) == 30 and len(set(midia_ia.NOMES_DAS_VOZES)) == 30
    assert midia_ia.VOZ_PADRAO in midia_ia.NOMES_DAS_VOZES
