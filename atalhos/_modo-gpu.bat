@echo off
REM Decide, num lugar so, se os servicos sobem com a placa NVIDIA.
REM
REM **Por que existe (22-set-2026).** Havia dois jeitos de subir -- subir.bat e
REM subir-gpu.bat -- e so um deles levava o docker-compose.gpu.yml. O
REM atualizar.bat e o reconstruir.bat usavam o outro. Bastava atualizar uma vez
REM e o `docker compose up -d` RECRIAVA o backend sem a placa: a configuracao do
REM servico muda sem o arquivo de GPU, e o compose recria o container quando a
REM configuracao muda. Dai em diante a transcricao rodava o whisper `small` em
REM CPU, sem erro e sem aviso. Um video de 10 min levou 5 min so para
REM transcrever, numa maquina com RTX 3060.
REM
REM A pergunta passou a ser feita a MAQUINA, e nao a quem clica: o `nvidia-smi`
REM do Windows vem junto com o driver da NVIDIA, entao ele responder e haver
REM placa e driver.
REM
REM Chamado com `call`. Deixa no ambiente de quem chamou:
REM   COMPOSE_FILE        o proprio `docker compose` le esta variavel, entao
REM                       TODO comando seguinte na mesma janela -- up, build,
REM                       restart, ps -- usa os mesmos arquivos sem repetir -f.
REM   CORTES_GPU          1 ou 0.
REM   CORTES_COMPOSE_CPU  so o arquivo base, para o _subir.bat cair para CPU se
REM                       o Docker recusar a placa.
REM
REM Caminhos absolutos de proposito: assim o resultado nao depende de quem
REM chamou ja ter feito o `cd` para a raiz.
for %%i in ("%~dp0..") do set "_CORTES_RAIZ=%%~fi"
set "COMPOSE_PATH_SEPARATOR=;"
set "CORTES_COMPOSE_CPU=%_CORTES_RAIZ%\docker-compose.yml"

REM Sem `goto` de proposito: com o arquivo em LF, a busca de rotulo do cmd.exe
REM pode errar conforme o rotulo cai no arquivo, e um bloco `if` nao depende disso.
nvidia-smi -L >nul 2>&1
if errorlevel 1 (
  set "COMPOSE_FILE=%CORTES_COMPOSE_CPU%"
  set "CORTES_GPU=0"
  echo Nenhuma placa NVIDIA respondeu nesta maquina: subindo em CPU.
  exit /b 0
)
set "COMPOSE_FILE=%_CORTES_RAIZ%\docker-compose.yml;%_CORTES_RAIZ%\docker-compose.gpu.yml"
set "CORTES_GPU=1"
echo Placa NVIDIA encontrada: subindo com a GPU.
exit /b 0
