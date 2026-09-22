@echo off
REM Qual cliente do YouTube ainda passa hoje, nesta maquina.
REM
REM   testar-youtube.bat https://youtu.be/xxxxxxxx
REM
REM Ganhou atalho pelo mesmo motivo do diagnostico.bat: e um comando que se
REM roda VARIAS vezes, e sempre no dia ruim -- quando um link parou de baixar
REM e a pergunta e "o que o YouTube esta servindo agora". A resposta muda sem
REM ninguem mexer no codigo, entao ela e medida, nao lembrada.
REM
REM Pergunta ao CONTAINER, nao a este computador: e de la que o job sai.
chcp 65001 >nul
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."

if "%~1"=="" (
  echo.
  echo  Falta a URL do video. Exemplo:
  echo.
  echo     testar-youtube.bat https://youtu.be/dQw4w9WgXcQ
  echo.
  echo  Arrastar o link do navegador para esta janela tambem cola a URL.
  echo.
  pause
  exit /b 1
)

set "ARQ=%~dp0..\diagnostico-youtube.txt"

echo.
echo Medindo (leva cerca de um minuto: sao varios clientes, um por vez)...
echo.
docker compose exec -T backend python diagnostico_youtube.py "%~1" > "%ARQ%"
if %errorlevel% neq 0 (
  echo.
  echo ============================================================
  echo  Nao consegui falar com o backend. O mais provavel e que os
  echo  servicos estejam parados. Suba:
  echo.
  echo     subir-gpu.bat   se a maquina tem placa NVIDIA
  echo     subir.bat       se nao tem
  echo.
  echo  E depois rode este atalho de novo.
  echo ============================================================
  echo.
  del "%ARQ%" 2>nul
  pause
  exit /b 1
)

type "%ARQ%"
echo.
echo ============================================================
echo  Salvo em diagnostico-youtube.txt, na pasta do projeto.
echo ============================================================
echo.
pause
