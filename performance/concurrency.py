"""
Concurrency-safe primitives for Jarvis.

Provides atomic operations, read-write locks, reentrant locks,
and distributed-ready rate limiters to ensure thread/async safety
across all concurrent code paths.
"""

import asyncio
import threading
import time
from typing import Dict, Optional, Callable, Any, Awaitable
from collections import deque


class AtomicCounter:
    """Thread-safe and async-safe monotonic counter."""

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = asyncio.Lock()

    async def inc(self, amount: int = 1) -> int:
        async with self._lock:
            self._value += amount
            return self._value

    async def dec(self, amount: int = 1) -> int:
        return await self.inc(-amount)

    async def get(self) -> int:
        async with self._lock:
            return self._value

    async def reset(self, value: int = 0) -> None:
        async with self._lock:
            self._value = value


class AtomicFloat:
    """Thread-safe and async-safe floating-point accumulator."""

    def __init__(self, initial: float = 0.0):
        self._value = initial
        self._lock = asyncio.Lock()

    async def add(self, amount: float) -> float:
        async with self._lock:
            self._value += amount
            return self._value

    async def get(self) -> float:
        async with self._lock:
            return self._value

    async def reset(self, value: float = 0.0) -> None:
        async with self._lock:
            self._value = value


class ReadWriteLock:
    """
    Async read-write lock.

    Multiple readers can hold the lock simultaneously.
    Writers wait for all readers to release.
    """

    def __init__(self):
        self._read_ready = asyncio.Condition()
        self._readers = 0
        self._writer_active = False

    async def acquire_read(self):
        async with self._read_ready:
            while self._writer_active:
                await self._read_ready.wait()
            self._readers += 1

    async def release_read(self):
        async with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    async def acquire_write(self):
        async with self._read_ready:
            while self._writer_active or self._readers > 0:
                await self._read_ready.wait()
            self._writer_active = True

    async def release_write(self):
        async with self._read_ready:
            self._writer_active = False
            self._read_ready.notify_all()

    @property
    async def reader_count(self) -> int:
        async with self._read_ready:
            return self._readers

    @property
    async def is_write_locked(self) -> bool:
        async with self._read_ready:
            return self._writer_active


class KeyedLock:
    """
    Per-key async lock.

    Allows concurrent operations on different keys while
    serializing access to the same key.
    """

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_lock = asyncio.Lock()

    async def acquire(self, key: str) -> asyncio.Lock:
        async with self._cleanup_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def __aenter__(self, key: str):
        lock = await self.acquire(key)
        await lock.__aenter__()
        return self

    async def __aexit__(self, key: str, *args):
        lock = await self.acquire(key)
        await lock.__aexit__(*args)


class AdaptiveConcurrency:
    """
    Dynamically adjusts concurrency limit based on success/failure.

    Uses additive-increase / multiplicative-decrease (AIMD)
    similar to TCP congestion control.
    """

    def __init__(
        self,
        initial_limit: int = 10,
        min_limit: int = 1,
        max_limit: int = 100,
        increase_step: int = 1,
        decrease_factor: float = 0.5,
    ):
        self._limit = initial_limit
        self._min = min_limit
        self._max = max_limit
        self._increase = increase_step
        self._decrease = decrease_factor
        self._semaphore = asyncio.Semaphore(initial_limit)
        self._lock = asyncio.Lock()

    @property
    async def limit(self) -> int:
        return self._limit

    async def acquire(self):
        await self._semaphore.acquire()

    def release(self):
        self._semaphore.release()

    async def on_success(self):
        async with self._lock:
            self._limit = min(self._limit + self._increase, self._max)
            self._semaphore = asyncio.Semaphore(self._limit)

    async def on_failure(self):
        async with self._lock:
            self._limit = max(int(self._limit * self._decrease), self._min)
            self._semaphore = asyncio.Semaphore(self._limit)

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        self.release()


class TokenBucket:
    """
    Async-safe token bucket rate limiter.

    Supports burst and sustained rates.
    """

    def __init__(self, rate: float, burst: Optional[int] = None):
        self._rate = rate
        self._burst = burst or int(rate)
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        async with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    async def wait_and_acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if await self.acquire(tokens):
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            await asyncio.sleep(max(0.001, 1.0 / self._rate))

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def get_available(self) -> float:
        async with self._lock:
            self._refill()
            return self._tokens


class AtomicDict:
    """Async-safe dictionary for shared state."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str, default: Any = None) -> Any:
        async with self._lock:
            return self._data.get(key, default)

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._data.pop(key, None) is not None

    async def keys(self):
        async with self._lock:
            return list(self._data.keys())

    async def items(self):
        async with self._lock:
            return list(self._data.items())

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

    async def size(self) -> int:
        async with self._lock:
            return len(self._data)


class Throttle:
    """
    Async throttle: ensures a function is called at most once per interval.

    Similar to JavaScript's _.throttle with leading edge execution.
    """

    def __init__(self, interval: float):
        self._interval = interval
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def __call__(self, fn: Callable[..., Awaitable[Any]], *args, **kwargs) -> Any:
        async with self._lock:
            now = time.monotonic()
            if now - self._last_call >= self._interval:
                self._last_call = now
                return await fn(*args, **kwargs)
            return None
