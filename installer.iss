; AAC Assistant - slim PyInstaller onedir installer.
; The application stores installed user data in %APPDATA%\AACAssistant.
; Portable copies keep data/, logs/, and uploads/ beside AAC_Assistant.exe.

#define MyAppName "AAC Assistant"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "AAC Assistant Team"
#define MyAppURL "https://github.com/your-repo/aac-assistant"
#define MyAppExeName "AAC_Assistant.exe"

[Setup]
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
OutputDir=dist
OutputBaseFilename=AAC_Assistant_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
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
