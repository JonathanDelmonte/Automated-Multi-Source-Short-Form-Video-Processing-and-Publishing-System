"""O botao "Atualizar agora" do site (atualizar_motor.py, 25-set-2026).

O que decide e o git, e o git aqui e de verdade: um repositorio "publicado"
(bare), um clone de quem escreve e o clone do Docker, que o botao avanca. Os
casos que importam sao os que estragariam a pasta do autor sem dar erro:

1. **o que mora na imagem nao e trocado pelo botao.** Avancar o codigo com um
   requirements.txt novo subiria um motor importando o que a imagem nao tem;
2. **o checkout do Windows continua CRLF.** O git do container nao le a
   configuracao do git do Windows; sem repetir a regra, os arquivos trocados
   sairiam com LF no meio de uma pasta CRLF -- e o `.bat` com LF e o que faz o
   cmd.exe errar o `goto`;
3. **nada e misturado nem sobrescrito**: so fast-forward, e mudanca local no
   caminho da versao nova e recusa, com o arquivo intacto.
"""
import asyncio
import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest

import atualizar_motor as am

RAIZ = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="sem git")

# Os dois casos da pasta do Windows sao o git do CONTAINER (Linux) lendo um
# checkout feito no Windows. No proprio Windows o git ja tem `autocrlf` na
# configuracao do sistema e o NTFS nao tem bit de execucao: o problema nao
# existe ali, e o controle negativo dos testes nao teria o que medir.
_SO_NO_LINUX = pytest.mark.skipif(os.name == "nt", reason="e o git do container Linux")

