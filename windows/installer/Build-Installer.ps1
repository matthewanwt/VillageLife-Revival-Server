# Build a single-file VillageLifeSetup.exe from a prepared, PRIVATE-asset-free player stage.
# Run on Windows with Inno Setup installed. Does not touch the user's v2.11 installation.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$StageFolder,
    [string]$IsccPath = ""
)
$ErrorActionPreference = "Stop"
$stage = (Resolve-Path -LiteralPath $StageFolder).Path
$needed = @(
    "StartVillageLife\VillageLifeLauncher.exe",
    "StartVillageLife\launcher.json",
    "runtime\python\python.exe",
    "backend\server.py",
    "tools\play_local.py",
    "tools\setup_local.py",
    "tools\export_diagnostics.py",
    "tools\platforms\bluestacks\adb.py",
    "tools\platforms\bluestacks\discovery.py"
)
foreach ($file in $needed) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $file) -PathType Leaf)) {
        throw "Incomplete Windows player stage: $file is missing. The new backend Alpha alone is NOT yet a legacy APK server."
    }
}
$forbidden = Get-ChildItem -LiteralPath $stage -Recurse -File | Where-Object {
    $_.Extension -in @(".xapk", ".apk", ".obb", ".pfx", ".p12", ".private", ".sqlite", ".db") -or
    $_.Name -in @("play-settings.json", "setup-network-check.json", "latest-runtime-error.json") -or
    $_.FullName -match '(?i)[\\/](private_state|backups|experiments|support)[\\/]'
}
if ($forbidden) {
    throw "The stage contains prohibited game assets, credentials or player data. Review and remove them from the STAGE COPY, not the original project. $($forbidden[0].FullName)"
}
if (-not $IsccPath) {
    $candidates = @()
    foreach ($programs in @(${env:ProgramFiles(x86)}, ${env:ProgramFiles})) {
        if ($programs) {
            $candidate = Join-Path $programs "Inno Setup 6\ISCC.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $candidates += $candidate }
        }
    }
    if ($candidates.Count -eq 0) { throw "Install Inno Setup 6 or provide -IsccPath with the full location of ISCC.exe." }
    $IsccPath = $candidates[0]
}
$script = Join-Path $PSScriptRoot "VillageLife.iss"
Write-Host "Compiling source-only per-user installer. Original game assets and player saves are excluded."
& $IsccPath "/DStageDir=$stage" $script
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE." }
Write-Host "Installer output: $(Join-Path $PSScriptRoot 'output\VillageLifeSetup.exe')"
