@echo off
REM Mostra o log do backend, ao vivo.
REM
REM Esta e a UNICA janela que fica rolando de proposito -- as outras sobem e
REM devolvem o terminal. Fechar esta nao para nada: e so uma leitura do log.
REM
REM O que rola sem parar aqui e normal: `GET /health/ready ... 200 OK` a cada
REM poucos segundos e o HEALTHCHECK do Dockerfile perguntando se o backend
REM continua vivo. 200 e a resposta certa.
REM
REM Ctrl+C fecha a leitura.
cd /d "%~dp0"
echo.
echo Log do backend. Ctrl+C para sair (nao para o sistema).
echo.
docker compose logs -f --tail 80 backend
