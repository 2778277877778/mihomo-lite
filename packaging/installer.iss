; Inno Setup script for Mihomo Lite (x64, onedir payload).
; Build first:  python scripts/build_windows.py
; Then run:     ISCC.exe packaging\installer.iss

#define MyAppName "Mihomo Lite"
#define MyAppVersion "0.4.2"
#define MyAppPublisher "Mihomo Lite contributors"
#define MyAppExeName "MihomoLite.exe"
#define MyAppId "{{7B6D3A2E-9C41-4E77-9A2B-1F3C5D8E6A10}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Mihomo Lite
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
WizardStyle=modern
OutputDir=output
OutputBaseFilename=MihomoLite-Setup-{#MyAppVersion}-x64
SetupIconFile=..\src\mihomo_lite\resources\icons\app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start Mihomo Lite with Windows"; GroupDescription: "Startup"; Flags: unchecked

[Files]
Source: "..\dist\MihomoLite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--hidden"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Ask the running copy to restore the system proxy before it exits, then make sure
; it is really gone (a hard kill without the first step would leave the proxy dangling).
Filename: "{app}\{#MyAppExeName}"; Parameters: "--shutdown"; Flags: runhidden waituntilterminated; RunOnceId: "StopApp"
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillAppOnce"
