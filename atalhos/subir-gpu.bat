@echo off
REM Sobe usando a GPU NVIDIA, destacado.
REM
REM Exige que a imagem tenha sido construida com as libs de CUDA uma vez:
REM   reconstruir-gpu.bat
REM Sem isso o container sobe e transcreve em CPU sem reclamar.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
if %errorlevel% neq 0 (
  echo.
  echo Nao subiu. O erro esta acima.
  pause
  exit /b 1
)
echo.
docker compose ps
echo.
echo ============================================================
echo  No ar: http://localhost:5175
echo.
echo  Confira se a placa chegou mesmo: conferir-gpu.bat
echo  Pode fechar esta janela: os servicos ficam rodando.
echo ============================================================
echo.
pause
