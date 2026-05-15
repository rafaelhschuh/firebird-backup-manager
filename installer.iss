; Inno Setup 6 — FB Backup Manager Installer
; Compilar com: iscc installer.iss

#define AppName      "FB Backup Manager"
#define AppVersion   "1.0.0"
#define AppPublisher "FB Backup Manager"
#define AppURL       "http://localhost:8099"
#define AppExeName   "fb_backup_manager.exe"
#define ServiceName  "FBBackupManager"

[Setup]
AppId={{A3F7B2C1-4D8E-4A9F-B6C2-1E5D3F8A2B7C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={autopf}\FBBackupManager
DefaultGroupName={#AppName}
AllowNoIcons=no
OutputDir=dist
OutputBaseFilename=FBBackupManager_Setup_{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\fb_backup_manager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs; Tasks: ""

[Dirs]
Name: "{app}\data"; Permissions: authusers-modify

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} - Interface Web"; Filename: "{app}\open_ui.url"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\open_ui.url"; Tasks: desktopicon

[INIFile]
Filename: "{app}\open_ui.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8099"

[Run]
; Para o serviço antes de atualizar (ignorar erro se não existir)
Filename: "net"; Parameters: "stop {#ServiceName}"; Flags: runhidden waituntilterminated; StatusMsg: "Parando serviço anterior…"; Check: ServiceExists
; Remove banco antigo em atualizações (schema mudou)
Filename: "{cmd}"; Parameters: "/C del /F /Q ""{app}\data\fb_backup.db"""; Flags: runhidden waituntilterminated; StatusMsg: "Limpando banco de dados…"
; Instala e inicia o serviço Windows
Filename: "{app}\{#AppExeName}"; Parameters: "--service install"; Flags: runhidden waituntilterminated; StatusMsg: "Instalando serviço Windows…"
; Configura senha do administrador (cria tabelas + define hash antes de iniciar o serviço)
Filename: "{app}\{#AppExeName}"; Parameters: "--admin-password ""{code:GetAdminPwd}"""; Flags: runhidden waituntilterminated; StatusMsg: "Configurando senha do administrador…"
Filename: "net"; Parameters: "start {#ServiceName}"; Flags: runhidden waituntilterminated; StatusMsg: "Iniciando serviço…"
; Abre a interface web ao final da instalação
Filename: "{#AppURL}"; Description: "Abrir interface web do {#AppName}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallRun]
Filename: "net"; Parameters: "stop {#ServiceName}"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "{app}\{#AppExeName}"; Parameters: "--service remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"

[Code]
var
  AdminPwdPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  AdminPwdPage := CreateInputQueryPage(
    wpSelectDir,
    'Senha do Administrador',
    'Defina a senha de acesso à interface web',
    'Esta senha será solicitada ao abrir o FB Backup Manager no navegador.'
  );
  AdminPwdPage.Add('Senha:', True);
  AdminPwdPage.Add('Confirmar senha:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Pwd, Confirm: String;
begin
  Result := True;
  if CurPageID = AdminPwdPage.ID then
  begin
    Pwd     := AdminPwdPage.Values[0];
    Confirm := AdminPwdPage.Values[1];
    if Length(Pwd) < 4 then
    begin
      MsgBox('A senha deve ter pelo menos 4 caracteres.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Pos('"', Pwd) > 0 then
    begin
      MsgBox('A senha não pode conter aspas duplas (").', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if Pwd <> Confirm then
    begin
      MsgBox('As senhas não coincidem. Por favor, repita a senha.', mbError, MB_OK);
      AdminPwdPage.Values[1] := '';
      Result := False;
      Exit;
    end;
  end;
end;

function GetAdminPwd(Param: String): String;
begin
  Result := AdminPwdPage.Values[0];
end;

function ServiceExists(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('sc.exe', 'query {#ServiceName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    Sleep(2000);
end;
