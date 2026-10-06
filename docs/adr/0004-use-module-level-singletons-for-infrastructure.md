# ADR-0004: Use Module-Level Singletons for Infrastructure

- **Status**: Accepted
- **Date**: 2024-02-15
- **Author**: Nicholas D. Chiv

## Context

Jarvis infrastructure subsystems (config, vault, logging, health, metrics, etc.) need to be globally accessible without:

- Passing instances through every function call
- Circular import issues in a deeply nested module tree
- Thread/async safety concerns with shared state
- Complex DI container setup

## Decision

Use module-level `_instance` variables with `get_*()` factory functions for all infrastructure singletons.

## Consequences

### Positive

- Simple, Pythonic pattern — no DI framework needed
- Lazy initialization — instances created on first access
- Clear import paths via `get_*()` functions
- Compatible with module-level `__init__.py` exports
- Testable via fixture cleanup and re-initialization

### Negative

- Global state can make tests order-dependent if not properly cleaned
- Hard to swap implementations at runtime without clearing singletons

### Risks

- Singleton state leaks between tests — mitigated by fixture teardown that resets `_instance = None`
- Race conditions on first initialization — mitigated by using module import lock (Python guarantees this)

## Alternatives Considered

### Dependency injection container (e.g., punq, dependency-injector)

Not chosen because it adds complexity and learning curve for a pattern that Python's module system handles naturally.

### FastAPI Depends() for all infrastructure

Not chosen because it couples infrastructure access to the request cycle, making background tasks and CLI tools more complex.

## Compliance

New infrastructure subsystems must follow this pattern:

```python
_instance = None

def get_subsystem():
    global _instance
    if _instance is None:
        _instance = Subsystem()
    return _instance
```

Test fixtures must reset the singleton in teardown.
