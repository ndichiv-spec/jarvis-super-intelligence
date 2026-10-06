"""Tests for performance optimization infrastructure."""

from __future__ import annotations

import asyncio
import time
import pytest


class TestConcurrencyPrimitives:
    """Tests for performance.concurrency module."""

    @pytest.mark.asyncio
    async def test_atomic_counter(self):
        from performance.concurrency import AtomicCounter
        c = AtomicCounter()
        assert await c.get() == 0
        assert await c.inc() == 1
        assert await c.inc(5) == 6
        assert await c.dec(2) == 4
        await c.reset(10)
        assert await c.get() == 10

    @pytest.mark.asyncio
    async def test_token_bucket(self):
        from performance.concurrency import TokenBucket
        tb = TokenBucket(rate=100, burst=10)
        assert await tb.get_available() == 10
        assert await tb.acquire(5) is True
        assert await tb.acquire(5) is True
        assert await tb.acquire(1) is False

    @pytest.mark.asyncio
    async def test_read_write_lock(self):
        from performance.concurrency import ReadWriteLock
        lock = ReadWriteLock()
        await lock.acquire_read()
        assert await lock.reader_count == 1
        await lock.release_read()
        assert await lock.reader_count == 0
        await lock.acquire_write()
        assert await lock.is_write_locked is True
        await lock.release_write()
        assert await lock.is_write_locked is False

    @pytest.mark.asyncio
    async def test_keyed_lock(self):
        from performance.concurrency import KeyedLock
        lock = KeyedLock()
        l1 = await lock.acquire("a")
        l2 = await lock.acquire("b")
        assert l1 is not l2
        l1_again = await lock.acquire("a")
        assert l1 is l1_again

    @pytest.mark.asyncio
    async def test_atomic_dict(self):
        from performance.concurrency import AtomicDict
        d = AtomicDict()
        await d.set("key", "value")
        assert await d.get("key") == "value"
        assert await d.get("missing") is None
        assert await d.delete("key") is True
        assert await d.size() == 0

    @pytest.mark.asyncio
    async def test_throttle(self):
        from performance.concurrency import Throttle
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return call_count

        t = Throttle(interval=0.1)
        result1 = await t(fn)
        assert result1 == 1
        result2 = await t(fn)
        assert result2 is None  # Throttled
        assert call_count == 1
        await asyncio.sleep(0.15)
        result3 = await t(fn)
        assert result3 == 2
        assert call_count == 2


