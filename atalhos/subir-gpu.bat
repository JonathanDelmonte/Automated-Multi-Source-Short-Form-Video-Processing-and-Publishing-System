@echo off
REM Ficou pelo costume. Desde 22-set-2026 o subir.bat descobre sozinho se a
REM maquina tem placa NVIDIA (_modo-gpu.bat), entao os dois fazem a mesma coisa.
REM
REM Ter dois era justamente o defeito: o atualizar.bat e o reconstruir.bat
REM subiam pelo caminho SEM placa, e bastava usa-los uma vez para o backend
REM voltar a transcrever em CPU, sem aviso. Pode ser apagado sem perda.
call "%~dp0subir.bat"
