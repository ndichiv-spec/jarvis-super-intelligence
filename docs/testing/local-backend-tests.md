# Local backend tests

The canonical backend entrypoint is `jarvis_api:app` (also re-exported by
`unified_jarvis_api.py` and `jarvis_backend.main`). Tests use the in-process
ASGI application; they do not require ports 5000 or 8000.

## Isolated Windows run

Use a new directory under the operating system temporary directory for every
run. If `JARVIS_TEST_DATABASE_PATH` is already set, the example preserves and
uses that exact path; verify it points to a disposable test database first.
The test bootstrap removes that database before creating the test schema, so
never point it at a developer, production, or otherwise valuable database.

```powershell
$providedTestDb = -not [string]::IsNullOrWhiteSpace($env:JARVIS_TEST_DATABASE_PATH)
$oldTestMode = $env:JARVIS_TEST_MODE
$oldSecretKey = $env:JARVIS_SECRET_KEY
$testRoot = $null
$dbPath = $null
if (-not $providedTestDb) {
    $testRoot = Join-Path $env:TEMP ("jarvis-tests-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $testRoot | Out-Null
    $dbPath = Join-Path $testRoot "jarvis.sqlite"
    $env:JARVIS_TEST_DATABASE_PATH = $dbPath
}
$env:JARVIS_TEST_MODE = "1"
$env:JARVIS_SECRET_KEY = "local-test-only-signing-key"
Push-Location (git rev-parse --show-toplevel)
$testExit = 0
try {
    python -m py_compile tests/test_page.py
    if ($LASTEXITCODE -ne 0) { throw "test_page.py compilation failed" }
    python -m compileall -q jarvis_backend infrastructure silverwing-backend tests
    if ($LASTEXITCODE -ne 0) { throw "Python compilation failed" }
    python -m pytest --collect-only -q
    if ($LASTEXITCODE -ne 0) { throw "pytest collection failed" }
    python -m pytest -q -m "not integration"
    $testExit = $LASTEXITCODE
}
finally {
    Pop-Location
    if (-not $providedTestDb) {
        Remove-Item Env:JARVIS_TEST_DATABASE_PATH -ErrorAction SilentlyContinue
        foreach ($path in @($dbPath, "$dbPath-shm", "$dbPath-wal", "$dbPath-journal")) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
            }
        }
        if (Test-Path -LiteralPath $testRoot) {
            Remove-Item -LiteralPath $testRoot -Force
        }
    }
    if ($null -eq $oldTestMode) {
        Remove-Item Env:JARVIS_TEST_MODE -ErrorAction SilentlyContinue
    }
    else {
        $env:JARVIS_TEST_MODE = $oldTestMode
    }
    if ($null -eq $oldSecretKey) {
        Remove-Item Env:JARVIS_SECRET_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:JARVIS_SECRET_KEY = $oldSecretKey
    }
}
if ($testExit -ne 0) { throw "Backend pytest exited with $testExit" }
```

The example removes only the disposable database files and directory it
created. Authentication, authorization, account verification, connector
ownership, and rate-limiting checks remain enabled.
Provider credentials from the developer environment are not loaded by the
test bootstrap, and test-mode provider probes do not load the parent workspace's
`.env` or inspect the developer's Kaggle credential files. Cloud routing unit
tests use named deterministic provider snapshots; they verify selection logic,
not real provider connectivity.

## Live-service integration checks

Tests that exercise the historical standalone service are marked
`integration` and skipped unless `JARVIS_LEGACY_SERVICE_URL` is explicitly
set. To run those checks, start the intended test service yourself, set that
variable to its HTTP(S) base URL, and run:

```powershell
$env:JARVIS_LEGACY_SERVICE_URL = "http://127.0.0.1:5000"
python -m pytest -m integration tests/test_smart.py tests/test_weather.py
```

The opt-in URL is not probed during test collection. Do not use production
service URLs for tests.

## Live AI-provider checks

Ordinary test runs do not call external providers. The Hugging Face revision
check and provider-control-center health check are marked `integration` and
`live_provider`. They remain skipped unless the run explicitly opts in and
provider credentials were present in the launching environment:

```powershell
$env:JARVIS_RUN_LIVE_PROVIDER_TESTS = "1"
python -m pytest -m "integration and live_provider" `
  tests/test_integration_fabric.py tests/test_capability_fabric.py
```

The test fixture restores credentials only while a marked live-provider test
is running; values are never printed. It does not load `.env` files. Select
only the marked tests when opting in, and use non-production credentials and
provider accounts. These checks are not evidence of inference unless the
specific test reports a successful real inference operation.

The root test fixture honors `JARVIS_TEST_DATABASE_PATH`, points SQLAlchemy at
that exact disposable SQLite file, and resets application stores between
tests. Set it to a fresh file outside the repository; the test bootstrap
rejects paths inside the checkout. If it is unset, each pytest process uses a
unique SQLite file in the operating system temporary directory. Tests never
delete `test_jarvis.db` from the caller's working directory.
