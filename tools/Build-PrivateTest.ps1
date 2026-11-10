# Builds a local, private-test launcher folder. It intentionally does not make
# an installer and must never be used to redistribute original game assets.
[CmdletBinding()]
param([string]$OutputFolder = (Join-Path $env:USERPROFILE 'Desktop\VillageLife-PrivateTest'))
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install the project plus pyinstaller first.' }
foreach ($required in @('game_tables.sqlite','obb_tcf.inventory.csv','main.241.com.playdemic.villagelife.android.obb')) {
    if (!(Test-Path -LiteralPath (Join-Path $repo "private-assets\$required"))) { throw "Missing private-assets\$required" }
}
if ((Get-ChildItem -LiteralPath (Join-Path $repo 'private-assets') -Filter '*.xapk' -File).Count -ne 1) { throw 'private-assets must contain exactly one XAPK.' }
if (Test-Path -LiteralPath $OutputFolder) { throw "Refusing to overwrite existing output: $OutputFolder" }
New-Item -ItemType Directory -Force (Join-Path $OutputFolder 'bin') | Out-Null
& $python -m PyInstaller --noconfirm --clean --onedir --console --name VillageLifeServer --paths (Join-Path $repo 'src') --collect-submodules villagelife --add-data ((Join-Path $repo 'tools\prepare_original_client.py')+';tools') --distpath (Join-Path $OutputFolder 'bin') --workpath (Join-Path $OutputFolder '.py-work') --specpath (Join-Path $OutputFolder '.spec') (Join-Path $repo 'windows\installer\new_backend_entry.py')
if ($LASTEXITCODE) { throw 'Backend bundling failed.' }
& dotnet publish (Join-Path $repo 'windows\launcher\VillageLifeLauncher.csproj') -c Release -r win-x64 --self-contained true -o (Join-Path $OutputFolder 'StartVillageLife')
if ($LASTEXITCODE) { throw 'Launcher publish failed.' }
Copy-Item -LiteralPath (Join-Path $repo 'private-assets') -Destination (Join-Path $OutputFolder 'private-assets') -Recurse
Remove-Item -LiteralPath (Join-Path $OutputFolder '.py-work'),(Join-Path $OutputFolder '.spec') -Recurse -Force
Write-Host "Private test build: $OutputFolder\StartVillageLife\VillageLifeLauncher.exe"
