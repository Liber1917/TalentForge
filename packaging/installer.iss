; TalentForge Windows 安装器（Inno Setup 6）
; 特点：用户可指定安装路径、开始菜单/桌面快捷方式、卸载器、安装后启动。
; 由 .github/workflows/build-windows.yml 在 windows-latest 上调用 iscc 编译。

#define MyAppName "TalentForge"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Liber1917"
#define MyAppExeName "talentforge.exe"

[Setup]
AppId={{8F3C2A1E-7D5B-4C6A-9E2F-5B8A1C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; 单用户安装到 AppData（无需管理员权限，小白双击直接装）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; iscc 从仓库根调用（workflow: iscc packaging/installer.iss），路径相对仓库根
OutputDir=dist
OutputBaseFilename=TalentForgeSetup-{#MyAppVersion}
; 图标：可选。放 packaging\icon.ico 后取消下一行注释即可带安装器图标。
; SetupIconFile=packaging\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; 注：Inno Setup 默认安装不含中文语言文件（ChineseSimplified.isl 需手动下载到 Languages 目录）。
; 分发版先用英文（compiler:Default.isl 内置，无需外部文件）；后续要中文向导可把
; ChineseSimplified.isl 放进仓库并在 CI 里拷到 Inno 安装目录。
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动 TalentForge"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 主程序 + 数据目录（运行时创建）
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 开机自启（autostart 任务勾选时写入 HKCU，无需管理员）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清理运行时数据目录（用户数据在 %APPDATA%\TalentForge，见 data 迁移——暂不删用户数据，只删程序目录）
Type: filesandordirs; Name: "{app}\data"
