"""Configuracoes -> Versoes: o numero do site e o navegador (25-set-2026).

O cartao mostra tres versoes, e duas nascem no navegador ou no build:

- a do SITE, gravada no build por `dashboard/versao-do-site.js`. E a contagem
  de commits, a mesma regra do motor (`versao_do_motor.py`) -- e, como la, so
  vale com o historico inteiro: num clone raso o `git rev-list --count`
  devolve a PROFUNDIDADE ("1" no lugar de "546"), sem erro nenhum. O build do
  Cloudflare pode clonar raso, e ali (`WORKERS_CI`) o script traz o historico.
- a do NAVEGADOR, por `dashboard/src/lib/navegador.js`, onde a ordem dos
  testes importa: o Edge e o Opera tambem escrevem "Chrome/" no userAgent.

Os dois sao JavaScript, entao rodam no `node` de verdade; sem node, pula.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "dashboard" / "versao-do-site.js"
NAVEGADOR = RAIZ / "dashboard" / "src" / "lib" / "navegador.js"

NODE = shutil.which("node")
GIT = shutil.which("git")
precisa_node = pytest.mark.skipif(not NODE, reason="sem node nesta maquina")
precisa_git = pytest.mark.skipif(not GIT, reason="sem git nesta maquina")


def _git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.name=Teste", "-c", "user.email=teste@example.com",
         "-c", "commit.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _versao(pasta, **extra):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("WORKERS_CI") and k != "CI"}
    # Uma pasta de teste dentro de outro repositorio acharia o repositorio de
    # fora; o teto impede o git de subir alem da pasta temporaria.
    env["GIT_CEILING_DIRECTORIES"] = str(Path(pasta).parent)
    env.update(extra)
    saida = subprocess.run(
        [NODE, str(SCRIPT), str(pasta)], env=env, check=True,
        capture_output=True, encoding="utf-8", timeout=120,
    ).stdout
    return json.loads(saida)


@pytest.fixture
def repositorio(tmp_path):
    origem = tmp_path / "origem"
    origem.mkdir()
    _git("init", "-q", cwd=origem)
    for i in range(3):
        (origem / "arquivo.txt").write_text(f"volta {i}\n", encoding="utf-8")
        _git("add", "arquivo.txt", cwd=origem)
        _git("commit", "-q", "-m", f"commit {i}", cwd=origem)
    return origem


@precisa_node
@precisa_git
def test_com_o_historico_inteiro_a_versao_e_a_contagem_de_commits(repositorio):
    info = _versao(repositorio)
    assert info["versao"] == "3"
    cabeca = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=repositorio,
                            capture_output=True, text=True, check=True).stdout.strip()
    assert info["commit"] == cabeca
    assert info["publicadoEm"].endswith("Z")


@precisa_node
@precisa_git
def test_clone_raso_fora_do_cloudflare_fica_sem_numero(repositorio, tmp_path):
    """O defeito que o script existe para evitar: "1" no lugar de "3"."""
    raso = tmp_path / "raso"
    _git("clone", "-q", "--depth", "1", repositorio.as_uri(), str(raso), cwd=tmp_path)
    contagem = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=raso,
                              capture_output=True, text=True, check=True).stdout.strip()
    assert contagem == "1", "o clone de teste deveria ser raso"

    info = _versao(raso)
    assert info["versao"] is None
    assert info["commit"], "o commit sai mesmo sem o historico"


@precisa_node
@precisa_git
def test_no_build_do_cloudflare_o_historico_e_buscado(repositorio, tmp_path):
    raso = tmp_path / "raso"
    _git("clone", "-q", "--depth", "1", repositorio.as_uri(), str(raso), cwd=tmp_path)
    info = _versao(raso, WORKERS_CI="1")
    assert info["versao"] == "3"


@precisa_node
def test_sem_git_o_commit_vem_do_cloudflare(tmp_path):
    pasta = tmp_path / "sem-git"
    pasta.mkdir()
    info = _versao(pasta, WORKERS_CI_COMMIT_SHA="abcdef0123456789")
    assert info == {**info, "versao": None, "commit": "abcdef0"}


@precisa_node
def test_sem_git_e_sem_cloudflare_nao_inventa(tmp_path):
    pasta = tmp_path / "sem-git"
    pasta.mkdir()
    info = _versao(pasta)
    assert info["versao"] is None and info["commit"] is None


def test_o_nome_gravado_no_build_e_o_que_o_cartao_le():
    """Um nome trocado de um lado so faria o cartao dizer "nao informado",
    sem erro no build nem no navegador."""
    vite = (RAIZ / "dashboard" / "vite.config.js").read_text(encoding="utf-8")
    cartao = (RAIZ / "dashboard" / "src" / "components" / "Versoes.jsx").read_text(encoding="utf-8")
    assert "__VERSAO_DO_SITE__: JSON.stringify(versaoDoSite())" in vite
    assert "typeof __VERSAO_DO_SITE__ !== 'undefined'" in cartao
    app = (RAIZ / "dashboard" / "src" / "App.jsx").read_text(encoding="utf-8")
    assert "<Versoes />" in app


CHROME = [
    {"brand": "Chromium", "version": "140.0.7339.128"},
    {"brand": "Not=A?Brand", "version": "24.0.0.0"},
    {"brand": "Google Chrome", "version": "140.0.7339.128"},
]


def _navegador(expressao):
    codigo = (
        f"import * as n from {json.dumps(NAVEGADOR.as_uri())};\n"
        f"const r = await ({expressao});\n"
        "console.log(JSON.stringify(r));\n"
    )
    # O node escreve UTF-8 em cano; sem isto, um Windows fora do modo UTF-8
    # do Python leria "Â·" no lugar de "·".
    saida = subprocess.run([NODE, "--input-type=module", "-e", codigo],
                           capture_output=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(saida)


@precisa_node
@pytest.mark.parametrize("versao_da_plataforma, esperado", [
    ("10.0.0", "Google Chrome 140.0.7339.128 · Windows 10"),
    ("15.0.0", "Google Chrome 140.0.7339.128 · Windows 11"),
    (None, "Google Chrome 140.0.7339.128 · Windows"),
])
def test_a_marca_que_interessa_e_o_windows_certo(versao_da_plataforma, esperado):
    r = _navegador(f"n.pelasMarcas({json.dumps(CHROME)}, 'Windows', {json.dumps(versao_da_plataforma)})")
    assert r == esperado


@precisa_node
@pytest.mark.parametrize("ua, esperado", [
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.3485.54", "Microsoft Edge 140.0.3485.54 · Windows"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
     "Chrome/140.0.0.0 Safari/537.36 OPR/124.0.0.0", "Opera 124.0.0.0 · Windows"),
    ("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
     "Firefox 143.0 · Windows"),
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1", "Safari 26.0 · iOS"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
     "(KHTML, like Gecko) Version/26.0 Safari/605.1.15", "Safari 26.0 · macOS"),
    ("", "não identificado"),
])
def test_sem_marcas_vale_o_user_agent(ua, esperado):
    assert _navegador(f"n.pelaIdentificacao({json.dumps(ua)})") == esperado


@precisa_node
def test_sem_a_pergunta_de_alta_entropia_fica_com_a_versao_curta():
    curtas = [{**m, "version": m["version"].split(".")[0]} for m in CHROME]
    nav = ("{ userAgentData: { brands: " + json.dumps(curtas) + ", platform: 'Windows', "
           "getHighEntropyValues: async () => { throw new Error('recusado'); } }, userAgent: '' }")
    assert _navegador(f"n.lerNavegador({nav})") == "Google Chrome 140 · Windows"
    assert _navegador("n.lerNavegador(null)") == "não identificado"
