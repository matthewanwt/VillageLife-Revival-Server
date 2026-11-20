# Build the complete community installer with the verified original game archive.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$OriginalXapk,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [Parameter(Mandatory=$true)][string]$IsccPath,
    [Parameter(Mandatory=$true)][string]$BuildFolder,
    [Parameter(Mandatory=$true)][string]$OutputFolder,
    [switch]$PrivateCandidate,
    [string]$SigningCertificateThumbprint = "",
    [string]$SignToolPath = "signtool.exe"
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
New-Item -ItemType Directory -Path $build -Force | Out-Null
$gate = Join-Path $build 'release-gate.json'
$gateArgs = @((Join-Path $repo 'tools/release_gate.py'), '--output', $gate)
if ($PrivateCandidate) { $gateArgs += '--private-candidate' }
& $PythonPath @gateArgs
if ($LASTEXITCODE -ne 0) { throw 'Exact-source release validation failed.' }
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
                '-p:PublishSingleFile=false', '-p:NuGetAudit=true', '-p:NuGetAuditMode=all', '-o', $launcher)
if ($PrivateCandidate) { $dotnetArgs += '-p:DefineConstants=PRIVATE_CANDIDATE' }
& dotnet @dotnetArgs
if ($LASTEXITCODE -ne 0) { throw 'Windows launcher build failed.' }
$signer = Join-Path $stage 'signing-tools/jdk'
New-Item -ItemType Directory -Path (Split-Path $signer) -Force | Out-Null
& (Join-Path $JavaHome 'bin/jlink.exe') --add-modules 'jdk.jartool,jdk.crypto.ec' --no-header-files --no-man-pages --output $signer
if ($LASTEXITCODE -ne 0) { throw 'Local Java signing runtime build failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Community-Start-Here.txt') -Destination (Join-Path $stage 'START-HERE.txt')
if ($PrivateCandidate) {
    @'
PRIVATE AUDIT CANDIDATE - NOT A PUBLIC RELEASE

This candidate uses a separate VillageLifeAuditPrivate save folder by default.
Choose a dedicated BlueStacks Pie 64-bit instance and let setup prepare its client.
Keep your existing community instance and save backups separate.
The original game archive and required expansion are included.
Do not publish this candidate before gameplay testing is complete.
'@ | Set-Content -LiteralPath (Join-Path $stage 'START-HERE.txt') -Encoding UTF8
}
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
function Sign-OwnedFile([string]$File) {
    if ($SigningCertificateThumbprint) {
        & $SignToolPath sign /sha1 $SigningCertificateThumbprint /fd SHA256 /tr 'https://timestamp.digicert.com' /td SHA256 $File
        if ($LASTEXITCODE -ne 0) { throw "Publisher signing failed: $File" }
    }
}
Sign-OwnedFile (Join-Path $launcher 'VillageLifeLauncher.exe')
Sign-OwnedFile (Join-Path $stage 'bin/VillageLifeServer/VillageLifeServer.exe')
$manifestArgs = @((Join-Path $repo 'tools/build_manifest.py'), '--payload', $stage, '--java-home', $JavaHome, '--gate', $gate)
if ($SigningCertificateThumbprint) { $manifestArgs += '--signed' }
& $PythonPath @manifestArgs
if ($LASTEXITCODE -ne 0) { throw 'Build provenance generation failed.' }
# Smoke-test the exact packaged backend, not a source import.
& (Join-Path $stage 'bin/VillageLifeServer/VillageLifeServer.exe') --db (Join-Path $build 'packaged-smoke.sqlite3') init-db
if ($LASTEXITCODE -ne 0) { throw 'Packaged server smoke test failed.' }
New-Item -ItemType Directory -Path $output | Out-Null
$isccArgs = @('/Qp',"/DStageDir=$stage","/DOutputDir=$output")
if ($PrivateCandidate) { $isccArgs += '/DPrivateCandidate=1' }
& $IsccPath @isccArgs (Join-Path $PSScriptRoot 'VillageLifeCommunity.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
$installer = Join-Path $output $(if ($PrivateCandidate) { 'VillageLife-Private-Audit-Setup.exe' } else { 'VillageLife-Community-0.3.6-Setup.exe' })
Sign-OwnedFile $installer
$checksum = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $([IO.Path]::GetFileName($installer))" | Set-Content -LiteralPath ($installer + '.sha256') -Encoding ASCII
Copy-Item -LiteralPath (Join-Path $stage 'BUILD-MANIFEST.json'),(Join-Path $stage 'BUILD-SBOM.cdx.json'),$gate -Destination $output
Get-Item -LiteralPath $installer
