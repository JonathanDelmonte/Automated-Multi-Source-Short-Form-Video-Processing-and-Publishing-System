"""As pecas do ajudante que dao para conferir daqui, sem Windows (Fase 6.2).

O teste de verdade e o `windows.yml`: instala o motor inteiro no Windows e
processa um video. Estes pegam antes, e no CI de sempre, o que faria aquela
volta de 15 minutos falhar por bobagem -- ou, pior, passar medindo outra coisa.
"""
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
AJUDANTE = RAIZ / "ajudante"
sys.path.insert(0, str(AJUDANTE))

import llm_falso  # noqa: E402


def _pinos(caminho):
    pinos = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip()
        if not linha or linha.startswith("-"):
            continue
        nome = re.split(r"[<>=!~\[; ]", linha, 1)[0].lower()
        pinos[nome] = linha
    return pinos


def test_as_versoes_do_windows_sao_as_do_docker():
    """Duas listas divergem no dia em que uma delas muda. O ajudante rodando
    outra versao de faster-whisper que o Docker seria um bug que so aparece
    no computador de um amigo."""
    docker = _pinos(RAIZ / "requirements.txt")
    windows = _pinos(AJUDANTE / "requirements-windows.txt")
    fora = {"ultralytics", "torchvision"}
    so_do_windows = {"pystray"}  # o icone do ajudante
    assert not (fora & set(windows)), "o YOLO (AGPL) nao vai para o computador de ninguem"
    faltando = set(docker) - fora - set(windows)
    assert not faltando, f"o requirements.txt tem e o do Windows nao: {sorted(faltando)}"
    for nome, linha in windows.items():
        if nome == "yt-dlp" or nome in so_do_windows:
            continue  # yt-dlp: sem pino nos dois; no Windows com o [default]
        assert docker.get(nome) == linha, f"{nome}: Docker {docker.get(nome)!r} x Windows {linha!r}"


# --- o LLM falso responde no formato que o pipeline valida -------------------

gemini_worker = pytest.importorskip("gemini_worker")
JANELAS = [{"id": "window_001", "start": 0.0, "end": 38.4, "text": "hello there"},
           {"id": "window_002", "start": 30.0, "end": 41.0, "text": "bye"}]


def _prompt(modelo, **extra):
    return modelo.format(video_duration=41, language="en",
                         windows_json=json.dumps(JANELAS, ensure_ascii=False), **extra)


def test_as_janelas_saem_do_prompt_de_verdade():
    prompt = _prompt(gemini_worker.SCORE_PROMPT_TEMPLATE)
    assert llm_falso.janelas_do_prompt(prompt) == [
        ("window_001", 0.0, 38.4), ("window_002", 30.0, 41.0)]


def _responde(prompt, schema, com_formato=True):
    corpo = {"messages": [{"role": "user", "content": prompt}]}
    if com_formato:
        corpo["response_format"] = {"type": "json_schema",
                                    "json_schema": {"name": schema.__name__.lower()}}
    conteudo = llm_falso.responder(corpo)["choices"][0]["message"]["content"]
    return schema.model_validate(json.loads(conteudo))


@pytest.mark.parametrize("com_formato", [True, False])
def test_nota_valida_no_schema(com_formato):
    r = _responde(_prompt(gemini_worker.SCORE_PROMPT_TEMPLATE),
                  gemini_worker.ScoreResponse, com_formato)
    assert [w.id for w in r.windows] == ["window_001", "window_002"]


@pytest.mark.parametrize("com_formato", [True, False])
def test_detalhe_valido_e_dentro_da_janela(com_formato):
    prompt = _prompt(gemini_worker.DETAIL_PROMPT_TEMPLATE, min_clips=1, max_clips=3,
                     min_secs=15, max_secs=60)
    r = _responde(prompt, gemini_worker.DetailResponse, com_formato)
    # A janela 2 tem 11 s: menos de 12 s de corte depois das folgas, fica de fora.
    assert len(r.shorts) == 1
    corte = r.shorts[0]
    assert corte.source_window_id == "window_001"
    assert 0.0 <= corte.start < corte.end <= 38.4
    assert 15 <= corte.end - corte.start <= 60


def test_o_texto_da_fala_cabe_nas_aspas_do_powershell():
    """A frase vai entre aspas simples no comando do SAPI: um apostrofo ali
    fecha a string e o sintetizador recebe metade -- ou nada."""
    fonte = (AJUDANTE / "ponta_a_ponta.py").read_text(encoding="utf-8")
    m = re.search(r"TEXTO = \((.*?)\n\)", fonte, re.S)
    texto = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    assert "'" not in texto
    assert len(texto.split()) >= 70, "fala curta demais para um corte de 15 s"


