"""O documento de template da seção 5 (Fase 2, bloco 2.1).

O que este bloco encontrou pronto vale registrar: a **segunda passada já existe**
(`/api/subtitle` requeima legenda sobre o clipe já renderizado) e os **presets
são configuração**, porque `generate_ass` já expõe todos os botões. O que
faltava não era motor — era o documento onde "o meu estilo" se escreve uma vez.
"""
import pytest

import template as t


class TestPadrao:
    def test_spec_vazio_vira_documento_completo(self):
        d = t.normalizar(None)
        for secao in ("name", "aspect", "hook", "captions", "overlays",
                      "audio", "cuts", "safeArea"):
            assert secao in d, secao

    def test_spec_parcial_completa_o_resto(self):
        d = t.normalizar({"captions": {"preset": "limpo"}})
        assert d["captions"]["preset"] == "limpo"
        assert d["safeArea"] == {"topPct": 12, "bottomPct": 18}
        assert d["hook"]["mode"] == "text_punch"

    def test_merge_e_por_secao_nao_substitui_a_secao_inteira(self):
        # Escrever só uma chave de safeArea não pode apagar a outra.
        d = t.normalizar({"safeArea": {"bottomPct": 25}})
        assert d["safeArea"]["topPct"] == 12
        assert d["safeArea"]["bottomPct"] == 25

    def test_nao_muta_o_padrao(self):
        d = t.normalizar({"safeArea": {"bottomPct": 30}})
        d["safeArea"]["bottomPct"] = 99
        assert t.PADRAO["safeArea"]["bottomPct"] == 18

    def test_campo_desconhecido_passa_intacto(self):
        # Documento versionado: recusar o que ainda não se lê transformaria todo
        # campo novo em migração.
        d = t.normalizar({"transicoes": {"tipo": "corte"}})
        assert d["transicoes"] == {"tipo": "corte"}


class TestValidacao:
    def test_preset_inexistente_diz_quais_existem(self):
        with pytest.raises(t.TemplateInvalido) as exc:
            t.normalizar({"captions": {"preset": "neon_maluco"}})
        assert "karaoke_fill" in str(exc.value)

    def test_nome_vazio(self):
        with pytest.raises(t.TemplateInvalido, match="name"):
            t.normalizar({"name": "   "})

    @pytest.mark.parametrize("area", [
        {"topPct": -1}, {"bottomPct": 60}, {"topPct": "doze"},
        {"topPct": True},                      # bool não é número
    ])
    def test_safe_area_fora_da_faixa(self, area):
        with pytest.raises(t.TemplateInvalido):
            t.normalizar({"safeArea": area})

    def test_safe_area_que_nao_deixa_faixa_para_a_legenda(self):
        # 45+45 não come o quadro inteiro, mas deixa 10% — num 1920, 192px,
        # menos que duas linhas de Anton. O erro só apareceria no clipe pronto.
        with pytest.raises(t.TemplateInvalido, match="10%"):
            t.normalizar({"safeArea": {"topPct": 45, "bottomPct": 45}})

    def test_faixa_apertada_mas_usavel_passa(self):
        t.normalizar({"safeArea": {"topPct": 40, "bottomPct": 40}})

    def test_hook_com_modo_inexistente(self):
        with pytest.raises(t.TemplateInvalido, match="hook.mode"):
            t.normalizar({"hook": {"mode": "explosao"}})

    def test_overlay_sem_asset(self):
        with pytest.raises(t.TemplateInvalido, match="asset"):
            t.normalizar({"overlays": [{"anchor": "top-right"}]})

    def test_overlay_com_ancora_inexistente(self):
        with pytest.raises(t.TemplateInvalido, match="anchor"):
            t.normalizar({"overlays": [{"asset": "l.png", "anchor": "meio-do-nada"}]})

    def test_overlay_com_opacidade_fora_de_0_1(self):
        with pytest.raises(t.TemplateInvalido, match="opacity"):
            t.normalizar({"overlays": [{"asset": "l.png", "opacity": 4}]})

    def test_overlays_precisa_ser_lista(self):
        with pytest.raises(t.TemplateInvalido, match="lista"):
            t.normalizar({"overlays": {"asset": "l.png"}})

    def test_overlay_valido_passa(self):
        d = t.normalizar({"overlays": [
            {"asset": "logo.png", "anchor": "top-right", "marginPx": 48, "opacity": 0.9},
            {"asset": "endcard.mp4", "anchor": "full", "atEnd": True, "durationMs": 2000},
        ]})
        assert len(d["overlays"]) == 2

    def test_nao_e_objeto(self):
        with pytest.raises(t.TemplateInvalido):
            t.normalizar(["nao", "sou", "objeto"])


