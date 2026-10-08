# start_all.ps1 - reliably bring up the whole JARVIS + Silverwing project.
#
# Brings up (in dependency order) and health-checks:
#   1. Silverwing runtime  -> :8010 (silverwing_runtime.server, real weights)
#   2. JARVIS platform     -> :8000 (jarvis_api.py, FastAPI + Silverwing mount)
#   3. Frontend            -> :3000 (Next.js dev server)
#
# Idempotent: a service already passing its health endpoint is reused as-is.
# Services run detached (Start-Process) and keep their own log files, so a
# restart never depends on this script's shell staying alive.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File start_all.ps1
#
# Logs:
#   F:\AI\_logs_runtime.log / _logs_runtime_err.log
#   F:\AI\_logs_platform.log / _logs_platform_err.log
#   F:\AI\_logs_frontend.log / _logs_frontend_err.log

$ErrorActionPreference = "Stop"
$PY = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
$ROOT = "F:\AI"
$JARVIS = Join-Path $ROOT "Jarvis-super-intelligence-"
$WEB = Join-Path $JARVIS "frontend\web"

# Canonical integration env (mirrors _env.py).
$env:PYTHONPATH = "$ROOT;$JARVIS"
$env:SILVERWING_ENDPOINT = "http://127.0.0.1:8010"
$env:SILVERWING_MODEL = "silverwing-120m-base-v1"
$env:SILVERWING_TIMEOUT = "300"
$env:SILVERWING_BACKEND = "torch"
$env:SILVERWING_PORT = "8010"
$env:SILVERWING_MAX_TOKENS = "64"
$env:SILVERWING_REQUEST_TIMEOUT = "300"
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
$env:JARVIS_APP_URL = "http://localhost:3000"
# Source a project-local .env (if present) so OAuth/API credentials can live in
# one place that both this launcher and the platform agree on. OS environment
# variables always take precedence over .env values (we only set if unset).
$envFile = Join-Path $ROOT ".env"
if (Test-Path $envFile) {
    Write-Output "[env] loading $envFile"
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line.Length -eq 0 -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -le 0) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if ($val.Length -ge 2 -and ($val[0] -eq '"' -or $val[0] -eq "'") -and $val[-1] -eq $val[0]) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if (-not [System.Environment]::GetEnvironmentVariable($key)) {
            [System.Environment]::SetEnvironmentVariable($key, $val)
        }
    }
}

