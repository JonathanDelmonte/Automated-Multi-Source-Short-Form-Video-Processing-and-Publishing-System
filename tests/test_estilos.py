"""O estilo de criacao do canal (etapa 7.7): o documento, os textos que vao aos
modelos e a leitura do roteiro."""
import json

import pytest

import estilos
import midia_ia


def test_o_estilo_novo_tem_os_padroes_e_uma_semente():
    doc = estilos.normalizar(None)
    assert doc["formato"] == "historia" and doc["duracao_s"] == 60 and doc["cenas"] == 8
    assert doc["visual"]["preset"] == "livro-infantil" and doc["personagens"] == []
    assert doc["legenda"] == {"preset": "karaoke_fill"}
    assert 0 < doc["semente"] < 2**31


def test_nada_e_deduzido_do_nicho():
    """Decisao do autor: estilo configurado, nunca adivinhado. O documento
    nem sabe de nicho -- o que nao veio fica no padrao, igual para todo canal."""
    infantil = estilos.normalizar({"publico": "criancas de 4 a 8 anos"})
    financas = estilos.normalizar({"publico": "adultos que investem"})
    assert infantil["visual"] == financas["visual"]
    assert "nicho" not in json.dumps(estilos.padrao())


def test_campo_desconhecido_passa_e_json_em_texto_e_aceito():
    doc = estilos.normalizar(json.dumps({"musica": {"arquivo": "x.mp3"}, "cenas": 5}))
    assert doc["musica"] == {"arquivo": "x.mp3"} and doc["cenas"] == 5


@pytest.mark.parametrize("spec,trecho", [
    ({"formato": "novela"}, "formato"),
    ({"duracao_s": 5}, "duracao_s"),
    ({"cenas": 40}, "cenas"),
    ({"visual": {"preset": "cubismo"}}, "visual.preset"),
    ({"legenda": {"preset": "rosa"}}, "legenda.preset"),
    ({"personagens": [{"nome": ""}]}, "falta o nome"),
    ({"personagens": [{"nome": "Lulu"}, {"nome": "lulu"}]}, "mesmo nome"),
    ({"personagens": [{"nome": str(i)} for i in range(5)]}, "no maximo 4"),
    ({"tom": "x" * 300}, "tom"),
    ("{nao e json", "JSON"),
])
def test_estilo_torto_diz_o_campo(spec, trecho):
    with pytest.raises(estilos.EstiloInvalido, match=trecho):
        estilos.normalizar(spec)


def test_a_voz_so_das_trinta_quando_o_motor_confere():
    with pytest.raises(estilos.EstiloInvalido, match="voz.nome"):
        estilos.normalizar({"voz": {"nome": "Inventada"}}, vozes=midia_ia.NOMES_DAS_VOZES)
    assert estilos.normalizar({"voz": {"nome": "Sulafat"}},
                              vozes=midia_ia.NOMES_DAS_VOZES)["voz"]["nome"] == "Sulafat"


def test_o_personagem_ganha_id_e_a_imagem_so_se_for_nome_nosso():
    doc = estilos.normalizar({"personagens": [
        {"nome": "Lulu", "descricao": "coelhinha", "imagem": "../../etc/passwd"},
        {"id": "0a1b2c3d", "nome": "Bento", "imagem": "0a1b2c3d-a1b2c3.png"}]})
    lulu, bento = doc["personagens"]
    assert len(lulu["id"]) == 8 and lulu["imagem"] is None
    assert bento["id"] == "0a1b2c3d" and bento["imagem"] == "0a1b2c3d-a1b2c3.png"


def test_sem_visual_nao_cria():
    assert estilos.falta_para_criar(estilos.normalizar({})) is None
    sem = estilos.normalizar({"visual": {"preset": "nenhum"}})
    assert "visual" in estilos.falta_para_criar(sem)
    assert estilos.falta_para_criar(estilos.normalizar(
        {"visual": {"preset": "nenhum", "descricao": "recorte de papel"}})) is None


