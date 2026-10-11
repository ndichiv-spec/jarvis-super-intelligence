$ErrorActionPreference = "Continue"

$platformRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $PSScriptRoot "web"
$escapedPlatformRoot = $platformRoot.Replace("'", "''")
$escapedWebRoot = $webRoot.Replace("'", "''")

$backendCommand = "Set-Location -LiteralPath '$escapedPlatformRoot'; python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000"
$backend = Start-Process powershell -ArgumentList @("-NoExit", "-Command", $backendCommand) -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 5

$webCommand = "Set-Location -LiteralPath '$escapedWebRoot'; npm run dev"
$web = Start-Process powershell -ArgumentList @("-NoExit", "-Command", $webCommand) -PassThru -WindowStyle Minimized

Write-Host "Backend PID: $($backend.Id)"
Write-Host "Web UI PID: $($web.Id)"
Write-Host "JARVIS running at:"
Write-Host "  Backend: http://127.0.0.1:8000"
Write-Host "  Web UI: http://127.0.0.1:3000"