class TestSafeArea:
    def test_traduz_para_a_escala_do_ass(self):
        # `generate_ass` escreve PlayResY: 288 e a MarginV é nessa escala.
        assert t.margem_vertical(None) == round(288 * 0.18)

    def test_alinhamento_no_topo_usa_a_porcentagem_de_cima(self):
        d = {"captions": {"preset": "karaoke_fill", "alignment": "top"},
             "safeArea": {"topPct": 10, "bottomPct": 30}}
        assert t.margem_vertical(d) == round(288 * 0.10)

    def test_padrao_da_mais_folga_que_o_codigo_de_hoje(self):
        # O SAFE_MARGIN_V atual (43, ~15%) já veio de uma falha observada: com
        # 25 (8,7%) a legenda saía por baixo da interface do TikTok. Os 18% da
        # seção 5 são mais folga na MESMA direção, nunca menos.
        import subtitles
        assert t.margem_vertical(None) > subtitles.SAFE_MARGIN_V

    def test_zero_e_permitido(self):
        assert t.margem_vertical({"safeArea": {"bottomPct": 0}}) == 0


class TestPresets:
    def test_sao_seis(self):
        assert len(t.PRESETS_DE_LEGENDA) == 6

    def test_o_padrao_e_o_estilo_ja_medido_no_repositorio(self):
        # Não foi inventado aqui: é o `subtitles.AUTO_CAPTION_STYLE`, escolhido
        # renderizando quatro candidatos num clipe real (25-jul-2026).
        import subtitles
        medido = subtitles.AUTO_CAPTION_STYLE
        nosso = t.PRESETS_DE_LEGENDA["karaoke_fill"]
        assert nosso["font_name"] == medido["font_name"]
        assert nosso["highlight_color"] == medido["highlight_color"]
        assert nosso["effect"] == medido["effect"]
        assert nosso["uppercase"] == medido["uppercase"]
        assert nosso["border_width"] == medido["border_width"]

    @pytest.mark.parametrize("nome", list(t.PRESETS_DE_LEGENDA))
    def test_todo_preset_e_aceito_pelo_generate_ass(self, nome):
        # A garantia que importa: um preset que o `generate_ass` não saiba
        # receber só quebraria na hora de queimar, depois do render inteiro.
        import inspect

        import subtitles
        aceitos = set(inspect.signature(subtitles.generate_ass).parameters)
        sobrando = set(t.PRESETS_DE_LEGENDA[nome]) - aceitos
        assert not sobrando, f"{nome} passa argumentos que generate_ass não tem: {sobrando}"

    @pytest.mark.parametrize("nome", list(t.PRESETS_DE_LEGENDA))
    def test_todo_preset_tem_contorno(self, nome):
        # Sem contorno, texto branco sobre cena clara desaparece.
        assert t.PRESETS_DE_LEGENDA[nome]["border_width"] >= 3

    def test_centro_existe_por_causa_do_split(self):
        # No layout SPLIT os dois falantes ocupam as metades; o meio é a única
        # posição que não cobre ninguém.
        assert t.PRESETS_DE_LEGENDA["centro"]["alignment"] == "middle"


class TestKwargsDeLegenda:
    def test_preset_vira_argumentos(self):
        k = t.kwargs_de_legenda({"captions": {"preset": "limpo"}})
        assert k["font_name"] == "Verdana"
        assert "preset" not in k, "o nome do preset não é argumento de render"

    def test_o_que_esta_escrito_vence_o_preset(self):
        k = t.kwargs_de_legenda({"captions": {"preset": "limpo", "highlight": "#FF0000"}})
        assert k["highlight_color"] == "#FF0000"
        assert k["font_name"] == "Verdana", "o resto do preset continua"

    @pytest.mark.parametrize("da_secao5,do_render", [
        ("sizePt", "fontsize"), ("font", "font_name"),
        ("highlight", "highlight_color"), ("strokePx", "border_width"),
        ("maxWords", "max_chars"),
    ])
    def test_traduz_os_nomes_da_secao_5(self, da_secao5, do_render):
        k = t.kwargs_de_legenda({"captions": {"preset": "limpo", da_secao5: 77}})
        assert k[do_render] == 77

    def test_y_anchor_e_ignorado_porque_a_posicao_vem_do_safe_area(self):
        k = t.kwargs_de_legenda({"captions": {"preset": "limpo", "yAnchor": 0.72}})
        assert "yAnchor" not in k
        assert "y_anchor" not in k

    def test_spec_invalido_levanta_antes_de_produzir_argumentos(self):
        with pytest.raises(t.TemplateInvalido):
            t.kwargs_de_legenda({"captions": {"preset": "nao_existe"}})
