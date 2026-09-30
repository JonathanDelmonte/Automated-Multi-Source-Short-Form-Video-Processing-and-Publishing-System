"""A montagem do video de IA (etapa 7.7, ADR-013): as imagens das cenas com
movimento lento, a narracao e a legenda, num ffmpeg so, em 1080x1920 -- ou em
1920x1080 no episodio longo (7.8), que e a mesma montagem deitada.

- **Cada cena dura o tempo da propria fala.** O tempo vem da narracao
  transcrita (o whisper da o tempo de cada palavra), e nao de uma conta de
  caracteres: a voz sintetizada acelera e respira do jeito dela.
- **O movimento e o Ken Burns**: aproximar, afastar ou deslizar devagar, um
  diferente por cena, na ordem (nada sorteado -- o mesmo roteiro da o mesmo
  video). O `zoompan` treme quando a imagem de entrada e pequena; ela entra
  ampliada 1,5x, que e o meio-termo entre tremer e custar caro.
- **A legenda mostra o ROTEIRO, no tempo da voz** (`palavras_do_roteiro`): o
  whisper so da o tempo de cada palavra. Ele erra justamente o que mais
  aparece num canal de historias -- o nome do personagem --, e quem escreveu o
  texto nos sabemos.
- **Um grafo so para as duas saidas**: o video limpo e o legendado saem do
  mesmo movimento de camera (a parte cara), como o pipeline de cortes entrega
  `<base>_clip_1.mp4` e `subtitled_<ts>_<base>_clip_1.mp4` -- e o limpo que
  deixa a pessoa trocar o estilo da legenda depois, sem queimar uma por cima
  da outra.

O que monta o comando e puro; `montar` so o executa. O teste roda o ffmpeg de
verdade quando ele existe.
"""
from __future__ import annotations

import difflib
import os
import subprocess
import unicodedata
from typing import Optional, Sequence

LARGURA, ALTURA = 1080, 1920
#: O episodio longo (7.8) e horizontal, para o YouTube.
LARGURA_HORIZONTAL, ALTURA_HORIZONTAL = 1920, 1080
QUADROS_POR_SEGUNDO = 30
#: A pausa entre dois blocos de narracao do episodio: cai entre duas cenas,
#: onde a voz ja respiraria.
PAUSA_ENTRE_BLOCOS_S = 0.6
#: A imagem entra maior que a saida para o movimento nao tremer.
AMPLIACAO = 1.5
#: Quanto a camera anda numa cena (15%): perceptivel sem enjoar.
MOVIMENTO = 0.15
#: Cena mais curta que isto some no piscar; a sobra vai para a vizinha.
CENA_MINIMA_S = 1.2

MOVIMENTOS = ("aproximar", "afastar", "direita", "esquerda")


def _pasta_de_fontes() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


def _escapar(valor: str) -> str:
    """Caminho dentro de filtro do ffmpeg (ver `ffmpeg_utils.escape_filter_value`)."""
    return valor.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _chave(palavra) -> str:
    """A palavra para comparar: minuscula, sem acento e sem pontuacao."""
    sem = unicodedata.normalize("NFKD", str(palavra or ""))
    return "".join(c for c in sem.lower() if c.isalnum() and not unicodedata.combining(c))


def _dividir(tempos: list, escritas: list, i1: int, i2: int, inicio: float, fim: float) -> None:
    """Reparte [inicio, fim] entre as palavras escritas i1..i2, pelo tamanho."""
    pesos = [max(1, len(escritas[i][1])) for i in range(i1, i2)]
    total = float(sum(pesos)) or 1.0
    t = inicio
    for i, peso in zip(range(i1, i2), pesos):
        dura = max(0.0, fim - inicio) * peso / total
        tempos[i] = (t, t + dura)
        t += dura


