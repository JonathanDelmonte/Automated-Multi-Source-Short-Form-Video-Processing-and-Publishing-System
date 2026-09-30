"""Os capitulos do video longo (etapa 7.8): as regras do YouTube.

Uma lista fora das regras e ignorada inteira pelo YouTube, sem aviso -- entao
o que importa aqui e que `validos` nunca devolva uma lista que ele recusaria.
"""
import capitulos


def test_o_tempo_no_formato_que_o_youtube_le():
    assert capitulos.tempo(0) == "0:00"
    assert capitulos.tempo(9.99) == "0:09"
    assert capitulos.tempo(75) == "1:15"
    assert capitulos.tempo(600) == "10:00"
    assert capitulos.tempo(3725) == "1:02:05"
    assert capitulos.tempo(None) == "0:00"
    assert capitulos.tempo(-3) == "0:00"


def test_o_primeiro_vai_para_zero_e_a_ordem_e_crescente():
    lista = capitulos.validos([(40, "Meio"), (12.8, "Começo"), (95, "Fim")], total_s=200)
    assert lista == [(0, "Começo"), (40, "Meio"), (95, "Fim")]


def test_o_capitulo_curto_sai_e_o_anterior_fica_com_o_trecho_dele():
    """10 s e o minimo do YouTube, contado no tempo que aparece (para baixo).
    Tirar o SEGUINTE poria o titulo do curto em cima do conteudo do outro."""
    lista = capitulos.validos([(0, "A"), (40, "Rápido"), (45, "B"), (105, "C")], total_s=135)
    assert lista == [(0, "A"), (45, "B"), (105, "C")]
    # O primeiro curto demais: o seguinte passa a comecar em 0:00.
    lista = capitulos.validos([(0, "Vinheta"), (9.9, "A"), (20, "B"), (29.5, "C"), (45, "D")],
                              total_s=120)
    assert lista == [(0, "A"), (29, "C"), (45, "D")]
    # Exatamente 10 s passa.
    assert capitulos.validos([(0, "A"), (10, "B"), (20, "C")], total_s=60) == \
        [(0, "A"), (10, "B"), (20, "C")]
    # Dois no mesmo segundo: fica o segundo deles.
    assert capitulos.validos([(0, "A"), (30, "B"), (30, "B2"), (60, "C")], total_s=90) == \
        [(0, "A"), (30, "B2"), (60, "C")]


def test_o_ultimo_precisa_de_dez_segundos_ate_o_fim():
    lista = capitulos.validos([(0, "A"), (30, "B"), (60, "C"), (95, "D")], total_s=100)
    assert lista == [(0, "A"), (30, "B"), (60, "C")]


def test_menos_de_tres_nao_vira_lista():
    assert capitulos.validos([(0, "A"), (30, "B")], total_s=100) == []
    assert capitulos.validos([(0, "A"), (5, "B"), (8, "C")], total_s=100) == []
    assert capitulos.validos([], total_s=100) == []


def test_titulo_vazio_ou_torto_sai():
    lista = capitulos.validos([(0, "  "), (15, "B"), ("x", "C"), (30, "  D \n  e "), (50, "E")],
                              total_s=100)
    assert lista == [(0, "B"), (30, "D e"), (50, "E")]


def test_um_tempo_no_comeco_do_titulo_nao_vira_outro_capitulo():
    assert capitulos.titulo("1:23 - A volta") == "A volta"
    assert capitulos.titulo("(0:45) Começo") == "Começo"
    assert capitulos.titulo("2 irmãos") == "2 irmãos"
    assert len(capitulos.titulo("x" * 200)) == capitulos.TITULO_MAX


def test_a_descricao_com_a_lista_e_as_hashtags():
    lista = capitulos.validos([(0, "A chegada"), (70, "O susto"), (130, "A volta")], total_s=200)
    texto = capitulos.na_descricao("A Lulu vai à floresta.", lista, "pt-BR",
                                   hashtags=["lulu", "#historia"])
    assert texto == ("A Lulu vai à floresta.\n\nCapítulos\n0:00 A chegada\n1:10 O susto\n"
                     "2:10 A volta\n\n#lulu #historia")
    assert capitulos.na_descricao("", lista, "en").startswith("Chapters\n0:00 A chegada")
    # Sem capitulos, sem lista.
    assert capitulos.na_descricao("Texto.", [], "pt") == "Texto."
