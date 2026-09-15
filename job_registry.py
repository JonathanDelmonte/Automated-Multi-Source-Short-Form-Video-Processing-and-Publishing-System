"""O pipeline escrevendo no banco: `sources`, `jobs` e `clips` (Fase 3, bloco 3.3).

Ate aqui o schema da secao 7 existia e so `templates` era escrita por um
caminho do pipeline. Este modulo fecha a pendencia registrada no fim da Fase 1
-- e nao e arrumacao: `publications` tem **FK composta para `clips`**, entao
sem linha de corte no banco nao ha publicacao a gravar, e a Fase 3 inteira
ficaria sem memoria.

**Tudo aqui falha aberto, sem excecao.** O banco e o registro do pipeline, nao
um participante dele: um SQLite corrompido, um Postgres fora do ar ou um schema
desatualizado nao podem derrubar um job que produziria cortes. Mesma postura do
`db_seed.seed()` no lifespan, e pelo mesmo motivo -- o pipeline funciona sem
banco, e sempre funcionou. Cada funcao devolve `None`/`False` e imprime uma
linha; nenhuma levanta.

**O indice de palavra e derivado, e a secao 2 previa o contrario.** Ela desenhou
o LLM devolvendo contagem de item em lista ("LLM erra aritmetica de tempo; nao
erra contagem de item em lista"), e o pipeline herdado pede segundos. A
derivacao a partir da transcricao e exata e devolve a coluna ao seu
significado; o unico caso sem resposta e o video sem fala, onde nao ha palavra
nenhuma -- e por isso as colunas sao anulaveis desde a migracao `4a7e1c30d8b2`.
Os segundos exatos, que sao a saida real do modelo, ficam no `rubric_json`.
"""
from __future__ import annotations

import os
from typing import Optional

import db
import db_models

#: `PIPELINE_STAGES` do `app.py` nomeia os estagios com o numero da secao 4
#: (`01_ingest`); `db_models.STAGES` usa o nome curto da secao 7. Sao as duas
#: metades da mesma lista e a traducao mora aqui, com um teste de paridade que
#: quebra se um marcador novo aparecer sem destino.
#:
#: `05_06_render` cai em `reframe` porque o pipeline emite UM marcador para os
#: estagios 05 (cortar) e 06 (reenquadrar) juntos -- eles rodam na mesma funcao.
ESTAGIO_DO_MARCADOR = {
    "01_ingest": "ingest",
    "02_probe": "probe",
    "03_transcribe": "transcribe",
    "04_detect": "detect",
    "05_06_render": "reframe",
}


def _avisar(erro: Exception, o_que: str) -> None:
    print(f"⚠️  Banco ({o_que}): {erro}")


# --------------------------------------------------------------------------- #
# Derivacao do indice de palavra
# --------------------------------------------------------------------------- #

def palavras_do_transcript(transcript) -> list:
    """A lista plana de palavras da transcricao, ou vazia.

    A transcricao do pipeline e `{"language": ..., "segments": [...]}` e cada
    segmento traz `words` com `{'word','start','end'}`. Um video mudo chega
    aqui como `{"language": "none", "segments": []}`, que e o caso em que a
    faixa de palavras nao existe.
    """
    if not isinstance(transcript, dict):
        return []
    palavras = []
    for segmento in transcript.get("segments") or []:
        if not isinstance(segmento, dict):
            continue
        for palavra in segmento.get("words") or []:
            if isinstance(palavra, dict) and "start" in palavra and "end" in palavra:
                palavras.append(palavra)
    return palavras


def faixa_de_palavras(palavras: list, inicio_s: float, fim_s: float):
    """`(start_word_idx, end_word_idx)` para um corte em segundos, ou
    `(None, None)`.

    **Fim exclusivo**, como fatia de lista: `palavras[inicio:fim]` e o texto do
    corte. Nao e detalhe -- o CHECK da tabela exige `end > start`, e com fim
    inclusivo um corte de uma palavra so teria `end == start` e seria recusado.

    Uma palavra entra se ela **encosta** no intervalo, e nao se esta contida
    nele: o corte e feito em segundos e quase nunca cai na fronteira exata de
    uma palavra, entao exigir contencao cortaria a primeira e a ultima de todo
    corte.
    """
    if not palavras:
        return None, None
    try:
        inicio_s = float(inicio_s)
        fim_s = float(fim_s)
    except (TypeError, ValueError):
        return None, None

    primeiro = None
    ultimo = None
    for i, palavra in enumerate(palavras):
        try:
            p_inicio = float(palavra["start"])
            p_fim = float(palavra["end"])
        except (TypeError, ValueError, KeyError):
            continue
        if p_fim <= inicio_s or p_inicio >= fim_s:
            continue
        if primeiro is None:
            primeiro = i
        ultimo = i
    if primeiro is None:
        # Corte num trecho sem fala de um video que fala em outros trechos.
        return None, None
    return primeiro, ultimo + 1


