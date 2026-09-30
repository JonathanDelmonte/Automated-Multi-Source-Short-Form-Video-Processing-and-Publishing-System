"""O video longo no painel (etapa 7.8).

As regras puras de `lib/criacao.js` e `lib/compilacao.js` rodam no `node` de
verdade (sem node, pula) e sao conferidas contra o motor: as cenas de cada
duracao sao as do `estilos.py`, os capitulos que a tela preve sao os que o
`capitulos.py` escreve, e os limites sao os do `compilacao.py`. O resto e a
forma das telas, lida na fonte.
"""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

import capitulos
import compilacao
import estilos

RAIZ = Path(__file__).resolve().parent.parent
SRC = RAIZ / "dashboard" / "src"
NODE = shutil.which("node")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")


def _js(expressao, modulo):
    caminho = (SRC / "lib" / modulo).as_uri()
    codigo = (f"import * as m from {json.dumps(caminho)};\n"
              f"console.log(JSON.stringify({expressao}));\n")
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


def _fonte(*partes):
    return SRC.joinpath(*partes).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# A tela e o motor falam das mesmas coisas
# --------------------------------------------------------------------------- #

@precisa_node
def test_os_numeros_do_episodio_sao_os_do_motor():
    assert _js("m.DURACAO_LONGA", "criacao.js") == {"min": estilos.DURACAO_LONGA_MIN,
                                                    "max": estilos.DURACAO_LONGA_MAX}
    assert _js("m.CENAS_LONGAS", "criacao.js") == {"min": estilos.CENAS_LONGAS_MIN,
                                                   "max": estilos.CENAS_LONGAS_MAX}
    assert _js("m.SEGUNDOS_POR_CENA_LONGA", "criacao.js") == estilos.SEGUNDOS_POR_CENA_LONGA
    assert _js("m.HISTORIA_MAX", "criacao.js") == estilos.HISTORIA_MAX
    # Cada minuto que a tela oferece da as mesmas cenas que o motor conta.
    minutos = list(range(estilos.DURACAO_LONGA_MIN // 60, estilos.DURACAO_LONGA_MAX // 60 + 1))
    vistas = _js(f"{json.dumps(minutos)}.map((x) => m.cenasDoLongo(x * 60))", "criacao.js")
    assert vistas == [estilos.cenas_do_longo(x * 60) for x in minutos]


@precisa_node
def test_os_limites_da_compilacao_sao_os_do_motor():
    assert _js("m.TRECHOS", "compilacao.js") == {"min": compilacao.TRECHOS_MIN,
                                                 "max": compilacao.TRECHOS_MAX}
    assert _js("m.DURACAO_MAX_S", "compilacao.js") == compilacao.DURACAO_MAX_S
    assert _js("m.TITULO_MAX", "compilacao.js") == compilacao.TITULO_MAX
    assert _js("m.DESCRICAO_MAX", "compilacao.js") == compilacao.DESCRICAO_MAX
    assert _js("m.CAPITULO_MINIMO_S", "compilacao.js") == capitulos.DURACAO_MINIMA_S
    valores = [0, 9.9, 59, 60, 75.5, 599, 3599, 3600, 3725]
    assert _js(f"{json.dumps(valores)}.map(m.tempo)", "compilacao.js") == \
        [capitulos.tempo(v) for v in valores]


@precisa_node
def test_os_capitulos_que_a_tela_preve_sao_os_que_o_motor_escreve():
    sorteio = random.Random(78)
    casos = []
    for _ in range(40):
        n = sorteio.randint(2, 9)
        casos.append([{"jobId": "j", "clip": i, "duracao_s": sorteio.choice([4, 8, 12, 30, 61]),
                       "titulo": sorteio.choice(["", f"Corte {i}"])} for i in range(n)])
    vistos = _js(f"{json.dumps(casos)}.map(m.capitulosPrevistos)", "compilacao.js")
    for caso, visto in zip(casos, vistos):
        plano = compilacao.planejar([{"arquivo": "a", "corte_inicio": 0,
                                      "corte_fim": c["duracao_s"], "titulo": c["titulo"]}
                                     for c in caso])
        assert [tuple(x) for x in visto] == compilacao.capitulos_do_plano(plano), caso


@precisa_node
def test_o_corpo_da_compilacao_e_o_que_o_motor_le():
    corpo = _js("m.corpoDaCompilacao({titulo: '  Os  melhores ', descricao: ' d ', canalId: 'c1', "
                "legenda: null, escolhidos: [{jobId: 'a', clip: 2}, {jobId: 'b', clip: 0}]})",
                "compilacao.js")
    assert corpo == {"titulo": "Os melhores", "descricao": "d", "legenda": "limpo",
                     "channel_id": "c1",
                     "cortes": [{"job_id": "a", "clip": 2}, {"job_id": "b", "clip": 0}]}
    assert "limpo" in estilos.LEGENDAS
    assert _js("m.porQueNaoMonta({titulo: '', escolhidos: [{duracao_s: 5}]})", "compilacao.js") == \
        "Escolha pelo menos 2 cortes."
    assert _js("m.porQueNaoMonta({titulo: ' ', escolhidos: [{duracao_s: 5}, {duracao_s: 5}]})",
               "compilacao.js").startswith("Dê um título")
    assert _js("m.porQueNaoMonta({titulo: 'T', escolhidos: [{duracao_s: 1900}, {duracao_s: 1900}]})",
               "compilacao.js").startswith("A compilação passaria de 60 minutos")
    assert _js("m.porQueNaoMonta({titulo: 'T', escolhidos: [{duracao_s: 5}, {duracao_s: 5}]})",
               "compilacao.js") is None


@precisa_node
def test_escolher_e_mudar_a_ordem():
    lista = _js("m.mover(m.alternar(m.alternar([], {jobId: 'a', clip: 0}), {jobId: 'a', clip: 1}), 1, -1)",
                "compilacao.js")
    assert [c["clip"] for c in lista] == [1, 0]
    assert _js("m.alternar([{jobId: 'a', clip: 0}], {jobId: 'a', clip: 0})", "compilacao.js") == []
    assert _js("m.mover([{clip: 0}], 0, -1)", "compilacao.js") == [{"clip": 0}]


@precisa_node
def test_o_corpo_do_episodio_e_as_frases():
    corpo = _js("m.corpoDoEpisodio({canalId: 'c1', ideia: ' a  chuva ', minutos: 5, "
                "historia: '  A  Lulu '})", "criacao.js")
    assert corpo == {"channel_id": "c1", "ideia": "a chuva", "formato": "longo",
                     "duracao_min": 5, "historia": "A Lulu"}
    assert "historia" not in _js("m.corpoDoEpisodio({canalId: 'c1', minutos: 2})", "criacao.js")
    cota = _js("m.fraseDaCotaDoEpisodio({imagens_hoje: 30}, 10)", "criacao.js")
    assert cota["ok"] is False and "tem 40 cenas" in cota["texto"]
    assert _js("m.fraseDaCotaDoEpisodio({imagens_hoje: 30}, 5)", "criacao.js")["ok"] is True
    assert _js("m.situacaoDoVideoLongo({configCarregada: true, videoLongoNoMotor: false})",
               "criacao.js") == "motor-antigo"
    proxima = _js("m.fraseDaHistoria({nome: 'A Lulu', ultimo: {episodio: 3, pronto: true}})",
                  "criacao.js")
    assert "episódio 4 de “A Lulu”" in proxima
    parada = _js("m.fraseDaHistoria({nome: 'A Lulu', ultimo: {episodio: 3, pronto: false}})",
                 "criacao.js")
    assert "O episódio 3 de “A Lulu” ainda não terminou" in parada
    # O nome da historia vira a mesma chave nos dois lados: um nome "novo"
    # igual ao de uma que existe continua aquela, e a tela diz antes.
    nomes = ["A Lulu", "a  lulu ", " A LULU na Floresta", "Ávila", "o Bento"]
    assert _js(f"{json.dumps(nomes)}.map(m.chaveDaHistoria)", "criacao.js") == \
        [estilos.chave_da_historia(n) for n in nomes]
    tela = _fonte("components", "longo", "CriarEpisodio.jsx")
    assert "chaveDaHistoria(h.nome) === chaveDaHistoria(nome)" in tela
    assert "Essa história já existe." in tela
    # A linha do estilo no episodio nao diz a duracao nem as cenas do video
    # CURTO do estilo: as do episodio sao as escolhidas na tela.
    spec = estilos.normalizar({"visual": {"preset": "aquarela"}, "cenas": 6, "duracao_s": 45,
                               "voz": {"nome": "Sulafat"}, "personagens": [{"nome": "Lulu"}]})
    assert _js(f"m.resumoDoEstilo({json.dumps(spec)}, {{duracao: false}})", "criacao.js") == \
        "história · aquarela · voz Sulafat · Lulu"
    assert "resumoDoEstilo(spec, { duracao: false })" in _fonte("components", "longo",
                                                                  "CriarEpisodio.jsx")


# --------------------------------------------------------------------------- #
# As telas
# --------------------------------------------------------------------------- #

def test_o_video_longo_deixou_de_ser_em_breve():
    tipos = _fonte("components", "TiposDeCriacao.jsx")
    bloco = tipos[tipos.index("id: 'longo'"):]
    assert "etapa:" not in bloco[:bloco.index("},")]
    criar = _fonte("pages", "Criar.jsx")
    assert "tipo === 'longo'" in criar and "<CriarVideoLongo" in criar
    assert "OUTROS" not in criar and "EmBreve" not in criar
    app = _fonte("App.jsx")
    assert "modoInicial={rota.busca.get('modo')}" in app
    assert "projetoInicial={rota.busca.get('projeto')}" in app


def test_o_site_novo_com_o_programa_velho_manda_atualizar():
    """Um motor de antes da 7.8 IGNORA o `formato` do `/api/criacoes` e faria
    um video curto no lugar do episodio: a tela olha a marca do /api/config."""
    import app  # noqa: F401
    assert "videoLongoNoMotor: config.video_longo === true" in _fonte("contexts", "AuthContext.jsx")
    tela = _fonte("components", "longo", "CriarVideoLongo.jsx")
    assert "situacaoDoVideoLongo" in tela and "data-aviso-video-longo-motor" in tela
    assert '"video_longo": True' in (RAIZ / "app.py").read_text(encoding="utf-8")


def test_as_rotas_que_o_painel_chama_existem_no_motor():
    import app
    rotas = {r.path for r in app.app.routes if hasattr(r, "path")}
    motor = _fonte("lib", "criacaoNoMotor.js")
    for rota, no_painel in (("/api/canais/{canal_id}/historias", "/historias`"),
                            ("/api/compilacoes", "'/api/compilacoes'"),
                            ("/api/compilacoes/{job_id}/refazer", "/refazer`"),
                            ("/api/jobs/{job_id}/cortes", "/cortes`")):
        assert rota in rotas and no_painel in motor, rota


def test_o_projeto_mostra_o_video_deitado_e_monta_de_novo():
    projeto = _fonte("pages", "Projeto.jsx")
    assert "<VideoLongo" in projeto and "refazerCompilacao(jobId)" in projeto
    assert "data-refazer-compilacao" in projeto and "data-compilacao" in projeto
    # Os cortes de um projeto viram um video longo pelo atalho da tela.
    assert "/criar/longo?modo=cortes&projeto=" in projeto
    assert "longo={longo}" in projeto
    video = _fonte("components", "longo", "VideoLongo.jsx")
    assert "aspect-video" in video and "video_description_for_youtube" in video


def test_a_publicacao_do_video_longo_diz_que_e_so_youtube():
    tela = _fonte("components", "PublicacoesTab.jsx")
    assert "data-longo-so-youtube" in tela
    # A regra vale para a conta avulsa E para o canal inteiro: o canal so e
    # destino pelas contas que aceitam o video longo, e o rotulo dele so lista
    # essas (era "Canal · TikTok, Instagram, YouTube" para um video que so vai
    # ao YouTube).
    assert "const serveDeDestino = (c) => !ehLongo || aceitaVideoLongo(c);" in tela
    assert "contasDoLugar.filter(serveDeDestino)" in tela
    assert "if (c.channel_id && serveDeDestino(c))" in tela
    # A lista filtrada nao esconde o seletor de projeto da Agenda: "sem
    # destino" e so quando nao ha conta nenhuma ali.
    assert "|| contasDoLugar.length === 0 ? (" in tela


@precisa_node
def test_as_plataformas_do_video_longo_sao_as_do_motor():
    import app
    assert _js("m.PLATAFORMAS_DO_VIDEO_LONGO", "publicacoes.js") == \
        list(app.PLATAFORMAS_DO_VIDEO_LONGO)
    assert _js("[{platform: 'youtube'}, {platform: 'tiktok'}, null].map(m.aceitaVideoLongo)",
               "publicacoes.js") == [True, False, False]


@precisa_node
def test_o_pacote_do_dia_conta_por_plataforma():
    """O botao do pacote do TikTok nao conta o video longo (ele so vai no do
    YouTube), e um motor de antes da 7.8, que so manda o total, continua
    funcionando."""
    dias = [{"dia": "2026-09-30", "cortes": 3, "por_plataforma": {"youtube": 3, "tiktok": 0}},
            {"dia": "2026-09-29", "cortes": 2, "por_plataforma": {"youtube": 2, "tiktok": 2}},
            {"dia": "2026-09-28", "cortes": 4}]
    assert _js(f"m.diasDoPacote({json.dumps(dias)}, 'tiktok').map((d) => d.dia)", "publicacoes.js") == \
        ["2026-09-29", "2026-09-28"]
    assert _js(f"m.diasDoPacote({json.dumps(dias)}, 'youtube').map((d) => m.cortesNoPacote(d, 'youtube'))",
               "publicacoes.js") == [3, 2, 4]
    tela = _fonte("components", "PublicacoesTab.jsx")
    assert "const diasComPacote = diasDoPacote(dias, pacotePara);" in tela
    assert "{maisRecente.cortes}" not in tela and "({d.cortes})" not in tela