# --- Required secrets: no literals in source -------------------------------
# Secrets are NEVER hardcoded here. They must arrive via the OS environment or
# the project-local .env loaded above. JARVIS_SECRET_KEY signs JWTs/sessions and
# JARVIS_ADMIN_PASSWORD is the initial admin credential, so both are mandatory
# and we fail fast rather than silently falling back to a default.
function Get-RequiredSecret([string]$Name) {
    $v = [System.Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($v)) {
        throw "[start_all] Required secret '$Name' is not set. Set it in the environment or in $envFile. Refusing to start with a default."
    }
    return $v
}
$env:JARVIS_SECRET_KEY = Get-RequiredSecret "JARVIS_SECRET_KEY"
$env:JARVIS_ADMIN_PASSWORD = Get-RequiredSecret "JARVIS_ADMIN_PASSWORD"
Write-Output "[env] JARVIS_SECRET_KEY / JARVIS_ADMIN_PASSWORD resolved from environment"
# --- Real OAuth for external services --------------------------------------
# When an OAuth app is registered for a provider, Connect performs a REAL
# provider authorization-code handshake: /launch returns the provider's
# authorize URL, the service signs the user in, and redirects back to
#   http://localhost:8000/api/v1/extensions/oauth/callback/<ext_id>
# where JARVIS exchanges the code for tokens server-side (client_secret read
# from env -- never sent to the browser) and records a VALIDATED connection
# (oauth_token stored, connected_by set, capabilities go live on the platform).
# That is what makes a connection "real" instead of the manual confirm-gate.
#
# Register ONE OAuth App per provider (classic OAuth app), using redirect URI:
#   http://localhost:8000/api/v1/extensions/oauth/callback/<ext_id>
# then export that app's id + secret with the env var convention below. Only
# providers with BOTH id and secret are included here; services without a
# registered app stay on the safe service-app-URL + confirm-gate path (no
# OAuth secrets required).
#   JARVIS_OAUTH_GITHUB_CLIENT_ID   / JARVIS_OAUTH_GITHUB_CLIENT_SECRET
#   JARVIS_OAUTH_GITLAB_CLIENT_ID   / JARVIS_OAUTH_GITLAB_CLIENT_SECRET
#   JARVIS_OAUTH_GOOGLE_CLIENT_ID   / JARVIS_OAUTH_GOOGLE_CLIENT_SECRET
#   JARVIS_OAUTH_SLACK_CLIENT_ID    / JARVIS_OAUTH_SLACK_CLIENT_SECRET
#   JARVIS_OAUTH_MICROSOFT_CLIENT_ID / JARVIS_OAUTH_MICROSOFT_CLIENT_SECRET  (Outlook/Graph)
#   JARVIS_OAUTH_N8N_API_KEY        (n8n -> JARVIS callback authentication)
$oauthSpecs = @(
    @{ ext = 'github';           prefix = 'GITHUB';  authorize_url = 'https://github.com/login/oauth/authorize';             token_url = 'https://github.com/login/oauth/access_token';             scope = 'repo,read:user,read:org' }
    @{ ext = 'gitlab';           prefix = 'GITLAB';  authorize_url = 'https://gitlab.com/oauth/authorize';                   token_url = 'https://gitlab.com/oauth/token';                    scope = 'read_api,read_user' }
    @{ ext = 'google-workspace'; prefix = 'GOOGLE';  authorize_url = 'https://accounts.google.com/o/oauth2/v2/auth';          token_url = 'https://oauth2.googleapis.com/token';               scope = 'openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/drive.metadata.readonly'; is_google = $true }
    @{ ext = 'slack';            prefix = 'SLACK';   authorize_url = 'https://slack.com/oauth/v2/authorize';                 token_url = 'https://slack.com/api/oauth.v2.access';              scope = 'chat:write,channels:read,users:read' }
    # Gmail: read-only-first (spec §7). Send/draft come from a later authorize with
    # the gmail.send / gmail.compose scopes + the developer confirmation gate.
    @{ ext = 'gmail';            prefix = 'GOOGLE';  authorize_url = 'https://accounts.google.com/o/oauth2/v2/auth';          token_url = 'https://oauth2.googleapis.com/token';               scope = 'https://www.googleapis.com/auth/gmail.readonly'; is_google = $true }
    # Outlook: read-only-first (spec §8). Send/draft require Mail.Send after consent.
    @{ ext = 'outlook';          prefix = 'MICROSOFT'; authorize_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize'; token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'; scope = 'Mail.Read'; is_microsoft = $true }
)
$oauth = @{}
foreach ($s in $oauthSpecs) {
    $cid = [System.Environment]::GetEnvironmentVariable("JARVIS_OAUTH_$($s.prefix)_CLIENT_ID")
    $secret = [System.Environment]::GetEnvironmentVariable("JARVIS_OAUTH_$($s.prefix)_CLIENT_SECRET")
    if ($cid -and $secret) {
        $entry = [ordered]@{
            client_id     = $cid
            client_secret = $secret
            authorize_url = $s.authorize_url
            token_url     = $s.token_url
            scope         = $s.scope
        }
        if ($s.ContainsKey('is_google'))     { $entry.is_google = $true }
        if ($s.ContainsKey('is_microsoft')) { $entry.is_microsoft = $true }
        $oauth[$s.ext] = $entry
    }
    else {
        Write-Output "[oauth] $($s.ext): credentials not set -> confirm-gate path"
    }
}
if ($oauth.Count -gt 0) {
    $env:JARVIS_OAUTH_CLIENTS = $oauth | ConvertTo-Json -Compress -Depth 5
    Write-Output "[oauth] real OAuth wired for: $($oauth.Keys -join ', ')"
}
else { Write-Output "[oauth] no provider apps registered -> external services use app-URL + confirm-gate" }

