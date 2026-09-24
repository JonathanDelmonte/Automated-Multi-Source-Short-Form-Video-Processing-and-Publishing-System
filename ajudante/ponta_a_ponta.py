"""Um video do comeco ao fim no motor, fora do Docker (ajudante, Fase 6.2).

Roda no Windows do GitHub (`.github/workflows/windows.yml`) a cada envio para a
`main`, e serve de roteiro para conferir o ajudante instalado num PC de
verdade. O que ele prova, e o que nao prova:

- PROVA que o servidor sobe, recebe um upload, transcreve (whisper em CPU),
  escolhe o momento, corta, reenquadra e queima a legenda com as fontes do
  repositorio -- tudo com os caminhos, o console e o sistema de arquivos do
  Windows. E que cancelar um job em andamento derruba o ffmpeg junto: senao o
  Windows se recusa a apagar a pasta, porque arquivo aberto ele nao apaga.
- NAO PROVA a placa de video (o GitHub nao tem), o download do YouTube (ele
  recusa os computadores do GitHub, como recusa qualquer servidor) nem a IA de
  verdade: a deteccao fala com `llm_falso.py`, pelo caminho de LLM local
  (`LLM_BASE_URL`). Esses tres ficam para o teste no PC do autor.

A fala vem do sintetizador do proprio Windows (SAPI); fora dele, do espeak, se
houver. Sem fala o motor iria para o caminho de video mudo, que exige o Gemini.

Uso: python ajudante/ponta_a_ponta.py [--pasta DIR] [--manter]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import llm_falso  # noqa: E402

PORTA_MOTOR = 8127
PORTA_LLM = 8765
BASE = f"http://127.0.0.1:{PORTA_MOTOR}"

# ~30 s de fala, dita duas vezes. Sem apostrofo: vai entre aspas simples no
# PowerShell.
TEXTO = (
    "Welcome to the helper test. This short video exists to prove that the "
    "clip engine runs on Windows without Docker. First it listens to this "
    "voice and writes down every word. Then it picks the best moment, cuts it, "
    "turns it into a vertical video, and burns the captions on top. If you can "
    "read these words on the final clip, the whole chain worked from start to "
    "finish. The only parts missing here are the graphics card and the real "
    "artificial intelligence, which are tested later on a real computer. "
    "Thank you for watching, and see you in the next clip."
)


def passo(msg: str) -> None:
    print(f"\n=== {msg}", flush=True)


def gerar_fala(wav: Path) -> None:
    if os.name == "nt":
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{wav}'); "
            f"$s.Speak('{TEXTO}'); $s.Speak('{TEXTO}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       check=True)
        return
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        raise SystemExit("Sem sintetizador de voz: rode no Windows ou instale o espeak-ng.")
    subprocess.run([espeak, "-w", str(wav), f"{TEXTO} {TEXTO}"], check=True)


# O motor recusa fonte com menos de 45 s (`MIN_SOURCE_SECONDS`): um video
# assim ja e curto. A fala e dita duas vezes, e o `apad` garante o piso mesmo
# que a voz do Windows fale mais depressa que a medida aqui.
DURACAO_MINIMA_S = 55


def gerar_video(wav: Path, mp4: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
         "-i", str(wav), "-af", f"apad=whole_dur={DURACAO_MINIMA_S}", "-shortest",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", str(mp4)],
        check=True)


def sondar(mp4: Path) -> dict:
    saida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", str(mp4)],
        capture_output=True, text=True, check=True).stdout
    return json.loads(saida)


def subir_motor(pasta: Path) -> tuple:
    # Sem chave nenhuma, de proposito: a deteccao tem de ir ao LLM falso. O
    # `.env` da pasta pode ter chaves (no PC do autor tem), entao a cascata e
    # esvaziada pelo nome e o picker de layout sai pelo pedido (`layouts=none`).
    env = {k: v for k, v in os.environ.items()
           if not k.endswith(("_API_KEY", "_API_TOKEN"))}
    env.update({
        "OUTPUT_DIR": str(pasta / "output"),
        "UPLOAD_DIR": str(pasta / "uploads"),
        "DATA_DIR": str(pasta / "data"),
        "HF_HOME": str(pasta / "hf"),
        "LLM_BASE_URL": f"http://127.0.0.1:{PORTA_LLM}/v1",
        "LLM_MODEL": "falso",
        "LLM_CASCADE": "nenhum",
        "WHISPER_MODEL": os.environ.get("WHISPER_MODEL", "tiny"),
        "WHISPER_DEVICE": "cpu",
        "WHISPER_COMPUTE": "int8",
        "HOOK_GROUNDING": "0",
        "PYTHONUTF8": "1",
    })
    log = open(pasta / "motor.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app",
         "--host", "127.0.0.1", "--port", str(PORTA_MOTOR)],
        cwd=RAIZ, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc, log


def esperar_motor(proc, prazo_s: float = 180) -> dict:
    fim = time.time() + prazo_s
    while time.time() < fim:
        if proc.poll() is not None:
            raise SystemExit(f"o motor morreu ao subir (codigo {proc.returncode})")
        try:
            r = httpx.get(BASE + "/api/config", timeout=5)
            if r.status_code == 200:
                return r.json()
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit(f"o motor nao respondeu em {prazo_s:.0f} s")


def enviar(mp4: Path, **extra) -> str:
    campos = {"acknowledged": "true", "layouts": "none", "target_clips": "1",
              "clip_min_seconds": "10", "clip_max_seconds": "30", **extra}
    with open(mp4, "rb") as f:
        r = httpx.post(BASE + "/api/process", data=campos,
                       files={"file": (mp4.name, f, "video/mp4")}, timeout=120)
    if r.status_code != 200:
        raise SystemExit(f"/api/process recusou ({r.status_code}): {r.text[:500]}")
    return r.json()["job_id"]


def acompanhar(job_id: str, prazo_s: float, parar_quando=None) -> dict:
    vistas = 0
    fim = time.time() + prazo_s
    while time.time() < fim:
        estado = httpx.get(f"{BASE}/api/status/{job_id}", timeout=30).json()
        logs = estado.get("logs") or []
        for linha in logs[vistas:]:
            print(f"   | {linha}", flush=True)
        vistas = len(logs)
        if estado.get("status") in ("completed", "failed", "cancelled"):
            return estado
        if parar_quando and parar_quando(estado):
            return estado
        time.sleep(3)
    raise SystemExit(f"o job {job_id} nao terminou em {prazo_s:.0f} s")


def conferir_cortes(pasta: Path, job_id: str, estado: dict) -> list:
    if estado.get("status") != "completed":
        raise SystemExit(f"o job terminou como {estado.get('status')!r}")
    cortes = (estado.get("result") or {}).get("clips") or []
    if not cortes:
        raise SystemExit("o job terminou sem corte nenhum")
    arquivos = []
    for corte in cortes:
        nome = (corte.get("video_url") or "").rsplit("/", 1)[-1]
        caminho = pasta / "output" / job_id / nome
        if not caminho.is_file() or caminho.stat().st_size < 10_000:
            raise SystemExit(f"o corte {nome!r} nao esta no disco")
        info = sondar(caminho)
        tipos = {s.get("codec_type") for s in info.get("streams", [])}
        duracao = float(info["format"]["duration"])
        video = next(s for s in info["streams"] if s.get("codec_type") == "video")
        print(f"   corte: {nome} | {video.get('width')}x{video.get('height')} | "
              f"{duracao:.1f} s | {sorted(tipos)}", flush=True)
        if tipos != {"video", "audio"}:
            raise SystemExit(f"o corte {nome!r} saiu sem {({'video', 'audio'} - tipos)}")
        if not 5 <= duracao <= 60:
            raise SystemExit(f"o corte {nome!r} tem {duracao:.1f} s")
        arquivos.append(nome)
    if not any(n.startswith("subtitled_") for n in arquivos):
        raise SystemExit("nenhum corte saiu com a legenda queimada")
    return arquivos


def conferir_cancelamento(pasta: Path, mp4: Path) -> None:
    """Cancela no meio e apaga: no Windows, um ffmpeg orfao seguraria o video
    aberto e o apagar responderia 409 dizendo o que sobrou."""
    job_id = enviar(mp4)
    acompanhar(job_id, 600, parar_quando=lambda e: e.get("status") == "processing")
    # O job inteiro leva minutos; em 5 s o main.py ja abriu ffmpeg ou whisper.
    time.sleep(5)
    r = httpx.post(f"{BASE}/api/jobs/{job_id}/cancel", timeout=60)
    print(f"   cancelar: {r.status_code}", flush=True)
    r.raise_for_status()
    time.sleep(2)
    r = httpx.delete(f"{BASE}/api/jobs/{job_id}", timeout=120)
    print(f"   apagar: {r.status_code} {r.text[:300]}", flush=True)
    if r.status_code != 200:
        raise SystemExit("apagar o projeto cancelado falhou -- sobrou processo segurando arquivo?")
    if (pasta / "output" / job_id).exists():
        raise SystemExit("a pasta do projeto cancelado continua no disco")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", help="onde trabalhar (padrao: output/ponta-a-ponta-<hora>)")
    ap.add_argument("--manter", action="store_true", help="nao apagar a pasta no fim")
    args = ap.parse_args()
    # Dentro do `output/` do repositorio, e nao no temporario do sistema: a
    # regra do `test_nada_dentro_do_docker`, e o CI publica o log dali quando
    # alguma coisa falha.
    padrao = RAIZ / "output" / f"ponta-a-ponta-{time.strftime('%Y%m%d-%H%M%S')}"
    pasta = Path(args.pasta or padrao).resolve()
    pasta.mkdir(parents=True, exist_ok=True)
    print(f"pasta de trabalho: {pasta}", flush=True)

    passo("gerando um video com fala")
    # Acento e espaco no nome, como o titulo de um video brasileiro: e o
    # caminho que mais quebra no Windows (OpenCV, libass, linha de comando).
    wav, mp4 = pasta / "fala.wav", pasta / "entrada teste ação.mp4"
    gerar_fala(wav)
    gerar_video(wav, mp4)
    print(f"   {mp4.name}: {sondar(mp4)['format']['duration']} s", flush=True)

    passo("subindo o LLM falso e o motor")
    llm_falso.subir(PORTA_LLM)
    proc, log = subir_motor(pasta)
    ok = False
    try:
        config = esperar_motor(proc)
        print(f"   /api/config: {json.dumps(config)[:300]}", flush=True)

        passo("processando o video do comeco ao fim")
        inicio = time.time()
        job_id = enviar(mp4)
        estado = acompanhar(job_id, 1500)
        arquivos = conferir_cortes(pasta, job_id, estado)
        print(f"   {len(arquivos)} corte(s) em {time.time() - inicio:.0f} s; "
              f"{len(llm_falso.pedidos())} pedido(s) ao LLM falso", flush=True)

        passo("cancelando um job no meio e apagando o projeto")
        conferir_cancelamento(pasta, mp4)
        ok = True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        if not ok:
            texto = (pasta / "motor.log").read_text(encoding="utf-8", errors="replace")
            print("\n=== fim do log do motor\n" + texto[-15000:], flush=True)
        if ok and not args.manter:
            shutil.rmtree(pasta, ignore_errors=True)

    passo("TUDO CERTO: o motor rodou do comeco ao fim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
