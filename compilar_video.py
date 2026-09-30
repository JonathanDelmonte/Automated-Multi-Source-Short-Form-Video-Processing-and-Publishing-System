"""A compilacao dos cortes como job (etapa 7.8): confere os trechos, faz a
legenda e monta o video horizontal, na pasta de um job.

    python -u compilar_video.py --pasta <pasta do job>

Fala com o `app.py` como o `criar_video.py`: os estagios pelo marcador do
`job_metrics` (a barra do painel), o video pronto pela linha
`CLIP_READY 0 <arquivo>`, e o `compilacao_metadata.json` escrito POR ULTIMO,
com um item em `shorts` -- para o `app.py`, metadata presente e job terminado,
e a compilacao vira um projeto comum, que publica e agenda como um corte (so no
YouTube: `formato: "longo"`).

O pedido vem de `compilacao.json`, escrito pelo `app.py` (`/api/compilacoes`)
com tudo resolvido: o arquivo de cada trecho (a origem, ou o corte vertical
quando a origem sumiu), o tempo, o titulo e as palavras. O job nao le a pasta
de outro projeto alem do arquivo de video -- e um arquivo que sumiu no meio
para o job dizendo qual trecho.

Sem IA nenhuma: nada aqui gasta cota.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

import capitulos
import compilacao
import job_metrics
import montagem

ARQUIVO_DA_LEGENDA = "legenda.ass"
BASE = compilacao.BASE
ESTAGIOS = compilacao.ESTAGIOS


class CompilacaoFalhou(RuntimeError):
    """A frase vai para o log do job, que e o que o painel mostra."""


def _ler_json(caminho: str) -> Optional[dict]:
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else None
    except (OSError, ValueError):
        return None


def _gravar_json(caminho: str, dados) -> None:
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(temporario, caminho)


def conferir_trechos(pedido: dict) -> list:
    """O plano da compilacao, com o que o disco diz de cada arquivo: o trecho
    que passa do fim do arquivo encolhe ate o fim, e o arquivo sem trilha de
    audio entra com silencio. Um arquivo que sumiu para o job."""
    trechos = []
    corte, titulo = 0, ""
    for k, t in enumerate(pedido.get("trechos") or []):
        if not isinstance(t, dict):
            raise CompilacaoFalhou(f"O trecho {k + 1} do pedido esta torto.")
        # O pedaco de um corte re-editado (`continua`) e do mesmo corte: a
        # frase fala do corte, que e o que a pessoa escolheu.
        if k == 0 or not t.get("continua"):
            corte, titulo = corte + 1, t.get("titulo") or ""
        arquivo = str(t.get("arquivo") or "")
        if not os.path.isfile(arquivo):
            raise CompilacaoFalhou(
                f"O corte {corte} (“{titulo or 'sem título'}”) não está mais no disco: o "
                "vídeo de origem e o corte foram apagados. Refaça a compilação sem ele.")
        sonda = compilacao.sondar(arquivo)
        t = dict(t)
        if sonda["duracao"]:
            t["corte_fim"] = min(float(t.get("corte_fim") or 0), sonda["duracao"])
            t["tem_audio"] = sonda["tem_audio"]
        trechos.append(t)
    try:
        return compilacao.planejar(trechos)
    except compilacao.CompilacaoInvalida as e:
        raise CompilacaoFalhou(str(e))


def gerar_legenda(pasta: str, pedido: dict, transcricao: dict,
                  total_s: float) -> Optional[str]:
    preset = pedido.get("legenda") or "limpo"
    if preset == "nenhuma" or not transcricao.get("segments"):
        return None
    import subtitles
    import template
    spec = {"captions": {"preset": preset}}
    kwargs = template.kwargs_de_legenda(spec)
    kwargs["margin_v"] = template.margem_vertical(spec)
    kwargs = montagem.legenda_horizontal(kwargs)
    caminho = os.path.join(pasta, ARQUIVO_DA_LEGENDA)
    if not subtitles.generate_ass(transcricao, 0.0, total_s, caminho, **kwargs):
        return None
    return caminho


def metadata(pedido: dict, plano: list, arquivo: str, transcricao: dict) -> dict:
    total = compilacao.duracao_total(plano)
    lista = compilacao.capitulos_do_plano(plano)
    titulo = (pedido.get("titulo") or "").strip()[:compilacao.TITULO_MAX] or "Melhores momentos"
    video = {
        "start": 0.0, "end": total,
        "video_title_for_youtube_short": titulo,
        "video_description_for_youtube": capitulos.na_descricao(
            pedido.get("descricao") or "", lista, pedido.get("idioma"),
            pedido.get("hashtags") or []),
        "formato": "longo",
        "capitulos": [{"inicio": t, "titulo": n} for t, n in lista],
        "compilacao": {"cortes": compilacao.quantos_cortes(plano), "trechos": len(plano)},
    }
    return {"shorts": [video], "transcript": transcricao,
            "compilacao": {
                "titulo": titulo, "arquivo": arquivo, "canal_id": pedido.get("canal_id"),
                "trechos": [{"job_id": t.get("job_id"), "clip": t.get("clip"),
                             "corte": t.get("corte"), "continua": bool(t.get("continua")),
                             "titulo": t["titulo"], "inicio": t["inicio_no_video"],
                             "duracao": t["duracao"], "vertical": bool(t.get("vertical"))}
                            for t in plano]}}


def compilar(pasta: str) -> str:
    """Faz a compilacao na pasta e devolve o nome do arquivo. Levanta
    `CompilacaoFalhou` com a frase para o log."""
    pedido = _ler_json(os.path.join(pasta, compilacao.ARQUIVO_DO_PEDIDO))
    if not pedido or not isinstance(pedido.get("trechos"), list):
        raise CompilacaoFalhou("O pedido da compilação (compilacao.json) não está na pasta "
                               "do projeto.")

    with job_metrics.stage("k1_trechos"):
        plano = conferir_trechos(pedido)
        total = compilacao.duracao_total(plano)
        job_metrics.fact("spoken_seconds", total)
        cortes = compilacao.quantos_cortes(plano)
        em_pedacos = f" em {len(plano)} trechos" if len(plano) > cortes else ""
        print(f"🎬 {cortes} cortes{em_pedacos}, {capitulos.tempo(total)} no total:")
        for t in plano:
            origem = "do corte vertical" if t.get("vertical") else "da origem"
            if t.get("continua"):
                print(f"      + {t['duracao']:.1f}s do mesmo corte (re-editado), {origem}")
                continue
            print(f"   {capitulos.tempo(t['inicio_no_video'])} {t['titulo'] or 'sem título'} "
                  f"({t['duracao']:.1f}s, {origem})")

    with job_metrics.stage("k2_legenda"):
        transcricao = compilacao.transcricao_do_plano(plano, pedido.get("idioma") or "")
        legenda = gerar_legenda(pasta, pedido, transcricao, total)
        if legenda is None and (pedido.get("legenda") or "limpo") != "nenhuma":
            print("⚠️ A compilação sai sem legenda (os cortes escolhidos não têm transcrição).")

    with job_metrics.stage("k3_montagem"):
        import ffmpeg_utils
        arquivo = f"{BASE}_clip_1.mp4"
        # Uma montagem anterior que nao chegou ao metadata deixou os dela.
        for antigo in os.listdir(pasta):
            if antigo.startswith("subtitled_") and antigo.endswith(f"_{arquivo}"):
                os.remove(os.path.join(pasta, antigo))
        legendado = f"subtitled_{int(time.time())}_{arquivo}" if legenda else None
        temporario = os.path.join(pasta, f"montando_{arquivo}")
        temporario_legendado = os.path.join(pasta, "montando_legendado.mp4") if legenda else None
        print(f"🎞️ Montando {len(plano)} trechos em 1920x1080...")
        compilacao.montar(plano, temporario, legenda=legenda,
                          saida_legendada=temporario_legendado,
                          video_args=ffmpeg_utils.video_encode_args(ffmpeg_utils.QUALITY_FAST),
                          video_args_legendada=ffmpeg_utils.video_encode_args(
                              ffmpeg_utils.QUALITY),
                          audio_args=ffmpeg_utils.audio_encode_args())
        os.replace(temporario, os.path.join(pasta, arquivo))
        if legenda:
            os.replace(temporario_legendado, os.path.join(pasta, legendado))

    _gravar_json(os.path.join(pasta, f"{BASE}_metadata.json"),
                 metadata(pedido, plano, arquivo, transcricao))
    print(f"CLIP_READY 0 {legendado or arquivo}")
    return legendado or arquivo


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Monta a compilacao dos cortes na pasta de um job.")
    parser.add_argument("--pasta", required=True)
    args = parser.parse_args(argv)
    pasta = os.path.abspath(args.pasta)
    job_metrics.reset(pasta, BASE)
    inicio = time.time()
    try:
        compilar(pasta)
    except (CompilacaoFalhou, RuntimeError) as e:
        print(f"❌ {e}")
        return 1
    finally:
        resumo = job_metrics.summary_line()
        if resumo:
            print("\n" + resumo)
        job_metrics.write()
    print(f"\n✅ Compilação pronta em {time.time() - inicio:.0f}s.")
    return 0


if __name__ == "__main__":
    try:
        import linhas_inteiras
        linhas_inteiras.instalar()
    except Exception:
        pass
    sys.exit(main())
