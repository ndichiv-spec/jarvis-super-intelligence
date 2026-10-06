# ADR-0002: Use pytest with pytest-asyncio for Testing

- **Status**: Accepted
- **Date**: 2024-01-15
- **Author**: Nicholas D. Chiv

## Context

Jarvis codebase is primarily async Python with FastAPI, SQLAlchemy async, and various async infrastructure components. The testing framework must:

- Support async test functions natively
- Handle pytest-asyncio event loop management
- Support fixtures for complex dependency injection
- Generate coverage reports
- Integrate with CI/CD pipelines
- Support parallel test execution

## Decision

Use pytest as the test runner with pytest-asyncio (asyncio_mode=auto) for async test support.

## Consequences

### Positive

- Async tests are first-class citizens with `asyncio_mode=auto`
- Rich fixture system enables clean dependency injection
- Plugin ecosystem (pytest-cov, pytest-xdist, pytest-mock, pytest-benchmark)
- CI/CD integration via JUnit XML output and coverage reports
- Parallel execution via pytest-xdist

### Negative

- Fixture scope management requires care with async fixtures
- pytest-asyncio mode changes (strict vs auto) can break existing tests

### Risks

- Asyncio mode migration (from auto to strict) may require fixture scope annotations — mitigated by pinning pytest-asyncio>=0.24.0 with mode=auto
- Async fixture cleanup requires try/finally or yield fixtures

## Alternatives Considered

### unittest with asyncio

Not chosen because it requires verbose boilerplate, lacks fixture injection, and has limited plugin support.

### nose2

Not chosen because it has a smaller ecosystem and slower development cycle.

## Compliance

All test files must:
- Follow the `test_*.py` naming convention
- Use `@pytest.mark.asyncio` for async test functions
- Use fixtures from `tests/conftest.py` or `tests/infrastructure/conftest.py`
- Be organized in `tests/` by subsystem
