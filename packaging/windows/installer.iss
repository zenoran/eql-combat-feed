#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define AppName "EQL Combat Feed"
#define AppExeName "EQL Combat Feed.exe"
#define AppPublisher "zenoran"
#define AppURL "https://github.com/zenoran/eql-combat-feed"

[Setup]
AppId={{1D82BC9E-F793-4FAE-BEBC-AFF5B3C892A4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\EQL Combat Feed
DefaultGroupName=EQL Combat Feed
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=EQL-Combat-Feed-Setup-{#AppVersion}
SetupIconFile=..\..\assets\icons\eql-combat-feed.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "autostart"; Description: "Start EQL Combat Feed when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\..\dist\EQL Combat Feed\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\EQL Combat Feed"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\EQL Combat Feed"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\EQL Combat Feed"; Filename: "{app}\{#AppExeName}"; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch EQL Combat Feed"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
