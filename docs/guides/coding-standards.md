# Coding Standards

## Python

### Formatting

- Use **ruff** for formatting (line length: 100)
- All code must pass `ruff format --check`
- Run `pre-commit run --all-files` before committing

### Import Order

- Standard library imports first
- Third-party imports second
- Local application imports third
- Each group separated by a blank line
- Use absolute imports

```python
import asyncio
import logging
from typing import Optional

import pytest
from fastapi import FastAPI

from infrastructure.config import ConfigLoader
from performance.concurrency import AtomicCounter
```

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Modules | snake_case | `config_loader.py` |
| Classes | PascalCase | `ConfigLoader` |
| Functions | snake_case | `get_loader()` |
| Methods | snake_case | `load_config()` |
| Variables | snake_case | `config_path` |
| Constants | UPPER_CASE | `DEFAULT_TIMEOUT` |
| Private | `_` prefix | `_instance` |
| Type vars | short PascalCase | `T`, `ConfigT` |

### Type Annotations

- All function signatures must have type annotations
- Use `Optional[T]` instead of `T | None` for Python <3.10 compatibility
- Use `from __future__ import annotations` at the top of all modules

```python
from __future__ import annotations
from typing import Optional

def load_config(path: str, default: Optional[str] = None) -> dict:
    ...
```

### Error Handling

- Raise specific exceptions (not bare `Exception`)
- Use custom exception classes from `infrastructure.errors.types`
- Always log errors with context

```python
from infrastructure.errors.types import ConfigurationError

def load(path: str) -> dict:
    if not path:
        raise ConfigurationError("Path is required", code="CONFIG_001")
```

### Async Patterns

- Use `async def` for all I/O-bound functions
- Use `asyncio.gather()` for concurrent operations
- Use `asyncio.wait_for()` for timeouts
- Avoid `asyncio.run()` in library code

```python
async def fetch_all():
    results = await asyncio.gather(
        fetch_one("a"),
        fetch_one("b"),
        return_exceptions=True,
    )
```

### Logging

- Use `StructuredLogger` from `infrastructure.logsys`
- Pass context via `context=` keyword
- Use `audit()` for security-relevant events

```python
from infrastructure.logsys import get_logger

logger = get_logger("my_module")
logger.info("Operation completed", context={"duration_ms": 42})
```

## Testing

- Test files must be named `test_*.py`
- Test classes must be named `Test*`
- Test functions must be named `test_*`
- Use `@pytest.mark.asyncio` for async tests
- Use fixtures from `tests/conftest.py`

## Documentation

- All public modules must have a module-level docstring
- All public classes must have a class-level docstring
- All public functions must have a docstring
- Follow Google-style docstring format

```python
def load_config(path: str) -> dict:
    """Load configuration from a file.

    Args:
        path: Path to the configuration file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        ConfigurationError: If the file is invalid.
    """
```

## Version Compatibility

- Target Python 3.12+
- Do not use syntax features from Python 3.13+ (e.g., `override` decorator)
- Avoid deprecated stdlib APIs
- Pin all dependencies with version ranges
