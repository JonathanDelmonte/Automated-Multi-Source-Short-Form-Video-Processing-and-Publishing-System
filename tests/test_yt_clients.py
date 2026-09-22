"""YouTube client selection shared by the download and the duration probe.

Measured 6-sep-2026 in the prod container, same static proxy, same video:
cookies + yt-dlp's authed defaults -> "Video unavailable" (no formats);
cookies + mweb with a PO token -> 1080p. The explicit `default,mweb` list is
what keeps those videos off the per-GB proxy.

A linha "sem cookies o padrao do yt-dlp devolve 1080p", que valia na mesma
medicao, deixou de valer em 22-set-2026: sem cookies os tres clientes daquela
lista (`visionos`, `web`, `mweb`) respondem LOGIN_REQUIRED e o job morre com
"sign in to confirm you're not a bot". Dai as duas listas separadas.
"""
import pytest

yt_clients = pytest.importorskip("yt_clients")


@pytest.fixture(autouse=True)
def _sem_override(monkeypatch):
    """Os testes descrevem os PADROES; um .env do desenvolvedor nao pode
    silenciar essa descricao."""
    monkeypatch.delenv("YT_CLIENTS_AUTH", raising=False)
    monkeypatch.delenv("YT_CLIENTS_ANON", raising=False)


def test_hd_com_cookies_precisa_de_um_pot_provider():
    # Com cookies a lista termina no `mweb`, que exige PO token: sem provedor
    # nao ha caminho HD e o plano pula a tentativa.
    assert yt_clients.hd_extractor_args("", "") is None


def test_hd_sem_cookies_existe_sem_pot_provider():
    # O `tv` nao pede token nenhum, entao o caminho HD anonimo vale numa
    # instalacao sem bgutil -- que e o self-host mais simples que existe.
    got = yt_clients.hd_extractor_args("", "", cookies=False)
    assert got["youtube"]["player_client"] == ["tv", "default"]
    assert "youtubepot-bgutilscript" not in got


def test_hd_lists_default_and_mweb_with_the_provider():
    got = yt_clients.hd_extractor_args("", "/opt/gen.js")
    assert got["youtube"]["player_client"] == ["default", "mweb"]
    assert got["youtubepot-bgutilscript"] == {"script_path": ["/opt/gen.js"]}
    http = yt_clients.hd_extractor_args("http://pot:4416", "/opt/gen.js")
    assert http["youtubepot-bgutilhttp"] == {"base_url": ["http://pot:4416"]}
    assert "youtubepot-bgutilscript" not in http


def test_a_lista_anonima_comeca_no_tv():
    # `tv` e o unico cliente da tabela do yt-dlp sem exigencia de conta NEM de
    # PO token (GVS ou player). E o que sustenta "so colar o link".
    assert yt_clients.clients_for(False)[0] == "tv"
    assert yt_clients.clients_for(True) == ["default", "mweb"]


def test_a_lista_anonima_nao_tem_cliente_que_exija_conta():
    yt_base = pytest.importorskip("yt_dlp.extractor.youtube._base")
    for nome in yt_clients.ANON_CLIENTS:
        if nome == "default":
            continue
        assert not yt_base.INNERTUBE_CLIENTS[nome].get("REQUIRE_AUTH"), nome


def test_o_ambiente_sobrescreve_cada_lista(monkeypatch):
    # Quem decide qual cliente ainda passa e o YouTube, e a resposta muda sem
    # aviso: trocar a lista tem de ser editar o .env e reiniciar, nunca
    # reconstruir a imagem.
    monkeypatch.setenv("YT_CLIENTS_ANON", "ios, android_vr ,")
    monkeypatch.setenv("YT_CLIENTS_AUTH", "tv")
    assert yt_clients.clients_for(False) == ["ios", "android_vr"]
    assert yt_clients.clients_for(True) == ["tv"]
    assert (yt_clients.fallback_extractor_args("", "", cookies=False)
            ["youtube"]["player_client"] == ["ios", "android_vr"])


def test_override_vazio_cai_no_padrao(monkeypatch):
    # Uma variavel posta em branco (ou so com virgulas) e o que sobra de quem
    # tentou "desligar" a linha do .env; virar lista vazia faria o yt-dlp
    # receber `player_client: []` e nao extrair nada.
    monkeypatch.setenv("YT_CLIENTS_ANON", " , ,")
    assert yt_clients.clients_for(False) == yt_clients.ANON_CLIENTS


def test_fallback_never_skips_the_webpage():
    # player_skip=webpage drops the account's Data Sync ID and mweb then
    # cannot get its PO token: only the 360p progressive format survives.
    for args in (yt_clients.fallback_extractor_args("", ""),
                 yt_clients.fallback_extractor_args("", "/opt/gen.js")):
        assert "player_skip" not in args["youtube"]
        assert "mweb" in args["youtube"]["player_client"]
        for dead in ("tv_embed", "android"):
            assert dead not in args["youtube"]["player_client"]


