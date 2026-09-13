@echo off
REM Reconstroi a imagem e sobe. DEMORA.
REM
REM So e necessario quando muda a LISTA DE DEPENDENCIAS -- requirements.txt,
REM package.json ou o Dockerfile. Mudanca de codigo nao precisa disto.
cd /d "%~dp0"
docker compose up --build