class TestTaskQueue:
    """Tests for performance.task_queue module."""

    @pytest.mark.asyncio
    async def test_enqueue_and_get_result(self):
        from performance.task_queue import WorkerPool
        pool = WorkerPool(name="test", min_workers=1, max_workers=2)
        await pool.start()

        async def simple_task(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        task_id = await pool.enqueue(simple_task(21))
        result = await pool.get_result(task_id)
        assert result == 42

        await pool.stop()

    @pytest.mark.asyncio
    async def test_task_status(self):
        from performance.task_queue import WorkerPool, TaskStatus
        pool = WorkerPool(name="status-test", min_workers=1, max_workers=2)
        await pool.start()

        async def quick():
            return "done"

        tid = await pool.enqueue(quick())
        await asyncio.sleep(0.05)
        status = pool.get_status(tid)
        assert status == TaskStatus.SUCCESS

        await pool.stop()

    @pytest.mark.asyncio
    async def test_task_failure(self):
        from performance.task_queue import WorkerPool
        pool = WorkerPool(name="fail-test", min_workers=1, max_workers=2)
        await pool.start()

        async def failing():
            raise ValueError("task error")

        tid = await pool.enqueue(failing())
        with pytest.raises(RuntimeError, match="ValueError"):
            await pool.get_result(tid)

        await pool.stop()


class TestConnectionPool:
    """Tests for performance.connection_pool module."""

    @pytest.mark.asyncio
    async def test_resource_pool_create_release(self):
        from performance.connection_pool import ResourcePool, PoolConfig

        created = []
        pool = ResourcePool(
            create=lambda: object(),
            destroy=lambda o: None,
            config=PoolConfig(max_size=5, min_size=0),
            name="test-pool",
        )

        conn = await pool.acquire()
        created.append(conn)
        await pool.release(conn)
        health = await pool.health()
        assert health["available"] >= 1
        assert health["in_use"] == 0

    @pytest.mark.asyncio
    async def test_pool_exhaustion(self):
        from performance.connection_pool import ResourcePool, PoolConfig, PoolExhaustedError

        pool = ResourcePool(
            create=lambda: object(),
            destroy=lambda o: None,
            config=PoolConfig(max_size=1, min_size=0, acquire_timeout=0.5),
            name="exhaust-test",
        )

        conn = await pool.acquire()
        with pytest.raises(PoolExhaustedError):
            await pool.acquire()
        await pool.release(conn)


class TestAIBatcher:
    """Tests for performance.ai_batcher module."""

    @pytest.mark.asyncio
    async def test_route_to_provider(self):
        from performance.ai_batcher import AIBatcher, AIProvider

        batcher = AIBatcher()

        async def mock_provider(model: str, **kwargs):
            return f"{model}: done"

        batcher.register_provider(AIProvider(
            name="test",
            models=["gpt-4"],
            call=mock_provider,
        ))

        result = await batcher.route("gpt-4", {"prompt": "hello"})
        assert result == "gpt-4: done"

    @pytest.mark.asyncio
    async def test_no_available_provider(self):
        from performance.ai_batcher import AIBatcher

        batcher = AIBatcher()
        with pytest.raises(RuntimeError, match="No available provider"):
            await batcher.route("gpt-4", {"prompt": "hello"})

    @pytest.mark.asyncio
    async def test_preferred_providers(self):
        from performance.ai_batcher import AIBatcher, AIProvider

        batcher = AIBatcher()
        calls = []

        async def p1(model: str, **kwargs):
            calls.append("p1")
            return "p1"

        async def p2(model: str, **kwargs):
            calls.append("p2")
            return "p2"

        batcher.register_provider(AIProvider(name="provider-a", models=["m"], call=p1))
        batcher.register_provider(AIProvider(name="provider-b", models=["m"], call=p2))

        result = await batcher.route("m", {}, preferred_providers=["provider-b"])
        assert result == "p2"
        assert calls == ["p2"]


class TestContextOptimizer:
    """Tests for performance.context_optimizer module."""

    @pytest.mark.asyncio
    async def test_add_and_get_context(self):
        from performance.context_optimizer import ContextOptimizer

        opt = ContextOptimizer(max_tokens=1000)
        await opt.add_message("user", "Hello")
        ctx = await opt.get_context()
        assert len(ctx) == 1
        assert ctx[0]["role"] == "user"
        assert ctx[0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_multiple_messages(self):
        from performance.context_optimizer import ContextOptimizer

        opt = ContextOptimizer(max_tokens=1000)
        await opt.add_message("user", "Hi")
        await opt.add_message("assistant", "Hello!")
        ctx = await opt.get_context()
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert ctx[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_clear(self):
        from performance.context_optimizer import ContextOptimizer

        opt = ContextOptimizer(max_tokens=1000)
        await opt.add_message("user", "data")
        await opt.clear()
        assert await opt.get_token_count() == 0


class TestLoadHandler:
    """Tests for performance.load_handler module."""

    @pytest.mark.asyncio
    async def test_load_metrics_level_normal(self):
        from performance.load_handler import LoadMetrics, LoadLevel
        m = LoadMetrics()
        assert m.level == LoadLevel.NORMAL

    @pytest.mark.asyncio
    async def test_load_metrics_overloaded(self):
        from performance.load_handler import LoadMetrics, LoadLevel
        m = LoadMetrics(cpu_percent=99, memory_percent=98, active_requests=200, error_rate=0.5)
        assert m.level == LoadLevel.OVERLOADED

    @pytest.mark.asyncio
    async def test_load_shed_error(self):
        from performance.load_handler import LoadShedder, LoadShedError, LoadMetrics
        shedder = LoadShedder()
        await shedder.update_metrics(LoadMetrics(
            cpu_percent=99, memory_percent=98,
            active_requests=200, error_rate=0.5,
        ))

        with pytest.raises(LoadShedError):
            await shedder.execute_or_shed(lambda: asyncio.sleep(0), priority=0)


class TestResponseOptimizer:
    """Tests for performance.response_optimizer module."""

    def test_etag_generation(self):
        from performance.response_optimizer import ETagManager
        mgr = ETagManager()
        etag1 = mgr.generate({"a": 1})
        etag2 = mgr.generate({"a": 1})
        assert etag1 == etag2
        etag3 = mgr.generate({"a": 2})
        assert etag1 != etag3

    def test_optimize_304(self):
        from performance.response_optimizer import ResponseOptimizer
        opt = ResponseOptimizer()
        data = {"message": "hello"}
        etag = opt._etag_manager.generate(data)
        result = opt.optimize(data, client_etag=etag)
        assert result["status_code"] == 304

    def test_optimize_200(self):
        from performance.response_optimizer import ResponseOptimizer
        opt = ResponseOptimizer()
        result = opt.optimize({"msg": "hi"})
        assert result["status_code"] == 200

    def test_field_filtering(self):
        from performance.response_optimizer import ResponseOptimizer
        opt = ResponseOptimizer()
        data = {"id": 1, "name": "test", "secret": "hidden"}
        result = opt.optimize(data, fields=["id", "name"])
        assert result["data"] == {"id": 1, "name": "test"}


class TestStartupOptimizer:
    """Tests for performance.startup_optimizer module."""

    @pytest.mark.asyncio
    async def test_register_and_initialize(self):
        from performance.startup_optimizer import StartupOptimizer
        opt = StartupOptimizer()
        inited = []

        @opt.register("test")
        async def init_test():
            inited.append("ok")
            return "done"

        results = await opt.initialize()
        assert results["test"].name == "READY"
        assert inited == ["ok"]

    @pytest.mark.asyncio
    async def test_dependency_ordering(self):
        from performance.startup_optimizer import StartupOptimizer
        opt = StartupOptimizer()
        order = []

        @opt.register("db")
        async def init_db():
            order.append("db")

        @opt.register("app", depends_on=["db"])
        async def init_app():
            order.append("app")

        await opt.initialize()
        assert order == ["db", "app"]

    @pytest.mark.asyncio
    async def test_critical_failure(self):
        from performance.startup_optimizer import StartupOptimizer, StartupError
        opt = StartupOptimizer()

        @opt.register("failing", critical=True)
        async def fail():
            raise RuntimeError("boom")

        with pytest.raises(StartupError):
            await opt.initialize()

    @pytest.mark.asyncio
    async def test_non_critical_failure(self):
        from performance.startup_optimizer import StartupOptimizer
        opt = StartupOptimizer()

        @opt.register("failing", critical=False)
        async def fail():
            raise RuntimeError("boom")

        results = await opt.initialize()
        assert results["failing"].name == "FAILED"


class TestTelemetry:
    """Tests for performance.telemetry module."""

    @pytest.mark.asyncio
    async def test_counter(self):
        from performance.telemetry import TelemetryCollector
        tc = TelemetryCollector()
        c = tc.counter("requests")
        assert await c.get() == 0
        await c.inc()
        assert await c.get() == 1
        await c.inc(5)
        assert await c.get() == 6

    def test_histogram(self):
        from performance.telemetry import TelemetryCollector
        tc = TelemetryCollector()
        h = tc.histogram("latency")
        h.observe(50)
        h.observe(200)
        snap = h.snapshot()
        assert snap["total"] == 2

    @pytest.mark.asyncio
    async def test_emit_hook(self):
        from performance.telemetry import TelemetryCollector
        tc = TelemetryCollector()
        called = []

        async def my_hook(**kwargs):
            called.append(kwargs)

        tc.on("test_event", my_hook)
        await tc.emit("test_event", data=42)
        assert len(called) == 1
        assert called[0]["data"] == 42


class TestPerformanceFacade:
    """Tests for performance.__init__ (PerformanceFacade)."""

    @pytest.mark.asyncio
    async def test_initialize_and_start(self):
        from performance import PerformanceFacade
        perf = PerformanceFacade()
        await perf.initialize()
        await perf.start()
        assert perf._initialized is True
        assert perf._running is True
        stats = perf.get_stats()
        assert "task_queue" in stats
        assert "connection_pools" in stats
        await perf.stop()
        assert perf._running is False

    @pytest.mark.asyncio
    async def test_http_pool_creation(self):
        from performance import PerformanceFacade
        perf = PerformanceFacade()
        await perf.initialize()
        pool = perf.get_http_pool("https://example.com", max_size=5)
        assert pool is not None
        await perf.stop()

    @pytest.mark.asyncio
    async def test_global_singleton(self):
        from performance import get_performance
        p1 = get_performance()
        p2 = get_performance()
        assert p1 is p2
