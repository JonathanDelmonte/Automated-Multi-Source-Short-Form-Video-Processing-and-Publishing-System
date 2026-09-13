@echo off
REM Para tudo, de verdade.
REM
REM Fechar a janela do terminal NAO para nada: os tres servicos tem
REM `restart: unless-stopped` no compose, entao o Docker os religa. Este e o
REM unico jeito de encerrar.
cd /d "%~dp0"
docker compose down
