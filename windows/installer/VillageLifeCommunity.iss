; Complete community test with the verified original game archive.
#ifndef StageDir
  #error Supply /DStageDir= when compiling
#endif
#ifndef OutputDir
  #error Supply /DOutputDir= when compiling
#endif

[Setup]
AppId=VillageLifeCommunityTest
AppName=Village Life Community Test
AppVersion=0.2.88
AppPublisher=Village Life Community Project
DefaultDirName={localappdata}\Programs\VillageLifeCommunityTest
DefaultGroupName=Village Life Community Test
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=VillageLife-Community-0.2.88-Part-II-of-III-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile={#StageDir}\START-HERE.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Village Life Community Test"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; Description: "Open Village Life Community Test"; Flags: postinstall nowait skipifsilent
