@echo off
REM Abre o painel no navegador padrao.
REM
REM A porta e 5175, nao 5173. O log do frontend anuncia 5173 porque essa e a
REM porta DENTRO do container; o compose a publica como 5175 no host
REM (`"5175:5173"`). Quem le o log e digita o que esta escrito bate em nada.
REM
REM Nao abre o Docker: se nada estiver no ar, o navegador vai dizer isso mais
REM depressa do que uma espera de dois minutos aqui.
start "" http://localhost:5175
