@echo off
REM Reconstroi a imagem e sobe. DEMORA.
REM
REM So e necessario quando muda a LISTA DE DEPENDENCIAS -- requirements.txt,
REM package.json ou o Dockerfile. Mudanca de codigo nao precisa disto.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
docker compose up -d --build
if %errorlevel% neq 0 (
  echo.
  echo A construcao falhou. O erro esta acima.
  pause
  exit /b 1
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
