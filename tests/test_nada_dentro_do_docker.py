"""Nada que o processamento grava fica dentro do Docker (22-set-2026).

O autor pediu, e repetiu: "os videos tem que ficar no computador da pessoa, em
momento nenhum tem que passar pelo Docker". Os videos ja ficavam em `output/`,
que e a pasta do repositorio montada no container. O que ainda caia no disco do
Docker -- no Windows, um .vhdx que cresce e nao encolhe sozinho -- eram os
temporarios em /tmp e o log do container, que nao tinha teto.

Estes testes impedem que voltem, sem precisar de Docker para rodar.
"""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

_CRIADORES_DE_TEMPORARIO = {"mkdtemp", "mkstemp", "NamedTemporaryFile",
                            "TemporaryDirectory", "SpooledTemporaryFile",
                            "TemporaryFile"}


def _modulos_do_backend():
    for caminho in sorted(RAIZ.rglob("*.py")):
        partes = caminho.relative_to(RAIZ).parts
        if partes[0] in ("tests", "dashboard", "node_modules", "render-service") \
                or any(p.startswith(".") for p in partes):
            continue
        yield caminho


def test_nenhum_temporario_sem_pasta_explicita():
    """`tempfile` sem `dir=` escreve no /tmp do container. Os dois que havia
    (render e ASR) passaram para a pasta do projeto; um novo precisa dizer onde
    grava, e o lugar certo e ao lado dos arquivos do job."""
    sem_pasta = []
    for caminho in _modulos_do_backend():
        try:
            arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Call):
                continue
            nome = getattr(no.func, "attr", None) or getattr(no.func, "id", None)
            if nome in _CRIADORES_DE_TEMPORARIO and \
                    not any(k.arg == "dir" for k in no.keywords):
                sem_pasta.append(f"{caminho.relative_to(RAIZ)}:{no.lineno}")
    assert sem_pasta == [], (
        "temporario sem dir= (cai no /tmp do container, dentro do disco do "
        f"Docker): {sem_pasta}")


def _servicos_do_compose(texto):
    dentro = False
    for linha in texto.splitlines():
        if linha.startswith("services:"):
            dentro = True
            continue
        if dentro and re.match(r"^\S", linha):
            dentro = False
        if dentro:
            m = re.match(r"^  ([a-z][a-z0-9_-]*):\s*$", linha)
            if m:
                yield m.group(1)


def test_todo_container_tem_teto_de_log():
    """O backend repete no log do container cada linha de todo job, e esse log
    mora no disco do Docker. Sem teto, so crescia."""
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    servicos = list(_servicos_do_compose(texto))
    assert {"backend", "frontend"} <= set(servicos)
    assert texto.count("logging: *log-com-teto") == len(servicos)
    assert 'max-size: "10m"' in texto and 'max-file: "3"' in texto


def test_o_atalho_abre_a_pasta_dos_cortes():
    bat = (RAIZ / "atalhos" / "abrir-pasta-dos-cortes.bat").read_text(encoding="utf-8")
    assert 'start "" "%~dp0..\\output"' in bat