def test_os_textos_para_os_modelos_levam_o_estilo():
    doc = estilos.normalizar({
        "publico": "criancas", "tom": "divertido", "cenas": 6, "duracao_s": 45,
        "visual": {"preset": "aquarela", "descricao": "tons de azul", "evitar": "sangue"},
        "personagens": [{"nome": "Lulu", "descricao": "coelhinha branca de laco vermelho"}]})
    lulu = doc["personagens"][0]
    ficha = estilos.prompt_do_personagem(doc, lulu)
    assert "Lulu" in ficha and "laco vermelho" in ficha and "plain white background" in ficha
    assert "watercolor" in ficha and "tons de azul" in ficha and "sangue" in ficha
    cena = estilos.prompt_da_cena(doc, {"imagem": "Lulu runs in the forest"}, [lulu])
    assert cena.startswith("Lulu runs in the forest") and "image 0 shows Lulu" in cena
    assert "no text" in cena
    roteiro = estilos.prompt_do_roteiro(doc, "a Lulu aprende a dividir", "pt-BR",
                                        ja_feitos=["A Lulu e a chuva"])
    assert "exatamente 6 cenas" in roteiro and "umas 103 palavras" in roteiro
    assert "- Lulu: coelhinha branca" in roteiro and "A Lulu e a chuva" in roteiro
    assert "a Lulu aprende a dividir" in roteiro


def test_ler_roteiro_troca_os_nomes_pelos_ids_e_limpa():
    doc = estilos.normalizar({"personagens": [{"id": "0a1b2c3d", "nome": "Lulu"}]})
    roteiro = estilos.ler_roteiro({
        "titulo": "  A Lulu   e a chuva ", "descricao": "Uma historia.",
        "hashtags": ["#Lulu", "lulu", "historia infantil", "", "#a", "#b", "#c"],
        "cenas": [{"fala": "Era uma vez   a Lulu.", "imagem": "Lulu under rain",
                   "personagens": ["lulu", "Estranho"]},
                  {"fala": "", "imagem": "x", "personagens": []},
                  {"fala": "Fim.", "imagem": "Lulu smiles", "personagens": ["Lulu", "Lulu"]}]},
        doc)
    assert roteiro["titulo"] == "A Lulu e a chuva"
    assert roteiro["hashtags"] == ["Lulu", "historiainfantil", "a", "b", "c"]
    assert [c["fala"] for c in roteiro["cenas"]] == ["Era uma vez a Lulu.", "Fim."]
    assert roteiro["cenas"][0]["personagens"] == ["0a1b2c3d"]
    assert roteiro["cenas"][1]["personagens"] == ["0a1b2c3d"]
    assert estilos.narracao(roteiro) == "Era uma vez a Lulu.\n\nFim."
    with pytest.raises(estilos.EstiloInvalido):
        estilos.ler_roteiro({"cenas": [{"fala": " "}]}, doc)


def test_cenas_demais_juntam_as_vizinhas_mais_curtas():
    """Cada cena e uma imagem da cota: o roteiro nao passa do que o estilo pediu,
    e nenhuma fala se perde."""
    doc = estilos.normalizar({"cenas": 3, "personagens": [{"id": "0a1b2c3d", "nome": "Lulu"},
                                                           {"id": "1a1b2c3d", "nome": "Bento"}]})
    falas = ["Era uma vez uma coelhinha muito curiosa.", "Oi.", "Tchau.",
             "Ela foi a floresta procurar cenouras.", "E voltou feliz para casa."]
    roteiro = estilos.ler_roteiro({"cenas": [
        {"fala": f, "imagem": f"img {i}", "personagens": ["Lulu"] if i != 2 else ["Bento"]}
        for i, f in enumerate(falas)]}, doc)
    assert len(roteiro["cenas"]) == 3
    assert estilos.narracao(roteiro).split() == " ".join(falas).split()
    juntas = roteiro["cenas"][1]
    assert juntas["fala"] == "Oi. Tchau. Ela foi a floresta procurar cenouras."
    assert juntas["imagem"] == "img 1"
    assert juntas["personagens"] == ["0a1b2c3d", "1a1b2c3d"]


@pytest.mark.parametrize("codigo,nome", [
    (None, "portugues do Brasil"), ("pt-BR", "portugues do Brasil"), ("pt", "portugues do Brasil"),
    ("pt-PT", "portugues de Portugal"), ("en-US", "ingles"), ("es", "espanhol"), ("tlh", "tlh")])
def test_o_idioma_do_canal_vai_por_extenso(codigo, nome):
    assert estilos.nome_do_idioma(codigo) == nome


# --------------------------------------------------------------------------- #
# O episodio longo (etapa 7.8)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("segundos,cenas", [(120, 8), (180, 12), (300, 20), (600, 40),
                                            (60, 8), (900, 40), ("x", 8)])
def test_as_cenas_do_episodio_crescem_com_a_duracao(segundos, cenas):
    assert estilos.cenas_do_longo(segundos) == cenas


