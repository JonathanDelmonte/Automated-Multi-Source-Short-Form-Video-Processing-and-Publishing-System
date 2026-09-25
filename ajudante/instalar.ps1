# O motor do Virtu Clips no Windows, sem Docker (ajudante, Fase 6.2).
#
# Roda no fim do instalador (Instalar-Virtu-Clips.exe) e a cada atualizacao
# que mude as dependencias. O instalador ja trouxe o codigo (versoes\), o
# Python (python\), o uv, o ffmpeg e o deno (bin\); aqui se baixa o que
# depende do computador:
#
#   1. as bibliotecas do motor (~350 MB);
#   2. com placa NVIDIA, as bibliotecas de CUDA do whisper (~1 GB a mais).
#
# O Python vem DENTRO do instalador, e nao do `uv python install`: o uv cria
# um atalho de pasta (junction) ao instalar Python, e no PC do autor o Windows
# recusou atravessa-lo -- erro 448, "ponto de montagem nao confiavel"
# (24-set-2026). Atalho criado por usuario comum e "nao confiavel" para a
# RedirectionGuard, e o GitHub instala como administrador, entao o CI nunca
# viu o erro.
#
# Sem administrador: tudo mora em %LOCALAPPDATA%\VirtuClips.
#
# Uso: powershell -ExecutionPolicy Bypass -File instalar.ps1 -Base <pasta> [-SoDependencias] [-SemPausa]
#
# `-SemPausa` e o que o instalador passa: ele roda este script escondido e
# mostra a saida na propria janela (cada linha "== " e um passo). Ali ninguem
# aperta Enter, e a pausa do erro esperaria para sempre.

