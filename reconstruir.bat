@echo off
REM Reconstroi a imagem e sobe. DEMORA.
REM
REM So e necessario quando muda a LISTA DE DEPENDENCIAS -- requirements.txt,
REM package.json ou o Dockerfile. Mudanca de codigo nao precisa disto.
REM
REM A construcao aparece na tela (e demorada, entao convem ver); no fim, os
REM servicos ficam rodando destacados e o terminal volta.
cd /d "%~dp0"
docker compose up -d --build
if %errorlevel% neq 0 (
  echo.
  echo A construcao falhou. O erro esta acima.
  pause
  exit /b %errorlevel%
)
echo.
docker compose ps
echo.
echo ============================================================
echo  No ar: http://localhost:5175
echo.
echo  Pode fechar esta janela: os servicos ficam rodando.
echo ============================================================
echo.
pause
