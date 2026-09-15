"""O pacote do dia -- a entrega do driver `manual` (Fase 3, bloco 3.2).

A secao 6 pede isto por escrito: "Faca ele entregar um pacote por dia: os
cortes do dia mais um arquivo de legenda pronta pra colar". O que estes testes
guardam e o "pronto pra colar": um `.txt` por corte e por plataforma, sem
rotulo, com o titulo na primeira linha -- e o pacote sobrevivendo a um corte
que sumiu do disco, porque perder os outros cinco por causa de um arquivo que a
limpeza levou seria trocar um problema pequeno por um grande.
"""
import asyncio
import io
import json
import os
import time
import uuid
import zipfile

import httpx
import pytest

from publishers import PostMeta, RenderedClip
from publishers import pacote

app_module = pytest.importorskip("app")


# --------------------------------------------------------------------------- #
# O montador, sozinho
# --------------------------------------------------------------------------- #

def _item(tmp_path, nome, titulo, descricao="desc", duracao=30.0, index=0,
          criar=True):
    caminho = tmp_path / nome
    if criar:
        caminho.write_bytes(b"\x00" * 64)
    return pacote.Item(
        clip=RenderedClip(path=str(caminho), job_id="j", index=index,
                          title=titulo, duration_s=duracao),
        meta=PostMeta(title=titulo, descriptions={"tiktok": descricao}))


class TestMontador:

    def test_um_video_e_uma_legenda_por_corte(self, tmp_path):
        itens = [_item(tmp_path, "a.mp4", "Primeiro", index=0),
                 _item(tmp_path, "b.mp4", "Segundo", index=1)]
        r = pacote.montar(itens, str(tmp_path / "p.zip"), "youtube", "2026-09-15")
        nomes = zipfile.ZipFile(r.caminho).namelist()
        assert "LEIA-ME.txt" in nomes
        assert "01_Primeiro.mp4" in nomes
        assert "01_Primeiro.youtube.txt" in nomes
        assert "02_Segundo.mp4" in nomes
        assert "02_Segundo.youtube.txt" in nomes
        assert r.cortes == 2

    def test_a_legenda_e_a_mesma_que_o_driver_escreve(self, tmp_path):
        """Um segundo texto, gerado de outro jeito, divergiria do que o driver
        `manual` grava ao lado do corte -- e o pacote e o mesmo driver."""
        from publishers.manual import render_caption
        meta = PostMeta(title="T", descriptions={"tiktok": "corpo"},
                        hashtags=("#a",))
        itens = [pacote.Item(clip=RenderedClip(
            path=str(_criar(tmp_path, "a.mp4")), job_id="j", index=0), meta=meta)]
        r = pacote.montar(itens, str(tmp_path / "p.zip"), "tiktok", "2026-09-15")
        dentro = zipfile.ZipFile(r.caminho).read("01_T.tiktok.txt").decode("utf-8")
        assert dentro == render_caption(meta, "tiktok")

    def test_corte_sem_arquivo_nao_derruba_o_pacote(self, tmp_path):
        itens = [_item(tmp_path, "existe.mp4", "Existe", index=0),
                 _item(tmp_path, "sumiu.mp4", "Sumiu", index=1, criar=False)]
        r = pacote.montar(itens, str(tmp_path / "p.zip"), "youtube", "2026-09-15")
        assert r.cortes == 1
        assert r.faltando == ("sumiu.mp4",)
        leia = zipfile.ZipFile(r.caminho).read("LEIA-ME.txt").decode("utf-8")
        assert "sumiu.mp4" in leia, "o que nao entrou tem de estar escrito"

    def test_a_numeracao_segue_a_ordem_recebida(self, tmp_path):
        """O passo de deteccao ja entrega do melhor para o pior, e essa e a
        ordem de publicar -- reordenar aqui jogaria fora o ranking."""
        itens = [_item(tmp_path, f"{c}.mp4", c.upper(), index=i)
                 for i, c in enumerate("cab")]
        r = pacote.montar(itens, str(tmp_path / "p.zip"), "youtube", "2026-09-15")
        videos = sorted(n for n in zipfile.ZipFile(r.caminho).namelist()
                        if n.endswith(".mp4"))
        assert videos == ["01_C.mp4", "02_A.mp4", "03_B.mp4"]

    def test_o_video_entra_sem_recomprimir(self, tmp_path):
        """mp4 ja esta comprimido; deflate nele so queima CPU. O texto, nao."""
        itens = [_item(tmp_path, "a.mp4", "T")]
        r = pacote.montar(itens, str(tmp_path / "p.zip"), "youtube", "2026-09-15")
        z = zipfile.ZipFile(r.caminho)
        assert z.getinfo("01_T.mp4").compress_type == zipfile.ZIP_STORED
        assert z.getinfo("01_T.youtube.txt").compress_type == zipfile.ZIP_DEFLATED

    def test_pacote_vazio_ainda_e_um_zip_legivel(self, tmp_path):
        r = pacote.montar([], str(tmp_path / "p.zip"), "youtube", "2026-09-15")
        assert r.cortes == 0
        assert zipfile.ZipFile(r.caminho).namelist() == ["LEIA-ME.txt"]

    def test_a_data_vai_no_nome_e_dentro(self, tmp_path):
        """O dia e do fuso do servidor. Escrito nos dois lugares para que nunca
        haja duvida de qual dia veio."""
        assert pacote.nome_do_pacote("2026-09-15", "tiktok") == \
            "cortes_2026-09-15_tiktok.zip"
        r = pacote.montar([_item(tmp_path, "a.mp4", "T")],
                          str(tmp_path / "p.zip"), "tiktok", "2026-09-15")
        leia = zipfile.ZipFile(r.caminho).read("LEIA-ME.txt").decode("utf-8")
        assert "2026-09-15" in leia


