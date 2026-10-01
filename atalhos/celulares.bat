@echo off
REM Liga o adb deste computador e mostra os celulares que ele ve (etapa 7.9).
REM
REM O adb e a ferramenta do Google que fala com o celular, pelo cabo ou pela
REM rede. O motor no Docker nao o tem: ele pergunta ao adb do WINDOWS, pelo
REM host.docker.internal, e o adb so atende se estiver ligado. Este atalho o
REM acha, liga e lista os aparelhos. Depois de reiniciar o computador, rode de
REM novo. Com o ajudante nada disso e preciso: ele liga o adb sozinho.
REM
REM Nao precisa do Docker, e por isso nao chama o _garantir-docker.bat.
REM
REM O adb nao vem com o projeto, de proposito: e do Google, e se instala uma
REM vez pelo winget. Quando nao o acha, o atalho pergunta se pode instalar.
REM
REM Procura nos mesmos lugares que o motor, na mesma ordem:
REM adb_cliente._candidatos_do_adb. O exe de verdade vem antes do apelido do
REM winget, que ja falhou em achar a AdbWinApi.dll.
chcp 65001 >nul
setlocal

call :achar_adb
if not defined ADB (
  echo.
  echo ============================================================
  echo  Nao achei o adb, a ferramenta do Google que fala com o
  echo  celular. Ele se instala uma vez, por este comando:
  echo.
  echo     winget install --id Google.PlatformTools
  echo ============================================================
  echo.
  where winget >nul 2>&1
  if errorlevel 1 goto :sem_winget
  choice /c SN /m "Instalar agora"
  if errorlevel 2 goto :fim
  winget install --id Google.PlatformTools -e --accept-source-agreements --accept-package-agreements
  call :achar_adb
)
if not defined ADB (
  echo.
  echo  O adb ainda nao apareceu. Feche esta janela e abra o atalho de
  echo  novo; se continuar, reinicie o computador e tente outra vez.
  goto :fim
)

echo.
echo Usando: "%ADB%"
"%ADB%" start-server
if errorlevel 1 (
  echo.
  echo  O adb nao conseguiu ligar. Feche programas que tambem usam o
  echo  celular pelo cabo - o Android Studio, programas de espelhar a
  echo  tela - e rode este atalho de novo.
  goto :fim
)

echo.
echo Os celulares que o adb ve agora:
echo.
"%ADB%" devices -l
echo.
echo ============================================================
echo  device        = pronto. Volte ao painel, na pagina Frota:
echo                  ele aparece em "vistos pelo adb".
echo  unauthorized  = destrave o celular e aceite o aviso
echo                  "permitir depuracao USB". Rode de novo.
echo  nenhuma linha = falta ligar a depuracao USB no celular:
echo                  Configuracoes, Sobre o telefone, toque 7 vezes
echo                  em Numero da versao; depois Opcoes do
echo                  desenvolvedor, Depuracao USB.
echo.
echo  Pode fechar esta janela: o adb continua ligado ate o
echo  computador desligar.
echo ============================================================
goto :fim

:sem_winget
echo.
echo  O winget nao esta neste Windows. Baixe o adb na pagina do
echo  Google, descompacte em C:\ e abra este atalho de novo:
echo.
echo     https://developer.android.com/tools/releases/platform-tools
echo.
echo  Depois de descompactar, tem de existir C:\platform-tools\adb.exe
goto :fim

:fim
echo.
pause
endlocal
exit /b 0

:achar_adb
set "ADB="
if defined ADB_PATH if exist "%ADB_PATH%" set "ADB=%ADB_PATH%"
if defined ADB exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools*") do (
  if exist "%%D\platform-tools\adb.exe" set "ADB=%%D\platform-tools\adb.exe"
)
if defined ADB exit /b 0
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
if defined ADB exit /b 0
if exist "%USERPROFILE%\platform-tools\adb.exe" set "ADB=%USERPROFILE%\platform-tools\adb.exe"
if defined ADB exit /b 0
if exist "C:\platform-tools\adb.exe" set "ADB=C:\platform-tools\adb.exe"
if defined ADB exit /b 0
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\adb.exe" set "ADB=%LOCALAPPDATA%\Microsoft\WinGet\Links\adb.exe"
if defined ADB exit /b 0
for /f "delims=" %%A in ('where adb 2^>nul') do if not defined ADB set "ADB=%%A"
exit /b 0
