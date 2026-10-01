"""O roteiro do automatico (etapa 7.9, ADR-016): ler a tela, achar o botao
ensinado, ensaiar, publicar e ensinar -- contra um celular imitado, com as telas
de um fluxo como o do Instagram."""
from xml.sax.saxutils import quoteattr

import pytest

import frota_roteiro as fr

PKG = "com.instagram.android"


def no(rid="", texto="", desc="", classe="android.widget.Button", clicavel=True,
       caixa=(0, 0, 10, 10), filhos=()):
    return {"rid": rid, "texto": texto, "desc": desc, "classe": classe,
            "clicavel": clicavel, "caixa": caixa, "filhos": list(filhos)}


def xml_de(nos, raiz=(0, 0, 1080, 2400), pacote=PKG):
    def um(n):
        x1, y1, x2, y2 = n["caixa"]
        attrs = (f'text={quoteattr(n["texto"])} resource-id={quoteattr(n["rid"])} '
                 f'class={quoteattr(n["classe"])} package="{pacote}" '
                 f'content-desc={quoteattr(n["desc"])} clickable="{str(n["clicavel"]).lower()}" '
                 f'long-clickable="false" bounds="[{x1},{y1}][{x2},{y2}]"')
        return f"<node {attrs}>{''.join(um(f) for f in n['filhos'])}</node>"
    x1, y1, x2, y2 = raiz
    corpo = "".join(um(n) for n in nos)
    return (f'<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">'
            f'<node text="" resource-id="" class="android.widget.FrameLayout" package="{pacote}" '
            f'content-desc="" clickable="false" long-clickable="false" '
            f'bounds="[{x1},{y1}][{x2},{y2}]">{corpo}</node></hierarchy>')


AVANCAR = no(rid=f"{PKG}:id/next_button", classe="android.widget.FrameLayout",
             caixa=(880, 100, 1060, 180),
             filhos=[no(texto="Avançar", classe="android.widget.TextView", clicavel=False,
                        caixa=(900, 110, 1040, 170))])
LEGENDA = no(rid=f"{PKG}:id/caption_input", texto="Escreva uma legenda...",
             classe="android.widget.EditText", caixa=(40, 300, 1040, 500))
COMPARTILHAR = no(rid=f"{PKG}:id/share_button", texto="Compartilhar",
                  caixa=(40, 2200, 1040, 2320))
FEED = no(rid=f"{PKG}:id/feed_tab", desc="Página inicial", caixa=(0, 2300, 200, 2400))


class CelularImitado:
    """As telas de um post e o que cada toque faz. O campo de legenda guarda o
    que foi digitado."""

    def __init__(self, telas, transicoes, inicio, digitar_funciona=True):
        self.telas = telas            # nome -> lista de nos
        self.transicoes = transicoes  # (tela, rid) -> proxima tela
        self.atual = inicio
        self.tocados = []
        self.digitado = ""
        self.digitar_funciona = digitar_funciona
        self.foco = None
        self.raizes = {}

    def ler_tela(self):
        nos = []
        for n in self.telas[self.atual]:
            n = dict(n)
            if n["classe"].endswith("EditText") and self.digitado:
                n["texto"] = self.digitado
            nos.append(n)
        return xml_de(nos, raiz=self.raizes.get(self.atual, (0, 0, 1080, 2400)))

    def tela_png(self):
        return b"\x89PNG\r\n\x1a\nfalso"

    def tocar(self, x, y):
        tela = fr.ler(self.ler_tela())
        alvo = fr.no_no_ponto(tela, x, y)
        self.tocados.append(alvo.rid or alvo.rotulo)
        if alvo.editavel:
            self.foco = alvo.rid
        self.atual = self.transicoes.get((self.atual, alvo.rid), self.atual)

    def limpar_campo(self):
        self.digitado = ""

    def digitar(self, texto):
        if self.digitar_funciona:
            self.digitado += texto


def fluxo_do_instagram(**kw):
    return CelularImitado(
        telas={"editor": [AVANCAR], "legenda": [LEGENDA, COMPARTILHAR], "feed": [FEED]},
        transicoes={("editor", AVANCAR["rid"]): "legenda",
                    ("legenda", COMPARTILHAR["rid"]): "feed"},
        inicio="editor", **kw)


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora

    def dormir(self, s):
        self.agora += s


def roteiro_ensinado():
    celular = fluxo_do_instagram()
    ensino = fr.Ensino(celular, (1080, 2400), dormir=lambda s: None)
    ensino.atualizar()
    ensino.tocar(950 / 1080, 140 / 2400)   # Avancar
    ensino.tocar(500 / 1080, 400 / 2400)   # a legenda
    ensino.publicar(500 / 1080, 2250 / 2400)
    return ensino.roteiro(), celular


