# Builds an explicitly labelled private reliability-test installer.
# Run in PowerShell on Windows with Python/.venv + PyInstaller, .NET 10 SDK,
# Inno Setup 6. All outputs are kept separate from the repository and old saves.
[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$StageFolder = "",
    [string]$IsccPath = "",
    [string]$OutputFolder = (Join-Path $env:USERPROFILE 'Desktop\VillageLife-ReliabilityTest-Handoff-Updated'),
    [string]$JavaHome = (Join-Path $env:USERPROFILE 'Downloads\openjdk-27.0.1.0.3_windows-x64_bin\jdk-27.0.1.0.3')
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $PythonPath) { $PythonPath = Join-Path $repo '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Missing project Python .venv. Run: py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e . pyinstaller'
}
if (-not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\keytool.exe') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\jarsigner.exe') -PathType Leaf)) {
    throw 'A JDK with keytool.exe and jarsigner.exe is required. Pass its folder with -JavaHome.'
}
$assets = Join-Path $repo 'private-assets'
foreach ($name in @('game_tables.sqlite','obb_tcf.inventory.csv')) {
    if (-not (Test-Path -LiteralPath (Join-Path $assets $name) -PathType Leaf)) {
        throw "Missing private test data: private-assets\$name"
    }
}
$xapks = @(Get-ChildItem -LiteralPath $assets -Filter '*.xapk' -File)
if ($xapks.Count -ne 1) { throw 'private-assets must contain exactly one XAPK for this reliability test build.' }
if (-not $StageFolder) { $StageFolder = Join-Path $env:TEMP ('VillageLife-NextTest-'+(Get-Date -Format 'yyyyMMddHHmmssfff')) }
$stage = [System.IO.Path]::GetFullPath($StageFolder)
if (Test-Path -LiteralPath $stage) { throw "Stage already exists: $stage" }
if ($stage.StartsWith($repo+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build stage must be OUTSIDE the repository.'
}
$outputPath = [System.IO.Path]::GetFullPath($OutputFolder)
if ($outputPath.StartsWith($repo+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer output must be OUTSIDE the repository.'
}
if (Test-Path -LiteralPath $outputPath) { throw "Refusing to overwrite existing handoff output: $outputPath" }
$null = Get-Command dotnet -ErrorAction Stop
& $PythonPath -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw 'Install PyInstaller in .venv: .\.venv\Scripts\python.exe -m pip install pyinstaller' }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$backendDist = Join-Path $stage 'bin'
$pyWork = Join-Path $stage 'pyinstaller-work'
$spec = Join-Path $stage 'spec'
& $PythonPath -m PyInstaller --noconfirm --clean --onedir --console --name VillageLifeServer `
    --paths (Join-Path $repo 'src') --collect-submodules villagelife `
    --add-data ((Join-Path $repo 'tools/prepare_original_client.py')+';tools') `
    --distpath $backendDist --workpath $pyWork --specpath $spec `
    (Join-Path $repo 'windows/installer/new_backend_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'New Python backend bundling failed' }
if (-not (Test-Path -LiteralPath (Join-Path $backendDist 'VillageLifeServer/VillageLifeServer.exe'))) {
    throw 'NEW backend executable is missing from the build output'
}
$publish = Join-Path $stage 'StartVillageLife'
& dotnet publish (Join-Path $repo 'windows/launcher/VillageLifeLauncher.csproj') -c Release `
    -r win-x64 --self-contained true -p:PublishSingleFile=false -o $publish
if ($LASTEXITCODE -ne 0) { throw 'C# test manager publish failed' }
if (-not (Test-Path -LiteralPath (Join-Path $publish 'VillageLifeLauncher.exe'))) {
    throw 'C# test manager executable was not published'
}
# Include the user's supplied test resources and JDK signing tools. The OBB
# is extracted from the bundled XAPK on first setup, avoiding a second 450 MB
# copy inside the installer. Nothing is copied into the source repository.
$packagedAssets = Join-Path $stage 'private-assets'
New-Item -ItemType Directory -Path $packagedAssets -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $assets 'game_tables.sqlite'),(Join-Path $assets 'obb_tcf.inventory.csv'),$xapks[0].FullName -Destination $packagedAssets
$signer = Join-Path $stage 'signing-tools\jdk'
New-Item -ItemType Directory -Path $signer -Force | Out-Null
Copy-Item -Path (Join-Path $JavaHome '*') -Destination $signer -Recurse -Force
if (-not (Test-Path -LiteralPath (Join-Path $signer 'legal\java.base\LICENSE'))) {
    throw 'The bundled JDK legal notices are missing; refusing to package the signer.'
}
# Generated build intermediates never go into the installer.
Remove-Item -LiteralPath $pyWork,$spec -Recurse -Force
@'
VILLAGE LIFE RELIABILITY TEST BUILD - NOT A FINISHED OR FIXED GAME.

This private handoff installer includes the new backend, launcher, this test
build's XAPK and local game-table data, plus the JDK tools used to sign the
prepared Android copy. It does not include or invoke the old 2.11 server.
It contains proprietary original game files; give it only to the intended
private tester and do not post it publicly. The Windows installer itself has
no Authenticode publisher signature, so Windows may show an unknown-publisher
warning.

FIRST USE
1. Install BlueStacks 5 and create a dedicated Pie64 instance in Multi-instance
   Manager. Do not use an instance containing saves you need to keep.
2. Install this test build and open Village Life Reliability Test from Start.
3. In the launcher, choose Set Up Game and select that dedicated instance.
   Confirm the warning. Setup extracts the OBB from the bundled XAPK, creates
   a separate locally signed APK in Local AppData, and installs it to only
   the selected instance. Setup can take several minutes.
4. Choose Play / Restart. Use Advanced diagnostics to export a safe
   missing-requests report when the game fails, then send that report to the
   project maintainer.

KNOWN LIMITS
This build is for reliability testing because gameplay is still failing.
Some game actions and shelter layouts are incomplete. A dedicated Pie64
instance is required. Network isolation has not been certified. Replacing an
existing original-signed Android app can erase its app data; back it up first.
Saves, local signing identity and prepared files stay in
%LOCALAPPDATA%\VillageLifeRevivalNext and are not removed by uninstall.
'@ | Set-Content -LiteralPath (Join-Path $stage 'TEST-READ-ME.txt') -Encoding UTF8
if (-not $IsccPath) {
    $userCompiler = Join-Path $env:LOCALAPPDATA 'Programs\InnoSetupForVillageLifeTest\ISCC.exe'
    if (Test-Path -LiteralPath $userCompiler -PathType Leaf) { $IsccPath = $userCompiler }
}
if (-not $IsccPath) {
    foreach ($base in @(${env:ProgramFiles(x86)},${env:ProgramFiles})) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base 'Inno Setup 6\ISCC.exe'))) {
            $IsccPath = Join-Path $base 'Inno Setup 6\ISCC.exe'; break
        }
    }
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
    throw 'Inno Setup 6 ISCC.exe not found. Install Inno Setup 6 or pass -IsccPath.'
}
$installerOutput = $outputPath
New-Item -ItemType Directory -Path $installerOutput | Out-Null
& $IsccPath "/DStageDir=$stage" "/DOutputDir=$installerOutput" (Join-Path $PSScriptRoot 'VillageLife.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
Write-Host "Reliability test installer: $(Join-Path $installerOutput 'VillageLife-ReliabilityTest-Setup.exe')"
