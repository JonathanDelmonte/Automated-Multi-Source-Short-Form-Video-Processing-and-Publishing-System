"""A serie em partes no painel (etapa 7.6).

As regras puras rodam no `node` de verdade (sem node, pula), e as que tem par
no motor sao conferidas contra ele: o numero de partes que o formulario preve
e o que o `series.py` corta; os estilos do rotulo sao os do gancho; a live da
Twitch que o formulario reconhece e a que o motor grava em bloco. Duas listas
que andam juntas so andam juntas se um teste olhar as duas.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import series

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(modulo, expressao):
    caminho = (SRC / "lib" / modulo).as_uri()
    codigo = (f"import * as m from {json.dumps(caminho)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return SRC.joinpath(*partes).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# O formulario e o motor falam das mesmas coisas
# --------------------------------------------------------------------------- #

@precisa_node
def test_a_previsao_de_partes_e_a_conta_do_motor():
    casos = [(3600, 60, None, None), (150, 60, None, None), (90, 60, None, None),
             (3725, 90, 300, 3300), (61, 60, None, None), (7200, 30, None, 5000),
             (500, 45, 480, None)]
    for duracao, alvo, inicio, fim in casos:
        spec = {"duracao_parte_s": alvo, "inicio_s": inicio, "fim_s": fim}
        esperado = series.quantas_partes(duracao, spec)
        visto = _js("serie.js", f"m.quantasPartes({duracao}, {alvo}, {json.dumps(inicio)}, {json.dumps(fim)})")
        assert visto == esperado, (duracao, alvo, inicio, fim)


@precisa_node
def test_as_escolhas_do_formulario_cabem_no_motor():
    duracoes = _js("serie.js", "m.DURACOES")
    assert all(series.ALVO_MIN_S <= d <= series.ALVO_MAX_S for d in duracoes)
    assert _js("serie.js", "m.DURACAO_PADRAO") == series.ALVO_PADRAO_S
    assert [r["value"] for r in _js("serie.js", "m.ROTULOS")] == list(series.ROTULOS)
    assert [e["value"] for e in _js("serie.js", "m.ESTILOS")] == list(series.ESTILOS_DO_ROTULO)
    assert max(_js("serie.js", "m.BLOCOS")) <= series.BLOCO_MAX_MIN
    assert _js("serie.js", "m.BLOCO_PADRAO") == series.BLOCO_PADRAO_MIN
    assert _js("serie.js", "m.MAX_PARTES") == series.MAX_PARTES


@precisa_node
def test_o_pedido_do_formulario_passa_no_motor():
    corpo = _js("serie.js", "m.corpoDaSerie({nome: '  Live   do Fulano ', duracao: 90, "
                            "rotulo: 'sempre', estilo: 'yellow', inicio: '1:30', fim: '1:02:30', "
                            "agendar: true, bloco: 120})")
    assert corpo == {"duracao_parte_s": 90, "rotulo": "sempre", "estilo_rotulo": "yellow",
                     "agendar": True, "nome": "Live do Fulano", "inicio_s": 90,
                     "fim_s": 3750, "bloco_min": 120}
    spec = series.normalizar_pedido(corpo)
    assert spec["nome"] == "Live do Fulano" and spec["fim_s"] == 3750
    # O minimo que o formulario manda tambem passa.
    series.normalizar_pedido(_js("serie.js", "m.corpoDaSerie({})"))


@precisa_node
@pytest.mark.parametrize("url", [
    "https://www.twitch.tv/gaules", "https://twitch.tv/alanzoka/", "https://m.twitch.tv/gaules",
    "https://www.twitch.tv/videos/123456789", "https://www.twitch.tv/gaules/clip/AbcDef",
    "https://clips.twitch.tv/AbcDef", "https://www.twitch.tv/gaules/videos",
    "https://www.youtube.com/watch?v=abc", "nao e link",
])
def test_a_live_no_ar_e_a_que_o_motor_grava_em_bloco(url):
    sources = pytest.importorskip("sources")
    try:
        motor = sources.resolve(url).id == "twitch-live"
    except sources.UnknownSource:
        motor = False
    # `/<canal>/videos` e recusada pelo motor (seria o canal inteiro): la nao
    # ha bloco a perguntar.
    if url.rstrip("/").endswith("/videos"):
        motor = False
    assert _js("serie.js", f"m.ehLiveDaTwitch({json.dumps(url)})") is motor


def test_os_estilos_sao_os_do_gancho():
    hooks = pytest.importorskip("hooks")
    assert set(series.ESTILOS_DO_ROTULO) == set(hooks.HOOK_STYLES)


# --------------------------------------------------------------------------- #
# As regras puras
# --------------------------------------------------------------------------- #

@precisa_node
@pytest.mark.parametrize("texto, segundos", [
    ("", None), ("  ", None), ("90", 90), ("1:30", 90), ("1:02:30", 3750), ("0:05", 5),
])
def test_ler_tempo(texto, segundos):
    assert _js("serie.js", f"m.lerTempo({json.dumps(texto)})") == segundos


@precisa_node
@pytest.mark.parametrize("texto", ["1:75", "abc", "1:2:3:4", "-5", "1.5"])
def test_tempo_torto(texto):
    # NaN vira null no JSON; o que importa e nao virar um numero.
    assert _js("serie.js", f"Number.isNaN(m.lerTempo({json.dumps(texto)}))") is True


@precisa_node
def test_a_previsao_e_os_problemas():
    assert _js("serie.js", "m.previsao(3600, 60)") == {
        "partes": 60, "texto": "60 partes de cerca de 1 min"}
    assert "limite" in _js("serie.js", "m.previsao(36000, 20)")["erro"]
    assert "fora do vídeo" in _js("serie.js", "m.previsao(100, 60, 200)")["erro"]
    assert _js("serie.js", "m.previsao(null, 60)") is None
    assert "curto" in _js("serie.js", "m.problemaDoTrecho('1:00', '1:10')")
    assert "1:30" in _js("serie.js", "m.problemaDoTrecho('abc', '')")
    assert _js("serie.js", "m.problemaDoTrecho('', '')") is None


@precisa_node
def test_textos():
    assert _js("serie.js", "m.duracaoEmTexto(90)") == "1 min 30 s"
    assert _js("serie.js", "m.duracaoEmTexto(30)") == "30 s"
    assert _js("serie.js", "m.formatarTempo(3750)") == "1:02:30"
    assert _js("serie.js", "m.formatarTempo(125)") == "2:05"
    assert _js("serie.js", "m.textoDaSerie({partes: 60, duracao_parte_s: 60})") == \
        "série · 60 partes de ~1 min"
    assert _js("serie.js", "m.textoDaSerie(null)") == ""


# --------------------------------------------------------------------------- #
# O indice estavel dos cortes
# --------------------------------------------------------------------------- #

@precisa_node
def test_o_indice_vem_do_corte_e_nao_da_posicao():
    clips = [{"clip_index": 0, "t": "a"}, {"clip_index": 1, "t": "b"}, {"clip_index": 3, "t": "d"}]
    assert _js("cortes.js", f"m.corteDoIndice({json.dumps(clips)}, 3).t") == "d"
    assert _js("cortes.js", f"m.corteDoIndice({json.dumps(clips)}, 2) ?? null") is None
    trocados = _js("cortes.js", f"m.comCorteTrocado({json.dumps(clips)}, 3, (c) => ({{...c, t: 'D'}}))")
    assert [c["t"] for c in trocados] == ["a", "b", "D"]
    # Motor de antes da 7.6: sem `clip_index`, a posicao e o indice.
    assert _js("cortes.js", "m.corteDoIndice([{t: 'x'}, {t: 'y'}], 1).t") == "y"


@precisa_node
def test_a_ordem_da_tela():
    cortes = [{"clip_index": 0, "predicted_score": 40}, {"clip_index": 2, "predicted_score": 90}]
    assert [c["index"] for c in _js("cortes.js", f"m.naOrdemDaTela({json.dumps(cortes)})")] == [2, 0]
    partes = [{"clip_index": 2, "serie": {"parte": 3}}, {"clip_index": 0, "serie": {"parte": 1}},
              {"clip_index": 1, "serie": {"parte": 2}}]
    assert [c["index"] for c in _js("cortes.js", f"m.naOrdemDaTela({json.dumps(partes)})")] == [0, 1, 2]


def test_a_tela_do_projeto_usa_o_indice_do_corte():
    """Todo lugar que a tela do projeto pega um corte pelo indice passa pelo
    `lib/cortes.js` -- `results.clips[indice]` e o defeito de volta."""
    projeto = _fonte("pages", "Projeto.jsx")
    assert "results?.clips?.[editingClip]" not in projeto
    assert "results.clips[editingClip]" not in projeto
    assert "results?.clips?.[reframingClip]" not in projeto
    assert "clip_index: indiceDoCorte(clips[i], i)," in projeto
    assert "naOrdemDaTela(results?.clips)" in projeto


# --------------------------------------------------------------------------- #
# A fila e o Criar
# --------------------------------------------------------------------------- #

@precisa_node
def test_a_parte_parada_diz_por_que():
    estado = _js("publicacoes.js", "m.estadoDoGalho({status: 'scheduled', scheduled_at: "
                                   "'2026-09-27T14:00:00Z', parada: {parte: 3, motivo: 'falhou'}})")
    assert estado == {"texto": "parada: a parte 3 falhou", "cor": "text-danger"}
    presa = _js("publicacoes.js", "m.estadoDoGalho({status: 'scheduled', scheduled_at: 'x', "
                                  "parada: {parte: 2, motivo: 'subindo'}}).texto")
    assert presa == "parada: a parte 2 ficou presa subindo"


YT = {"id": "yt", "platform": "youtube", "handle": "@a"}
TT = {"id": "tt", "platform": "tiktok", "handle": "@a"}


def _parte(n, conta, status, quando="2026-10-05T12:00:00Z", parada=None, total=5):
    return {"id": f"{conta['id']}{n}", "status": status, "account": conta,
            "scheduled_at": quando if status == "scheduled" else None, "parada": parada,
            "clip": {"id": f"c{n}", "title": f"Live - Parte {n}", "job_id": "J"},
            "serie": {"id": "S", "parte": n, "partes": total, "nome": "Live"}}


def _fila(publicacoes, filtrada=False):
    return _js("publicacoes.js", f"m.agruparNaFila({json.dumps(publicacoes)}, "
                                 f"{{filtrada: {json.dumps(filtrada)}}}).map((i) => i.tipo === 'serie' "
                                 "? {tipo: i.tipo, partes: i.grupos.map((g) => g.serie.parte), "
                                 "contas: i.contas.map((c) => ({p: c.conta.platform, contagem: c.contagem, "
                                 "texto: c.texto, cor: c.cor, foco: c.foco && c.foco.id}))} "
                                 ": {tipo: i.tipo, chave: i.grupo.chave})")


@precisa_node
def test_a_serie_e_um_item_so_na_fila():
    """Uma live de 1 hora eram 60 grupos na fila, e a parte que falhou -- a
    unica que pede alguem -- ficava no fim da pagina, depois de 57 "parada"."""
    solto = {"id": "x", "status": "scheduled", "scheduled_at": "2026-10-05T12:00:00Z",
             "account": YT, "clip": {"id": "solto", "title": "Um corte"}}
    fila = [solto]
    for n in (5, 4, 3, 2, 1):                   # a mais recente primeiro
        fila.append(_parte(n, TT, "published" if n <= 3 else "scheduled"))
        fila.append(_parte(n, YT, {1: "published", 2: "published", 3: "failed"}.get(n, "scheduled"),
                           parada={"parte": 3, "motivo": "falhou"} if n > 3 else None))
    corte, serie = _fila(fila)
    assert corte == {"tipo": "corte", "chave": "solto"}
    assert serie["partes"] == [1, 2, 3, 4, 5]
    youtube, tiktok = serie["contas"]
    assert youtube == {"p": "youtube", "contagem": "2 de 5 publicadas",
                       "texto": "a parte 3 falhou · 2 paradas atrás dela",
                       "cor": "text-danger", "foco": "yt3"}
    assert tiktok["contagem"] == "3 de 5 publicadas" and tiktok["foco"] is None
    assert tiktok["texto"].startswith("próxima: parte 4 · ")


@precisa_node
def test_o_resumo_da_serie_diz_o_que_pede_voce():
    feita = [_parte(n, YT, "published", total=3) for n in (1, 2, 3)]
    assert _fila(feita)[0]["contas"][0]["texto"] == "todas publicadas"
    pulada = [_parte(1, YT, "published", total=2), _parte(2, YT, "cancelled", total=2)]
    assert _fila(pulada)[0]["contas"][0]["texto"] == "terminou · 1 pulada"
    # Sem a conexao, cada parte vai para a fila manual quando chega a hora.
    manual = [_parte(1, YT, "published"), _parte(2, YT, "scheduled", quando=None),
              _parte(3, YT, "scheduled", quando=None), _parte(4, YT, "scheduled")]
    conta = _fila(manual)[0]["contas"][0]
    assert conta["texto"] == "a parte 2 espera você postar (e mais 1)" and conta["foco"] == "yt2"
    subindo = [_parte(1, YT, "publishing"),
               _parte(2, YT, "scheduled", parada={"parte": 1, "motivo": "subindo"})]
    assert _fila(subindo)[0]["contas"][0]["texto"] == "a parte 1 está subindo · 1 parada atrás dela"


@precisa_node
def test_na_fila_filtrada_a_serie_nao_termina():
    """Na aba Publicados, as outras partes so nao estao na lista: "todas
    publicadas" ou "2 de 60" seria mentira."""
    publicadas = [_parte(1, YT, "published"), _parte(2, YT, "published")]
    conta = _fila(publicadas, filtrada=True)[0]["contas"][0]
    assert conta["contagem"] == "2 partes" and conta["texto"] == ""
    # Na Agenda do canal sem a que falhou (um motor de antes), a parada diz
    # quem a segura; a proxima continua valendo.
    paradas = [_parte(4, YT, "scheduled", parada={"parte": 3, "motivo": "falhou"}),
               _parte(5, YT, "scheduled", parada={"parte": 3, "motivo": "falhou"})]
    conta = _fila(paradas, filtrada=True)[0]["contas"][0]
    assert conta["texto"] == "parada: a parte 3 falhou" and conta["cor"] == "text-danger"
    agendadas = [_parte(4, TT, "scheduled"), _parte(5, TT, "scheduled")]
    assert _fila(agendadas, filtrada=True)[0]["contas"][0]["texto"].startswith("próxima: parte 4 · ")


