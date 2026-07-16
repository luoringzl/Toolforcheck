#define MyAppName "核验工具"
#define MyAppVersion "0.2.4"
#define MyAppPublisher "离线核验工具"
#define MyAppExeName "OfflinePersonnelVerifier.exe"

[Setup]
SourceDir=..\..
AppId={{CB91BBD9-211B-42C8-86D5-6018F2A02FA7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\核验工具
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist-installer
OutputBaseFilename=核验工具_安装包_v0.2.4
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "dist\核验工具\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "sample_company_registry.csv"; DestDir: "{app}\示例"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent
