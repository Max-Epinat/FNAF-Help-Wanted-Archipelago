$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "zip-helpers.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sourceWorldDir = Join-Path $repoRoot "fnaf_help_wanted"
$distDir = Join-Path $repoRoot "dist"
$tempRoot = Join-Path $env:TEMP ("fnafhw_apworld_" + [guid]::NewGuid().ToString("N"))
$tempPackageRoot = Join-Path $tempRoot "package"
$zipPath = Join-Path $distDir "fnaf_help_wanted.zip"
$apworldPath = Join-Path $distDir "fnaf_help_wanted.apworld"

if (-not (Test-Path $sourceWorldDir)) {
    throw "Missing world source folder: $sourceWorldDir"
}

New-Item -ItemType Directory -Path $distDir -Force | Out-Null
New-Item -ItemType Directory -Path $tempPackageRoot -Force | Out-Null

Copy-Item -Path $sourceWorldDir -Destination (Join-Path $tempPackageRoot "fnaf_help_wanted") -Recurse -Force

# The launcher client reuses the transport-free client core and the save reader: they are copied into the package at
# build time (single source of truth in ap_client/ and bridge/), listed in scripts/vendored_client_files.json.
$vendoredList = Get-Content (Join-Path $PSScriptRoot "vendored_client_files.json") -Raw | ConvertFrom-Json
foreach ($entry in $vendoredList) {
    $src = Join-Path $repoRoot $entry.source
    if (-not (Test-Path $src)) { throw "Missing vendored client file: $src" }
    Copy-Item -Path $src -Destination (Join-Path $tempPackageRoot ("fnaf_help_wanted\" + $entry.target)) -Force
}

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
if (Test-Path $apworldPath) { Remove-Item $apworldPath -Force }

New-StandardZip -SourceDir $tempPackageRoot -ZipPath $zipPath -IncludeBaseDirectory $false
Rename-Item -Path $zipPath -NewName "fnaf_help_wanted.apworld"

Remove-Item -Path $tempRoot -Recurse -Force

Write-Host "Built AP world package: $apworldPath"
