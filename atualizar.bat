@echo off
REM Puxa as mudancas e sobe.
REM
REM Sem rebuild de proposito: `.py` e `.jsx` valem sozinhos. Se o `git pull`
REM tiver trazido mudanca em requirements.txt, package.json ou Dockerfile, o
REM script avisa e voce roda reconstruir.bat.
cd /d "%~dp0"

for /f %%i in ('git rev-parse HEAD') do set ANTES=%%i
git pull
for /f %%i in ('git rev-parse HEAD') do set DEPOIS=%%i

git diff --name-only %ANTES% %DEPOIS% | findstr /R "requirements.txt package.json Dockerfile" >nul
if %errorlevel%==0 (
  echo.
  echo ============================================================
  echo  As DEPENDENCIAS mudaram neste pull.
  echo  Feche isto e rode reconstruir.bat antes de subir.
  echo ============================================================
  echo.
  pause
  exit /b 1
)

docker compose up
