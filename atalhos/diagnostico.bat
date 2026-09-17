@echo off
REM Por que esta lento: a medicao e o ambiente, salvos num txt para colar.
REM
REM Ganhou atalho porque e o comando que se roda VARIAS vezes -- antes de mexer
REM no .env, depois de mexer, e depois de cada video. A mao ele tem quatro
REM pegadinhas, e todas as quatro ja morderam de verdade (16-set-2026):
REM
REM   1. Sem o Docker no ar, o erro fala de um "cano" do Windows
REM      (npipe:////./pipe/dockerDesktopLinuxEngine) e o txt sai VAZIO -- o erro
REM      vai para a tela e o `>` so recebe a saida boa, que nao existiu.
REM   2. Sem o `-T`, o `>` recebe a saida embaralhada com o terminal.
REM   3. `docker compose` tem de rodar na pasta do projeto, nao na do atalho.
REM   4. O `exec` NAO sobe nada: se o backend estiver parado, ele so falha.
chcp 65001 >nul
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
set "ARQ=%~dp0..\diagnostico.txt"

echo.
echo Perguntando ao container...
echo.
docker compose exec -T backend python diagnostico.py > "%ARQ%"
if %errorlevel% neq 0 (
  echo.
  echo ============================================================
  echo  Nao consegui falar com o backend, e o diagnostico pergunta
  echo  a ELE -- nao a este computador.
  echo.
  echo  O mais provavel e que os servicos estejam parados. Suba:
  echo.
  echo     subir-gpu.bat   se a maquina tem placa NVIDIA
  echo     subir.bat       se nao tem
  echo.
  echo  E depois rode este atalho de novo.
  echo ============================================================
  echo.
  del "%ARQ%" 2>nul
  pause
  exit /b 1
)

type "%ARQ%"
echo.
echo ============================================================
echo  Salvo em diagnostico.txt, na pasta do projeto.
echo  Vou abrir no Bloco de Notas: Ctrl+A, Ctrl+C, e cole no chat.
echo ============================================================
echo.
start "" notepad "%ARQ%"
pause
