"""
Jarvis Infrastructure Layer.

Centralized security, observability, resilience, sandboxing, and performance subsystems.
"""

from infrastructure.config.loader import ConfigLoader
from infrastructure.vault.manager import SecretsManager
from infrastructure.logsys.structured import get_logger, set_request_context, clear_request_context
from infrastructure.health.checker import get_health_checker, HealthChecker
from infrastructure.startup.validator import get_startup_validator
from infrastructure.observability import (
    get_metrics_collector, MetricsCollector,
    get_tracer, Tracer,
    ObservabilityMiddleware,
)
from infrastructure.security.auth import AuthMiddleware, JWTAuthenticator
from infrastructure.security.rate_limiter import RateLimiter
from infrastructure.security.api_key import ApiKeyManager
from infrastructure.resilience.circuit_breaker import CircuitBreaker
from infrastructure.resilience.retry import RetryStrategy
from infrastructure.resilience.fallback import FallbackChain, DegradationPolicy, StaleCacheFallback
from infrastructure.resilience.ai_provider import AIProviderResilience
from infrastructure.errors.handler import ErrorHandler, error_response
from infrastructure.errors.tracker import ErrorTracker, get_error_tracker
from infrastructure.errors.types import JarvisError
from infrastructure.sandbox.executor import SandboxExecutor, ExecutionPolicy
from infrastructure.sandbox.policy import PolicyEngine, Capability
from infrastructure.deploy.manager import DeploymentManager, DeploymentMode


class JarvisInfrastructure:
    """
    Central integration point for all infrastructure subsystems.

    Wires together config, secrets, logging, health, observability,
    security, resilience, errors, and sandboxing into a single,
    easy-to-initialize object.

    Usage:
        infra = JarvisInfrastructure(
            app_name="jarvis",
            environment="production",
        )
        app = infra.instrument(app)

        @app.get("/health")
        async def health():
            return await infra.health_status()

        @app.get("/metrics")
        async def metrics():
            return infra.metrics_snapshot()
    """

    def __init__(
        self,
        app_name: str = "jarvis",
        version: str = "3.0.0",
        environment: str = "development",
        config_path: str = "",
    ):
        self.app_name = app_name
        self.version = version
        self.environment = environment

        # Core services
        self.config = ConfigLoader()
        if config_path:
            self.config = ConfigLoader([config_path])
        self.secrets = SecretsManager()

        # Logging
        self.logger = get_logger(app_name)
        self.audit_logger = get_logger(f"{app_name}.audit")

        # Observability
        self.metrics = get_metrics_collector()
        self.tracer = get_tracer()
        self.error_tracker = get_error_tracker()

        # Health
        self.health = get_health_checker()

        # Security
        self.auth = JWTAuthenticator()
        self.rate_limiter = RateLimiter()
        self.api_key_manager = ApiKeyManager()

        # Resilience
        self.ai_resilience = AIProviderResilience()
        self.degradation = DegradationPolicy()
        self.circuit_breakers: dict = {}

        # Sandbox
        self.sandbox_policy = PolicyEngine.default_policy()
        self.sandbox_executor = SandboxExecutor()

        # Startup
        self.startup_validator = get_startup_validator()

        # Performance
        self.performance = None

    async def init_performance(self):
        """Lazily initialize and start performance subsystems."""
        from performance import get_performance
        self.performance = get_performance()
        await self.performance.initialize()
        await self.performance.start()

    async def stop_performance(self):
        """Stop performance subsystems."""
        if self.performance:
            await self.performance.stop()

    def instrument(self, app, **kwargs):
        """Apply all standard middlewares to a FastAPI/Starlette app."""
        app.add_middleware(ErrorHandler, **kwargs)
        return app

    def auth_middleware(self, excluded_paths: tuple = ("/health", "/docs", "/openapi.json", "/metrics")):
        return lambda app: AuthMiddleware(app, excluded_paths=excluded_paths)

    def error_middleware(self, include_traceback: bool = False):
        return lambda app: ErrorHandler(app, include_traceback=include_traceback)

    def observability_middleware(self):
        return ObservabilityMiddleware

    async def health_status(self, probe: str = "readiness"):
        from infrastructure.health.checker import ComponentStatus
        checker = get_health_checker()
        status = await checker.get_status(probe=probe)
        return {
            "status": status.status.value,
            "summary": status.summary,
            "version": status.version,
            "app": status.app_name,
            "environment": status.environment,
            "uptime_seconds": status.uptime_seconds,
            "timestamp": status.timestamp,
            "components": {
                n: {"status": c.status.value, "message": c.message}
                for n, c in status.components.items()
            },
        }

    def metrics_snapshot(self):
        return self.metrics.snapshot()

    def error_stats(self):
        return self.error_tracker.get_stats()

    async def startup_check(self):
        return await self.startup_validator.run()

    def circuit_breaker(self, name: str, **kwargs) -> CircuitBreaker:
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
        return self.circuit_breakers[name]

    def register_health_check(self, name: str, check_fn, **kwargs):
        self.health.register_func(name, check_fn, **kwargs)

    def register_ai_provider(self, name: str, fn, **kwargs):
        self.ai_resilience.register(name, fn, **kwargs)