def test_a_agenda_do_canal_mostra_o_que_falhou():
    """A que falhou segura as partes seguintes da serie: fora da aba Agenda,
    o canal dizia "parada" sem o botao que a destrava."""
    canal = _fonte("pages", "Canal.jsx")
    assert "const NA_FILA = ['scheduled', 'publishing', 'failed'];" in canal
    assert "status={NA_FILA}" in canal
    assert "[].concat(status).includes(p.status)" in _fonte("components", "PublicacoesTab.jsx")


def test_a_serie_nao_e_mais_em_breve():
    tipos = _fonte("components", "TiposDeCriacao.jsx")
    bloco = tipos[tipos.index("id: 'serie'"):tipos.index("id: 'longo'")]
    assert "etapa:" not in bloco
    criar = _fonte("pages", "Criar.jsx")
    assert "serie: { titulo" not in criar
    assert "<SerieInput" in criar
    # A serie nao pede chave de IA: nenhuma IA escolhe trecho.
    assert "if (keysMissing && !dados.serie)" in criar


def test_a_serie_so_agenda():
    """"Publicar agora" soltaria as partes todas juntas; a serie sai na ordem."""
    publicacoes = _fonte("components", "PublicacoesTab.jsx")
    assert "{!ehSerie && (" in publicacoes
    assert "serie={!!serie}" in _fonte("pages", "Projeto.jsx")


def test_a_serie_vai_no_envio():
    processar = _fonte("lib", "processar.js")
    assert "serie: dados.serie || null," in processar
    assert "typeof v === 'object' ? JSON.stringify(v) : v" in processar


def test_a_fila_tem_tentar_de_novo_e_pular():
    fila = _fonte("components", "FilaDePublicacoes.jsx")
    assert "/api/publicacoes/${p.id}/tentar" in fila
    assert "pular esta parte" in fila
    assert "agruparNaFila(publicacoes, { filtrada })" in fila
    assert "filtrada={!!status}" in _fonte("components", "PublicacoesTab.jsx")


@precisa_node
def test_a_playlist_e_a_terceira_conexao_do_youtube():
    conexoes = pytest.importorskip("conexoes")
    assert _js("conexoes.js", "m.TIPOS_DE.youtube") == list(conexoes.TIPOS_DE["youtube"])
    assert _js("conexoes.js", "m.DESCRICAO_DOS_TIPOS.youtube.organizar.botao") == "conectar para playlists"
    assert "escopo_organizar" in _js("conexoes.js", "Object.keys(m.MENSAGENS)")
    assert "data-aviso-organizar" in _fonte("components", "ConexaoDaConta.jsx")
