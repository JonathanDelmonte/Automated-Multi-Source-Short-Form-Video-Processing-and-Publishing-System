; O instalador do Virtu Clips (ajudante, Fase 6.2, 24-set-2026).
;
; Compilado no CI (.github/workflows/windows.yml) pelo ISCC do Inno Setup,
; que e gratis. Nada aqui pede administrador: tudo mora em
; %LOCALAPPDATA%\VirtuClips, por usuario -- o que tambem poe tudo fora das
; pastas que o OneDrive sincroniza.
;
; O .exe traz o que nao depende do computador (o codigo do motor, o Python,
; o uv, o ffmpeg e o deno); o `instalar.ps1` baixa o que depende (as
; bibliotecas, e as de CUDA so onde ha placa NVIDIA).
;
; O Python vem DENTRO do .exe. Ate 24-set-2026 o `instalar.ps1` o baixava com
; `uv python install`, que cria um atalho de pasta (junction) por versao -- e
; no PC do autor o Windows se recusou a atravessa-lo: erro 448, "ponto de
; montagem nao confiavel". Ver RedirectionGuard, abaixo.
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
; Onde o empacotar.py deixou o pacote. O CI o monta numa pasta CURTA
; (/DPacote=C:\vc\pacote): o ISCC do Inno 6.7 nao abre caminho de mais de 260
; caracteres, e o Python embutido, dentro da pasta do checkout do GitHub, passa
; disso (Lib\site-packages\pip\...\__pycache__\...).
#ifndef Pacote
  #define Pacote "pacote"
#endif

