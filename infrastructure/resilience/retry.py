"""
Retry strategies with exponential backoff and jitter.

Supports:
  - Fixed delay
  - Exponential backoff
  - Exponential backoff with jitter
  - Decorator-based and direct usage
"""

import time
import random
import asyncio
import logging
from typing import Callable, Any, Type, Tuple, Optional, List, Union
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0, jitter: bool = True) -> float:
    """Calculate delay with exponential backoff and optional jitter."""
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    if jitter:
        delay = delay * (0.5 + random.random() * 0.5)
    return delay


@dataclass
class RetryStrategy:
    """
    Configurable retry strategy.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        jitter: Add random jitter to delays
        retryable_exceptions: Tuple of exception types that trigger retry
        on_retry: Callback invoked before each retry
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable[[int, Exception, float], None]] = None

    def get_delay(self, attempt: int) -> float:
        return exponential_backoff(attempt, self.base_delay, self.max_delay, self.jitter)

    def is_retryable(self, exc: Exception) -> bool:
        return isinstance(exc, self.retryable_exceptions)


async def retry(fn: Callable, *args, strategy: Optional[RetryStrategy] = None, **kwargs) -> Any:
    """
    Execute a function with retry logic.

    Usage:
        result = await retry(call_api, arg1, arg2, strategy=RetryStrategy(max_retries=5))
    """
    strat = strategy or RetryStrategy()

    for attempt in range(1, strat.max_retries + 2):
        try:
            if asyncio.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            return fn(*args, **kwargs)
        except Exception as e:
            if not strat.is_retryable(e) or attempt > strat.max_retries:
                raise

            delay = strat.get_delay(attempt)
            if strat.on_retry:
                strat.on_retry(attempt, e, delay)

            logger.warning(
                f"Retry {attempt}/{strat.max_retries} for {fn.__name__} "
                f"after {delay:.1f}s: {e}"
            )
            await asyncio.sleep(delay)

    raise RuntimeError("Retry exhausted")  # pragma: no cover


class RetryDecorator:
    """Decorator-based retry."""

    def __init__(self, strategy: Optional[RetryStrategy] = None):
        self.strategy = strategy or RetryStrategy()

    def __call__(self, fn: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            return await retry(fn, *args, strategy=self.strategy, **kwargs)
        return wrapper


retryable = RetryDecorator