def _criar(tmp_path, nome):
    caminho = tmp_path / nome
    caminho.write_bytes(b"\x00" * 64)
    return caminho


class TestNomeDeArquivo:

    def test_acento_vira_letra_sem_acento(self):
        """O ZIP vai ser aberto numa maquina qualquer, e nem todo
        descompactador do Windows acerta UTF-8 no nome."""
        assert pacote.slug("Como ganhar tração com açaí!") == \
            "Como_ganhar_tracao_com_acai"

    def test_caractere_proibido_some(self):
        assert "/" not in pacote.slug("a/b:c*d")
        assert pacote.slug("a/b:c*d") == "a_b_c_d"

    def test_titulo_longo_cabe_em_bytes_nao_em_caracteres(self):
        """Um titulo em bengali passa de 255 bytes muito antes de parecer
        longo -- foi assim que o `/api/hook` morreu com OSError 36 em prod."""
        bengali = "মজার_ধাঁধা_শুনুন_আর_হাসুন" * 10
        saida = pacote.slug(bengali)
        assert len(saida.encode("utf-8")) <= pacote.MAX_NOME_BYTES

    def test_titulo_vazio_ainda_produz_nome(self, tmp_path):
        item = pacote.Item(
            clip=RenderedClip(path=str(_criar(tmp_path, "a.mp4")), job_id="j",
                              index=4),
            meta=PostMeta())
        assert pacote.nome_no_zip(1, item) == "01_corte_5"

    def test_titulo_so_de_emoji_nao_vira_nome_vazio(self, tmp_path):
        item = pacote.Item(
            clip=RenderedClip(path=str(_criar(tmp_path, "a.mp4")), job_id="j",
                              index=0),
            meta=PostMeta(title="🔥🤯"))
        assert pacote.nome_no_zip(1, item) == "01_corte_1"


# --------------------------------------------------------------------------- #
# Os endpoints
# --------------------------------------------------------------------------- #

@pytest.fixture()
def saida(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app_module, "jobs", {})
    yield tmp_path


def _job_com_cortes(raiz, quantos=2, titulos=None):
    job_id = str(uuid.uuid4())
    pasta = raiz / job_id
    pasta.mkdir()
    shorts = []
    for i in range(quantos):
        titulo = (titulos or [])[i] if titulos and i < len(titulos) else f"Corte {i+1}"
        shorts.append({
            "start": 10.0 * i, "end": 10.0 * i + 30.0,
            "video_title_for_youtube_short": titulo,
            "video_description_for_tiktok": f"descricao tiktok {i+1}",
            "video_description_for_instagram": f"descricao insta {i+1}",
        })
        (pasta / f"video_clip_{i+1}.mp4").write_bytes(b"\x00" * 32)
    (pasta / "video_metadata.json").write_text(
        json.dumps({"shorts": shorts}), encoding="utf-8")
    return job_id


def _chama(metodo, url):
    async def _do():
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport,
                                     base_url="http://testserver") as client:
            return await client.request(metodo, url)
    return asyncio.run(_do())


class TestEndpointDias:

    def test_lista_os_dias_com_corte(self, saida):
        _job_com_cortes(saida, 2)
        corpo = _chama("GET", "/api/publicacoes/dias").json()
        assert len(corpo["dias"]) == 1
        assert corpo["dias"][0]["cortes"] == 2
        assert corpo["hoje"] == pacote.hoje()

    def test_sem_job_nenhum_responde_lista_vazia(self, saida):
        assert _chama("GET", "/api/publicacoes/dias").json()["dias"] == []

    def test_pasta_que_nao_e_job_e_ignorada(self, saida):
        (saida / "thumbnails").mkdir()
        (saida / "thumbnails" / "x_metadata.json").write_text("{}")
        assert _chama("GET", "/api/publicacoes/dias").json()["dias"] == []

    def test_agrupa_pela_data_do_arquivo_do_corte(self, saida):
        """A data e a do corte, nao a do job: um job de ontem que ganhou
        legenda hoje produz um arquivo de hoje."""
        job_id = _job_com_cortes(saida, 2)
        antigo = saida / job_id / "video_clip_1.mp4"
        ontem = time.time() - 86400
        os.utime(antigo, (ontem, ontem))
        dias = _chama("GET", "/api/publicacoes/dias").json()["dias"]
        assert len(dias) == 2
        assert [d["cortes"] for d in dias] == [1, 1]


