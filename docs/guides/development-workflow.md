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
uvicorn core.api.main:app --reload --port 8000
```

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
      "args": ["core.api.main:app", "--reload", "--port", "8000"],
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
