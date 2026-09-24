"""O modelo de transcricao carregado UMA vez, fora do job (24-set-2026).

Todo job e um `main.py` novo, entao todo job subia o whisper do zero: 13,8 s no
log de 192 s, 23,5 s no anterior -- ~1,6 GB lidos do `.cache/` no disco do
Windows, mais a subida do CUDA. Um volume do Docker cortaria a leitura, mas poe
1,6 GB no disco do Docker, e o autor preferiu nao.

Aqui o modelo mora num processo proprio. O servidor o sobe quando alguem abre
o painel (`POST /api/asr/aquecer`) ou quando um video comeca (`app.run_job`),
e ele se desliga sozinho depois de `ASR_RESIDENTE_OCIOSO_MIN` minutos sem uso.
**Nem para sempre, nem por aba:** o modelo e do SERVIDOR, e serve todas as abas
e todas as pessoas da mesma instalacao. O painel manda um sinal a cada poucos
minutos enquanto esta aberto, entao "sem uso" quer dizer "ninguem com o painel
aberto e nenhum video em andamento".

O que o desenho protege, e por que:

* **O modelo nasce e trabalha na MESMA thread, e o processo nunca faz fork.**
  E o oposto exato das duas suspeitas da pre-carga que travou em 23-set-2026
  (`transcribe_backends._get_whisper_model`): a thread que criou o modelo ja
  tinha acabado quando ele foi usado, e o CUDA subiu enquanto o processo fazia
  fork para o yt-dlp. Aqui a thread de trabalho vive o processo inteiro, e o
  processo so transcreve.
* **Qualquer duvida volta ao caminho de hoje.** O cliente devolve `None` e o
  job carrega o modelo sozinho, como sempre fez: residente desligado, ausente,
  de outra configuracao, lento demais para subir ou morto no meio. O job fica
  mais lento, nunca para.
* **Travou, morre.** Uma placa que parou de responder nao volta sozinha. O laco
  principal mede o tempo desde o ultimo sinal de vida da thread de trabalho e
  encerra o processo quando passa do limite: o job ve a conexao cair e segue
  pelo caminho local, e o proximo aquecimento sobe um residente novo.
* **Socket de arquivo em /tmp, e nao porta de rede nem a pasta do projeto.** Um
  socket de arquivo so aceita quem ja esta dentro do container (pasta 0700), e
  nao ha porta nova exposta ao mundo. E ele nao pode morar em `/app`: aquilo e
  a pasta do Windows montada, onde socket nao abre. Nao e dado -- o arquivo tem
  zero byte --, entao nao fere o "nada do processamento dentro do Docker".
* **JSON, nao pickle.** Um pickle recebido e codigo executado.
* Uma transcricao por vez, na ordem de chegada: e o mesmo `_ASR_GATE` que o
  pipeline ja tinha, so que agora entre jobs e nao dentro de um.
"""
import json
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import time

#: Minutos sem uso (nem video, nem painel aberto) ate o residente soltar a placa.
OCIOSO_MIN_PADRAO = 10
#: De quanto em quanto tempo quem espera recebe sinal de vida.
BATIDA_S = 5.0
#: Sem mensagem nenhuma por este tempo, o job desiste e carrega sozinho.
SILENCIO_MAX_S = 60.0
#: Quanto o job espera o residente terminar de CARREGAR. Uma carga normal leva
#: 14 a 25 s; passou disto, sai mais barato o job carregar o dele.
ESPERA_CARGA_MAX_S = 150.0
#: A thread de trabalho sem sinal de vida por isto, no meio de uma transcricao:
#: travou. Uma janela de 30 s nunca leva minutos numa placa.
TRAVADO_S = 300.0
#: Uma carga que nao termina nisto travou. Generoso de proposito: a PRIMEIRA
#: carga numa instalacao nova inclui baixar ~1,6 GB do Hugging Face.
CARGA_MAX_S = 1800.0
#: Teto de uma mensagem. Uma hora de fala da ~1 MB de transcricao.
MENSAGEM_MAX = 64 * 1024 * 1024
#: Um residente que saiu porque a PLACA falhou nao e subido de novo por este
#: tempo. Sem isto, uma instalacao com `WHISPER_DEVICE=cuda` e a placa fora do
#: container tentaria (e cairia) a cada aviso do painel, de 2 em 2 minutos.
ESPERA_APOS_FALHA_S = 600.0
#: O codigo de saida de quem saiu porque a placa falhou.
SAIDA_FALHOU = 3


