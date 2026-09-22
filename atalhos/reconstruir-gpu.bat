@echo off
REM Ficou pelo costume. Desde 22-set-2026 o reconstruir.bat descobre sozinho se
REM a maquina tem placa NVIDIA e, se tiver, constroi COM as libs de CUDA (o
REM docker-compose.gpu.yml passa `GPU=1` ao build). Os dois fazem a mesma
REM coisa. Pode ser apagado sem perda.
call "%~dp0reconstruir.bat"
