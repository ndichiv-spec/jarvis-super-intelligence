param(
    [string]$TaskName = "JARVIS Backend Supervisor"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Supervisor = Join-Path $PSScriptRoot "supervise_backend.py"
$Python = (Get-Command python -ErrorAction Stop).Source
$User = (& whoami).Trim()

if (-not (Test-Path -LiteralPath $Supervisor)) {
    throw "Backend supervisor not found: $Supervisor"
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Supervisor`"" `
    -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal `
    -UserId $User `
    -LogonType S4U `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Keeps the JARVIS API independent of frontend availability and restarts it after failures." `
    -Force | Out-Null

$backendAlreadyUp = $false
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/live" -TimeoutSec 2
    $backendAlreadyUp = $health.status -eq "alive"
} catch {
    $backendAlreadyUp = $false
}

if (-not $backendAlreadyUp) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "Installed and started '$TaskName'."
} else {
    Write-Output "Installed '$TaskName'; the existing API was left untouched. The task will own startup after the next boot."
}
Write-Output "Backend state and logs are under $Root\jarvis_data\supervisor."
