"""Baixar o audio primeiro e transcrever enquanto o video chega (24-set-2026).

No YouTube o audio e o video sao dois arquivos separados, e o yt-dlp baixava
o VIDEO primeiro: no log de 192 s foram ~10 s de video (181 MB), 1 s de audio
(10 MB) e 5 s juntando os dois -- e so entao a transcricao podia comecar,
mesmo lendo SO o audio (estagio 02, "o audio dirige"). Aqui a ordem se
inverte: o audio chega em ~1 s, a transcricao comeca, e o video termina de
baixar numa thread enquanto ela roda. O video so e esperado quando alguem
precisa dele -- o corte, a analise visual, a escolha de layout.

Nada muda no que se baixa: o mesmo formato, a mesma cascata de rotas e
cookies do `main.download_youtube_video`, so a ordem dos dois arquivos. A
qualidade do corte e a mesma, e o arquivo final e o mesmo mp4.

* **O audio e COPIADO assim que termina.** O yt-dlp apaga os pedacos depois
  de juntar, e uma tentativa que falha no video e recomeca da zero -- ler o
  arquivo dele enquanto ele ainda mexe nos proprios arquivos e pedir corrida.
  A copia fica na pasta do job, no disco de quem usa, e sai no fim.
* **O primeiro audio vale.** Uma tentativa que baixou o audio e caiu no video
  recomeca, e baixa o mesmo audio de novo: e o mesmo som, e a transcricao ja
  esta andando em cima do primeiro.
* **Falhou o download, falha o job** -- so que depois. O erro fica guardado e
  sobe quando alguem pede o video (ou antes, em `levantar_se_falhou`, entre
  um estagio e outro).
* **Sem parte de audio separada, e o caminho de antes**: formato progressivo
  (um arquivo so) nao dispara o aviso, e `aguardar_audio` devolve None quando
  o download termina -- o job segue com o video inteiro, como sempre fez.
"""
import os
import shutil
import threading
import time

#: A copia do audio, na pasta do job. Oculta, como o `.audio16k.wav`.
NOME_DO_AUDIO = ".audio_primeiro"


def ligado():
    """`AUDIO_PRIMEIRO=0` volta ao download de antes (video, audio, junta)."""
    return os.environ.get("AUDIO_PRIMEIRO", "1").strip() != "0"


# --- o seletor de formato ---------------------------------------------------

def _dividir(texto, separador):
    """`texto.split(separador)`, mas sem cortar dentro de `[...]`."""
    partes, atual, fundo = [], [], 0
    for c in texto:
        if c == "[":
            fundo += 1
        elif c == "]":
            fundo = max(0, fundo - 1)
        if c == separador and fundo == 0:
            partes.append("".join(atual))
            atual = []
        else:
            atual.append(c)
    partes.append("".join(atual))
    return partes


def audio_antes(seletor):
    """`video+audio/.../best` -> `audio+video/.../best`.

    O yt-dlp baixa as partes de um `A+B` na ordem em que estao escritas, e so
    isso muda: cada alternativa continua escolhendo exatamente o mesmo par. As
    alternativas de arquivo unico (`best[...]`) ficam como estao.
    """
    alternativas = []
    for alt in _dividir(seletor, "/"):
        partes = _dividir(alt, "+")
        if (len(partes) == 2 and partes[0].startswith("bestvideo")
                and partes[1].startswith("bestaudio")):
            alt = f"{partes[1]}+{partes[0]}"
        alternativas.append(alt)
    return "/".join(alternativas)


def e_parte_de_audio(d):
    """O aviso do yt-dlp e o de um arquivo SO de audio que terminou?"""
    info = d.get("info_dict") or {}
    return (d.get("status") == "finished" and bool(d.get("filename"))
            and info.get("vcodec") == "none"
            and (info.get("acodec") or "none") != "none")


# --- o download numa thread -------------------------------------------------

class DownloadEmParalelo:
    """Roda `baixar(ao_audio)` numa thread e avisa quando o audio chega.

    `baixar` e o `fetch` do adapter com o aviso ligado; devolve o `Fetched`.
    """

    def __init__(self, baixar, pasta):
        self._baixar = baixar
        self._pasta = pasta
        self._mudou = threading.Event()       # chegou o audio OU acabou
        self._terminou = threading.Event()
        self.audio = None
        self.titulo = None
        self.resultado = None
        self.erro = None
        self.t_inicio = None
        self.t_audio = None
        self.t_fim = None

    def iniciar(self):
        self.t_inicio = time.monotonic()
        threading.Thread(target=self._rodar, name="download-do-video",
                         daemon=True).start()
        return self

    def _rodar(self):
        try:
            self.resultado = self._baixar(self._ao_audio)
        except BaseException as e:  # noqa: BLE001 - sobe na thread de quem pedir
            # BaseException porque o `exit(1)` do caminho de erro tambem tem de
            # chegar a quem espera, e nao morrer calado aqui.
            self.erro = e
        finally:
            self.t_fim = time.monotonic()
            self._terminou.set()
            self._mudou.set()

    def _ao_audio(self, d, titulo=None):
        if self.audio is not None or not e_parte_de_audio(d):
            return
        origem = d["filename"]
        destino = os.path.join(self._pasta, NOME_DO_AUDIO + os.path.splitext(origem)[1])
        try:
            shutil.copyfile(origem, destino)
        except OSError as e:
            print(f"   ⚠️ Nao consegui separar o audio ({e}); a transcricao "
                  f"espera o video inteiro.", flush=True)
            return
        self.titulo = titulo
        self.t_audio = time.monotonic()
        self.audio = destino
        self._mudou.set()

    # -- quem espera ----------------------------------------------------------

    def aguardar_audio(self):
        """O caminho da copia do audio assim que ela existe.

        None quando o download terminou sem parte de audio separada; o erro do
        download, se ele falhou antes do audio.
        """
        self._mudou.wait()
        if self.audio is not None:
            # O aviso sai daqui, na thread de quem espera, e nao do `_ao_audio`.
            # Aquele roda na thread do download, onde a linha de progresso do
            # yt-dlp ainda esta pela metade (ele reescreve com `\r` e so poe o
            # `\n` depois): impresso de la, o aviso saia grudado nela --
            # "[download] 100% of 9.73MiB ...  🎧 Audio pronto", no log de 165 s.
            print(f"   🎧 Audio pronto em {self.t_audio - self.t_inicio:.1f}s: a "
                  f"transcricao comeca enquanto o video termina de baixar.", flush=True)
            return self.audio
        if self.erro is not None:
            raise self.erro
        return None

    def aguardar_video(self):
        """O `Fetched` do download inteiro; levanta o erro dele se falhou."""
        self._terminou.wait()
        if self.erro is not None:
            raise self.erro
        return self.resultado

    def esperar_terminar(self):
        """Espera sem levantar nada: o erro aparece em `aguardar_video`."""
        self._terminou.wait()

    def levantar_se_falhou(self):
        if self._terminou.is_set() and self.erro is not None:
            raise self.erro

    def caminho_previsto(self):
        """O mp4 que o download vai deixar, antes de ele terminar.

        E a mesma expressao do `main.download_youtube_video`. Serve de chave
        ao checkpoint da transcricao, que existe antes do video.
        """
        return os.path.join(self._pasta, f"{self.titulo or 'youtube_video'}.mp4")

    def apagar_copia(self):
        if self.audio:
            try:
                os.remove(self.audio)
            except OSError:
                pass
