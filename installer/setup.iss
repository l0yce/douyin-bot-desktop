#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef SourceArchive
  #error SourceArchive is required
#endif
#ifndef OutputDirPath
  #define OutputDirPath "..\release"
#endif
#ifndef AppRelease
  #define AppRelease "2026.10.12"
#endif

[Setup]
AppId={{97D734E5-7CF4-4D90-84CC-2A7A2E77CC79}
AppName=抖音 AI 好友助手
AppVersion={#AppRelease}
VersionInfoVersion={#AppRelease}.0
DefaultDirName={localappdata}\Programs\DouyinBotDesktop
DefaultGroupName=抖音 AI 好友助手
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDirPath}
OutputBaseFilename=DouyinBot-Setup-{#AppRelease}
SetupIconFile=..\app\ui\assets\app-icon.ico
UninstallDisplayIcon={app}\douyin-bot-desktop.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
UninstallDisplayName=抖音 AI 好友助手

[Languages]
Name: "zhcn"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceArchive}"; DestDir: "{app}\source"; Flags: ignoreversion

[Icons]
Name: "{group}\抖音 AI 好友助手"; Filename: "{app}\douyin-bot-desktop.exe"; WorkingDir: "{app}"; AppUserModelID: "DouyinBot.Desktop"
Name: "{group}\卸载抖音 AI 好友助手"; Filename: "{uninstallexe}"
Name: "{autodesktop}\抖音 AI 好友助手"; Filename: "{app}\douyin-bot-desktop.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "DouyinBot.Desktop"

[Run]
Filename: "{app}\douyin-bot-desktop.exe"; Description: "打开抖音 AI 好友助手"; Flags: nowait postinstall skipifsilent

[Code]
function AppStopped: Boolean;
var
  Locator, Services, Processes: Variant;
begin
  Result := False;
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Processes := Services.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name = ''douyin-bot-desktop.exe''');
    Result := Processes.Count = 0;
    if not Result then
      MsgBox('程序仍在运行。请右键系统托盘图标选择“退出”，再重新运行安装或卸载程序。关闭主窗口只会缩到托盘。', mbInformation, MB_OK);
  except
    MsgBox('无法检查程序是否已退出。请确认 Windows Management Instrumentation 服务正常，然后重试。', mbError, MB_OK);
  end;
end;

function InitializeSetup: Boolean;
begin
  Result := AppStopped;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not AppStopped then
    Result := '请先从系统托盘完全退出抖音 AI 好友助手。';
end;

function InitializeUninstall: Boolean;
begin
  Result := AppStopped;
end;
