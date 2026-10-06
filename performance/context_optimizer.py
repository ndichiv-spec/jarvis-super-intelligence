"""
Memory and context optimization strategies for LLM interactions.

Provides sliding window management, token counting, context compression,
summarization triggers, and priority-based context pruning to ensure
LLM context windows are used efficiently.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from performance.concurrency import ReadWriteLock

logger = logging.getLogger(__name__)


@dataclass
class ContextMessage:
    """A single message in the conversation context."""
    role: str
    content: str
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
    priority: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    summary: Optional[str] = None


@dataclass
class ContextWindow:
    """Current context window state."""
    messages: List[ContextMessage] = field(default_factory=list)
    total_tokens: int = 0
    max_tokens: int = 4096
    summary_tokens: int = 0


class TokenCounter:
    """
    Estimates token counts for text content.

    Uses tiktoken if available, falls back to character-based estimation.
    """

    def __init__(self, model: str = "gpt-4"):
        self._model = model
        self._encoding = None
        self._load_encoding()

    def _load_encoding(self):
        try:
            import tiktoken
            self._encoding = tiktoken.encoding_for_model(self._model)
        except (ImportError, KeyError):
            self._encoding = None

    def count(self, text: str) -> int:
        if self._encoding:
            return len(self._encoding.encode(text))
        return len(text) // 4

    def count_messages(self, messages: List[ContextMessage]) -> int:
        return sum(m.token_count for m in messages)


class ContextSummarizer:
    """
    Generates summaries of conversation segments to compress context.

    Uses a configured summarization function (typically an LLM call).
    """

    def __init__(
        self,
        summarizer_fn: Optional[Callable[[str], str]] = None,
        max_summary_tokens: int = 256,
    ):
        self._summarizer_fn = summarizer_fn
        self._max_summary_tokens = max_summary_tokens

    async def summarize(self, messages: List[ContextMessage]) -> str:
        if self._summarizer_fn:
            text = "\n".join(f"{m.role}: {m.content}" for m in messages)
            if asyncio.iscoroutinefunction(self._summarizer_fn):
                return await self._summarizer_fn(text)
            return self._summarizer_fn(text)
        return "..."


class ContextOptimizer:
    """
    Manages and optimizes LLM context windows.

    Features:
    - Token counting with tiktoken
    - Sliding window management (FIFO with priority awareness)
    - Automatic summarization of older segments when nearing limit
    - Priority-based message retention
    - Configurable maximum context size per model

    Usage:
        optimizer = ContextOptimizer(max_tokens=8192)
        optimizer.add_message("user", "Hello")
        messages = optimizer.get_context()
    """

    def __init__(
        self,
        max_tokens: int = 4096,
        model: str = "gpt-4",
        summarizer: Optional[ContextSummarizer] = None,
        compression_ratio: float = 0.8,
        preserve_system_messages: bool = True,
    ):
        self._max_tokens = max_tokens
        self._compression_threshold = int(max_tokens * compression_ratio)
        self._preserve_system = preserve_system_messages

        self._token_counter = TokenCounter(model=model)
        self._summarizer = summarizer or ContextSummarizer()
        self._lock = ReadWriteLock()
        self._window = ContextWindow(max_tokens=max_tokens)

    async def add_message(
        self,
        role: str,
        content: str,
        priority: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextMessage:
        """Add a message to the context window."""
        token_count = self._token_counter.count(content)
        message = ContextMessage(
            role=role,
            content=content,
            token_count=token_count,
            priority=priority,
            metadata=metadata or {},
        )

        await self._lock.acquire_write()
        try:
            self._window.messages.append(message)
            self._window.total_tokens += token_count

            if self._window.total_tokens >= self._compression_threshold:
                await self._compress()

        finally:
            await self._lock.release_write()

        return message

    async def get_context(
        self,
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Get the current context as a list of message dicts."""
        limit = max_tokens or self._max_tokens

        await self._lock.acquire_read()
        try:
            if self._window.total_tokens <= limit:
                return self._to_dicts(self._window.messages)

            return self._to_dicts(self._truncate_to_limit(limit))
        finally:
            await self._lock.release_read()

    async def add_summary(self, messages: List[ContextMessage]) -> ContextMessage:
        """Summarize a list of messages and add the summary to context."""
        summary_text = await self._summarizer.summarize(messages)
        token_count = self._token_counter.count(summary_text)

        summary_msg = ContextMessage(
            role="system",
            content=f"[Summary of previous conversation]\n{summary_text}",
            token_count=token_count,
            priority=5,
            summary="auto-generated",
        )

        await self._lock.acquire_write()
        try:
            self._window.summary_tokens = token_count
            self._window.messages.append(summary_msg)
            self._window.total_tokens += token_count
        finally:
            await self._lock.release_write()

        return summary_msg

    async def get_token_count(self) -> int:
        await self._lock.acquire_read()
        try:
            return self._window.total_tokens
        finally:
            await self._lock.release_read()

    async def get_usage_ratio(self) -> float:
        await self._lock.acquire_read()
        try:
            if self._max_tokens == 0:
                return 0.0
            return self._window.total_tokens / self._max_tokens
        finally:
            await self._lock.release_read()

    async def clear(self):
        await self._lock.acquire_write()
        try:
            self._window.messages.clear()
            self._window.total_tokens = 0
            self._window.summary_tokens = 0
        finally:
            await self._lock.release_write()

    async def _compress(self):
        """Compress context when approaching the token limit."""
        if self._window.total_tokens < self._compression_threshold:
            return

        system_msgs = []
        high_priority = []
        low_priority = []

        for msg in self._window.messages:
            if self._preserve_system and msg.role == "system":
                system_msgs.append(msg)
            elif msg.priority >= 3:
                high_priority.append(msg)
            else:
                low_priority.append(msg)

        if not low_priority:
            return

        summary = await self._summarizer.summarize(low_priority)

        summary_msg = ContextMessage(
            role="system",
            content=f"[Summarized conversation segment]\n{summary}",
            token_count=self._token_counter.count(summary),
            priority=4,
        )

        self._window.messages = system_msgs + high_priority + [summary_msg]
        self._window.total_tokens = (
            sum(m.token_count for m in system_msgs) +
            sum(m.token_count for m in high_priority) +
            summary_msg.token_count
        )

    def _truncate_to_limit(self, limit: int) -> List[ContextMessage]:
        """Truncate messages to fit within token limit."""
        result = []
        total = 0
        for msg in reversed(self._window.messages):
            if total + msg.token_count > limit:
                continue
            result.insert(0, msg)
            total += msg.token_count
        return result

    def _to_dicts(self, messages: List[ContextMessage]) -> List[Dict[str, str]]:
        """Convert messages to API-compatible dicts."""
        result = []
        for msg in messages:
            entry: Dict[str, str] = {"role": msg.role, "content": msg.content}
            if msg.summary:
                entry["summary"] = msg.summary
            result.append(entry)
        return result
