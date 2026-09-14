@echo off
REM Reconstroi a imagem COM as libs de CUDA (~2 GB a mais) e sobe usando a GPU.
REM
REM Roda-se isto uma vez. Depois, o do dia a dia e subir-gpu.bat.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
docker compose build --build-arg GPU=1 backend
if %errorlevel% neq 0 (
  echo.
  echo A construcao falhou. O erro esta acima.
  pause
  exit /b 1
)
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
echo ============================================================
echo.
pause
