@echo off
REM Sobe os servicos no modo que o _modo-gpu.bat decidiu. Chamado com `call`,
REM DEPOIS dele.
REM
REM Se a placa existe mas o Docker se recusa a entrega-la ao container, tenta
REM de novo em CPU em vez de deixar o sistema fora do ar: devagar e melhor que
REM parado. E AVISA, porque devagar em silencio foi exatamente o defeito que o
REM _modo-gpu.bat existe para consertar.
docker compose up -d
if not errorlevel 1 exit /b 0
if not "%CORTES_GPU%"=="1" exit /b 1

echo.
echo ============================================================
echo  O Docker nao subiu com a placa NVIDIA - o erro esta acima.
echo  Tentando de novo em CPU, para nao ficar fora do ar: vai
echo  funcionar, so que mais devagar.
echo.
echo  Para a placa voltar, o Docker Desktop precisa do motor
echo  WSL 2: Settings, General, Use the WSL 2 based engine.
echo ============================================================
echo.
set "COMPOSE_FILE=%CORTES_COMPOSE_CPU%"
set "CORTES_GPU=0"
docker compose up -d
exit /b %errorlevel%
