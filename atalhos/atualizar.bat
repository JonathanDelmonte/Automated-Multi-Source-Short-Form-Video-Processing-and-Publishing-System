@echo off
REM Puxa as mudancas e sobe. Abre o Docker Desktop sozinho se preciso.
REM
REM Sem rebuild de proposito: `.py` e `.jsx` valem sozinhos. Se o `git pull`
REM tiver trazido mudanca em requirements.txt, package.json ou Dockerfile, o
REM script avisa e voce roda reconstruir.bat.
cd /d "%~dp0.."

for /f %%i in ('git rev-parse HEAD') do set ANTES=%%i
git pull
for /f %%i in ('git rev-parse HEAD') do set DEPOIS=%%i

if "%ANTES%"=="%DEPOIS%" (
  echo.
  echo Nada novo para baixar. Subindo o que ja existe.
  call "%~dp0_garantir-docker.bat"
  if errorlevel 1 ( pause & exit /b 1 )
  docker compose up -d
  goto fim
)

git diff --name-only %ANTES% %DEPOIS% | findstr /R "requirements.txt package.json Dockerfile" >nul
if %errorlevel%==0 (
  echo.
  echo ============================================================
  echo  As DEPENDENCIAS mudaram neste pull.
  echo  Feche isto e rode reconstruir.bat antes de subir.
  echo ============================================================
  echo.
  pause
  exit /b 1
)

call "%~dp0_garantir-docker.bat"
if errorlevel 1 ( pause & exit /b 1 )

docker compose up -d
if %errorlevel% neq 0 (
  echo.
  echo Nao subiu. O erro esta acima.
  pause
  exit /b 1
)

REM O `--reload` do uvicorn depende de eventos do sistema de arquivos, e eles
REM NAO atravessam o bind mount do Docker Desktop quando o repositorio mora num
REM caminho do Windows (C:\...). Entao a atualizacao e explicita em vez de
REM torcer para os processos perceberem: sao ~3 s cada, e tira a duvida de
REM "sera que o pull chegou?".
REM
REM **O frontend tambem entra, e ate 17-set-2026 nao entrava.** O comentario
REM antigo dizia "o frontend nao precisa -- o Vite roda com polling
REM (VITE_USE_POLLING=1)", e o polling resolve mesmo a EDICAO de um arquivo que
REM ja existia. O que ele nao cobre e a mudanca do GRAFO DE MODULOS: um pull que
REM ACRESCENTA ou APAGA arquivo deixa o dev server servindo o grafo que leu na
REM subida, e o painel abre em PRETO -- sem erro, sem log, so preto. Aconteceu
REM depois do pull da Fase 5, e a tabela do docs/COMO-EXECUTAR.md ja previa o
REM caso ("arquivos de frontend apagados -> docker compose restart frontend"):
REM faltava o atalho fazer.
echo.
echo Reiniciando o backend e o painel para valer o que foi baixado...
docker compose restart backend frontend

:fim
echo.
docker compose ps
echo.
echo ============================================================
echo  Atualizado. No ar: http://localhost:5175
echo.
echo  No navegador, de um Ctrl+F5 na aba do painel.
echo  Pode fechar esta janela: os servicos ficam rodando.
echo ============================================================
echo.
pause
