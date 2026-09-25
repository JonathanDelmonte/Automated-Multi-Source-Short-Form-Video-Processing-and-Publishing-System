"""A atualizacao sozinha do ajudante (ajudante/atualizacao.py e iniciar.py).

O que se prende aqui, em ordem do custo do erro:

1. uma versao que nao passa na verificacao NUNCA vira a atual -- e, se ela
   trocou as dependencias, as da versao anterior voltam;
2. o `iniciar.py` sempre acha uma versao inteira, mesmo com o `atual.txt`
   apontando para o nada ou uma extracao que caiu no meio;
3. zip adulterado, de outra versao ou que escapa da pasta nao e extraido;
4. o motor so e reiniciado com a fila vazia e ninguem no painel.

Nada aqui precisa de Windows: a troca de verdade (instalar, verificar,
reabrir) roda no CI do Windows, contra o instalador compilado.
"""
import asyncio
import hashlib
import io
import json
import sys
import threading
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ajudante"))

import ajudante as aj  # noqa: E402
import atualizacao as at  # noqa: E402
import iniciar  # noqa: E402


# --- montagem -------------------------------------------------------------------

def _versao(base: Path, nome: str, deps: str = "torch==1\n", completa: bool = True) -> Path:
    pasta = base / "versoes" / nome
    (pasta / "ajudante").mkdir(parents=True)
    (pasta / "ajudante" / "ajudante.py").write_text("# ajudante\n")
    (pasta / "ajudante" / "requirements-windows.txt").write_text(deps)
    (pasta / "VERSAO").write_text(nome + "\n")
    if completa:
        (pasta / at.MARCA_COMPLETA).write_text(nome)
    return pasta


def _instalado(tmp_path: Path, atual: str = "10") -> "aj.Caminhos":
    """Um ajudante instalado na versao `atual`, rodando o codigo dela."""
    base = tmp_path / "VirtuClips"
    pasta = _versao(base, atual)
    c = aj.Caminhos(base, codigo=pasta)
    at.gravar_atual(c, atual)
    return c


def _nada(*_a, **_kw):
    return None


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def github(tmp_path):
    """Um servidor com o formato das URLs de download do GitHub Releases."""
    raiz = tmp_path / "releases"
    raiz.mkdir()
    s = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(raiz)))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        yield raiz, f"http://127.0.0.1:{s.server_port}"
    finally:
        s.shutdown()
        s.server_close()


