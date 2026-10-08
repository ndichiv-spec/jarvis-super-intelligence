#!/usr/bin/env pwsh
# Continuous monitor for the Kaggle LoRA training kernel.
# Polls kernel status, logs transitions, and downloads output once complete.
param(
    [string]$Kernel = "videlisndichi/jarvis-lora-training",
    [int]$IntervalSec = 30,
    [string]$OutDir = "F:\AI\Jarvis-super-intelligence-\monitoring\kaggle"
)

$ErrorActionPreference = "Continue"
$Null = New-Item -ItemType Directory -Path $OutDir -Force
$log = Join-Path $OutDir "monitor.log"
$statusLog = Join-Path $OutDir "status_history.jsonl"

function Get-TimeStamp { return (Get-Date).ToString("yyyy-MM-dd HH:mm:ss") }

function Write-Log([string]$msg) {
    $line = "[$(Get-TimeStamp)] $msg"
    $line | Tee-Object -FilePath $log -Append | Write-Host
}

function Get-KernelStatus {
    $raw = kaggle kernels status $Kernel 2>&1
    $raw = $raw.ToString().Trim()
    if ($raw -match '"([^"]+)"') { return $Matches[1] }
    return $raw
}

Write-Log "=== Kaggle kernel monitor started ==="
Write-Log "Kernel: $Kernel | Poll interval: ${IntervalSec}s | Log: $log"

$lastStatus = ""
$startTs = Get-Date
$noChangeCount = 0

while ($true) {
    $status = Get-KernelStatus
    if (-not $status) {
        Write-Log "WARN: could not read kernel status"
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    $changed = ($status -ne $lastStatus)
    if ($changed) {
        Write-Log "STATUS -> $status"
        $noChangeCount = 0
    } else {
        $noChangeCount++
        Write-Log "STATUS = $status (unchanged ${noChangeCount}x)"
    }

    # Persist history
    $rec = [pscustomobject]@{ ts = (Get-TimeStamp); status = $status }
    $rec | ConvertTo-Json -Compress | Add-Content $statusLog

    $lastStatus = $status

    # Terminal states
    $terminal = @("FINISHED", "FAILED", "ERROR", "CANCELLED", "CRASHED", "RUNNING_ERROR")
    if ($status -match "FINISHED|FAILED|ERROR|CANCELLED|CRASHED|RUNNING_ERROR") {
        Write-Log "Kernel reached terminal state: $status"
        Write-Log "Downloading output files..."
        $dlDir = Join-Path $OutDir "output"
        if (Test-Path $dlDir) { Remove-Item $dlDir -Recurse -Force }
        kaggle kernels output $Kernel -p $dlDir -o 2>&1 | Tee-Object -Variable out | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Output downloaded to $dlDir"
            $files = Get-ChildItem -Recurse -File $dlDir | Select-Object FullName, Length, LastWriteTime
            $files | ForEach-Object { Write-Log "  - $($_.FullName) ($('{0:N0}' -f ($_.Length/1KB)) KB) $($_.LastWriteTime)" }
        } else {
            Write-Log "WARN: output download exited code $LASTEXITCODE"
        }
        Write-Log "=== Monitor finished (runtime: $([math]::Round(((Get-Date) - $startTs).TotalMinutes,1)) min) ==="
        break
    }

    Start-Sleep -Seconds $IntervalSec
}
