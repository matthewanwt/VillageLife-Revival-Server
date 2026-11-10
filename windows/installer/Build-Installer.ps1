throw '[VL-INSTALLER-NOT-READY] Full gameplay installer gate not satisfied. Do not build a partial EXE. See docs/REMAINING_GAMEPLAY.md.'

# Compile a staged NEW-backend-only test manager into one installer using Inno Setup.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$StageFolder, [string]$IsccPath='')
$ErrorActionPreference='Stop'
$stage=(Resolve-Path -LiteralPath $StageFolder).Path
foreach($item in @('StartVillageLife\VillageLifeLauncher.exe','bin\VillageLifeServer\VillageLifeServer.exe','TEST-READ-ME.txt')) {
    if(-not (Test-Path -LiteralPath (Join-Path $stage $item) -PathType Leaf)) {throw "Missing required NEW backend build file: $item"}
}
$prohibited=Get-ChildItem -LiteralPath $stage -Recurse -File | Where-Object {
    $_.Extension -in @('.xapk','.apk','.obb','.sqlite','.sqlite3','.db','.pfx','.p12') -or
    $_.Name -in @('play-settings.json','bluestacks-binding.json','state.sqlite3','server.py') -or
    $_.FullName -match '(?i)[\\/](legacy_reference|private_state|backups|originals|private-assets)[\\/]'
}
if($prohibited) {throw "Prohibited legacy source or private game/player data found: $($prohibited[0].Name)"}
if(-not $IsccPath) {
    foreach($base in @(${env:ProgramFiles(x86)},${env:ProgramFiles})) {
        if($base -and (Test-Path -LiteralPath (Join-Path $base 'Inno Setup 6\ISCC.exe'))) {
            $IsccPath=Join-Path $base 'Inno Setup 6\ISCC.exe'; break
        }
    }
}
if(-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {throw 'Inno Setup 6 ISCC.exe not found. Provide -IsccPath.'}
& $IsccPath "/DStageDir=$stage" (Join-Path $PSScriptRoot 'VillageLife.iss')
if($LASTEXITCODE -ne 0) {throw "Inno Setup failed with exit code $LASTEXITCODE"}
