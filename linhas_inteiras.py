"""O log do job so recebe LINHAS INTEIRAS, uma de cada vez (24-set-2026).

O `app.py` le o stdout do `main.py` linha a linha e reconhece os marcadores
pelo COMECO da linha: `__STAGE__BEGIN` move a barra, `CLIP_READY` diz qual
arquivo servir, `PROXY_ROUTE=` vira linha no banco. So que o job tem varias
threads imprimindo ao mesmo tempo, e um `print` sao DUAS escritas (o texto e o
`\\n`). Entre uma e outra cabe a escrita de outra thread, e ai o marcador cai
no meio da linha dos outros -- e passa direto pelo `startswith`. No log de
192 s do autor ja aconteceu, com os tres cortes em paralelo:

    Title: A atracao surpresa que ninguem acreditou__STAGE__BEGIN 05_06_render

O download em paralelo com a transcricao (`audio_primeiro`) tornaria isso a
regra, nao o acidente: o yt-dlp escreve o progresso com `\\r` e sem `\\n`
durante o download inteiro, entao TODA linha que o resto do job imprimisse
nesse intervalo cairia dentro da linha de progresso dele.

Aqui cada thread acumula o que escreve ate fechar a linha, e so entao a linha
vai para o destino, inteira e sob uma trava que stdout e stderr dividem (o
`app.py` junta os dois no mesmo cano).

* **Linha parcial nao sai no `flush()`.** Sair seria abrir de novo a janela
  que este modulo fecha. A linha incompleta de uma thread sai quando ela
  escrever o `\\n`, ou no fim do processo (`despejar`).
* **Sem atributo `buffer`, de proposito.** O `write_string` do yt-dlp escreve
  direto no `out.buffer` quando ele existe -- e passaria por fora da trava.
* So vale para o processo do job: o `main.py` instala no comeco do
  `__main__`. O servidor (`app.py`) nao usa.
"""
import atexit
import sys
import threading

_TRAVA = threading.Lock()


class LinhasInteiras:
    """Envolve um stream de texto; so escreve linhas completas."""

    def __init__(self, destino, trava=_TRAVA):
        self._destino = destino
        self._trava = trava
        # Por thread, e num dict e nao em `threading.local`: o `despejar` do fim
        # do processo precisa alcancar o resto de threads que ja terminaram.
        self._pendente = {}

    # -- o que o `print` e o yt-dlp usam -------------------------------------

    def write(self, texto):
        if not texto:
            return 0
        eu = threading.get_ident()
        junto = self._pendente.pop(eu, "") + texto
        corte = junto.rfind("\n")
        if corte < 0:
            self._pendente[eu] = junto
            return len(texto)
        pronto, resto = junto[:corte + 1], junto[corte + 1:]
        if resto:
            self._pendente[eu] = resto
        with self._trava:
            self._destino.write(pronto)
            self._destino.flush()
        return len(texto)

    def flush(self):
        with self._trava:
            self._destino.flush()

    def despejar(self):
        """Escreve o que sobrou sem `\\n`, de todas as threads. Fim do processo."""
        with self._trava:
            for eu in list(self._pendente):
                resto = self._pendente.pop(eu, "")
                if resto:
                    self._destino.write(resto + "\n")
            self._destino.flush()

    # -- o resto da interface de um stream, repassado ------------------------

    def isatty(self):
        return self._destino.isatty()

    def fileno(self):
        return self._destino.fileno()

    def writable(self):
        return True

    @property
    def encoding(self):
        return getattr(self._destino, "encoding", None) or "utf-8"

    @property
    def errors(self):
        return getattr(self._destino, "errors", None) or "strict"


def instalar():
    """Troca stdout e stderr do processo. Idempotente."""
    if isinstance(sys.stdout, LinhasInteiras):
        return
    sys.stdout = LinhasInteiras(sys.stdout)
    sys.stderr = LinhasInteiras(sys.stderr)
    for stream in (sys.stdout, sys.stderr):
        atexit.register(stream.despejar)
