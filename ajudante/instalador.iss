; O instalador do Virtu Clips (ajudante, Fase 6.2, 24-set-2026).
;
; Compilado no CI (.github/workflows/windows.yml) pelo ISCC do Inno Setup,
; que e gratis. Nada aqui pede administrador: tudo mora em
; %LOCALAPPDATA%\VirtuClips, por usuario -- o que tambem poe tudo fora das
; pastas que o OneDrive sincroniza.
;
; O .exe traz o que nao depende do computador (o codigo do motor, o Python,
; o uv, o ffmpeg e o deno); o `instalar.ps1` baixa o que depende (as
; bibliotecas, e as de CUDA so onde ha placa NVIDIA). Ele roda escondido, no
; PowerShell de 64 bits, e a saida dele aparece na propria janela do
; instalador (CriarTerminal, no [Code]).
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
; O texto vem da traducao do proprio Inno, com os acentos que este arquivo --
; ASCII de proposito -- nao pode ter.
Name: "atalho"; Description: "{cm:CreateDesktopIcon}"

[Registry]
; Liga com o Windows. O proprio ajudante deixa desligar pelo menu. O nome do
; valor ficou o de antes da marca (ajudante.VALOR_NO_INICIO): assim o de uma
; instalacao antiga e sobrescrito, e nao sobra um segundo.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "Cortes"; \
  ValueData: """{app}\venv\Scripts\pythonw.exe"" ""{app}\iniciar.py"""; \
  Flags: uninsdeletevalue

[Run]
; So com o motor instalado: abrir um motor que nao terminou de instalar so
; mostraria um erro a mais.
Filename: "{app}\venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\iniciar.py"""; WorkingDir: "{app}"; \
  Description: "Abrir o Virtu Clips agora"; Flags: postinstall nowait skipifsilent; \
  Check: MotorInstalado

