@echo off
REM Reconstroi a imagem e sobe. DEMORA.
REM
REM So e necessario quando muda a LISTA DE DEPENDENCIAS -- requirements.txt,
REM package.json ou o Dockerfile. Mudanca de codigo nao precisa disto.
REM
REM **Numa maquina com placa NVIDIA a imagem sai COM as libs de CUDA** (22-set-
REM 2026): o docker-compose.gpu.yml passa `GPU=1` para o build, e o
REM _modo-gpu.bat o inclui sozinho. Ate aqui este atalho construia SEM elas --
REM e e ele que o atualizar.bat manda rodar quando uma dependencia muda. Ou
REM seja: uma atualizacao de dependencia tirava a placa de vez, e so os 40
REM minutos do reconstruir-gpu.bat a devolviam.
REM
REM Construir e subir em dois passos, e nao `up --build`, para que uma falha de
REM CONSTRUCAO nao seja confundida com a placa recusada: so o `up` tem a queda
REM para CPU (_subir.bat), e ela so faz sentido para ele.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
call "%~dp0_modo-gpu.bat"
docker compose build
if %errorlevel% neq 0 (
  echo.
  echo A construcao falhou. O erro esta acima.
  pause
  exit /b 1
)
call "%~dp0_subir.bat"
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
echo  Pode fechar esta janela: os servicos ficam rodando.
echo ============================================================
echo.
pause
