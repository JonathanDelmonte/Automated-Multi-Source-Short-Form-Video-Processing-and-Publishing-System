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


def libs_de_cuda_na_imagem() -> Optional[bool]:
    """A imagem foi construida com `--build-arg GPU=1`?

    Pergunta ao `LD_LIBRARY_PATH`, que o Dockerfile aponta para as libs de CUDA
    instaladas por pip -- e o comentario dele diz, com estas palavras, que os
    caminhos "simplesmente nao existem em imagens CPU". Entao a existencia da
    pasta E a resposta, e ela continua certa se o Dockerfile mudar os caminhos:
    a lista vem dele, nao daqui.

    Separar isto de `cuda_para_o_whisper` e o ponto. Os dois dao `nao` pelo
    mesmo sintoma e a correcao e OUTRA -- imagem sem as libs pede uma
    reconstrucao de 15 a 40 minutos; placa nao reservada pede um `up` de
    segundos. Sem separar, a escolha entre as duas e cara ou coroa.
    """
    caminhos = [p for p in (os.environ.get("LD_LIBRARY_PATH") or "").split(os.pathsep)
                if p and "nvidia" in p]
    if not caminhos:
        return None      # nem o `ENV` do Dockerfile chegou: nao da para saber
    return any(os.path.isdir(p) and os.listdir(p) for p in caminhos)


def driver_no_container() -> Optional[bool]:
    """O runtime da NVIDIA injetou o driver aqui dentro?

    E o segundo passo do `docs/COMO-EXECUTAR.md` -- a reserva do dispositivo
    pelo `docker-compose.gpu.yml`. Quando ela vale, o runtime injeta o
    `nvidia-smi` e os nos de dispositivo; quando nao, nada disso existe, mesmo
    numa imagem cheia de libs de CUDA.

    No Docker Desktop com WSL 2 o no e `/dev/dxg` e nao `/dev/nvidia0`, entao
    olhar so o segundo daria `nao` numa maquina Windows que esta funcionando.
    """
    import shutil
    if shutil.which("nvidia-smi"):
        return True
    for no in ("/dev/nvidia0", "/dev/nvidiactl", "/dev/dxg"):
        if os.path.exists(no):
            return True
    # Ausencia dos tres e ausencia de verdade: sao os caminhos que o runtime
    # cria. Nao e "nao deu para saber".
    return False


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


#: Erros conhecidos da sonda do NVENC, e o que cada um significa em portugues.
#: Casado por pedaco de texto, em minusculas. So entra aqui o que se sabe
#: diagnosticar -- o resto sai como a linha crua do ffmpeg, que e mais honesto
#: que uma explicacao inventada.
MOTIVOS_DO_NVENC = (
    ("cannot load libnvidia-encode",
     "o container nao recebeu as libs de ENCODE da NVIDIA. E comum no Docker "
     "Desktop com WSL 2: o CUDA passa e o NVENC nao. O render fica em libx264 "
     "-- mais lento, e nao quebra nada."),
    ("cannot load libcuda",
     "o container nao recebeu as libs de CUDA do driver."),
    ("no capable devices found",
     "o ffmpeg alcancou o driver e nao achou placa que sirva."),
    ("out of memory",
     "a placa esta sem memoria livre para abrir uma sessao de encode agora."),
    ("no free encoding sessions",
     "a placa esta com todas as sessoes de encode ocupadas. Placas GeForce tem "
     "um teto baixo de sessoes simultaneas."),
    ("unknown encoder",
     "este ffmpeg foi compilado sem h264_nvenc."),
)


