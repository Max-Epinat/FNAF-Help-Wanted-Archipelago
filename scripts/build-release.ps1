<#
.SYNOPSIS
    Builds the player release: dist\FNAF-HW-Archipelago-v<version>.zip

.DESCRIPTION
    The zip contains everything a player needs and nothing else, so it works without cloning the repository:

      fnaf_help_wanted.apworld      the Archipelago world + the launcher client
      mod\FNAFHWArchipelago\        the UE4SS mod
      install-mod.ps1               installer (checks UE4SS, installs the mod, copies the apworld)
      templates\*.yaml              player options template (includes Death Link)
      README.md, INSTALL.md, LICENSE

    Machine-specific or private files (config.lua, logs, saves, bridge runtime files) are never included.

.PARAMETER OutputDir  Where the zip is written. Default: <repo>\dist
#>
param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "zip-helpers.ps1")

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $repoRoot "dist" }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$pyproject = Get-Content (Join-Path $repoRoot "pyproject.toml") -Raw
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw "Could not read the version from pyproject.toml" }
$version = $Matches[1]
$name = "FNAF-HW-Archipelago-v$version"

# the apworld (also builds the vendored client files into it)
& (Join-Path $PSScriptRoot "build-apworld.ps1") | Out-Null
$apworld = Join-Path $repoRoot "dist\fnaf_help_wanted.apworld"
if (-not (Test-Path $apworld)) { throw "build-apworld.ps1 did not produce $apworld" }

$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("fnafhw_release_" + [guid]::NewGuid().ToString("N"))
$package = Join-Path $staging $name
New-Item -ItemType Directory -Path $package -Force | Out-Null

try {
    Copy-Item $apworld (Join-Path $package "fnaf_help_wanted.apworld")
    Copy-Item (Join-Path $PSScriptRoot "install-mod.ps1") (Join-Path $package "install-mod.ps1")
    Copy-Item (Join-Path $repoRoot "README.md") (Join-Path $package "README.md")
    Copy-Item (Join-Path $repoRoot "LICENSE") (Join-Path $package "LICENSE")

    $install = Join-Path $repoRoot "docs\installation.md"
    if (-not (Test-Path $install)) { throw "Missing docs\installation.md (the player install guide)" }
    Copy-Item $install (Join-Path $package "INSTALL.md")

    New-Item -ItemType Directory -Path (Join-Path $package "templates") -Force | Out-Null
    Copy-Item (Join-Path $repoRoot "templates\*.yaml") (Join-Path $package "templates")

    $modTarget = Join-Path $package "mod\FNAFHWArchipelago"
    New-Item -ItemType Directory -Path $modTarget -Force | Out-Null
    Copy-Item -Path (Join-Path $repoRoot "ue4ss_mod\FNAFHWArchipelago\*") -Destination $modTarget -Recurse -Force
    # never ship the developer's machine-specific or runtime files
    Get-ChildItem -Path $modTarget -Recurse -Force -File |
        Where-Object { $_.Name -eq "config.lua" -or $_.Extension -in @(".log", ".sav", ".bak", ".lock", ".dmp") -or $_.Name -like "ap_name_dump*" } |
        Remove-Item -Force
    Get-ChildItem -Path $modTarget -Recurse -Force -Directory | Where-Object { $_.Name -in @("bridge", "__pycache__") } |
        Remove-Item -Recurse -Force

    $zip = Join-Path $OutputDir "$name.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    New-StandardZip -SourceDir $package -ZipPath $zip -IncludeBaseDirectory $true
    Write-Host "Built release: $zip"
}
finally {
    Remove-Item -Path $staging -Recurse -Force -ErrorAction SilentlyContinue
}