function Test-Url($url, $timeoutSec = 3) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec $timeoutSec -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Wait-Url($url, $label, $waitSec) {
    $deadline = (Get-Date).AddSeconds($waitSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Url $url) { Write-Output "[ok] $label up: $url"; return $true }
        Start-Sleep -Seconds 2
    }
    Write-Output "[warn] $label still down: $url after ${waitSec}s"
    return $false
}

try {
    # 1. Runtime
    if (Test-Url "http://127.0.0.1:8010/v1/health") {
        Write-Output "[ok] runtime already healthy - reusing"
    } else {
        Write-Output "[start] Silverwing runtime (warmup may take ~1-2 min)..."
        Start-Process -FilePath $PY -ArgumentList "-m","silverwing_runtime.server" `
            -WorkingDirectory $ROOT `
            -RedirectStandardOutput (Join-Path $ROOT "_logs_runtime.log") `
            -RedirectStandardError  (Join-Path $ROOT "_logs_runtime_err.log")
        if (-not (Wait-Url "http://127.0.0.1:8010/v1/health" "runtime" 240)) { exit 1 }
    }

    # 2. Platform
    if (Test-Url "http://127.0.0.1:8000/health") {
        Write-Output "[ok] platform already healthy - reusing"
    } else {
        Write-Output "[start] JARVIS platform..."
        Start-Process -FilePath $PY -ArgumentList "jarvis_api.py" `
            -WorkingDirectory $JARVIS `
            -RedirectStandardOutput (Join-Path $ROOT "_logs_platform.log") `
            -RedirectStandardError  (Join-Path $ROOT "_logs_platform_err.log")
        if (-not (Wait-Url "http://127.0.0.1:8000/health" "platform" 90)) { exit 1 }
    }

    # 3. Frontend
    if (Test-Url "http://127.0.0.1:3000/") {
        Write-Output "[ok] frontend already up - reusing"
    } else {
        Write-Output "[start] frontend (Next.js dev - first compile may take a while)..."
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c","npm run dev" `
            -WorkingDirectory $WEB `
            -RedirectStandardOutput (Join-Path $ROOT "_logs_frontend.log") `
            -RedirectStandardError  (Join-Path $ROOT "_logs_frontend_err.log")
        if (-not (Wait-Url "http://127.0.0.1:3000/" "frontend" 180)) { exit 1 }
    }

    # 4. Automation engine (n8n) — spec §33/§50. n8n is the *automation engine*
    #    managed FROM this console (not a second admin platform). It executes
    #    actions JARVIS authorizes via the JARVIS API, authenticating with
    #    JARVIS_OAUTH_N8N_API_KEY. n8n never holds OAuth provider tokens: when a
    #    workflow needs an integration, it calls back into a JARVIS tool API that
    #    is itself confirmation-gated.
    $n8nUrl = "http://127.0.0.1:5678"
    $n8nKey  = [System.Environment]::GetEnvironmentVariable("JARVIS_OAUTH_N8N_API_KEY")
    if (Test-Url "$n8nUrl/healthz") {
        Write-Output "[ok] n8n already healthy - reusing"
    } elseif ((Get-Command n8n -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $ROOT "_launch_n8n.py"))) {
        Write-Output "[start] n8n automation engine (:5678)..."
        # Prefer the dedicated launcher (_launch_n8n.py), which binds IPv4
        # (0.0.0.0) and wires N8N_API_KEY + the project-local storages so the
        # owner user's API key from .env is always used.
        $launcher = Join-Path $ROOT "_launch_n8n.py"
        if (Test-Path $launcher) {
            $env:N8N_HOST = "0.0.0.0"
            $env:N8N_PORT = "5678"
            if (-not $env:N8N_ENCRYPTION_KEY) {
                Write-Output "[warn] N8N_ENCRYPTION_KEY missing from .env - generated one for this session"
                $bytes = New-Object byte[] 32
                [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
                $env:N8N_ENCRYPTION_KEY = [System.Convert]::ToBase64String($bytes)
            }
            Start-Process -FilePath "python" -ArgumentList $launcher `
                -WorkingDirectory $ROOT `
                -RedirectStandardOutput (Join-Path $ROOT "_logs_n8n.log") `
                -RedirectStandardError  (Join-Path $ROOT "_logs_n8n_err.log")
        } else {
            $env:N8N_HOST = "0.0.0.0"
            $env:N8N_PORT = "5678"
            # n8n encrypts its credential store with N8N_ENCRYPTION_KEY, which must be
            # a 32-byte base64 key (n8n rejects the hex JARVIS_SECRET_KEY). Prefer the
            # value sourced from .env; generate a stable one if it is missing.
            if (-not $env:N8N_ENCRYPTION_KEY) {
                Write-Output "[warn] N8N_ENCRYPTION_KEY missing from .env - generated one for this session"
                $bytes = New-Object byte[] 32
                [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
                $env:N8N_ENCRYPTION_KEY = [System.Convert]::ToBase64String($bytes)
            }
            $env:N8N_BASIC_AUTH_ACTIVE = "true"
            $env:N8N_BASIC_AUTH_USER   = "jarvis"
            if ($n8nKey) { $env:N8N_BASIC_AUTH_PASSWORD = $n8nKey }
            # Project-local n8n storages (SQLite DB + encrypted credentials) so they
            # ship with the project instead of landing in the user profile.
            $env:N8N_USER_FOLDER = (Join-Path $JARVIS "jarvis_data\n8n")
            if (-not (Test-Path $env:N8N_USER_FOLDER)) { New-Item -ItemType Directory -Path $env:N8N_USER_FOLDER -Force | Out-Null }
            $env:N8N_DATABASE_SQLITE_DATABASE = (Join-Path $env:N8N_USER_FOLDER "db.sqlite3")
            $env:JARVIS_API_URL = $env:NEXT_PUBLIC_API_URL
            if ($n8nKey) { $env:JARVIS_API_KEY = $n8nKey }
            Start-Process -FilePath "n8n" -ArgumentList "start","--port","5678" `
                -WorkingDirectory $JARVIS `
                -RedirectStandardOutput (Join-Path $ROOT "_logs_n8n.log") `
                -RedirectStandardError  (Join-Path $ROOT "_logs_n8n_err.log")
        }
        Wait-Url "$n8nUrl/healthz" "n8n" 60 | Out-Null
    } else {
        Write-Output "[skip] n8n not installed (install with `npm i -g n8n`) - automation console still usable"
    }

    Write-Output ""
    Write-Output "=== STATUS ==="
    $rt = if (Test-Url "http://127.0.0.1:8010/v1/health") { "UP" } else { "DOWN" }
    $pf = if (Test-Url "http://127.0.0.1:8000/health")  { "UP" } else { "DOWN" }
    $fe = if (Test-Url "http://127.0.0.1:3000/")        { "UP" } else { "DOWN" }
    $n8 = if (Test-Url "$n8nUrl/healthz") { "UP" } else { "DOWN" }
    Write-Output "runtime  :8010  $rt"
    Write-Output "platform :8000  $pf"
    Write-Output "frontend :3000  $fe"
    Write-Output "n8n      :5678  $n8"
    Write-Output ""

    if ($pf -eq "UP") {
        Write-Output "optional: unauthenticated smoke checks"
        Write-Output "  GET $env:SILVERWING_ENDPOINT/v1/models -> runtime model list"
        Write-Output "  GET http://127.0.0.1:8000/api/v1/sandbox/policy -> sandbox capabilities"
    }
} catch {
    Write-Output "[error] $($_.Exception.Message)"
    exit 1
}