"""
JARVIS MEMORY CAPABILITY
=========================

Memory is an independent cognitive subsystem - NOT owned by Chat, Voice, Vision,
or any other modality. All modalities contribute to memory; none owns it.

Memory types:
- Working Memory: Short-lived conversation context
- Episodic Memory: Conversation history and experiences
- Semantic Memory: Facts and knowledge extracted from interactions
- Conversation Memory: Shared session state
- Knowledge Retrieval: RAG-style retrieval

Memory must be independently queryable and auditable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import (
    Capability,
    CapabilityStatus,
    ExecutionContext,
    ExecutionResult,
)
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import AuditLog, MemoryRepository


class MemoryCapability(Capability):
    """
    Independent Memory capability for JARVIS.

    Memory types:
    - working: Short-term context (per-session)
    - episodic: Long-term conversation history
    - semantic: Facts and knowledge
    - conversation: Shared session state
    - knowledge: RAG retrieval index

    Memory is contributed to by ALL modalities but owned by nobody.
    """

    name = "memory"
    version = "1.0.0"
    category = "memory"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._local_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl: float = 300.0  # 5 minutes
        self._embedding_model = None

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify database connection."""
        try:
            # Real check - can we access the database?
            test_mem = MemoryRepository.store_memory(
                memory_type='health_check',
                content='health check',
                user_id='system',
                metadata={'test': True}
            )
            result = MemoryRepository.retrieve_memories(
                memory_type='health_check',
                limit=1
            )

            # Clean up
            from jarvis_backend.persistence import db_session, delete, memory_entries_table
            with db_session() as conn:
                conn.execute(
                    delete(memory_entries_table).where(
                        memory_entries_table.c.memory_type == 'health_check'
                    )
                )

            return {
                'status': CapabilityStatus.READY if result else CapabilityStatus.DEGRADED,
                'db_connected': True,
                'healthy': True,
            }
        except Exception as e:
            return {
                'status': CapabilityStatus.ERROR,
                'db_connected': False,
                'error': str(e),
                'healthy': False,
            }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a memory operation.

        Request types:
        - 'store': Store a memory entry
        - 'retrieve': Retrieve memories
        - 'retrieve_context': Get working memory for a session
        - 'forget': Remove a memory entry
        - 'summarize': Generate a summary of memories
        - 'get_provenance': Get memory provenance chain
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'retrieve')
        start_time = time.time()

        correlation_id = context.correlation_id
        session_id = context.session_id

        self._event_bus.emit(
            event_type='memory.operation.started',
            source='orchestrator',
            capability='memory',
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action},
        )

        try:
            if action == 'store':
                result = self._store_memory(request, context)
            elif action == 'retrieve':
                result = self._retrieve_memories(request, context)
            elif action == 'retrieve_context':
                result = self._get_working_memory(context)
            elif action == 'forget':
                result = self._forget_memory(request, context)
            elif action == 'summarize':
                result = await self._summarize(request, context)
            elif action == 'get_provenance':
                result = self._get_provenance(request, context)
            elif action == 'store_working':
                result = self._store_working_memory(request, context)
            elif action == 'store_episodic':
                result = self._store_episodic(request, context)
            elif action == 'store_semantic':
                result = self._store_semantic(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown memory action: {action}",
                    error_type="INVALID_ACTION",
                    correlation_id=correlation_id,
                )
        except Exception as e:
            result = ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
                correlation_id=correlation_id,
            )

        result.latency_ms = (time.time() - start_time) * 1000.0
        result.correlation_id = correlation_id

        # Emit completion
        self._event_bus.emit(
            event_type=f'memory.{action}.completed',
            source='memory',
            capability='memory',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload={'success': result.success},
        )

        AuditLog.log(
            event_type=f'memory.{action}',
            source='memory',
            capability='memory',
            user_id=context.user_id,
            session_id=session_id,
            action=action,
            result='success' if result.success else 'error',
        )

        return result

    def _store_memory(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Store a memory entry."""
        mem_type = request.get('memory_type', 'episodic')
        content = request.get('content', '')
        provenance = request.get('provenance', 'conversation')
        expires_at = request.get('expires_at')

        mem_id = MemoryRepository.store_memory(
            memory_type=mem_type,
            content=content,
            session_id=context.session_id,
            user_id=context.user_id,
            metadata=request.get('metadata', {}),
            provenance=provenance,
            expires_at=expires_at,
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'memory_id': mem_id, 'memory_type': mem_type},
            correlation_id=context.correlation_id,
        )

    def _retrieve_memories(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Retrieve memories."""
        mem_type = request.get('memory_type')
        limit = request.get('limit', 20)

        memories = MemoryRepository.retrieve_memories(
            memory_type=mem_type,
            session_id=context.session_id,
            user_id=context.user_id,
            limit=limit,
        )

        # Parse metadata
        for m in memories:
            if m.get('metadata_json'):
                m['metadata'] = json.loads(m['metadata_json'])

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'memories': memories, 'count': len(memories)},
            correlation_id=context.correlation_id,
            metrics={'retrieved_count': len(memories)},
        )

    def _get_working_memory(self, context: ExecutionContext) -> ExecutionResult:
        """Get working memory for the current session."""
        # Working memory is recent context
        memories = MemoryRepository.get_working_memory(context.session_id, limit=20)

        # Also get recent messages from conversation
        from jarvis_backend.persistence import ConversationRepository
        session = ConversationRepository.get_session(context.session_id)
        conversation_id = session['id'] if session else None

        messages = []
        if conversation_id:
            messages = ConversationRepository.get_messages(conversation_id, limit=30)

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'working_memory': memories,
                'recent_messages': messages,
                'session_id': context.session_id,
            },
            correlation_id=context.correlation_id,
        )

    def _forget_memory(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Remove a memory entry."""
        from sqlalchemy import delete

        from jarvis_backend.persistence import db_session, memory_entries_table
        mem_id = request.get('memory_id')

        if not mem_id:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="memory_id required for forget action",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        with db_session() as conn:
            result = conn.execute(
                delete(memory_entries_table).where(memory_entries_table.c.id == mem_id)
            )
            deleted = result.rowcount > 0 if hasattr(result, 'rowcount') else True

        return ExecutionResult(
            capability=self.name,
            success=deleted,
            data={'deleted': deleted, 'memory_id': mem_id},
            correlation_id=context.correlation_id,
        )

    def _get_provenance(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get the provenance chain for a memory."""
        mem_id = request.get('memory_id')
        memories = MemoryRepository.retrieve_memories(
            session_id=context.session_id,
            user_id=context.user_id,
            limit=200,
        )

        # Find provenance chain
        provenance = []
        target = None
        for m in memories:
            if m['id'] == mem_id:
                target = m
                break

        if target:
            prov_str = target.get('provenance')
            provenance = [{'memory_id': mem_id, 'provenance': prov_str}]

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'provenance': provenance, 'memory_id': mem_id},
            correlation_id=context.correlation_id,
        )

    def _store_working_memory(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Store a working memory entry."""
        content = request.get('content', '')
        mem_id = MemoryRepository.store_working_memory(
            session_id=context.session_id,
            content=content,
            user_id=context.user_id,
            metadata=request.get('metadata', {}),
        )
        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'memory_id': mem_id, 'memory_type': 'working'},
            correlation_id=context.correlation_id,
        )

    def _store_episodic(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Store an episodic memory entry."""
        content = request.get('content', '')
        mem_id = MemoryRepository.store_episodic_memory(
            session_id=context.session_id,
            content=content,
            user_id=context.user_id,
            metadata=request.get('metadata', {}),
        )
        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'memory_id': mem_id, 'memory_type': 'episodic'},
            correlation_id=context.correlation_id,
        )

    def _store_semantic(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Store a semantic memory entry (fact)."""
        content = request.get('content', '')
        mem_id = MemoryRepository.store_memory(
            memory_type='semantic',
            content=content,
            session_id=context.session_id,
            user_id=context.user_id,
            metadata=request.get('metadata', {}),
            provenance='semantic_knowledge',
        )
        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'memory_id': mem_id, 'memory_type': 'semantic'},
            correlation_id=context.correlation_id,
        )

    async def _summarize(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Generate a summary of memories."""
        memories = MemoryRepository.retrieve_memories(
            session_id=context.session_id,
            user_id=context.user_id,
            limit=50,
        )

        content_parts = []
        for m in memories:
            content_parts.append(m.get('content', ''))

        combined = '\n'.join(content_parts[:100])

        # Try to summarize using LLM if available
        summary = await self._generate_summary(combined)

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'summary': summary, 'source_count': len(memories)},
            correlation_id=context.correlation_id,
        )

    async def _generate_summary(self, text: str) -> str:
        """Generate a summary using available LLM."""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if api_key:
                import openai
                client = openai.OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model='gpt-3.5-turbo',
                    messages=[{
                        'role': 'user',
                        'content': f"Summarize this text concisely:\n\n{text[:2000]}"
                    }],
                    max_tokens=150,
                )
                return response.choices[0].message.content.strip()
        except Exception:
            pass

        # Fallback: truncate
        return text[:200] + "..." if len(text) > 200 else text

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._local_cache.clear()
        return True


__all__ = ['MemoryCapability']
