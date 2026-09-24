"""O log do job so recebe linhas inteiras (24-set-2026).

Um `print` sao duas escritas, e entre elas cabe a de outra thread: foi assim
que o log de 192 s do autor saiu com
`...ninguem acreditou__STAGE__BEGIN 05_06_render`, e o marcador, que o `app.py`
so reconhece no COMECO da linha, se perdeu.
"""
import ast
import io
import threading
from pathlib import Path

import linhas_inteiras
from linhas_inteiras import LinhasInteiras

RAIZ = Path(__file__).resolve().parent.parent


class Destino(io.StringIO):
    """Um StringIO que conta quantas escritas recebeu."""

    def __init__(self):
        super().__init__()
        self.escritas = []

    def write(self, s):
        self.escritas.append(s)
        return super().write(s)


def test_linha_escrita_em_pedacos_sai_inteira():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    s.write("abc")
    s.write("def")
    assert d.getvalue() == ""
    s.write("\n")
    assert d.getvalue() == "abcdef\n"
    assert d.escritas == ["abcdef\n"]


def test_o_print_de_verdade_passa_inteiro():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    print("__STAGE__BEGIN 02_probe", file=s, flush=True)
    assert d.escritas == ["__STAGE__BEGIN 02_probe\n"]


def test_varias_linhas_de_uma_vez_saem_juntas_e_o_resto_espera():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    s.write("um\ndois\ntr")
    assert d.getvalue() == "um\ndois\n"
    s.write("es\n")
    assert d.getvalue() == "um\ndois\ntres\n"


def test_o_progresso_do_ytdlp_nao_engole_a_linha_de_outra_thread():
    """O caso que o download em paralelo criaria em todo job: o yt-dlp escreve
    `\\r[download] 45%` sem `\\n` durante o download inteiro."""
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    download_andou = threading.Event()
    marcador_saiu = threading.Event()

    def download():
        s.write("\r[download]  10.0% of 180MiB")
        download_andou.set()
        marcador_saiu.wait(2)
        s.write("\r[download] 100.0% of 180MiB\n")

    t = threading.Thread(target=download)
    t.start()
    download_andou.wait(2)
    print("__STAGE__BEGIN 03_transcribe", file=s, flush=True)
    marcador_saiu.set()
    t.join(2)

    # `split` e nao `splitlines`: o segundo tambem corta no `\r`.
    linhas = d.getvalue().split("\n")
    assert "__STAGE__BEGIN 03_transcribe" in linhas
    assert any(l.startswith("\r[download]") and "100.0%" in l for l in linhas)


def test_muitas_threads_nunca_grudam_um_marcador():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())

    def falar(n):
        for i in range(200):
            print(f"Title: corte {n} numero {i}", file=s)
            print(f"__STAGE__BEGIN 05_06_render", file=s)

    ts = [threading.Thread(target=falar, args=(n,)) for n in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    linhas = d.getvalue().splitlines()
    assert len(linhas) == 4 * 200 * 2
    assert all(l.startswith(("Title: corte", "__STAGE__BEGIN")) for l in linhas)
    assert sum(l == "__STAGE__BEGIN 05_06_render" for l in linhas) == 800


def test_flush_nao_solta_linha_pela_metade():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    s.write("pela metade")
    s.flush()
    assert d.getvalue() == ""


def test_despejar_solta_o_que_sobrou_no_fim():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    s.write("sem fim de linha")
    s.despejar()
    assert d.getvalue() == "sem fim de linha\n"


def test_stdout_e_stderr_dividem_a_trava():
    """O `app.py` junta os dois no mesmo cano (`stderr=STDOUT`)."""
    assert linhas_inteiras._TRAVA is LinhasInteiras.__init__.__defaults__[0]


def test_nao_tem_buffer_para_o_ytdlp_nao_passar_por_fora():
    """`yt_dlp.utils.write_string` escreve em `out.buffer` quando ele existe --
    por fora da trava."""
    s = LinhasInteiras(Destino(), threading.Lock())
    assert not hasattr(s, "buffer")
    assert "b" not in (getattr(s, "mode", None) or "")


def test_repassa_o_resto_da_interface():
    d = Destino()
    s = LinhasInteiras(d, threading.Lock())
    assert s.isatty() is False
    assert s.writable() is True
    assert s.encoding


def test_o_main_instala_antes_de_tudo():
    """Instalado no comeco do `__main__`, antes de qualquer thread e antes do
    yt-dlp guardar o `sys.stdout` que ve na hora em que nasce."""
    arvore = ast.parse((RAIZ / "main.py").read_text(encoding="utf-8"))
    bloco = [n for n in arvore.body if isinstance(n, ast.If)
             and "__main__" in ast.unparse(n.test)][-1]
    primeira = ast.unparse(bloco.body[0])
    assert primeira == "linhas_inteiras.instalar()", primeira
