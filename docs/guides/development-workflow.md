# Development Workflow Guide

## Prerequisites

- Python 3.12+
- Git
- Make (optional, for Makefile targets)

## One-Time Setup

```bash
# Clone the repository
git clone https://github.com/ndichiv-spec/jarvis-cloud.git
cd jarvis-cloud

# Create virtual environment
python -m venv .venv

# Activate (choose one):
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg

# Copy environment configuration
cp .env.example .env
# Edit .env with your settings
```

## Daily Development Loop

```bash
# Activate virtual environment
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1

# Run tests as you develop
pytest tests/path/to/test_file.py -v

# Run linting
pre-commit run --all-files

# Run type checking
mypy infrastructure/ core/

# Start the development server
python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000
```

## Local JARVIS Runtime (Windows PowerShell)

The canonical FastAPI entrypoint is `jarvis_backend.main:app`. For local
acceptance without Docker or PostgreSQL, SQLite is the persistent database;
the path below keeps local runtime data separate from test databases. Start
each process in its own PowerShell terminal from the repository root.

**Backend**

```powershell
Set-Location F:\AI\Jarvis-super-intelligence-
.\.venv\Scripts\Activate.ps1
Remove-Item Env:JARVIS_TEST_MODE -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force .\jarvis_data | Out-Null
$env:DATABASE_URL = 'sqlite:///F:/AI/Jarvis-super-intelligence-/jarvis_data/local-runtime.db'
$env:CELERY_BROKER_URL = 'redis://127.0.0.1:6379/1'
python -m uvicorn jarvis_backend.main:app --host 127.0.0.1 --port 8000
```

**Redis** (only if Redis is not already running locally)

```powershell
redis-server --bind 127.0.0.1 --port 6379
```

**Celery worker** (a separate terminal; consumes the command and research queues)

```powershell
Set-Location F:\AI\Jarvis-super-intelligence-
.\.venv\Scripts\Activate.ps1
$env:DATABASE_URL = 'sqlite:///F:/AI/Jarvis-super-intelligence-/jarvis_data/local-runtime.db'
$env:CELERY_BROKER_URL = 'redis://127.0.0.1:6379/1'
celery -A jarvis_backend.celery_app:celery_app worker --loglevel=INFO --pool=solo --queues=commands,research
```

**Frontend** (a separate terminal)

```powershell
Set-Location F:\AI\Jarvis-super-intelligence-\frontend\web
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8000'
$env:NEXT_PUBLIC_ENVIRONMENT = 'development'
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`, authenticate through the normal JARVIS login
flow, and use the Chat page. Do not set `JARVIS_TEST_MODE`; it selects test
stores and prevents normal project environment loading. Provider credentials
are read through the existing backend configuration loader and must never be
copied into frontend variables.

SQLite runs in-process, so no separate database server is needed for this
local setup. Silverwing is optional: this environment's configured endpoint
is unreachable and its in-process import fails, so starting the standalone
Silverwing service is not part of the verified local chat path. Do not report
it available unless its own runtime and inference check succeed.

## Code Quality Checks

Before committing, ensure:

1. **Tests pass**: `pytest tests/ -x --tb=short`
2. **Linting passes**: `pre-commit run --all-files`
3. **Type checks pass**: `mypy infrastructure/ core/`
4. **Security scan**: `bandit -r infrastructure/ core/`

Quick check script:
```bash
python scripts/check_code_quality.py
```

## Commit Workflow

1. **Stage changes**: `git add <files>`
2. **Commit with Conventional Commits format**:
   ```
   feat(scope): description
   
   Body explaining the change.
   
   Closes #123
   ```
3. **Pre-commit hooks run automatically** on `git commit`

## Branch Strategy

| Branch | Purpose | Base |
|--------|---------|------|
| `main` | Production-ready code | — |
| `develop` | Integration branch | `main` |
| `feature/*` | New features | `develop` |
| `fix/*` | Bug fixes | `develop` |
| `docs/*` | Documentation | `develop` |
| `refactor/*` | Code refactoring | `develop` |

## Pull Request Process

1. Rebase your branch on latest `develop`
2. Push to your fork
3. Create PR against `develop`
4. Fill in the PR template completely
5. Request review from maintainers
6. Address all review comments
7. Squash-merge when approved

## Running Different Test Suites

```bash
# All tests
pytest tests/

# Specific subsystems
pytest tests/infrastructure/
pytest tests/api/
pytest tests/performance/

# By marker
pytest tests/ -m unit
pytest tests/ -m integration
pytest tests/ -m slow

# With coverage
pytest tests/ --cov=infrastructure --cov=performance

# Parallel (requires pytest-xdist)
pytest tests/ -n auto

# Performance tests
locust -f tests/performance/locustfile.py --headless -u 10 -r 1
```

## Debugging Tips

### VS Code Launch Configuration

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "API Server",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["jarvis_backend.main:app", "--reload", "--port", "8000"],
      "jinja": true
    },
    {
      "name": "Debug Tests",
      "type": "python",
      "request": "test",
      "purpose": ["debug-test"],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ]
}
```

### Log Levels

Set `LOG_LEVEL=DEBUG` in `.env` for verbose output. Structured JSON logs are written to `logs/jarvis.log`.
