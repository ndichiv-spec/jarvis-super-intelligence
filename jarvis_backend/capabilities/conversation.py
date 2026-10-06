"""
JARVIS CONVERSATION CAPABILITY
===============================

Conversation is the SHARED interaction state layer. It is NOT the owner of
Voice, Vision, or Image Generation. Instead, conversation aggregates:

- text input
- voice input
- image input
- generated image
- tool results
- browser results
- memory references
- system events

A conversation preserves:
- session ID
- messages
- modality
- timestamps
- attachments
- tool calls / results
- model/provider
- Brain decisions
- errors
- state
- correlation IDs
- artifact references

Conversations must survive:
- browser reload
- frontend restart
- backend restart
- network interruption
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, AsyncIterator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ConversationRepository, ArtifactRepository, AuditLog


class ConversationCapability(Capability):
    """
    Conversation capability - shared interaction state.

    Conversation is the glue that connects all modalities. It persists
    across restarts and provides context to the Brain.
    """

    name = "conversation"
    version = "1.0.0"
    category = "conversation"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify database connection."""
        try:
            # Real check - can we create and retrieve a session?
            test_session = f"health-{uuid.uuid4().hex[:8]}"
            conv_id = ConversationRepository.create_session(
                session_id=test_session,
                user_id="health-check",
                modality="text",
                metadata={'health_check': True}
            )
            retrieved = ConversationRepository.get_session(test_session)

            # Clean up
            from jarvis_backend.persistence import db_session, conversations_table, delete
            with db_session() as conn:
                conn.execute(
                    delete(conversations_table).where(
                        conversations_table.c.session_id == test_session
                    )
                )

            ok = retrieved is not None and retrieved['id'] == conv_id
            return {
                'status': CapabilityStatus.READY if ok else CapabilityStatus.DEGRADED,
                'db_connected': True,
                'healthy': ok,
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
        Execute a conversation operation.

        Actions:
        - 'create': Create a new conversation session
        - 'get': Get conversation state
        - 'add_message': Add a message (any modality)
        - 'get_messages': Retrieve conversation history
        - 'get_state': Get full conversation state with context
        - 'restore': Restore after interruption
        - 'end': End the conversation
        - 'get_artifacts': Get all artifacts for conversation
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'create')
        start_time = time.time()
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type=f'conversation.{action}.started',
            source='orchestrator',
            capability='conversation',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={},
        )

        try:
            if action == 'create':
                result = await self._create_session(request, context)
            elif action == 'get':
                result = await self._get_session(request, context)
            elif action == 'add_message':
                result = await self._add_message(request, context)
            elif action == 'get_messages':
                result = await self._get_messages(request, context)
            elif action == 'get_state':
                result = await self._get_state(request, context)
            elif action == 'restore':
                result = await self._restore(request, context)
            elif action == 'end':
                result = await self._end_session(request, context)
            elif action == 'get_artifacts':
                result = await self._get_artifacts(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown conversation action: {action}",
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

        self._event_bus.emit(
            event_type=f'conversation.{action}.completed',
            source='conversation',
            capability='conversation',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload=result.to_dict(),
        )

        return result

    async def _create_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Create a new conversation."""
        conv_id = ConversationRepository.create_session(
            session_id=context.session_id,
            user_id=context.user_id,
            title=request.get('title'),
            modality=request.get('modality', 'text'),
            metadata=request.get('metadata', {}),
        )

        self._active_sessions[context.session_id] = {
            'conversation_id': conv_id,
            'session_id': context.session_id,
            'user_id': context.user_id,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'modality': request.get('modality', 'text'),
        }

        self._event_bus.emit(
            event_type='conversation.created',
            source='conversation',
            capability='conversation',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'conversation_id': conv_id},
        )

        AuditLog.log(
            event_type='conversation.created',
            source='conversation',
            capability='conversation',
            user_id=context.user_id,
            session_id=context.session_id,
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'conversation_id': conv_id, 'session_id': context.session_id},
            correlation_id=context.correlation_id,
        )

    async def _get_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get conversation session."""
        session = ConversationRepository.get_session(context.session_id)

        if session is None:
            # Create one if it doesn't exist (recovery)
            conv_id = ConversationRepository.create_session(
                session_id=context.session_id,
                user_id=context.user_id,
                modality='text',
            )
            session = ConversationRepository.get_session(context.session_id)
            self._active_sessions[context.session_id] = {
                'conversation_id': conv_id,
                'session_id': context.session_id,
            }

        # Parse metadata
        if session and session.get('metadata_json'):
            session['metadata'] = json.loads(session['metadata_json'])

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'session': session},
            correlation_id=context.correlation_id,
        )

    async def _add_message(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Add a message to the conversation."""
        # Get or create conversation
        session = ConversationRepository.get_session(context.session_id)
        if session is None:
            conv_id = ConversationRepository.create_session(
                session_id=context.session_id,
                user_id=context.user_id,
                modality=request.get('modality', 'text'),
            )
        else:
            conv_id = session['id']

        msg_id = ConversationRepository.add_message(
            conversation_id=conv_id,
            session_id=context.session_id,
            role=request.get('role', 'user'),
            content=request.get('content', ''),
            modality=request.get('modality', 'text'),
            correlation_id=context.correlation_id,
            tool_calls=request.get('tool_calls'),
            tool_results=request.get('tool_results'),
            provider_used=request.get('provider_used'),
            model_used=request.get('model_used'),
            brain_decision=request.get('brain_decision'),
            metadata=request.get('metadata'),
        )

        self._event_bus.emit(
            event_type='conversation.message.received',
            source='conversation',
            capability='conversation',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed',
            payload={
                'message_id': msg_id,
                'conversation_id': conv_id,
                'role': request.get('role', 'user'),
                'modality': request.get('modality', 'text'),
            },
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'message_id': msg_id, 'conversation_id': conv_id},
            correlation_id=context.correlation_id,
        )

    async def _get_messages(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get all messages for a conversation."""
        session = ConversationRepository.get_session(context.session_id)
        if session is None:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="No conversation found for session",
                error_type="NOT_FOUND",
                correlation_id=context.correlation_id,
            )

        conv_id = session['id']
        limit = request.get('limit', 100)
        messages = ConversationRepository.get_messages(conv_id, limit=limit)

        # Parse JSON fields
        for msg in messages:
            if msg.get('tool_calls_json'):
                msg['tool_calls'] = json.loads(msg['tool_calls_json'])
            if msg.get('tool_results_json'):
                msg['tool_results'] = json.loads(msg['tool_results_json'])
            if msg.get('metadata_json'):
                msg['metadata'] = json.loads(msg['metadata_json'])

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'messages': messages, 'conversation_id': conv_id},
            correlation_id=context.correlation_id,
        )

    async def _get_state(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get full conversation state including context."""
        session_result = await self._get_session(request, context)
        if not session_result.success:
            return session_result

        session = session_result.data.get('session', {})
        conv_id = session.get('id')

        # Get messages
        msgs_result = await self._get_messages(request, context)
        messages = msgs_result.data.get('messages', []) if msgs_result.success else []

        # Get artifacts
        artifacts = ArtifactRepository.get_for_conversation(conv_id)

        # Get working memory
        from jarvis_backend.persistence import MemoryRepository
        working_mem = MemoryRepository.retrieve_memories(
            memory_type='working',
            session_id=context.session_id,
            limit=10,
        )
        episodic = MemoryRepository.retrieve_memories(
            memory_type='episodic',
            session_id=context.session_id,
            limit=10,
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'conversation': session,
                'messages': messages,
                'artifacts': artifacts,
                'working_memory': working_mem,
                'episodic_memory': episodic,
            },
            correlation_id=context.correlation_id,
        )

    async def _restore(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Restore conversation after interruption/restart."""
        session = ConversationRepository.get_session(context.session_id)

        if session:
            self._event_bus.emit(
                event_type='conversation.restored',
                source='conversation',
                capability='conversation',
                correlation_id=context.correlation_id,
                session_id=context.session_id,
                user_id=context.user_id,
                status='completed',
                payload={'conversation_id': session['id']},
            )

            return ExecutionResult(
                capability=self.name,
                success=True,
                data={
                    'restored': True,
                    'conversation_id': session['id'],
                    'session_id': context.session_id,
                },
                correlation_id=context.correlation_id,
            )

        # No session found - create new one
        return await self._create_session({'modality': 'text'}, context)

    async def _end_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """End a conversation session."""
        ConversationRepository.update_session_state(
            ConversationRepository.get_session(context.session_id)['id'],
            'ended',
            {'ended_reason': request.get('reason', 'user_initiated')}
        )

        self._event_bus.emit(
            event_type='conversation.ended',
            source='conversation',
            capability='conversation',
            correlation_id=context.correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed',
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'ended': True},
            correlation_id=context.correlation_id,
        )

    async def _get_artifacts(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get artifacts for conversation."""
        session = ConversationRepository.get_session(context.session_id)
        if session:
            artifacts = ArtifactRepository.get_for_conversation(session['id'])
            return ExecutionResult(
                capability=self.name, success=True,
                data={'artifacts': artifacts},
                correlation_id=context.correlation_id,
            )
        return ExecutionResult(
            capability=self.name, success=True,
            data={'artifacts': []},
            correlation_id=context.correlation_id,
        )

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._active_sessions.clear()
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['ConversationCapability']
