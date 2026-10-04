<#
.SYNOPSIS
    Installs the FNAF Help Wanted Archipelago mod (and the apworld) for a player or a developer.

.DESCRIPTION
    1. Finds the game (Steam) or uses -GameRoot.
    2. Checks that UE4SS is installed in the game folder. It is NOT bundled or downloaded (see the link printed when it is missing).
    3. Copies the mod into freddys\Binaries\Win64\Mods\FNAFHWArchipelago and writes its config.lua. The bridge folder (the files the
       game mod and the Archipelago client share) is created inside the installed mod folder unless -BridgeDir says otherwise.
    4. Enables the mod in mods.txt.
    5. Copies fnaf_help_wanted.apworld into Archipelago's custom_worlds folder when Archipelago is found.

    Works from the release zip (mod\ and fnaf_help_wanted.apworld next to this script) and from the repository
    (ue4ss_mod\ and dist\fnaf_help_wanted.apworld, built on demand).

.PARAMETER GameRoot       Game folder (the one that contains freddys\). Detected from Steam when omitted.
.PARAMETER BridgeDir      Bridge folder. Default: <installed mod folder>\bridge. Developers can point it at the repo's bridge\ folder.
.PARAMETER ArchipelagoDir Archipelago installation. Default: C:\ProgramData\Archipelago.
.PARAMETER SkipApworld    Do not copy the apworld.
.PARAMETER CheckOnly      Only report what is found and what is missing; change nothing.
#>
param(
    [string]$GameRoot = "",
    [string]$BridgeDir = "",
    [string]$ArchipelagoDir = "C:\ProgramData\Archipelago",
    [switch]$SkipApworld,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$Ue4ssReleases = "https://github.com/UE4SS-RE/RE-UE4SS/releases"
$Ue4ssVersionTested = "v3.0.1"

function Find-ModSource {
    foreach ($candidate in @(
        (Join-Path $PSScriptRoot "mod\FNAFHWArchipelago"),
        (Join-Path $PSScriptRoot "..\ue4ss_mod\FNAFHWArchipelago")
    )) {
        if (Test-Path (Join-Path $candidate "Scripts\main.lua")) { return (Resolve-Path $candidate).Path }
    }
    throw "Could not find the mod files (expected mod\FNAFHWArchipelago next to this script, or ue4ss_mod\FNAFHWArchipelago in the repository)."
}

function Find-Apworld {
    $released = Join-Path $PSScriptRoot "fnaf_help_wanted.apworld"
    if (Test-Path $released) { return $released }
    $built = Join-Path $PSScriptRoot "..\dist\fnaf_help_wanted.apworld"
    if (-not (Test-Path $built) -and (Test-Path (Join-Path $PSScriptRoot "build-apworld.ps1"))) {
        Write-Host "Building the Archipelago world package..."
        & (Join-Path $PSScriptRoot "build-apworld.ps1") | Out-Null
    }
    if (Test-Path $built) { return (Resolve-Path $built).Path }
    return $null
}

function Find-GameRoot {
    param([string]$Requested)
    if ($Requested) {
        if (Test-Path (Join-Path $Requested "freddys")) { return (Resolve-Path $Requested).Path }
        throw "-GameRoot '$Requested' does not contain a 'freddys' folder."
    }

    $candidates = [System.Collections.Generic.List[string]]::new()
    $candidates.Add("C:\Program Files (x86)\Steam\steamapps\common\FNAFVRHelpWanted")
    $candidates.Add("C:\Program Files\Steam\steamapps\common\FNAFVRHelpWanted")
    foreach ($drive in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Root)) {
        $candidates.Add((Join-Path $drive "SteamLibrary\steamapps\common\FNAFVRHelpWanted"))
        $candidates.Add((Join-Path $drive "Steam\steamapps\common\FNAFVRHelpWanted"))
    }
    try {
        $steamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -Name "SteamPath" -ErrorAction SilentlyContinue).SteamPath
        if (-not $steamPath) {
            $steamPath = (Get-ItemProperty -Path "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam" -Name "InstallPath" -ErrorAction SilentlyContinue).InstallPath
        }
        $vdfPath = if ($steamPath) { Join-Path $steamPath "steamapps\libraryfolders.vdf" } else { $null }
        if ($vdfPath -and (Test-Path $vdfPath)) {
            foreach ($m in [regex]::Matches((Get-Content $vdfPath -Raw), '"path"\s+"([^"]+)"')) {
                $candidates.Add((Join-Path $m.Groups[1].Value.Replace('\\', '\') "steamapps\common\FNAFVRHelpWanted"))
            }
        }
    } catch {}

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path (Join-Path $candidate "freddys\Binaries\Win64"))) { return (Resolve-Path $candidate).Path }
    }
    return $null
}

function Write-Status {
    param([string]$Label, [bool]$Ok, [string]$Detail = "")
    $mark = if ($Ok) { "[ OK ]" } else { "[ !! ]" }
    $color = if ($Ok) { "Green" } else { "Yellow" }
    Write-Host ("{0} {1} {2}" -f $mark, $Label, $Detail) -ForegroundColor $color
}