def motivo_do_nvenc() -> Optional[str]:
    """POR QUE o h264_nvenc nao abriu -- rodando a sonda e LENDO o erro.

    O `ffmpeg_utils._probe_nvenc` responde um booleano e descarta o stderr de
    proposito: ele roda antes de cada encode e nao pode poluir o log de todo
    job. Mas "nao" sozinho manda a pessoa adivinhar, e as causas pedem coisas
    diferentes -- libs de encode ausentes e um limite de sessoes simultaneas
    nao tem o mesmo conserto.

    Usa `ffmpeg_utils.comando_da_sonda_nvenc()`, e nao uma copia: duas
    definicoes do mesmo comando divergem no dia em que uma delas mudar.
    """
    import subprocess
    try:
        import ffmpeg_utils
        r = subprocess.run(ffmpeg_utils.comando_da_sonda_nvenc(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           timeout=30)
    except Exception as e:
        return f"nao consegui rodar a sonda ({type(e).__name__})"
    if r.returncode == 0:
        return None
    erro = (r.stderr or b"").decode("utf-8", "replace").strip()
    baixo = erro.lower()
    for pedaco, explicacao in MOTIVOS_DO_NVENC:
        if pedaco in baixo:
            return explicacao
    # Sem casar com nada conhecido, a ULTIMA linha do ffmpeg crua. Inventar
    # explicacao para erro que ninguem viu e o oposto do que este modulo faz.
    ultima = [l for l in erro.splitlines() if l.strip()]
    return ultima[-1].strip() if ultima else "a sonda falhou sem dizer por que"


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
        "libs_de_cuda_na_imagem": libs_de_cuda_na_imagem(),
        "driver_no_container": driver_no_container(),
        "ffmpeg_encoder": os.environ.get("FFMPEG_ENCODER", "x264").strip().lower(),
        "nvenc_usavel": nvenc_usavel(),
        # So quando falhou: com o nvenc funcionando nao ha motivo a explicar, e
        # rodar a sonda de novo seria um encode a toa.
        "motivo_do_nvenc": None if nvenc_usavel() else motivo_do_nvenc(),
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


def _encoder_pedido_e_nao_atendido(ambiente: dict) -> list:
    """`FFMPEG_ENCODER=auto|nvenc` com o h264_nvenc recusando abrir.

    Nao e falha: o `ffmpeg_utils` cai para libx264 sozinho, e o job roda. Mas e
    uma expectativa que nao se cumpre em silencio, e o custo dela e todo encode
    da cadeia de um corte na CPU. Quem pediu merece saber, e saber POR QUE --
    lib de encode ausente e sessao esgotada nao tem o mesmo conserto.
    """
    if (ambiente.get("ffmpeg_encoder") or "") not in ("auto", "nvenc"):
        return []                      # ninguem pediu nvenc: nada a cobrar
    if ambiente.get("nvenc_usavel") is not False:
        return []                      # abriu, ou nao deu para saber
    frase = ("A placa esta em uso pelo whisper, mas o **h264_nvenc nao abre** "
             "-- entao todo encode da cadeia de um corte fica em libx264, na "
             "CPU. Nao quebra nada (a queda e automatica), so e mais lento.")
    # O motivo sai na linha `porque:` do bloco de ambiente. Repetir aqui daria
    # o mesmo paragrafo duas vezes na mesma tela.
    if ambiente.get("motivo_do_nvenc"):
        frase += " O motivo esta na linha `porque:` acima."
    return [frase]


def caminho_da_gpu(ambiente: dict) -> list:
    """Por que a placa nao chegou -- e QUAL das duas causas e.

    As duas dao o mesmo `nao` em `placa p/ o whisper` e a correcao e outra:

    - **imagem sem as libs de CUDA** (`--build-arg GPU=1` nunca rodou, ou
      falhou): `reconstruir.bat`, 15 a 40 minutos;
    - **placa nao reservada** (subiu sem o `docker-compose.gpu.yml`):
      `subir.bat`, segundos.

    Os dois atalhos sao os de sempre desde 22-set-2026: eles perguntam ao
    `nvidia-smi` do Windows se ha placa (`_modo-gpu.bat`) e poem o overlay
    sozinhos. As variantes `-gpu` viraram apelido -- ter duas de cada era o que
    tirava a placa, porque o `atualizar.bat` subia pelo caminho sem ela. Por
    isso a frase manda ler a PRIMEIRA linha do atalho: se ela disser que nenhuma
    placa respondeu, o problema saiu do container e esta no driver do Windows.

    Sem separar, escolher entre as duas e cara ou coroa -- e a coroa custa 40
    minutos. Era o unico buraco que restava no diagnostico: ele dizia que a
    placa nao chegou e nao dizia onde ela parou.

    **Isto nao depende de medicao, e nao viola a regra das duas metades.** A
    regra existe para nao prescrever mudanca no que talvez esteja certo -- e
    por isso a frase daqui e CONDICIONAL ("se esta maquina tem placa"): o
    container nao sabe se ha uma. O que ele sabe e onde a corrente arrebentou,
    e isso e fato, nao palpite.
    """
    libs = ambiente.get("libs_de_cuda_na_imagem")
    driver = ambiente.get("driver_no_container")
    if ambiente.get("cuda_para_o_whisper") is True:
        # A placa chegou para o whisper. Falta so o outro consumidor dela: o
        # encoder. Isto e contradicao observada e nao palpite -- o encoder foi
        # PEDIDO (`auto`/`nvenc`) e nao abre --, entao sai sem medicao.
        return _encoder_pedido_e_nao_atendido(ambiente)

    if libs is False:
        return ["A placa nao chega no container porque **a imagem nao tem as "
                "libs de CUDA** -- ela foi construida sem `--build-arg GPU=1`, "
                "ou aquela construcao falhou. Os caminhos do `LD_LIBRARY_PATH` "
                "nao existem aqui dentro. Conserto: `atalhos\\reconstruir.bat`, "
                "que constroi e sobe; numa maquina com placa NVIDIA ele poe as "
                "libs sozinho. Leva de 15 a 40 minutos, uma vez. Se a primeira "
                "linha dele disser que nenhuma placa respondeu, o que falta e o "
                "driver da NVIDIA no Windows (`nvidia-smi` no Prompt de "
                "Comando responde)."]
    if libs is True and driver is False:
        return ["A imagem TEM as libs de CUDA, mas **a placa nao foi reservada "
                "para o container**: nem o `nvidia-smi` nem os nos de "
                "dispositivo estao aqui dentro. Foi o segundo dos dois passos "
                "que ficou faltando. Conserto: `atalhos\\subir.bat`, que "
                "pergunta ao Windows se ha placa e sobe com o "
                "`docker-compose.gpu.yml`. Leva segundos. Leia a primeira "
                "linha dele: se disser que nenhuma placa respondeu, e o driver "
                "da NVIDIA no Windows; se disser que o Docker recusou a placa, "
                "e o Docker Desktop fora do motor WSL 2."]
    if libs is True and driver is True:
        return ["As duas metades estao no lugar -- libs de CUDA na imagem e "
                "driver injetado --, e o `ctranslate2` ainda nao ve a placa. "
                "Isto nao e configuracao: e versao de lib ou driver. O log do "
                "backend na primeira transcricao diz o que faltou."]
    # `libs is None` e o diagnostico rodando FORA do container, onde nem o
    # `ENV` do Dockerfile existe. Ali nao ha nada a afirmar.
    return []


def conclusoes(ambiente: dict, agregado: dict) -> list:
    """As frases que precisam das DUAS metades para existir.

    O relatorio sozinho diz "a transcricao domina" e manda conferir; o ambiente
    sozinho diz "o whisper esta em CPU", que numa maquina sem placa e apenas
    verdade. Juntar os dois e o que transforma medicao em proximo passo.

    A excecao esta em `caminho_da_gpu`, e ela se justifica: "a corrente da GPU
    arrebentou AQUI" e fato observado, nao prescricao sobre o que talvez esteja
    certo, e sai em frase condicional. Sem ela, um container sem placa nenhuma
    respondia so "rode um video e volte" -- mandando esperar uma medicao para
    descobrir o que ja estava na tela.
    """
    saida = list(caminho_da_gpu(ambiente))
    if not agregado.get("jobs"):
        saida.append(
            "Nenhum job medido em `output/`. Para saber ONDE o tempo vai, "
            "rode um video e volte -- sem medicao, qualquer conclusao sobre "
            "qual estagio pesa e chute, que e o que este projeto vem recusando "
            "em toda decisao.")
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
    # Os dois elos, e so quando a placa NAO chegou: sao eles que dizem se o
    # conserto custa 40 minutos ou 30 segundos. Com a placa em uso viram ruido.
    if ambiente.get("cuda_para_o_whisper") is not True:
        linhas.append(
            f"    libs de CUDA na imagem  "
            f"{_sim_nao(ambiente.get('libs_de_cuda_na_imagem')):<20}"
            f" (--build-arg GPU=1)")
        linhas.append(
            f"    driver no container     "
            f"{_sim_nao(ambiente.get('driver_no_container')):<20}"
            f" (docker-compose.gpu.yml)")
    linhas.append(f"  ffmpeg             {ambiente.get('ffmpeg_encoder')}"
                  f"   (h264_nvenc utilizavel: "
                  f"{_sim_nao(ambiente.get('nvenc_usavel'))})")
    if ambiente.get("motivo_do_nvenc"):
        linhas.append(f"    porque: {ambiente['motivo_do_nvenc']}")
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
