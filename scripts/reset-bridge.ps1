param(
    [switch]$ResetState,
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bridgeDir = Join-Path $repoRoot "bridge"
$outboxPath = Join-Path $bridgeDir "ap_outbox.txt"
$inboxPath = Join-Path $bridgeDir "ap_inbox.txt"
$statePath = Join-Path $bridgeDir "ap_state.json"

if (-not (Test-Path $bridgeDir)) {
    New-Item -Path $bridgeDir -ItemType Directory -Force | Out-Null
}

if (-not (Test-Path $outboxPath)) {
    New-Item -Path $outboxPath -ItemType File -Force | Out-Null
}

if (-not (Test-Path $inboxPath)) {
    New-Item -Path $inboxPath -ItemType File -Force | Out-Null
}

if ($ResetState) {
    Set-Content -Path $outboxPath -Value "" -Encoding Ascii
    Set-Content -Path $inboxPath -Value "" -Encoding Ascii

    $state = [ordered]@{
        checked_locations = @()
        pending_locations = @()
        next_item_index = 0
        outbox_position = 0
    }

    ($state | ConvertTo-Json -Depth 4) + "`n" | Set-Content -Path $statePath -Encoding Ascii
    Write-Host "Cleared bridge inbox/outbox buffers"
    Write-Host "Reset bridge state file: $statePath"
}

Add-Content -Path $outboxPath -Value "RECONNECT"
if (-not $NoSync) {
    Add-Content -Path $outboxPath -Value "SYNC"
}

Write-Host "Queued bridge reconnect command in: $outboxPath"
if ($NoSync) {
    Write-Host "SYNC command skipped (-NoSync)."
} else {
    Write-Host "SYNC command queued after reconnect."
}
Write-Host "If ap_client is running, reconnect should happen within ~1 second."