# --- configuracao -----------------------------------------------------------

def ativo():
    """Usar o residente? `ASR_RESIDENTE`: `auto` (padrao), `1` ou `0`.

    `auto` liga so com o whisper NA PLACA: e la que a carga custa (em CPU o
    modelo pequeno sobe em segundos) e e so o whisper que ele serve -- com o
    Parakeet como transcritor principal, segurar o whisper na placa seria
    ocupar memoria de video para o caso raro da queda.
    """
    modo = os.environ.get("ASR_RESIDENTE", "auto").strip().lower()
    if modo in ("0", "off", "false", "no", "nao", "não"):
        return False
    if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
        return False
    if modo in ("1", "on", "true", "yes", "sim"):
        return True
    backend = os.environ.get("TRANSCRIBE_BACKEND", "whisper").strip().lower()
    dispositivo = os.environ.get("WHISPER_DEVICE", "cpu").strip().lower()
    return backend == "whisper" and dispositivo.startswith("cuda")


def endereco():
    return (os.environ.get("ASR_RESIDENTE_SOCKET", "").strip()
            or "/tmp/cortes-asr/asr.sock")


def ocioso_s():
    """Com piso de 1 minuto: zero faria o modelo subir e descer a cada video."""
    try:
        minutos = float(os.environ.get("ASR_RESIDENTE_OCIOSO_MIN", OCIOSO_MIN_PADRAO))
    except ValueError:
        minutos = OCIOSO_MIN_PADRAO
    return max(minutos, 1.0) * 60.0


# --- mensagens: 4 bytes de tamanho + JSON ------------------------------------

def _enviar(sock, mensagem):
    dados = json.dumps(mensagem, ensure_ascii=False).encode("utf-8")
    sock.sendall(struct.pack(">I", len(dados)) + dados)


def _ler(sock, n):
    partes, falta = [], n
    while falta:
        pedaco = sock.recv(min(falta, 1 << 20))
        if not pedaco:
            raise ConnectionError("a conexao fechou")
        partes.append(pedaco)
        falta -= len(pedaco)
    return b"".join(partes)


def _receber(sock):
    (n,) = struct.unpack(">I", _ler(sock, 4))
    if n > MENSAGEM_MAX:
        raise ValueError(f"mensagem de {n} bytes")
    return json.loads(_ler(sock, n).decode("utf-8"))


def _conectar(timeout):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(endereco())
    except OSError:
        s.close()
        raise
    return s


# --- cliente: o job e o servidor HTTP ---------------------------------------

def pingar(timeout=0.5):
    """`{"estado": ..., "chave": ...}` do residente, ou None se nao ha nenhum.

    Tambem conta como uso: e o sinal que o painel manda enquanto esta aberto.
    """
    if not hasattr(socket, "AF_UNIX"):
        return None
    try:
        s = _conectar(timeout)
    except OSError:
        return None
    try:
        _enviar(s, {"tipo": "ping"})
        resposta = _receber(s)
        return resposta if resposta.get("tipo") == "pong" else None
    except (OSError, ValueError):
        return None
    finally:
        s.close()


