# RELEASE GATE: This installer MUST NOT ship until the original Android XAPK
# is verified end-to-end against the NEW backend, local game resources, and
# a working safe network policy on Windows. The old installer was API-only.
throw '[VL-INSTALLER-NOT-READY] Full original-client gameplay, signed XAPK installation, guided BlueStacks setup, save upgrades and Wi-Fi isolation are not yet verified. The installer is intentionally blocked. See docs/REMAINING_GAMEPLAY.md.'

# Builds a NEW BACKEND-ONLY Windows test installer. No 2.11 player kit required.
# Run in PowerShell on Windows with Python/.venv + PyInstaller, .NET 10 SDK,
# Inno Setup 6. All outputs are kept separate from the repository and old saves.
[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [string]$StageFolder = "",
    [string]$IsccPath = ""
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $PythonPath) { $PythonPath = Join-Path $repo '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Missing project Python .venv. Run: py -3 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e . pyinstaller'
}
if (-not $StageFolder) { $StageFolder = Join-Path $env:TEMP ('VillageLife-NextTest-'+(Get-Date -Format 'yyyyMMddHHmmssfff')) }
$stage = [System.IO.Path]::GetFullPath($StageFolder)
if (Test-Path -LiteralPath $stage) { throw "Stage already exists: $stage" }
if ($stage.StartsWith($repo+[System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build stage must be OUTSIDE the repository.'
}
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
# Generated build intermediates never go into the installer.
Remove-Item -LiteralPath $pyWork,$spec -Recurse -Force
@'
NEW BACKEND TEST BUILD - NOT THE ORIGINAL APK GAME PLAYER.
This installer includes ONLY the new modular API (/v1), its account/save store,
read-only BlueStacks selection/diagnostics and one-way legacy save importer.
The original binary ClientService protocol is NOT implemented yet. You CANNOT
play the original Village Life APK with this build; there is NO old fallback.
Original 2.11 saves are NOT automatically migrated or modified.
Wi-Fi-on guest isolation has NOT been established.
'@ | Set-Content -LiteralPath (Join-Path $stage 'TEST-READ-ME.txt') -Encoding UTF8
& (Join-Path $PSScriptRoot 'Build-Installer.ps1') -StageFolder $stage -IsccPath $IsccPath
if ($LASTEXITCODE -ne 0) { throw 'Installer creation failed' }
Write-Host 'Output: windows\installer\output\VillageLife-NextBackend-TestSetup.exe'
