@echo off
REM Sobe o projeto. Este e o comando do dia a dia.
REM
REM Abre o Docker Desktop sozinho se ele nao estiver de pe, e roda DESTACADO
REM (`-d`): o Docker sobe os tres servicos e devolve o terminal. Para ver o
REM log quando ele for preciso: ver-log.bat
REM
REM Nao reconstroi a imagem: `git pull` de codigo Python ou React ja vale
REM sozinho (o repositorio e montado dentro do container, o uvicorn roda com
REM --reload e o Vite vigia os arquivos com polling). Use reconstruir.bat SO
REM quando mudar requirements.txt, package.json ou o Dockerfile.
REM
REM **Usa a placa NVIDIA sozinho quando a maquina tem uma** (22-set-2026, ver
REM _modo-gpu.bat). Ate aqui havia este e o subir-gpu.bat, e clicar no errado
REM tirava a placa do backend sem dizer nada.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

REM `..` porque este arquivo mora em atalhos\ e o docker-compose.yml na raiz.
cd /d "%~dp0.."
call "%~dp0_modo-gpu.bat"
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
echo  Para parar de verdade, use parar.bat
echo ============================================================
echo.
pause