[UninstallRun]
; Desliga o ajudante (e o motor) antes de apagar os arquivos dele. Numa
; instalacao que morreu antes de criar o venv (o erro 448 de 24-set-2026), o
; python.exe nao existe e nao ha ajudante para desligar: sem o
; `skipifdoesntexist`, o desinstalador mostraria um erro por isso.
Filename: "{app}\venv\Scripts\python.exe"; \
  Parameters: """{app}\iniciar.py"" --parar"; \
  WorkingDir: "{app}"; Flags: runhidden waituntilterminated skipifdoesntexist; \
  RunOnceId: "PararAjudante"

[UninstallDelete]
; Os PROJETOS ficam (dados\): sao os cortes da pessoa. O resto sai.
Type: filesandordirs; Name: "{app}\versoes"
Type: files; Name: "{app}\atual.txt"
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\bin"
Type: filesandordirs; Name: "{app}\cache-uv"

[Code]
const
  WM_VSCROLL = $0115;
  SB_BOTTOM = 7;
  // O terminal guarda so as ultimas: a instalacao inteira ficaria pesada de
  // redesenhar a cada linha.
  LINHAS_NO_TERMINAL = 400;

var
  MotorFalhou: Boolean;
  PaginaDoQueFazer: TInputOptionWizardPage;
  Desinstalando: Boolean;
  Terminal: TNewMemo;
  Resumo: String;

// A janela do PowerShell, dentro do instalador. O instalar.ps1 roda
// escondido e cada linha dele aparece aqui, numa caixa escura de letra fixa;
// a linha "== Passo 2 de 4: ..." vira o titulo acima da barra. A janela azul
// de verdade assustava quem instalava e nao dizia em que passo estava
// (25-set-2026, pedido do autor).
procedure CriarTerminal;
begin
  Terminal := TNewMemo.Create(WizardForm);
  Terminal.Parent := WizardForm.InstallingPage;
  Terminal.ReadOnly := True;
  Terminal.ScrollBars := ssVertical;
  Terminal.WordWrap := True;
  Terminal.TabStop := False;
  Terminal.Color := clBlack;
  Terminal.Font.Name := 'Consolas';
  Terminal.Font.Size := 8;
  Terminal.Font.Color := $00D0D0D0;
  Terminal.Visible := False;
end;

procedure MostrarTerminal;
begin
  Terminal.Left := WizardForm.ProgressGauge.Left;
  Terminal.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(12);
  Terminal.Width := WizardForm.ProgressGauge.Width;
  Terminal.Height := WizardForm.InstallingPage.Height - Terminal.Top;
  if Terminal.Height < ScaleY(60) then
    Terminal.Height := ScaleY(60);
  Terminal.Anchors := [akLeft, akTop, akRight, akBottom];
  Terminal.Visible := True;
end;

// Cada linha do instalar.ps1. As "== " sao os passos; a "== Pronto: ..." e o
// resumo que a pagina final mostra (placa ou processador).
procedure AoLerLinhaDoMotor(const S: String; const Error, FirstLine: Boolean);
var
  Linha: String;
begin
  Linha := TrimRight(S);
  Log('motor: ' + Linha);
  if Linha = '' then
    Exit;
  if Copy(Linha, 1, 3) = '== ' then
  begin
    if Copy(Linha, 4, 8) = 'Pronto: ' then
    begin
      Resumo := Copy(Linha, 12, Length(Linha));
      Resumo := Uppercase(Copy(Resumo, 1, 1)) + Copy(Resumo, 2, Length(Resumo)) + '.';
    end
    else
      WizardForm.StatusLabel.Caption := Copy(Linha, 4, Length(Linha));
    WizardForm.FilenameLabel.Caption := '';
  end
  else
    WizardForm.FilenameLabel.Caption := Linha;
  Terminal.Lines.Add(Linha);
  while Terminal.Lines.Count > LINHAS_NO_TERMINAL do
    Terminal.Lines.Delete(0);
  SendMessage(Terminal.Handle, WM_VSCROLL, SB_BOTTOM, 0);
end;

function MotorInstalado: Boolean;
begin
  Result := not MotorFalhou;
end;

// A pagina final diz o que o motor vai usar -- a pergunta que ficava sem
// resposta ("achou a minha placa?"). A lista de "abrir agora" desce junto,
// como o proprio Inno faz quando o texto cresce.
procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (Resumo <> '') then
  begin
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + Resumo;
    WizardForm.IncTopDecHeight(WizardForm.RunList,
      WizardForm.AdjustLabelHeight(WizardForm.FinishedLabel));
  end;
end;

// O desinstalador de uma instalacao que ja existe neste computador -- desta
// ou do tempo em que o programa se chamava Cortes (o AppId e o mesmo, entao a
// chave do registro e a mesma). Vazio se nao ha nenhuma.
function DesinstaladorExistente: String;
var
  Caminho: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, ExpandConstant(
       'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1'),
       'UninstallString', Caminho) then
  begin
    Caminho := RemoveQuotes(Caminho);
    if FileExists(Caminho) then
      Result := Caminho;
  end;
end;

// Abrir o instalador com o programa ja instalado pergunta o que fazer:
// reinstalar (o padrao -- e o que uma instalacao sem janela faz, porque ali
// ninguem escolhe) ou desinstalar. Os textos com acento vao por codigo de
// caractere: este arquivo e ASCII de proposito (ver o teste).
procedure InitializeWizard;
begin
  CriarTerminal;
  if DesinstaladorExistente = '' then
    Exit;
  PaginaDoQueFazer := CreateInputOptionPage(wpWelcome,
    'O Virtu Clips j' + #$E1 + ' est' + #$E1 + ' instalado neste computador',
    'O que voc' + #$EA + ' quer fazer?',
    'Nos dois casos, os seus projetos (os cortes que o programa j' + #$E1 +
      ' fez) ficam guardados.',
    True, False);
  PaginaDoQueFazer.Add('Reinstalar: conserta a instala' + #$E7 + #$E3 +
    'o e atualiza o motor');
  PaginaDoQueFazer.Add('Desinstalar: tira o programa deste computador');
  PaginaDoQueFazer.SelectedValueIndex := 0;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Codigo: Integer;
begin
  Result := True;
  if (PaginaDoQueFazer <> nil) and (CurPageID = PaginaDoQueFazer.ID) and
     (PaginaDoQueFazer.SelectedValueIndex = 1) then
  begin
    // O desinstalador pede a propria confirmacao e, antes de apagar, desliga
    // o ajudante; este instalador so sai do caminho.
    Exec(DesinstaladorExistente, '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
    Desinstalando := True;
    WizardForm.Close;
    Result := False;
  end;
end;

// Fechar para desinstalar nao e desistir: sem isto o Inno perguntaria se a
// pessoa quer mesmo cancelar a instalacao.
procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if Desinstalando then
    Confirm := False;
end;

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

// O `uv python install` da instalacao do erro 448 foi alem da pasta dela
// antes de morrer: registrou o Python no Windows (PEP 514) e pos um
// python3.11.exe na pasta de executaveis do uv -- e so depois tentou o atalho
// de pasta que o Windows recusou. Os dois apontam para Cortes\python, que o
// MigrarDoCortes apaga. `Alvo` e essa pasta, em minusculas; so sai o que
// aponta para ela, e um Python que a pessoa instalou pelo uv fica.
procedure ApagarRegistroDoUv(const Alvo: String);
var
  Empresa, Caminho: String;
  Versoes: TArrayOfString;
  I: Integer;
begin
  Empresa := 'Software\Python\Astral';
  if not RegGetSubkeyNames(HKCU, Empresa, Versoes) then
    Exit;
  for I := 0 to GetArrayLength(Versoes) - 1 do
    if RegQueryStringValue(HKCU, Empresa + '\' + Versoes[I] + '\InstallPath', '', Caminho) then
    begin
      if Pos('\\?\', Caminho) = 1 then
        Delete(Caminho, 1, 4);
      if Pos(Alvo, Lowercase(AddBackslash(Caminho))) = 1 then
      begin
        RegDeleteKeyIncludingSubkeys(HKCU, Empresa + '\' + Versoes[I]);
        Log('Registro do Python da instalacao antiga removido: ' + Versoes[I]);
      end;
    end;
  // A chave da empresa so tem nome e endereco: sem nenhum Python, sai.
  if RegGetSubkeyNames(HKCU, Empresa, Versoes) and (GetArrayLength(Versoes) = 0) then
    RegDeleteKeyIncludingSubkeys(HKCU, Empresa);
end;

// O lancador do uv e um .exe pequeno com o caminho do Python que ele abre
// escrito dentro: e por esse caminho que se sabe de quem ele e.
procedure ApagarLancadoresDoUv(const Pasta, Alvo: String);
var
  Nomes: TArrayOfString;
  Conteudo: AnsiString;
  Texto: String;
  I: Integer;
begin
  if Pasta = '' then
    Exit;
  SetArrayLength(Nomes, 3);
  Nomes[0] := 'python3.11.exe';
  Nomes[1] := 'python3.exe';
  Nomes[2] := 'python.exe';
  for I := 0 to GetArrayLength(Nomes) - 1 do
    if LoadStringFromFile(AddBackslash(Pasta) + Nomes[I], Conteudo) then
    begin
      Texto := String(Conteudo);
      if Pos(Alvo, Lowercase(Texto)) > 0 then
      begin
        DeleteFile(AddBackslash(Pasta) + Nomes[I]);
        Log('Lancador do Python da instalacao antiga removido: ' + AddBackslash(Pasta) + Nomes[I]);
      end;
    end;
end;

procedure LimparRestosDoUv;
var
  Alvo, PastaLocal: String;
begin
  Alvo := Lowercase(ExpandConstant('{localappdata}\Cortes\python\'));
  ApagarRegistroDoUv(Alvo);
  // Onde o uv poe os executaveis: a variavel dele, a do XDG ou a pasta
  // padrao. Olhar numa pasta a mais nao custa nada, pelo mesmo criterio.
  ApagarLancadoresDoUv(GetEnv('UV_PYTHON_BIN_DIR'), Alvo);
  ApagarLancadoresDoUv(GetEnv('XDG_BIN_HOME'), Alvo);
  if GetEnv('USERPROFILE') = '' then
    Exit;
  PastaLocal := GetEnv('USERPROFILE') + '\.local';
  ApagarLancadoresDoUv(PastaLocal + '\bin', Alvo);
  // So se ficaram vazias: quem as criou foi o uv da instalacao antiga.
  RemoveDir(PastaLocal + '\bin');
  RemoveDir(PastaLocal);
end;

// Instalar por cima de um ajudante aberto: desliga-o (e o motor) antes de a
// pasta de versoes ser apagada. Os restos do uv nao dependem da pasta antiga
// existir: quem desinstalou o Cortes pelo desinstalador dele ainda os tem.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  PararAjudante(ExpandConstant('{app}'));
  MigrarDoCortes;
  LimparRestosDoUv;
end;

// O `instalar.ps1`, escondido, com a saida no terminal da pagina de
// instalacao: a pessoa ve o passo, a barra andando e o que esta baixando. A
// instalacao so se declara pronta se o script terminou bem.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
  Parametros: String;
  Rodou: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    // A versao que o `iniciar.py` roda.
    SaveStringToFile(ExpandConstant('{app}\atual.txt'), '{#Versao}' + #13#10, False);
    WizardForm.StatusLabel.Caption :=
      'Instalando o motor: baixa algumas centenas de MB e leva alguns minutos.';
    WizardForm.FilenameLabel.Caption := '';
    // Sem porcentagem: o uv nao diz quanto falta. A barra so mostra que esta
    // andando; quanto falta, quem diz e o "Passo k de n".
    WizardForm.ProgressGauge.Style := npbstMarquee;
    MostrarTerminal;
    // -SemPausa sempre: escondido, ninguem apertaria o Enter da pausa do erro.
    Parametros := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\versoes\{#Versao}\ajudante\instalar.ps1') + '" -Base "' +
      ExpandConstant('{app}') + '" -SemPausa';
    // O PowerShell de 64 bits, pelo Sysnative. O Exec comum, num instalador de
    // 32 bits como este, abre o de 32 (o System32 vira SysWOW64), que nao ve o
    // nvidia-smi: a placa NVIDIA do notebook de um amigo do autor ficou de
    // fora assim (25-set-2026). O {sysnative} e o caminho que o Inno 6.7 tem;
    // o ExecAndLogOutputWithNativeSysDir so existe numa versao posterior.
    try
      Rodou := ExecAndLogOutput(
        ExpandConstant('{sysnative}\WindowsPowerShell\v1.0\powershell.exe'), Parametros,
        ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Codigo, @AoLerLinhaDoMotor);
    except
      Log(GetExceptionMessage);
      Rodou := False;
    end;
    WizardForm.ProgressGauge.Style := npbstNormal;
    WizardForm.ProgressGauge.Position := WizardForm.ProgressGauge.Max;
    if not Rodou or (Codigo <> 0) then
    begin
      MotorFalhou := True;
      WizardForm.ProgressGauge.State := npbsError;
      WizardForm.StatusLabel.Caption := 'A instala' + #$E7 + #$E3 + 'o do motor n' + #$E3 + 'o terminou.';
      // Suprimivel: no /VERYSILENT do CI uma caixa comum esperaria um clique
      // para sempre.
      // Nenhuma linha pode COMECAR com `#`: o pre-processador do Inno a le
      // como diretiva (`#13#10` virava "Unknown preprocessor directive").
      SuppressibleMsgBox('A instala' + #$E7 + #$E3 + 'o do motor n' + #$E3 + 'o terminou.' + #13#10 + #13#10 +
             'O registro est' + #$E1 + ' em ' + ExpandConstant('{app}\dados\logs\instalacao.log') + #13#10 +
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
