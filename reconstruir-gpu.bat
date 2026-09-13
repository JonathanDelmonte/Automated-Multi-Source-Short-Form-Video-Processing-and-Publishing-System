@echo off
REM Reconstroi a imagem COM as libs de CUDA (~2 GB a mais) e sobe usando a GPU.
REM
REM Roda-se isto uma vez. Depois, o do dia a dia e subir-gpu.bat.
cd /d "%~dp0"
docker compose build --build-arg GPU=1 backend
if %errorlevel% neq 0 (
  echo.
  echo A construcao falhou. O erro esta acima.
  pause
  exit /b %errorlevel%
)
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
