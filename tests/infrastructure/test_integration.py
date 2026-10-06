"""Integration tests for cross-subsystem infrastructure workflows."""

from __future__ import annotations
import pytest
import asyncio


class TestConfigAndVaultIntegration:
    def test_config_loader_accepts_vault_values(self):
        from infrastructure.config import ConfigLoader
        from infrastructure.vault import SecretsManager
        loader = ConfigLoader()
        vault = SecretsManager()
        vault.set("api_key", "sk-test123")
        loader.load_from_dict({"api_key": vault.get("api_key")})
        assert loader.get("api_key") == "sk-test123"

    def test_env_var_overrides_vault(self):
        from infrastructure.config import ConfigLoader
        from tests.utils.helpers import temp_env_vars
        loader = ConfigLoader()
        loader.load_from_dict({"api_key": "from_config"})
        with temp_env_vars({"JARVIS_API_KEY": "from_env"}):
            loader.load_from_env(prefix="JARVIS_")
            assert loader.get("api_key") == "from_env"


class TestHealthAndStartupIntegration:
    def test_health_checker_exposes_startup_status(self):
        from infrastructure.health import HealthChecker
        from infrastructure.startup import StartupValidator
        checker = HealthChecker()
        validator = StartupValidator()
        checker.register("startup")
        result = validator.validate()
        if result["passed"]:
            checker.report_healthy("startup")
        else:
            checker.report_unhealthy("startup", error="Startup checks failed")
        status = checker.get_status()
        assert "startup" in status["components"]

    def test_component_healthy_after_validator_passes(self):
        from infrastructure.health import HealthChecker
        checker = HealthChecker()
        checker.register("config", required=True)
        checker.report_healthy("config")
        status = checker.get_status()
        assert status["healthy"] is True


class TestSecurityAndRateLimitIntegration:
    def test_authenticated_requests_count_towards_limit(self):
        from infrastructure.security import JWTAuthenticator, RateLimiter
        auth = JWTAuthenticator(secret="test-secret-32-chars-long-for-hmac!")
        limiter = RateLimiter(default_limit=5)
        token = auth.create_token("user1")
        assert auth.verify(token) is not None
        for _ in range(5):
            result = limiter.check("user1")
            assert result.allowed is True
        result = limiter.check("user1")
        assert result.allowed is False

    def test_different_users_have_independent_limits(self):
        from infrastructure.security import RateLimiter
        limiter = RateLimiter(default_limit=2)
        limiter.check("user_a")
        limiter.check("user_a")
        assert limiter.check("user_a").allowed is False
        assert limiter.check("user_b").allowed is True


class TestErrorAndObservabilityIntegration:
    def test_error_tracker_feeds_metrics(self):
        from infrastructure.errors import ErrorTracker, ErrorEvent
        from infrastructure.observability import MetricsCollector
        tracker = ErrorTracker()
        metrics = MetricsCollector()
        error_count = metrics.counter("errors")
        tracker.add_exporter(lambda event: error_count.inc())
        tracker.track(ErrorEvent(code="e1", subsystem="core"))
        assert error_count.value == 1
        tracker.track(ErrorEvent(code="e2", subsystem="plugins"))
        assert error_count.value == 2

    def test_errors_increment_counter_via_metrics(self):
        from infrastructure.errors import ErrorTracker, ErrorEvent
        from infrastructure.observability import MetricsCollector
        tracker = ErrorTracker()
        metrics = MetricsCollector()
        counter = metrics.counter("test_errors")
        tracker.add_exporter(lambda e: counter.inc())
        for _ in range(3):
            tracker.track(ErrorEvent(code="x", subsystem="test"))
        assert counter.value == 3


