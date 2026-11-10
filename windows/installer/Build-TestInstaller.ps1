# Developer-only Windows build. Never modifies the existing 2.11 player folder.
# Creates a separate, source-only VillageLife-TestSetup.exe for LOCAL testing.
# Requires: Windows + .NET 10 SDK + Inno Setup 6 + an existing, legitimately
# distributable bundled Python/.NET runtime from a clean 2.11 player kit.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PlayerKitRoot,
    [string]$StageFolder = "",
    [string]$IsccPath = ""
)
$ErrorActionPreference = "Stop"
$source = (Resolve-Path -LiteralPath $PlayerKitRoot).Path
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if (-not $StageFolder) { $StageFolder = Join-Path $env:TEMP "VillageLife-TestBuild-$(Get-Date -Format yyyyMMddHHmmss)" }
$stage = [System.IO.Path]::GetFullPath($StageFolder)
if ($stage.StartsWith($source + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
    $stage.Equals($source, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to build inside the original player kit: choose a SEPARATE stage folder."
}
if (Test-Path -LiteralPath $stage) { throw "Stage folder already exists; choose a NEW empty directory: $stage" }
foreach ($name in @("runtime\python\python.exe", "runtime\dotnet\dotnet.exe")) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) {
        throw "Missing clean bundled runtime $name in PlayerKitRoot. Use an unpacked 2.11 player kit (not the 55 GB working folder)."
    }
}
$dotnet = Get-Command dotnet -ErrorAction Stop
New-Item -ItemType Directory -Force -Path $stage | Out-Null
foreach ($kind in @("python", "dotnet")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "runtime\$kind") | Out-Null
    Copy-Item -Path (Join-Path $source "runtime\$kind\*") -Destination (Join-Path $stage "runtime\$kind") -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $repo "legacy_reference\backend") -Destination (Join-Path $stage "backend") -Recurse
Copy-Item -LiteralPath (Join-Path $repo "windows\tools") -Destination (Join-Path $stage "tools") -Recurse
# Ensure no test caches or source-tree data get distributed.
Get-ChildItem -LiteralPath $stage -Recurse -Directory | Where-Object Name -in @("__pycache__", ".pytest_cache") | Remove-Item -Recurse -Force
$publish = Join-Path $stage 'StartVillageLife'
Write-Host "Building the CURRENT C# launcher with the new buttons (Windows x64)."
& $dotnet.Source publish (Join-Path $repo "windows\launcher\VillageLifeLauncher.csproj") -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=false -o $publish
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed" }
Copy-Item -LiteralPath (Join-Path $repo 'windows\launcher\launcher.json') -Destination (Join-Path $publish 'launcher.json')
# Native APK signing code currently launches the bundled dotnet host and the
# published launcher assembly, so keep both files in place.
if (-not (Test-Path -LiteralPath (Join-Path $publish 'VillageLifeLauncher.dll'))) {
    throw "Expected signing assembly is absent: VillageLifeLauncher.dll"
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$versionJson = @{
    restoration_version = "2.11-windows-test"
    release_scope = "PRIVATE development test; Wi-Fi network isolation unverified"
    full_multiplayer_verified = $false
} | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $stage 'VERSION.json'), $versionJson, $utf8NoBom)
$communityJson = @{
    version = "2.11-windows-test"
    game_files_included = $false
    personal_saves_included = $false
    setup_uses_recipients_original_xapk = $true
} | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $stage 'COMMUNITY-PACKAGE.json'), $communityJson, $utf8NoBom)
@'
Village Life Windows test player. This installer is NOT a public release.
Install BlueStacks 5 separately. Use Instance Manager to create a Pie64 VM.
Click Set Up Game, select the instance and supply your OWN supported XAPK.
The current Wi-Fi-on isolation design has NOT been validated and setup may
reject a network configuration. Do not bypass the network guard.
The original 2.11 player folder is never changed by the build.
'@ | Set-Content -LiteralPath (Join-Path $stage 'TEST-BUILD-NOTICE.txt') -Encoding UTF8
$builder = Join-Path $PSScriptRoot 'Build-Installer.ps1'
Write-Host "Preparing isolated test installer stage: $stage"
& $builder -StageFolder $stage -IsccPath $IsccPath
if ($LASTEXITCODE -ne 0) { throw "Installer step failed" }
Write-Host "TEST INSTALLER: $(Join-Path $PSScriptRoot 'output\VillageLife-TestSetup.exe')"
Write-Warning 'Windows host/BlueStacks networking and full APK setup MUST be validated before distributing to other players.'
