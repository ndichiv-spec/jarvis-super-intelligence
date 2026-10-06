#dev-start.ps1
# JARVIS Development Server Starter
# Usage: .\scripts\dev-start.ps1

param(
    [switch]$NoFrontend = $false
)

$ErrorActionPreference = "Stop"

Write-Host "Starting JARVIS Development Environment..." -ForegroundColor Cyan

# Kill any existing processes on our ports
Write-Host "Checking for existing processes..." -ForegroundColor Yellow
$apiProcs = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { 
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    $cmd -match "jarvis|uvicorn" 
}
if ($apiProcs) {
    Write-Host "Killing existing JARVIS API processes..." -ForegroundColor Yellow
    $apiProcs | Stop-Process -Force -ErrorAction SilentlyContinue
}

# Get the project root
$Root = Split-Path -Parent $PSScriptRoot

# Load environment variables from .env
Write-Host "Loading environment variables from .env..." -ForegroundColor Yellow
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#')) {
            if ($line.Contains('=')) {
                $parts = $line.Split('=', 2)
                if ($parts.Count -eq 2) {
                    $name = $parts[0].Trim()
                    $value = $parts[1].Trim()
                    # Skip placeholder markers
                    if ($value -and -not $value.StartsWith('[') -and -not $value.StartsWith('⟦')) {
                        [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
                        Write-Host "  Set $name" -ForegroundColor Gray
                    }
                }
            }
        }
    }
}

# Start the backend API
Write-Host "Starting JARVIS Backend API on port 8000..." -ForegroundColor Green
$ApiProcess = Start-Process -FilePath "python" -ArgumentList "jarvis_api.py" -WorkingDirectory $Root -NoNewWindow -PassThru

Start-Sleep 3

if ($ApiProcess.HasExited) {
    Write-Host "ERROR: Backend failed to start!" -ForegroundColor Red
    exit 1
}

Write-Host "Backend API started (PID: $($ApiProcess.Id))" -ForegroundColor Green

if (-not $NoFrontend) {
    # Start the frontend
    Write-Host "Starting JARVIS Frontend on port 3000..." -ForegroundColor Green
    $FrontendDir = Join-Path $Root "frontend\web"
    
    # Check for node_modules
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
        Start-Process -FilePath "npm" -ArgumentList "install" -WorkingDirectory $FrontendDir -Wait -NoNewWindow
    }
    
    $FrontendProcess = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory $FrontendDir -NoNewWindow -PassThru
    
    Start-Sleep 5
    
    if ($FrontendProcess.HasExited) {
        Write-Host "WARNING: Frontend failed to start!" -ForegroundColor Yellow
    } else {
        Write-Host "Frontend started (PID: $($FrontendProcess.Id))" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "JARVIS Unified System is running!" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "API:          http://localhost:8000" -ForegroundColor White
Write-Host "API Docs:     http://localhost:8000/docs" -ForegroundColor White
if (-not $NoFrontend) {
    Write-Host "Frontend:     http://localhost:3000" -ForegroundColor White
}
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor White
Write-Host "==============================================" -ForegroundColor Cyan

# Wait for Ctrl+C or process exit
try {
    while ($ApiProcess.HasExited -eq $false) {
        Start-Sleep 1
    }
} finally {
    Write-Host "`nStopping all processes..." -ForegroundColor Yellow
    if ($ApiProcess -and -not $ApiProcess.HasExited) {
        $ApiProcess.Kill()
    }
}