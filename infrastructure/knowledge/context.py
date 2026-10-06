"""
Conversation context manager.

Maintains context windows with:
  - Configurable window sizes
  - Token-aware truncation
  - Structured history format
  - Automatic summarization triggers
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ContextEntry:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content[:500],
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ContextWindowConfig:
    max_tokens: int = 4096
    max_turns: int = 50
    max_age_seconds: float = 3600.0
    summary_threshold_tokens: int = 3000
    preserve_system_prompt: bool = True


class ContextManager:
    """
    Manages conversation context with windowing and eviction.

    Design:
      - FIFO with token budget
      - Evicts oldest non-system messages when over budget
      - Trigger point for summarization
      - Structured format for LLM consumption
    """

    def __init__(self, config: Optional[ContextWindowConfig] = None):
        self.config = config or ContextWindowConfig()
        self._entries: List[ContextEntry] = []
        self._summaries: List[str] = []

    def add(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
        self._entries.append(ContextEntry(
            role=role,
            content=content,
            metadata=metadata or {},
        ))
        self._evict()

    def add_user(self, content: str):
        self.add("user", content)

    def add_assistant(self, content: str):
        self.add("assistant", content)

    def add_system(self, content: str):
        self.add("system", content)

    def get_history(self, max_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        budget = max_tokens or self.config.max_tokens
        result: List[Dict[str, str]] = []
        tokens_used = 0

        # System prompts first (always included if within budget)
        system_entries = [
            e for e in self._entries if e.role == "system"
        ]
        for entry in system_entries:
            tokens = len(entry.content) // 4
            if tokens_used + tokens <= budget:
                result.append({"role": "system", "content": entry.content})
                tokens_used += tokens

        # Recent non-system entries
        non_system = [
            e for e in self._entries if e.role != "system"
        ]
        for entry in reversed(non_system):
            tokens = len(entry.content) // 4
            if tokens_used + tokens <= budget:
                result.insert(
                    len([r for r in result if r["role"] == "system"]),
                    {"role": entry.role, "content": entry.content},
                )
                tokens_used += tokens
            else:
                break

        return result

    def get_token_count(self) -> int:
        return sum(len(e.content) // 4 for e in self._entries)

    def get_turn_count(self) -> int:
        return sum(1 for e in self._entries if e.role in ("user", "assistant"))

    def needs_summarization(self) -> bool:
        return self.get_token_count() >= self.config.summary_threshold_tokens

    def add_summary(self, summary: str):
        self._summaries.append(summary)
        # Replace oldest non-system entries with summary
        self._entries = [e for e in self._entries if e.role == "system"]
        self._entries.append(ContextEntry(
            role="system",
            content=f"Previous conversation summary: {summary}",
        ))

    def clear(self):
        self._entries.clear()

    def snapshot(self) -> Dict[str, Any]:
        return {
            "total_entries": len(self._entries),
            "estimated_tokens": self.get_token_count(),
            "turns": self.get_turn_count(),
            "summaries": len(self._summaries),
            "needs_summarization": self.needs_summarization(),
            "entries": [e.to_dict() for e in self._entries[-10:]],
        }

    def _evict(self):
        """Evict entries to stay within constraints."""
        while self.get_turn_count() > self.config.max_turns:
            self._evict_one()

        while self.get_token_count() > self.config.max_tokens:
            self._evict_one()

    def _evict_one(self):
        for i, e in enumerate(self._entries):
            if e.role != "system" or not self.config.preserve_system_prompt:
                self._entries.pop(i)
                return
        if self._entries:
            self._entries.pop(0)
