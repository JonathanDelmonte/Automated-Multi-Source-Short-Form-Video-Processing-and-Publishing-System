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
