"""A sobreposicao de GPU liga a placa para os DOIS custos (16-set-2026).

O `docker-compose.gpu.yml` existe para dizer "esta maquina tem placa NVIDIA".
Ate 16-set-2026 ele dizia isso so para a transcricao: punha `WHISPER_DEVICE=cuda`
e deixava `FFMPEG_ENCODER` no padrao `x264`, ou seja, todo encode em libx264 na
CPU. E nao e um encode por corte -- a cadeia e corte -> reenquadra -> [marca] ->
[gancho] -> legenda.

Sem teste, a linha sai num merge com o upstream e ninguem ve: a falha e o job
ficar lento, que e exatamente o modo de falhar que nao avisa.

Le como TEXTO e nao com pyyaml: o CI instala uma lista explicita de pacotes e o
pyyaml nao esta nela (ver .github/workflows/ci.yml). Um teste que so roda na
maquina de quem tem a dependencia certa nao guarda nada.
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO = os.path.join(RAIZ, "docker-compose.gpu.yml")


def _ambiente_do_backend() -> dict:
    """As chaves do bloco `environment:` do backend, sem pyyaml."""
    with open(CAMINHO, encoding="utf-8") as fh:
        linhas = fh.readlines()
    dentro = False
    achadas = {}
    for linha in linhas:
        if linha.strip().startswith("#"):
            continue
        if re.match(r"^\s*environment:\s*$", linha):
            dentro = True
            continue
        if dentro:
            m = re.match(r"^\s+([A-Z_][A-Z0-9_]*):\s*(\S.*?)\s*$", linha)
            if m:
                achadas[m.group(1)] = m.group(2)
            elif linha.strip() and not linha.startswith(" " * 6):
                dentro = False      # saiu do bloco
    return achadas


def test_a_sobreposicao_liga_a_placa_para_transcricao_e_encode():
    amb = _ambiente_do_backend()
    assert amb.get("WHISPER_DEVICE", "").startswith("${WHISPER_DEVICE:-cuda")
    assert "FFMPEG_ENCODER" in amb, (
        "o overlay de GPU nao liga o encoder: a transcricao vai para a placa e "
        "os 3 a 5 encodes por corte ficam em libx264 na CPU")


def test_o_encoder_e_auto_e_nao_nvenc():
    """`auto` sonda uma sessao h264_nvenc de verdade e cai para libx264 sozinho
    quando ela nao abre. Com `nvenc` o fallback tambem acontece, mas depois de
    uma linha de aviso por job -- numa maquina que so as vezes tem VRAM livre,
    isso e ruido permanente."""
    assert _ambiente_do_backend()["FFMPEG_ENCODER"] == "${FFMPEG_ENCODER:-auto}"


def test_tudo_continua_sobrescrivel_pelo_env():
    """A forma `${VAR:-padrao}` e o que deixa o `.env` mandar. Fixar o valor
    tiraria do autor a chance de voltar para a CPU sem editar o compose."""
    for chave, valor in _ambiente_do_backend().items():
        assert valor.startswith("${" + chave + ":-"), (
            f"{chave} deixou de ser sobrescrivel pelo .env")


def test_o_comentario_nao_manda_conferir_a_placa_pelo_torch():
    """Quem o faster-whisper usa e o ctranslate2. Um `True` do torch com a
    transcricao em CPU e a falha silenciosa disfarcada de conferencia feita."""
    with open(CAMINHO, encoding="utf-8") as fh:
        texto = fh.read()
    assert "diagnostico.py" in texto
    assert "print(torch.cuda.is_available())" not in texto
