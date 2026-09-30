"""A criacao de um video curto por IA (etapa 7.7, ADR-013): roteiro, imagens,
voz, legenda e montagem, na pasta de um job.

    python -u criar_video.py --pasta <pasta do job>

E um job como os do `main.py`, e fala com o `app.py` do mesmo jeito: os
estagios pelo marcador do `job_metrics` (a barra do painel), o corte pronto
pela linha `CLIP_READY 0 <arquivo>`, e o `<base>_metadata.json` com um item em
`shorts` -- e por isso que o video criado vira um projeto comum, com
publicacao, agenda e tudo o que um corte tem.

**O que ja ficou pronto na pasta nao e refeito.** O roteiro, cada imagem e a
narracao sao arquivos; um job retomado depois de um reinicio (o manifesto de
resume roda este mesmo comando) continua do primeiro que falta. E cota gratis:
gerar de novo uma imagem que ja existe e gastar a do dia a toa.

**O metadata e escrito por ultimo**, quando o video ja esta na pasta: para o
`app.py`, metadata presente e job terminado.

**Saem dois arquivos, como num corte do pipeline**: `criacao_clip_1.mp4`, sem
legenda, e `subtitled_<ts>_criacao_clip_1.mp4`, com ela -- e o limpo que deixa
a pessoa trocar o estilo da legenda pelo painel sem queimar uma por cima da
outra. A legenda e o texto do ROTEIRO no tempo da voz, e e essa transcricao que
fica no metadata (`montagem.palavras_do_roteiro`).

O pedido vem de `criacao.json`, escrito pelo `app.py` (`/api/criacoes`): o
estilo (uma copia, para que editar o estilo no meio nao mude um video em
andamento), a ideia, o idioma e as imagens dos personagens, ja copiadas para
`referencias/`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Optional

import estilos
import job_metrics
import midia_ia
import montagem

ARQUIVO_DO_PEDIDO = "criacao.json"
ARQUIVO_DO_ROTEIRO = "roteiro.json"
ARQUIVO_DA_VOZ = "narracao.wav"
ARQUIVO_DA_TRANSCRICAO = "narracao_transcricao.json"
ARQUIVO_DA_LEGENDA = "legenda.ass"
#: Nome neutro: o caminho entra num filtro do ffmpeg, e apostrofo de titulo ali
#: quebra o grafo (ver `ffmpeg_utils.escape_filter_value`).
BASE = "criacao"

#: Os estagios, na ordem. O `app.py` desenha a barra com esta lista
#: (`CRIACAO_STAGES`), e ha teste comparando.
ESTAGIOS = ("c1_roteiro", "c2_imagens", "c3_voz", "c4_legenda", "c5_montagem")


class CriacaoFalhou(RuntimeError):
    """A frase vai para o log do job, que e o que o painel mostra."""


# --------------------------------------------------------------------------- #
# O roteiro, pela cascata de texto
# --------------------------------------------------------------------------- #

def _schema():
    from pydantic import BaseModel

    class Cena(BaseModel):
        fala: str
        imagem: str
        personagens: List[str]

    class Roteiro(BaseModel):
        titulo: str
        descricao: str
        hashtags: List[str]
        cenas: List[Cena]

    return Roteiro


def _chamar_provedor(prompt, schema, provider):
    """Uma tentativa num provedor da cascata (o mesmo desenho do
    `main._run_gemini_stage`, sem o resto do `main.py`, que so importa com
    torch)."""
    import llm_backend
    import llm_cascade
    if provider.base_url is not None:
        return llm_backend.generate_json(
            prompt, schema, model=provider.model, base_url_override=provider.base_url,
            api_key=provider.api_key(), timeout=llm_cascade.timeout_para(provider),
            extra_body=dict(provider.extra) or None)
    import gemini_worker
    from google import genai
    from google.genai import types as genai_types
    cliente = genai.Client(api_key=provider.api_key())
    resposta = cliente.models.generate_content(
        model=provider.model, contents=prompt,
        config=genai_types.GenerateContentConfig(response_mime_type="application/json",
                                                 response_schema=schema))
    gemini_worker.raise_if_blocked(resposta)
    objeto = getattr(resposta, "parsed", None)
    if objeto is not None:
        dados = objeto.model_dump() if hasattr(objeto, "model_dump") else objeto
    else:
        dados = gemini_worker._parse_json_response_text(gemini_worker._get_response_text(resposta))
    return dados, gemini_worker._calculate_cost_analysis(resposta, provider.model)


def escrever_roteiro(doc: dict, ideia: str, idioma: str, ja_feitos: list) -> dict:
    import llm_cascade
    prompt = estilos.prompt_do_roteiro(doc, ideia, idioma, ja_feitos)
    try:
        bruto, custo = llm_cascade.run(prompt, _schema(), call=_chamar_provedor)
    except llm_cascade.AllProvidersFailed as e:
        raise CriacaoFalhou(f"Nenhuma IA de texto escreveu o roteiro: {e}")
    job_metrics.add_llm(custo)
    try:
        return estilos.ler_roteiro(bruto, doc)
    except estilos.EstiloInvalido as e:
        raise CriacaoFalhou(f"O roteiro veio incompleto: {e}")


# --------------------------------------------------------------------------- #
# Os passos
# --------------------------------------------------------------------------- #

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


def arquivo_da_cena(pasta: str, i: int) -> Optional[str]:
    for ext in (".png", ".jpg"):
        caminho = os.path.join(pasta, f"cena_{i + 1:02d}{ext}")
        if os.path.isfile(caminho) and os.path.getsize(caminho) > 0:
            return caminho
    return None


def gerar_imagens(pasta: str, pedido: dict, roteiro: dict) -> List[str]:
    doc = pedido["estilo"]
    personagens = {p["id"]: p for p in doc.get("personagens") or []}
    refs_prontas = {}
    for pid, relativo in (pedido.get("referencias") or {}).items():
        caminho = os.path.join(pasta, relativo)
        if pid in personagens and os.path.isfile(caminho):
            with open(caminho, "rb") as f:
                refs_prontas[pid] = midia_ia.preparar_referencia(f.read())
    cenas = roteiro["cenas"]
    faltam = [i for i in range(len(cenas)) if arquivo_da_cena(pasta, i) is None]
    cabem = midia_ia.imagens_que_cabem(referencias=2)
    if faltam and cabem < len(faltam):
        raise CriacaoFalhou(
            f"A cota gratis de imagem de hoje so da para {cabem} das {len(faltam)} imagens que "
            "faltam. O video continua de onde parou amanha (a cota volta a meia-noite UTC).")
    semente = int(doc.get("semente") or 1)
    neurons = 0.0
    for i in faltam:
        cena = cenas[i]
        na_cena = [personagens[pid] for pid in cena.get("personagens") or [] if pid in personagens]
        refs = [refs_prontas[p["id"]] for p in na_cena if p["id"] in refs_prontas]
        com_ref = [p for p in na_cena if p["id"] in refs_prontas]
        prompt = estilos.prompt_da_cena(doc, cena, com_ref)
        print(f"🖼️ Cena {i + 1}/{len(cenas)}"
              + (f" com {', '.join(p['nome'] for p in com_ref)}" if com_ref else ""))
        img = midia_ia.gerar_imagem(prompt, referencias=refs, semente=semente + i)
        destino = os.path.join(pasta, f"cena_{i + 1:02d}{img.extensao}")
        with open(destino + ".tmp", "wb") as f:
            f.write(img.dados)
        os.replace(destino + ".tmp", destino)
        neurons += img.neurons
    if faltam:
        job_metrics.fact("neurons", round(neurons, 2))
        print(f"   {len(faltam)} imagem(ns), ~{neurons:.0f} neurons da cota gratis de hoje "
              f"({int(midia_ia.uso()['neurons'])} de {int(midia_ia.neurons_por_dia())} usados).")
    return [arquivo_da_cena(pasta, i) for i in range(len(cenas))]


def gerar_voz(pasta: str, pedido: dict, roteiro: dict) -> str:
    caminho = os.path.join(pasta, ARQUIVO_DA_VOZ)
    if os.path.isfile(caminho) and os.path.getsize(caminho) > 44:
        print("🎙️ A narracao ja estava pronta.")
        return caminho
    voz = pedido["estilo"].get("voz") or {}
    audio = midia_ia.narrar(estilos.narracao(roteiro), voz=voz.get("nome") or midia_ia.VOZ_PADRAO,
                            instrucao=voz.get("instrucao") or "")
    with open(caminho + ".tmp", "wb") as f:
        f.write(audio.wav)
    os.replace(caminho + ".tmp", caminho)
    print(f"🎙️ Narracao de {audio.segundos:.1f}s na voz {audio.voz} ({audio.modelo}).")
    return caminho


def duracao_do_wav(caminho: str) -> float:
    import wave
    with wave.open(caminho) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def transcrever(pasta: str, voz: str) -> Optional[dict]:
    """O tempo de cada palavra da narracao. Sem ele a legenda nao sai, e a
    duracao das cenas cai para a proporcao do texto -- o video sai do mesmo
    jeito, e o log diz."""
    caminho = os.path.join(pasta, ARQUIVO_DA_TRANSCRICAO)
    pronta = _ler_json(caminho)
    if pronta is not None:
        return pronta
    try:
        from transcribe_backends import transcribe_media
        transcricao = transcribe_media(voz)
    except Exception as e:
        print(f"⚠️ A narracao nao foi transcrita ({type(e).__name__}: {e}); sem legenda, e as "
              "cenas dividem o tempo pelo tamanho do texto.")
        return None
    _gravar_json(caminho, transcricao)
    return transcricao


def palavras_de(transcricao: Optional[dict]) -> list:
    saida = []
    for seg in (transcricao or {}).get("segments") or []:
        for w in seg.get("words") or []:
            if isinstance(w, dict) and w.get("start") is not None:
                saida.append(w)
    return saida


def transcricao_do_roteiro(roteiro: dict, palavras: list, transcricao: Optional[dict],
                           idioma: str) -> dict:
    """A transcricao que o projeto guarda: as palavras do roteiro no tempo da
    voz, um segmento por cena. E dela que sai a legenda -- agora, e quando a
    pessoa trocar o estilo pelo painel (o `/api/subtitle` le o metadata)."""
    segmentos = []
    for k, cena in enumerate(roteiro["cenas"]):
        da_cena = [p for p in palavras if p.get("cena") == k]
        if da_cena:
            segmentos.append({
                "start": da_cena[0]["start"], "end": da_cena[-1]["end"], "text": cena["fala"],
                "words": [{"word": p["word"], "start": p["start"], "end": p["end"]}
                          for p in da_cena]})
    return {"language": (transcricao or {}).get("language") or idioma, "segments": segmentos}


def gerar_legenda(pasta: str, pedido: dict, transcricao: Optional[dict],
                  segundos: float) -> Optional[str]:
    preset = ((pedido["estilo"].get("legenda") or {}).get("preset")) or "karaoke_fill"
    if preset == "nenhuma" or not palavras_de(transcricao):
        return None
    import subtitles
    import template
    spec = {"captions": {"preset": preset}}
    kwargs = template.kwargs_de_legenda(spec)
    kwargs["margin_v"] = template.margem_vertical(spec)
    caminho = os.path.join(pasta, ARQUIVO_DA_LEGENDA)
    if not subtitles.generate_ass(transcricao, 0.0, segundos, caminho, **kwargs):
        return None
    return caminho


def texto_do_post(roteiro: dict) -> str:
    tags = " ".join(f"#{h}" for h in roteiro.get("hashtags") or [])
    return " ".join(p for p in (roteiro.get("descricao") or "", tags) if p).strip()


def metadata(pedido: dict, roteiro: dict, arquivo: str, segundos: float,
             transcricao: Optional[dict]) -> dict:
    texto = texto_do_post(roteiro)
    curto = {
        "start": 0.0, "end": round(segundos, 3),
        "video_title_for_youtube_short": roteiro["titulo"],
        "video_description_for_tiktok": texto,
        "video_description_for_instagram": texto,
        "viral_hook_text": roteiro["cenas"][0]["fala"] if roteiro.get("cenas") else "",
        "criacao": {"estilo_id": pedido.get("estilo_id"), "ideia": pedido.get("ideia") or "",
                    "cenas": len(roteiro.get("cenas") or [])},
    }
    return {"shorts": [curto],
            "transcript": transcricao or {"language": pedido.get("idioma") or "", "segments": []},
            "criacao": {"titulo": roteiro["titulo"], "arquivo": arquivo,
                        "canal_id": pedido.get("canal_id")}}


def criar(pasta: str) -> str:
    """Faz o video na pasta e devolve o nome do arquivo. Levanta
    `CriacaoFalhou` ou `midia_ia.MidiaIndisponivel` com a frase para o log."""
    pedido = _ler_json(os.path.join(pasta, ARQUIVO_DO_PEDIDO))
    if not pedido or not isinstance(pedido.get("estilo"), dict):
        raise CriacaoFalhou("O pedido da criacao (criacao.json) nao esta na pasta do projeto.")
    doc = estilos.normalizar(pedido["estilo"])
    pedido["estilo"] = doc

    with job_metrics.stage("c1_roteiro"):
        caminho_do_roteiro = os.path.join(pasta, ARQUIVO_DO_ROTEIRO)
        roteiro = _ler_json(caminho_do_roteiro)
        if roteiro is None:
            print("✍️ Escrevendo o roteiro...")
            roteiro = escrever_roteiro(doc, pedido.get("ideia") or "",
                                       estilos.nome_do_idioma(pedido.get("idioma")),
                                       pedido.get("ja_feitos") or [])
            _gravar_json(caminho_do_roteiro, roteiro)
        else:
            print("✍️ O roteiro ja estava pronto.")
        print(f"   \"{roteiro['titulo']}\" -- {len(roteiro['cenas'])} cenas")
        for i, cena in enumerate(roteiro["cenas"]):
            print(f"   {i + 1}. {cena['fala']}")

    with job_metrics.stage("c2_imagens"):
        imagens = gerar_imagens(pasta, pedido, roteiro)

    with job_metrics.stage("c3_voz"):
        voz = gerar_voz(pasta, pedido, roteiro)
        segundos = duracao_do_wav(voz)
        job_metrics.fact("spoken_seconds", round(segundos, 2))

    with job_metrics.stage("c4_legenda"):
        ouvida = transcrever(pasta, voz)
        palavras = montagem.palavras_do_roteiro([c["fala"] for c in roteiro["cenas"]],
                                                palavras_de(ouvida))
        transcricao = transcricao_do_roteiro(roteiro, palavras, ouvida,
                                             pedido.get("idioma") or "")
        legenda = gerar_legenda(pasta, pedido, transcricao, segundos)
        if legenda is None and ((doc.get("legenda") or {}).get("preset") != "nenhuma"):
            print("⚠️ O video sai sem legenda.")

    with job_metrics.stage("c5_montagem"):
        import ffmpeg_utils
        duracoes = montagem.duracoes_das_cenas([c["fala"] for c in roteiro["cenas"]],
                                               palavras, segundos)
        arquivo = f"{BASE}_clip_1.mp4"
        # Uma montagem anterior que nao chegou ao metadata deixou os dela: o
        # mais novo venceria na hora de servir, mas e lixo.
        for antigo in os.listdir(pasta):
            if antigo.startswith("subtitled_") and antigo.endswith(f"_{arquivo}"):
                os.remove(os.path.join(pasta, antigo))
        legendado = f"subtitled_{int(time.time())}_{arquivo}" if legenda else None
        temporario = os.path.join(pasta, f"montando_{arquivo}")
        temporario_legendado = os.path.join(pasta, "montando_legendado.mp4") if legenda else None
        print(f"🎞️ Montando {len(imagens)} cenas em {segundos:.1f}s...")
        montagem.montar(imagens, duracoes, voz, temporario, legenda=legenda,
                        saida_legendada=temporario_legendado,
                        video_args=ffmpeg_utils.video_encode_args(ffmpeg_utils.QUALITY_FAST),
                        video_args_legendada=ffmpeg_utils.video_encode_args(ffmpeg_utils.QUALITY),
                        audio_args=ffmpeg_utils.audio_encode_args())
        entregues = [(temporario, arquivo)] + ([(temporario_legendado, legendado)]
                                               if legenda else [])
        for origem, nome in entregues:
            destino = os.path.join(pasta, nome)
            os.replace(origem, destino)
            ffmpeg_utils.mark_ai_generated(destino, "imagens, voz e roteiro gerados por IA")

    _gravar_json(os.path.join(pasta, f"{BASE}_metadata.json"),
                 metadata(pedido, roteiro, arquivo, segundos, transcricao))
    print(f"CLIP_READY 0 {legendado or arquivo}")
    return legendado or arquivo


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Cria um video curto por IA na pasta de um job.")
    parser.add_argument("--pasta", required=True)
    args = parser.parse_args(argv)
    pasta = os.path.abspath(args.pasta)
    job_metrics.reset(pasta, BASE)
    inicio = time.time()
    try:
        criar(pasta)
    except (CriacaoFalhou, midia_ia.MidiaIndisponivel, estilos.EstiloInvalido) as e:
        print(f"❌ {e}")
        return 1
    finally:
        resumo = job_metrics.summary_line()
        if resumo:
            print("\n" + resumo)
        job_metrics.write()
    print(f"\n✅ Video criado em {time.time() - inicio:.0f}s.")
    return 0


if __name__ == "__main__":
    try:
        import linhas_inteiras
        linhas_inteiras.instalar()
    except Exception:
        pass
    sys.exit(main())
