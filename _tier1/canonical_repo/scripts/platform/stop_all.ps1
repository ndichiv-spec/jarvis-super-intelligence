# stop_all.ps1 - stop the JARVIS + Silverwing project services.
#
# Stops (by command line, never by blanket process kill):
#   * silverwing_runtime.server   (:8010)
#   * jarvis_api.py               (:8000)
#   * the Next.js dev server      (:3000)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File stop_all.ps1

$ErrorActionPreference = "SilentlyContinue"

$targets = @(
    @{ Match = "*silverwing_runtime.server*";   Name = "runtime  :8010" },
    @{ Match = "*jarvis_api.py*";               Name = "platform :8000" },
    @{ Match = "*frontend*web*next*";           Name = "frontend :3000" },
    @{ Match = "*frontend*web*npm*run dev*";    Name = "frontend :3000" },
    @{ Match = "*frontend\\web*";               Name = "frontend :3000" }
)

$done = @{}
Get-CimInstance Win32_Process | Where-Object { $_.Name -match "python.exe|node.exe" } | ForEach-Object {
    $cmd = $_.CommandLine
    foreach ($t in $targets) {
        if ($cmd -like $t.Match -and -not $done.ContainsKey($_.ProcessId)) {
            $done[$_.ProcessId] = $true
            Write-Output ("[stop] {0} pid={1}" -f $t.Name, $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force
        }
    }
}

Write-Output "Services stopped (matched by command line)."