# O motor do Cortes no Windows, sem Docker (ajudante, Fase 6.2).
#
# Roda no fim do instalador (Cortes-Ajudante.exe) e a cada atualizacao que
# mude as dependencias. O instalador ja trouxe o codigo (motor\), o uv, o
# ffmpeg e o deno (bin\); aqui se baixa o que depende do computador:
#
#   1. o Python 3.11, pelo uv (uma copia so do Cortes, que nao mexe em nada
#      que a pessoa ja tenha instalado);
#   2. as bibliotecas do motor (~350 MB);
#   3. com placa NVIDIA, as bibliotecas de CUDA do whisper (~1 GB a mais).
#
# Sem administrador: tudo mora em %LOCALAPPDATA%\Cortes.
#
# Uso: powershell -ExecutionPolicy Bypass -File instalar.ps1 -Base <pasta> [-SoDependencias] [-SemPausa]
#
# `-SemPausa` e o que o instalador passa quando roda sem janela (/VERYSILENT):
# ali ninguem aperta Enter, e a pausa do erro esperaria para sempre.

param(
    [Parameter(Mandatory = $true)][string]$Base,
    [switch]$SoDependencias,
    [switch]$SemPausa
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$uv = Join-Path $Base "bin\uv.exe"
# A versao a que este script pertence (versoes\<versao>\ajudante\instalar.ps1):
# a atualizacao roda o da versao NOVA para instalar as dependencias dela, e o
# da anterior para devolve-las se a nova nao passar.
$motor = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $Base "venv"
$python = Join-Path $venv "Scripts\python.exe"
$log = Join-Path $Base "dados\logs\instalacao.log"

New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
Start-Transcript -Path $log -Append | Out-Null

function Passo($texto) {
    Write-Host ""
    Write-Host "== $texto" -ForegroundColor Yellow
}

# A saida do programa passa pelo Write-Host, e nao direto ao console: so assim
# ela entra no registro (o Start-Transcript do Windows PowerShell nao ve o que
# um .exe escreve sozinho). E o "Continue" e local de proposito: com "Stop", o
# Windows PowerShell 5.1 transforma a PRIMEIRA linha que o uv escreve no stderr
# -- o progresso dele vai todo para la -- num erro que derruba o script.
function Rodar($exe, [string[]]$argumentos) {
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $exe @argumentos 2>&1 | ForEach-Object { Write-Host "$_" }
        $codigo = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $anterior
    }
    if ($codigo -ne 0) {
        throw "falhou ($codigo): $exe $($argumentos -join ' ')"
    }
}

function TemPlacaNvidia {
    try {
        $saida = & nvidia-smi -L 2>$null
        return ($LASTEXITCODE -eq 0) -and ($saida -match "GPU")
    } catch {
        return $false
    }
}

try {
    Write-Host "Instalando o motor do Cortes. Isto baixa algumas centenas de MB"
    Write-Host "e leva alguns minutos; a janela fecha sozinha no fim."

    # O Python do uv fica dentro da pasta do Cortes, e nao no perfil da pessoa:
    # desinstalar leva tudo junto.
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $Base "python"
    $env:UV_CACHE_DIR = Join-Path $Base "cache-uv"

    if (-not $SoDependencias) {
        Passo "Python 3.11"
        Rodar $uv @("python", "install", "3.11")
        # `only-managed`: sem isto o uv pode escolher um Python que a pessoa ja
        # tenha instalado, e o motor passaria a depender dele.
        Rodar $uv @("venv", $venv, "--python", "3.11", "--python-preference", "only-managed",
                    "--allow-existing")
    }

    Passo "Bibliotecas do motor"
    Rodar $uv @("pip", "install", "--python", $python,
                "-r", (Join-Path $motor "ajudante\requirements-windows.txt"))
    # O YouTube muda toda semana e o yt-dlp acompanha: vai sempre o mais novo.
    Rodar $uv @("pip", "install", "--python", $python, "--upgrade", "yt-dlp[default]")

    if (TemPlacaNvidia) {
        Passo "Placa NVIDIA encontrada: bibliotecas de CUDA para o whisper"
        Rodar $uv @("pip", "install", "--python", $python,
                    "-r", (Join-Path $motor "ajudante\requirements-windows-gpu.txt"))
    } else {
        Passo "Sem placa NVIDIA: o motor vai usar o processador"
    }

    Passo "Conferindo"
    Rodar $python @("-c", "import fastapi, faster_whisper, mediapipe, torch, cv2; print('motor ok')")

    # O cache do uv so serve para a proxima instalacao; sao centenas de MB.
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:UV_CACHE_DIR

    Passo "Pronto"
    Stop-Transcript | Out-Null
    exit 0
} catch {
    Write-Host ""
    Write-Host "A instalacao nao terminou: $_" -ForegroundColor Red
    Write-Host "O registro completo esta em $log"
    Stop-Transcript | Out-Null
    if (-not $SoDependencias -and -not $SemPausa) {
        Read-Host "Aperte Enter para fechar"
    }
    exit 1
}
