@echo off
REM Sobe o projeto. Este e o comando do dia a dia.
REM
REM Nao reconstroi a imagem: `git pull` de codigo Python ou React ja vale
REM sozinho (o repositorio e montado dentro do container, o uvicorn roda com
REM --reload e o Vite vigia os arquivos). Use reconstruir.bat SO quando mudar
REM requirements.txt, package.json ou o Dockerfile.
cd /d "%~dp0"
docker compose up
