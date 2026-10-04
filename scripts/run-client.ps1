param(
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$clientDir = Join-Path $repoRoot "ap_client"
$venvDir = Join-Path $repoRoot ".venv"

function Get-ExistingBridgeClients {
    $candidates = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match "^python(\.exe|w\.exe)?$" -and
            $_.CommandLine -and
            $_.CommandLine -match "ap_client[\\/]main\.py"
        }

    return @($candidates)
}

function Stop-ExistingBridgeClients {
    $candidates = Get-ExistingBridgeClients

    foreach ($proc in $candidates) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped existing bridge client process: $($proc.ProcessId)"
        }
        catch {
            Write-Warning "Could not stop existing bridge client process $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

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

$existing = Get-ExistingBridgeClients
if ($existing.Count -gt 0 -and -not $ForceRestart) {
    $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ", "
    Write-Host "AP bridge client already running (PID(s): $pids)."
    Write-Host "Use -ForceRestart if you intentionally want to bounce it."
    exit 0
}

if ($existing.Count -gt 0 -and $ForceRestart) {
    Stop-ExistingBridgeClients
}

$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ((-not (Test-Path $venvDir)) -or (-not (Test-Path $venvPython))) {
    $bootstrap = Get-BootstrapPython
    if (-not $bootstrap) {
        throw "No usable Python launcher was found. Install Python 3.11+ and ensure either python or py works in PowerShell."
    }
    if (Test-Path $venvDir) {
        Remove-Item -Path $venvDir -Recurse -Force
    }

    & $bootstrap.Exe @($bootstrap.Args + @("-m", "venv", $venvDir))
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment was created, but $venvPython is missing. Check Python installation and retry."
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $clientDir "requirements.txt")
& $venvPython (Join-Path $clientDir "main.py")