def palavras_do_roteiro(falas: Sequence[str], ouvidas: Sequence[dict]) -> list:
    """As palavras do ROTEIRO, cada uma com o tempo em que a voz a disse.

    O whisper ouve a narracao e erra o que mais aparece: o nome do personagem
    ("Lulu" vira "Lulú"), o numero ("3" vira "tres"). Quem escreveu o texto
    nos sabemos -- e o roteiro --, entao a legenda mostra o roteiro, e do
    whisper vem so o TEMPO. O casamento e o do `difflib` sobre as palavras sem
    acento e sem pontuacao: a que casa leva o tempo da ouvida; um trecho
    trocado reparte o tempo do trecho ouvido pelo tamanho de cada palavra
    escrita; a que o whisper nao ouviu fica no intervalo entre as vizinhas.

    Cada palavra sai com o indice da cena (`cena`), que da a fronteira exata
    das cenas, e com o espaco na frente, que e a marca de palavra nova do
    `subtitles.merge_continuation_words`. Sem palavras ouvidas, lista vazia.
    """
    escritas = [(k, w) for k, fala in enumerate(falas) for w in str(fala or "").split()]
    ouvidas = [w for w in ouvidas or () if isinstance(w, dict)
               and w.get("start") is not None and w.get("end") is not None]
    if not escritas or not ouvidas:
        return []
    a = [_chave(w) for _, w in escritas]
    b = [_chave(w.get("word")) for w in ouvidas]
    tempos: list = [None] * len(escritas)
    casador = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in casador.get_opcodes():
        if tag == "equal":
            for d in range(i2 - i1):
                o = ouvidas[j1 + d]
                tempos[i1 + d] = (float(o["start"]), float(o["end"]))
        elif tag == "replace":
            _dividir(tempos, escritas, i1, i2,
                     float(ouvidas[j1]["start"]), float(ouvidas[j2 - 1]["end"]))
    # O que o whisper nao ouviu fica entre as vizinhas.
    n, i = len(escritas), 0
    while i < n:
        if tempos[i] is not None:
            i += 1
            continue
        j = i
        while j < n and tempos[j] is None:
            j += 1
        antes = tempos[i - 1][1] if i > 0 else 0.0
        depois = tempos[j][0] if j < n else float(ouvidas[-1]["end"])
        _dividir(tempos, escritas, i, j, antes, max(antes, depois))
        i = j
    return [{"word": " " + w, "start": round(ini, 3), "end": round(max(ini, fim), 3), "cena": k}
            for (k, w), (ini, fim) in zip(escritas, tempos)]


def duracoes_das_cenas(falas: Sequence[str], palavras: Sequence[dict],
                       total_s: float) -> list:
    """Quanto dura cada cena, a partir das palavras da narracao.

    Com as palavras do `palavras_do_roteiro` (cada uma sabe a sua `cena`), a
    cena k comeca exatamente quando a voz comeca a fala dela. Com palavras que
    nao sabem a cena (as do whisper cru, que nao batem uma a uma com o
    roteiro), a fronteira da cena k e a palavra na mesma PROPORCAO do texto:
    se as cenas 1 e 2 sao 30% dos caracteres, a cena 3 comeca na palavra a 30%
    da lista. Sem palavras (o whisper falhou), vale a proporcao de caracteres
    sobre a duracao total.

    A primeira cena comeca em 0 e a ultima termina no fim do audio, sem buraco:
    a soma e sempre `total_s`.
    """
    n = len(falas)
    if n == 0:
        return []
    total_s = max(float(total_s), 0.1)
    primeiras: dict = {}
    for p in palavras:
        k = p.get("cena") if isinstance(p, dict) else None
        if isinstance(k, int) and k not in primeiras and p.get("start") is not None:
            primeiras[k] = float(p["start"])
    tamanhos = [max(1, len(f)) for f in falas]
    soma = float(sum(tamanhos))
    acumulado, fracoes = 0, []
    for t in tamanhos[:-1]:
        acumulado += t
        fracoes.append(acumulado / soma)
    inicios_das_palavras = [float(p.get("start", 0.0)) for p in palavras
                            if isinstance(p, dict) and p.get("start") is not None]
    fronteiras = []
    if all(k in primeiras for k in range(1, n)):
        fronteiras = [min(max(primeiras[k], 0.0), total_s) for k in range(1, n)]
    for f in ([] if fronteiras or n == 1 else fracoes):
        if inicios_das_palavras:
            i = min(len(inicios_das_palavras) - 1, int(round(f * len(inicios_das_palavras))))
            fronteiras.append(min(max(inicios_das_palavras[i], 0.0), total_s))
        else:
            fronteiras.append(f * total_s)
    # Monotonas e dentro do audio.
    for i in range(1, len(fronteiras)):
        fronteiras[i] = max(fronteiras[i], fronteiras[i - 1])
    pontos = [0.0] + fronteiras + [total_s]
    duracoes = [max(0.0, pontos[i + 1] - pontos[i]) for i in range(n)]
    return _sem_cena_relampago(duracoes)


def _sem_cena_relampago(duracoes: list) -> list:
    """A cena curta demais cede o tempo para a vizinha (a seguinte, ou a
    anterior se for a ultima). A soma nao muda."""
    duracoes = list(duracoes)
    i = 0
    while i < len(duracoes) and len(duracoes) > 1:
        if duracoes[i] < CENA_MINIMA_S:
            alvo = i + 1 if i + 1 < len(duracoes) else i - 1
            falta = CENA_MINIMA_S - duracoes[i]
            doa = min(falta, max(0.0, duracoes[alvo] - CENA_MINIMA_S))
            duracoes[i] += doa
            duracoes[alvo] -= doa
        i += 1
    return duracoes


