# ADR-0003: Use Structured JSON Logging with Contextvars

- **Status**: Accepted
- **Date**: 2024-02-01
- **Author**: Nicholas D. Chiv

## Context

Jarvis needs consistent, searchable logging across microservices, async tasks, and API requests. Requirements include:

- Structured output for log aggregation (ELK/Loki/Grafana)
- Request-scoped context propagation (request_id, session_id, user_id)
- No thread-local pollution in async code
- Multiple output formats (JSON for production, text for development)

## Decision

Use custom StructuredLogger with contextvars for context propagation and JSON formatting via StructuredFormatter.

## Consequences

### Positive

- contextvars provides clean async context propagation without thread-local issues
- JSON output is natively parseable by log aggregation systems
- Request/session/user IDs automatically attached to all log entries
- Rotating file handler for persistent logs
- Audit trail support for security-relevant events

### Negative

- Custom logger implementation requires maintenance
- contextvars must be properly initialized per request (via ASGI middleware)

### Risks

- Log volume can be high in JSON format — mitigated by configurable log levels and log rotation
- contextvars leak across requests if not cleaned — mitigated by middleware cleanup in `clear_request_context()`

## Alternatives Considered

### structlog

Not chosen because of additional dependency and limited contextvars support.

### standard logging with JSON library

Not chosen because it lacks built-in context propagation.

## Compliance

All logging must use StructuredLogger. Context must be passed via the `context` keyword argument. Audit events must use the `audit()` method.
