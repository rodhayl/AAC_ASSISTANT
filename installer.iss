; AAC Assistant - Inno Setup Installer Script
; This creates a professional Windows installer for the packaged application

#define MyAppName "AAC Assistant"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "AAC Assistant Team"
#define MyAppURL "https://github.com/your-repo/aac-assistant"
#define MyAppExeName "AAC_Assistant.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; Output settings
OutputDir=dist
OutputBaseFilename=AAC_Assistant_Setup_{#MyAppVersion}
; SetupIconFile requires .ico format - uncomment and add icon.ico if available
; SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Require admin for Program Files installation
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
; Architecture
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Uninstall settings
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main application (one-folder PyInstaller output)
Source: "dist\AAC_Assistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Additional files
Source: "env.properties.example"; DestDir: "{app}"; DestName: "env.properties"; Flags: onlyifdoesntexist
; Ensure data directory exists
Source: "data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.db"

[Dirs]
; Create writable directories for user data
Name: "{app}\data"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify
Name: "{app}\uploads"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Option to launch app after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Custom code for first-run setup

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Create necessary directories
    DataDir := ExpandConstant('{app}\data');
    if not DirExists(DataDir) then
      CreateDir(DataDir);
      
    DataDir := ExpandConstant('{app}\logs');
    if not DirExists(DataDir) then
      CreateDir(DataDir);
      
    DataDir := ExpandConstant('{app}\uploads');
    if not DirExists(DataDir) then
      CreateDir(DataDir);
  end;
end;

[Messages]
; Custom messages
WelcomeLabel2=This will install [name/ver] on your computer.%n%nAAC Assistant is a communication tool for people who need augmentative and alternative communication support.%n%nIt is recommended that you close all other applications before continuing.

[UninstallDelete]
; Clean up logs on uninstall (preserve user data)
Type: filesandordirs; Name: "{app}\logs"
