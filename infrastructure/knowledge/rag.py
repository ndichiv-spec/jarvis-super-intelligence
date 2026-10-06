"""
Retrieval-Augmented Generation pipeline.

Assembles context from knowledge sources and generates responses
using a pluggable LLM provider.
"""

from __future__ import annotations
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass

from .types import (
    RAGContext, RAGResult, SearchQuery, DocumentChunk,
)
from .retrieval import KnowledgeRetriever, RetrievalConfig
from .context import ContextManager, ContextWindowConfig

logger = logging.getLogger(__name__)

LLMGenerateFn = Callable[[str], Awaitable[str]]


@dataclass
class RAGConfig:
    max_context_tokens: int = 3000
    max_history_turns: int = 10
    chunk_limit: int = 8
    include_sources: bool = True
    system_prompt_template: str = (
        "You are a knowledgeable assistant with access to the following context. "
        "Answer the user's question based on the provided information. "
        "If the context doesn't contain enough information, say so."
    )


class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline.

    Flow:
      1. Receive query
      2. Retrieve relevant chunks from knowledge store
      3. Assemble context with conversation history
      4. Build prompt with context
      5. Call LLM to generate answer
      6. Return answer with source attributions
    """

    def __init__(
        self,
        retriever: KnowledgeRetriever,
        context_manager: Optional[ContextManager] = None,
        llm_generate: Optional[LLMGenerateFn] = None,
        config: Optional[RAGConfig] = None,
    ):
        self.retriever = retriever
        self.context_manager = context_manager or ContextManager()
        self.llm_generate = llm_generate or self._mock_generate
        self.config = config or RAGConfig()
        self._pre_hooks: List[Callable[[str], str]] = []
        self._post_hooks: List[Callable[[RAGResult], None]] = []

    def add_pre_hook(self, fn: Callable[[str], str]):
        self._pre_hooks.append(fn)

    def add_post_hook(self, fn: Callable[[RAGResult], None]):
        self._post_hooks.append(fn)

    def set_llm(self, fn: LLMGenerateFn):
        self.llm_generate = fn

    async def generate(self, query: str, namespace: str = "default",
                       user_id: str = "", stream: bool = False) -> RAGResult:
        """Execute the full RAG pipeline."""
        start = time.time()

        # Pre-processing hooks
        for hook in self._pre_hooks:
            query = hook(query)

        # Retrieve context
        search_query = SearchQuery(
            text=query,
            top_k=self.config.chunk_limit,
            namespace=namespace,
        )
        results = self.retriever.retrieve(search_query)
        chunks = [r.chunk for r in results]

        # Build RAG context
        history = self.context_manager.get_history(max_tokens=self.config.max_history_turns)
        history_texts = [f"{h['role']}: {h['content']}" for h in history]

        rag_ctx = RAGContext(
            query=query,
            chunks=chunks,
            conversation_history=history_texts,
            system_prompt=self.config.system_prompt_template,
            max_tokens=self.config.max_context_tokens,
        )

        # Assemble prompt
        prompt = rag_ctx.assembled_prompt()

        # Generate response
        if stream:
            # Streaming not yet implemented - return generator placeholder
            answer = await self.llm_generate(prompt)
        else:
            answer = await self.llm_generate(prompt)

        # Track in context
        self.context_manager.add_user(query)
        self.context_manager.add_assistant(answer)

        result = RAGResult(
            answer=answer,
            context=rag_ctx,
            latency_ms=(time.time() - start) * 1000,
            confidence=self._calculate_confidence(results),
        )

        # Post-processing hooks
        for hook in self._post_hooks:
            try:
                hook(result)
            except Exception as e:
                logger.warning(f"Post-hook failed: {e}")

        logger.info(f"RAG generated: {len(chunks)} chunks, {len(answer)} chars, {result.latency_ms:.0f}ms")
        return result

    async def generate_stream(self, query: str, namespace: str = "default") -> RAGResult:
        """Streaming generation (placeholder - returns whole result)."""
        return await self.generate(query, namespace, stream=True)

    def _calculate_confidence(self, results: list) -> float:
        if not results:
            return 0.0
        return sum(r.score for r in results) / len(results)

    @staticmethod
    async def _mock_generate(prompt: str) -> str:
        """Mock LLM for testing."""
        return f"This is a simulated response based on {len(prompt)} characters of context."