def test_o_windows_do_github_roda_o_video_de_ponta_a_ponta():
    fluxo = (RAIZ / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in fluxo
    assert "python ajudante/ponta_a_ponta.py" in fluxo
    assert "ajudante/requirements-windows.txt" in fluxo


# --- o que o instalador leva -------------------------------------------------

import empacotar  # noqa: E402


def test_o_pacote_leva_o_motor_e_deixa_o_resto():
    rastreados = [
        "app.py", "main.py", "sources/__init__.py", "fonts/Anton-Regular.ttf",
        "ajudante/ajudante.py", "assets/watermark.png", "alembic/env.py",
        "dashboard/src/App.jsx", "docs/DECISOES.md", "tests/test_x.py",
        ".github/workflows/ci.yml", "atalhos/subir.bat", "screenshots/a.png",
        "remotion/src/x.tsx", "render-service/server.js", "demo-openshorts.mp4",
        "churchil_queen_vertical.gif", "ajudante/instalador.iss",
        # o que so o Docker, o GitHub e quem le o repositorio usam
        "CLAUDE.md", "README.md", "design.md", "skills/openshorts/SKILL.md",
        "cli/openshorts_cli.py", "Dockerfile", "docker-compose.gpu.yml",
        ".env.example", ".gitignore", "requirements.txt", "server.json",
        # a licenca acompanha o codigo distribuido
        "LICENSE", "NOTICE", "alembic.ini",
    ]
    assert empacotar.arquivos_do_motor(rastreados) == sorted([
        "app.py", "main.py", "sources/__init__.py", "fonts/Anton-Regular.ttf",
        "ajudante/ajudante.py", "assets/watermark.png", "alembic/env.py",
        "LICENSE", "NOTICE", "alembic.ini",
    ])


def test_o_requirements_de_uma_subpasta_nao_e_o_da_raiz():
    """So a raiz perde `requirements.txt` (e o do Docker); o do ajudante mora
    numa subpasta e e o que o instalar.ps1 le."""
    assert empacotar.arquivos_do_motor([
        "requirements.txt", "ajudante/requirements-windows.txt",
    ]) == ["ajudante/requirements-windows.txt"]


def test_nenhum_codigo_python_do_motor_fica_de_fora():
    """A lista e de EXCLUSAO para que codigo novo entre sozinho; este teste
    pega o dia em que alguem exclui uma pasta que o motor importa."""
    import subprocess
    todos = subprocess.run(["git", "ls-files", "*.py"], cwd=RAIZ, capture_output=True,
                           text=True, check=True).stdout.split()
    # cli/ e o cliente de linha de comando, outro programa: nao e o motor.
    motor = [a for a in todos
             if not a.startswith(("tests/", "examples/", "ops/", "dashboard/", "cli/"))]
    fora = set(motor) - set(empacotar.arquivos_do_motor(motor))
    assert not fora, f"codigo do motor fora do pacote: {sorted(fora)}"


def test_a_assinatura_muda_com_as_dependencias(tmp_path):
    motor = tmp_path / "motor"
    (motor / "ajudante").mkdir(parents=True)
    (motor / "ajudante" / "requirements-windows.txt").write_text("torch==1\n")
    antes = empacotar.assinatura_das_dependencias(motor)
    (motor / "ajudante" / "requirements-windows.txt").write_text("torch==2\n")
    assert empacotar.assinatura_das_dependencias(motor) != antes


def test_o_instalador_nao_pede_administrador_e_guarda_os_projetos():
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss
    assert "DefaultDirName={localappdata}\\VirtuClips" in iss
    apagados = re.findall(r'Type: filesandordirs; Name: "\{app\}\\([^"]+)"', iss)
    assert "dados" not in apagados and {"versoes", "venv", "python", "bin"} <= set(apagados)
    # No /VERYSILENT uma caixa comum esperaria um clique para sempre.
    assert "SuppressibleMsgBox(" in iss and "  MsgBox(" not in iss


def test_o_python_vem_no_instalador_e_o_uv_nao_baixa_outro():
    """O erro 448 do PC do autor (24-set-2026): o `uv python install` cria um
    atalho de pasta (junction) por versao, e o Windows recusou atravessar o
    que um usuario comum criou. O Python agora vem no .exe, e o uv so o usa
    -- nunca baixa outro, que e o que criaria o atalho de novo."""
    ps1 = (AJUDANTE / "instalar.ps1").read_text(encoding="utf-8")
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert '"python", "install"' not in ps1
    assert '$env:UV_PYTHON_DOWNLOADS = "never"' in ps1
    assert 'Rodar $uv @("venv", $venv, "--python", $pythonBase' in ps1
    assert 'Source: "{#Pacote}\\python\\*"; DestDir: "{app}\\python"' in iss
    assert "requirements-windows-gpu.txt" in ps1 and "TemPlacaNvidia" in ps1
    # A atualizacao tambem instala com o uv: la tambem, nada de baixar Python.
    fonte = (AJUDANTE / "atualizacao.py").read_text(encoding="utf-8")
    assert 'UV_PYTHON_DOWNLOADS="never"' in fonte and "UV_PYTHON_INSTALL_DIR" not in fonte


def test_o_ci_compila_o_instalador_de_uma_pasta_curta():
    """O ISCC do Inno 6.7 nao abre caminho de mais de 260 caracteres, e o
    Python embutido, dentro da pasta do checkout do GitHub (~150 so ela),
    passa disso: "The system cannot find the path specified", no meio da
    compressao (24-set-2026). O pacote e montado em C:\\vc e o .iss o recebe
    por /DPacote."""
    fluxo = (RAIZ / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert "--pacote C:\\vc\\pacote" in fluxo and '"/DPacote=C:\\vc\\pacote"' in fluxo
    assert '#define Pacote "pacote"' in iss
    # Nenhum caminho do pacote escrito a mao, que escaparia da pasta curta.
    assert not re.search(r"pacote\\", iss.replace("{#Pacote}", "")), "caminho do pacote a mao"


def test_a_redirectionguard_do_inno_fica_desligada():
    """O Inno Setup 6.7 liga a RedirectionGuard por padrao, e ela chegou ao
    uv, neto do instalador. Ela protege instalador ADMINISTRADOR mexendo em
    pasta que qualquer um escreve; este roda como a pessoa, na pasta dela."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert re.search(r"^RedirectionGuard=no$", iss, re.M)
    # O registro da instalacao diz se ela chegou ao powershell: e a primeira
    # pergunta se o erro 448 voltar.
    ps1 = (AJUDANTE / "instalar.ps1").read_text(encoding="utf-8")
    assert "GetProcessMitigationPolicy" in ps1 and "ProtecaoDeRedirecionamento" in ps1


def test_a_instalacao_do_tempo_do_cortes_vem_para_a_pasta_nova():
    """Mesmo AppId (uma entrada so em Aplicativos), pasta nova: sem
    `UsePreviousAppDir=no` o Inno instalaria de novo na pasta antiga. E os
    projetos da antiga vem junto, antes de o resto dela ser apagado."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert "AppId={{6F3B2C1E-8D4A-4E7B-9C21-5A0D3E9F7B64}" in iss
    assert re.search(r"^UsePreviousAppDir=no$", iss, re.M)
    preparar = iss.split("function PrepareToInstall", 1)[1].split("\nend;", 1)[0]
    assert "MigrarDoCortes" in preparar
    migrar = iss.split("procedure MigrarDoCortes", 1)[1].split("\nend;", 1)[0]
    assert migrar.index("PararAjudante(Antiga)") < migrar.index("RenameFile(Antiga + '\\dados'")
    assert migrar.index("RenameFile(") < migrar.index("DelTree(")
    assert "DelTree(Antiga + '\\dados'" not in migrar, "os projetos nunca sao apagados"


def test_o_inicio_com_o_windows_e_o_mesmo_valor_que_o_ajudante_liga():
    """O .iss grava o valor do registro, e o menu do ajudante o liga e
    desliga. Com nomes diferentes, desligar pelo menu deixaria o do
    instalador -- e o ajudante continuaria subindo no login."""
    import ajudante
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    registro = iss.split("[Registry]", 1)[1].split("\n[", 1)[0]
    assert f'ValueName: "{ajudante.VALOR_NO_INICIO}"' in registro


def test_o_ci_instala_como_usuario_comum_com_a_protecao_ligada():
    """O runner do GitHub e administrador, e atalho criado por administrador e
    confiavel: foi assim que o erro 448 passou pelo CI. A volta que prova o
    conserto instala como usuario comum, com a RedirectionGuard forcada."""
    fluxo = (RAIZ / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    passo = fluxo.split("- name: Um usuario comum instala", 1)[1].split("- name:", 1)[0]
    assert "net user amigo" in passo and "-Credential $cred" in passo
    assert '"/REDIRECTIONGUARD"' in passo and "--verificar" in passo


def test_motor_quebrado_nao_termina_como_instalado():
    """Sem o codigo de saida proprio, o Inno Setup devolveria 0 com o motor
    quebrado: os arquivos foram copiados, e e so isso que ele confere."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert "function GetCustomSetupExitCode" in iss
    assert "MotorFalhou := True" in iss


def test_sem_janela_o_script_nao_espera_um_enter():
    """No /VERYSILENT ninguem aperta Enter: a pausa do erro travaria o CI (e a
    instalacao por linha de comando) ate o prazo acabar."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    ps1 = (AJUDANTE / "instalar.ps1").read_text(encoding="utf-8")
    assert "if WizardSilent then" in iss and "-SemPausa" in iss
    assert "[switch]$SemPausa" in ps1
    assert re.search(r"if \(-not \$SoDependencias -and -not \$SemPausa\)\s*\{\s*Read-Host", ps1)


def test_o_progresso_do_uv_no_stderr_nao_derruba_o_script():
    """No Windows PowerShell 5.1, com `Stop`, a primeira linha que um .exe
    escreve no stderr redirecionado vira erro -- e o uv escreve o progresso
    todo la. O `Rodar` troca para `Continue` so enquanto o programa roda."""
    ps1 = (AJUDANTE / "instalar.ps1").read_text(encoding="utf-8")
    rodar = ps1.split("function Rodar", 1)[1].split("\n}\n", 1)[0]
    assert '$ErrorActionPreference = "Continue"' in rodar
    assert "2>&1" in rodar and "Write-Host" in rodar
    assert "$LASTEXITCODE" in rodar


def test_nenhuma_linha_do_iss_comeca_com_cerquilha_fora_das_diretivas():
    """O pre-processador do Inno le como diretiva toda linha que COMECA com
    `#`, e no Pascal do [Code] `#13#10` e a quebra de linha. Uma continuacao
    comecando por ela derrubou a compilacao no CI (24-set-2026)."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    diretivas = ("#ifndef", "#ifdef", "#if ", "#else", "#endif", "#define", "#include")
    ruins = [n for n, linha in enumerate(iss.splitlines(), 1)
             if linha.lstrip().startswith("#") and not linha.lstrip().startswith(diretivas)]
    assert not ruins, f"linhas {ruins} comecam com # e nao sao diretiva"


def test_atalhos_e_inicio_chamam_o_iniciar_que_a_atualizacao_nao_troca():
    """O codigo muda de pasta a cada versao; o que o Windows guarda (atalho,
    menu Iniciar, inicio com o Windows, desinstalador) tem de apontar para o
    `iniciar.py`, que fica fixo."""
    iss = (AJUDANTE / "instalador.iss").read_text(encoding="utf-8")
    assert "motor\\ajudante\\ajudante.py" not in iss
    for secao in ("[Icons]", "[Registry]", "[Run]", "[UninstallRun]"):
        trecho = iss.split(secao, 1)[1].split("\n[", 1)[0]
        assert "{app}\\iniciar.py" in trecho, secao


@pytest.mark.parametrize("nome", ["instalar.ps1", "instalador.iss"])
def test_o_que_o_windows_le_sem_bom_fica_em_ascii(nome):
    """O Windows PowerShell 5.1 le um .ps1 sem BOM como ANSI, e o ISCC um .iss
    idem: um acento ali vira lixo na tela de quem instala -- ou um erro de
    sintaxe numa string. O que a pessoa le no icone mora no ajudante.py, que
    e Python e UTF-8."""
    texto = (AJUDANTE / nome).read_bytes()
    fora = sorted({chr(b) for b in texto if b > 127})
    assert not fora, f"{nome} tem caracteres fora do ASCII: {fora}"


def test_so_a_ponta_da_main_publica():
    """Tag num commit cujo .github/workflows difere do da main exige a
    permissao `workflows`, que o GITHUB_TOKEN nunca tem: publicar um commit
    que ja foi superado respondia 403 (24-set-2026)."""
    fluxo = (RAIZ / ".github" / "workflows" / "windows.yml").read_text(encoding="utf-8")
    publicar = fluxo.split("  publicar:", 1)[1]
    assert 'commits/main" --jq .sha' in publicar
    assert publicar.index("commits/main") < publicar.index("gh release create")
