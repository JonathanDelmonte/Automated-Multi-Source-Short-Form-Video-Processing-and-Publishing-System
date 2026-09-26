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