def test_a_cena_do_episodio_e_horizontal():
    doc = estilos.normalizar({"visual": {"preset": "anime"}})
    assert "Horizontal 16:9 composition" in estilos.prompt_da_cena(doc, {"imagem": "a"}, [],
                                                                   horizontal=True)
    assert "Vertical 9:16" in estilos.prompt_da_cena(doc, {"imagem": "a"}, [])


def test_o_nome_da_historia():
    assert estilos.nome_da_historia("  A Lulu   na\nfloresta ") == "A Lulu na floresta"
    assert estilos.chave_da_historia("A LULU na  Floresta") == \
        estilos.chave_da_historia("a lulu na floresta")
    assert len(estilos.nome_da_historia("x" * 300)) == estilos.HISTORIA_MAX
    assert estilos.nome_da_historia(None) == ""


def _doc_com_lulu():
    return estilos.normalizar({"personagens": [{"nome": "Lulu", "descricao": "coelha"}],
                               "tom": "carinhoso"})


def test_o_pedido_do_episodio_pede_capitulos_e_resumo():
    texto = estilos.prompt_do_episodio(_doc_com_lulu(), "a chuva", "portugues do Brasil",
                                       300, 20, ja_feitos=["O sol"])
    assert "horizontal para o YouTube" in texto and "cerca de 5 minutos" in texto
    assert f"umas {estilos.palavras_por_duracao(300)} palavras" in texto
    assert "exatamente 20 cenas" in texto and "`capitulos`" in texto and "`resumo`" in texto
    assert "- Lulu: coelha" in texto and "Tom: carinhoso" in texto
    assert "Nao repita estes temas, que o canal ja fez: O sol." in texto
    assert texto.endswith("Ideia deste episodio: a chuva.")


def test_o_episodio_continua_a_historia():
    anteriores = [{"episodio": i, "titulo": f"Ep {i}", "resumo": f"aconteceu {i}"}
                  for i in range(1, 11)]
    texto = estilos.prompt_do_episodio(_doc_com_lulu(), "", "portugues do Brasil", 300, 20,
                                       {"nome": "A Lulu", "episodio": 11,
                                        "anteriores": anteriores},
                                       ja_feitos=["Ep 10"])
    assert "Esta e a historia \"A Lulu\"" in texto
    # So os oito mais recentes por inteiro; os outros pela contagem.
    assert "aconteceu 3" in texto and "aconteceu 2" not in texto
    assert "mais 2 episodio(s)" in texto
    assert "Este e o episodio 11: continue de onde o anterior parou" in texto
    # Pedir para nao repetir os temas do canal brigaria com continuar a historia.
    assert "Nao repita estes temas" not in texto
    assert texto.endswith("Ideia deste episodio: continue a historia.")
    primeiro = estilos.prompt_do_episodio(_doc_com_lulu(), "", "portugues do Brasil", 300, 20,
                                          {"nome": "A Lulu", "episodio": 1, "anteriores": []})
    assert "Este e o episodio 1 da historia \"A Lulu\"" in primeiro


def test_o_video_curto_nao_mudou():
    """O pedido do video curto e o de antes da 7.8, palavra por palavra."""
    doc = _doc_com_lulu()
    texto = estilos.prompt_do_roteiro(doc, "a chuva", "portugues do Brasil")
    assert texto.splitlines()[0] == ("Voce escreve roteiros de videos curtos verticais "
                                     "(TikTok, Reels, Shorts) em portugues do Brasil.")
    assert "capitulos" not in texto and "resumo" not in texto
    roteiro = estilos.ler_roteiro({"titulo": "T", "cenas": [{"fala": "oi"}],
                                   "capitulos": [{"titulo": "x", "cena": 1}], "resumo": "r"}, doc)
    assert "capitulos" not in roteiro and "resumo" not in roteiro


def _cena(fala, **kw):
    return {"fala": fala, "imagem": "img", "personagens": [], **kw}