def test_fallback_keeps_the_provider_when_configured():
    assert "youtubepot-bgutilscript" in yt_clients.fallback_extractor_args("", "/x.js")
    assert "youtubepot-bgutilscript" not in yt_clients.fallback_extractor_args("", "")


def test_lists_are_copies():
    a = yt_clients.hd_extractor_args("", "/x.js")["youtube"]["player_client"]
    a.append("web_safari")
    assert yt_clients.hd_extractor_args("", "/x.js")["youtube"]["player_client"] == ["default", "mweb"]
    b = yt_clients.clients_for(False)
    b.append("web_safari")
    assert yt_clients.clients_for(False) == ["tv", "default"]


# --- a tentativa, que e onde a lista e escolhida de verdade ------------------

def test_sem_jar_toda_tentativa_sai_anonima():
    # O caso do painel: alguem colou um link e nao configurou nada. Ate
    # 22-set-2026 as duas tentativas saiam com `default,mweb` e as duas
    # morriam com "sign in to confirm you're not a bot".
    for label in ("HD", "HD-direct", "HD-static1", "fallback", "fallback-static"):
        args = yt_clients.args_da_tentativa(label, True, False, "", "/opt/gen.js")
        assert args["youtube"]["player_client"] == ["tv", "default"], label


def test_com_jar_a_tentativa_HD_usa_a_lista_da_conta():
    args = yt_clients.args_da_tentativa("HD", True, True, "", "/opt/gen.js")
    assert args["youtube"]["player_client"] == ["default", "mweb"]


def test_a_fallback_anonima_troca_de_lista_mesmo_com_jar():
    # O plano manda a fallback sair sem cookies depois de uma HD que falhou:
    # se ela sai anonima, tem de sair com a lista anonima -- mandar cookies
    # fora e lista de conta dentro e a combinacao que nao passa em nenhum dos
    # dois mundos.
    args = yt_clients.args_da_tentativa("fallback", False, True, "", "/opt/gen.js")
    assert args["youtube"]["player_client"] == ["tv", "default"]


def test_o_provedor_de_token_acompanha_a_tentativa():
    # Mesmo anonima a tentativa leva o provedor quando ele existe: o `default`
    # que vem atras do `tv` pode precisar dele.
    args = yt_clients.args_da_tentativa("HD", True, False, "", "/opt/gen.js")
    assert args["youtubepot-bgutilscript"] == {"script_path": ["/opt/gen.js"]}
    sem = yt_clients.args_da_tentativa("HD", True, False, "", "")
    assert "youtubepot-bgutilscript" not in sem


def test_o_main_nao_volta_a_ter_uma_lista_so():
    """O `main.py` monta os args POR TENTATIVA, nunca uma vez para todas.

    Era assim que `default,mweb` (medida para a conta) chegava ao caminho sem
    conta. O `main.py` nao e importavel no CI -- pede torch --, entao a
    garantia e sobre a arvore sintatica.
    """
    import ast
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    arvore = ast.parse((raiz / "main.py").read_text(encoding="utf-8"))
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "append"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "attempts"]
    assert chamadas, "o laco que monta as tentativas sumiu do main.py"
    for chamada in chamadas:
        fontes = {ast.unparse(a) for a in ast.walk(chamada)
                  if isinstance(a, ast.Call) and isinstance(a.func, ast.Name)}
        assert any(f.startswith("_args_da_tentativa(") for f in fontes), ast.unparse(chamada)


def test_o_probe_nao_tem_lista_propria():
    """O probe mede pela MESMA lista pela qual o download baixa.

    Ate 22-set-2026 ele nao passava `player_client` nenhum, com um comentario
    dizendo que o padrao do yt-dlp "ainda serve HD sem PO token". Quando o
    padrao parou de servir, o probe passou a medir uma coisa e o download a
    baixar outra -- que e exatamente o que este modulo existe para impedir.
    """
    import ast
    import pathlib
    fonte = (pathlib.Path(__file__).resolve().parent.parent
             / "quality_probe.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    chamadas = {ast.unparse(n.func) for n in ast.walk(arvore)
                if isinstance(n, ast.Call)}
    assert any(c.startswith("yt_clients.") for c in chamadas), \
        "o quality_probe parou de perguntar ao yt_clients"
    # Nenhum nome de cliente escrito a mao: seria a segunda lista de volta.
    literais = {n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant)
                and isinstance(n.value, str)}
    for cru in ("player_client", "mweb", "tv_downgraded", "web_safari"):
        assert cru not in literais, cru
