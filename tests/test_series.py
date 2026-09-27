"""A regra da serie em partes (etapa 7.6), sem torch nem ffmpeg.

O "pronto quando": uma live de 1 hora vira uma serie agendada, na ordem, **sem
buraco e sem repeticao**. Aqui mora a metade que se prova sem video: as partes
cobrem o trecho inteiro, contiguas, nunca cortam uma palavra; o texto de cada
uma diz "Parte N"; e a trava da ordem nunca deixa a parte seguinte passar na
frente de uma anterior que ainda vai sair, esta subindo ou falhou.
"""
import json
import random
import threading
from datetime import datetime, timezone

import pytest

import series


def _palavras_aleatorias(rng, duracao):
    """Fala de mentira: palavras de 0,1 a 0,7 s com pausas de 0 a 1,5 s, e de
    vez em quando um silencio longo. Algumas terminam frase."""
    lista, t = [], rng.uniform(0, 3)
    while t < duracao - 0.2:
        fim = min(duracao, t + rng.uniform(0.1, 0.7))
        texto = rng.choice(["olha", "isso", "aqui", "agora.", "entao,", "sim!", "e"])
        lista.append((round(t, 3), round(fim, 3), texto))
        t = fim + (rng.uniform(4, 12) if rng.random() < 0.02 else rng.uniform(0, 1.5))
    return lista


class TestOndeCortar:

    def test_o_trecho_inteiro_sem_buraco_e_sem_sobreposicao(self):
        for duracao, alvo in ((3600, 60), (185, 60), (61, 60), (7200, 30), (95, 20)):
            partes = series.partes(duracao, [], alvo=alvo)
            assert partes[0][0] == 0 and partes[-1][1] == duracao
            for (a_ini, a_fim), (b_ini, b_fim) in zip(partes, partes[1:]):
                assert a_fim == b_ini, "buraco ou trecho repetido na costura"
                assert a_ini < a_fim and b_ini < b_fim

    def test_uma_live_de_uma_hora_vira_sessenta_partes_de_um_minuto(self):
        partes = series.partes(3600, [], alvo=60)
        assert len(partes) == 60
        assert all(abs((f - i) - 60) < 1e-6 for i, f in partes)

    def test_o_tamanho_se_divide_em_vez_de_sobrar(self):
        # 90 s com partes de 60: duas de 45, e nao uma de 60 e uma sobra de 30.
        assert series.partes(90, [], alvo=60) == [(0.0, 45.0), (45.0, 90.0)]
        # Meio para cima: 150 s viram tres de 50, e nao duas de 75.
        assert len(series.partes(150, [], alvo=60)) == 3

    def test_nunca_corta_no_meio_de_uma_palavra(self):
        rng = random.Random(76)
        for _ in range(60):
            duracao = rng.uniform(120, 1800)
            lista = _palavras_aleatorias(rng, duracao)
            partes = series.partes(duracao, lista, alvo=rng.choice((30, 60, 90)))
            for _, fronteira in partes[:-1]:
                for ini, fim, _txt in lista:
                    assert not (ini < fronteira < fim), \
                        f"a fronteira {fronteira} corta a palavra {ini}-{fim}"

    def test_cada_parte_fica_perto_do_alvo(self):
        rng = random.Random(3)
        for _ in range(30):
            duracao = rng.uniform(600, 3600)
            lista = _palavras_aleatorias(rng, duracao)
            partes = series.partes(duracao, lista, alvo=60)
            passo = duracao / len(partes)
            for ini, fim in partes:
                assert 0.5 * passo <= fim - ini <= 1.5 * passo

    def test_prefere_o_fim_da_frase_a_pausa_do_meio(self):
        # Ideal em 60 s. Uma pausa curta no meio de uma frase logo ali, e o
        # fim de uma frase um pouco mais longe: a frase inteira vale mais.
        lista = [(55.0, 58.0, "entao"), (58.2, 59.9, "continuando."),
                 (60.5, 61.0, "e"), (61.1, 63.0, "depois"), (63.2, 70.0, "fala")]
        (_, fronteira), _ = series.partes(120, lista, alvo=60)
        assert 59.9 < fronteira < 60.5
        # E a parte seguinte comeca antes da proxima palavra, nunca depois.
        assert fronteira <= 60.5 - series.ANTECEDENCIA_S + 1e-9

    def test_numa_pausa_longa_a_parte_seguinte_comeca_perto_da_fala(self):
        # Pausa de 20 s (58 a 78) com o ideal no meio: corta no ideal, que ja
        # esta dentro do silencio.
        lista = [(50.0, 58.0, "fim."), (78.0, 79.0, "volta")]
        (_, fronteira), _ = series.partes(120, lista, alvo=60)
        assert fronteira == 60.0

    def test_o_trecho_escolhido(self):
        partes = series.partes(3600, [], alvo=60, inicio=300, fim=900)
        assert partes[0][0] == 300 and partes[-1][1] == 900 and len(partes) == 10
        # O fim alem do video vale o fim do video.
        assert series.partes(100, [], alvo=60, fim=500)[-1][1] == 100

    def test_video_vazio_nao_tem_parte(self):
        assert series.partes(0, [], alvo=60) == []
        assert series.partes(100, [], alvo=60, inicio=150) == []

    def test_quantas_partes_bate_com_as_partes(self):
        for duracao in (45, 90, 150, 3600, 5000):
            spec = {"duracao_parte_s": 60}
            assert series.quantas_partes(duracao, spec) == len(series.partes(duracao, [], alvo=60))

    def test_palavras_da_transcricao(self):
        transcript = {"segments": [
            {"words": [{"word": " b", "start": 2.0, "end": 2.5},
                       {"word": " a", "start": 1.0, "end": 1.4},
                       {"word": "sem tempo"},
                       {"word": " nan", "start": float("nan"), "end": 3.0}]}]}
        assert series.palavras(transcript) == [(1.0, 1.4, "a"), (2.0, 2.5, "b")]
        assert series.palavras(None) == []


