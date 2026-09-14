"""O `main` é resolvido uma vez, não carregado duas (Fase 1, correção do 1.1).

`python main.py` carrega o arquivo como `__main__`. Um `import main` lá dentro
**não** devolve esse módulo: o Python não encontra "main" em `sys.modules` e lê
o arquivo OUTRA VEZ, com o topo reexecutado — outro grafo do MediaPipe, outro
`DETECT_LOCK`, outro conjunto de globais. O `main.py` é um subprocesso novo a
cada vídeo, então isso se pagaria em todo job.

O teste roda um subprocesso de verdade, porque é a única forma de reproduzir a
condição: sob o pytest, `__main__` é o próprio pytest e o defeito não aparece.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _roda(main_py: str, tmp_path: Path) -> str:
    alvo = tmp_path / "main.py"
    alvo.write_text(textwrap.dedent(main_py), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(alvo)], capture_output=True,
                          cwd=str(tmp_path),
                          env={"PYTHONPATH": f"{tmp_path}{':'}{RAIZ}",
                               "PATH": "/usr/bin:/bin"},
                          timeout=60)
    assert proc.returncode == 0, proc.stderr.decode()
    return proc.stdout.decode()


class TestNaoCarregaDuasVezes:
    def test_o_topo_do_main_roda_uma_vez_so(self, tmp_path):
        saida = _roda("""
            import sources

            print("TOPO")

            def download_youtube_video(url, output_dir="."):
                return "/x.mp4", "x"

            def sanitize_filename(n):
                return n

            if __name__ == "__main__":
                got = sources.resolve("https://youtu.be/a").fetch("https://youtu.be/a", ".")
                print("FETCH", got.path)
        """, tmp_path)
        assert saida.count("TOPO") == 1, (
            f"o topo do main.py rodou {saida.count('TOPO')} vezes -- "
            "cada uma recria o grafo do MediaPipe e os globais")
        assert "FETCH /x.mp4" in saida

    def test_devolve_o_MESMO_modulo_que_esta_rodando(self, tmp_path):
        # Não basta rodar uma vez: tem que ser o mesmo objeto, senão duas
        # cópias de `DETECT_LOCK` protegem coisas diferentes.
        saida = _roda("""
            import sys
            import sources.base

            MARCA = object()

            def download_youtube_video(url, output_dir="."):
                return "/x.mp4", "x"

            if __name__ == "__main__":
                m = sources.base.modulo_main()
                print("MESMO", m is sys.modules["__main__"])
                print("MARCA", m.MARCA is MARCA)
        """, tmp_path)
        assert "MESMO True" in saida
        assert "MARCA True" in saida

    def test_todos_os_adapters_de_rede_usam_o_helper(self, tmp_path):
        saida = _roda("""
            import sources

            print("TOPO")
            CHAMADAS = []

            def download_youtube_video(url, output_dir="."):
                CHAMADAS.append(url)
                return "/x.mp4", "x"

            if __name__ == "__main__":
                for u in ("https://youtu.be/a",
                          "https://www.twitch.tv/videos/1",
                          "https://drive.google.com/file/d/1A/view",
                          "https://cdn.exemplo.com/v.mp4"):
                    sources.resolve(u).fetch(u, ".")
                print("CHAMADAS", len(CHAMADAS))
        """, tmp_path)
        assert saida.count("TOPO") == 1
        assert "CHAMADAS 4" in saida, (
            "um adapter que ainda faça `import main` chamaria a cópia dele, "
            "e a lista deste módulo ficaria curta")


class TestSobOUvicorn:
    def test_quando_main_nao_e_o_entrypoint_importa_normalmente(self, tmp_path):
        # Forma do `app.py`: o entrypoint é outro, e o `main` é um módulo comum.
        (tmp_path / "main.py").write_text(
            'print("TOPO")\n'
            'def download_youtube_video(url, output_dir="."):\n'
            '    return "/x.mp4", "x"\n', encoding="utf-8")
        app = tmp_path / "app.py"
        app.write_text(textwrap.dedent("""
            import sources

            if __name__ == "__main__":
                got = sources.resolve("https://youtu.be/a").fetch("https://youtu.be/a", ".")
                print("FETCH", got.path)
        """), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(app)], capture_output=True,
                              cwd=str(tmp_path),
                              env={"PYTHONPATH": f"{tmp_path}:{RAIZ}", "PATH": "/usr/bin:/bin"},
                              timeout=60)
        assert proc.returncode == 0, proc.stderr.decode()
        saida = proc.stdout.decode()
        assert saida.count("TOPO") == 1, "o main foi importado uma vez, como módulo comum"
        assert "FETCH /x.mp4" in saida
