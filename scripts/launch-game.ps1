<#
.SYNOPSIS
    One-click launcher for Five Nights at Freddy's: Help Wanted Archipelago Multiworld.
.DESCRIPTION
    1. Verifies UE4SS DLL placement (dwmapi.dll / UE4SS.dll).
    2. Syncs updated mod scripts and locations.json to the game Mods directory.
    3. Starts the Archipelago client: by default the launcher client ("FNAF Help Wanted Client", opened through the Archipelago launcher;
       the current apworld is copied into Archipelago first, because the client is part of it). -Client Standalone starts the old
       tkinter client (ap_client\main.py) instead, -Client None starts none.
    4. Prompts or launches the game in either Normal (Flat / Desktop) or VR mode.
#>

param(
    [string]$GameRoot = "",
    [ValidateSet("Ask", "Normal", "VR", "Flat")][string]$Mode = "Ask",
    [switch]$Normal,
    [switch]$VR,
    [ValidateSet("Launcher", "Standalone", "None")][string]$Client = "Launcher",
    [string]$ArchipelagoDir = "C:\ProgramData\Archipelago",
    [switch]$HeadlessBridge
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Find-GameRoot {
    param([string]$RequestedPath)
    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return (Resolve-Path $RequestedPath).Path
    }

    $candidates = [System.Collections.Generic.List[string]]::new()
    $candidates.Add("C:\Program Files (x86)\Steam\steamapps\common\FNAFVRHelpWanted")
    $candidates.Add("C:\Program Files\Steam\steamapps\common\FNAFVRHelpWanted")

    $drives = Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Root
    foreach ($d in $drives) {
        $candidates.Add((Join-Path $d "SteamLibrary\steamapps\common\FNAFVRHelpWanted"))
        $candidates.Add((Join-Path $d "Steam\steamapps\common\FNAFVRHelpWanted"))
        $candidates.Add((Join-Path $d "Games\FNAFVRHelpWanted"))
    }

    try {
        $steamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -Name "SteamPath" -ErrorAction SilentlyContinue).SteamPath
        if (-not $steamPath) {
            $steamPath = (Get-ItemProperty -Path "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam" -Name "InstallPath" -ErrorAction SilentlyContinue).InstallPath
        }
        if ($steamPath -and (Test-Path "$steamPath\steamapps\libraryfolders.vdf")) {
            $vdf = Get-Content "$steamPath\steamapps\libraryfolders.vdf" -Raw -ErrorAction SilentlyContinue
            $matches = [regex]::Matches($vdf, '"path"\s+"([^"]+)"')
            foreach ($m in $matches) {
                $libPath = $m.Groups[1].Value.Replace('\\', '\')
                $candidates.Add((Join-Path $libPath "steamapps\common\FNAFVRHelpWanted"))
            }
        }
    } catch {}

    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path (Join-Path $cand "freddys\Binaries\Win64\freddys-Win64-Shipping.exe"))) {
            return (Resolve-Path $cand).Path
        }
    }

    return "C:\Program Files (x86)\Steam\steamapps\common\FNAFVRHelpWanted"
}

$effectiveGameRoot = Find-GameRoot -RequestedPath $GameRoot
$binariesDir = Join-Path $effectiveGameRoot "freddys\Binaries\Win64"
$shippingExe = Join-Path $binariesDir "freddys-Win64-Shipping.exe"
$ue4ssDll    = Join-Path $binariesDir "UE4SS.dll"
$proxyDll    = Join-Path $binariesDir "dwmapi.dll"
$clientScript = Join-Path $repoRoot "ap_client\main.py"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  FNAF: Help Wanted - Archipelago Mod Launcher" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Game and UE4SS Binaries
Write-Host "[1/4] Verifying game binaries and UE4SS installation..." -ForegroundColor Yellow
if (-not (Test-Path $shippingExe)) {
    throw "Game executable not found at: $shippingExe. If installed in a non-standard location, run with -GameRoot '<path>'."
}
if (-not (Test-Path $ue4ssDll)) {
    throw "UE4SS.dll not found in $binariesDir. Please install UE4SS v3.0+ (place UE4SS.dll and dwmapi.dll in freddys\Binaries\Win64) first."
}
if (-not (Test-Path $proxyDll)) {
    $altProxy = Join-Path $binariesDir "xinput1_3.dll"
    if (-not (Test-Path $altProxy)) {
        Write-Warning "Neither dwmapi.dll nor xinput1_3.dll found in $binariesDir. UE4SS proxy may not hook automatically."
    }
}
Write-Host "      -> Game & UE4SS binaries verified at $effectiveGameRoot." -ForegroundColor Green

# 2. Sync Mod files to Game Mods folder
Write-Host "[2/4] Syncing latest mod scripts to game..." -ForegroundColor Yellow
# The launcher client is inside the apworld: install the current one. The standalone client runs from the repo and needs no apworld.
$installArgs = @{ GameRoot = $effectiveGameRoot; BridgeDir = (Join-Path $repoRoot "bridge"); ArchipelagoDir = $ArchipelagoDir }
if ($Client -ne "Launcher") { $installArgs["SkipApworld"] = $true }
& (Join-Path $PSScriptRoot "install-mod.ps1") @installArgs
Write-Host "      -> Mod files synchronized." -ForegroundColor Green

# 3. Start the Archipelago client (only one client may run at a time: they share bridge\ap_client.lock)
Write-Host "[3/4] Starting the Archipelago client ($Client)..." -ForegroundColor Yellow

$existingBridge = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match "^python(\.exe|w\.exe)?$" -and
        $_.CommandLine -and
        $_.CommandLine -match "ap_client[\\/]main\.py"
    }

