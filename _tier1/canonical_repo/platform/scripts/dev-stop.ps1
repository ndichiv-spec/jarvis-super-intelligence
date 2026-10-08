#dev-stop.ps1
# JARVIS Development Server Stopper
# Usage: .\scripts\dev-stop.ps1

$ErrorActionPreference = "SilentlyContinue"

Write-Host "Stopping JARVIS Development Environment..." -ForegroundColor Cyan

# Find and kill Python processes running jarvis
$JarvisProcs = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { 
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    $cmd -match "jarvis|uvicorn|8000"
}

if ($JarvisProcs) {
    $JarvisProcs | ForEach-Object {
        Write-Host "Killing Python process (PID: $($_.Id))..." -ForegroundColor Yellow
        $_ | Stop-Process -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "No JARVIS Python processes found." -ForegroundColor Yellow
}

# Find and kill Node processes running next
$NodeProcs = Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    $cmd -match "next|jarvis|3000"
}

if ($NodeProcs) {
    $NodeProcs | ForEach-Object {
        Write-Host "Killing Node process (PID: $($_.Id))..." -ForegroundColor Yellow
        $_ | Stop-Process -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "No JARVIS Node processes found." -ForegroundColor Yellow
}

Write-Host "JARVIS processes stopped." -ForegroundColor Green

# Check if ports are free
$Port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$Port3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue

if (-not $Port8000 -and -not $Port3000) {
    Write-Host "Ports 8000 and 3000 are free." -ForegroundColor Green
} else {
    if ($Port8000) { Write-Host "Port 8000 is in use." -ForegroundColor Yellow }
    if ($Port3000) { Write-Host "Port 3000 is in use." -ForegroundColor Yellow }
}