class TestTexto:

    def test_parte_n_no_titulo(self):
        assert series.titulo("Live do Fulano", 3) == "Live do Fulano - Parte 3"
        assert series.titulo("Live", 12, "en") == "Live - Part 12"
        assert series.titulo("Live", 1, "es-MX") == "Live - Parte 1"
        assert series.titulo("", 4) == "Parte 4"

    def test_o_titulo_nunca_passa_de_cem_e_nunca_perde_o_numero(self):
        titulo = series.titulo("X" * 300, 147)
        assert len(titulo) <= 100 and titulo.endswith(" - Parte 147")

    def test_descricao(self):
        assert series.descricao("Live do Fulano!", 3, 60) == "Parte 3 de 60 — Live do Fulano!"
        assert series.descricao("Live", 3, 60, "en") == "Part 3 of 60 — Live"
        assert series.descricao("", 1, 2) == "Parte 1 de 2"

    def test_os_estilos_do_rotulo_sao_os_do_gancho(self):
        hooks = pytest.importorskip("hooks")
        assert set(series.ESTILOS_DO_ROTULO) == set(hooks.HOOK_STYLES)

    def test_os_cortes_de_uma_serie(self):
        spec = series.normalizar_pedido({"nome": "Filme antigo", "duracao_parte_s": 60})
        cortes = series.cortes(spec, 180, None, "titulo do video")
        assert [c["serie"]["parte"] for c in cortes] == [1, 2, 3]
        assert all(c["serie"]["partes"] == 3 and c["serie"]["id"] == spec["id"] for c in cortes)
        assert cortes[1]["video_title_for_youtube_short"] == "Filme antigo - Parte 2"
        assert cortes[1]["viral_hook_text"] == "Parte 2"
        assert cortes[2]["video_description_for_tiktok"] == "Parte 3 de 3 — Filme antigo"
        # Sem nome, vale o titulo do video.
        sem_nome = series.cortes(series.normalizar_pedido({}), 60, None, "Live de ontem")
        assert sem_nome[0]["video_title_for_youtube_short"] == "Live de ontem - Parte 1"

    def test_quanto_tempo_o_rotulo_fica(self):
        assert series.segundos_do_rotulo({"rotulo": "inicio"}) == series.SEGUNDOS_DO_ROTULO
        assert series.segundos_do_rotulo({"rotulo": "sempre"}) == 0.0
        assert series.segundos_do_rotulo({"rotulo": "nao"}) is None
        assert series.segundos_do_rotulo(None) == series.SEGUNDOS_DO_ROTULO


