"""Tests for infrastructure.resilience — CircuitBreaker, RetryStrategy, FallbackChain."""

from __future__ import annotations
import asyncio
import pytest
from infrastructure.resilience.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from infrastructure.resilience.fallback import FallbackChain, FallbackProvider, FallbackResult


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self, circuit_breaker):
        assert circuit_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_call(self, circuit_breaker):
        async def success():
            return "ok"
        result = await circuit_breaker.call(success)
        assert result == "ok"
        assert circuit_breaker.stats.total_calls == 1
        assert circuit_breaker.stats.success_calls == 1

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self, circuit_breaker):
        async def fail():
            raise ValueError("fail")
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.call(fail)
        assert circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_when_open(self, circuit_breaker):
        async def fail():
            raise ValueError("fail")
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.call(fail)
        with pytest.raises(CircuitOpenError):
            await circuit_breaker.call(fail)

    @pytest.mark.asyncio
    async def test_half_open_recovers(self, circuit_breaker):
        circuit_breaker.failure_threshold = 2
        circuit_breaker.recovery_timeout = 0.1
        call_count = 0
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("fail")
            return "recovered"
        for _ in range(2):
            with pytest.raises(ValueError):
                await circuit_breaker.call(flaky)
        assert circuit_breaker.state == CircuitState.OPEN
        await asyncio.sleep(0.15)
        result = await circuit_breaker.call(flaky)
        assert result == "recovered"

    @pytest.mark.asyncio
    async def test_reset(self, circuit_breaker):
        async def fail():
            raise ValueError("fail")
        for _ in range(3):
            with pytest.raises(ValueError):
                await circuit_breaker.call(fail)
        circuit_breaker.reset()
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_context_manager_success(self, circuit_breaker):
        async with circuit_breaker:
            pass
        assert circuit_breaker.stats.success_calls == 1

    @pytest.mark.asyncio
    async def test_context_manager_failure(self, circuit_breaker):
        with pytest.raises(ValueError):
            async with circuit_breaker:
                raise ValueError("fail")
        assert circuit_breaker.stats.failed_calls == 1

    def test_to_dict(self, circuit_breaker):
        d = circuit_breaker.to_dict()
        assert d["state"] == "closed"
        assert "stats" in d
        assert "config" in d


class TestRetryStrategy:
    def test_default_retries(self, retry_strategy):
        assert retry_strategy.max_retries == 3

    def test_get_delay_increases(self, retry_strategy):
        d1 = retry_strategy.get_delay(1)
        d2 = retry_strategy.get_delay(2)
        assert d2 >= d1

    def test_get_delay_capped(self):
        from infrastructure.resilience import RetryStrategy
        rs = RetryStrategy(max_retries=10, base_delay=1.0, max_delay=5.0, jitter=False)
        d10 = rs.get_delay(10)
        assert d10 <= 5.0

    def test_is_retryable_default(self, retry_strategy):
        assert retry_strategy.is_retryable(ValueError("test")) is True
        assert retry_strategy.is_retryable(RuntimeError("test")) is True

    def test_is_retryable_filtered(self):
        from infrastructure.resilience import RetryStrategy
        rs = RetryStrategy(retryable_exceptions=(ValueError,))
        assert rs.is_retryable(ValueError("test")) is True
        assert rs.is_retryable(TypeError("test")) is False

    @pytest.mark.asyncio
    async def test_retry_async_success_after_retries(self):
        from infrastructure.resilience import retry, RetryStrategy
        call_count = 0
        async def succeeds_on_second():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"
        result = await retry(
            succeeds_on_second,
            strategy=RetryStrategy(max_retries=3, base_delay=0.01, max_delay=0.1),
        )
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        from infrastructure.resilience import retry, RetryStrategy
        async def always_fails():
            raise ValueError("persistent")
        with pytest.raises(ValueError):
            await retry(
                always_fails,
                strategy=RetryStrategy(max_retries=2, base_delay=0.01, max_delay=0.1),
            )


class TestFallbackChain:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        chain = FallbackChain([
            FallbackProvider("primary", lambda: "primary_result"),
        ])
        result = await chain.execute()
        assert result.success is True
        assert result.value == "primary_result"
        assert result.provider == "primary"

    @pytest.mark.asyncio
    async def test_fallback_used_when_primary_fails(self):
        def primary():
            raise ValueError("fail")
        def secondary():
            return "fallback_result"
        chain = FallbackChain([
            FallbackProvider("primary", primary),
            FallbackProvider("secondary", secondary),
        ])
        result = await chain.execute()
        assert result.success is True
        assert result.value == "fallback_result"
        assert result.provider == "secondary"

    @pytest.mark.asyncio
    async def test_all_fail(self):
        def always_fail():
            raise RuntimeError("fail")
        chain = FallbackChain([
            FallbackProvider("a", always_fail),
            FallbackProvider("b", always_fail),
        ])
        result = await chain.execute()
        assert result.success is False
        assert "failed" in (result.error or "")

    @pytest.mark.asyncio
    async def test_empty_providers(self):
        chain = FallbackChain([])
        result = await chain.execute()
        assert result.success is False
