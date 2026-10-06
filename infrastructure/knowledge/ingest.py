"""
Document ingestion pipeline.

Splits documents into chunks with configurable strategies,
extracts metadata, and prepares content for indexing.
"""

from __future__ import annotations
import uuid
import re
import hashlib
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field

from .types import (
    Document, DocumentChunk, DocumentMetadata, ChunkingStrategy,
    KnowledgeSource, KnowledgeStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class ChunkConfig:
    strategy: ChunkingStrategy = ChunkingStrategy.RECURSIVE
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 50
    separators: List[str] = field(default_factory=lambda: ["\n\n", "\n", ". ", " ", ""])


class KnowledgeIngestor:
    """
    Processes raw content into indexed knowledge.

    Pipeline:
      1. Validate content
      2. Extract metadata
      3. Chunk with strategy
      4. Compute token counts
      5. Attach to document
    """

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()
        self._preprocessors: List[Callable[[str], str]] = []
        self._postprocessors: List[Callable[[Document], None]] = []

    def add_preprocessor(self, fn: Callable[[str], str]):
        self._preprocessors.append(fn)

    def add_postprocessor(self, fn: Callable[[Document], None]):
        self._postprocessors.append(fn)

    def ingest(self, content: str, metadata: Optional[DocumentMetadata] = None,
               user_id: str = "", session_id: str = "",
               chunk_config: Optional[ChunkConfig] = None) -> Document:
        """Ingest content and produce a chunked Document."""
        if not content or not content.strip():
            raise ValueError("Cannot ingest empty content")

        # Preprocessing
        for fn in self._preprocessors:
            content = fn(content)

        cfg = chunk_config or self.config
        doc_id = uuid.uuid4().hex[:16]

        doc = Document(
            id=doc_id,
            content=content,
            metadata=metadata or DocumentMetadata(),
            status=KnowledgeStatus.PENDING,
            user_id=user_id,
            session_id=session_id,
        )

        # Chunk
        chunks = self._chunk_content(content, doc_id, cfg)
        doc.chunks = chunks

        # Token estimates
        for chunk in chunks:
            chunk.tokens = self._estimate_tokens(chunk.content)

        # Postprocessing
        for fn in self._postprocessors:
            try:
                fn(doc)
            except Exception as e:
                logger.warning(f"Postprocessor failed: {e}")

        logger.info(f"Ingested document: {doc_id} ({len(chunks)} chunks, {len(content)} chars)")
        return doc

    def ingest_batch(self, items: List[tuple]) -> List[Document]:
        """Ingest multiple items. Each item: (content, metadata, user_id, session_id)."""
        return [self.ingest(*item) for item in items]

    def _chunk_content(self, content: str, doc_id: str,
                       config: ChunkConfig) -> List[DocumentChunk]:
        if config.strategy == ChunkingStrategy.FIXED_SIZE:
            return self._chunk_fixed_size(content, doc_id, config)
        elif config.strategy == ChunkingStrategy.RECURSIVE:
            return self._chunk_recursive(content, doc_id, config)
        elif config.strategy == ChunkingStrategy.SENTENCE:
            return self._chunk_by_sentence(content, doc_id, config)
        elif config.strategy == ChunkingStrategy.PARAGRAPH:
            return self._chunk_by_paragraph(content, doc_id, config)
        else:
            return self._chunk_recursive(content, doc_id, config)

    def _chunk_fixed_size(self, content: str, doc_id: str,
                          config: ChunkConfig) -> List[DocumentChunk]:
        chunks = []
        size = config.chunk_size
        overlap = config.chunk_overlap
        start = 0
        index = 0

        while start < len(content):
            end = min(start + size, len(content))
            chunk_text = content[start:end]
            if len(chunk_text) >= config.min_chunk_size:
                chunks.append(self._make_chunk(chunk_text, doc_id, index))
                index += 1
            start += size - overlap

        return chunks

    def _chunk_recursive(self, content: str, doc_id: str,
                         config: ChunkConfig) -> List[DocumentChunk]:
        chunks = []
        separators = config.separators
        size = config.chunk_size
        overlap = config.chunk_overlap

        def _recursive_split(text: str, sep_idx: int) -> List[str]:
            if len(text) <= size or sep_idx >= len(separators):
                return [text] if text.strip() else []

            sep = separators[sep_idx]
            parts = []
            for segment in text.split(sep):
                if len(segment) > size:
                    parts.extend(_recursive_split(segment, sep_idx + 1))
                elif segment.strip():
                    parts.append(segment.strip())
            return parts

        segments = _recursive_split(content, 0)
        index = 0
        buffer = ""

        for seg in segments:
            if len(buffer) + len(seg) + 1 <= size:
                buffer = (buffer + "\n" + seg).strip()
            else:
                if buffer and len(buffer) >= config.min_chunk_size:
                    chunks.append(self._make_chunk(buffer, doc_id, index))
                    index += 1
                    buffer = self._overlap_from(buffer, overlap)
                buffer = seg

        if buffer and len(buffer) >= config.min_chunk_size:
            chunks.append(self._make_chunk(buffer, doc_id, index))

        return chunks

    def _chunk_by_sentence(self, content: str, doc_id: str,
                           config: ChunkConfig) -> List[DocumentChunk]:
        sentences = re.split(r'(?<=[.!?])\s+', content)
        return self._chunk_from_segments(
            [s.strip() for s in sentences if s.strip()],
            doc_id, config,
        )

    def _chunk_by_paragraph(self, content: str, doc_id: str,
                            config: ChunkConfig) -> List[DocumentChunk]:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        return self._chunk_from_segments(paragraphs, doc_id, config)

    def _chunk_from_segments(self, segments: List[str], doc_id: str,
                             config: ChunkConfig) -> List[DocumentChunk]:
        chunks = []
        index = 0
        buffer = ""
        for seg in segments:
            if len(buffer) + len(seg) + 1 <= config.chunk_size:
                buffer = (buffer + "\n" + seg).strip()
            else:
                if buffer:
                    chunks.append(self._make_chunk(buffer, doc_id, index))
                    index += 1
                buffer = seg
        if buffer:
            chunks.append(self._make_chunk(buffer, doc_id, index))
        return chunks

    def _make_chunk(self, content: str, doc_id: str, index: int) -> DocumentChunk:
        return DocumentChunk(
            id=uuid.uuid4().hex[:16],
            document_id=doc_id,
            content=content,
            index=index,
        )

    @staticmethod
    def _overlap_from(text: str, overlap_chars: int) -> str:
        if len(text) <= overlap_chars:
            return text
        return text[-overlap_chars:]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4