def _score(clip: dict):
    """O `predicted_score` do modelo, preso em 0..100.

    Preso, e nao validado: o CHECK da coluna recusa fora da faixa, e um modelo
    que devolveu 120 derrubaria a gravacao dos OUTROS cortes do mesmo job.
    Melhor um numero no teto que um job sem registro nenhum.
    """
    bruto = clip.get("predicted_score")
    if bruto is None:
        return None
    try:
        return max(0.0, min(100.0, float(bruto)))
    except (TypeError, ValueError):
        return None


def _rubrica(clip: dict, visual: bool, indice: int = 0) -> dict:
    """Tudo o que se sabe do corte e que a secao 7 nao deu coluna.

    Os **segundos exatos** entram aqui. A secao 7 nao tem coluna de tempo por
    decisao (a secao 2 escolheu indice de palavra), e inventar uma seria
    desfazer essa escolha por conveniencia -- mas `start`/`end` sao literalmente
    a saida do modelo sobre este corte, que e o que `rubric_json` guarda. Sem
    eles, o corte exato que gerou o arquivo so existiria no arquivo.

    `clip_index` e a posicao do corte no job -- o "Clip 3" do painel, do nome do
    arquivo e da URL. Sem ele, ligar uma linha de `clips` ao corte que a pessoa
    esta vendo dependeria de ordenar por `created_at` e contar, que funciona
    ate dois inserts caírem no mesmo microssegundo. Uma publicacao apontando
    para o corte errado e o tipo de erro que so se descobre depois de publicado.
    """
    rubrica = {"visual": visual, "clip_index": int(indice)}
    for origem, destino in (("start", "start_s"), ("end", "end_s")):
        try:
            rubrica[destino] = round(float(clip.get(origem)), 3)
        except (TypeError, ValueError):
            pass
    for campo in ("source_window_id", "viral_hook_text",
                  "video_title_for_youtube_short"):
        valor = clip.get(campo)
        if valor:
            rubrica[campo] = valor
    return rubrica


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #

async def registrar_fonte(adapter: str, entrada: str,
                          duration_ms: Optional[int] = None,
                          storage_key: Optional[str] = None) -> Optional[str]:
    """Cria a linha de `sources` e devolve o id, ou None se nao deu."""
    try:
        async with db.tenant() as t:
            fonte = t.add(db_models.Source(
                adapter=adapter, input=entrada,
                duration_ms=duration_ms if duration_ms and duration_ms > 0 else None,
                storage_key=storage_key))
            await t.commit()
            return fonte.id
    except Exception as e:
        _avisar(e, f"registrar fonte {adapter}")
        return None


async def registrar_job(job_id: str, source_id: str) -> bool:
    """Cria a linha de `jobs` com o **mesmo id do pipeline**.

    `db_models.new_id` ja previa isto: o `job_id` que o `app.py` gera e um
    uuid4, entao a tabela aceita sem conversao e o id do painel, o da pasta em
    disco e o do banco sao o mesmo. Um id proprio aqui obrigaria a manter um
    mapa e a traduzir em todo lugar que junta as duas metades.
    """
    if not source_id:
        return False
    try:
        async with db.tenant() as t:
            t.add(db_models.Job(id=job_id, source_id=source_id,
                                stage="ingest", status="queued"))
            await t.commit()
            return True
    except Exception as e:
        _avisar(e, f"registrar job {job_id}")
        return False


async def marcar_job(job_id: str, *, status: Optional[str] = None,
                     marcador: Optional[str] = None,
                     error: Optional[str] = None,
                     timings: Optional[dict] = None) -> bool:
    """Atualiza a linha do job. Um job que nunca foi gravado nao e erro."""
    estagio = ESTAGIO_DO_MARCADOR.get(marcador or "")
    try:
        async with db.tenant() as t:
            job = await t.get(db_models.Job, job_id)
            if job is None:
                return False
            if status:
                job.status = status
            if estagio:
                job.stage = estagio
            if error is not None:
                # A coluna e Text, mas um traceback inteiro num campo de erro e
                # log no lugar errado -- o log do job ja tem tudo.
                job.error = error[:2000]
            if timings is not None:
                job.timings_json = timings
            if status in ("completed", "failed"):
                job.finished_at = db_models._now()
            await t.commit()
            return True
    except Exception as e:
        _avisar(e, f"atualizar job {job_id}")
        return False


async def registrar_clipes(job_id: str, shorts: list, transcript=None,
                           arquivos: Optional[dict] = None) -> int:
    """Grava os cortes de um job e devolve quantos entraram.

    `arquivos` mapeia indice -> nome do arquivo renderizado, que vira
    `render_key`. Vem de fora porque quem sabe qual e a versao ATUAL de um
    corte (limpo, com legenda, recortado) e o `app.py`.

    Idempotente por job: se ja ha corte gravado para este job, nao grava de
    novo. Um job retomado depois de um redeploy roda o fim do pipeline outra
    vez, e sem isto o mesmo corte apareceria duas vezes no banco -- e
    `publications` tem unicidade por corte, nao por conteudo.
    """
    if not shorts:
        return 0
    palavras = palavras_do_transcript(transcript)
    arquivos = arquivos or {}
    try:
        async with db.tenant() as t:
            job = await t.get(db_models.Job, job_id)
            if job is None:
                return 0
            ja_tem = await t.all(db_models.Clip,
                                 db_models.Clip.job_id == job_id)
            if ja_tem:
                return 0
            gravados = 0
            for i, clip in enumerate(shorts):
                if not isinstance(clip, dict):
                    continue
                inicio, fim = faixa_de_palavras(palavras, clip.get("start"),
                                                clip.get("end"))
                t.add(db_models.Clip(
                    job_id=job_id,
                    start_word_idx=inicio, end_word_idx=fim,
                    score=_score(clip),
                    rubric_json=_rubrica(clip, visual=not palavras, indice=i),
                    render_key=arquivos.get(i)))
                gravados += 1
            await t.commit()
            return gravados
    except Exception as e:
        _avisar(e, f"registrar cortes de {job_id}")
        return 0


def adapter_de(url: Optional[str], caminho: Optional[str] = None) -> str:
    """O id de adapter para a coluna `sources.adapter`.

    Import tardio do `sources` pelo mesmo motivo de sempre: manter este modulo
    leve. Uma URL que nenhum adapter reconhece cai em `direct`, que e o que o
    `DirectUrlAdapter` faria -- recusar aqui transformaria um registro
    impossivel numa fonte nao gravada.
    """
    if not url:
        return "upload"
    try:
        import sources
        return sources.resolve(url).id
    except Exception:
        return "direct"


async def clipe_do_job(job_id: str, indice: int):
    """A linha de `clips` do corte numero `indice` deste job, ou None.

    Procura por `rubric_json.clip_index` em vez de contar por `created_at`:
    uma publicacao apontando para o corte errado nao da erro nenhum, so publica
    o video errado.
    """
    try:
        async with db.tenant() as t:
            cortes = await t.all(db_models.Clip,
                                 db_models.Clip.job_id == job_id)
            for corte in cortes:
                if (corte.rubric_json or {}).get("clip_index") == int(indice):
                    return corte
            return None
    except Exception as e:
        _avisar(e, f"achar corte {indice} de {job_id}")
        return None


async def atualizar_render_key(clip_id: str, render_key: str) -> bool:
    """Aponta a linha do corte para o arquivo ATUAL.

    O `render_key` foi gravado no fim do job; desde entao o corte pode ter
    ganhado legenda ou sido recortado, e e o arquivo novo que vai ser
    publicado. Atualizar no momento de publicar deixa a linha descrevendo o que
    foi ao ar, e nao o que existia quando o job acabou.
    """
    if not render_key:
        return False
    try:
        async with db.tenant() as t:
            corte = await t.get(db_models.Clip, clip_id)
            if corte is None:
                return False
            corte.render_key = render_key
            await t.commit()
            return True
    except Exception as e:
        _avisar(e, f"atualizar render_key de {clip_id}")
        return False