class TestPedido:

    def test_padroes(self):
        spec = series.normalizar_pedido({}, idioma="pt-BR")
        assert spec["duracao_parte_s"] == 60 and spec["rotulo"] == "inicio"
        assert spec["estilo_rotulo"] == "classic" and spec["idioma"] == "pt"
        assert spec["agendar"] is False and spec["bloco_min"] == series.BLOCO_PADRAO_MIN
        assert spec["nome"] is None and len(spec["id"]) == 36

    def test_o_id_e_sempre_nosso(self):
        spec = series.normalizar_pedido({"id": "escolhido-por-quem-pediu"})
        assert spec["id"] != "escolhido-por-quem-pediu"

    def test_texto_json_e_verdadeiro(self):
        assert series.normalizar_pedido('{"duracao_parte_s": 45}')["duracao_parte_s"] == 45
        assert series.normalizar_pedido(True)["duracao_parte_s"] == 60
        assert series.normalizar_pedido("")["duracao_parte_s"] == 60

    @pytest.mark.parametrize("pedido, trecho", [
        ({"duracao_parte_s": 5}, "duracao_parte_s"),
        ({"duracao_parte_s": 999}, "duracao_parte_s"),
        ({"duracao_parte_s": "abc"}, "numero"),
        ({"duracao_parte_s": True}, "numero"),
        ({"rotulo": "piscando"}, "rotulo"),
        ({"estilo_rotulo": "neon"}, "estilo"),
        ({"nome": "x" * 200}, "nome"),
        ({"nome": 42}, "texto"),
        ({"inicio_s": 100, "fim_s": 110}, "curto"),
        ({"bloco_min": 500}, "bloco_min"),
        ({"bloco_min": 1.5}, "inteiro"),
        ("nao e json", "JSON"),
        ([1, 2], "JSON"),
    ])
    def test_recusas(self, pedido, trecho):
        with pytest.raises(series.SerieInvalida, match=trecho):
            series.normalizar_pedido(pedido)

    def test_o_nome_perde_os_espacos_repetidos(self):
        assert series.normalizar_pedido({"nome": "  Minha   serie "})["nome"] == "Minha serie"


class TestRetomada:

    def test_marcar_e_ler(self, tmp_path):
        series.gravar_spec(str(tmp_path), series.normalizar_pedido({}))
        assert series.incompleta(str(tmp_path))       # nada pronto ainda
        for i in range(3):
            (tmp_path / f"parte{i}.mp4").write_bytes(b"x")
            series.marcar_pronta(str(tmp_path), i, str(tmp_path / f"parte{i}.mp4"), 3,
                                 extra={"auto_hook": {"text": f"Parte {i + 1}"}})
        prontas = series.prontas(str(tmp_path))
        assert set(prontas) == {0, 1, 2}
        assert prontas[1]["arquivo"] == "parte1.mp4"
        assert prontas[1]["auto_hook"] == {"text": "Parte 2"}
        assert not series.incompleta(str(tmp_path))
        # A parte cujo arquivo sumiu volta a faltar.
        (tmp_path / "parte1.mp4").unlink()
        assert set(series.prontas(str(tmp_path))) == {0, 2}
        assert series.incompleta(str(tmp_path))

    def test_so_serie_pode_estar_incompleta(self, tmp_path):
        assert not series.incompleta(str(tmp_path))
        assert series.ler_spec(str(tmp_path)) is None
        (tmp_path / series.ARQUIVO).write_text("{quebrado")
        assert series.ler_spec(str(tmp_path)) is None

    def test_partes_em_paralelo_nao_se_perdem(self, tmp_path):
        # As partes terminam em paralelo (CLIP_WORKERS): nenhuma anotacao pode
        # engolir a de outra.
        total = 40
        for i in range(total):
            (tmp_path / f"p{i}.mp4").write_bytes(b"x")
        threads = [threading.Thread(target=series.marcar_pronta,
                                    args=(str(tmp_path), i, str(tmp_path / f"p{i}.mp4"), total))
                   for i in range(total)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(series.prontas(str(tmp_path))) == total
        dados = json.loads((tmp_path / series.PROGRESSO).read_text())
        assert dados["total"] == total


def _pub(pid, parte, status="scheduled", conta="yt", serie="s1", quando=True):
    return {"id": pid, "account_id": conta, "serie_id": serie, "parte": parte,
            "status": status,
            "scheduled_at": datetime(2026, 9, 27, 14, tzinfo=timezone.utc) if quando else None}


class TestOrdem:

    def test_so_a_parte_mais_baixa_passa(self):
        todas = [_pub("p1", 1), _pub("p2", 2), _pub("p3", 3)]
        assert series.seguradas(todas, todas) == {"p2": 1, "p3": 1}

    def test_a_que_falhou_segura_as_seguintes(self):
        todas = [_pub("p1", 1, "published", quando=False), _pub("p2", 2, "failed"),
                 _pub("p3", 3), _pub("p4", 4)]
        pendentes = [p for p in todas if p["status"] == "scheduled"]
        assert series.seguradas(pendentes, todas) == {"p3": 2, "p4": 2}

    def test_subindo_segura(self):
        todas = [_pub("p1", 1, "publishing"), _pub("p2", 2)]
        assert series.seguradas([todas[1]], todas) == {"p2": 1}

    def test_pulada_publicada_e_fila_manual_nao_seguram(self):
        todas = [_pub("p1", 1, "published"), _pub("p2", 2, "cancelled"),
                 _pub("p3", 3, "scheduled", quando=False), _pub("p4", 4)]
        assert series.seguradas([todas[3]], todas) == {}

    def test_cada_conta_anda_no_seu_passo(self):
        todas = [_pub("t2", 2, "failed", conta="tiktok"), _pub("y1", 1, "published", conta="yt"),
                 _pub("y3", 3, conta="yt"), _pub("t3", 3, conta="tiktok")]
        assert series.seguradas([todas[2], todas[3]], todas) == {"t3": 2}

    def test_fora_de_serie_nunca_e_segurada(self):
        todas = [_pub("a", 1, "failed", serie=None), _pub("b", 2, serie=None)]
        assert series.seguradas(todas, todas) == {}

    def test_series_diferentes_nao_se_misturam(self):
        todas = [_pub("a", 1, "failed", serie="s1"), _pub("b", 2, serie="s2")]
        assert series.seguradas([todas[1]], todas) == {}

    def test_paradas_so_mostra_o_problema(self):
        todas = [_pub("p1", 1, "published"), _pub("p2", 2, "failed"),
                 _pub("p3", 3), _pub("p4", 4), _pub("x5", 5, conta="tiktok")]
        assert series.paradas(todas) == {"p3": {"parte": 2, "motivo": "falhou"},
                                         "p4": {"parte": 2, "motivo": "falhou"}}
        # A espera normal pela parte de antes nao e noticia.
        assert series.paradas([_pub("p1", 1), _pub("p2", 2)]) == {}
