@echo off
REM Sobe o projeto. Este e o comando do dia a dia.
REM
REM Roda DESTACADO (`-d`): o Docker sobe os tres servicos e devolve o terminal.
REM Antes isto ficava anexado ao log, entao a janela nunca fechava e cada
REM atalho aberto virava mais uma janela rolando as MESMAS linhas -- nao sao
REM sistemas diferentes, e a mesma pilha vista de varios lugares. Para ver o
REM log quando ele for preciso: ver-log.bat
REM
REM Nao reconstroi a imagem: `git pull` de codigo Python ou React ja vale
REM sozinho (o repositorio e montado dentro do container, o uvicorn roda com
REM --reload e o Vite vigia os arquivos). Use reconstruir.bat SO quando mudar
REM requirements.txt, package.json ou o Dockerfile.
cd /d "%~dp0"
docker compose up -d
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
echo  Pode fechar esta janela: os servicos ficam rodando.
echo  Para parar de verdade, use parar.bat
echo ============================================================
echo.
pause