Write-Host "FNAF Help Wanted x Archipelago - installer" -ForegroundColor Cyan

# ---- the game
$root = Find-GameRoot -Requested $GameRoot
if (-not $root) {
    Write-Status "Game" $false "not found. Run again with -GameRoot ""<folder that contains freddys>""."
    exit 2
}
$win64 = Join-Path $root "freddys\Binaries\Win64"
Write-Status "Game" $true $root

# ---- UE4SS (not bundled: check and link)
$ue4ssDll = Test-Path (Join-Path $win64 "UE4SS.dll")
$ue4ssProxy = (Test-Path (Join-Path $win64 "dwmapi.dll")) -or (Test-Path (Join-Path $win64 "xinput1_3.dll"))
$modsDir = Join-Path $win64 "Mods"
$ue4ssOk = $ue4ssDll -and $ue4ssProxy -and (Test-Path $modsDir)
Write-Status "UE4SS" $ue4ssOk $(if ($ue4ssOk) { "installed in $win64" } else { "NOT found in $win64" })
if (-not $ue4ssOk) {
    Write-Host ""
    Write-Host "UE4SS (Unreal Engine scripting system) is required and is not included in this package." -ForegroundColor Yellow
    Write-Host "  1. Download UE4SS $Ue4ssVersionTested (the version this mod was tested with) from:"
    Write-Host "       $Ue4ssReleases"
    Write-Host "  2. Extract it into: $win64"
    Write-Host "     (UE4SS.dll, dwmapi.dll and the Mods folder must end up next to freddys-Win64-Shipping.exe)"
    Write-Host "  3. Start the game once, close it, then run this installer again."
    exit 3
}

# ---- sources
$modSource = Find-ModSource
$apworld = if ($SkipApworld) { $null } else { Find-Apworld }
Write-Status "Mod files" $true $modSource
if (-not $SkipApworld) { Write-Status "apworld" ($null -ne $apworld) $(if ($apworld) { $apworld } else { "not found (nothing to copy)" }) }

$targetMod = Join-Path $modsDir "FNAFHWArchipelago"
$bridge = if ($BridgeDir) { $BridgeDir } else { Join-Path $targetMod "bridge" }
$customWorlds = Join-Path $ArchipelagoDir "custom_worlds"
$archipelagoFound = Test-Path $ArchipelagoDir
Write-Status "Archipelago" $archipelagoFound $(if ($archipelagoFound) { $ArchipelagoDir } else { "not found at $ArchipelagoDir (copy the .apworld by hand, see below)" })

if ($CheckOnly) {
    Write-Host "`nCheck only: nothing was changed." -ForegroundColor Cyan
    exit 0
}

# ---- install the mod
New-Item -Path $targetMod -ItemType Directory -Force | Out-Null
Get-ChildItem -Path $modSource -Force | Where-Object { $_.Name -ne "config.lua" } |
    ForEach-Object { Copy-Item -Path $_.FullName -Destination $targetMod -Recurse -Force }

New-Item -Path $bridge -ItemType Directory -Force | Out-Null
$locations = Join-Path $modSource "locations.json"
if (Test-Path $locations) { Copy-Item -Path $locations -Destination (Join-Path $bridge "locations.json") -Force }

$bridgeLua = $bridge.Replace("\", "/")
$config = @"
return {
    -- Folder shared by the game mod and the Archipelago client (written by install-mod.ps1).
    bridge_dir = "$bridgeLua",

    -- In-game UI toggle key (default F1)
    ui_key = "F1",

    -- Verbose debug logging in the UE4SS console
    debug_logging = true,
}
"@
[System.IO.File]::WriteAllText((Join-Path $targetMod "config.lua"), $config, (New-Object System.Text.UTF8Encoding($false)))

$modsTxt = Join-Path $modsDir "mods.txt"
if (-not (Test-Path $modsTxt)) {
    [System.IO.File]::WriteAllText($modsTxt, "FNAFHWArchipelago : 1`r`n")
} elseif ((Get-Content $modsTxt -Raw) -notmatch "(?m)^\s*FNAFHWArchipelago\s*:\s*1\s*$") {
    Add-Content -Path $modsTxt -Value "FNAFHWArchipelago : 1"
}
Write-Status "Mod installed" $true $targetMod
Write-Status "Bridge folder" $true $bridge

# ---- the apworld
if ($apworld) {
    if ($archipelagoFound) {
        New-Item -Path $customWorlds -ItemType Directory -Force | Out-Null
        Copy-Item -Path $apworld -Destination (Join-Path $customWorlds "fnaf_help_wanted.apworld") -Force
        Write-Status "apworld installed" $true (Join-Path $customWorlds "fnaf_help_wanted.apworld")
    } else {
        Write-Host "`nArchipelago was not found. Install fnaf_help_wanted.apworld yourself: double-click it, or copy it into the" -ForegroundColor Yellow
        Write-Host "custom_worlds folder of your Archipelago installation."
    }
}

Write-Host "`nDone. Next: start 'FNAF Help Wanted Client' from the Archipelago launcher, connect to your room, then start the game." -ForegroundColor Cyan
exit 0
