; Village Life per-user installer, assembled only from a validated build stage.
; The original commercial APK/XAPK/OBB and player saves are NOT distributed.
; Build: ISCC.exe /DStageDir="C:\path\to\release-stage" VillageLife.iss
#ifndef StageDir
  #error Supply /DStageDir="C:\absolute\release-stage" when compiling
#endif
#define AppTitle "Village Life Revival"
#define AppVersion "2.11-compat-alpha"
[Setup]
AppId=VillageLifeCommunityRevival
AppName={#AppTitle}
AppVersion={#AppVersion}
AppPublisher=Village Life Community Project
DefaultDirName={localappdata}\Programs\VillageLifeRevival
DefaultGroupName=Village Life Revival
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=VillageLifeSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppTitle}
CloseApplications=no
RestartApplications=no
ChangesAssociations=no
UsePreviousAppDir=yes

[Files]
; Source tree must be reviewed and privacy-scanned before invoking ISCC.
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.xapk,*.apk,*.obb,*.sqlite,*.db,*.pfx,*.p12,*.private,play-settings.json,setup-network-check.json,latest-runtime-error.json,private_state\*,backups\*,experiments\*,support\*,analysis\private\*"

[Icons]
Name: "{autoprograms}\Village Life Revival"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Village Life Revival"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; Description: "Open Village Life Revival"; Flags: postinstall nowait skipifsilent

; Players supply their own supported XAPK through Set Up Game.
; The dedicated BlueStacks 5 Pie64 instance is not installed or modified by Inno Setup.
; No automatic firewall or VM network changes are made during installation.
; The app writes saves in its per-user install folder in this interim version.
; Production should migrate saves to a stable separate data location before major upgrades.
