"""Os atalhos nao podem tirar a placa de ninguem (22-set-2026).

Havia dois jeitos de subir -- `subir.bat` e `subir-gpu.bat` -- e so o segundo
levava o `docker-compose.gpu.yml`. O `atualizar.bat` e o `reconstruir.bat`
usavam o primeiro. Bastava atualizar uma vez: o `docker compose up -d` so com o
arquivo base RECRIA o backend, porque a configuracao do servico muda sem o
overlay (medido com o proprio `docker compose config --hash`: os dois hashes
diferem). Dali em diante o whisper rodava `small` em CPU, sem erro e sem aviso.
Um video de 10 min levou 5 min so para transcrever numa RTX 3060.

A regra que estes testes guardam: a decisao "tem placa?" mora num lugar so, o
`_modo-gpu.bat`, e todo atalho que sobe ou constroi passa por ele.

Le os `.bat` como TEXTO: o CI roda em Linux, sem cmd.exe. O que se consegue
garantir daqui e a forma -- quem chama quem, e em que ordem --, e sao
exatamente essas as coisas que quebraram.
"""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATALHOS = os.path.join(RAIZ, "atalhos")


def _bats() -> dict:
    saida = {}
    for nome in sorted(os.listdir(ATALHOS)):
        if nome.lower().endswith(".bat"):
            with open(os.path.join(ATALHOS, nome), encoding="utf-8",
                      newline="") as fh:
                saida[nome] = fh.read()
    return saida


def _linhas_de_codigo(texto: str) -> list:
    """As linhas que o cmd.exe executa: sem `REM` e sem as vazias."""
    return [l.strip() for l in texto.splitlines()
            if l.strip() and not l.strip().upper().startswith("REM")]


def _sobe(linha: str) -> bool:
    return bool(re.search(r"docker compose\b.*\bup\b", linha))


def _constroi(linha: str) -> bool:
    return bool(re.search(r"docker compose\b.*\bbuild\b", linha))


# --------------------------------------------------------------------------- #
# Um lugar so decide
# --------------------------------------------------------------------------- #

def test_so_o_modo_gpu_nomeia_o_overlay():
    """Quem escreve `-f docker-compose.gpu.yml` num atalho reabre o defeito: e
    uma segunda resposta para "tem placa?", e ela diverge da primeira no dia em
    que alguem mexer so numa."""
    for nome, texto in _bats().items():
        if nome == "_modo-gpu.bat":
            continue
        codigo = "\n".join(_linhas_de_codigo(texto))
        assert "docker-compose.gpu.yml" not in codigo, (
            f"{nome} escolhe os arquivos do compose por conta propria; quem "
            "decide e o _modo-gpu.bat")


def test_o_modo_gpu_pergunta_ao_windows_e_poe_os_dois_arquivos():
    texto = _bats()["_modo-gpu.bat"]
    codigo = "\n".join(_linhas_de_codigo(texto))
    assert "nvidia-smi" in codigo
    # O separador do COMPOSE_FILE no Windows ja e `;`, mas dizer explicitamente
    # tira a duvida de quem le -- e de quem rodar isto noutro shell.
    assert 'set "COMPOSE_PATH_SEPARATOR=;"' in codigo
    m = re.search(r'set "COMPOSE_FILE=([^"]*docker-compose\.gpu\.yml[^"]*)"', codigo)
    assert m, "o modo GPU nao poe o overlay no COMPOSE_FILE"
    arquivos = m.group(1).split(";")
    assert [os.path.basename(a.replace("\\", "/")) for a in arquivos] == [
        "docker-compose.yml", "docker-compose.gpu.yml"]


def test_so_o_subir_faz_up():
    """Todo `up` passa pelo `_subir.bat`, que e onde mora a queda para CPU
    quando o Docker recusa a placa. Um `up` solto noutro atalho nao teria
    essa rede -- e subiria no modo que estivesse no ambiente, qualquer que
    fosse."""
    for nome, texto in _bats().items():
        if nome == "_subir.bat":
            continue
        for linha in _linhas_de_codigo(texto):
            assert not _sobe(linha), f"{nome} faz `up` por fora do _subir.bat: {linha}"


def test_todo_atalho_que_sobe_ou_constroi_pergunta_a_placa_antes():
    """A ordem importa: o `_modo-gpu.bat` poe o COMPOSE_FILE no ambiente, e
    so o que vem DEPOIS dele na mesma janela enxerga a variavel."""
    for nome, texto in _bats().items():
        if nome in ("_subir.bat", "_modo-gpu.bat"):
            continue
        linhas = _linhas_de_codigo(texto)
        ja_perguntou = False
        for linha in linhas:
            if "_modo-gpu.bat" in linha:
                ja_perguntou = True
            if "_subir.bat" in linha or _constroi(linha):
                assert ja_perguntou, (
                    f"{nome} sobe ou constroi antes de perguntar a placa: {linha}")


def test_as_variantes_gpu_sao_apelidos():
    """`subir-gpu.bat` e `reconstruir-gpu.bat` ficaram pelo costume. Se um
    deles voltar a ter comando proprio, voltam a existir dois caminhos -- e
    foi isso que tirava a placa."""
    bats = _bats()
    for apelido, alvo in (("subir-gpu.bat", "subir.bat"),
                          ("reconstruir-gpu.bat", "reconstruir.bat")):
        codigo = _linhas_de_codigo(bats[apelido])
        assert codigo == ["@echo off", f'call "%~dp0{alvo}"'], (
            f"{apelido} deixou de ser so um apelido de {alvo}")


