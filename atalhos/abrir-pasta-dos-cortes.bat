@echo off
REM Abre no Explorer a pasta onde ficam os cortes: output, dentro do projeto.
REM
REM E a prova de que os videos estao no SEU disco, e nao dentro do Docker: o
REM container grava direto aqui, porque o compose monta esta pasta dentro dele.
REM Cada subpasta e um projeto, e os arquivos comecam pelo titulo do video. O
REM corte mais completo e o que comeca com subtitled_ (gancho e legenda).
REM
REM Nao abre o Docker: a pasta existe mesmo com ele desligado.
if not exist "%~dp0..\output" mkdir "%~dp0..\output"
start "" "%~dp0..\output"
