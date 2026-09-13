@echo off
REM Reconstroi a imagem COM as libs de CUDA (~2 GB a mais) e sobe usando a GPU.
REM
REM Roda-se isto uma vez. Depois, o do dia a dia e subir-gpu.bat.
cd /d "%~dp0"
docker compose build --build-arg GPU=1 backend
if %errorlevel% neq 0 exit /b %errorlevel%
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
