$ErrorActionPreference = "Continue"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendCommand = "Set-Location '$projectRoot'; python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000"
$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 5

$webCommand = "Set-Location '$projectRoot\frontend\web'; node node_modules\next\dist\bin\next dev -p 3000"
$web = Start-Process powershell -ArgumentList "-NoExit", "-Command", $webCommand -PassThru -WindowStyle Minimized

Write-Host "Backend PID: $($backend.Id)"
Write-Host "Web UI PID: $($web.Id)"
Write-Host "JARVIS running at:"
Write-Host "  Backend: http://127.0.0.1:8000"
Write-Host "  Web UI: http://127.0.0.1:3000"