def test_o_roteiro_do_episodio_guarda_capitulos_e_resumo():
    bruto = {"titulo": "Ep", "descricao": "d", "hashtags": ["a"], "resumo": "  a Lulu\n foi ",
             "cenas": [_cena("um"), _cena("dois"), _cena(""), _cena("quatro"), _cena("cinco"),
                       _cena("seis")],
             "capitulos": [{"titulo": "Começo", "cena": 1}, {"titulo": "Susto", "cena": 3},
                           {"titulo": "Fim", "cena": 5}, {"titulo": "torto", "cena": "x"}]}
    roteiro = estilos.ler_roteiro(bruto, _doc_com_lulu(), alvo=10, longo=True)
    # A cena 3 nao tinha fala: o capitulo dela passa a cena seguinte.
    assert [c["fala"] for c in roteiro["cenas"]] == ["um", "dois", "quatro", "cinco", "seis"]
    assert roteiro["capitulos"] == [{"cena": 0, "titulo": "Começo"},
                                    {"cena": 2, "titulo": "Susto"},
                                    {"cena": 3, "titulo": "Fim"}]
    assert roteiro["resumo"] == "a Lulu foi"
    assert all("capitulo" not in c for c in roteiro["cenas"])


def test_o_primeiro_capitulo_volta_para_a_primeira_cena():
    bruto = {"titulo": "Ep", "cenas": [_cena("um"), _cena("dois"), _cena("tres")],
             "capitulos": [{"titulo": "Meio", "cena": 2}, {"titulo": "Fim", "cena": 3}]}
    roteiro = estilos.ler_roteiro(bruto, _doc_com_lulu(), alvo=10, longo=True)
    assert roteiro["capitulos"] == [{"cena": 0, "titulo": "Meio"}, {"cena": 2, "titulo": "Fim"}]


def test_juntar_cenas_nao_apaga_capitulo():
    cenas = [_cena("a" * 10, capitulo="Um"), _cena("b" * 5, capitulo="Dois"), _cena("c" * 5),
             _cena("d" * 50, capitulo="Tres")]
    juntas = estilos.juntar_cenas(cenas, 3)
    # O par mais curto (b+c) junta, e o capitulo "Dois" fica.
    assert [c.get("capitulo") for c in juntas] == ["Um", "Dois", "Tres"]
    # So sobram pares com dois capitulos: junta assim mesmo, e o da primeira fica.
    juntas = estilos.juntar_cenas([_cena("a", capitulo="Um"), _cena("b", capitulo="Dois")], 1)
    assert juntas[0]["capitulo"] == "Um" and juntas[0]["fala"] == "a b"


def test_o_episodio_pode_ter_quarenta_cenas():
    bruto = {"titulo": "Ep", "cenas": [_cena(f"fala {i}") for i in range(45)]}
    roteiro = estilos.ler_roteiro(bruto, _doc_com_lulu(), alvo=40, longo=True)
    assert len(roteiro["cenas"]) == 40


def test_os_blocos_de_narracao_nao_partem_cena_e_saem_parecidos():
    roteiro = {"cenas": [_cena("x" * 500) for _ in range(12)]}
    blocos = estilos.blocos_de_narracao(roteiro, maximo=2200)
    assert sum(blocos, []) == list(range(12))
    tamanhos = [len(estilos.texto_do_bloco(roteiro, b)) for b in blocos]
    assert len(blocos) == 3 and max(tamanhos) <= 2200
    assert max(tamanhos) - min(tamanhos) <= 510
    # Uma cena maior que o teto vai sozinha.
    grande = {"cenas": [_cena("a" * 100), _cena("b" * 3000), _cena("c" * 100)]}
    assert estilos.blocos_de_narracao(grande, maximo=2200) == [[0], [1], [2]]
    # Tudo cabe: um bloco so.
    assert estilos.blocos_de_narracao({"cenas": [_cena("oi"), _cena("tchau")]}) == [[0, 1]]
    assert estilos.blocos_de_narracao({"cenas": []}) == []
    assert estilos.texto_do_bloco(roteiro, [0, 1]) == "x" * 500 + "\n\n" + "x" * 500


def test_o_titulo_do_episodio_diz_a_historia_e_o_numero():
    assert estilos.titulo_do_episodio("A Lulu", 3, "O susto", "pt-BR") == \
        "A Lulu - Episódio 3: O susto"
    assert estilos.titulo_do_episodio("Lulu", 2, "The scare", "en") == "Lulu - Episode 2: The scare"
    # Avulso: o titulo do roteiro.
    assert estilos.titulo_do_episodio(None, None, "O susto") == "O susto"
    assert estilos.titulo_do_episodio("A Lulu", 0, "O susto") == "O susto"
    # O titulo do roteiro encolhe; a historia e o numero ficam.
    longo = estilos.titulo_do_episodio("A Lulu", 12, "x" * 200)
    assert len(longo) == 100 and longo.startswith("A Lulu - Episódio 12: xxx")