class TestResilienceAndErrorIntegration:
    @pytest.mark.asyncio
    async def test_circuit_breaker_records_errors(self):
        from infrastructure.resilience import CircuitBreaker
        from infrastructure.errors import ErrorTracker, ErrorEvent
        breaker = CircuitBreaker(name="integration-test", failure_threshold=2, recovery_timeout=60)
        tracker = ErrorTracker()
        async def fail():
            raise ConnectionError("API unavailable")
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await breaker.call(fail)
        assert breaker.state.value == "open"
        tracker.track(ErrorEvent(code="circuit_open", subsystem="resilience",
                                 context={"breaker": "integration-test"}))
        events = tracker.get_events(subsystem="resilience")
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_retry_with_fallback_integration(self):
        from infrastructure.resilience import retry, RetryStrategy
        from infrastructure.resilience.fallback import FallbackChain, FallbackProvider
        call_count = 0
        async def flaky_primary():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "primary_result"
        def static_fallback():
            return "fallback_result"
        chain = FallbackChain([
            FallbackProvider("primary", flaky_primary, is_async=True),
            FallbackProvider("fallback", static_fallback),
        ])
        result = await chain.execute()
        assert result.success is True
        assert result.provider in ("primary", "fallback")


class TestFullObservabilityPipeline:
    @pytest.mark.asyncio
    async def test_trace_metrics_and_errors(self):
        from infrastructure.observability import Tracer, MetricsCollector
        from infrastructure.errors import ErrorTracker, ErrorEvent
        tracer = Tracer(service_name="integration")
        metrics = MetricsCollector()
        tracker = ErrorTracker()
        span_counter = metrics.counter("spans")
        tracer.add_exporter(lambda spans: span_counter.inc(len(spans)))
        with tracer.span("op1"):
            pass
        with tracer.span("op2"):
            pass
        tracer.flush()
        assert span_counter.value >= 2
        tracker.track(ErrorEvent(code="test", subsystem="observability"))
        stats = tracker.get_stats()
        assert stats["total_events"] >= 1


class TestKnowledgeAndStoreIntegration:
    def test_document_ingest_and_search(self):
        from infrastructure.knowledge import KnowledgeStore, KnowledgeIngestor, ChunkConfig
        from infrastructure.knowledge.types import ChunkingStrategy, KnowledgeStatus, SearchQuery
        store = KnowledgeStore()
        ingestor = KnowledgeIngestor(
            ChunkConfig(chunk_size=50, min_chunk_size=10, strategy=ChunkingStrategy.FIXED_SIZE)
        )
        content = "Machine learning is transforming artificial intelligence research."
        doc = store.create_document(content, status=KnowledgeStatus.ACTIVE)
        chunks = ingestor.ingest(content).chunks
        for c in chunks:
            c.document_id = doc.id
            store.add_chunk(c)
        query = SearchQuery(text="machine learning", top_k=5, min_score=0.0)
        results = store.search(query)
        assert len(results) > 0
        assert results[0].score > 0

    def test_document_lifecycle(self):
        from infrastructure.knowledge import KnowledgeStore, LearningController, LearningConfig
        from infrastructure.knowledge.types import KnowledgeSource, KnowledgeStatus
        store = KnowledgeStore()
        controller = LearningController(store, LearningConfig(require_approval=True))
        request = controller.propose("Test content", KnowledgeSource.MANUAL, user_id="test")
        assert request.id is not None
        assert controller.get_pending_count() == 1
        doc = controller.approve(request.id, user_id="admin")
        assert doc is not None
        assert doc.status == KnowledgeStatus.ACTIVE
        assert controller.get_pending_count() == 0
        controller.rollback(doc.id, user_id="admin")
        assert store.get_document(doc.id).status == KnowledgeStatus.REJECTED

    @pytest.mark.asyncio
    async def test_rag_pipeline_with_store(self):
        from infrastructure.knowledge import (
            KnowledgeStore, KnowledgeRetriever, KnowledgeIngestor, ChunkConfig, RAGPipeline,
        )
        from infrastructure.knowledge.types import ChunkingStrategy, KnowledgeStatus
        store = KnowledgeStore()
        ingestor = KnowledgeIngestor(
            ChunkConfig(chunk_size=50, min_chunk_size=10, strategy=ChunkingStrategy.FIXED_SIZE)
        )
        doc = store.create_document(
            "Python is a versatile programming language.", status=KnowledgeStatus.ACTIVE,
        )
        chunks = ingestor.ingest(doc.content).chunks
        for c in chunks:
            c.document_id = doc.id
            store.add_chunk(c)
        retriever = KnowledgeRetriever(store)
        pipeline = RAGPipeline(retriever)
        result = await pipeline.generate("Tell me about Python")
        assert result.answer
        assert len(result.context.chunks) > 0
