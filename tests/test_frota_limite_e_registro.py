"""O limite por conta e o historico de cada aparelho da frota (etapa 7.9,
ADR-016), sem adb e sem banco: os dois moram em disco, e e o disco que se
confere aqui.

O limite e a trava que vale para os dois drivers -- debitado ANTES de tocar no
aparelho e devolvido quando nada aconteceu --, e o historico e a resposta para
"por que nao saiu?", com nomes que viram caminho.
"""
import io
import json
import os
import threading
import uuid

import pytest

import frota_limite
import frota_registro

CONTA = "conta-1"
APARELHO = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def dados(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _png(largura=1080, altura=2400):
    from PIL import Image
    saida = io.BytesIO()
    Image.new("RGB", (largura, altura), (40, 20, 60)).save(saida, "PNG")
    return saida.getvalue()


# --------------------------------------------------------------------------- #
# O limite por conta
# --------------------------------------------------------------------------- #

def test_debita_ate_o_limite_e_para():
    for _ in range(3):
        assert frota_limite.debitar(CONTA, "2026-10-01", 3)
    assert not frota_limite.debitar(CONTA, "2026-10-01", 3)
    assert frota_limite.usados(CONTA, "2026-10-01") == 3
    assert not frota_limite.cabe(CONTA, "2026-10-01", 3)
    # Outro dia e outra conta comecam do zero.
    assert frota_limite.cabe(CONTA, "2026-10-02", 3)
    assert frota_limite.cabe("conta-2", "2026-10-01", 3)


def test_devolver_desfaz_um_debito_e_nunca_fica_negativo():
    frota_limite.debitar(CONTA, "2026-10-01", 3)
    frota_limite.devolver(CONTA, "2026-10-01")
    frota_limite.devolver(CONTA, "2026-10-01")
    assert frota_limite.usados(CONTA, "2026-10-01") == 0


def test_dois_posts_ao_mesmo_tempo_nao_passam_os_dois_pelo_ultimo_lugar():
    """O agendador e um "publicar agora" da mesma conta: ler e gravar sob a
    mesma trava, ou os dois veem o lugar livre."""
    frota_limite.debitar(CONTA, "2026-10-01", 3)
    frota_limite.debitar(CONTA, "2026-10-01", 3)
    resultados = []
    largada = threading.Barrier(8)

    def tentar():
        largada.wait()
        resultados.append(frota_limite.debitar(CONTA, "2026-10-01", 3))

    threads = [threading.Thread(target=tentar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert resultados.count(True) == 1
    assert frota_limite.usados(CONTA, "2026-10-01") == 3


def test_guarda_so_os_dias_que_a_tela_mostra():
    for dia in range(1, 13):
        frota_limite.debitar(CONTA, f"2026-10-{dia:02d}", 3)
    semana = frota_limite.semana(CONTA)
    assert len(semana) == frota_limite.DIAS_GUARDADOS
    assert min(semana) == f"2026-10-{12 - frota_limite.DIAS_GUARDADOS + 1:02d}"


def test_a_conta_que_sai_da_frota_leva_a_contagem():
    frota_limite.debitar(CONTA, "2026-10-01", 3)
    assert frota_limite.esquecer(CONTA) == {"2026-10-01": 1}
    assert frota_limite.usados(CONTA, "2026-10-01") == 0


def test_limite_zero_ou_negativo_nunca_debita():
    assert not frota_limite.debitar(CONTA, "2026-10-01", 0)
    assert not frota_limite.debitar(CONTA, "2026-10-01", -3)


# --------------------------------------------------------------------------- #
# O historico de cada aparelho
# --------------------------------------------------------------------------- #

def test_execucao_guarda_as_telas_reduzidas_e_o_resumo():
    registro = frota_registro.Execucao(APARELHO, "ensaio", "instagram")
    registro.guardar("passo-1-tocar", _png())
    registro.fechar("passou", "O motor chegou ao botão de publicar e não tocou.", passo=None)
    ultima = frota_registro.ultimas(APARELHO)[0]
    assert ultima["situacao"] == "passou" and ultima["fotos"] == ["01-passo-1-tocar.jpg"]
    fotos = frota_registro.fotos(APARELHO, registro.id)
    assert fotos[0]["imagem"].startswith("data:image/jpeg;base64,")
    from PIL import Image
    import base64
    imagem = Image.open(io.BytesIO(base64.b64decode(fotos[0]["imagem"].split(",", 1)[1])))
    assert imagem.width == frota_registro.LARGURA


@pytest.mark.parametrize("nome,esperado", [
    ("passo-2-legenda-não-entrou", "01-passo-2-legenda-n-o-entrou.jpg"),
    ("../../segredo", "01-segredo.jpg"),
    ("", "01-tela.jpg"),
])
def test_o_nome_da_foto_vira_caminho_e_e_saneado(nome, esperado):
    registro = frota_registro.Execucao(APARELHO, "automatico", "instagram")
    registro.guardar(nome, _png(100, 200))
    assert registro.resumo["fotos"] == [esperado]
    assert os.path.exists(os.path.join(registro.pasta, esperado))


def test_fotos_so_le_o_que_casa_com_o_padrao(dados):
    """O id da execucao e os nomes vem da URL e do resumo em disco: um resumo
    adulterado nao serve arquivo de fora da pasta."""
    registro = frota_registro.Execucao(APARELHO, "entrega", "instagram")
    registro.guardar("passo-1-tocar", _png(100, 200))
    registro.resumo["fotos"].append("../../../segredo.txt")
    registro.fechar("entregue", "")
    (dados / "segredo.txt").write_text("nao", encoding="utf-8")
    assert [f["nome"] for f in frota_registro.fotos(APARELHO, registro.id)] == [
        "01-passo-1-tocar.jpg"]
    with pytest.raises(ValueError):
        frota_registro.fotos(APARELHO, "../" + registro.id)
    with pytest.raises(ValueError):
        frota_registro.Execucao("../fora", "entrega")


def test_ficam_as_ultimas_execucoes_no_historico_e_no_disco(monkeypatch):
    monkeypatch.setattr(frota_registro, "MAXIMO", 3)
    ids = []
    for i in range(5):
        registro = frota_registro.Execucao(APARELHO, "entrega", "instagram")
        registro.fechar("entregue", f"{i}")
        ids.append(registro.id)
    assert [e["detalhe"] for e in frota_registro.ultimas(APARELHO)] == ["4", "3", "2"]
    pasta = os.path.join(frota_registro.pasta_do_aparelho(APARELHO), "execucoes")
    assert sorted(os.listdir(pasta)) == sorted(ids[2:])
    with open(os.path.join(frota_registro.pasta_do_aparelho(APARELHO),
                           "execucoes.jsonl"), encoding="utf-8") as f:
        assert len([json.loads(l) for l in f]) == 3


def test_tirar_o_aparelho_leva_o_historico():
    frota_registro.Execucao(APARELHO, "entrega").fechar("entregue")
    frota_registro.apagar(APARELHO)
    assert frota_registro.ultimas(APARELHO) == []
