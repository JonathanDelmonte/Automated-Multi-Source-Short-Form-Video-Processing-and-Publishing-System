"""A versao do motor no /api/config (Fase 6.2).

O site e publicado a cada envio; o motor do Docker so muda com o
atualizar.bat. O site so pode avisar "o motor ficou para tras" se o motor
disser a versao dele -- e so pode dizer a verdade: sem como saber, `None`.
"""
import asyncio
from types import SimpleNamespace

import httpx

import versao_do_motor as vm


def _git(saida="521", codigo=0, erro=None):
    chamadas = []

    def executar(cmd, **kw):
        chamadas.append(cmd)
        if erro:
            raise erro
        return SimpleNamespace(returncode=codigo, stdout=saida + "\n")
    executar.chamadas = chamadas
    return executar


def test_o_ajudante_traz_a_versao_pronta(tmp_path):
    (tmp_path / "VERSAO").write_text("521\n")
    (tmp_path / ".git").mkdir()
    git = _git()
    assert vm.descobrir(tmp_path, git) == {"versao": "521", "origem": "ajudante"}
    assert git.chamadas == [], "com o arquivo, nao pergunta ao git"


def test_o_docker_conta_os_commits(tmp_path):
    (tmp_path / ".git").mkdir()
    git = _git("530")
    assert vm.descobrir(tmp_path, git, no_docker=True) == {"versao": "530", "origem": "docker"}
    # A pasta montada no Docker e de outro dono: sem isto o git nao le.
    assert "safe.directory=*" in git.chamadas[0]
    assert vm.descobrir(tmp_path, git, no_docker=False)["origem"] == "codigo"


def test_sem_como_saber_a_versao_e_none(tmp_path):
    assert vm.descobrir(tmp_path, _git(), no_docker=True)["versao"] is None  # sem .git
    (tmp_path / ".git").mkdir()
    assert vm.descobrir(tmp_path, _git(codigo=128), no_docker=True)["versao"] is None
    assert vm.descobrir(tmp_path, _git(erro=FileNotFoundError()), no_docker=True)["versao"] is None
    assert vm.descobrir(tmp_path, _git("fatal: x"), no_docker=True)["versao"] is None
    # Clone raso conta so o que baixou: um checkout do CI diria "1".
    (tmp_path / ".git" / "shallow").write_text("abc\n")
    assert vm.descobrir(tmp_path, _git("1"), no_docker=True)["versao"] is None


def test_a_config_diz_a_versao_do_motor():
    import app as app_module

    async def _do():
        transporte = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
            return await c.get("/api/config")
    motor = asyncio.run(_do()).json()["motor"]
    assert set(motor) == {"versao", "origem"}
    assert motor["origem"] in ("ajudante", "docker", "codigo")
