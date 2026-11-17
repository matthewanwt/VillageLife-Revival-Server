# Build the complete community installer with the verified original game archive.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OriginalXapk,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [Parameter(Mandatory=$true)][string]$IsccPath,
    [Parameter(Mandatory=$true)][string]$BuildFolder,
    [Parameter(Mandatory=$true)][string]$OutputFolder
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$build = [System.IO.Path]::GetFullPath($BuildFolder)
$output = [System.IO.Path]::GetFullPath($OutputFolder)
foreach ($folder in @($build, $output)) {
    if (Test-Path -LiteralPath $folder) { throw "Build destination already exists: $folder" }
}
if ($build -eq $output -or
    $output.StartsWith($build + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -or
    $build.StartsWith($output + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Build and installer output must be separate directories.'
}
$original = (Get-Item -LiteralPath $OriginalXapk).FullName
$expectedHash = '8D25823B824BA766B38E53AEDB74B270A0254E6BF3FBBcf1A858B090A66B5C08'
if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Original XAPK does not match the verified 0.2.6 community archive.'
}
$stage = Join-Path $build 'payload'
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$pyArgs = @('-m', 'PyInstaller', '--log-level', 'WARN', '--noconfirm', '--onedir', '--console',
            '--name', 'VillageLifeServer', '--paths', (Join-Path $repo 'src'), '--collect-submodules', 'villagelife', '--hidden-import', 'villagelife.protocol.original_client.source_assets',
            '--add-data', ((Join-Path $repo 'tools/prepare_original_client.py')+';tools'),
            '--distpath', (Join-Path $stage 'bin'), '--workpath', (Join-Path $build 'pyinstaller-work'),
            '--specpath', $build, (Join-Path $PSScriptRoot 'new_backend_entry.py'))
$originalPythonPath = $env:PYTHONPATH
try {
    $sourcePath = Join-Path $repo 'src'
    $env:PYTHONPATH = if ($originalPythonPath) { $sourcePath + [IO.Path]::PathSeparator + $originalPythonPath } else { $sourcePath }
    & $PythonPath @pyArgs
} finally {
    $env:PYTHONPATH = $originalPythonPath
}
if ($LASTEXITCODE -ne 0) { throw 'Village Life server build failed.' }
$launcher = Join-Path $stage 'StartVillageLife'
$dotnetArgs = @('publish', (Join-Path $repo 'windows/launcher/VillageLifeLauncher.csproj'),
                '-c', 'Release', '-r', 'win-x64', '--self-contained', 'true',
                '-p:PublishSingleFile=false', '-p:NuGetAudit=false', '--ignore-failed-sources', '-o', $launcher)
& dotnet @dotnetArgs
if ($LASTEXITCODE -ne 0) { throw 'Windows launcher build failed.' }
$signer = Join-Path $stage 'signing-tools/jdk'
New-Item -ItemType Directory -Path (Split-Path $signer) -Force | Out-Null
& (Join-Path $JavaHome 'bin/jlink.exe') --add-modules 'jdk.jartool,jdk.crypto.ec' --no-header-files --no-man-pages --output $signer
if ($LASTEXITCODE -ne 0) { throw 'Local Java signing runtime build failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Community-Start-Here.txt') -Destination (Join-Path $stage 'START-HERE.txt')
foreach ($name in @('StartVillageLife/VillageLifeLauncher.exe','bin/VillageLifeServer/VillageLifeServer.exe',
                    'signing-tools/jdk/bin/keytool.exe','signing-tools/jdk/bin/jarsigner.exe',
                    'signing-tools/jdk/legal/java.base/LICENSE')) {
    if (!(Test-Path -LiteralPath (Join-Path $stage $name) -PathType Leaf)) { throw "Missing installer payload: $name" }
}
$private = Get-ChildItem -LiteralPath $stage -Recurse -File | Where-Object {
    $_.Extension -in @('.xapk','.apk','.obb','.sqlite','.sqlite3','.db','.pfx','.p12') -or
    $_.Name -in @('play-settings.json','launcher-settings.json','bluestacks-binding.json','private-password.txt') -or
    $_.FullName -match '(?i)[\\/](legacy_reference|private_state|backups|originals|private-assets)[\\/]'
} | Select-Object -First 1
if ($private) { throw "Private file in installer payload: $($private.Name)" }
# The original XAPK already contains the main OBB. Stage it separately from
# the runtime privacy check so this exact file is the only game asset allowed.
$assets = Join-Path $stage 'game-assets'
New-Item -ItemType Directory -Path $assets | Out-Null
$bundled = Join-Path $assets 'Village-Life-Original.xapk'
Copy-Item -LiteralPath $original -Destination $bundled
if ((Get-FileHash -LiteralPath $bundled -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Bundled original XAPK failed the integrity check.'
}
New-Item -ItemType Directory -Path $output | Out-Null
& $IsccPath /Qp "/DStageDir=$stage" "/DOutputDir=$output" (Join-Path $PSScriptRoot 'VillageLifeCommunity.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
Get-Item -LiteralPath (Join-Path $output 'VillageLife-Community-0.3.6-Setup.exe')
