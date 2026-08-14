; AAC Assistant - slim PyInstaller onedir installer.
; The application stores installed user data in %APPDATA%\AACAssistant.
; Portable copies keep data/, logs/, and uploads/ beside AAC_Assistant.exe.

#define MyAppName "AAC Assistant"
#define MyAppVersion "2.0.0"
#define MyAppId "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}"
#define MyAppPublisher "AAC Assistant Team"
#define MyAppURL "https://github.com/rodhayl/AAC_ASSISTANT"
#define MyAppExeName "AAC_Assistant.exe"
#define MyAppProcessName "AAC_Assistant"

[Setup]
AppId={{#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=AAC_Assistant_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; The windowless PyInstaller launcher can keep the executable locked during an upgrade.
; Force Inno Setup to close only applications using the files being replaced.
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Complete PyInstaller onedir output, including frontend and bundled resources.
Source: "dist\AAC_Assistant\*"; DestDir: "{app}"; Excludes: "data\*;logs\*;uploads\*;*.env"; Flags: ignoreversion recursesubdirs createallsubdirs
; The launcher copies this template to the writable runtime root on first run.
Source: ".env.example"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Dirs]
; These directories support portable copies and are intentionally not removed.
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\uploads"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Application logs are disposable. User database, uploads, and portable data remain.
Type: filesandordirs; Name: "{app}\logs"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nAAC Assistant is a communication tool for people who need augmentative and alternative communication support.%n%nInstalled runs may require UAC approval. User data is preserved when the app is uninstalled.

[CustomMessages]
english.UpdateCaption=Update AAC Assistant to version {#MyAppVersion}
english.UpdateWelcomeTitle=Update AAC Assistant
english.UpdateWelcome=An existing AAC Assistant installation was found.%n%nThis will update the application to version {#MyAppVersion}. Save your work and close the app before continuing; unsaved work may be lost. Your settings, database, and uploaded files will be preserved.
spanish.UpdateCaption=Actualizar AAC Assistant a la versión {#MyAppVersion}
spanish.UpdateWelcomeTitle=Actualizar AAC Assistant
spanish.UpdateWelcome=Se ha encontrado una instalación existente de AAC Assistant.%n%nEsta operación actualizará la aplicación a la versión {#MyAppVersion}. Guarda tu trabajo y cierra la aplicación antes de continuar; podrías perder el trabajo no guardado. Se conservarán tus ajustes, la base de datos y los archivos subidos.
english.CloseFailed=The existing AAC Assistant process could not be closed. Close it manually and try again.
spanish.CloseFailed=No se pudo cerrar el proceso existente de AAC Assistant. Ciérralo manualmente y vuelve a intentarlo.

[Code]
const
  EVENT_MODIFY_STATE = $0002;

var
  DefaultCaption: String;
  DefaultWelcomeTitle: String;
  DefaultWelcomeMessage: String;

function OpenEvent(dwDesiredAccess: Cardinal; bInheritHandle: Boolean; lpName: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(hEvent: THandle): Boolean;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function ShutdownEventName(const AppPath: String): String;
begin
  Result := 'Local\AACAssistantShutdown_' +
    Copy(GetSHA256OfString(Lowercase(AppPath)), 1, 32);
end;

function RequestGracefulShutdown(const AppPath: String): Boolean;
var
  EventHandle: THandle;
begin
  EventHandle := OpenEvent(EVENT_MODIFY_STATE, False, ShutdownEventName(AppPath));
  Result := EventHandle <> 0;
  if Result then
  begin
    Result := SetEvent(EventHandle);
    CloseHandle(EventHandle);
  end;
end;

// Returns the directory of an existing AAC Assistant installation, or '' when
// none is found. Checks the wizard-selected directory, the registered previous
// install (per-user and per-machine), and the standard default locations.
function ExistingInstallationPath(): String;
var
  AppPath: String;
  PrevPath: String;
  UninstallKey: String;
begin
  Result := '';
  // 1) The directory currently selected in the wizard.
  AppPath := AddBackslash(WizardForm.DirEdit.Text) + '{#MyAppExeName}';
  if FileExists(AppPath) then
  begin
    Result := WizardForm.DirEdit.Text;
    Exit;
  end;
  // 2) Previous installation registered by this or an earlier version.
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';
  if RegQueryStringValue(HKCU, UninstallKey, 'Inno Setup: App Path', PrevPath) then
  begin
    if FileExists(AddBackslash(PrevPath) + '{#MyAppExeName}') then
    begin
      Result := PrevPath;
      Exit;
    end;
  end;
  if RegQueryStringValue(HKLM, UninstallKey, 'Inno Setup: App Path', PrevPath) then
  begin
    if FileExists(AddBackslash(PrevPath) + '{#MyAppExeName}') then
    begin
      Result := PrevPath;
      Exit;
    end;
  end;
  // 3) Standard default locations (per-machine and per-user).
  AppPath := ExpandConstant('{autopf}\{#MyAppName}\{#MyAppExeName}');
  if FileExists(AppPath) then
  begin
    Result := ExtractFilePath(AppPath);
    Exit;
  end;
  AppPath := ExpandConstant('{localappdata}\Programs\{#MyAppName}\{#MyAppExeName}');
  if FileExists(AppPath) then
  begin
    Result := ExtractFilePath(AppPath);
    Exit;
  end;
end;

function ExistingInstallationSelected(): Boolean;
begin
  Result := ExistingInstallationPath() <> '';
end;

procedure UpdateWelcomeMessage;
begin
  if ExistingInstallationSelected() then
  begin
    WizardForm.Caption := CustomMessage('UpdateCaption');
    WizardForm.WelcomeLabel1.Caption := CustomMessage('UpdateWelcomeTitle');
    WizardForm.WelcomeLabel2.Caption := CustomMessage('UpdateWelcome');
  end
  else
  begin
    WizardForm.Caption := DefaultCaption;
    WizardForm.WelcomeLabel1.Caption := DefaultWelcomeTitle;
    WizardForm.WelcomeLabel2.Caption := DefaultWelcomeMessage;
  end;
end;

procedure DirEditChanged(Sender: TObject);
begin
  UpdateWelcomeMessage();
end;

procedure InitializeWizard;
begin
  DefaultCaption := WizardForm.Caption;
  DefaultWelcomeTitle := WizardForm.WelcomeLabel1.Caption;
  DefaultWelcomeMessage := WizardForm.WelcomeLabel2.Caption;
  WizardForm.DirEdit.OnChange := @DirEditChanged;
  UpdateWelcomeMessage();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then
    UpdateWelcomeMessage();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  AppPath: String;
  PowerShellPath: String;
  PowerShellArgs: String;
begin
  Result := '';
  NeedsRestart := False;
  if ExistingInstallationSelected() then
  begin
    // The frozen launcher is windowless, so Restart Manager may not close it.
    // Filter by the selected installation path so portable or other-user
    // instances of the same executable are never terminated.
    AppPath := AddBackslash(WizardForm.DirEdit.Text) + '{#MyAppExeName}';
    StringChangeEx(AppPath, '''', '''''', True);
    RequestGracefulShutdown(AppPath);
    PowerShellPath := ExpandConstant(
      '{sys}\\WindowsPowerShell\\v1.0\\powershell.exe'
    );
    PowerShellArgs :=
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ' +
      '"$target = [IO.Path]::GetFullPath(''' + AppPath + '''); ' +
      '$deadline = [DateTime]::UtcNow.AddSeconds(25); ' +
      'do { $processes = @(Get-Process -Name ''{#MyAppProcessName}'' ' +
      '-ErrorAction SilentlyContinue | Where-Object { $_.Path -and ' +
      '([IO.Path]::GetFullPath($_.Path) -ieq $target) }); ' +
      'if ($processes.Count -eq 0) { exit 0 }; ' +
      'Start-Sleep -Milliseconds 250 } while ([DateTime]::UtcNow -lt $deadline); ' +
      '$processes | Stop-Process -Force; Start-Sleep -Milliseconds 500; ' +
      'if (Get-Process -Name ''{#MyAppProcessName}'' -ErrorAction SilentlyContinue ' +
      '| Where-Object { $_.Path -and ([IO.Path]::GetFullPath($_.Path) ' +
      '-ieq $target) }) { exit 1 }"';
    if (not Exec(
      PowerShellPath,
      PowerShellArgs,
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    )) or (ResultCode <> 0) then
    begin
      Result := CustomMessage('CloseFailed');
      Exit;
    end;
  end;
end;
