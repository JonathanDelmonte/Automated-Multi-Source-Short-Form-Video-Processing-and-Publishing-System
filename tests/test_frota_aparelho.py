"""Um aparelho da frota (etapa 7.9, ADR-016): as leituras do que o Android
responde, e as acoes pelo servidor do adb falso."""
import base64
import re
import shlex

import pytest

import frota_aparelho as fa
from adb_cliente import Cliente
from adb_falso import AparelhoFalso, ServidorFalso

ESTADO_ANDROID_13 = """@@props
samsung
SM-A145M
13
33
R9TW12345AB
@@bateria
Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  status: 2
  level: 87
@@energia
  mWakefulness=Awake
  Display Power: state=ON
@@bloqueio
    mKeyguardShowing=false
    mDreamingLockscreen=false
@@espaco
/dev/fuse        115453952 34567890 80886062  30% /storage/emulated
@@pacotes
package:com.android.chrome
package:com.instagram.android
package:com.instagram.android.lite
package:com.zhiliaoapp.musically
package:com.android.adbkeyboard
@@versoes
com.instagram.android     versionName=312.0.0.39.120
com.zhiliaoapp.musically     versionName=36.5.4
com.android.adbkeyboard     versionName=2.4-dev
@@teclado
com.samsung.android.honeyboard/.service.HoneyBoardService
@@tamanho
Physical size: 1080x2408
@@fim
"""


def test_ler_estado():
    e = fa.ler_estado(ESTADO_ANDROID_13)
    assert (e["fabricante"], e["modelo"], e["android"], e["sdk"]) == ("samsung", "SM-A145M", "13", 33)
    assert e["numero_de_serie"] == "R9TW12345AB"
    assert e["bateria"] == {"nivel": 87, "carregando": True, "na_tomada": True}
    assert e["tela_ligada"] is True and e["bloqueado"] is False
    assert e["espaco_livre_mb"] == 80886062 // 1024
    assert e["apps"] == {
        "instagram": {"pacote": "com.instagram.android", "versao": "312.0.0.39.120"},
        "tiktok": {"pacote": "com.zhiliaoapp.musically", "versao": "36.5.4"},
    }
    assert e["adbkeyboard"] is True
    assert e["teclado"].startswith("com.samsung")
    assert e["tela"] == (1080, 2408)


def test_estado_sem_nada_e_nao_sei_nunca_um_chute():
    e = fa.ler_estado("@@props\n@@fim\n")
    assert e["bloqueado"] is None and e["tela_ligada"] is None
    assert e["apps"] == {} and e["adbkeyboard"] is False and e["tela"] is None


@pytest.mark.parametrize("texto,esperado", [
    ("    mShowingLockscreen=true mShowingDream=false", True),   # Android 9
    ("  KeyguardController:\n    mKeyguardShowing=true", True),  # Android 12+
    ("    mKeyguardShowing=false\n    mDreamingLockscreen=false", False),
    ("    isKeyguardShowing=false", False),
    ("", None),
])
def test_bloqueio(texto, esperado):
    assert fa.ler_bloqueio(texto) is esperado


def test_tamanho_usa_o_override():
    assert fa.ler_tamanho("Physical size: 1440x3200\nOverride size: 1080x2400") == (1080, 2400)


INSTAGRAM = """priority=0 preferredOrder=0 match=0x608000 specificIndex=-1 isDefault=false
com.instagram.android/com.instagram.share.handleractivity.ShareHandlerActivity
priority=0 preferredOrder=0 match=0x608000 specificIndex=-1 isDefault=false
com.instagram.android/com.instagram.share.handleractivity.ClipsShareHandlerActivity
priority=0 preferredOrder=0 match=0x608000 specificIndex=-1 isDefault=false
com.instagram.android/com.instagram.share.handleractivity.StoryShareHandlerActivity
priority=0 preferredOrder=0 match=0x608000 specificIndex=-1 isDefault=false
com.instagram.android/com.instagram.direct.share.handler.DirectShareHandlerActivity
"""