def executor(celular, passos, **kw):
    relogio = Relogio()
    fotos = []
    return fr.Executor(celular, passos, guardar=lambda nome, png: fotos.append(nome),
                       relogio=relogio, dormir=relogio.dormir, log=lambda m: None,
                       **kw), fotos


# --------------------------------------------------------------------------- #
# A tela
# --------------------------------------------------------------------------- #

def test_o_rotulo_vem_de_dentro_do_botao():
    tela = fr.ler(xml_de([AVANCAR]))
    botao = next(n for n in tela.nos if n.rid.endswith("next_button"))
    assert botao.tocavel and botao.rotulo == "Avançar"


def test_o_toque_cai_no_menor_tocavel():
    tela = fr.ler(xml_de([AVANCAR, LEGENDA]))
    assert fr.no_no_ponto(tela, 950, 140).rid.endswith("next_button")
    assert fr.no_no_ponto(tela, 500, 400).editavel
    assert fr.no_no_ponto(tela, 500, 1500) is None


def test_janela_menor_que_a_tela():
    assert fr.ler(xml_de([COMPARTILHAR])).cheia is True
    assert fr.ler(xml_de([COMPARTILHAR], raiz=(60, 900, 1020, 1500))).cheia is False


def test_achar_pelo_id_mesmo_em_outro_lugar():
    alvo = fr.alvo_de(fr.ler(xml_de([COMPARTILHAR])).nos[1])
    movido = dict(COMPARTILHAR, caixa=(40, 1900, 1040, 2020))
    achado = fr.achar(fr.ler(xml_de([movido])), alvo)
    assert achado is not None and achado.caixa == (40, 1900, 1040, 2020)


def test_achar_pelo_texto_quando_nao_ha_id():
    sem_id = no(texto="Compartilhar", caixa=(40, 2200, 1040, 2320))
    alvo = fr.alvo_de(fr.ler(xml_de([sem_id])).nos[1])
    outro_idioma = no(texto="Share", caixa=(40, 2200, 1040, 2320))
    assert fr.achar(fr.ler(xml_de([sem_id])), alvo) is not None
    assert fr.achar(fr.ler(xml_de([outro_idioma])), alvo) is None


def test_icone_sem_nome_so_pela_posicao_e_nunca_para_publicar():
    icone = no(classe="android.widget.ImageView", caixa=(900, 100, 1000, 200))
    alvo = fr.alvo_de(fr.ler(xml_de([icone])).nos[1])
    assert not fr.tem_identidade(alvo)
    tela = fr.ler(xml_de([icone]))
    assert fr.achar(tela, alvo) is not None
    assert fr.achar(tela, alvo, so_por_identidade=True) is None


def test_do_campo_de_texto_nao_se_guarda_o_texto():
    alvo = fr.alvo_de(fr.ler(xml_de([LEGENDA])).nos[1])
    assert alvo["editavel"] and alvo["texto"] == "" and alvo["rotulo"] == ""
    assert fr.descrever(alvo) == "o campo da legenda"


@pytest.mark.parametrize("passos,motivo", [
    ([], "vazio"),
    ([{"tipo": "tocar", "alvo": {"rid": "x"}}], "termina no botão de publicar"),
    ([{"tipo": "publicar", "alvo": {"rid": "x"}}, {"tipo": "tocar", "alvo": {"rid": "y"}}],
     "termina no botão de publicar"),
    ([{"tipo": "publicar", "alvo": {"caixa": [0, 0, 1, 1]}}], "nome ou id"),
    ([{"tipo": "curtir", "alvo": {"rid": "x"}}], "torto"),
])
def test_validar_recusa_roteiro_torto(passos, motivo):
    with pytest.raises(ValueError, match=motivo):
        fr.validar(passos)


# --------------------------------------------------------------------------- #
# O ensino
# --------------------------------------------------------------------------- #

def test_ensinar_anota_os_passos_e_nao_toca_em_publicar():
    passos, celular = roteiro_ensinado()
    assert [p["tipo"] for p in passos] == ["tocar", "legenda", "publicar"]
    assert passos[0]["alvo"]["rotulo"] == "Avançar"
    assert passos[2]["alvo"]["rid"].endswith("share_button")
    # O ensino tocou no Avancar e no campo, digitou a legenda de teste, e NAO
    # tocou em Compartilhar.
    assert celular.tocados == [AVANCAR["rid"], LEGENDA["rid"]]
    assert celular.digitado == fr.LEGENDA_DE_TESTE
    assert celular.atual == "legenda"


