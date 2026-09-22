"""Leitura do levantamento de clientes -- a parte que o CI alcanca.

`medir()` e a unica funcao com rede e nao e exercitada aqui de proposito:
o CI nao fala com o YouTube, e um teste que dependesse disso seria vermelho
por motivo alheio ao repositorio. O que se testa e a CONCLUSAO, que e onde
mora o julgamento.
"""
import pytest

d = pytest.importorskip("diagnostico_youtube")


def _res(altura=0, erro=None):
    return {"altura": altura, "erro": erro}


BLOQUEIO = "Sign in to confirm you're not a bot."


def test_bloqueio_e_reconhecido_em_qualquer_caixa():
    assert d.e_bloqueio(BLOQUEIO)
    assert d.e_bloqueio("ERRO: LOGIN_REQUIRED")
    assert not d.e_bloqueio("Video unavailable")
    assert not d.e_bloqueio(None)


def test_sem_nada_medido_nao_conclui_nada():
    assert d.conclusoes([]) == ["Nada foi medido."]


def test_todos_bloqueados_aponta_o_IP_e_nao_a_lista():
    resultados = [(r, c, _res(erro=BLOQUEIO)) for r, c in d.CANDIDATOS]
    frases = " ".join(d.conclusoes(resultados))
    assert "anti-bot" in frases
    assert "nao sobre a lista de clientes" in frases
    # Nao pode sugerir troca de lista: seria mandar mexer no que nao e a causa.
    assert "YT_CLIENTS_ANON=" not in frases


def test_falhas_diferentes_nao_viram_diagnostico_unico():
    resultados = [
        ("tv", ["tv"], _res(erro="Video unavailable")),
        ("default", ["default"], _res(erro="HTTP Error 429")),
    ]
    frases = " ".join(d.conclusoes(resultados))
    assert "motivos diferentes" in frases
    assert "anti-bot" not in frases


def test_o_vencedor_e_a_maior_altura_e_vira_linha_de_env(monkeypatch):
    monkeypatch.setenv("YT_CLIENTS_ANON", "mweb")
    resultados = [
        ("tv", ["tv"], _res(altura=720)),
        ("ios", ["ios"], _res(altura=1080)),
        ("mweb", ["mweb"], _res(erro=BLOQUEIO)),
    ]
    frases = d.conclusoes(resultados)
    assert "`ios` (1080p)" in frases[0]
    assert any("YT_CLIENTS_ANON=ios" in f for f in frases)


def test_com_cookies_a_linha_sugerida_e_a_do_outro_env(monkeypatch):
    monkeypatch.setenv("YT_CLIENTS_AUTH", "mweb")
    resultados = [("tv", ["tv"], _res(altura=1080))]
    frases = d.conclusoes(resultados, tem_cookies=True)
    assert any("YT_CLIENTS_AUTH=tv" in f for f in frases)


def test_nao_manda_mudar_quando_o_vencedor_ja_e_o_primeiro_da_lista(monkeypatch):
    monkeypatch.setenv("YT_CLIENTS_ANON", "tv,default")
    resultados = [
        ("tv", ["tv"], _res(altura=1080)),
        ("default", ["default"], _res(erro=BLOQUEIO)),
    ]
    frases = " ".join(d.conclusoes(resultados))
    assert "Nao ha nada a mudar no .env" in frases
    assert "YT_CLIENTS_ANON=" not in frases


def test_lista_identica_tambem_nao_manda_mudar(monkeypatch):
    monkeypatch.setenv("YT_CLIENTS_ANON", "tv")
    resultados = [("tv", ["tv"], _res(altura=1080))]
    frases = " ".join(d.conclusoes(resultados))
    assert "exatamente a lista que o pipeline ja usa" in frases


def test_o_resumo_do_erro_corta_o_rodape_do_yt_dlp():
    longo = ("ERROR: [youtube] abc: Sign in to confirm you're not a bot. "
             "Use --cookies-from-browser or --cookies for the authentication. "
             "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ")
    curto = d._resumo_do_erro(longo)
    assert curto.startswith("[youtube] abc: Sign in to confirm")
    assert "cookies-from-browser" not in curto
    assert d.e_bloqueio(curto)


def test_os_candidatos_nao_pedem_conta():
    # Um cliente com REQUIRE_AUTH so responderia sobre a conta, nunca sobre a
    # pergunta que este modulo faz.
    yt_base = pytest.importorskip("yt_dlp.extractor.youtube._base")
    for _rotulo, clients in d.CANDIDATOS:
        for c in clients:
            if c == "default":
                continue
            cfg = yt_base.INNERTUBE_CLIENTS[c]
            assert not cfg.get("REQUIRE_AUTH"), c


def test_a_tabela_sai_alinhada():
    resultados = [("tv", ["tv"], _res(altura=1080)),
                  ("web_embedded", ["web_embedded"], _res(erro="x"))]
    linhas = d.texto("https://youtu.be/abc", resultados).splitlines()
    i = next(n for n, ln in enumerate(linhas) if "candidato" in ln)
    # A coluna da altura comeca na mesma posicao no cabecalho, na regua e em
    # todas as linhas -- inclusive na do rotulo mais longo, que e o caso que
    # estourava a largura quando ela vinha so dos resultados.
    coluna = linhas[i].index("altura")
    regua = linhas[i + 1]
    assert regua[coluna] == "-" and regua[coluna - 1] == " "
    assert linhas[i + 2].index("1080p") == coluna
    assert linhas[i + 3][coluna] == "-"
