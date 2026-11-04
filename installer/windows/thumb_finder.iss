#define MyAppName "Thumb Finder"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define MyAppPublisher "Thumb Finder"
#define MyAppExeName "Thumb-Finder.exe"

[Setup]
AppId={{A2A6B4B1-7C6E-4D0B-9D9A-123456789001}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher={#MyAppPublisher}
AppComments=Standalone desktop application with bundled Python runtime and dependencies.
DefaultDirName={autopf}\Thumb Finder
DefaultGroupName=Thumb Finder
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=Thumb-Finder-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\Thumb-Finder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Thumb Finder"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Thumb Finder"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Thumb Finder"; Flags: postinstall nowait skipifsilent