def transcrever(media_path, chave, params, *, linha_do_whisper="", progresso=None,
                silencio_max_s=SILENCIO_MAX_S, espera_carga_max_s=ESPERA_CARGA_MAX_S):
    """A transcricao pronta (o contrato do `transcribe_backends`), ou None.

    `progresso(total)` e o mesmo medidor que o job ja usava: as linhas
    "Transcribing… 25%" saem no log do JOB, com a posicao que o residente
    manda. Sem residente nao sai linha nenhuma -- e o caminho de antes.
    """
    try:
        s = _conectar(2.0)
    except OSError:
        return None
    chegou = time.monotonic()
    medidor = None
    esperando_carga = False
    try:
        s.settimeout(silencio_max_s)
        _enviar(s, {"tipo": "transcrever", "arquivo": os.path.abspath(media_path),
                    "chave": list(chave), "params": params})
        while True:
            m = _receber(s)
            tipo = m.get("tipo")
            if tipo == "estado":
                if m.get("estado") == "carregando":
                    if not esperando_carga:
                        esperando_carga = True
                        print("   ⏳ [ASR] o modelo ainda esta subindo na placa "
                              "(processo residente); esperando.", flush=True)
                    if time.monotonic() - chegou > espera_carga_max_s:
                        print(f"   ⚠️ [ASR] o residente nao terminou de carregar em "
                              f"{espera_carga_max_s:.0f}s — carregando o modelo "
                              f"neste job.", flush=True)
                        return None
            elif tipo == "inicio":
                if linha_do_whisper:
                    print(linha_do_whisper, flush=True)
                espera = time.monotonic() - chegou
                print("   ⚡ [ASR] modelo ja na placa (processo residente): "
                      + (f"esperei {espera:.1f}s por ele" if espera >= 1
                         else "nenhuma carga neste job"), flush=True)
            elif tipo == "progresso":
                if medidor is None and progresso is not None:
                    medidor = progresso(m.get("total") or 0)
                if medidor is not None:
                    medidor.update(float(m.get("pos") or 0))
            elif tipo == "pronto":
                t = m.get("transcricao")
                if isinstance(t, dict) and isinstance(t.get("segments"), list):
                    return t
                print("   ⚠️ [ASR] o residente devolveu uma transcricao sem "
                      "segmentos — carregando o modelo neste job.", flush=True)
                return None
            elif tipo in ("recusado", "erro"):
                print(f"   ⚠️ [ASR] residente: {m.get('motivo')} — carregando o "
                      f"modelo neste job.", flush=True)
                return None
    except (OSError, ValueError) as e:
        # socket.timeout e ConnectionError sao OSError; JSON ruim e ValueError.
        print(f"   ⚠️ [ASR] o residente parou de responder ({type(e).__name__}) "
              f"— carregando o modelo neste job.", flush=True)
        return None
    finally:
        s.close()


# --- servidor: o processo residente -----------------------------------------

class JaExiste(RuntimeError):
    """Outro residente ja segura este endereco."""


class _Abandonado(BaseException):
    """O job que pediu foi embora: parar de gastar a placa com ele.

    `BaseException` de proposito: a tentativa em lotes de
    `transcribe_backends._decodificar` pega `Exception` e refaz no sequencial
    -- que e o contrario de parar.
    """


class _Pedido:
    def __init__(self, arquivo, params):
        self.arquivo = arquivo
        self.params = params
        self.saida = queue.Queue()
        self.abandonado = threading.Event()


class _Progresso:
    """Leva a posicao ao job, e e o sinal de vida da thread de trabalho."""

    def __init__(self, servidor, pedido, total):
        self.servidor = servidor
        self.pedido = pedido
        self.total = float(total or 0)

    def update(self, posicao):
        if self.pedido.abandonado.is_set():
            raise _Abandonado()
        self.servidor.ultimo_sinal = time.monotonic()
        self.pedido.saida.put({"tipo": "progresso", "pos": float(posicao),
                               "total": self.total})


def _carregar_modelo():
    """Na thread de trabalho: o mesmo singleton que o job usaria."""
    import transcribe_backends as tb

    inicio = time.monotonic()
    modelo, dispositivo = tb._get_whisper_model()
    return modelo, dispositivo, tb._whisper_key, time.monotonic() - inicio


def _decodificar_com(modelo, dispositivo, arquivo, params, progresso):
    import transcribe_backends as tb

    segmentos, info = tb._decodificar(modelo, dispositivo, arquivo, params, progresso)
    return tb._transcricao_de(segmentos, info)


