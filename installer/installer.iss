; installer.iss — PushAnything Inno Setup 安装脚本
; 构建：先跑 build.bat 生成 dist\PushAnything.exe，再用 ISCC 编译本脚本
;   "C:\Users\33836\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\installer.iss

#define AppName "PushAnything"
#define AppVersion "1.0.0"
#define AppExe "PushAnything.exe"
#define AppId "{{4D8C1F5B-AD6E-556B-9742-ECA33AB6E391}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
AppPublisherURL=https://github.com/
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\installer
OutputBaseFilename={#AppName}_Setup_{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\icon.ico
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chs"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载只删程序本体，不碰用户数据（drafts/profiles/assets/config/history 留在原位）