def filtro_da_cena(indice: int, entrada: int, segundos: float,
                   movimento: Optional[str] = None, largura: int = LARGURA,
                   altura: int = ALTURA) -> str:
    """O grafo de uma cena: cobre o quadro (corta o que sobra), amplia e anda.
    Devolve o rotulo `[vN]`."""
    quadros = max(1, int(round(segundos * QUADROS_POR_SEGUNDO)))
    grande_l, grande_a = int(largura * AMPLIACAO), int(altura * AMPLIACAO)
    movimento = movimento or MOVIMENTOS[indice % len(MOVIMENTOS)]
    passo = f"{MOVIMENTO}*on/{quadros}"
    if movimento == "aproximar":
        z, x, y = f"1+{passo}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif movimento == "afastar":
        z, x, y = f"{1 + MOVIMENTO}-{passo}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif movimento == "direita":
        z = f"{1 + MOVIMENTO}"
        x, y = f"(iw-iw/zoom)*on/{quadros}", "ih/2-(ih/zoom/2)"
    else:  # esquerda
        z = f"{1 + MOVIMENTO}"
        x, y = f"(iw-iw/zoom)*(1-on/{quadros})", "ih/2-(ih/zoom/2)"
    return (f"[{entrada}:v]scale={grande_l}:{grande_a}:force_original_aspect_ratio=increase,"
            f"crop={grande_l}:{grande_a},setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={quadros}:s={largura}x{altura}"
            f":fps={QUADROS_POR_SEGUNDO},setsar=1,format=yuv420p[v{indice}]")