class Servidor:
    def __init__(self, caminho, ocioso, *, carregar=None, decodificar=None,
                 batida=BATIDA_S, travado=TRAVADO_S, carga_max=CARGA_MAX_S):
        self.caminho = caminho
        self.ocioso = ocioso
        self.batida = batida
        self.travado = travado
        self.carga_max = carga_max
        self._carregar = carregar or _carregar_modelo
        self._decodificar = decodificar or _decodificar_com
        self.fila = queue.Queue()
        self.estado = "carregando"        # carregando | pronto | falhou
        self.motivo = None
        self.chave = None
        self.pronto = threading.Event()   # a carga terminou, bem ou mal
        self.ocupado = False
        self.nascimento = time.monotonic()
        self.ultimo_uso = self.nascimento
        self.ultimo_sinal = self.nascimento
        self.sock = None
        self._trava_fd = None

    # -- abrir e fechar -------------------------------------------------------

    def abrir(self):
        import fcntl

        pasta = os.path.dirname(self.caminho) or "."
        os.makedirs(pasta, mode=0o700, exist_ok=True)
        # A trava decide quem e o residente, sem corrida: dois `garantir` ao
        # mesmo tempo sobem dois processos, e so um passa daqui.
        self._trava_fd = os.open(self.caminho + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._trava_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self._trava_fd)
            self._trava_fd = None
            raise JaExiste(self.caminho)
        try:
            os.unlink(self.caminho)       # sobra de um residente que morreu
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.caminho)
        os.chmod(self.caminho, 0o600)
        self.sock.listen(16)

    def fechar(self, motivo):
        print(f"💤 [ASR residente] soltando a placa: {motivo}.", flush=True)
        for acao in (lambda: self.sock and self.sock.close(),
                     lambda: os.unlink(self.caminho),
                     lambda: self._trava_fd is not None and os.close(self._trava_fd)):
            try:
                acao()
            except OSError:
                pass

    # -- a thread de trabalho: nasce com o processo, carrega E transcreve ----

    def trabalhar(self):
        try:
            modelo, dispositivo, chave, segundos = self._carregar()
        except Exception as e:  # noqa: BLE001 - qualquer falha e "nao sirvo"
            self.motivo = f"a carga do modelo falhou ({type(e).__name__}: {e})"[:400]
            self.estado = "falhou"
            print(f"❌ [ASR residente] {self.motivo}", flush=True)
            self.pronto.set()
            return
        self.chave = list(chave)
        self.estado = "pronto"
        self.pronto.set()
        print(f"🔥 [ASR residente] whisper {chave[0]} em {chave[1]} ({chave[2]}) "
              f"pronto na placa em {segundos:.1f}s.", flush=True)
        while self.estado == "pronto":
            try:
                pedido = self.fila.get(timeout=1.0)
            except queue.Empty:
                continue
            if pedido.abandonado.is_set():
                continue
            self.ocupado = True
            self.ultimo_sinal = time.monotonic()
            try:
                pedido.saida.put({"tipo": "inicio"})
                transcricao = self._decodificar(
                    modelo, dispositivo, pedido.arquivo, pedido.params,
                    lambda total, p=pedido: _Progresso(self, p, total))
                pedido.saida.put({"tipo": "pronto", "transcricao": transcricao})
            except _Abandonado:
                print("   [ASR residente] o job que pediu foi embora; parei no meio.",
                      flush=True)
            except Exception as e:  # noqa: BLE001 - o job segue pelo caminho local
                motivo = f"{type(e).__name__}: {e}"[:400]
                pedido.saida.put({"tipo": "erro",
                                  "motivo": f"a transcricao falhou ({motivo})"})
                if "cuda" in motivo.lower():
                    # A placa falhou no meio: um modelo nesse estado nao volta
                    # sozinho, e o proximo pedido cairia na mesma parede.
                    self.motivo = motivo
                    self.estado = "falhou"
            finally:
                self.ocupado = False
                self.ultimo_uso = time.monotonic()

    # -- uma thread por conexao ---------------------------------------------

    def atender(self, conn):
        pedido = None
        try:
            conn.settimeout(30)
            msg = _receber(conn)
            self.ultimo_uso = time.monotonic()
            tipo = msg.get("tipo")
            if tipo == "ping":
                _enviar(conn, {"tipo": "pong", "estado": self.estado,
                               "chave": self.chave, "motivo": self.motivo})
                return
            if tipo != "transcrever":
                _enviar(conn, {"tipo": "erro", "motivo": f"pedido desconhecido: {tipo!r}"})
                return
            while not self.pronto.wait(self.batida):
                _enviar(conn, {"tipo": "estado", "estado": "carregando"})
            if self.estado != "pronto":
                _enviar(conn, {"tipo": "recusado",
                               "motivo": self.motivo or "o residente nao esta pronto"})
                return
            if list(msg.get("chave") or []) != self.chave:
                _enviar(conn, {"tipo": "recusado",
                               "motivo": f"o residente tem {self.chave}, o job pediu "
                                         f"{msg.get('chave')}"})
                return
            pedido = _Pedido(msg.get("arquivo"), msg.get("params") or {})
            self.fila.put(pedido)
            while True:
                try:
                    m = pedido.saida.get(timeout=self.batida)
                except queue.Empty:
                    _enviar(conn, {"tipo": "estado",
                                   "estado": "transcrevendo" if self.ocupado else "na_fila"})
                    continue
                _enviar(conn, m)
                if m.get("tipo") in ("pronto", "erro"):
                    return
        except (OSError, ValueError):
            if pedido is not None:
                pedido.abandonado.set()
        finally:
            self.ultimo_uso = time.monotonic()
            try:
                conn.close()
            except OSError:
                pass

    # -- o laco principal: aceita e vigia -------------------------------------

    def motivo_para_sair(self, agora=None):
        agora = time.monotonic() if agora is None else agora
        if self.estado == "falhou" and not self.ocupado:
            return self.motivo or "a placa falhou"
        if self.estado == "carregando" and agora - self.nascimento > self.carga_max:
            return f"a carga do modelo nao terminou em {self.carga_max:.0f}s"
        if self.ocupado and agora - self.ultimo_sinal > self.travado:
            return f"a transcricao parou de andar ha {self.travado:.0f}s"
        if (self.estado == "pronto" and not self.ocupado and self.fila.empty()
                and agora - self.ultimo_uso > self.ocioso):
            return f"{self.ocioso / 60:.0f} min sem uso"
        return None

    def laco(self):
        threading.Thread(target=self.trabalhar, name="asr-trabalho", daemon=True).start()
        self.sock.settimeout(min(1.0, self.batida))
        while True:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                conn = None
            except OSError as e:
                return f"o socket fechou ({e})"
            if conn is not None:
                threading.Thread(target=self.atender, args=(conn,), daemon=True).start()
            motivo = self.motivo_para_sair()
            if motivo:
                time.sleep(0.2)   # deixa quem esta respondendo terminar a frase
                return motivo


