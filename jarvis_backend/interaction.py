"""
JARVIS INTERACTION LAYER
=========================

This is the interaction fabric that connects User <-> Interaction Layer <->
Orchestrator <-> Brain <-> Capabilities.

It provides a single entry point for all JARVIS interactions regardless of
modality (chat, voice, vision, image).

The interaction layer:
1. Receives user requests
2. Creates/reuses conversation state
3. Passes to the Brain for reasoning
4. Selects and executes capabilities
5. Returns results through the same conversation state

This is NOT a chat component. This is the orchestration entry point.
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

from jarvis_backend.capability import (
    ExecutionContext,
    ExecutionResult,
    get_orchestrator,
    get_registry,
)
from jarvis_backend.event_fabric import get_event_bus, Event
from jarvis_backend.persistence import (
    ConversationRepository,
    MemoryRepository,
    TaskRepository,
    AuditLog,
)
from jarvis_backend.capabilities.tools.github import GitHubTool
from jarvis_backend.capabilities.tools.postgresql import PostgreSQLTool


class InteractionLayer:
    """
    The JARVIS Interaction Fabric.

    Connects all modalities to the Brain through a unified orchestration path:

    User
     |
    Interaction Layer
     |
    Orchestrator
     |
    Brain
     |
    Capability selection
     |
    Authorization
     |
    Capability execution
     |
    Result
     |
    Brain
     |
    Response
     |
    Interaction Layer

    Chat is one interface. Voice is another. Vision is another. Image generation
    is another. They all connect here.
    """

    def __init__(self):
        self._orchestrator = get_orchestrator()
        self._registry = get_registry()
        self._event_bus = get_event_bus()

    async def start_session(
        self,
        user_id: str,
        session_id: str,
        modality: str = "text",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Start a new interaction session."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
            permissions=['admin'] if os.environ.get('JARVIS_ENV') == 'dev' else [],
        )

        # Create conversation
        result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'create',
                'modality': modality,
                'title': metadata.get('title') if metadata else None,
                'metadata': metadata,
            },
            context=context,
        )

        return {
            'session_id': session_id,
            'conversation_id': result.data.get('conversation_id') if result.success else None,
            'correlation_id': correlation_id,
            'modality': modality,
            'status': 'active',
        }

    async def restore_session(
        self,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Restore a session after interruption/restart."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={'action': 'restore'},
            context=context,
        )

        return {
            'session_id': session_id,
            'conversation_id': result.data.get('conversation_id') if result.success else None,
            'restored': result.success,
            'status': 'active',
            'correlation_id': correlation_id,
        }

    async def process_text(
        self,
        user_id: str,
        session_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process a text input through the full JARVIS pipeline."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        # Step 1: Add user message to conversation
        conv_result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'user',
                'content': text,
                'modality': 'text',
                'metadata': metadata,
            },
            context=context,
        )

        conversation_id = conv_result.data.get('conversation_id') if conv_result.success else None

        # Step 2: Store in working memory
        await self._orchestrator.execute_capability(
            capability_name='memory',
            request={
                'action': 'store_working',
                'content': text,
                'metadata': {'modality': 'text', 'source': 'user_input'},
            },
            context=context,
        )

        # Step 3: Store in episodic memory
        await self._orchestrator.execute_capability(
            capability_name='memory',
            request={
                'action': 'store_episodic',
                'content': text,
                'metadata': {'conversation_id': conversation_id, 'source': 'user_text'},
            },
            context=context,
        )

        # Step 4: Brain reasoning
        brain_result = await self._orchestrator.execute_capability(
            capability_name='brain',
            request={
                'action': 'respond',
                'input': text,
                'conversation_id': conversation_id,
                'allowed_capabilities': self._registry.list_all(),
            },
            context=context,
        )

        response_text = ""
        provider_used = None
        model_used = None

        if brain_result.success:
            response_text = brain_result.data.get('response', '')
            provider_used = brain_result.data.get('provider', 'unknown')
            model_used = brain_result.data.get('model', 'unknown')
        else:
            # Honest error - don't fake it
            response_text = f"[Brain error: {brain_result.error}]"
            provider_used = None
            model_used = None

        # Step 5: Add AI response to conversation
        await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'assistant',
                'content': response_text,
                'modality': 'text',
                'provider_used': provider_used,
                'model_used': model_used,
                'brain_decision': brain_result.data.get('reasoning') if brain_result.success else str(brain_result.error),
                'correlation_id': correlation_id,
            },
            context=context,
        )

        # Step 6: Store response in memory
        await self._orchestrator.execute_capability(
            capability_name='memory',
            request={
                'action': 'store_working',
                'content': response_text,
                'metadata': {'modality': 'text', 'source': 'jarvis_response', 'provider': provider_used},
            },
            context=context,
        )

        # Emit final event
        self._event_bus.emit(
            event_type='conversation.message.sent',
            source='interaction',
            correlation_id=correlation_id,
            session_id=session_id,
            user_id=user_id,
            status='completed',
            payload={'conversation_id': conversation_id, 'response_length': len(response_text)},
        )

        return {
            'session_id': session_id,
            'conversation_id': conversation_id,
            'response': response_text,
            'provider': provider_used,
            'model': model_used,
            'correlation_id': correlation_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    async def process_voice(
        self,
        user_id: str,
        session_id: str,
        audio_data: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Process voice through the full pipeline: STT -> Brain -> TTS."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        # Step 1: Voice session started
        voice_result = await self._orchestrator.execute_capability(
            capability_name='voice',
            request={'action': 'start_session', 'session_id': session_id},
            context=context,
        )

        # Step 2: STT - Transcribe audio
        stt_result = await self._orchestrator.execute_capability(
            capability_name='voice',
            request={'action': 'transcribe', 'audio_data': audio_data},
            context=context,
        )

        if not stt_result.success:
            return {
                'session_id': session_id,
                'error': stt_result.error,
                'error_type': stt_result.error_type,
                'state': 'error',
                'correlation_id': correlation_id,
            }

        transcription = stt_result.data.get('text', '')

        # Step 3: Add voice message to conversation (shared state)
        conv_result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'user',
                'content': transcription,
                'modality': 'voice',
                'provider_used': stt_result.data.get('provider', 'unknown'),
            },
            context=context,
        )

        conversation_id = conv_result.data.get('conversation_id') if conv_result.success else None

        # Step 4: Store in memory (voice contributes to memory)
        await self._orchestrator.execute_capability(
            capability_name='memory',
            request={
                'action': 'store_episodic',
                'content': transcription,
                'metadata': {'modality': 'voice', 'source': 'user_speech'},
            },
            context=context,
        )

        # Step 5: Brain reasoning (same as text)
        brain_result = await self._orchestrator.execute_capability(
            capability_name='brain',
            request={
                'action': 'respond',
                'input': transcription,
                'conversation_id': conversation_id,
                'allowed_capabilities': self._registry.list_all(),
            },
            context=context,
        )

        response_text = ""
        if brain_result.success:
            response_text = brain_result.data.get('response', '')
        else:
            response_text = f"[Brain error: {brain_result.error}]"

        # Add response to conversation
        await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'assistant',
                'content': response_text,
                'modality': 'voice',
                'provider_used': brain_result.data.get('provider') if brain_result.success else None,
                'model_used': brain_result.data.get('model') if brain_result.success else None,
            },
            context=context,
        )

        # Step 6: TTS - Synthesize response
        tts_result = await self._orchestrator.execute_capability(
            capability_name='voice',
            request={'action': 'synthesize', 'text': response_text},
            context=context,
        )

        # Step 7: Stop voice session
        await self._orchestrator.execute_capability(
            capability_name='voice',
            request={'action': 'stop_session'},
            context=context,
        )

        return {
            'session_id': session_id,
            'conversation_id': conversation_id,
            'transcription': transcription,
            'response': response_text,
            'audio': tts_result.data if tts_result.success else None,
            'tts_provider': tts_result.data.get('provider') if tts_result.success else None,
            'correlation_id': correlation_id,
        }

    async def process_image(
        self,
        user_id: str,
        session_id: str,
        image_data: str,  # base64 encoded
        prompt: str = "What is in this image?",
    ) -> Dict[str, Any]:
        """Process an image through the Vision capability."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        # Step 1: Add image message to conversation
        conv_result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'user',
                'content': prompt,
                'modality': 'image',
                'metadata': {'image_data_present': True, 'image_size': len(image_data)},
            },
            context=context,
        )

        conversation_id = conv_result.data.get('conversation_id') if conv_result.success else None

        # Step 2: Vision analysis
        vision_result = await self._orchestrator.execute_capability(
            capability_name='vision',
            request={
                'action': 'analyze_image',
                'image_data': image_data,
                'prompt': prompt,
                'conversation_id': conversation_id,
            },
            context=context,
        )

        if vision_result.success:
            analysis = vision_result.data.get('analysis', '')

            # Add vision result to conversation
            await self._orchestrator.execute_capability(
                capability_name='conversation',
                request={
                    'action': 'add_message',
                    'role': 'assistant',
                    'content': analysis,
                    'modality': 'vision',
                    'provider_used': vision_result.data.get('provider', 'unknown'),
                },
                context=context,
            )

            # Store in memory
            await self._orchestrator.execute_capability(
                capability_name='memory',
                request={
                    'action': 'store_episodic',
                    'content': f"Image received: {prompt}",
                    'metadata': {'modality': 'vision', 'source': 'user_image',
                               'analysis': analysis[:200]},
                },
                context=context,
            )

        return {
            'session_id': session_id,
            'conversation_id': conversation_id,
            'analysis': vision_result.data.get('analysis', '') if vision_result.success else None,
            'error': vision_result.error if not vision_result.success else None,
            'correlation_id': correlation_id,
        }

    async def generate_image(
        self,
        user_id: str,
        session_id: str,
        prompt: str,
        model: str = None,
    ) -> Dict[str, Any]:
        """Generate an image through the image generation capability."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        # Get conversation
        conv = ConversationRepository.get_session(session_id)
        conversation_id = conv['id'] if conv else None

        # Add image generation request to conversation
        await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={
                'action': 'add_message',
                'role': 'user',
                'content': prompt,
                'modality': 'image_request',
                'metadata': {'image_prompt': prompt},
            },
            context=context,
        )

        # Execute image generation
        img_result = await self._orchestrator.execute_capability(
            capability_name='image.generate',
            request={
                'prompt': prompt,
                'model': model,
                'conversation_id': conversation_id,
            },
            context=context,
        )

        if img_result.success:
            # Add generated image to conversation as attachment
            await self._orchestrator.execute_capability(
                capability_name='conversation',
                request={
                    'action': 'add_message',
                    'role': 'assistant',
                    'content': f"[Image generated: {prompt}]",
                    'modality': 'image_generated',
                    'metadata': {
                        'artifacts': [a.get('url') for a in img_result.artifacts],
                        'model': img_result.data.get('model'),
                        'provider': img_result.data.get('provider'),
                    },
                },
                context=context,
            )

            return {
                'success': True,
                'artifacts': img_result.artifacts,
                'model': img_result.data.get('model'),
                'provider': img_result.data.get('provider'),
                'correlation_id': correlation_id,
            }
        else:
            return {
                'success': False,
                'error': img_result.error,
                'error_type': img_result.error_type,
                'correlation_id': correlation_id,
            }

    async def execute_tool(
        self,
        user_id: str,
        session_id: str,
        tool: str,
        action: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a tool through the Brain -> tool -> external system flow."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
            permissions=['admin', 'tool.browser', 'tool.github', 'tool.database'] if os.environ.get('JARVIS_ENV') == 'dev' else [],
        )

        # Execute tool through orchestrator
        result = await self._orchestrator.execute_capability(
            capability_name='tool',
            request={
                'tool': tool,
                'action': action,
                'params': params,
            },
            context=context,
        )

        # Add tool result to conversation
        if result.success:
            await self._orchestrator.execute_capability(
                capability_name='conversation',
                request={
                    'action': 'add_message',
                    'role': 'assistant',
                    'content': json.dumps(result.data, default=str)[:500],
                    'modality': 'tool_result',
                    'metadata': {'tool': tool, 'action': action, 'success': True},
                },
                context=context,
            )
        else:
            await self._orchestrator.execute_capability(
                capability_name='conversation',
                request={
                    'action': 'add_message',
                    'role': 'system',
                    'content': f"Tool {tool}.{action} failed: {result.error}",
                    'modality': 'error',
                    'metadata': {'tool': tool, 'action': action, 'error': result.error},
                },
                context=context,
            )

        return {
            'success': result.success,
            'data': result.data,
            'error': result.error if not result.success else None,
            'correlation_id': correlation_id,
        }

    async def execute_task(
        self,
        user_id: str,
        session_id: str,
        capability: str,
        title: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create and execute a task."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
            permissions=['admin'] if os.environ.get('JARVIS_ENV') == 'dev' else [],
        )

        # Create task
        create_result = await self._orchestrator.execute_capability(
            capability_name='task',
            request={
                'action': 'create',
                'capability': capability,
                'title': title,
                'input': input_data or {},
            },
            context=context,
        )

        if not create_result.success:
            return {'success': False, 'error': create_result.error}

        task_id = create_result.data.get('task_id')

        # Execute task
        exec_result = await self._orchestrator.execute_capability(
            capability_name='task',
            request={'action': 'execute', 'task_id': task_id},
            context=context,
        )

        return {
            'success': exec_result.success,
            'task_id': task_id,
            'result': exec_result.data,
            'error': exec_result.error if not exec_result.success else None,
            'correlation_id': correlation_id,
        }

    async def get_capability_status(self) -> Dict[str, Any]:
        """Get status of all capabilities through live health checks."""
        return await self._registry.health_all()

    async def get_conversation_history(self, user_id: str, session_id: str) -> Dict[str, Any]:
        """Get full conversation history with context."""
        correlation_id = f"corr-{uuid.uuid4().hex[:12]}"
        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

        result = await self._orchestrator.execute_capability(
            capability_name='conversation',
            request={'action': 'get_state'},
            context=context,
        )

        if result.success:
            return result.data
        return {'error': result.error}

    async def get_system_state(self) -> Dict[str, Any]:
        """Get the full system state for the dashboard."""
        capabilities_health = await self._registry.health_all()
        capability_status = self._registry.get_status()

        # Get provider states
        from jarvis_backend.persistence import ProviderStateRepository
        provider_states = ProviderStateRepository.get_all_states()

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'capabilities': capabilities_health,
            'capability_status': capability_status,
            'providers': provider_states,
            'orchestrator_status': {
                'active_executions': len(self._orchestrator._active_executions),
            },
            'events_recent': self._event_bus.get_events(limit=20),
        }


# ============================================================================
# SINGLETON
# ============================================================================

_interaction_layer: Optional[InteractionLayer] = None


def get_interaction_layer() -> InteractionLayer:
    """Get the global interaction layer."""
    global _interaction_layer
    if _interaction_layer is None:
        _interaction_layer = InteractionLayer()
    return _interaction_layer


__all__ = [
    'InteractionLayer',
    'get_interaction_layer',
]
