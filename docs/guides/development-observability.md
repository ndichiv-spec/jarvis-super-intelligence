# Development Observability

## Logging Standards

### Log Levels

| Level | When to Use |
|-------|-------------|
| `DEBUG` | Detailed diagnostic info (development only) |
| `INFO` | Normal operational events (startup, config loaded, request completed) |
| `WARNING` | Unexpected but handled issues (retry attempt, fallback used) |
| `ERROR` | Recoverable errors (API call failed, component degraded) |
| `CRITICAL` | Unrecoverable errors (system cannot continue) |

### Required Context

Every log call should include relevant context:

```python
logger.info("Request completed", context={
    "method": request.method,
    "path": request.url.path,
    "duration_ms": duration_ms,
    "status_code": response.status_code,
})
```

### Audit Logging

Use `logger.audit()` for security-relevant events:

```python
logger.audit("user_login", "auth", user_id=user.id, details={"ip": client_ip})
```

## Performance Metrics

### Where Metrics Are Collected

| Metric | Source | Location |
|--------|--------|----------|
| Request duration | FastAPI middleware | `core/api/main.py` (MetricsMiddleware) |
| Cache hit rate | CacheManager | `performance/cache_manager.py` |
| Circuit breaker state | CircuitBreaker | `infrastructure/resilience/circuit_breaker.py` |
| Worker pool depth | WorkerPool | `performance/task_queue.py` |
| Connection pool usage | ResourcePool | `performance/connection_pool.py` |

### Viewing Metrics

```bash
# Development metrics endpoint
curl http://localhost:8000/metrics

# Prometheus-formatted metrics (when configured)
curl http://localhost:8000/api/v1/monitoring/metrics
```

## Profiling

### Local Profiling

```bash
# Profile a specific function
python -m cProfile -o profile.stats scripts/check_code_quality.py

# Analyze results
python -m pstats profile.stats
```

### Using py-spy (sampling profiler)

```bash
pip install py-spy
py-spy record -o profile.svg --pid $(pgrep -f uvicorn)
```

## Development Server Health

```bash
# Health check
curl http://localhost:8000/health

# Readiness probe
curl http://localhost:8000/api/v1/health/readiness

# Startup status
curl http://localhost:8000/api/v1/health/startup
```

## Common Debug Patterns

### 1. Structured log search

```bash
# Search for errors in JSON logs
cat logs/jarvis.log | python -c "import sys,json; [print(json.loads(l)['message']) for l in sys.stdin if json.loads(l).get('level')=='ERROR']"
```

### 2. Request tracing

Set `REQUEST_ID` header in your HTTP client to trace a request through all services:

```bash
curl -H "X-Request-ID: my-trace-id" http://localhost:8000/api/v1/health
```

### 3. Circuit breaker health

```bash
python -c "
from infrastructure.resilience.circuit_breaker import CircuitBreaker
# Check breaker states
"
```

## Development Metrics Dashboard

When running locally, metrics are available at `/metrics`:

- Active requests
- Request duration (p50, p95, p99)
- Cache hit rate
- Error rate
- Circuit breaker states
- Worker pool depth
- Connection pool utilization

## Tracing

The telemetry system supports distributed tracing via context propagation:

```python
from performance.telemetry import TelemetryTracer

tracer = TelemetryTracer()
async with tracer.span("database_query", db="postgres") as span:
    results = await db.query("SELECT ...")
```

Spans are captured by the TelemetryCollector and can be exported to
Jaeger or Zipkin when configured.
