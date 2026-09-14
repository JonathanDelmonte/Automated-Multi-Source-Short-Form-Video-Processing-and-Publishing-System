@echo off
REM Para tudo, de verdade.
REM
REM Fechar a janela do terminal NAO para nada: os tres servicos tem
REM `restart: unless-stopped` no compose, entao o Docker os religa. Este e o
REM unico jeito de encerrar.
REM
REM Este atalho NAO abre o Docker Desktop: se ele estiver fechado, nao ha o que
REM parar -- abrir o Docker para entao desligar containers seria trabalho para
REM chegar ao mesmo lugar.
cd /d "%~dp0.."
docker info >nul 2>&1
if %errorlevel% neq 0 (
  echo.
  echo O Docker Desktop nao esta rodando -- entao nao ha nada no ar.
  echo.
  pause
  exit /b 0
)
docker compose down
echo.
echo Tudo parado.
echo.
pause