def _saida(mapa: str, audio: int, video_args: Optional[list], audio_args: Optional[list],
           arquivo: str) -> list:
    return (["-map", f"[{mapa}]", "-map", f"{audio}:a"]
            + list(video_args or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
            + ["-pix_fmt", "yuv420p", "-r", str(QUADROS_POR_SEGUNDO)]
            + list(audio_args or ["-c:a", "aac", "-b:a", "160k"])
            + ["-shortest", "-movflags", "+faststart", arquivo])


def comando(imagens: Sequence[str], duracoes: Sequence[float], audio: str, saida: str,
            legenda: Optional[str] = None, video_args: Optional[list] = None,
            audio_args: Optional[list] = None, saida_legendada: Optional[str] = None,
            video_args_legendada: Optional[list] = None, largura: int = LARGURA,
            altura: int = ALTURA) -> list:
    """O comando do ffmpeg da montagem inteira.

    Com `legenda` e `saida_legendada`, saem dois arquivos do mesmo grafo: o
    limpo em `saida` e o legendado em `saida_legendada`. So com `legenda`, ela
    queima em `saida`."""
    if len(imagens) != len(duracoes) or not imagens:
        raise ValueError("uma duracao por imagem")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for img in imagens:
        cmd += ["-i", img]
    cmd += ["-i", audio]
    voz = len(imagens)
    partes = [filtro_da_cena(i, i, d, largura=largura, altura=altura)
              for i, d in enumerate(duracoes)]
    juntas = "".join(f"[v{i}]" for i in range(len(imagens)))
    partes.append(f"{juntas}concat=n={len(imagens)}:v=1:a=0[vc]")
    queimar = (f"ass=filename='{_escapar(legenda)}':"
               f"fontsdir='{_escapar(_pasta_de_fontes())}'") if legenda else None
    if queimar and saida_legendada:
        partes.append("[vc]split=2[vs][va]")
        partes.append(f"[va]{queimar}[vl]")
        return (cmd + ["-filter_complex", ";".join(partes)]
                + _saida("vs", voz, video_args, audio_args, saida)
                + _saida("vl", voz, video_args_legendada or video_args, audio_args,
                         saida_legendada))
    final = "vc"
    if queimar:
        partes.append(f"[vc]{queimar}[vl]")
        final = "vl"
    return (cmd + ["-filter_complex", ";".join(partes)]
            + _saida(final, voz, video_args, audio_args, saida))


def montar(imagens: Sequence[str], duracoes: Sequence[float], audio: str, saida: str,
           legenda: Optional[str] = None, video_args: Optional[list] = None,
           audio_args: Optional[list] = None, timeout: float = 1800,
           saida_legendada: Optional[str] = None,
           video_args_legendada: Optional[list] = None, largura: int = LARGURA,
           altura: int = ALTURA) -> None:
    """Roda a montagem. Levanta RuntimeError com o fim do erro do ffmpeg."""
    cmd = comando(imagens, duracoes, audio, saida, legenda, video_args, audio_args,
                  saida_legendada, video_args_legendada, largura, altura)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    saidas = [saida] + ([saida_legendada] if legenda and saida_legendada else [])
    if r.returncode != 0 or any(not os.path.exists(a) or os.path.getsize(a) < 1024
                                for a in saidas):
        raise RuntimeError(f"a montagem falhou: {(r.stderr or '').strip()[-600:]}")


# --------------------------------------------------------------------------- #
# O episodio longo (7.8): a narracao em blocos e a legenda deitada
# --------------------------------------------------------------------------- #

def juntar_wavs(entradas: Sequence[str], saida: str,
                pausa_s: float = PAUSA_ENTRE_BLOCOS_S) -> float:
    """Junta os blocos de narracao num WAV so, com uma pausa entre eles, e
    devolve a duracao.

    Os blocos vem todos do mesmo modelo de voz, entao o formato bate e a
    juncao e so encostar as amostras (o modulo `wave`, sem processo). Se um
    bloco veio noutro formato (o modelo de reserva, com outra taxa), quem junta
    e o ffmpeg, que converte todos para o do primeiro."""
    import wave
    if not entradas:
        raise ValueError("nenhum bloco de narracao")
    formatos, quadros = [], []
    for caminho in entradas:
        with wave.open(caminho, "rb") as w:
            formatos.append((w.getnchannels(), w.getsampwidth(), w.getframerate()))
            quadros.append(w.readframes(w.getnframes()))
    canais, largura, taxa = formatos[0]
    temporario = saida + ".tmp"
    if all(f == formatos[0] for f in formatos):
        silencio = b"\x00" * (int(round(pausa_s * taxa)) * canais * largura)
        with wave.open(temporario, "wb") as w:
            w.setnchannels(canais)
            w.setsampwidth(largura)
            w.setframerate(taxa)
            for i, bloco in enumerate(quadros):
                if i:
                    w.writeframes(silencio)
                w.writeframes(bloco)
    else:
        _juntar_com_ffmpeg(entradas, temporario, pausa_s, canais, taxa)
    os.replace(temporario, saida)
    with wave.open(saida, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def _juntar_com_ffmpeg(entradas: Sequence[str], saida: str, pausa_s: float,
                       canais: int, taxa: int) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for caminho in entradas:
        cmd += ["-i", caminho]
    layout = "mono" if canais == 1 else "stereo"
    partes, rotulos = [], []
    for i in range(len(entradas)):
        pausa = f",apad=pad_dur={pausa_s:g}" if i < len(entradas) - 1 else ""
        partes.append(f"[{i}:a]aresample={taxa},aformat=sample_fmts=s16:"
                      f"channel_layouts={layout}{pausa}[a{i}]")
        rotulos.append(f"[a{i}]")
    partes.append(f"{''.join(rotulos)}concat=n={len(entradas)}:v=0:a=1[voz]")
    cmd += ["-filter_complex", ";".join(partes), "-map", "[voz]", "-c:a", "pcm_s16le",
            "-f", "wav", saida]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(saida):
        raise RuntimeError(f"a juncao da narracao falhou: {(r.stderr or '').strip()[-400:]}")


#: A legenda no video horizontal. O ASS mede a letra pela ALTURA do quadro
#: (`PlayResY` 288), entao o preset do Short num 1920x1080 sairia com a letra
#: do Short -- uns 13% da altura, grande demais para minutos de video. Aqui ela
#: cai para uns 7%, e o bloco leva mais texto, porque a linha e mais larga.
ESCALA_DA_LETRA_HORIZONTAL = 0.55
ESCALA_DO_BLOCO_HORIZONTAL = 2.2
#: ~7% da altura: acima da barra do player, que cobre o pe do video.
MARGEM_HORIZONTAL = 20


def legenda_horizontal(kwargs: dict) -> dict:
    """Os argumentos do `subtitles.generate_ass` de um preset, para o quadro
    deitado."""
    k = dict(kwargs)
    k["fontsize"] = max(12, int(round(float(k.get("fontsize") or 16)
                                      * ESCALA_DA_LETRA_HORIZONTAL)))
    k["max_chars"] = min(48, int(round(float(k.get("max_chars") or 20)
                                       * ESCALA_DO_BLOCO_HORIZONTAL)))
    k["max_duration"] = min(4.0, round(float(k.get("max_duration") or 2.0)
                                       * ESCALA_DO_BLOCO_HORIZONTAL, 2))
    k["margin_v"] = MARGEM_HORIZONTAL
    return k