def test_tela_de_compartilhar_do_instagram_e_a_dos_reels():
    telas = fa.ler_telas_de_compartilhar(INSTAGRAM, "com.instagram.android")
    assert len(telas) == 4
    assert fa.escolher_tela(telas, "instagram").endswith("ClipsShareHandlerActivity")


def test_sem_a_dos_reels_sobra_o_feed_e_nunca_stories_ou_direct():
    telas = [t for t in fa.ler_telas_de_compartilhar(INSTAGRAM, "com.instagram.android")
             if "Clips" not in t]
    assert fa.escolher_tela(telas, "instagram").endswith(".ShareHandlerActivity")
    so_story = [t for t in telas if "Story" in t or "Direct" in t]
    assert fa.escolher_tela(so_story, "instagram") is None


def test_mais_de_uma_tela_possivel_o_automatico_nao_chuta():
    telas = ["com.ss.android.ugc.aweme/.share.A", "com.ss.android.ugc.aweme/.share.B"]
    assert fa.escolher_tela(telas, "douyin") is None
    assert fa.escolher_tela(telas[:1], "douyin") == telas[0]
    assert fa.escolher_tela([], "tiktok") is None


@pytest.mark.parametrize("texto,esperado", [
    ("Row: 0 _id=1234\n", "1234"),
    ("No result found.\n", None),
])
def test_id_da_midia(texto, esperado):
    assert fa.ler_id_da_midia(texto) == esperado


@pytest.mark.parametrize("texto", [
    "  mResumedActivity: ActivityRecord{8a1b2c u0 com.instagram.android/.activity.MainTabActivity t123}",
    "  topResumedActivity=ActivityRecord{8a1b2c u0 com.instagram.android/com.x.Y t99}",
])
def test_app_em_frente(texto):
    assert fa.ler_app_em_frente(texto) == "com.instagram.android"


def test_pedacos_nao_partem_caractere_e_voltam_iguais():
    texto = "Corte incrível 🎬 " * 120 + "#fim"
    pedacos = fa.pedacos_do_texto(texto, maximo=100)
    assert len(pedacos) > 1
    for p in pedacos:
        assert len(base64.b64decode(p)) <= 100
    assert "".join(base64.b64decode(p).decode("utf-8") for p in pedacos) == texto


def test_nome_no_aparelho_so_tem_o_que_o_shell_aceita():
    nome = fa.nome_no_aparelho("Pub 9f3c'; rm -rf /", ".mp4")
    assert re.fullmatch(r"vc-[a-z0-9-]+\.mp4", nome)


# --------------------------------------------------------------------------- #
# Pelo servidor do adb falso
# --------------------------------------------------------------------------- #

@pytest.fixture
def ambiente():
    with ServidorFalso() as s:
        celular = s.acrescentar(AparelhoFalso("R9TW12345AB"))
        yield s, celular, fa.Aparelho("R9TW12345AB", Cliente("127.0.0.1", s.porta, timeout=5))


def test_estado_pelo_adb(ambiente):
    _s, celular, aparelho = ambiente
    celular.responder(r'^echo "@@props"', ESTADO_ANDROID_13)
    assert aparelho.estado()["apps"]["instagram"]["versao"] == "312.0.0.39.120"


