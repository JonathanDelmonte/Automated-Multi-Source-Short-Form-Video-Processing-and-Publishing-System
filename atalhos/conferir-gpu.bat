@echo off
REM A placa chegou ao container?
REM
REM Pergunta que vale a pena fazer porque a resposta errada e SILENCIOSA: sem a
REM GPU, o WHISPER_DEVICE=cuda cai para CPU sozinho, sem erro nenhum. Funciona,
REM so que lento -- e nao ha nada no log dizendo que foi isso.
call "%~dp0_garantir-docker.bat"
if %errorlevel% neq 0 ( pause & exit /b 1 )

cd /d "%~dp0.."
echo.
echo Perguntando ao container se ele enxerga a GPU...
echo.
REM Pergunta pelo diagnostico.py, e nao mais por
REM `torch.cuda.is_available()` (ate 16-set-2026 era esse). Quem o
REM faster-whisper usa e o ctranslate2, nao o torch: sao bibliotecas diferentes
REM com exigencias diferentes de CUDA/cuDNN, e um True do torch com a
REM transcricao rodando em CPU e a falha silenciosa disfarcada de conferencia
REM feita. De brinde, isto responde tambem pelo encoder de video.
docker compose exec -T backend python diagnostico.py
echo.
echo   A linha "placa p/ o whisper" e a resposta:
echo     sim = GPU de verdade. Pode mandar o video.
echo     nao = a placa nao chegou; ele transcreve em CPU, devagar.
echo.
echo   Para salvar isto num txt e poder colar: diagnostico.bat
echo.
pause
