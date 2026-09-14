@echo off
REM Garante que o Docker Desktop esta de pe. Chamado pelos outros atalhos com
REM `call`; devolve errorlevel 1 se nao conseguiu.
REM
REM Este era o erro que aparecia antes:
REM   failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
REM Ele nao diz "abra o Docker Desktop", diz que nao achou um cano -- entao
REM parece problema do projeto e e do Windows. `docker info` e a pergunta certa:
REM `docker --version` responde sem nunca falar com o motor.

docker info >nul 2>&1
if %errorlevel%==0 exit /b 0

echo.
echo O Docker Desktop nao esta rodando. Abrindo...

set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER_EXE%" set "DOCKER_EXE=%ProgramW6432%\Docker\Docker\Docker Desktop.exe"
if not exist "%DOCKER_EXE%" set "DOCKER_EXE=%LOCALAPPDATA%\Docker\Docker Desktop.exe"

if not exist "%DOCKER_EXE%" (
  echo.
  echo ============================================================
  echo  Nao achei o Docker Desktop nos lugares onde ele costuma ser
  echo  instalado.
  echo.
  echo  Se ele ESTA instalado: abra-o pelo menu Iniciar, espere a
  echo  baleia parar de se mexer, e rode este atalho de novo.
  echo.
  echo  Se NAO esta: docs\COMO-EXECUTAR.md tem o passo de instalacao.
  echo ============================================================
  exit /b 1
)

start "" "%DOCKER_EXE%"

echo Esperando o motor responder. A primeira vez do dia leva de 30s a 2 min.
set /a _tentativas=0
:espera
REM 2s por tentativa, 90 tentativas = 3 minutos de teto.
docker info >nul 2>&1
if %errorlevel%==0 goto pronto
set /a _tentativas+=1
if %_tentativas% geq 90 (
  echo.
  echo ============================================================
  echo  O Docker abriu mas o motor nao respondeu em 3 minutos.
  echo  Veja a janela do Docker Desktop: se ela pedir alguma coisa
  echo  (atualizacao, login, aceitar os termos), responda e rode
  echo  este atalho de novo.
  echo ============================================================
  exit /b 1
)
<nul set /p "=."
timeout /t 2 /nobreak >nul
goto espera

:pronto
echo.
echo Docker no ar.
exit /b 0