def test_ensinar_recusa_publicar_sem_identidade_e_campo_de_texto():
    icone = no(classe="android.widget.ImageView", caixa=(900, 100, 1000, 200))
    celular = CelularImitado({"t": [icone, LEGENDA]}, {}, "t")
    ensino = fr.Ensino(celular, (1080, 2400), dormir=lambda s: None)
    with pytest.raises(ValueError, match="nome nem id"):
        ensino.publicar(950 / 1080, 150 / 2400)
    with pytest.raises(ValueError, match="campo de texto"):
        ensino.publicar(500 / 1080, 400 / 2400)
    with pytest.raises(ValueError, match="nada para tocar"):
        ensino.tocar(0.5, 0.9)


def test_desfazer_tira_o_ultimo_passo():
    celular = fluxo_do_instagram()
    ensino = fr.Ensino(celular, (1080, 2400), dormir=lambda s: None)
    ensino.tocar(950 / 1080, 140 / 2400)
    assert ensino.desfazer()["tipo"] == "tocar"
    assert ensino.passos == []


# --------------------------------------------------------------------------- #
# O ensaio e o post
# --------------------------------------------------------------------------- #

def test_ensaio_para_antes_de_publicar():
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram()
    ex, fotos = executor(celular, passos, legenda="Meu corte #shorts", ensaio=True)
    r = ex.rodar()
    assert r.ok and not r.publicado
    assert COMPARTILHAR["rid"] not in celular.tocados
    assert celular.digitado == "Meu corte #shorts"
    assert fotos[-1].endswith("publicar")


def test_post_toca_em_publicar_e_confirma_pela_tela():
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram()
    ex, fotos = executor(celular, passos, legenda="Meu corte #shorts")
    r = ex.rodar()
    assert r.ok and r.publicado and not r.duvida
    assert celular.tocados[-1] == COMPARTILHAR["rid"]
    assert fotos[-1] == "depois-de-publicar"


def test_janela_que_ninguem_ensinou_para_o_roteiro():
    passos, _ = roteiro_ensinado()
    aviso = no(rid="android:id/button1", texto="Permitir", caixa=(600, 1300, 1000, 1400))
    celular = fluxo_do_instagram()
    celular.telas["editor"] = [aviso]
    celular.raizes["editor"] = (60, 900, 1020, 1500)
    ex, fotos = executor(celular, passos, legenda="x")
    r = ex.rodar()
    assert not r.ok and r.parou_em == 0
    assert "janela que ninguém ensinou" in r.motivo
    assert celular.tocados == []          # nunca toca no que nao foi ensinado
    assert fotos[-1].endswith("parou")


def test_aviso_que_so_apareceu_no_ensino_e_pulado():
    """Um "OK" de dica que apareceu no dia do ensino nao trava o post do dia
    seguinte, quando o passo depois dele ja esta na tela."""
    passos, _ = roteiro_ensinado()
    dica = {"tipo": "tocar", "alvo": fr.alvo_de(fr.ler(xml_de(
        [no(texto="OK", caixa=(400, 1000, 680, 1100))])).nos[1])}
    passos = [dica] + passos
    celular = fluxo_do_instagram()
    ex, _ = executor(celular, passos, legenda="x")
    assert ex.rodar().publicado


def test_legenda_que_nao_entrou_para_antes_de_publicar():
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram(digitar_funciona=False)
    ex, _ = executor(celular, passos, legenda="Meu corte")
    r = ex.rodar()
    assert not r.ok and "legenda não entrou" in r.motivo
    assert COMPARTILHAR["rid"] not in celular.tocados


def test_janela_depois_de_publicar_e_duvida_nao_sucesso():
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram()
    pergunta = no(rid="android:id/button1", texto="Compartilhar no Facebook?",
                  caixa=(600, 1300, 1000, 1400))
    celular.telas["feed"] = [pergunta]
    celular.raizes["feed"] = (60, 900, 1020, 1500)
    ex, _ = executor(celular, passos, legenda="x")
    r = ex.rodar()
    assert not r.ok and r.duvida and not r.publicado
    assert "confira no app" in r.motivo


def test_tela_que_nao_muda_depois_de_publicar_e_duvida():
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram()
    celular.transicoes.pop(("legenda", COMPARTILHAR["rid"]))
    ex, _ = executor(celular, passos, legenda="x")
    r = ex.rodar()
    assert r.duvida and not r.publicado and "não mudou" in r.motivo


def test_botao_de_publicar_em_outro_idioma_nao_e_tocado():
    """O app mudou de idioma: o id ainda bate, mas o texto nao. O id manda --
    e o mesmo botao."""
    passos, _ = roteiro_ensinado()
    celular = fluxo_do_instagram()
    celular.telas["legenda"] = [LEGENDA, dict(COMPARTILHAR, texto="Share")]
    ex, _ = executor(celular, passos, legenda="x")
    assert ex.rodar().publicado
