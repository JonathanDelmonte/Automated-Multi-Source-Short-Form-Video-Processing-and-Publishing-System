@echo off
REM Sobe usando a GPU NVIDIA, destacado (veja o comentario em subir.bat).
REM
REM Exige que a imagem tenha sido construida com as libs de CUDA uma vez:
REM   reconstruir-gpu.bat
REM Sem isso o container sobe e transcreve em CPU sem reclamar.
cd /d "%~dp0"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
if %errorlevel% neq 0 (
  echo.
  echo Nao subiu. O erro esta acima.
  pause
  exit /b %errorlevel%
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