[Setup]
; O mesmo AppId de quando o programa se chamava Cortes: o Windows trata esta
; instalacao como atualizacao daquela, e fica uma entrada so em "Aplicativos".
AppId={{6F3B2C1E-8D4A-4E7B-9C21-5A0D3E9F7B64}
AppName=Virtu Clips
AppVersion={#Versao}
AppVerName=Virtu Clips {#Versao}
AppPublisher=Jonathan Delmonte
AppPublisherURL=https://virtu-clips.zirtuno.workers.dev
DefaultDirName={localappdata}\VirtuClips
; A pasta mudou com o nome (era {localappdata}\Cortes). Sem isto o Inno
; instalaria de novo na pasta da instalacao anterior, que tem o mesmo AppId.
; O que ficou la e levado pelo MigrarDoCortes, no [Code].
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
; uv, ffmpeg, deno e o Python sao de 64 bits. Num Windows de 32, uma mensagem
; clara na hora, e nao um erro sem sentido no meio da instalacao do motor.
ArchitecturesAllowed=x64compatible
; Desde o Inno Setup 6.7 o instalador liga, por padrao, a RedirectionGuard do
; Windows: recusar atravessar atalho de pasta criado por usuario comum. Ela
; protege instalador que roda como administrador e mexe em pasta que qualquer
; um pode escrever -- nao e o caso: este roda como a propria pessoa, dentro
; da pasta dela. E ela chegou aos programas que o instalador abre: foi o uv,
; filho do powershell, filho do instalador, que levou o erro 448 no PC do
; autor (24-set-2026). O Python embutido ja tira o atalho do caminho; isto
; garante que nenhum outro vire o mesmo erro.
RedirectionGuard=no
OutputDir=saida
OutputBaseFilename=Instalar-Virtu-Clips
Compression=lzma2/max
SolidCompression=yes
; Escuro como a marca e o site. As imagens sao desenhadas pelo marca.py
; (empacotar.py): a logo sobre preto na primeira e na ultima tela, e sem
; fundo no canto das outras -- o transparente ganha a cor da janela, que no
; estilo escuro ja e escura. Varios tamanhos: o Inno escolhe pelo DPI.
WizardStyle=modern dark includetitlebar
WizardImageFile={#Pacote}\assistente\grande-*.png
WizardSmallImageFile={#Pacote}\assistente\pequena-*.png
SetupIconFile={#Pacote}\virtu-clips.ico
UninstallDisplayIcon={app}\virtu-clips.ico
UninstallDisplayName=Virtu Clips
; Uma atualizacao feita pelo instalador fecha o ajudante antes de copiar.
CloseApplications=force

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[InstallDelete]
; Reinstalar (ou instalar uma versao nova por cima) comeca de uma pasta de
; versoes limpa, e de um Python exatamente igual ao que vem no .exe. O
; ajudante ja foi desligado no PrepareToInstall.
Type: filesandordirs; Name: "{app}\versoes"
Type: filesandordirs; Name: "{app}\python"

[Files]
Source: "{#Pacote}\motor\*"; DestDir: "{app}\versoes\{#Versao}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#Pacote}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "iniciar.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Pacote}\bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "{#Pacote}\virtu-clips.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Virtu Clips"; Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  IconFilename: "{app}\virtu-clips.ico"; Comment: "Abre o Virtu Clips e liga o motor"
Name: "{userdesktop}\Virtu Clips"; Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  IconFilename: "{app}\virtu-clips.ico"; Tasks: atalho

[Tasks]
Name: "atalho"; Description: "Criar um atalho na area de trabalho"

[Registry]
; Liga com o Windows. O proprio ajudante deixa desligar pelo menu. O nome do
; valor ficou o de antes da marca (ajudante.VALOR_NO_INICIO): assim o de uma
; instalacao antiga e sobrescrito, e nao sobra um segundo.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Cortes"; \
  ValueData: """{app}\venv\Scripts\pythonw.exe"" ""{app}\iniciar.py"""; \
  Flags: uninsdeletevalue

[Run]
Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  Description: "Abrir o Virtu Clips agora"; Flags: postinstall nowait skipifsilent

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

// Pede ao ajudante instalado numa pasta que saia, levando o motor junto. Sem
// ajudante rodando, o `--parar` volta na hora.
procedure PararAjudante(const Pasta: String);
var
  Codigo: Integer;
begin
  if FileExists(Pasta + '\iniciar.py') and
     FileExists(Pasta + '\venv\Scripts\python.exe') then
    Exec(Pasta + '\venv\Scripts\python.exe', '"' + Pasta + '\iniciar.py" --parar',
         Pasta, SW_HIDE, ewWaitUntilTerminated, Codigo);
end;

// Ate 24-set-2026 o programa se chamava Cortes e morava em
// %LOCALAPPDATA%\Cortes. Os projetos (dados\) vem para a pasta nova; o
// programa antigo e os atalhos dele saem.
procedure MigrarDoCortes;
var
  Antiga, Nova: String;
begin
  Antiga := ExpandConstant('{localappdata}\Cortes');
  // A assinatura de uma instalacao nossa -- e nao de outro programa que
  // tenha escolhido o mesmo nome de pasta.
  if not (FileExists(Antiga + '\iniciar.py') and DirExists(Antiga + '\versoes')) then
    Exit;
  Log('Instalacao anterior, do tempo em que se chamava Cortes: ' + Antiga);
  PararAjudante(Antiga);
  Nova := ExpandConstant('{app}');
  if DirExists(Antiga + '\dados') and not DirExists(Nova + '\dados') then
  begin
    ForceDirectories(Nova);
    if RenameFile(Antiga + '\dados', Nova + '\dados') then
      Log('Projetos movidos para ' + Nova + '\dados')
    else
      Log('Os projetos ficaram em ' + Antiga + '\dados: a pasta nao pode ser movida');
  end;
  DelTree(Antiga + '\versoes', True, True, True);
  DelTree(Antiga + '\venv', True, True, True);
  DelTree(Antiga + '\python', True, True, True);
  DelTree(Antiga + '\bin', True, True, True);
  DelTree(Antiga + '\cache-uv', True, True, True);
  DeleteFile(Antiga + '\iniciar.py');
  DeleteFile(Antiga + '\atual.txt');
  DeleteFile(Antiga + '\cortes.ico');
  DeleteFile(Antiga + '\unins000.exe');
  DeleteFile(Antiga + '\unins000.dat');
  // So sai se ficou vazia: projetos que nao puderam ser movidos ficam.
  RemoveDir(Antiga);
  DeleteFile(ExpandConstant('{userprograms}\Cortes.lnk'));
  DeleteFile(ExpandConstant('{userdesktop}\Cortes.lnk'));
end;

// Instalar por cima de um ajudante aberto: desliga-o (e o motor) antes de a
// pasta de versoes ser apagada.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  PararAjudante(ExpandConstant('{app}'));
  MigrarDoCortes;
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
