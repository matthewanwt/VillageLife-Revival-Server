; NEW BACKEND ONLY - no 2.11 runtime or legacy server, no APK bundled.
#ifndef StageDir
  #error Supply /DStageDir= when compiling
#endif
#define AppTitle "Village Life | New Backend Test Manager"
#define AppVersion "0.2.0-alpha"
[Setup]
AppId=VillageLifeNextBackendManager
AppName={#AppTitle}
AppVersion={#AppVersion}
AppPublisher=Village Life Community Project
DefaultDirName={localappdata}\Programs\VillageLifeNextBackend
DefaultGroupName=Village Life Backend Test
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=VillageLife-NextBackend-TestSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
CloseApplications=no
[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.xapk,*.apk,*.obb,*.sqlite,*.sqlite3,*.db,*.pfx,*.p12,play-settings.json,bluestacks-binding.json,legacy_reference\*,private_state\*,backups\*"
[Icons]
Name: "{autoprograms}\Village Life New Backend Test"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; Description: "Open new-backend test manager"; Flags: postinstall nowait skipifsilent
; Saves live in %LOCALAPPDATA%\VillageLifeRevivalNext and are not uninstalled.
; Separate from historical 2.11 installation. No BlueStacks/Windows firewall changes.
