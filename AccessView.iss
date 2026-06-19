#define MyAppName "AccessView"
#define MyAppVersion "0.10.1"
#define MyAppPublisher "Click's da Serra"
#define MyAppExeName "AccessView.exe"
#define InstallerPassword GetEnv("ACCESSVIEW_INSTALLER_PASSWORD")

[Setup]
AppId={{B75D745C-DB2B-4EF4-A1FC-0827DD55A52E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AlwaysUsePersonalGroup=no
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=AccessView-Setup-v{#MyAppVersion}
SetupIconFile=AccessView.ico
UninstallDisplayIcon={app}\AccessView.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
#if Len(InstallerPassword) > 0
Password={#InstallerPassword}
Encryption=yes
EncryptionKeyDerivation=pbkdf2/220000
#endif
CloseApplications=yes
RestartApplications=no
ChangesAssociations=no
VersionInfoVersion=0.10.1.0
VersionInfoProductName={#MyAppName}
VersionInfoDescription=Navegador seguro somente leitura para compartilhamentos Samba
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright=Desenvolvido por Raphael Alves

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\AccessView\*"; DestDir: "{app}"; Excludes: "config.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{commonprograms}\AccessView\AccessView"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AccessView.ico"
Name: "{commondesktop}\AccessView"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AccessView.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o AccessView"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ServerPage: TInputQueryWizardPage;

function JsonEscape(Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
  StringChangeEx(Result, #13, '', True);
  StringChangeEx(Result, #10, '', True);
end;

function IsValidIPv4(Value: String): Boolean;
var
  Remaining: String;
  Part: String;
  DotPosition: Integer;
  PartValue: Integer;
  PartCount: Integer;
begin
  Result := False;
  Remaining := Trim(Value);
  PartCount := 0;

  while Remaining <> '' do
  begin
    DotPosition := Pos('.', Remaining);
    if DotPosition > 0 then
    begin
      Part := Copy(Remaining, 1, DotPosition - 1);
      Delete(Remaining, 1, DotPosition);
    end
    else
    begin
      Part := Remaining;
      Remaining := '';
    end;

    if (Part = '') or (Length(Part) > 3) then
      Exit;

    PartValue := StrToIntDef(Part, -1);
    if (PartValue < 0) or (PartValue > 255) then
      Exit;

    PartCount := PartCount + 1;
    if PartCount > 4 then
      Exit;
  end;

  Result := PartCount = 4;
end;

function BuildSharesJson(Value: String): String;
var
  Remaining: String;
  ShareName: String;
  SeparatorPosition: Integer;
begin
  Result := '';
  Remaining := Value;

  while Remaining <> '' do
  begin
    SeparatorPosition := Pos(',', Remaining);
    if SeparatorPosition > 0 then
    begin
      ShareName := Trim(Copy(Remaining, 1, SeparatorPosition - 1));
      Delete(Remaining, 1, SeparatorPosition);
    end
    else
    begin
      ShareName := Trim(Remaining);
      Remaining := '';
    end;

    if ShareName <> '' then
    begin
      if Result <> '' then
        Result := Result + ',' + #13#10;
      Result := Result + '    "' + JsonEscape(ShareName) + '"';
    end;
  end;
end;

function SharesAreValid(Value: String): Boolean;
var
  Remaining: String;
  ShareName: String;
  SeparatorPosition: Integer;
  ShareCount: Integer;
begin
  Result := False;
  Remaining := Value;
  ShareCount := 0;

  while Remaining <> '' do
  begin
    SeparatorPosition := Pos(',', Remaining);
    if SeparatorPosition > 0 then
    begin
      ShareName := Trim(Copy(Remaining, 1, SeparatorPosition - 1));
      Delete(Remaining, 1, SeparatorPosition);
    end
    else
    begin
      ShareName := Trim(Remaining);
      Remaining := '';
    end;

    if ShareName <> '' then
    begin
      if (Pos('\', ShareName) > 0) or (Pos('/', ShareName) > 0) then
        Exit;
      ShareCount := ShareCount + 1;
    end;
  end;

  Result := ShareCount > 0;
end;

procedure InitializeWizard;
begin
  ServerPage :=
    CreateInputQueryPage(
      wpSelectDir,
      'Configuração do servidor',
      'Defina qual servidor esta instalação acessará.',
      'Informe o nome exibido, o IP Tailnet e os nomes exatos dos compartilhamentos Samba.'
    );

  ServerPage.Add('Nome do servidor:', False);
  ServerPage.Add('IP Tailnet do servidor:', False);
  ServerPage.Add('Compartilhamentos (separados por vírgula):', False);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result :=
    (PageID = ServerPage.ID) and
    FileExists(ExpandConstant('{app}\config.json'));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = ServerPage.ID then
  begin
    if Trim(ServerPage.Values[0]) = '' then
    begin
      MsgBox('Informe o nome do servidor.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not IsValidIPv4(ServerPage.Values[1]) then
    begin
      MsgBox('Informe um endereço IPv4 válido para o servidor Tailnet.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not SharesAreValid(ServerPage.Values[2]) then
    begin
      MsgBox(
        'Informe pelo menos um compartilhamento Samba.' + #13#10 + #13#10 +
        'Use somente os nomes, separados por vírgula. Exemplo:' + #13#10 +
        'BACKUP-2026, SERVER-FILES',
        mbError,
        MB_OK
      );
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigContent: String;
  ConfigPath: String;
  ConfigLines: TArrayOfString;
begin
  if (CurStep = ssPostInstall) and
     (not FileExists(ExpandConstant('{app}\config.json'))) then
  begin
    ConfigContent :=
      '{' + #13#10 +
      '  "server_ip": "' + JsonEscape(Trim(ServerPage.Values[1])) + '",' + #13#10 +
      '  "shares": [' + #13#10 +
      BuildSharesJson(ServerPage.Values[2]) + #13#10 +
      '  ],' + #13#10 +
      '  "display_name": "' + JsonEscape(Trim(ServerPage.Values[0])) + '",' + #13#10 +
      '  "port": 445,' + #13#10 +
      '  "connection_timeout": 8,' + #13#10 +
      '  "skip_dfs": true,' + #13#10 +
      '  "auth_protocol": "ntlm"' + #13#10 +
      '}' + #13#10;

    ConfigPath := ExpandConstant('{app}\config.json');
    SetArrayLength(ConfigLines, 1);
    ConfigLines[0] := ConfigContent;
    if not SaveStringsToUTF8FileWithoutBOM(ConfigPath, ConfigLines, False) then
      RaiseException('Não foi possível criar o arquivo de configuração: ' + ConfigPath);
  end;
end;
