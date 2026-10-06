$ErrorActionPreference = "Continue"

$backend = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Users\Administrator\Jarvis; python -m uvicorn api.main:create_application --factory --host 127.0.0.1 --port 8000" -PassThru -WindowStyle Minimized

Start-Sleep -Seconds 5

$web = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd C:\Users\Administrator\Jarvis\web; node node_modules\next\dist\bin\next dev -p 3000" -PassThru -WindowStyle Minimized

Write-Host "Backend PID: $($backend.Id)"
Write-Host "Web UI PID: $($web.Id)"
Write-Host "JARVIS running at:"
Write-Host "  Backend: http://127.0.0.1:8000"
Write-Host "  Web UI: http://127.0.0.1:3000"