; O instalador do ajudante do Cortes (Fase 6.2, 24-set-2026).
;
; Compilado no CI (.github/workflows/windows.yml) pelo ISCC do Inno Setup,
; que e gratis. Nada aqui pede administrador: tudo mora em
; %LOCALAPPDATA%\Cortes, por usuario -- o que tambem poe tudo fora das pastas
; que o OneDrive sincroniza.
;
; O .exe traz o que nao depende do computador (o codigo do motor, o uv, o
; ffmpeg e o deno); o `instalar.ps1` baixa o que depende (Python, bibliotecas,
; e as de CUDA so onde ha placa NVIDIA).
;
; O codigo mora em `versoes\<versao>\`, e o `atual.txt` diz qual vale: e o
; formato da atualizacao sozinha (atualizacao.py). Os atalhos chamam o
; `iniciar.py`, que a atualizacao nunca troca.
;
; Sem assinatura digital, que e paga: o Windows mostra "O Windows protegeu o
; computador" na primeira vez. "Mais informacoes" -> "Executar assim mesmo".

#ifndef Versao
  #define Versao "0.0.0-local"
#endif

[Setup]
AppId={{6F3B2C1E-8D4A-4E7B-9C21-5A0D3E9F7B64}
AppName=Cortes
AppVersion={#Versao}
AppVerName=Cortes (ajudante) {#Versao}
AppPublisher=Jonathan Delmonte
AppPublisherURL=https://virtu-clips.zirtuno.workers.dev
DefaultDirName={localappdata}\Cortes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
; uv, ffmpeg e deno sao de 64 bits. Num Windows de 32, uma mensagem clara na
; hora, e nao um erro sem sentido no meio da instalacao do motor.
ArchitecturesAllowed=x64compatible
OutputDir=saida
OutputBaseFilename=Cortes-Ajudante
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=cortes.ico
UninstallDisplayIcon={app}\cortes.ico
UninstallDisplayName=Cortes (ajudante)
; Uma atualizacao feita pelo instalador fecha o ajudante antes de copiar.
CloseApplications=force

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[InstallDelete]
; Reinstalar (ou instalar uma versao nova por cima) comeca de uma pasta de
; versoes limpa. O ajudante ja foi desligado no PrepareToInstall.
Type: filesandordirs; Name: "{app}\versoes"

[Files]
Source: "pacote\motor\*"; DestDir: "{app}\versoes\{#Versao}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "iniciar.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "pacote\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "cortes.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Cortes"; Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  IconFilename: "{app}\cortes.ico"; Comment: "Abre o Cortes e liga o motor"
Name: "{userdesktop}\Cortes"; Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  IconFilename: "{app}\cortes.ico"; Tasks: atalho

[Tasks]
Name: "atalho"; Description: "Criar um atalho na area de trabalho"

[Registry]
; Liga com o Windows. O proprio ajudante deixa desligar pelo menu.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Cortes"; \
  ValueData: """{app}\venv\Scripts\pythonw.exe"" ""{app}\iniciar.py"""; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  Description: "Abrir o Cortes agora"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Desliga o ajudante (e o motor) antes de apagar os arquivos dele.
Filename: "{app}\venv\Scripts\python.exe"; \
  Parameters: """{app}\iniciar.py"" --parar"; \
  WorkingDir: "{app}"; Flags: runhidden waituntilterminated; RunOnceId: "PararAjudante"

[UninstallDelete]
; Os PROJETOS ficam (dados\): sao os cortes da pessoa. O resto sai.
Type: filesandordirs; Name: "{app}\versoes"
Type: files; Name: "{app}\atual.txt"
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\cache-uv"

[Code]
var
  MotorFalhou: Boolean;

// Instalar por cima de um Cortes aberto: desliga o ajudante e o motor antes
// de a pasta de versoes ser apagada. Sem ajudante rodando, volta na hora.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\iniciar.py')) and
     FileExists(ExpandConstant('{app}\venv\Scripts\python.exe')) then
    Exec(ExpandConstant('{app}\venv\Scripts\python.exe'),
         '"' + ExpandConstant('{app}\iniciar.py') + '" --parar',
         ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

// O `instalar.ps1` num console visivel: a pessoa ve o que esta baixando, e a
// instalacao so se declara pronta se o script terminou bem.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
  Parametros: String;
begin
  if CurStep = ssPostInstall then
  begin
    // A versao que o `iniciar.py` roda.
    SaveStringToFile(ExpandConstant('{app}\atual.txt'), '{#Versao}' + #13#10, False);
    WizardForm.StatusLabel.Caption :=
      'Baixando o motor (algumas centenas de MB). Pode levar alguns minutos...';
    Parametros := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\versoes\{#Versao}\ajudante\instalar.ps1') + '" -Base "' +
      ExpandConstant('{app}') + '"';
    if WizardSilent then
      Parametros := Parametros + ' -SemPausa';
    if not Exec('powershell.exe', Parametros, ExpandConstant('{app}'),
                SW_SHOWNORMAL, ewWaitUntilTerminated, Codigo) or (Codigo <> 0) then
    begin
      MotorFalhou := True;
      // Suprimivel: no /VERYSILENT do CI uma caixa comum esperaria um clique
      // para sempre.
      // Nenhuma linha pode COMECAR com `#`: o pre-processador do Inno a le
      // como diretiva (`#13#10` virava "Unknown preprocessor directive").
      SuppressibleMsgBox('A instalacao do motor nao terminou.' + #13#10 + #13#10 +
             'O registro esta em ' + ExpandConstant('{app}\dados\logs\instalacao.log') + #13#10 +
             'Confira a internet e rode o instalador de novo.',
             mbError, MB_OK, IDOK);
    end;
  end;
end;

// Sem isto o instalador terminaria com 0 mesmo com o motor quebrado -- os
// arquivos foram copiados, e e so isso que o Inno Setup confere. O CI (e
// quem instalar por linha de comando) precisa saber.
function GetCustomSetupExitCode: Integer;
begin
  if MotorFalhou then
    Result := 8
  else
    Result := 0;
end;
