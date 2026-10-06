# Dependency Management

## Principles

1. **Explicit over implicit** — All dependencies must be declared in `requirements.txt` AND `pyproject.toml`
2. **Pinned versions** — Every dependency must have a version pin
3. **Minimal footprint** — Only add dependencies that are actively used
4. **Security first** — Vulnerable dependencies must be updated immediately

## Where to Declare Dependencies

| File | Purpose |
|------|---------|
| `requirements.txt` | Runtime dependencies with exact pins |
| `requirements-dev.txt` | Development-only dependencies |
| `pyproject.toml` | Project metadata and dependency ranges |

## Adding a New Dependency

```bash
# 1. Install the package
pip install <package>

# 2. Add to requirements.txt with exact version
pip freeze | grep <package> >> requirements.txt

# 3. Add to pyproject.toml [project.dependencies] with version range
echo '<package> >= <min>, < <max>' >> /dev/null  # manual edit

# 4. Update dev requirements if applicable
```

## Removing a Dependency

```bash
# 1. Remove from requirements.txt
# 2. Remove from pyproject.toml
# 3. Check for remaining imports
ruff check --select=F401 infrastructure/ core/
```

## Auditing Dependencies

```bash
# Security audit
safety check -r requirements.txt

# Outdated packages
pip list --outdated

# License check
pip-licenses --format=json
```

## Dependency Categories

| Category | Key Packages | Update Cadence |
|----------|-------------|----------------|
| Web Framework | FastAPI, Uvicorn, Starlette | Monthly |
| Database | SQLAlchemy, asyncpg, Alembic | Monthly |
| Cache/Queue | Redis, Celery | Monthly |
| AI/ML | OpenAI, Anthropic, LangChain, LlamaIndex | Weekly |
| Testing | pytest, pytest-asyncio, pytest-cov | Monthly |
| Quality | ruff, mypy, bandit, pre-commit | Monthly |

## Ignored Major Updates

The following packages have major version bumps ignored by Dependabot
(due to breaking changes or model compatibility):

- `torch` (manual upgrade)
- `transformers` (manual upgrade)
- `tensorflow` (manual upgrade)

## Lockfile

Currently, the project uses `requirements.txt` without a lockfile.
To generate a pinned lockfile:

```bash
pip freeze > requirements.lock.txt
```

For production deployments, consider using `pip-compile` from pip-tools:

```bash
pip install pip-tools
pip-compile requirements.txt
```
