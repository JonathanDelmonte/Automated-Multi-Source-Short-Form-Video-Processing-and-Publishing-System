"""
Fast pre-flight probe: what maximum resolution does YouTube offer for a URL?

Run as a short subprocess by app.py BEFORE a job starts, so the user can decide
to abort (and e.g. refresh cookies) instead of burning 20+ minutes of
transcription and rendering on a 360p-only source.

Prints JSON to stdout: {"max_height": int, "mode": str, "cookies_invalid": bool}
Always exits 0 — the caller treats probe failures as "unknown" and starts the
job anyway (fail-open), where the in-job warning still applies.
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _find_cookies_path(url: str = "https://www.youtube.com/"):
    """Onde esta o jar de cookies desta fonte.

    Delega para `sources.jar_em_disco`, que agora e a UNICA definicao. O
    comentario que estava aqui dizia "mirrors main.py's cookie discovery", e
    nao era verdade: o `main.py` so lia a variavel de ambiente. As duas metades
    discordavam -- o probe achava o arquivo, o download nao --, e na mesma
    maquina o probe passava e o download dizia "sign in to confirm you're not
    a bot" (22-set-2026).
    """
    import sources
    return sources.jar_em_disco(url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe available YouTube quality for a URL.")
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    result = {"max_height": 0, "mode": None, "cookies_invalid": False, "duration": 0}
    try:
        import yt_dlp

        warnings = []

        class _CollectLogger:
            def debug(self, msg):
                pass

            def info(self, msg):
                pass

            def warning(self, msg):
                warnings.append(str(msg))

            def error(self, msg):
                warnings.append(str(msg))

        cookies_path = _find_cookies_path()
        base_opts = {
            'quiet': True,
            'no_warnings': False,
            'logger': _CollectLogger(),
            'socket_timeout': 20,
            'retries': 2,
            'nocheckcertificate': True,
            'cachedir': False,
        }
        # A lista de clientes e a MESMA do download (`yt_clients`), e por
        # tentativa. O comentario que estava aqui dizia para nunca sobrescrever
        # o padrao do yt-dlp, porque ele "ainda serve HD sem PO token" -- em
        # 22-set-2026 o padrao anonimo (`visionos`, `web`) respondeu
        # LOGIN_REQUIRED, e um probe que mede por uma lista e um download que
        # baixa por outra medem coisas diferentes. E o mesmo motivo pelo qual
        # o `yt_clients` existe.
        import yt_clients
        _bgutil_http = os.environ.get("BGUTIL_BASE_URL", "").strip()
        _bgutil_script = os.environ.get("BGUTIL_SCRIPT_PATH", "").strip()

        def _opts(cookies):
            # `fallback_...` e nao `hd_...` porque este e um probe: ele nao
            # pode devolver None e desistir quando falta o provedor de PO
            # token -- a medicao que sobra (o formato progressivo) ainda
            # responde a pergunta "qual altura este video oferece".
            return {**base_opts,
                    'cookiefile': cookies_path if cookies else None,
                    'extractor_args': yt_clients.fallback_extractor_args(
                        _bgutil_http, _bgutil_script, cookies=cookies)}

        attempts = []
        if cookies_path:
            attempts.append(("cookie-auth", _opts(True)))
        attempts.append(("anonymous", _opts(False)))

        for mode, opts in attempts:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(args.url, download=False)
                formats = info.get('formats') or []
                heights = [
                    f.get('height') or 0
                    for f in formats
                    if f.get('vcodec', 'none') != 'none'
                    and f.get('protocol') != 'mhtml'
                    and f.get('ext') != 'mhtml'
                ]
                max_height = max(heights, default=0)
                if max_height > result["max_height"]:
                    result["max_height"] = max_height
                    result["mode"] = mode
                if not result["duration"]:
                    result["duration"] = int(info.get('duration') or 0)
                if result["max_height"] >= 1080:
                    break
            except Exception:
                continue

        result["cookies_invalid"] = any("no longer valid" in w for w in warnings)
    except Exception:
        pass

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
