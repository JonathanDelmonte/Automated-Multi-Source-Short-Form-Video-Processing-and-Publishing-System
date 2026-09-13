@echo off
REM A placa chegou ao container?
REM
REM Pergunta que vale a pena fazer porque a resposta errada e SILENCIOSA: sem a
REM GPU, o WHISPER_DEVICE=cuda cai para CPU sozinho, sem erro nenhum. Funciona,
REM so que lento -- e nao ha nada no log dizendo que foi isso.
cd /d "%~dp0"
echo.
echo Perguntando ao container se ele enxerga a GPU...
echo.
docker compose exec backend python -c "import torch; print('GPU disponivel:', torch.cuda.is_available())"
echo.
echo   True  = GPU de verdade. Pode mandar o video.
echo   False = a placa nao chegou; ele vai transcrever em CPU, devagar.
echo.
pause