if ($Client -eq "None") {
    Write-Host "      -> No client started (-Client None)." -ForegroundColor Yellow
} elseif ($Client -eq "Launcher") {
    $launcherExe = Join-Path $ArchipelagoDir "ArchipelagoLauncher.exe"
    if ($existingBridge) {
        Write-Warning "The old standalone client is running (PID $((($existingBridge | Select-Object -ExpandProperty ProcessId)) -join ', ')). Close it before using the launcher client: only one client may run."
    }
    if (Test-Path $launcherExe) {
        # The component name selects "FNAF Help Wanted Client"; if this launcher ignores it, the launcher window still opens and you click it.
        Start-Process -FilePath $launcherExe -ArgumentList '"FNAF Help Wanted Client"' -WorkingDirectory $ArchipelagoDir
        Write-Host "      -> Opened the Archipelago launcher (FNAF Help Wanted Client)." -ForegroundColor Green
    } else {
        Write-Warning "ArchipelagoLauncher.exe not found in $ArchipelagoDir (use -ArchipelagoDir). Start 'FNAF Help Wanted Client' from your Archipelago launcher yourself."
    }
} elseif ($existingBridge) {
    $pids = ($existingBridge | Select-Object -ExpandProperty ProcessId) -join ", "
    Write-Host "      -> Archipelago client is already running (PID: $pids)." -ForegroundColor Green
} else {
    function Get-BootstrapPython {
        $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCmd -and $pythonCmd.Source -notlike "*WindowsApps*") {
            return @{ Exe = $pythonCmd.Source; Args = @() }
        }
        $pyCmd = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCmd) {
            return @{ Exe = $pyCmd.Source; Args = @("-3") }
        }
        return $null
    }

    $venvDir = Join-Path $repoRoot ".venv"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    $clientDir = Join-Path $repoRoot "ap_client"

    if ((-not (Test-Path $venvDir)) -or (-not (Test-Path $venvPython))) {
        Write-Host "      -> Initializing Python virtual environment (.venv)..." -ForegroundColor Yellow
        $bootstrap = Get-BootstrapPython
        if (-not $bootstrap) {
            throw "No usable Python launcher found. Please install Python 3.10+ and ensure python or py is in PATH."
        }
        if (Test-Path $venvDir) {
            Remove-Item -Path $venvDir -Recurse -Force
        }
        & $bootstrap.Exe @($bootstrap.Args + @("-m", "venv", $venvDir))
        if (-not (Test-Path $venvPython)) {
            throw "Failed to create virtual environment at $venvDir"
        }
        Write-Host "      -> Installing client dependencies..." -ForegroundColor Yellow
        & $venvPython -m pip install --upgrade pip --quiet
        & $venvPython -m pip install -r (Join-Path $clientDir "requirements.txt") --quiet
    }

    $pyToUse = if (Test-Path $venvPython) { $venvPython } else { "python.exe" }
    $bridgeArgs = if ($HeadlessBridge) { "`"$clientScript`" --headless" } else { "`"$clientScript`"" }
    $procInfo = New-Object System.Diagnostics.ProcessStartInfo
    $procInfo.FileName = $pyToUse
    $procInfo.Arguments = $bridgeArgs
    $procInfo.WorkingDirectory = (Join-Path $repoRoot "ap_client")
    $procInfo.UseShellExecute = $true
    if ($HeadlessBridge) {
        $procInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    }

    $bridgeProc = [System.Diagnostics.Process]::Start($procInfo)
    Write-Host "      -> Started Archipelago Client GUI (PID: $($bridgeProc.Id))." -ForegroundColor Green
}

# Determine Launch Mode (Normal vs VR)
$targetMode = "Normal"
if ($Normal -or ($Mode -in @("Normal", "Flat"))) {
    $targetMode = "Normal"
} elseif ($VR -or ($Mode -eq "VR")) {
    $targetMode = "VR"
} else {
    Write-Host ""
    Write-Host "Select Game Launch Mode:" -ForegroundColor Cyan
    Write-Host "  [1] Normal Mode (Flat / Desktop Monitor) [DEFAULT]" -ForegroundColor White
    Write-Host "  [2] VR Mode (SteamVR / Oculus Headset)" -ForegroundColor White
    Write-Host ""
    $choice = Read-Host "Choose mode [1 or 2, default: 1]"
    if ($choice -eq "2") {
        $targetMode = "VR"
    } else {
        $targetMode = "Normal"
    }
}

# 4. Launch Game
Write-Host "[4/4] Launching game in $targetMode mode..." -ForegroundColor Yellow
if ($targetMode -eq "Normal") {
    $procInfo = New-Object System.Diagnostics.ProcessStartInfo
    $procInfo.FileName = $shippingExe
    $procInfo.Arguments = "-nohmd"
    $procInfo.WorkingDirectory = $binariesDir
    [System.Diagnostics.Process]::Start($procInfo)
    Write-Host "      -> Launched $shippingExe in Flat / Normal Mode (-nohmd)." -ForegroundColor Green
} else {
    Start-Process "steam://rungameid/732690"
    Write-Host "      -> Sent VR launch command to Steam (AppID 732690)." -ForegroundColor Green
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  Ready to Play!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
if ($Client -eq "Launcher") {
    Write-Host "- In the Archipelago launcher, connect 'FNAF Help Wanted Client' to your room (start it first if it did not open)." -ForegroundColor White
} elseif ($Client -eq "Standalone") {
    Write-Host "- Archipelago Client window is open on your desktop." -ForegroundColor White
    Write-Host "- Press [F1] in-game anytime to check status, connect, or bring the window to front." -ForegroundColor White
    Write-Host "- Console commands available: ap_connect, ap_disconnect, ap_status, ap_check_name." -ForegroundColor White
}
Write-Host "==========================================================" -ForegroundColor Cyan