def test_o_overlay_constroi_com_as_libs_de_cuda():
    """Sem isto, o `reconstruir.bat` -- que o `atualizar.bat` manda rodar quando
    uma dependencia muda -- construiria a imagem sem CUDA, e a placa sumiria
    de vez: so os 40 minutos do antigo reconstruir-gpu a devolviam."""
    with open(os.path.join(RAIZ, "docker-compose.gpu.yml"), encoding="utf-8") as fh:
        linhas = [l for l in fh.read().splitlines() if not l.strip().startswith("#")]
    texto = "\n".join(linhas)
    assert re.search(r"^\s+build:\s*$", texto, re.M)
    assert re.search(r"^\s+args:\s*$", texto, re.M)
    assert re.search(r'^\s+GPU:\s*"1"\s*$', texto, re.M)


# --------------------------------------------------------------------------- #
# O atualizar.bat se reescreve enquanto roda
# --------------------------------------------------------------------------- #

# Byte a byte, do comeco ate o fim da linha do `git pull`. NAO atualize esta
# constante para fazer o teste passar sem ler o docstring abaixo.
PREFIXO_DO_ATUALIZAR = (
    '@echo off\n'
    'REM Puxa as mudancas e sobe. Abre o Docker Desktop sozinho se preciso.\n'
    'REM\n'
    'REM Sem rebuild de proposito: `.py` e `.jsx` valem sozinhos. Se o `git pull`\n'
    'REM tiver trazido mudanca em requirements.txt, package.json ou Dockerfile, o\n'
    'REM script avisa e voce roda reconstruir.bat.\n'
    'cd /d "%~dp0.."\n'
    '\n'
    "for /f %%i in ('git rev-parse HEAD') do set ANTES=%%i\n"
    'git pull\n'
)


def test_o_prefixo_do_atualizar_esta_congelado():
    """O `git pull` troca o proprio `atualizar.bat` enquanto ele roda, e o
    cmd.exe nao rele o arquivo do comeco: continua da mesma POSICAO EM BYTES,
    agora dentro do arquivo novo. Com tudo ate o `git pull` identico, essa
    posicao e o comeco da linha seguinte. Qualquer mudanca ali faria a
    primeira atualizacao depois dela executar um pedaco de linha qualquer --
    num arquivo que mexe no Docker.

    Se for mesmo preciso mudar esse trecho, a mudanca tem de vir em duas
    etapas: primeiro uma versao que, depois do `git pull`, chama outro arquivo
    e termina; so na seguinte o cabecalho muda.
    """
    texto = _bats()["atualizar.bat"].replace("\r\n", "\n")
    assert texto.startswith(PREFIXO_DO_ATUALIZAR), (
        "o trecho do atualizar.bat ate o `git pull` mudou -- leia o docstring")
    seguinte = texto[len(PREFIXO_DO_ATUALIZAR):].split("\n", 1)[0]
    assert seguinte.startswith("for /f %%i in ('git rev-parse HEAD') do set DEPOIS")


def test_os_dois_caminhos_do_atualizar_perguntam_a_placa():
    """O "nada novo para baixar" tambem sobe -- e era o caminho que o autor
    mais usava. Os dois ramos chamam o `_modo-gpu.bat` cada um."""
    codigo = _linhas_de_codigo(_bats()["atualizar.bat"])
    assert sum("_modo-gpu.bat" in l for l in codigo) == 2
    assert sum("_subir.bat" in l for l in codigo) == 2


# --------------------------------------------------------------------------- #
# Armadilhas do cmd.exe que o CI nao ve
# --------------------------------------------------------------------------- #

def test_nenhum_rem_tem_porcento():
    """O cmd.exe expande `%` ANTES de reconhecer o `REM`: um `%~` num
    comentario derruba o arquivo inteiro com "the following usage of the path
    operator in batch-parameter substitution is invalid"."""
    for nome, texto in _bats().items():
        for linha in texto.splitlines():
            if linha.strip().upper().startswith("REM"):
                assert "%" not in linha, f"{nome}: % num REM: {linha}"


def test_nenhum_echo_dentro_de_bloco_tem_parenteses():
    """Dentro de `if ... (` um `)` num `echo` fecha o bloco no meio: o resto
    vira comando solto. O primeiro sintoma e a janela piscar e fechar."""
    for nome, texto in _bats().items():
        profundidade = 0
        for linha in texto.splitlines():
            crua = linha.strip()
            if crua.upper().startswith("REM"):
                continue
            if profundidade and crua.lower().startswith("echo"):
                resto = crua[4:]
                assert "(" not in resto and ")" not in resto, (
                    f"{nome}: parentese num echo dentro de bloco: {crua}")
            if crua.endswith("(") and not crua.lower().startswith("echo"):
                profundidade += 1
            elif crua == ")":
                profundidade -= 1
        assert profundidade == 0, f"{nome}: blocos `(` / `)` desbalanceados"


def test_quem_chama_os_ajudantes_garantiu_o_docker_antes():
    """Os `_*.bat` confiam em quem os chama: o `_subir.bat` roda `docker
    compose` sem perguntar se o motor esta de pe. A garantia, entao, e de quem
    chama -- senao o erro do cano (`npipe:////...`) volta a chegar na tela."""
    for nome, texto in _bats().items():
        if nome.startswith("_"):
            continue
        garantiu = False
        for linha in _linhas_de_codigo(texto):
            if "_garantir-docker.bat" in linha:
                garantiu = True
            if "_subir.bat" in linha:
                assert garantiu, f"{nome} chama o _subir.bat sem garantir o Docker"
