"""Helper utilities for writing concise, reliable tests."""

from __future__ import annotations
import os
import uuid
import asyncio
import time
import contextlib
from typing import Dict, Optional, Any, AsyncIterator, Callable, Awaitable


@contextlib.contextmanager
def temp_env_vars(vars: Dict[str, Optional[str]]):
    """Temporarily set environment variables for a test.

    Usage:
        with temp_env_vars({"MY_KEY": "value"}):
            assert os.environ["MY_KEY"] == "value"
    """
    saved = {}
    for key, value in vars.items():
        saved[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def deterministic_uuid(seed: str = "test", length: int = 16) -> str:
    """Generate a deterministic hex string from a seed for reproducible tests."""
    return uuid.uuid5(uuid.NAMESPACE_DNS, seed).hex[:length]


async def async_collect(async_gen: AsyncIterator[Any], max_items: int = 100) -> list:
    """Collect items from an async iterator into a list."""
    items = []
    async for item in async_gen:
        items.append(item)
        if len(items) >= max_items:
            break
    return items


@contextlib.contextmanager
def measure_time() -> Callable[[], float]:
    """Measure elapsed time in milliseconds.

    Usage:
        with measure_time() as elapsed:
            do_something()
        assert elapsed() < 1000
    """
    start = time.time()
    yield lambda: (time.time() - start) * 1000


async def poll_until(condition: Callable[[], bool],
                     timeout: float = 5.0,
                     interval: float = 0.1,
                     description: str = "condition") -> bool:
    """Poll a condition function until it returns True or timeout.

    Returns True if condition was met, False on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        await asyncio.sleep(interval)
    return False


class AsyncContextManager:
    """Wrap an async context manager for easier testing."""

    def __init__(self, mgr):
        self._mgr = mgr
        self._obj = None

    async def __aenter__(self):
        self._obj = await self._mgr.__aenter__()
        return self._obj

    async def __aexit__(self, *args):
        await self._mgr.__aexit__(*args)


def make_test_logger(name: str = "test"):
    """Create a logger that captures output for test inspection."""
    import logging
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger
