"""O documento da receita do canal (etapa 7.5): de onde vem o video e como
editar. Stdlib pura, como o template -- as regras rodam no CI sem banco."""
import pytest

import receitas


class TestPadrao:

    def test_a_receita_padrao(self):
        r = receitas.normalizar(None)
        assert r["fonte"]["tipo"] == "busca" and r["fonte"]["duracao"] == "longa"
        assert r["edicao"] == {"cortes_por_video": 5, "duracao_min": 20, "duracao_max": 60,
                               "layout": "auto", "legenda": True, "gancho": True,
                               "template_id": None}
        assert r["ritmo"] == {"videos_por_dia": 1} and r["direitos"] is None

    def test_por_secao(self):
        base = receitas.normalizar({"fonte": {"tema": "desenho animado"}})
        junto = receitas.normalizar({"edicao": {"cortes_por_video": 3}}, base=base)
        assert junto["fonte"]["tema"] == "desenho animado"
        assert junto["edicao"]["cortes_por_video"] == 3

    def test_campo_novo_passa(self):
        """Documento versionado: recusar o que ainda nao se le transformaria
        todo campo novo em migracao."""
        assert receitas.normalizar({"futuro": {"x": 1}})["futuro"] == {"x": 1}


class TestFonte:

    @pytest.mark.parametrize("fonte", [
        {"tipo": "nuvem"}, {"duracao": "curta"}, {"tema": "x" * 121}, {"tema": "a\x00b"}])
    def test_recusada(self, fonte):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar({"fonte": fonte})

    def test_links_limpos(self):
        r = receitas.normalizar({"fonte": {"tipo": "links", "links": [
            " https://youtu.be/dQw4w9WgXcQ ", "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/@canal", ""]}})
        assert r["fonte"]["links"] == ["https://youtu.be/dQw4w9WgXcQ",
                                       "https://www.youtube.com/@canal"]

    def test_links_em_texto_um_por_linha(self):
        r = receitas.normalizar({"fonte": {"tipo": "links",
                                           "links": "https://youtu.be/a\nhttps://youtu.be/b"}})
        assert len(r["fonte"]["links"]) == 2

    @pytest.mark.parametrize("link,trecho", [
        ("youtube.com/watch?v=x", "não é um endereço"),
        ("https://www.twitch.tv/canal", "live da Twitch"),
        ("https://www.twitch.tv/canal/videos", "lista de videos"),
        ("https://drive.google.com/drive/folders/abc", "pasta do Drive")])
    def test_link_recusado_diz_por_que(self, link, trecho):
        with pytest.raises(receitas.ReceitaInvalida, match=trecho):
            receitas.normalizar({"fonte": {"tipo": "links", "links": [link]}})

    def test_muitos_links(self):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar({"fonte": {"tipo": "links", "links": [
                f"https://youtu.be/{i:011d}" for i in range(51)]}})

    def test_canal_da_twitch(self):
        r = receitas.normalizar({"fonte": {"tipo": "twitch", "twitch": "twitch.tv/canal"}})
        assert r["fonte"]["twitch"] == "https://twitch.tv/canal"
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar({"fonte": {"tipo": "twitch",
                                           "twitch": "https://twitch.tv/videos/123"}})


class TestEdicao:

    @pytest.mark.parametrize("edicao", [
        {"cortes_por_video": 0}, {"cortes_por_video": 16}, {"duracao_min": 4},
        {"duracao_max": 181}, {"duracao_min": 50, "duracao_max": 52}, {"layout": "3d"},
        {"legenda": "sim"}, {"gancho": None}, {"template_id": "nao-e-id"},
        {"cortes_por_video": True}])
    def test_recusada(self, edicao):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar({"edicao": edicao})

    def test_template(self):
        tid = "11111111-2222-4333-8444-555555555555"
        assert receitas.normalizar({"edicao": {"template_id": tid}})["edicao"]["template_id"] == tid
        assert receitas.normalizar({"edicao": {"template_id": ""}})["edicao"]["template_id"] is None

    @pytest.mark.parametrize("n", [0, 11])
    def test_videos_por_dia(self, n):
        with pytest.raises(receitas.ReceitaInvalida):
            receitas.normalizar({"ritmo": {"videos_por_dia": n}})


class TestPronta:

    def test_busca_sem_tema(self):
        assert receitas.pronta(receitas.normalizar(None)) == "falta o tema da busca"
        assert receitas.pronta(receitas.normalizar({"fonte": {"tema": "x"}})) is None

    def test_a_busca_nao_pede_direitos(self):
        """A busca so traz licenca livre CONFERIDA pelo programa."""
        assert not receitas.precisa_de_direitos(receitas.normalizar(None))

    @pytest.mark.parametrize("fonte", [
        {"tipo": "links", "links": ["https://youtu.be/dQw4w9WgXcQ"]},
        {"tipo": "twitch", "twitch": "twitch.tv/canal"},
        {"tipo": "pasta"}])
    def test_o_resto_pede_a_confirmacao_de_quem_usa(self, fonte):
        spec = receitas.normalizar({"fonte": fonte})
        assert "direitos" in receitas.pronta(spec)
        assert receitas.pronta({**spec, "direitos": "2026-09-26T10:00:00+00:00"}) is None

    def test_mesma_fonte(self):
        a = receitas.normalizar({"fonte": {"tipo": "links", "links": ["https://youtu.be/a"]}})
        b = receitas.normalizar({"fonte": {"tipo": "links", "links": ["https://youtu.be/b"]}})
        assert receitas.mesma_fonte(a, a) and not receitas.mesma_fonte(a, b)
        busca = receitas.normalizar({"fonte": {"tema": "x"}})
        assert not receitas.mesma_fonte(busca, a)
        # Mudar o tema da busca nao importa: a busca nao depende de confirmacao.
        assert receitas.mesma_fonte(busca, receitas.normalizar({"fonte": {"tema": "y"}}))