_IDENTIDADE = ["-c", "user.name=Teste", "-c", "user.email=teste@exemplo.invalid",
               "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]


def _g(pasta, *args, check=True, extra=()):
    r = subprocess.run(["git", *_IDENTIDADE, *extra, "-C", str(pasta), *args],
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def _escrever(pasta: Path, arquivos: dict) -> None:
    for nome, conteudo in arquivos.items():
        p = pasta / nome
        if conteudo is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(conteudo.encode("utf-8"))


class _Repos:
    """O publicado, o de quem escreve e o do Docker."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.origem = raiz / "origem.git"
        subprocess.run(["git", *_IDENTIDADE, "init", "-q", "--bare", str(self.origem)],
                       check=True, capture_output=True)
        self.dev = raiz / "dev"
        subprocess.run(["git", *_IDENTIDADE, "clone", "-q", str(self.origem), str(self.dev)],
                       check=True, capture_output=True)
        self.publicar({
            "app.py": "print('motor')\nprint('v1')\n",
            "main.py": "print('pipeline')\n",
            "README.md": "# Virtu Clips\n",
            "requirements.txt": "fastapi\n",
            "atalhos/atualizar.bat": "@echo off\ngoto fim\n:fim\necho ok\n",
            "dashboard/src/App.jsx": "export default 1;\n",
        }, "inicio")

    def publicar(self, arquivos: dict, msg: str = "mudanca") -> str:
        _escrever(self.dev, arquivos)
        _g(self.dev, "add", "-A")
        _g(self.dev, "commit", "-q", "-m", msg)
        _g(self.dev, "push", "-q", "origin", "HEAD:main")
        return _g(self.dev, "rev-parse", "HEAD")

    def clonar(self, nome: str = "docker", crlf: bool = False) -> Path:
        destino = self.raiz / nome
        extra = ["-c", "core.autocrlf=true"] if crlf else []
        subprocess.run(["git", *_IDENTIDADE, *extra, "clone", "-q", str(self.origem),
                        str(destino)], check=True, capture_output=True)
        return destino


@pytest.fixture
def repos(tmp_path):
    return _Repos(tmp_path)


def _head(pasta):
    return _g(pasta, "rev-parse", "HEAD")


def _limpo(pasta, extra=()):
    return _g(pasta, "status", "--porcelain", extra=extra) == ""


# --- o que o botao faz ---------------------------------------------------------------

def test_sem_nada_novo_o_motor_ja_esta_atualizado(repos):
    docker = repos.clonar()
    assert am.atualizar_docker(docker, _head(docker)) == {"situacao": "atualizado"}
    # Sem saber com que commit o motor subiu, vale o disco.
    assert am.atualizar_docker(docker, None) == {"situacao": "atualizado"}


def test_mudanca_de_codigo_avanca_o_checkout_e_pede_o_reinicio(repos):
    docker = repos.clonar()
    subiu = _head(docker)
    novo = repos.publicar({"app.py": "print('motor')\nprint('v2')\n"})
    r = am.atualizar_docker(docker, subiu)
    assert r == {"situacao": "atualizou", "de": "1", "para": "2", "painel": False}
    assert _head(docker) == novo
    assert (docker / "app.py").read_text() == "print('motor')\nprint('v2')\n"
    assert _limpo(docker)
    assert not (docker / am.MARCA_DO_PAINEL).exists(), "o painel nao mudou: nao reinicia"


def test_arquivo_novo_do_painel_deixa_a_marca_para_o_vite(repos):
    """O arquivo NOVO e o caso que deixava o painel em preto: o polling do
    Vite ve edicao, nao grafo de modulos."""
    docker = repos.clonar()
    subiu = _head(docker)
    novo = repos.publicar({"dashboard/src/Novo.jsx": "export const x = 1;\n"})
    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "atualizou" and r["painel"] is True
    assert (docker / am.MARCA_DO_PAINEL).read_text().strip() == novo


@pytest.mark.parametrize("arquivo, reconstruir", [
    ("requirements.txt", True),
    ("dashboard/package.json", True),
    ("dashboard/package-lock.json", True),
    ("render-service/src/index.ts", True),
    ("remotion/src/Root.tsx", True),
    ("Dockerfile", True),
    ("dashboard/Dockerfile", True),
    ("fonts/openshorts-fontmap.conf", True),
    ("docker-compose.yml", False),
    ("docker-compose.gpu.yml", False),
])
def test_o_que_mora_na_imagem_fica_para_o_atalho(repos, arquivo, reconstruir):
    docker = repos.clonar()
    subiu = _head(docker)
    repos.publicar({arquivo: "mudou\n", "app.py": "print('v2')\n"})
    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "precisa_do_atalho"
    assert r["reconstruir"] is reconstruir
    assert r["arquivos"] == [arquivo] and r["total"] == 1
    # Nem o codigo avanca: metade de uma versao e o pior dos dois mundos.
    assert _head(docker) == subiu
    assert (docker / "app.py").read_text() == "print('motor')\nprint('v1')\n"


def test_baixado_por_fora_e_sem_reiniciar_o_motor_ainda_esta_atras(repos):
    """O `git pull` pelo GitHub Desktop deixa o disco em dia e o motor rodando
    o codigo de quando subiu. A distancia e do commit com que ele SUBIU."""
    docker = repos.clonar()
    subiu = _head(docker)
    novo = repos.publicar({"app.py": "print('v2')\n"})
    _g(docker, "pull", "-q", "origin", "main")
    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "atualizou" and _head(docker) == novo


def test_baixado_por_fora_com_dependencia_nova_ainda_precisa_reconstruir(repos):
    """O mesmo pull, trazendo um requirements.txt novo: reiniciar sem
    reconstruir seria o erro que o botao existe para nao cometer."""
    docker = repos.clonar()
    subiu = _head(docker)
    repos.publicar({"requirements.txt": "fastapi\nnova-lib\n"})
    _g(docker, "pull", "-q", "origin", "main")
    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "precisa_do_atalho" and r["arquivos"] == ["requirements.txt"]


def test_commit_de_quem_subiu_que_sumiu_vale_o_disco(repos):
    docker = repos.clonar()
    repos.publicar({"app.py": "print('v2')\n"})
    r = am.atualizar_docker(docker, "0" * 40)
    assert r["situacao"] == "atualizou"


# --- o que o botao recusa ---------------------------------------------------------------

def test_commits_locais_sao_recusados(repos):
    docker = repos.clonar()
    _escrever(docker, {"meu.txt": "local\n"})
    _g(docker, "add", "-A")
    _g(docker, "commit", "-q", "-m", "local")
    local = _head(docker)
    repos.publicar({"app.py": "print('v2')\n"})
    r = am.atualizar_docker(docker, local)
    assert r["situacao"] == "recusado" and r["causa"] == "divergiu"
    assert _head(docker) == local


def test_so_atualiza_a_main(repos):
    docker = repos.clonar()
    _g(docker, "checkout", "-q", "-b", "testes")
    r = am.atualizar_docker(docker, _head(docker))
    assert r["causa"] == "ramo" and r["ramo"] == "testes"


def test_mudanca_local_no_caminho_da_versao_nova_e_recusada_e_fica(repos):
    docker = repos.clonar()
    subiu = _head(docker)
    _escrever(docker, {"app.py": "print('mexido a mao')\n"})
    repos.publicar({"app.py": "print('v2')\n"})
    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "recusado" and r["causa"] == "mudancas_locais"
    assert r["arquivos"] == ["app.py"]
    assert (docker / "app.py").read_text() == "print('mexido a mao')\n"
    assert _head(docker) == subiu


def test_mudanca_local_em_outro_arquivo_nao_atrapalha(repos):
    docker = repos.clonar()
    subiu = _head(docker)
    _escrever(docker, {"README.md": "# anotacao minha\n"})
    repos.publicar({"app.py": "print('v2')\n"})
    assert am.atualizar_docker(docker, subiu)["situacao"] == "atualizou"
    assert (docker / "README.md").read_text() == "# anotacao minha\n"


def test_arquivo_solto_com_o_nome_do_que_chega_e_recusado(repos):
    docker = repos.clonar()
    subiu = _head(docker)
    _escrever(docker, {"dashboard/src/Novo.jsx": "meu\n"})
    repos.publicar({"dashboard/src/Novo.jsx": "export const x = 1;\n"})
    r = am.atualizar_docker(docker, subiu)
    assert r["causa"] == "arquivos_soltos" and r["arquivos"] == ["dashboard/src/Novo.jsx"]
    assert (docker / "dashboard/src/Novo.jsx").read_text() == "meu\n"


def test_sem_rede_diz_o_que_o_git_disse(repos):
    docker = repos.clonar()
    _g(docker, "remote", "set-url", "origin", str(repos.raiz / "nao-existe.git"))
    r = am.atualizar_docker(docker, _head(docker))
    assert r["situacao"] == "recusado" and r["causa"] == "sem_rede"
    assert r["linha"].startswith("fatal:")


def test_fora_de_um_repositorio(tmp_path):
    r = am.atualizar_docker(tmp_path, None)
    assert r["situacao"] == "recusado" and r["causa"] == "sem_repositorio"


# --- a pasta que veio do Windows --------------------------------------------------------

def _envelhecer(pasta: Path) -> None:
    """Muda o `stat` de todo arquivo, como o container ve a pasta do Windows:
    o indice foi gravado pelo git do Windows, e os numeros nao batem. E ai que
    o git relê o conteudo -- e compara CRLF com LF."""
    antes = time.time() - 3600
    for p in pasta.rglob("*"):
        if ".git" not in p.parts and p.is_file():
            os.utime(p, (antes, antes))


@_SO_NO_LINUX
def test_checkout_do_windows_continua_crlf(repos):
    docker = repos.clonar(crlf=True)
    assert b"\r\n" in (docker / "app.py").read_bytes()
    subiu = _head(docker)
    repos.publicar({"app.py": "print('motor')\nprint('v2')\n",
                    "atalhos/atualizar.bat": "@echo off\ngoto fim\nrem novo\n:fim\necho ok\n"})
    _envelhecer(docker)
    # Sem a regra, o git do container veria a pasta inteira como mudada.
    assert subprocess.run(["git", "-C", str(docker), "diff", "--quiet"]).returncode == 1

    r = am.atualizar_docker(docker, subiu)
    assert r["situacao"] == "atualizou"
    for nome in ("app.py", "atalhos/atualizar.bat"):
        conteudo = (docker / nome).read_bytes()
        assert b"\r\n" in conteudo and b"\n" not in conteudo.replace(b"\r\n", b""), nome
    assert _limpo(docker, extra=["-c", "core.autocrlf=true"])


@_SO_NO_LINUX
def test_bit_de_execucao_do_windows_nao_conta_como_mudanca(repos):
    """Montado no Linux, o NTFS mostra todo arquivo como executavel."""
    docker = repos.clonar()
    subiu = _head(docker)
    _g(docker, "config", "core.filemode", "true")
    (docker / "app.py").chmod(0o755)
    assert subprocess.run(["git", "-C", str(docker), "diff", "--quiet"]).returncode == 1
    repos.publicar({"app.py": "print('v2')\n"})
    assert am.atualizar_docker(docker, subiu)["situacao"] == "atualizou"


def test_o_commit_com_que_o_motor_subiu(repos, tmp_path):
    docker = repos.clonar()
    assert am.commit_de(docker) == _head(docker)
    assert am.commit_de(tmp_path / "nada") is None


# --- as regras ---------------------------------------------------------------------------

@pytest.mark.parametrize("caminho", [
    "requirements.txt", "dashboard/package.json", "dashboard/package-lock.json",
    "render-service/package.json", "render-service/src/index.ts", "remotion/src/Root.tsx",
    "Dockerfile", "dashboard/Dockerfile", "render-service/Dockerfile", ".dockerignore",
    "fonts/openshorts-fontmap.conf",
])
def test_fica_na_imagem(caminho):
    assert am.fica_na_imagem(caminho)


@pytest.mark.parametrize("caminho", [
    "app.py", "main.py", "dashboard/src/App.jsx", "dashboard/vite.config.js",
    "ajudante/requirements-windows.txt", "atalhos/atualizar.bat", "docs/COMO-EXECUTAR.md",
    "tests/test_x.py", "dashboard/public/fonts/anton.woff2",
    # A legenda le as fontes da pasta montada (`fontsdir`), e o gancho pelo caminho.
    "fonts/Anton-Regular.ttf",
])
def test_codigo_nao_fica_na_imagem(caminho):
    assert not am.fica_na_imagem(caminho)


def test_a_legenda_le_as_fontes_da_pasta_montada():
    """E o que deixa uma fonte nova valer sem reconstruir. Se a legenda
    passar a depender so do fontconfig do sistema, `fonts/` inteira volta a
    morar na imagem."""
    assert "fontsdir=" in (RAIZ / "subtitles.py").read_text(encoding="utf-8")


def test_o_compose():
    assert am.e_do_compose("docker-compose.yml") and am.e_do_compose("docker-compose.gpu.yml")
    assert not am.e_do_compose("docs/docker-compose.yml")
    assert not am.e_do_compose("docker-compose.md")


def _copias(dockerfile: Path, contexto: str, estagio=None) -> list:
    """O que um Dockerfile copia do repositorio, fora o `COPY . .` (que o bind
    mount do compose cobre). Com `estagio`, so as linhas dele: o compose
    constroi o painel no alvo `dev`."""
    fontes, dentro = [], estagio is None
    for linha in dockerfile.read_text(encoding="utf-8").splitlines():
        partes = linha.split()
        if not partes or partes[0].startswith("#"):
            continue
        if partes[0].upper() == "FROM":
            dentro = estagio is None or partes[-1] == estagio
            continue
        if dentro and partes[0].upper() == "COPY" and not any(
                p.startswith("--from") for p in partes):
            for fonte in partes[1:-1]:
                if fonte not in (".", "./"):
                    fonte = contexto + fonte.rstrip("*")
                    fontes.append(fonte + "x" if fonte.endswith("/") else fonte)
    return fontes


def test_tudo_o_que_as_imagens_copiam_fica_para_o_atalho():
    """Um `COPY` novo num Dockerfile e uma coisa a mais que so a reconstrucao
    troca. Sem este teste, o botao a avancaria como se fosse codigo."""
    copias = (_copias(RAIZ / "Dockerfile", "")
              + _copias(RAIZ / "dashboard" / "Dockerfile", "dashboard/", estagio="dev")
              + _copias(RAIZ / "render-service" / "Dockerfile", ""))
    assert "requirements.txt" in copias and "dashboard/package.json" in copias
    assert [c for c in copias if not am.fica_na_imagem(c)] == []
    # O Dockerfile do backend poe o mapa de fontes no fontconfig do sistema.
    assert "cp fonts/openshorts-fontmap.conf" in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


def test_o_compose_constroi_o_painel_no_estagio_dev():
    """`_copias` le so o estagio `dev` do painel: se o compose passar a
    construir outro, o teste acima leria as linhas erradas."""
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "target: dev" in texto


def _servico(texto: str, nome: str) -> str:
    linhas = texto.splitlines()
    inicio = linhas.index(f"  {nome}:")
    fim = next((i for i in range(inicio + 1, len(linhas))
                if linhas[i][:1] not in (" ", "") or
                (linhas[i].startswith("  ") and linhas[i][2:3] not in (" ", ""))), len(linhas))
    return "\n".join(linhas[inicio:fim])


def test_o_compose_sobe_de_novo_quem_o_botao_para():
    """Os dois reinicios sao um processo que SAI e o Docker que o sobe de
    novo: o backend (sinal ao processo 1) e o painel (o Vite). Sem a politica,
    o botao DESLIGARIA os dois. E o `--reload` e o que `subiu_pelo_compose`
    procura para saber que esta neste compose."""
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    for nome in ("backend", "frontend"):
        assert "restart: unless-stopped" in _servico(texto, nome), nome
    assert "--reload" in _servico(texto, "backend")
    assert "--reload" not in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


def test_a_marca_do_painel_e_a_que_o_vite_vigia_e_nao_e_versionada():
    vite = (RAIZ / "dashboard" / "vite.config.js").read_text(encoding="utf-8")
    assert f"'./{am.MARCA_DO_PAINEL.name}'" in vite
    # No Docker o painel SAI: o `server.restart()` do Vite 4, medido, morre se
    # a troca cair na pre-otimizacao das dependencias.
    assert "process.exit(0)" in vite and "/.dockerenv" in vite
    r = subprocess.run(["git", "-C", str(RAIZ), "check-ignore", "-q",
                        am.MARCA_DO_PAINEL.as_posix()])
    assert r.returncode == 0


# --- quem pode reiniciar -------------------------------------------------------------------

@pytest.mark.parametrize("cmdline, pode", [
    # O docker-compose.yml: o shebang poe o python na frente do script.
    (b"/opt/venv/bin/python\0/opt/venv/bin/uvicorn\0app:app\0--host\0000.0.0.0\0"
     b"--port\08000\0--reload\0--reload-exclude\0output/*\0", True),
    # O CMD do Dockerfile (producao), sem --reload: nao e o compose deste repositorio.
    (b"/opt/venv/bin/python\0/opt/venv/bin/uvicorn\0app:app\0--proxy-headers\0", False),
    (b"/bin/sh\0-c\0uvicorn app:app --reload\0", False),
])
def test_so_reinicia_o_uvicorn_do_compose(tmp_path, cmdline, pode):
    arquivo = tmp_path / "cmdline"
    arquivo.write_bytes(cmdline)
    assert am.subiu_pelo_compose(arquivo) is pode
    assert am.subiu_pelo_compose(tmp_path / "nao-existe") is False


def test_o_pedido_ao_ajudante(tmp_path):
    caminho = tmp_path / "dados" / ".atualizar-agora"
    am.pedir_ao_ajudante(str(caminho))
    assert caminho.read_text().strip().isdigit()


# --- o endpoint ---------------------------------------------------------------------------

import app as app_module  # noqa: E402


def _post(corpo="{}", tipo="application/json", depois_s=0.0):
    async def _run():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            cabecalhos = {"Content-Type": tipo} if tipo else {}
            r = await c.post("/api/motor/atualizar", content=corpo, headers=cabecalhos)
            if depois_s:
                await asyncio.sleep(depois_s)
            return r
    return asyncio.run(_run())


@pytest.fixture
def motor(monkeypatch):
    """Um motor do Docker de mentira, que nunca manda sinal a ninguem."""
    sinais = []
    monkeypatch.setattr(app_module, "_MOTOR", {"versao": "600", "origem": "docker"})
    monkeypatch.setattr(app_module, "_MOTOR_COMMIT", "a" * 40)
    monkeypatch.setattr(app_module, "_reinicio_pedido", False)
    monkeypatch.setattr(app_module, "_sinal_ao_processo_1", lambda: sinais.append(1))
    monkeypatch.setattr(am, "subiu_pelo_compose", lambda: True)
    monkeypatch.setattr(app_module, "_jobs_ativos", lambda: 0)
    return sinais


@pytest.mark.parametrize("tipo", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_so_aceita_json(motor, monkeypatch, tipo):
    """Sem tipo e o que um `fetch` `no-cors` de qualquer site consegue mandar,
    sem preflight -- e o FastAPI o leria como JSON."""
    chamado = []
    monkeypatch.setattr(am, "atualizar_docker", lambda *a: chamado.append(a))
    assert _post(tipo=tipo).status_code == 415
    assert chamado == [] and motor == []


def test_no_docker_atualiza_e_reinicia(motor, monkeypatch):
    recebido = []

    def atualizar(raiz, subiu_em):
        recebido.append((raiz, subiu_em))
        return {"situacao": "atualizou", "de": "600", "para": "610", "painel": True}
    monkeypatch.setattr(am, "atualizar_docker", atualizar)
    r = _post(depois_s=1.3)
    assert r.status_code == 202 and r.json()["para"] == "610"
    assert recebido == [(app_module.versao_do_motor.RAIZ, "a" * 40)]
    assert motor == [1], "um segundo depois, o sinal ao processo 1"
    # Outro clique durante o reinicio nao mexe no git de novo.
    assert _post().json() == {"situacao": "reiniciando"}
    assert len(recebido) == 1


@pytest.mark.parametrize("resultado, status", [
    ({"situacao": "atualizado"}, 200),
    ({"situacao": "precisa_do_atalho", "reconstruir": True,
      "arquivos": ["requirements.txt"], "total": 1}, 409),
    ({"situacao": "recusado", "causa": "divergiu", "motivo": "x"}, 409),
])
def test_no_docker_sem_reinicio_quando_nao_atualizou(motor, monkeypatch, resultado, status):
    monkeypatch.setattr(am, "atualizar_docker", lambda *a: resultado)
    r = _post(depois_s=1.3)
    assert r.status_code == status
    corpo = r.json()
    assert (corpo if status == 200 else corpo["detail"]) == resultado
    assert motor == [] and app_module._reinicio_pedido is False


def test_com_video_na_fila_nao_atualiza(motor, monkeypatch):
    monkeypatch.setattr(app_module, "_jobs_ativos", lambda: 1)
    monkeypatch.setattr(am, "atualizar_docker", lambda *a: pytest.fail("mexeu no git"))
    r = _post()
    assert r.status_code == 409 and r.json()["detail"]["causa"] == "jobs"


def test_fora_do_compose_nao_atualiza(motor, monkeypatch):
    monkeypatch.setattr(am, "subiu_pelo_compose", lambda: False)
    monkeypatch.setattr(am, "atualizar_docker", lambda *a: pytest.fail("mexeu no git"))
    r = _post()
    assert r.status_code == 409 and r.json()["detail"]["causa"] == "fora_do_compose"


def test_no_ajudante_so_deixa_o_pedido(motor, monkeypatch, tmp_path):
    caminho = tmp_path / "dados" / ".atualizar-agora"
    monkeypatch.setattr(app_module, "_MOTOR", {"versao": "540", "origem": "ajudante"})
    monkeypatch.setenv("CORTES_PEDIDO_DE_ATUALIZACAO", str(caminho))
    monkeypatch.setattr(am, "atualizar_docker", lambda *a: pytest.fail("o git e do Docker"))
    r = _post(depois_s=1.3)
    assert r.status_code == 202 and r.json() == {"situacao": "pedido"}
    assert caminho.exists() and motor == []

    monkeypatch.delenv("CORTES_PEDIDO_DE_ATUALIZACAO")
    assert _post().json()["detail"]["causa"] == "sem_bandeja"


def test_rodando_do_codigo_nao_atualiza(motor, monkeypatch):
    monkeypatch.setattr(app_module, "_MOTOR", {"versao": "600", "origem": "codigo"})
    assert _post().json()["detail"]["causa"] == "codigo"


def test_o_reinicio_pedido_nao_espera_o_proxy(monkeypatch):
    """Os 20 s de `PROXY_DRAIN_SECONDS` sao do deploy em nuvem. No reinicio
    que o botao pede, so ha a pessoa esperando o painel voltar."""
    pedidos = []

    async def drenar(_anterior, timeout=None, proxy_grace=None, hard_exit_after=None):
        pedidos.append(proxy_grace)

    monkeypatch.setattr(app_module, "_drain_then_exit", drenar)
    monkeypatch.setattr(app_module, "_begin_drain", lambda motivo: None)
    monkeypatch.setattr(app_module, "_stopping", False)

    async def _run(reinicio):
        monkeypatch.setattr(app_module, "_reinicio_pedido", reinicio)
        loop = asyncio.get_running_loop()
        capturado = {}
        loop.add_signal_handler = lambda sinal, fn: capturado.setdefault("fn", fn)
        app_module._install_drain_signal_handler()
        capturado["fn"]()
        await asyncio.sleep(0)

    asyncio.run(_run(True))
    asyncio.run(_run(False))
    assert pedidos == [0, None]