def servir():
    """O processo residente: `python asr_residente.py --servir`."""
    s = Servidor(endereco(), ocioso_s())
    try:
        s.abrir()
    except JaExiste:
        print("[ASR residente] ja ha um de pe neste endereco; saindo.", flush=True)
        return 0
    s.fechar(s.laco())
    sys.stdout.flush()
    # `_exit` e nao `exit`: a thread de trabalho pode estar presa numa chamada
    # a placa, e esperar o interpretador desmontar tudo com ela ali e o jeito
    # de um processo que devia ter saido ficar segurando a memoria de video.
    os._exit(SAIDA_FALHOU if s.estado == "falhou" else 0)


# --- dono: o servidor HTTP --------------------------------------------------

_dono_lock = threading.Lock()
_processo = None
_falhou_em = None


def garantir(motivo=""):
    """Sobe o residente se ele nao estiver de pe, e devolve o estado.

    Nunca espera a carga: um ping curto e, se ninguem responder, um `Popen`. O
    ping tambem renova o prazo de ociosidade -- e por ele que o painel aberto
    mantem o modelo na placa.

    **Nunca levanta.** E chamado do `run_job`, logo antes de subir o video: um
    erro aqui derrubaria o job por causa de uma otimizacao, e sem o residente
    o job so carrega o modelo sozinho, como antes.
    """
    global _processo, _falhou_em
    if not ativo():
        return "desligado"
    resposta = pingar()
    if resposta:
        return resposta.get("estado") or "pronto"
    with _dono_lock:
        if _processo is not None:
            codigo = _processo.poll()
            if codigo is None:
                return "iniciando"
            _processo = None
            if codigo == SAIDA_FALHOU:
                _falhou_em = time.monotonic()
        if _falhou_em is not None and time.monotonic() - _falhou_em < ESPERA_APOS_FALHA_S:
            return "falhou"
        aqui = os.path.dirname(os.path.abspath(__file__))
        try:
            # Sessao propria: cancelar um job mata o GRUPO dele
            # (`app._sinalizar_grupo`), e o residente nao e de job nenhum.
            _processo = subprocess.Popen(
                [sys.executable, "-u", os.path.join(aqui, "asr_residente.py"), "--servir"],
                cwd=aqui, start_new_session=True)
        except OSError as e:
            print(f"⚠️ [ASR residente] nao consegui subir o processo ({e}); cada "
                  f"video carrega o modelo sozinho.", flush=True)
            return "falhou"
        print(f"🔥 [ASR residente] subindo o modelo na placa ({motivo or 'pedido'}).",
              flush=True)
    return "iniciando"


if __name__ == "__main__":
    if "--servir" in sys.argv[1:]:
        sys.exit(servir())
    print("uso: python asr_residente.py --servir", file=sys.stderr)
    sys.exit(2)