def _publicar(raiz: Path, versao: str, arquivos: dict = None, sha: str = None) -> None:
    arquivos = arquivos if arquivos is not None else {
        "VERSAO": versao + "\n",
        "ajudante/ajudante.py": "# nova\n",
        "ajudante/requirements-windows.txt": "torch==1\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nome, conteudo in arquivos.items():
            z.writestr(nome, conteudo)
    dados = buf.getvalue()
    tag = f"ajudante-{versao}"
    (raiz / "download" / tag).mkdir(parents=True, exist_ok=True)
    (raiz / "download" / tag / "motor.zip").write_bytes(dados)
    (raiz / "latest" / "download").mkdir(parents=True, exist_ok=True)
    info = {"versao": versao, "tag": tag,
            "motor_zip_sha256": sha or hashlib.sha256(dados).hexdigest()}
    (raiz / "latest" / "download" / "versao.json").write_text(json.dumps(info))


# --- versoes ---------------------------------------------------------------------

def test_versoes_em_ordem():
    assert at.mais_nova("464", "463")
    assert at.mais_nova("463.1", "463")
    assert not at.mais_nova("463", "463")
    assert not at.mais_nova("462", "463")
    # A de desenvolvimento perde para qualquer publicada, e vazio e "nenhuma".
    assert at.mais_nova("1", "0.0.0-local")
    assert at.mais_nova("1", "")
    assert not at.mais_nova("", "1")


def test_url_das_versoes():
    assert at.url_das_versoes({}) == at.RELEASES
    assert at.RELEASES.startswith("https://github.com/JonathanDelmonte/")
    assert at.url_das_versoes({"CORTES_ATUALIZACAO_URL": "http://x/y/"}) == "http://x/y"


# --- o iniciar.py ------------------------------------------------------------------

def test_iniciar_segue_o_atual(tmp_path):
    c = _instalado(tmp_path, "10")
    _versao(c.base, "11")
    assert iniciar.versao_em_uso(c.base) == c.versoes / "10"


def test_iniciar_cai_na_completa_mais_nova_quando_o_atual_quebra(tmp_path):
    c = _instalado(tmp_path, "10")
    _versao(c.base, "9")
    _versao(c.base, "12", completa=False)   # extracao que caiu no meio
    at.gravar_atual(c, "11")                # aponta para o nada
    assert iniciar.versao_em_uso(c.base) == c.versoes / "10"
    (c.base / "atual.txt").unlink()
    assert iniciar.versao_em_uso(c.base) == c.versoes / "10"


def test_iniciar_sem_versao_nenhuma(tmp_path):
    assert iniciar.versao_em_uso(tmp_path) is None


def test_iniciar_e_o_ajudante_concordam_na_marca_e_na_ordem():
    """O `iniciar.py` nao importa nada do motor (ele nunca e atualizado), entao
    repete duas definicoes -- e elas nao podem divergir."""
    assert iniciar.MARCA_COMPLETA == at.MARCA_COMPLETA
    for v in ("463", "463.1", "0.0.0-local", "12"):
        assert iniciar._chave(v) == at.chave(v)


def test_gravar_atual_nao_deixa_arquivo_pela_metade(tmp_path):
    c = _instalado(tmp_path, "10")
    at.gravar_atual(c, "11")
    assert (c.base / "atual.txt").read_text().strip() == "11"
    assert not (c.base / "atual.txt.tmp").exists()


# --- preparar (baixar e extrair) ----------------------------------------------------

def test_prepara_a_versao_nova_sem_tocar_na_atual(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11")
    nova = at.preparar_se_houver(c, _nada, url)
    assert nova == c.versoes / "11" and at.completa(nova)
    assert (c.base / "atual.txt").read_text().strip() == "10"
    assert not list((c.dados / "atualizacao").glob("*")), "o zip fica para tras"
    # Ja preparada: nao baixa de novo.
    assert at.preparar_se_houver(c, _nada, url, baixar_fn=pytest.fail) == nova


def test_mesma_versao_nao_baixa(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "10")
    assert at.preparar_se_houver(c, _nada, url, baixar_fn=pytest.fail) is None


def test_versao_que_ja_falhou_nao_e_tentada_de_novo(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11")
    at.registrar(c, "11", "revertida")
    assert at.preparar_se_houver(c, _nada, url, baixar_fn=pytest.fail) is None
    _publicar(raiz, "12")  # a seguinte, sim
    assert at.preparar_se_houver(c, _nada, url) == c.versoes / "12"


def test_zip_adulterado_e_recusado(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11", sha="0" * 64)
    with pytest.raises(ValueError, match="nao confere"):
        at.preparar_se_houver(c, _nada, url)
    assert not (c.versoes / "11").exists()
    assert not list((c.dados / "atualizacao").glob("*"))


def test_zip_que_escapa_da_pasta_e_recusado(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11", {"VERSAO": "11\n", "../../fora.txt": "x"})
    with pytest.raises(ValueError, match="fora da pasta"):
        at.preparar_se_houver(c, _nada, url)
    assert not list(tmp_path.rglob("fora.txt"))


def test_zip_de_outra_versao_e_recusado(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11", {"VERSAO": "9\n", "ajudante/ajudante.py": ""})
    with pytest.raises(ValueError, match="versao"):
        at.preparar_se_houver(c, _nada, url)
    assert not at.completa(c.versoes / "11")


# --- aplicar (a troca) ----------------------------------------------------------------

class _Registro:
    def __init__(self, verificacao=True, dependencias=True):
        self.chamadas = []
        self.verificacao = verificacao
        self.dependencias = dependencias

    def verificar(self, _c, pasta, _log):
        self.chamadas.append(("verificar", pasta.name))
        return self.verificacao

    def deps(self, _c, pasta, _log):
        self.chamadas.append(("deps", pasta.name))
        return self.dependencias if pasta.name != "10" else True

    def ytdlp(self, _c, _log):
        self.chamadas.append(("ytdlp",))

    def aplicar(self, c, nova):
        return at.aplicar(c, nova, _nada, verificar_fn=self.verificar,
                          dependencias_fn=self.deps, ytdlp_fn=self.ytdlp)


def test_troca_quando_a_verificacao_passa(tmp_path):
    c = _instalado(tmp_path, "10")
    _versao(c.base, "9")
    nova = _versao(c.base, "11")
    r = _Registro()
    assert r.aplicar(c, nova)
    assert (c.base / "atual.txt").read_text().strip() == "11"
    assert iniciar.versao_em_uso(c.base) == nova
    # A anterior fica (para voltar a mao); as mais velhas saem.
    assert sorted(p.name for p in c.versoes.iterdir()) == ["10", "11"]
    assert r.chamadas == [("ytdlp",), ("verificar", "11")]
    assert at.ler_estado(c)["ultima"]["resultado"] == "aplicada"


def test_versao_que_nao_passa_nao_vira_a_atual(tmp_path):
    c = _instalado(tmp_path, "10")
    nova = _versao(c.base, "11")
    r = _Registro(verificacao=False)
    assert not r.aplicar(c, nova)
    assert (c.base / "atual.txt").read_text().strip() == "10"
    assert not nova.exists()
    assert "11" in at.ler_estado(c)["falhou"]


def test_dependencias_novas_voltam_se_a_versao_nao_passa(tmp_path):
    """Os pinos sao exatos: reinstalar a lista da versao anterior devolve o
    venv ao que ela conhecia."""
    c = _instalado(tmp_path, "10")
    nova = _versao(c.base, "11", deps="torch==2\n")
    r = _Registro(verificacao=False)
    assert not r.aplicar(c, nova)
    assert r.chamadas == [("deps", "11"), ("verificar", "11"), ("deps", "10")]


def test_dependencias_que_nao_instalam_nem_chegam_a_verificacao(tmp_path):
    c = _instalado(tmp_path, "10")
    nova = _versao(c.base, "11", deps="torch==2\n")
    r = _Registro(dependencias=False)
    assert not r.aplicar(c, nova)
    assert r.chamadas == [("deps", "11"), ("deps", "10")]
    assert (c.base / "atual.txt").read_text().strip() == "10"


def test_pasta_incompleta_nunca_vira_a_atual(tmp_path):
    c = _instalado(tmp_path, "10")
    nova = _versao(c.base, "11", completa=False)
    r = _Registro()
    assert not r.aplicar(c, nova)
    assert r.chamadas == []
    assert (c.base / "atual.txt").read_text().strip() == "10"


def test_do_servidor_ate_a_troca(tmp_path, github):
    raiz, url = github
    c = _instalado(tmp_path, "10")
    _publicar(raiz, "11")
    nova = at.preparar_se_houver(c, _nada, url)
    assert _Registro().aplicar(c, nova)
    assert iniciar.versao_em_uso(c.base) == c.versoes / "11"
    # A versao nova e a que roda agora: nao ha mais nada a trocar.
    c2 = aj.Caminhos(c.base, codigo=c.versoes / "11")
    assert at.preparar_se_houver(c2, _nada, url) is None


# --- quando trocar ---------------------------------------------------------------------

@pytest.mark.parametrize("estado, saude, pode", [
    (aj.DOCKER, None, True),          # o Docker atende: nao ha o que proteger
    (aj.ERRO, None, True),            # quebrado: a versao nova pode ser o conserto
    (aj.PRONTO, None, True),          # motor sem resposta
    (aj.PRONTO, {"status": "ok"}, True),
    (aj.PRONTO, {"jobs_ativos": 1, "ocioso_s": 9999}, False),
    (aj.PRONTO, {"jobs_ativos": 0, "ocioso_s": 30}, False),
    (aj.PRONTO, {"jobs_ativos": 0, "ocioso_s": at.OCIOSO_MINIMO_S}, True),
])
def test_so_reinicia_com_a_fila_vazia_e_ninguem_no_painel(estado, saude, pode):
    assert at.pode_trocar_agora(estado, lambda: saude) is pode


# --- o pacote ---------------------------------------------------------------------------

def test_o_zip_nao_leva_a_marca_e_o_conteudo_nao_depende_da_versao(tmp_path):
    import empacotar
    binarios = tmp_path / "bin"
    binarios.mkdir()
    for nome in empacotar.BINARIOS:
        (binarios / nome).write_bytes(b"x")
    a = empacotar.empacotar("11", binarios, pacote=tmp_path / "p1", saida=tmp_path / "s1",
                            imagens=False)
    b = empacotar.empacotar("12", binarios, pacote=tmp_path / "p2", saida=tmp_path / "s2",
                            imagens=False)
    # O CI so publica quando o `conteudo` muda: a versao sozinha nao conta.
    assert a["conteudo"] == b["conteudo"]
    assert a["tag"] == "ajudante-11"
    with zipfile.ZipFile(tmp_path / "s1" / "motor.zip") as z:
        nomes = set(z.namelist())
        assert z.read("VERSAO").decode().strip() == "11"
    assert at.MARCA_COMPLETA not in nomes, "a extracao e quem marca a pasta completa"
    assert {"app.py", "main.py", "ajudante/iniciar.py", "ajudante/atualizacao.py"} <= nomes
    assert (tmp_path / "p1" / "motor" / at.MARCA_COMPLETA).is_file()
    assert json.loads((tmp_path / "s1" / "versao.json").read_text())["versao"] == "11"


def test_mudanca_so_no_instalador_tambem_vira_versao_nova(tmp_path):
    """O CI publica quando a impressao digital muda. Ela e do motor -- mas o
    .iss nao vai no motor, e sem ele uma mudanca so no instalador nao seria
    publicada: o site continuaria oferecendo o instalador de antes."""
    import empacotar
    assert empacotar.AQUI / "instalador.iss" in empacotar.SO_DO_INSTALADOR
    motor = tmp_path / "motor"
    motor.mkdir()
    (motor / "app.py").write_text("# motor\n")
    iss = tmp_path / "instalador.iss"
    iss.write_text("[Setup]\nAppName=Virtu Clips\n")
    antes = empacotar.impressao_do_conteudo(motor, (iss,))
    assert empacotar.impressao_do_conteudo(motor, (iss,)) == antes
    iss.write_text("[Setup]\nAppName=Virtu Clips\nWizardStyle=modern dark\n")
    assert empacotar.impressao_do_conteudo(motor, (iss,)) != antes


def test_o_python_vai_no_instalador_e_nao_na_atualizacao(tmp_path):
    """O Python embutido (desde 24-set-2026, o erro 448) vai em pacote/python,
    que o .iss copia; o motor.zip da atualizacao nao o leva -- a instalacao ja
    tem o dela, e sao dezenas de MB a cada versao."""
    import empacotar
    binarios = tmp_path / "bin"
    binarios.mkdir()
    for nome in empacotar.BINARIOS:
        (binarios / nome).write_bytes(b"x")
    python = tmp_path / "cpython-3.11.13-windows-x86_64-none"
    (python / "Lib").mkdir(parents=True)
    (python / "python.exe").write_bytes(b"MZ")
    (python / "Lib" / "os.py").write_text("# stdlib\n")
    empacotar.empacotar("11", binarios, pacote=tmp_path / "p", saida=tmp_path / "s",
                        imagens=False, python=python)
    assert (tmp_path / "p" / "python" / "python.exe").read_bytes() == b"MZ"
    assert (tmp_path / "p" / "python" / "Lib" / "os.py").is_file()
    with zipfile.ZipFile(tmp_path / "s" / "motor.zip") as z:
        assert not [n for n in z.namelist() if n.startswith("python/")]


def test_uma_pasta_sem_python_nao_vira_instalador(tmp_path):
    import empacotar
    (tmp_path / "vazia").mkdir()
    with pytest.raises(SystemExit, match="python.exe"):
        empacotar.copiar_python(tmp_path / "vazia", tmp_path / "destino")


# --- o motor diz se esta livre ------------------------------------------------------------

def _chama(caminho):
    import httpx
    import app as app_module

    async def _do():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as cliente:
            return await cliente.get(caminho)
    return asyncio.run(_do())


def test_health_diz_se_ha_job_e_ha_quanto_tempo_ninguem_mexe(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "jobs", {
        "a": {"status": "processing"}, "b": {"status": "queued"},
        "c": {"status": "completed"}, "d": {"status": "failed"}})
    monkeypatch.setattr(app_module, "_ultima_atividade", time.monotonic() - 1000)
    corpo = _chama("/health").json()
    assert corpo["status"] == "ok" and corpo["jobs_ativos"] == 2
    assert corpo["ocioso_s"] >= 1000
    # Perguntar a saude, a config ou aquecer o whisper nao e usar o painel...
    _chama("/api/config")
    assert _chama("/health").json()["ocioso_s"] >= 1000
    # ...qualquer outro pedido e.
    _chama("/api/rota-que-nao-existe")
    assert _chama("/health").json()["ocioso_s"] < 5


# --- o laco da bandeja -------------------------------------------------------------------

class _Laco:
    """Um `vigiar` com os prazos zerados e cada efeito contado."""

    def __init__(self, preparos, livre_depois=0, lancar_falha=False):
        self.preparos = list(preparos)   # o que cada conferencia devolve
        self.livre_depois = livre_depois  # quantas vezes o motor diz "ocupado"
        self.lancar_falha = lancar_falha
        self.parar = threading.Event()
        self.lancadas, self.saidas, self.perguntas, self.log = [], 0, 0, []

    def preparar(self, _c, _log):
        if not self.preparos:
            self.parar.set()
            return None
        item = self.preparos.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def pode(self, _estado):
        self.perguntas += 1
        return self.perguntas > self.livre_depois

    def lancar(self, _c, nova):
        if self.lancar_falha:
            raise OSError("pythonw sumiu")
        self.lancadas.append(nova.name)

    def sair(self):
        self.saidas += 1

    def rodar(self):
        at.vigiar(None, lambda: aj.PRONTO, self.parar, self.lancar, self.sair,
                  self.log.append, preparar_fn=self.preparar, pode_fn=self.pode,
                  primeira_s=0, intervalo_s=0, espera_s=0)


def test_laco_sem_versao_nova_nao_mexe_em_nada():
    laco = _Laco([None, None])
    laco.rodar()
    assert laco.lancadas == [] and laco.saidas == 0


def test_laco_espera_o_motor_ficar_livre_e_so_entao_troca():
    laco = _Laco([Path("versoes/11")], livre_depois=3)
    laco.rodar()
    assert laco.perguntas == 4, "perguntou ate o motor ficar livre"
    assert laco.lancadas == ["11"] and laco.saidas == 1


def test_laco_sem_internet_tenta_na_volta_seguinte():
    laco = _Laco([OSError("sem rede"), Path("versoes/11")])
    laco.rodar()
    assert laco.lancadas == ["11"]
    assert any("sem rede" in linha for linha in laco.log)


def test_laco_sem_o_processo_da_troca_o_ajudante_fica():
    laco = _Laco([Path("versoes/11")], lancar_falha=True)
    laco.rodar()
    assert laco.saidas == 0, "sair sem a troca deixaria a pessoa sem ajudante"
    assert any("nao conseguiu comecar" in linha for linha in laco.log)


def test_laco_para_quando_pedem():
    laco = _Laco([Path("versoes/11")], livre_depois=10**9)
    threading.Timer(0.2, laco.parar.set).start()
    laco.rodar()
    assert laco.lancadas == [] and laco.saidas == 0