def test_por_na_galeria_e_abrir_no_app(ambiente, tmp_path):
    _s, celular, aparelho = ambiente
    video = tmp_path / "corte.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 1000)
    celular.responder(r"^content query .*vc-pub-1\.mp4", "Row: 0 _id=4321\n")
    uri = aparelho.por_na_galeria(str(video), "vc-pub-1.mp4", espera_s=2)
    assert uri == "content://media/external/video/media/4321"
    # O `sh` do aparelho le o filtro como UM argumento, com as aspas do SQL.
    consulta = shlex.split(next(c for c in celular.executados if c.startswith("content query")))
    assert consulta[consulta.index("--where") + 1] == "_display_name='vc-pub-1.mp4'"
    assert celular.arquivos["/sdcard/Movies/Virtu Clips/vc-pub-1.mp4"] == video.read_bytes()
    assert any("MEDIA_SCANNER_SCAN_FILE" in c and "Virtu%20Clips" in c for c in celular.executados)

    aparelho.abrir_no_app(uri, "com.instagram.android",
                          "com.instagram.android/com.instagram.share.handleractivity.ClipsShareHandlerActivity")
    abrir = celular.executados[-1]
    assert "-a android.intent.action.SEND -t video/mp4" in abrir
    assert f"--eu android.intent.extra.STREAM '{uri}'" in abrir
    assert "--grant-read-uri-permission" in abrir and "--activity-clear-task" in abrir
    assert "-n 'com.instagram.android/" in abrir
    # O app nunca e parado: um envio de antes pode estar subindo.
    assert not any("force-stop" in c for c in celular.executados)


def test_galeria_que_nao_mostra_o_video_e_erro_claro(ambiente, tmp_path):
    _s, _celular, aparelho = ambiente
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")
    with pytest.raises(fa.AparelhoErro, match="galeria"):
        aparelho.por_na_galeria(str(video), "vc-a.mp4", espera_s=0.1)


def test_digitar_vai_em_base64_pelo_adbkeyboard(ambiente):
    _s, celular, aparelho = ambiente
    texto = "Legenda com acento é emoji 🎬"
    aparelho.digitar(texto)
    enviados = [re.search(r"--es msg '([^']+)'", c).group(1)
                for c in celular.executados if "ADB_INPUT_B64" in c]
    assert "".join(base64.b64decode(p).decode("utf-8") for p in enviados) == texto


def test_o_teclado_de_antes_volta_mesmo_com_erro(ambiente):
    _s, celular, aparelho = ambiente
    celular.responder(r"^settings get secure default_input_method", "com.google.android.inputmethod.latin/x\n")
    with pytest.raises(RuntimeError):
        with fa.com_adbkeyboard(aparelho):
            raise RuntimeError("o roteiro parou")
    sets = [c for c in celular.executados if c.startswith("ime set")]
    assert sets[0] == f"ime set '{fa.ADBKEYBOARD}'"
    assert sets[-1] == "ime set 'com.google.android.inputmethod.latin/x'"


def test_so_apaga_o_que_o_motor_pos(ambiente):
    _s, celular, aparelho = ambiente
    aparelho.apagar("/sdcard/Movies/Virtu Clips/vc-a.mp4")
    with pytest.raises(fa.AparelhoErro):
        aparelho.apagar("/sdcard/DCIM/Camera/foto.jpg")
    assert celular.executados == ["rm -f '/sdcard/Movies/Virtu Clips/vc-a.mp4'"]


def test_ler_tela_tenta_o_comprimido_primeiro(ambiente):
    _s, celular, aparelho = ambiente
    xml = '<?xml version="1.0"?><hierarchy rotation="0"><node bounds="[0,0][10,10]"/></hierarchy>'
    celular.responder(r"uiautomator dump --compressed", "UI hierchary dumped to: x\n" + xml)
    assert aparelho.ler_tela() == xml
    assert "--compressed" in celular.executados[0]


def test_uma_coisa_de_cada_vez():
    with fa.ocupar("SERIAL-1", "publicando"):
        assert fa.ocupado_com("SERIAL-1") == "publicando"
        with pytest.raises(fa.Ocupado, match="publicando"):
            with fa.ocupar("SERIAL-1", "ensinando"):
                pass
        with fa.ocupar("SERIAL-2", "ensaiando"):
            pass
    assert fa.ocupado_com("SERIAL-1") is None
    with fa.ocupar("SERIAL-1", "ensinando"):
        pass
