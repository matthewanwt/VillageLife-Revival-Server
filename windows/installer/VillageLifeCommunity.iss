; Complete community test with the verified original game archive.
#ifndef StageDir
  #error Supply /DStageDir= when compiling
#endif

#ifdef PrivateCandidate
  #define AppIdentity "VillageLifeAuditPrivate"
  #define AppLabel "Village Life Private Audit Candidate"
  #define AppFolder "VillageLifeAuditPrivate"
  #define InstallerName "VillageLife-Private-Audit-Setup"
#else
  #define AppIdentity "VillageLifeCommunityTest"
  #define AppLabel "Village Life Community Test"
  #define AppFolder "VillageLifeCommunityTest"
  #define InstallerName "VillageLife-Community-0.4.1-Setup"
#endif
#ifndef OutputDir
  #error Supply /DOutputDir= when compiling
#endif

[Setup]
SetupIconFile=..\launcher\VillageLife.ico
AppId={#AppIdentity}
AppName={#AppLabel}
AppVersion=0.4.1
AppPublisher=Village Life Community Project
DefaultDirName={localappdata}\Programs\{#AppFolder}
DefaultGroupName={#AppLabel}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename={#InstallerName}
VersionInfoVersion=0.4.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile={#StageDir}\START-HERE.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
AppMutex=Local\VillageLifeLauncherActive

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppLabel}"; Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\StartVillageLife\VillageLifeLauncher.exe"; Description: "Open Village Life Community Test"; Flags: postinstall nowait skipifsilent
