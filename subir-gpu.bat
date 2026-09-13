@echo off
REM Sobe usando a GPU NVIDIA.
REM
REM Exige que a imagem tenha sido construida com as libs de CUDA uma vez:
REM   reconstruir-gpu.bat
REM Sem isso o container sobe e transcreve em CPU sem reclamar.
cd /d "%~dp0"
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