param(
    [Parameter(Mandatory = $true)][string]$Base,
    [switch]$SoDependencias,
    [switch]$SemPausa
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
# O uv escreve em UTF-8, e o Windows PowerShell le a saida de um .exe na
# pagina de codigo do console: sem isto, cada acento da mensagem de erro do
# Windows chegava como dois caracteres sem sentido (o "nao" com til virava
# lixo no meio da palavra).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$uv = Join-Path $Base "bin\uv.exe"
# A versao a que este script pertence (versoes\<versao>\ajudante\instalar.ps1):
# a atualizacao roda o da versao NOVA para instalar as dependencias dela, e o
# da anterior para devolve-las se a nova nao passar.
$motor = Split-Path -Parent $PSScriptRoot
$pythonBase = Join-Path $Base "python\python.exe"
$venv = Join-Path $Base "venv"
$python = Join-Path $venv "Scripts\python.exe"
$log = Join-Path $Base "dados\logs\instalacao.log"

New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
Start-Transcript -Path $log -Append | Out-Null

# Os passos sao numerados aqui, e nao no instalador: e este script que sabe
# quantos sao. O instalador mostra o texto de cada linha "== " como titulo.
$script:passo = 0
$script:passos = if ($SoDependencias) { 3 } else { 4 }
function Passo($texto) {
    $script:passo++
    Write-Host ""
    Write-Host "== Passo $($script:passo) de $($script:passos): $texto" -ForegroundColor Yellow
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

# O nvidia-smi vem com o driver: no System32 nos drivers de hoje, na pasta
# NVSMI nos antigos. Num PowerShell de 32 bits o System32 e trocado pelo
# SysWOW64, onde ele nao esta -- dali, so pelo Sysnative. Foi o que fez o
# notebook de um amigo do autor, com placa NVIDIA, instalar no processador
# (25-set-2026): o instalador abria o PowerShell de 32 bits.
function AcharNvidiaSmi {
    $candidatos = @()
    if ($env:windir) {
        $candidatos += Join-Path $env:windir "Sysnative\nvidia-smi.exe"
        $candidatos += Join-Path $env:windir "System32\nvidia-smi.exe"
    }
    foreach ($pf in @($env:ProgramW6432, $env:ProgramFiles)) {
        if ($pf) { $candidatos += Join-Path $pf "NVIDIA Corporation\NVSMI\nvidia-smi.exe" }
    }
    foreach ($c in $candidatos) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    $cmd = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    return $null
}

# O nome da primeira placa NVIDIA, ou $null. O motivo de nao achar vai para o
# registro: "sem placa" e "sem driver" nao tem o mesmo conserto.
function PlacaNvidia {
    $smi = AcharNvidiaSmi
    if (-not $smi) {
        Write-Host "(nvidia-smi nao encontrado: sem placa NVIDIA ou sem o driver dela)"
        return $null
    }
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $saida = @(& $smi -L 2>$null)
        $codigo = $LASTEXITCODE
    } catch {
        Write-Host "(nvidia-smi falhou: $_)"
        return $null
    } finally {
        $ErrorActionPreference = $anterior
    }
    $linha = $saida | Where-Object { "$_" -match "^GPU \d+: " } | Select-Object -First 1
    if ($codigo -ne 0 -or -not $linha) {
        Write-Host "(nvidia-smi em $smi respondeu $codigo sem listar placa)"
        return $null
    }
    return ("$linha" -replace "^GPU \d+: ", "") -replace "\s*\(UUID:.*$", ""
}

# A RedirectionGuard deste processo, para o registro: se o erro 448 voltar,
# a primeira pergunta e se ela estava ligada, e quem a ligou.
function ProtecaoDeRedirecionamento {
    try {
        Add-Type -Namespace VirtuClips -Name Mitigacao -MemberDefinition @'
[DllImport("kernel32.dll")]
public static extern System.IntPtr GetCurrentProcess();
[DllImport("kernel32.dll", SetLastError = true)]
public static extern bool GetProcessMitigationPolicy(System.IntPtr processo, int politica, ref uint valor, System.IntPtr tamanho);
'@ -ErrorAction SilentlyContinue
        $valor = [uint32]0
        # 16 = ProcessRedirectionTrustPolicy; o bit 0 e o "EnforceRedirectionTrust".
        # O tamanho e um SIZE_T: IntPtr tem a mesma largura, e o PowerShell
        # converte um inteiro para ele sem ambiguidade (para UIntPtr, nao).
        $ok = [VirtuClips.Mitigacao]::GetProcessMitigationPolicy(
            [VirtuClips.Mitigacao]::GetCurrentProcess(), 16, [ref]$valor, [System.IntPtr]4)
        if (-not $ok) { return "nao se aplica a este Windows" }
        if ($valor -band 1) { return "LIGADA" }
        return "desligada"
    } catch {
        return "nao deu para saber"
    }
}

try {
    Write-Host "Instalando o motor do Virtu Clips. Isto baixa algumas centenas de MB"
    Write-Host "e leva alguns minutos; a janela fecha sozinha no fim."
    Write-Host "(protecao de redirecionamento do Windows: $(ProtecaoDeRedirecionamento))"
    # O de 32 bits nao ve o nvidia-smi (ver AcharNvidiaSmi): o CI confere esta linha.
    Write-Host "(PowerShell de 64 bits: $(if ([Environment]::Is64BitProcess) { 'sim' } else { 'NAO' }))"

    # O uv so usa o Python que veio no instalador: nada de baixar outro, nem
    # de criar os atalhos de pasta com que ele organiza os que baixa.
    $env:UV_PYTHON_DOWNLOADS = "never"
    $env:UV_CACHE_DIR = Join-Path $Base "cache-uv"

    if (-not $SoDependencias) {
        Passo "ambiente do motor (o Python que veio no instalador)"
        if (-not (Test-Path $pythonBase)) {
            throw "o Python que vem no instalador nao esta em $pythonBase"
        }
        Rodar $uv @("venv", $venv, "--python", $pythonBase, "--allow-existing")
    }

    Passo "bibliotecas do motor (algumas centenas de MB)"
    Rodar $uv @("pip", "install", "--python", $python,
                "-r", (Join-Path $motor "ajudante\requirements-windows.txt"))
    # O YouTube muda toda semana e o yt-dlp acompanha: vai sempre o mais novo.
    Rodar $uv @("pip", "install", "--python", $python, "--upgrade", "yt-dlp[default]")

    $placa = PlacaNvidia
    if ($placa) {
        Passo "placa NVIDIA encontrada ($placa): bibliotecas de CUDA para o whisper (cerca de 1 GB)"
        # Sem elas o motor funciona, no processador -- entao faltar nao derruba
        # a instalacao. A atualizacao sozinha tenta de novo quando ve a placa
        # sem as bibliotecas (atualizacao.aplicar).
        try {
            Rodar $uv @("pip", "install", "--python", $python,
                        "-r", (Join-Path $motor "ajudante\requirements-windows-gpu.txt"))
            $resumo = "o motor vai usar a placa NVIDIA ($placa)"
        } catch {
            Write-Host "aviso: as bibliotecas da placa nao vieram ($_)"
            $resumo = "o motor vai usar o processador por enquanto: as bibliotecas da placa nao vieram"
        }
    } else {
        Passo "sem placa NVIDIA: o motor vai usar o processador"
        $resumo = "o motor vai usar o processador"
    }

    Passo "conferindo"
    Rodar $python @("-c", "import fastapi, faster_whisper, mediapipe, torch, cv2; print('motor ok')")

    # O cache do uv so serve para a proxima instalacao; sao centenas de MB.
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $env:UV_CACHE_DIR

    Write-Host ""
    Write-Host "== Pronto: $resumo" -ForegroundColor Green
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
