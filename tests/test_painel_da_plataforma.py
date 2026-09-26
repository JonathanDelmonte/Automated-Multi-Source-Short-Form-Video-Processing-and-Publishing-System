"""O painel organizado por canal (Fase 7, etapa 7.1).

JS nao roda no CI do backend; estes guardas leem a fonte, como os de
`test_log_com_hora`, e o endereco das telas roda no `node` de verdade (sem
node, pula) -- `lib/endereco.js` existe separado de `lib/rota.js` justamente
para nao importar o React, que o job do backend nao instala.

O que eles guardam:

- **O mapa do plano inteiro tem lugar**: cada item da navegacao tem pagina, e
  nenhuma pagina fica sem item. Um item sem rota cairia no Inicio sem erro.
- **A aprovacao nasce sem resposta** (o autor, 26-set-2026: "quem escolhe isso
  e o usuario"). Um `useState(false)` aqui decidiria por ele sem ninguem ver.
- **O canal viaja com o video**: o Criar manda o `channel_id`.
- **Nenhuma dependencia nova no painel**: o botao "atualizar agora" do Docker
  recusa mudanca no `package.json` (reconstruir a imagem, 40 minutos).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
APP = (SRC / "App.jsx").read_text(encoding="utf-8")

NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _fonte(*partes):
    return (SRC.joinpath(*partes)).read_text(encoding="utf-8")


def _ids_da_navegacao():
    bloco = APP[APP.index("const NAV = ["):APP.index("].map((item, i)")]
    return re.findall(r"\{ id: '([a-z]+)'", bloco)


def test_o_mapa_do_plano_esta_na_navegacao():
    """As dez partes de "O mapa do aplicativo" (docs/PLANO-DA-PLATAFORMA.md)."""
    assert _ids_da_navegacao() == [
        "inicio", "canais", "criar", "projetos", "agenda", "analises",
        "ferramentas", "frota", "configuracoes", "ajuda",
    ]


def test_cada_item_da_navegacao_tem_pagina():
    for secao in _ids_da_navegacao():
        if secao == "inicio":
            assert "default: pagina = <Inicio />;" in APP
            continue
        assert f"case '{secao}':" in APP, f"'{secao}' esta na navegacao e cai no Inicio"


def test_toda_pagina_importada_existe():
    for nome in re.findall(r"from './pages/(\w+)'", APP):
        assert (SRC / "pages" / f"{nome}.jsx").exists(), nome


def test_as_sete_abas_do_canal():
    canal = _fonte("pages", "Canal.jsx")
    bloco = canal[canal.index("const ABAS = ["):canal.index("];", canal.index("const ABAS = ["))]
    assert re.findall(r"id: '(\w+)'", bloco) == [
        "visao", "criar", "automacao", "agenda", "publicados", "analises", "ajustes"]


def test_a_aprovacao_nasce_sem_resposta():
    formulario = _fonte("components", "FormularioDoCanal.jsx")
    assert "useState(editando ? !!canal.requires_approval : null)" in formulario
    assert "disabled={salvando || !nome.trim() || aprovacao === null}" in formulario


def test_o_canal_viaja_com_o_video():
    assert "channel_id: canalId || null," in _fonte("lib", "processar.js")
    assert "enviarVideo(dados, { apiKey, forcarBaixaQualidade: forcar, canalId: canalValido })" \
        in _fonte("pages", "Criar.jsx")


def test_os_canais_esperam_a_sessao():
    """O hook roda antes da tela de entrada; sem esperar a sessao, numa
    instalacao com senha a lista nasceria de um 401 e ficaria em erro depois do
    login."""
    assert "const canais = useListaDeCanais(sessaoPronta);" in APP
    assert "const sessaoPronta = configCarregada && (!authAtiva || isSignedIn);" in APP
    assert "useEffect(() => { if (ativo) carregar(); }, [ativo, carregar]);" in _fonte("lib", "canais.js")


def test_o_canal_manda_json_ao_motor():
    """O motor recusa com 415 o que nao vier como JSON (`_exigir_json`)."""
    canais = _fonte("lib", "canais.js")
    assert "{ 'Content-Type': 'application/json' }" in canais


def test_nenhuma_dependencia_nova_no_painel():
    pacote = json.loads((RAIZ / "dashboard" / "package.json").read_text(encoding="utf-8"))
    assert sorted(pacote["dependencies"]) == [
        "@remotion/media", "@remotion/media-utils", "@remotion/player",
        "@remotion/web-renderer", "lucide-react", "react", "react-dom",
        "remotion", "zod",
    ], ("dependencia nova no painel: o botao 'atualizar agora' do Docker recusa "
        "mudanca no package.json -- ver lib/rota.js")


def _endereco(expressao):
    modulo = (SRC / "lib" / "endereco.js").as_uri()
    codigo = (
        f"import * as e from {json.dumps(modulo)};\n"
        f"const r = {expressao};\n"
        "console.log(JSON.stringify(r, (k, v) => v instanceof URLSearchParams"
        " ? Object.fromEntries(v) : v));\n"
    )
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


@precisa_node
@pytest.mark.parametrize("hash_, partes, busca", [
    ("#/canais/abc/agenda", ["canais", "abc", "agenda"], {}),
    ("#/criar/cortes?canal=xyz", ["criar", "cortes"], {"canal": "xyz"}),
    ("#/", [], {}),
    ("", [], {}),
    # O link da marca nas versoes de antes: o App o manda para o Inicio.
    ("#app", ["app"], {}),
    ("#/projetos/a%20b", ["projetos", "a b"], {}),
    # Um % solto nao derruba a leitura.
    ("#/canais/%E0%A4%A", ["canais", "%E0%A4%A"], {}),
])
def test_o_endereco_das_telas(hash_, partes, busca):
    assert _endereco(f"e.lerRota({json.dumps(hash_)})") == {"partes": partes, "busca": busca}


@precisa_node
def test_o_href_de_uma_tela():
    assert _endereco("[e.hrefDe('/canais'), e.hrefDe('canais'), e.hrefDe('#/x')]") == \
        ["#/canais", "#/canais", "#/x"]


# --------------------------------------------------------------------------- #
# A fila com os galhos (etapa 7.3)
# --------------------------------------------------------------------------- #

def _publicacoes(expressao):
    modulo = (SRC / "lib" / "publicacoes.js").as_uri()
    codigo = (
        f"import * as p from {json.dumps(modulo)};\n"
        f"console.log(JSON.stringify({expressao}));\n"
    )
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


@precisa_node
def test_os_galhos_ficam_juntos_pelo_corte():
    fila = [
        {"id": "a", "clip": {"id": "c1"}, "account": {"platform": "youtube"}},
        {"id": "b", "clip": {"id": "c2"}, "account": {"platform": "youtube"}},
        {"id": "c", "clip": {"id": "c1"}, "account": {"platform": "tiktok"}},
    ]
    grupos = _publicacoes(f"p.agruparPorCorte({json.dumps(fila)})")
    assert [(g["chave"], [x["id"] for x in g["galhos"]]) for g in grupos] == \
        [("c1", ["a", "c"]), ("c2", ["b"])]


@precisa_node
def test_dentro_do_corte_a_ordem_e_a_das_plataformas():
    fila = [{"id": i, "clip": {"id": "c"}, "account": {"platform": pl}}
            for i, pl in (("1", "instagram"), ("2", "tiktok"), ("3", "youtube"))]
    (grupo,) = _publicacoes(f"p.agruparPorCorte({json.dumps(fila)})")
    assert [g["account"]["platform"] for g in grupo["galhos"]] == \
        ["youtube", "tiktok", "instagram"]


@precisa_node
@pytest.mark.parametrize("destino, corpo", [
    ("canal:X", {"job_id": "J", "channel_id": "X"}),
    ("conta:Y", {"job_id": "J", "account_id": "Y"}),
    ("", None),
    ("canal:", None),
    ("driver:browser", None),
])
def test_o_destino_vira_canal_ou_conta_e_nunca_driver(destino, corpo):
    """O ADR-010: o painel manda a conta (ou o canal), nunca o driver."""
    assert _publicacoes(f"p.corpoDoDestino('J', {json.dumps(destino)})") == corpo


@precisa_node
@pytest.mark.parametrize("pub, comeco", [
    ({"status": "scheduled", "scheduled_at": None}, "esperando você postar"),
    ({"status": "scheduled", "scheduled_at": "2026-09-27T14:07:00+00:00"}, "agendado · "),
    ({"status": "published", "posted_at": "2026-09-26T17:00:00+00:00"}, "publicado · "),
    ({"status": "published"}, "publicado"),
    ({"status": "failed"}, "falhou"),
])
def test_o_estado_de_cada_galho_em_palavras(pub, comeco):
    assert _publicacoes(f"p.estadoDoGalho({json.dumps(pub)}).texto").startswith(comeco)


def test_o_ja_publiquei_manda_o_link_como_json():
    fila = _fonte("components", "FilaDePublicacoes.jsx")
    assert "`/api/publicacoes/${publicacao.id}/publicado`" in fila
    assert "JSON.stringify(comLink ? { url: link.trim() } : {})" in fila
    assert "'Content-Type': 'application/json'" in fila


def test_o_projeto_publica_no_canal_dele():
    projeto = _fonte("pages", "Projeto.jsx")
    assert "canalDoProjeto={canalId}" in projeto
    assert "projeto={jobId}" in projeto


# --------------------------------------------------------------------------- #
# "Conectar YouTube" (etapa 7.3)
# --------------------------------------------------------------------------- #

def _conexoes(expressao):
    modulo = (SRC / "lib" / "conexoes.js").as_uri()
    codigo = (
        f"import * as c from {json.dumps(modulo)};\n"
        f"console.log(JSON.stringify({expressao}));\n"
    )
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


@precisa_node
@pytest.mark.parametrize("base, pagina, origem", [
    # O site do Cloudflare fala com o motor direto: a volta e o motor.
    ("http://localhost:8000", "https://virtu-clips.zirtuno.workers.dev", "http://localhost:8000"),
    ("http://localhost:8001", "https://virtu-clips.zirtuno.workers.dev", "http://localhost:8001"),
    # O painel do Docker usa a API relativa: a volta e o proprio painel.
    ("", "http://localhost:5175", "http://localhost:5175"),
])
def test_a_volta_vai_para_onde_o_navegador_fala_com_o_motor(base, pagina, origem):
    assert _conexoes(f"c.origemDoMotor({json.dumps(base)}, {json.dumps(pagina)})") == origem


@precisa_node
@pytest.mark.parametrize("origem, pode", [
    ("http://localhost:8000", True),
    ("http://127.0.0.1:5175", True),
    ("http://192.168.0.10:5175", False),
    ("https://virtu-clips.zirtuno.workers.dev", False),
])
def test_so_localhost_conecta(origem, pode):
    assert _conexoes(f"c.voltaPossivel({json.dumps(origem)})") is pode


@precisa_node
@pytest.mark.parametrize("busca, volta", [
    ("?state=abc&code=xyz&scope=s", True),
    ("?state=abc&error=access_denied", True),
    ("?canal=x", False),
    ("", False),
])
def test_reconhece_a_volta_do_google(busca, volta):
    assert _conexoes(f"c.ehVoltaDoGoogle({json.dumps(busca)})") is volta


@precisa_node
def test_toda_recusa_do_motor_tem_frase_na_tela():
    """O motor devolve codigos; a tela escreve a frase. Um codigo novo sem
    frase viraria "Nao deu para conectar" sem dizer o que fazer."""
    fontes = "".join((RAIZ / f).read_text(encoding="utf-8")
                     for f in ("conexoes.py", "aplicativos.py", "app.py"))
    codigos = set(re.findall(r'ConexaoError\("(\w+)"', fontes))
    codigos |= set(re.findall(r'_erro_de_conexao\("(\w+)"', fontes))
    codigos |= set(re.findall(r'"codigo": "(\w+)"', fontes))
    codigos |= set(re.findall(r'AplicativoInvalido\("(\w+)"', fontes))
    # O que a conferencia com o Google devolve e o motor repassa como `erro`.
    codigos |= set(re.findall(r'return "(\w+)"', (RAIZ / "aplicativos.py").read_text(encoding="utf-8")))
    codigos -= {"ok", "incerto"}
    # `campo` e erro de programa (um campo que o painel nunca manda), nao de
    # quem usa.
    codigos.discard("campo")
    assert {"expirou", "volta", "sem_aplicativo", "formato", "cliente"} <= codigos, \
        "a varredura nao achou os codigos"
    frases = set(_conexoes("Object.keys(c.MENSAGENS_DO_CADASTRO)"))
    assert codigos - frases == set()


def test_a_aba_do_google_abre_antes_de_esperar_o_motor():
    """Aberta depois de um `await`, o bloqueador de pop-up a trataria como
    propaganda."""
    fonte = _fonte("components", "ConexaoDaConta.jsx")
    corpo = fonte[fonte.index("const conectar = async"):fonte.index("const desconectar")]
    assert corpo.index("window.open(") < corpo.index("await apiFetch(")
    assert "body: JSON.stringify({ tipo, volta: origem })" in corpo


def test_a_volta_no_painel_vem_antes_da_tranca():
    """A volta vale pelo `state` do pedido, nao pela sessao."""
    assert APP.index("return <VoltaDoGoogle />;") < APP.index("return <Tranca />;")


# --------------------------------------------------------------------------- #
# O TikTok (etapa 7.3c)
# --------------------------------------------------------------------------- #

@precisa_node
def test_a_tela_conecta_o_que_o_motor_conecta():
    """Uma plataforma que a tela nao conhece nao ganha botao; uma que o motor
    nao conecta daria "plataforma" no clique. As duas listas andam juntas."""
    conexoes = pytest.importorskip("conexoes")
    assert _conexoes("c.TIPOS_DE") == {p: list(t) for p, t in conexoes.TIPOS_DE.items()}
    assert _conexoes("c.APLICATIVO_DE") == conexoes.APLICATIVO_DE
    descricoes = _conexoes("c.DESCRICAO_DOS_TIPOS")
    for plataforma, tipos in conexoes.TIPOS_DE.items():
        for tipo in tipos:
            assert descricoes[plataforma][tipo]["botao"], (plataforma, tipo)


@precisa_node
@pytest.mark.parametrize("origem, plataforma, pode", [
    ("http://[::1]:8000", "youtube", True),
    # O Login Kit for Desktop do TikTok so aceita localhost e 127.0.0.1, sempre
    # com porta -- o mesmo que `conexoes.volta_de` recusa no motor.
    ("http://[::1]:8000", "tiktok", False),
    ("http://localhost", "tiktok", False),
    ("http://localhost:8001", "tiktok", True),
    ("http://127.0.0.1:5175", "tiktok", True),
])
def test_a_volta_do_tiktok_e_mais_estreita(origem, plataforma, pode):
    assert _conexoes(f"c.voltaPossivel({json.dumps(origem)}, {json.dumps(plataforma)})") is pode
    conexoes = pytest.importorskip("conexoes")
    try:
        conexoes.volta_de(origem, plataforma)
        aceita = True
    except conexoes.ConexaoError:
        aceita = False
    assert aceita is pode, "a tela e o motor discordam sobre essa volta"


@precisa_node
def test_a_frase_diz_quem_mostrou_a_tela():
    """Mandar quem cancelou no TikTok a pagina de permissoes do Google seria
    mandar ao lugar errado."""
    for codigo in ("recusada", "troca", "volta"):
        tiktok = _conexoes(f"c.mensagemDe({json.dumps(codigo)}, {{ plataforma: 'tiktok' }})")
        google = _conexoes(f"c.mensagemDe({json.dumps(codigo)})")
        assert "TikTok" in tiktok and "Google" not in tiktok, codigo
        assert "Google" in google, codigo
    assert "myaccount.google.com" not in _conexoes("c.mensagemDe('sem_refresh', { plataforma: 'tiktok' })")
    assert "{" not in "".join(_conexoes(
        "Object.keys(c.MENSAGENS).map((k) => c.mensagemDe(k, { plataforma: 'tiktok' }))"))


@precisa_node
@pytest.mark.parametrize("plataforma, campo, trecho", [
    ("google", "client_id", ".apps.googleusercontent.com"),
    ("google", "client_secret", "GOCSPX-"),
    ("tiktok", "client_key", "client key do TikTok"),
    ("tiktok", "client_secret", "client secret do TikTok"),
])
def test_o_formato_errado_diz_qual_campo(plataforma, campo, trecho):
    frase = _conexoes(f"c.mensagemDoCadastro('formato', {{ plataforma: {json.dumps(plataforma)}, "
                      f"campo: {json.dumps(campo)} }})")
    assert trecho in frase


@precisa_node
@pytest.mark.parametrize("prontos, plataforma, situacao", [
    ({"google": True, "tiktok": False}, "youtube", "pronto"),
    ({"google": True, "tiktok": False}, "tiktok", "falta"),
    # O site e publicado antes de o programa ser atualizado: o motor da 7.3b
    # nao conhece o TikTok, e mandar cadastrar levaria a uma pagina sem o
    # cartao dele.
    ({"google": True}, "tiktok", "motor-antigo"),
    ({"google": True, "tiktok": True}, "instagram", "motor-antigo"),
    # Ainda nao se sabe (ou motor de antes da 7.3): nada de botao.
    (None, "youtube", None),
])
def test_o_cadastro_que_serve_a_cada_conta(prontos, plataforma, situacao):
    assert _conexoes(f"c.situacaoDoAplicativo({json.dumps(prontos)}, {json.dumps(plataforma)})") \
        == situacao


@precisa_node
def test_todo_driver_do_motor_tem_nome_na_tela():
    """Um driver sem linha aparece cru ("tiktok-api") no cartao da conta."""
    publishers = pytest.importorskip("publishers")
    modulo = (SRC / "lib" / "plataformas.js").as_uri()
    codigo = (f"import * as p from {json.dumps(modulo)};\n"
              "console.log(JSON.stringify(Object.keys(p.DRIVERS)));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo], capture_output=True,
                           encoding="utf-8", check=True, timeout=60).stdout
    assert set(publishers.DRIVER_IDS) <= set(json.loads(saida))


def test_o_cartao_do_tiktok_manda_cadastrar_os_dois_enderecos():
    """O TikTok compara a volta com o que foi cadastrado no app; o `*` e a
    porta, e sem os dois hosts o painel aberto em 127.0.0.1 nao conectaria."""
    cadastro = _fonte("components", "CadastroDoAplicativo.jsx")
    assert "http://localhost:*/" in cadastro and "http://127.0.0.1:*/" in cadastro
    assert "plataforma: 'tiktok'" in cadastro


def test_a_conta_do_tiktok_ganha_o_botao_nas_duas_telas():
    publicacoes = _fonte("components", "PublicacoesTab.jsx")
    canal = _fonte("pages", "Canal.jsx")
    assert "c.platform === 'youtube'" not in publicacoes
    assert "{c.conexao && (TIPOS_DE[c.platform] || c.platform === 'instagram') && (" in publicacoes
    assert "aplicativo={situacaoDoAplicativo(aplicativos.prontos, c.platform)}" in publicacoes
    assert "aplicativo={situacaoDoAplicativo(aplicativos.prontos, p)}" in canal


def test_o_programa_antigo_manda_atualizar_e_nao_cadastrar():
    """Com o programa de antes da 7.3c, o cartao do TikTok nao existe nas
    Configuracoes: mandar "cadastre o app do TikTok" seria um beco."""
    conexao = _fonte("components", "ConexaoDaConta.jsx")
    cadastro = _fonte("components", "CadastroDoAplicativo.jsx")
    assert "aplicativo === 'motor-antigo'" in conexao
    assert "aplicativo === 'falta'" in conexao
    assert "atualize o programa deste computador" in conexao
    assert "estados[app.plataforma] === undefined ? (" in cadastro
    assert "Atualize o\n            programa" in cadastro or "Atualize o programa" in cadastro


# --------------------------------------------------------------------------- #
# O Instagram na versao simples (etapa 7.3d)
# --------------------------------------------------------------------------- #

@precisa_node
@pytest.mark.parametrize("contas, esperado", [
    # Sem conta, o pacote serve assim mesmo: as tres.
    ([], ["youtube", "tiktok", "instagram"]),
    ([{"platform": "instagram"}, {"platform": "youtube"}], ["youtube", "instagram"]),
    ([{"platform": "instagram"}], ["instagram"]),
])
def test_o_pacote_oferece_as_plataformas_das_contas(contas, esperado):
    assert _publicacoes(f"p.plataformasDoPacote({json.dumps(contas)})") == esperado


@precisa_node
def test_o_pacote_pede_a_plataforma_escolhida():
    """Ate a 7.3d o painel so baixava o do YouTube: a legenda do Instagram (e a
    do TikTok) existia no motor e nunca chegava a ninguem."""
    assert _publicacoes("p.caminhoDoPacote('2026-09-26', 'instagram')") == \
        "/api/publicacoes/pacote?dia=2026-09-26&plataforma=instagram"
    assert _publicacoes("p.caminhoDoPacote('2026-09-26')").endswith("&plataforma=youtube")
    aba = _fonte("components", "PublicacoesTab.jsx")
    assert "getApiUrl(caminhoDoPacote(dia, pacotePara))" in aba
    assert "/api/publicacoes/pacote?dia=" not in aba


def test_a_conta_do_instagram_diz_o_caminho_dela():
    """Sem botao de conectar, a conta do Instagram diria nada -- e "por que
    nao sobe sozinho?" ficaria sem resposta na tela."""
    conexao = _fonte("components", "ConexaoDaConta.jsx")
    bloco = conexao[conexao.index("if (plataforma === 'instagram') {"):]
    bloco = bloco[:bloco.index("if (!TIPOS_DE[plataforma]) return null;")]
    assert "hrefDe('/agenda')" in bloco
    assert "pacote do dia" in bloco and "5 hashtags" in bloco and "já publiquei" in bloco



def test_a_grade_de_cortes_se_divide_pelo_espaco_que_sobra():
    """Com o menu lateral da 7.1, o `xl:grid-cols-2` dava cartoes de ~330 px
    numa tela de 1280, e os rotulos dos botoes se sobrepunham (achado na
    conferencia da 7.3e). A grade conta o espaco do container, nao a janela."""
    projeto = _fonte("pages", "Projeto.jsx")
    grade = next(linha for linha in projeto.splitlines() if "grid gap-4 pb-10" in linha)
    assert "grid-cols-[repeat(auto-fill,minmax(min(100%,24rem),1fr))]" in grade
    assert "xl:grid-cols-2" not in grade
