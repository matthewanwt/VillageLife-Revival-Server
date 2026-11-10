# Safe optional cleanup for a GitHub checkout that received earlier source ZIPs.
# Dry-run by default; when -Apply is supplied, MOVE old files to a separate
# directory outside this repo. Does not delete files, saves, or the old 55 GB folder.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ArchiveDir,[switch]$Apply)
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    throw 'This is not a Git working checkout. No files were moved.'
}
$dest=[System.IO.Path]::GetFullPath($ArchiveDir)
$separator=[System.IO.Path]::DirectorySeparatorChar
if ($dest.Equals($repo,[System.StringComparison]::OrdinalIgnoreCase) -or $dest.StartsWith($repo+$separator,[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'ArchiveDir must be outside the repository.'
}
if (Test-Path -LiteralPath $dest) {
    if ((Get-ChildItem -LiteralPath $dest -Force | Select-Object -First 1)) {throw 'ArchiveDir must be new or empty.'}
}
$old=@('legacy_reference','windows/tools','windows/tests','windows/docs',
       'SOURCE_FILE_MANIFEST.json','MIGRATION_MANIFEST.json',
       'windows/COMPATIBILITY_MANIFEST.json','windows/launcher/LocalApkSigner.cs',
       'tools/audit_legacy_source.py')
foreach($relative in $old) {
    $source=Join-Path $repo $relative
    if (-not (Test-Path -LiteralPath $source)) {continue}
    Write-Host ('Obsolete checkout item: '+$relative)
    if ($Apply) {
        $target=Join-Path $dest $relative
        $parent=Split-Path -Parent $target
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
        Move-Item -LiteralPath $source -Destination $target -ErrorAction Stop
        Write-Host ('Archived: '+$relative)
    }
}
if (Test-Path -LiteralPath (Join-Path $repo 'backend')) {
    Write-Warning 'A backend/ folder remains. It may contain LIVE PLAYER SAVES. It was NOT moved. Inspect and back it up manually before removing anything.'
}
if (-not $Apply) {Write-Warning 'DRY RUN ONLY. Commit your old checkout, choose an empty archive directory outside Git, then rerun with -Apply.'}
