; RELIABILITY TEST ONLY - the new backend and user-supplied test assets.
#ifndef StageDir
  #error Supply /DStageDir= when compiling
#endif
#ifndef OutputDir
  #error Supply /DOutputDir= when compiling
#endif
#define AppTitle "Village Life | Reliability Test"
#define AppVersion "0.3.1-test"
[Setup]
AppId=VillageLifeReliabilityTest
AppName={#AppTitle}
AppVersion={#AppVersion}
AppPublisher=Village Life Community Project - Private Test
DefaultDirName={localappdata}\Programs\VillageLifeReliabilityTest
DefaultGroupName=Village Life Reliability Test
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=VillageLife-ReliabilityTest-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile={#StageDir}\TEST-READ-ME.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=no
CloseApplications=no
[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.apk,*.obb,*.db,*.pfx,*.p12,play-settings.json,bluestacks-binding.json,state.sqlite3,private_state\*,backups\*"
[Icons]
Name: "{autoprograms}\Village Life Reliability Test"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; Description: "Open Village Life Reliability Test"; Flags: postinstall nowait skipifsilent
; Saves and per-tester signing identity live in %LOCALAPPDATA%\VillageLifeRevivalNext.
; No old server fallback and no BlueStacks/Windows firewall changes.
