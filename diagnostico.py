"""Por que este job demorou -- o numero e o ambiente, na mesma tela.

`python diagnostico.py`

Existe porque o relatorio do bloco 5.3 sabe dizer QUAL estagio dominou e nao
sabe dizer POR QUE. Ele termina em frases como "confira se a GPU esta mesmo em
uso" -- e quem le tem de ir conferir a mao, em dois lugares que ninguem lembra
de cor. Aqui a conferencia e feita.

**A conclusao pede as duas metades.** "A transcricao e 70% do tempo" nao e um
defeito: num video muito falado pode ser o certo. "O whisper esta em CPU"
tambem nao e, sozinho: numa maquina sem placa e a unica opcao. As duas juntas
sao uma frase acionavel, e e so essa frase que este modulo produz.

### Os dois padroes que ninguem escolheu

Nenhum dos dois grita; os dois sao o valor de fabrica:

- `WHISPER_DEVICE` nasce **`cpu`** (`subtitles.get_whisper_config`). E
  `--build-arg GPU=1` nao muda isso -- ele instala as libs de CUDA na imagem.
  Ver a placa e o `docker-compose.gpu.yml`, e USAR a placa e esta variavel.
- `FFMPEG_ENCODER` nasce **`x264`** (`ffmpeg_utils.video_encode_args`), ou
  seja, libx264 em CPU. E nao e um encode por corte: a cadeia e corte ->
  reenquadra -> [marca] -> [gancho] -> legenda, quatro ou cinco encodes do
  mesmo clipe, os dois primeiros a `-crf 18`.

### Onde ele le

Nos sidecars `<base>.timings.json` que o `main.py` deixa na pasta de cada job,
e nao no banco. Dois motivos: o sidecar e escrito em TODO job desde a Fase 0.5,
enquanto `jobs.timings_json` so existe desde o bloco 3.3; e um CLI que nao
precisa levantar o engine async le disco e pronto. O `/api/tempo` junta os
dois e continua sendo o caminho do painel.

`output/` e varrido pela limpeza por idade, entao isto responde sobre jobs
recentes. Para o historico inteiro, `/api/tempo`.

### Separado de proposito

`conclusoes()` e funcao pura sobre dois dicts -- e o CI exercita a conta sem
GPU, sem ffmpeg e sem job. As sondagens ficam em funcoes proprias, cada uma
capaz de devolver `None` para "nao deu para saber", que nunca e o mesmo que
"nao".
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Optional

import timings_report

#: Acima disto, um estagio e o assunto do job.
FATIA_QUE_DOMINA = 0.5

#: Quantos encodes do MESMO clipe a cadeia de um corte faz, no caminho comum
#: (corte, reenquadramento, legenda). Com marca d'agua e gancho ligados sao
#: cinco. Serve para dizer ao leitor que o custo do encoder e multiplicado.
ENCODES_POR_CORTE = 3


# --------------------------------------------------------------------------- #
# Sondagens -- cada uma devolve None quando nao deu para saber
# --------------------------------------------------------------------------- #

def whisper_configurado() -> dict:
    """O que o pipeline VAI pedir ao faster-whisper.

    Lido de `subtitles.get_whisper_config()` e nao reescrito aqui: dois lugares
    com os mesmos defaults divergem no dia em que um deles mudar.
    """
    try:
        import subtitles
        return dict(subtitles.get_whisper_config())
    except Exception:
        # O `subtitles` importa o `ffmpeg_utils`; se nem isso carregar, os
        # defaults publicados no .env.example ainda respondem a pergunta.
        return {"model_size": os.environ.get("WHISPER_MODEL", "small"),
                "device": os.environ.get("WHISPER_DEVICE", "cpu"),
                "compute_type": os.environ.get("WHISPER_COMPUTE", "int8")}


def cuda_para_o_whisper() -> Optional[bool]:
    """A placa esta ao alcance do faster-whisper? None = nao deu para saber.

    Pergunta ao **ctranslate2**, que e quem o faster-whisper usa de fato. O
    `torch.cuda.is_available()` responde por outra biblioteca: numa imagem em
    que so uma das duas enxerga a placa, ele daria a resposta errada com cara
    de certa.
    """
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return None


def nvenc_usavel() -> Optional[bool]:
    """O ffmpeg consegue mesmo abrir uma sessao h264_nvenc aqui?

    E a sonda que o proprio pipeline usa antes de cada encode, entao a resposta
    e a dele -- nao uma leitura de `ffmpeg -encoders`, que lista o encoder
    compilado mesmo sem driver para ele.
    """
    try:
        import ffmpeg_utils
        return bool(ffmpeg_utils.nvenc_available())
    except Exception:
        return None


def _inteiro_do_ambiente(nome: str, padrao: int) -> int:
    try:
        return int(os.environ.get(nome, str(padrao)))
    except (TypeError, ValueError):
        return padrao


def fatos_do_ambiente() -> dict:
    """Tudo o que decide velocidade e nao aparece na medicao."""
    cfg = whisper_configurado()
    return {
        "whisper_model": cfg.get("model_size"),
        "whisper_device": cfg.get("device"),
        "whisper_compute": cfg.get("compute_type"),
        "cuda_para_o_whisper": cuda_para_o_whisper(),
        "ffmpeg_encoder": os.environ.get("FFMPEG_ENCODER", "x264").strip().lower(),
        "nvenc_usavel": nvenc_usavel(),
        "clip_workers": _inteiro_do_ambiente("CLIP_WORKERS", 3),
        "teto_de_cortes": _inteiro_do_ambiente("CLIP_TARGET_MAX", 15),
    }


# --------------------------------------------------------------------------- #
# Leitura da medicao
# --------------------------------------------------------------------------- #

def sidecars(output_dir: str = "output") -> list:
    """Os `<base>.timings.json`, do mais recente para o mais antigo."""
    achados = []
    for caminho in glob.glob(os.path.join(output_dir, "*", "*.timings.json")):
        try:
            with open(caminho, "r", encoding="utf-8") as fh:
                dados = json.load(fh)
            if isinstance(dados, dict):
                achados.append((os.path.getmtime(caminho), dados))
        except (OSError, ValueError):
            continue     # um sidecar truncado nao derruba o diagnostico
    achados.sort(key=lambda par: par[0], reverse=True)
    return [dados for _, dados in achados]


# --------------------------------------------------------------------------- #
# A conta -- pura, e por isso o CI a exercita inteira
# --------------------------------------------------------------------------- #

def _fatia(agregado: dict, estagio: str) -> float:
    for e in agregado.get("estagios") or []:
        if e.get("estagio") == estagio:
            return float(e.get("fatia") or 0.0)
    return 0.0


def conclusoes(ambiente: dict, agregado: dict) -> list:
    """As frases que precisam das DUAS metades para existir.

    O relatorio sozinho diz "a transcricao domina" e manda conferir; o ambiente
    sozinho diz "o whisper esta em CPU", que numa maquina sem placa e apenas
    verdade. Juntar os dois e o que transforma medicao em proximo passo -- e
    nenhuma frase daqui sai sem os dois lados.
    """
    saida = []
    if not agregado.get("jobs"):
        saida.append(
            "Nenhum job medido em `output/`. Rode um video e volte -- sem "
            "medicao, qualquer conclusao sobre lentidao e chute, que e o que "
            "este projeto vem recusando em toda decisao.")
        return saida

    if agregado.get("jobs_com_medida_inflada"):
        saida.append(
            "A medicao destes jobs e anterior ao conserto de 16-set-2026: o "
            "laco de cortes somava o tempo de cada worker no mesmo estagio, "
            "entao o render vem multiplicado por ate `CLIP_WORKERS` e a ordem "
            "de culpa nao vale. Rode UM job novo antes de mexer em qualquer "
            "coisa.")

    transcricao = _fatia(agregado, "03_transcribe")
    render = _fatia(agregado, "05_06_render")
    cuda = ambiente.get("cuda_para_o_whisper")
    device = (ambiente.get("whisper_device") or "").lower()

    # --- transcricao -------------------------------------------------------
    if transcricao >= FATIA_QUE_DOMINA:
        pct = int(transcricao * 100)
        # `cuda is None` e "nao deu para saber", e NUNCA cai junto com "sim":
        # o `ctranslate2` nao importa fora do container, e um `else` que
        # tratasse os dois igual afirmaria que a placa esta em uso justamente
        # quando ninguem olhou. Dizer o que nao se sabe e o defeito que este
        # arquivo existe para nao cometer.
        if device == "cpu":
            if cuda is True:
                saida.append(
                    f"A transcricao e {pct}% do tempo E o whisper esta em CPU "
                    "com a placa disponivel. `WHISPER_DEVICE=cuda "
                    "WHISPER_COMPUTE=float16` no `.env`. Nao e o mesmo que "
                    "`--build-arg GPU=1`: aquele instala as libs de CUDA na "
                    "imagem, este escolhe usar.")
            elif cuda is False:
                saida.append(
                    f"A transcricao e {pct}% do tempo e o whisper esta em CPU "
                    "porque nao ha placa ao alcance dele. Ver a placa e o "
                    "`docker-compose.gpu.yml` (`-f docker-compose.yml -f "
                    "docker-compose.gpu.yml`); sem isso, `WHISPER_DEVICE=cuda` "
                    "cai para CPU em silencio e nada muda.")
            else:
                saida.append(
                    f"A transcricao e {pct}% do tempo e o whisper esta em CPU. "
                    "Nao deu para saber se ha placa ao alcance daqui -- rode "
                    "este diagnostico DENTRO do container para a resposta.")
        elif cuda is False:
            saida.append(
                f"A transcricao e {pct}% do tempo, `WHISPER_DEVICE={device}` "
                "esta pedido e a placa NAO esta ao alcance: isto e exatamente "
                "a queda silenciosa para CPU. O container nao ve a GPU.")
        elif cuda is True:
            saida.append(
                f"A transcricao e {pct}% do tempo ja com a placa em uso. O "
                f"modelo e `{ambiente.get('whisper_model')}` -- "
                "`large-v3-turbo` e mais rapido que `small` em GPU, e o "
                "`.env.example` ja registra essa combinacao.")
        else:
            saida.append(
                f"A transcricao e {pct}% do tempo com "
                f"`WHISPER_DEVICE={device}` pedido, mas nao deu para saber se "
                "a placa esta ao alcance -- e a queda para CPU e silenciosa. "
                "Rode este diagnostico DENTRO do container.")

    # --- render ------------------------------------------------------------
    encoder = (ambiente.get("ffmpeg_encoder") or "").lower()
    nvenc = ambiente.get("nvenc_usavel")
    if render >= FATIA_QUE_DOMINA or render >= 0.3:
        pct = int(render * 100)
        if encoder == "x264" and nvenc is True:
            saida.append(
                f"O render e {pct}% do tempo E o ffmpeg esta em libx264 com "
                "h264_nvenc utilizavel. `FFMPEG_ENCODER=auto` no `.env`. Pesa "
                f"mais do que parece: sao ~{ENCODES_POR_CORTE} encodes do "
                "MESMO clipe por corte (corte, reenquadramento, legenda), os "
                "dois primeiros a `-crf 18`.")
        elif encoder == "x264" and nvenc is False:
            saida.append(
                f"O render e {pct}% do tempo em libx264, e h264_nvenc nao "
                "abre sessao aqui. Sem placa util, o que resta e o numero de "
                f"cortes: o teto e {ambiente.get('teto_de_cortes')} "
                "(`CLIP_TARGET_MAX`), e cada corte custa a cadeia inteira.")
        elif nvenc is True and encoder in ("auto", "nvenc"):
            saida.append(
                f"O render e {pct}% do tempo ja com h264_nvenc. O que sobra e "
                f"o numero de cortes (teto {ambiente.get('teto_de_cortes')}, "
                "`CLIP_TARGET_MAX`) e quantos correm juntos "
                f"(`CLIP_WORKERS`={ambiente.get('clip_workers')}).")
        elif nvenc is None:
            saida.append(
                f"O render e {pct}% do tempo com `FFMPEG_ENCODER={encoder}`, "
                "mas nao deu para sondar o h264_nvenc daqui. Rode este "
                "diagnostico DENTRO do container.")

    # --- dentro do render --------------------------------------------------
    for e in agregado.get("substages") or []:
        if (e.get("fatia") or 0) >= 0.2:
            saida.append(
                f"Dentro do render, `{e['estagio']}` sozinho e "
                f"{int(e['fatia'] * 100)}% da parede do job.")

    if not saida:
        saida.append(
            "Nenhum estagio domina e o ambiente nao tem nada obviamente "
            "errado. O tempo esta distribuido -- veja a tabela acima antes de "
            "mexer em qualquer coisa.")
    return saida


# --------------------------------------------------------------------------- #
# Saida
# --------------------------------------------------------------------------- #

def _sim_nao(valor) -> str:
    if valor is None:
        return "nao deu para saber"
    return "sim" if valor else "nao"


def texto(ambiente: dict, agregado: dict) -> str:
    linhas = ["", "=" * 72, "  POR QUE ESTA DEMORANDO", "=" * 72, ""]

    linhas.append("AMBIENTE (o que decide velocidade e nao aparece na medicao)")
    linhas.append(f"  whisper            {ambiente.get('whisper_model')} / "
                  f"{ambiente.get('whisper_device')} / "
                  f"{ambiente.get('whisper_compute')}")
    linhas.append(f"  placa p/ o whisper {_sim_nao(ambiente.get('cuda_para_o_whisper'))}")
    linhas.append(f"  ffmpeg             {ambiente.get('ffmpeg_encoder')}"
                  f"   (h264_nvenc utilizavel: "
                  f"{_sim_nao(ambiente.get('nvenc_usavel'))})")
    linhas.append(f"  cortes             ate {ambiente.get('teto_de_cortes')}, "
                  f"{ambiente.get('clip_workers')} em paralelo")
    linhas.append("")

    jobs = agregado.get("jobs") or 0
    linhas.append(f"MEDICAO ({jobs} job(s) em output/)")
    if jobs:
        fator = agregado.get("fator_tempo_real")
        if fator:
            linhas.append(f"  cada minuto de video custou {fator:.1f} min de "
                          "processamento")
        linhas.append(f"  parede total       {agregado.get('wall_seconds')}s")
        for e in agregado.get("estagios") or []:
            fatia = e.get("fatia")
            marca = f"{int(fatia * 100):>3}%" if fatia is not None else "   ?"
            linhas.append(f"    {e['estagio']:<18} {e['seconds']:>8.1f}s  {marca}")
        for e in agregado.get("substages") or []:
            fatia = e.get("fatia")
            marca = f"{int(fatia * 100):>3}%" if fatia is not None else "   ?"
            linhas.append(f"    └ {e['estagio']:<16} {e['seconds']:>8.1f}s  {marca}")
        fora = agregado.get("fora_de_estagio_seconds")
        if fora:
            linhas.append(f"    {'(fora de estagio)':<18} {fora:>8.1f}s")
    linhas.append("")

    linhas.append("O QUE ISSO QUER DIZER")
    for c in conclusoes(ambiente, agregado):
        linhas.append(f"  - {c}")
    linhas.append("")
    return "\n".join(linhas)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    saida_dir = argv[0] if argv else os.environ.get("OUTPUT_DIR", "output")
    medidos = sidecars(saida_dir)
    print(texto(fatos_do_ambiente(), timings_report.agregar(medidos)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