class TestEndpointPacote:

    def test_baixa_o_zip_do_dia(self, saida):
        _job_com_cortes(saida, 2, titulos=["Primeiro corte", "Segundo corte"])
        r = _chama("GET", "/api/publicacoes/pacote")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nomes = z.namelist()
        assert "01_Primeiro_corte.mp4" in nomes
        assert "01_Primeiro_corte.youtube.txt" in nomes
        assert "LEIA-ME.txt" in nomes

    def test_a_legenda_do_short_cai_na_descricao_que_existe(self, saida):
        """Nao ha `video_description_for_youtube` no prompt de deteccao. A
        queda de `description_for` e o que impede um Short sem descricao."""
        _job_com_cortes(saida, 1, titulos=["Titulo"])
        r = _chama("GET", "/api/publicacoes/pacote?plataforma=youtube")
        texto = zipfile.ZipFile(io.BytesIO(r.content)).read(
            "01_Titulo.youtube.txt").decode("utf-8")
        assert texto.startswith("Titulo\n\n")
        assert "descricao tiktok 1" in texto

    def test_cada_plataforma_recebe_o_texto_dela(self, saida):
        _job_com_cortes(saida, 1, titulos=["Titulo"])
        insta = zipfile.ZipFile(io.BytesIO(
            _chama("GET", "/api/publicacoes/pacote?plataforma=instagram").content))
        assert "descricao insta 1" in insta.read(
            "01_Titulo.instagram.txt").decode("utf-8")

    def test_plataforma_desconhecida_e_400(self, saida):
        _job_com_cortes(saida, 1)
        r = _chama("GET", "/api/publicacoes/pacote?plataforma=orkut")
        assert r.status_code == 400

    def test_sem_corte_nenhum_e_404(self, saida):
        assert _chama("GET", "/api/publicacoes/pacote").status_code == 404

    def test_dia_sem_corte_diz_quais_dias_tem(self, saida):
        """Um 404 que so diz "nao tem" manda a pessoa adivinhar."""
        _job_com_cortes(saida, 1)
        r = _chama("GET", "/api/publicacoes/pacote?dia=1999-01-01")
        assert r.status_code == 404
        assert pacote.hoje() in r.json()["detail"]

    def test_sem_dia_vale_o_mais_recente_que_tem_corte(self, saida):
        """E nao "hoje": pedir o pacote as nove da manha e receber um ZIP vazio
        porque o job da noite caiu no dia anterior so atrapalha."""
        job_id = _job_com_cortes(saida, 1)
        antigo = time.time() - 5 * 86400
        for arquivo in (saida / job_id).glob("*.mp4"):
            os.utime(arquivo, (antigo, antigo))
        r = _chama("GET", "/api/publicacoes/pacote")
        assert r.status_code == 200
        esperado = pacote.dia_de(antigo)
        assert esperado in r.headers.get("content-disposition", "")

    def test_o_zip_temporario_nao_fica_no_disco(self, saida):
        _job_com_cortes(saida, 1)
        _chama("GET", "/api/publicacoes/pacote")
        assert not list(saida.glob("pacote_*.zip")), \
            "o ZIP e servido e apagado; acumular encheria o output/"

    def test_metadata_corrompido_nao_derruba_o_pacote(self, saida):
        _job_com_cortes(saida, 1, titulos=["Bom"])
        quebrado = saida / str(uuid.uuid4())
        quebrado.mkdir()
        (quebrado / "x_metadata.json").write_text("{isso nao e json")
        r = _chama("GET", "/api/publicacoes/pacote")
        assert r.status_code == 200
        assert "01_Bom.mp4" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()

    def test_prefere_a_versao_com_legenda_queimada(self, saida):
        """Mesma resolucao do `download_all_clips`: empacotar o arquivo limpo
        entregaria o corte sem as legendas que a pessoa mandou queimar."""
        job_id = _job_com_cortes(saida, 1, titulos=["Titulo"])
        pasta = saida / job_id
        (pasta / "subtitled_9999_video_clip_1.mp4").write_bytes(b"\x01" * 99)
        r = _chama("GET", "/api/publicacoes/pacote")
        dados = zipfile.ZipFile(io.BytesIO(r.content)).read("01_Titulo.mp4")
        assert len(dados) == 99
