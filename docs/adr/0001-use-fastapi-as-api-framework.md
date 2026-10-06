# ADR-0001: Use FastAPI as the Core API Framework

- **Status**: Accepted
- **Date**: 2024-01-15
- **Author**: Nicholas D. Chiv

## Context

Jarvis is an AI assistant platform that requires a modern, async-capable web framework to serve API requests, WebSocket connections, and background tasks. The framework must support:

- High-throughput async request handling
- WebSocket support for real-time chat
- Automatic OpenAPI documentation
- Middleware stacking for auth, rate limiting, metrics
- Type validation via Pydantic

## Decision

Use FastAPI as the core API framework, deployed via Uvicorn ASGI server.

## Consequences

### Positive

- Native async support enables concurrent request handling without thread pool overhead
- Automatic OpenAPI/Swagger documentation generation
- Pydantic-based request/response validation with type hints
- WebSocket support built into the framework
- Large ecosystem of middleware and extensions
- Starlette foundation provides flexibility

### Negative

- Ties the project to ASGI ecosystem (cannot easily switch to WSGI)
- FastAPI release cycle may introduce breaking changes

### Risks

- Framework lock-in mitigated by Starlette abstraction layer
- Response serialization overhead at high throughput — mitigated by streaming responses

## Alternatives Considered

### Flask

Not chosen because it is synchronous-only and requires additional libraries for async support (Quart), WebSockets, and automatic OpenAPI docs.

### Django + Django REST Framework

Not chosen because it is too heavyweight for an AI-focused platform, adds ORM coupling, and has higher startup overhead.

### Node.js Express

Not chosen because the project requires Python for AI/ML library integration.

## Compliance

All new API endpoints must use FastAPI route decorators. The `core/api/main.py` factory function is the single entry point. Middleware must be added via the standard FastAPI middleware pattern.
