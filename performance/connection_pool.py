"""
Connection and resource pool management for Jarvis.

Provides generic resource pooling for HTTP sessions, database connections,
and other expensive-to-create resources. Supports async context managers,
health checking, lazy initialization, and configurable pool limits.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Optional, Set, TypeVar, Generic,
    AsyncIterator, AsyncContextManager,
)
from collections import OrderedDict

from performance.concurrency import AtomicCounter

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PoolExhaustedError(Exception):
    """Raised when all connections in the pool are in use."""


class PoolHealthError(Exception):
    """Raised when a connection fails health check."""


@dataclass
class PoolConfig:
    max_size: int = 20
    min_size: int = 2
    max_idle: int = 5
    max_lifetime: float = 300.0
    acquire_timeout: float = 10.0
    health_check_interval: float = 60.0
    retry_on_failure: bool = True
    retry_attempts: int = 3


@dataclass
class ConnectionInfo(Generic[T]):
    conn: T
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    borrow_count: int = 0
    healthy: bool = True


class ResourcePool(Generic[T]):
    """
    Generic async resource pool.

    Manages a pool of reusable resources (connections, sessions, clients)
    with health checking, idle cleanup, and configurable size limits.

    Usage:
        pool = ResourcePool(create=create_http_session, destroy=lambda s: s.close())
        async with pool.acquire() as session:
            await session.get(...)
    """

    def __init__(
        self,
        create: Callable[[], Any],
        destroy: Optional[Callable[[T], Any]] = None,
        validate: Optional[Callable[[T], bool]] = None,
        config: Optional[PoolConfig] = None,
        name: str = "resource",
    ):
        self._create = create
        self._destroy = destroy or (lambda _: None)
        self._validate = validate or (lambda _: True)
        self._config = config or PoolConfig()
        self._name = name
        self._available: OrderedDict[str, ConnectionInfo[T]] = OrderedDict()
        self._in_use: Dict[str, ConnectionInfo[T]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        self._total_created = AtomicCounter()
        self._total_destroyed = AtomicCounter()

    async def initialize(self):
        """Create minimum connections and start background cleanup."""
        async with self._lock:
            for _ in range(self._config.min_size):
                info = await self._create_connection()
                conn_id = id(info.conn)
                self._available[conn_id] = info

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            "Pool '%s' initialized with %d connections",
            self._name, self._config.min_size,
        )

    async def close(self):
        """Destroy all connections and stop cleanup."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for conn_id in list(self._available):
                await self._destroy_connection(conn_id)
            for conn_id in list(self._in_use):
                await self._force_return(conn_id)
                await self._destroy_connection(conn_id)

        logger.info("Pool '%s' closed", self._name)

    async def acquire(self) -> T:
        """
        Acquire a connection from the pool.

        Raises PoolExhaustedError if no connection is available and
        the pool is at max capacity.
        """
        deadline = time.monotonic() + self._config.acquire_timeout

        while True:
            async with self._lock:
                if self._available:
                    conn_id, info = self._available.popitem(last=False)
                    info.last_used = time.time()
                    info.borrow_count += 1
                    self._in_use[conn_id] = info
                    return info.conn

                if len(self._in_use) + len(self._available) < self._config.max_size:
                    info = await self._create_connection()
                    conn_id = id(info.conn)
                    self._in_use[conn_id] = info
                    return info.conn

            if time.monotonic() >= deadline:
                raise PoolExhaustedError(
                    f"Pool '{self._name}' exhausted "
                    f"(in_use={len(self._in_use)}, "
                    f"available={len(self._available)}, "
                    f"max={self._config.max_size})"
                )

            await asyncio.sleep(0.01)

    async def release(self, conn: T):
        """Return a connection to the pool."""
        conn_id = id(conn)
        async with self._lock:
            info = self._in_use.pop(conn_id, None)
            if info is None:
                return

            info.last_used = time.time()

            if not self._validate(conn):
                info.healthy = False
                await self._destroy_connection(conn_id)
                if len(self._available) + len(self._in_use) < self._config.min_size:
                    new_info = await self._create_connection()
                    new_id = id(new_info.conn)
                    self._available[new_id] = new_info
                return

            if time.time() - info.created_at > self._config.max_lifetime:
                await self._destroy_connection(conn_id)
                new_info = await self._create_connection()
                new_id = id(new_info.conn)
                self._available[new_id] = new_info
                return

            if len(self._available) >= self._config.max_idle:
                await self._destroy_connection(conn_id)
                return

            self._available[conn_id] = info

    @asynccontextmanager
    async def acquire_context(self) -> AsyncIterator[T]:
        """Async context manager for acquire/release."""
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)

    async def health(self) -> Dict[str, Any]:
        async with self._lock:
            available_count = len(self._available)
            in_use_count = len(self._in_use)
            to_destroy = []
            for conn_id, info in self._available.items():
                if not self._validate(info.conn):
                    to_destroy.append(conn_id)

            for conn_id in to_destroy:
                self._available.pop(conn_id, None)
                await self._destroy_connection(conn_id)

            return {
                "name": self._name,
                "available": available_count,
                "in_use": in_use_count,
                "total": available_count + in_use_count,
                "max_size": self._config.max_size,
                "min_size": self._config.min_size,
                "created_total": await self._total_created.get(),
                "destroyed_total": await self._total_destroyed.get(),
            }

    async def _create_connection(self) -> ConnectionInfo[T]:
        """Create a new connection and return its info (does not add to pool)."""
        loop = asyncio.get_event_loop()
        conn = await loop.run_in_executor(None, self._create)
        await self._total_created.inc()
        info = ConnectionInfo(conn=conn)
        return info

    async def _destroy_connection(self, conn_id: str):
        """Destroy a connection by ID."""
        info = self._available.pop(conn_id, None) or self._in_use.pop(conn_id, None)
        if info is None:
            return
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._destroy, info.conn)
            await self._total_destroyed.inc()
        except Exception as e:
            logger.warning("Pool '%s' destroy error: %s", self._name, e)

    async def _force_return(self, conn_id: str):
        """Force a connection from in_use back to available."""
        info = self._in_use.pop(conn_id, None)
        if info:
            self._available[conn_id] = info

    async def _cleanup_loop(self):
        """Background cleanup of idle and expired connections."""
        while True:
            await asyncio.sleep(self._config.health_check_interval)
            try:
                await self._cleanup_idle()
            except Exception as e:
                logger.warning("Pool '%s' cleanup error: %s", self._name, e)

    async def _cleanup_idle(self):
        """Remove idle and expired connections."""
        async with self._lock:
            now = time.time()
            to_remove = []
            for conn_id, info in self._available.items():
                if now - info.last_used > self._config.max_lifetime:
                    to_remove.append(conn_id)
                elif now - info.created_at > self._config.max_lifetime:
                    to_remove.append(conn_id)

            for conn_id in to_remove:
                self._available.pop(conn_id, None)
                await self._destroy_connection(conn_id)

            idle_count = len(self._available)
            while idle_count > self._config.max_idle:
                conn_id, _ = self._available.popitem(last=False)
                await self._destroy_connection(conn_id)
                idle_count -= 1


class HTTPSessionPool(ResourcePool):
    """Specialized resource pool for HTTP sessions (aiohttp/httpx)."""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_size: int = 20,
        headers: Optional[Dict[str, str]] = None,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._default_headers = headers or {}

        super().__init__(
            create=self._create_session,
            destroy=self._destroy_session,
            validate=self._validate_session,
            config=PoolConfig(max_size=max_size),
            name=f"http:{base_url}",
        )

    def _create_session(self):
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for HTTPSessionPool")
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=self._default_headers,
        )

    async def _destroy_session(self, session):
        try:
            await session.aclose()
        except Exception:
            pass

    def _validate_session(self, session) -> bool:
        try:
            if hasattr(session, "is_closed"):
                return not session.is_closed()
            return True
        except Exception:
            return False
