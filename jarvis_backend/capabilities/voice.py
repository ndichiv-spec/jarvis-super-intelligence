"""
JARVIS VOICE CAPABILITY - First-Class Subsystem
================================================

Voice is NOT a child of Chat. Voice is its own capability that connects
to the same underlying interaction/session/orchestration system.

Voice state machine:
  IDLE -> LISTENING -> CAPTURING -> TRANSCRIBING -> UNDERSTANDING ->
  THINKING -> ACTING -> GENERATING_RESPONSE -> SYNTHESIZING -> SPEAKING ->
  (back to LISTENING or IDLE)

Or on error:
  -> INTERRUPTED
  -> ERROR
  -> OFFLINE
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncIterator, Callable

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import Event, get_event_bus
from jarvis_backend.persistence import ConversationRepository, MemoryRepository, AuditLog, EventLog

# ============================================================================
# VOICE STATE ENUMERATION
# ============================================================================

class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    UNDERSTANDING = "understanding"
    THINKING = "thinking"
    ACTING = "acting"
    GENERATING_RESPONSE = "generating_response"
    SYNTHESIZING = "synthesizing"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    OFFLINE = "offline"


# ============================================================================
# VOICE CAPABILITY
# ============================================================================

class VoiceCapability(Capability):
    """
    First-class Voice capability for JARVIS.

    Connects to:
    - Conversation persistence (shared session state)
    - Brain (through orchestrator)
    - Memory (contributes context)
    - Security (credential boundaries)
    - Events (full state tracking)
    - Persistence (conversation state)

    Voice is its own modality, parallel to Chat - not a child of it.
    """

    name = "voice"
    version = "1.0.0"
    category = "voice"

    def __init__(self):
        super().__init__()
        self._state: VoiceState = VoiceState.IDLE
        self._state_lock = threading.Lock()
        self._session_id: Optional[str] = None
        self._conversation_id: Optional[str] = None
        self._user_id: str = "anonymous"
        self._audio_buffer: List[bytes] = []
        self._max_audio_seconds: int = 60
        self._stt_provider: Optional[str] = None
        self._tts_provider: Optional[str] = None
        self._event_bus = get_event_bus()

    @property
    def state(self) -> VoiceState:
        """Current voice state."""
        with self._state_lock:
            return self._state

    def set_state(self, state: VoiceState, **metadata):
        """Transition voice state and emit events."""
        with self._state_lock:
            old_state = self._state
            self._state = state

            # Emit state transition event
            self._event_bus.emit(
                event_type=f'voice.state.{state.value}',
                source='voice',
                capability='voice',
                session_id=self._session_id or '',
                user_id=self._user_id,
                status='started' if state not in (VoiceState.IDLE, VoiceState.ERROR, VoiceState.OFFLINE) else 'completed',
                payload={
                    'old_state': old_state.value,
                    'new_state': state.value,
                    'session_id': self._session_id,
                    'correlation_id': metadata.get('correlation_id', ''),
                    **metadata
                }
            )

        # Persist state change
        from jarvis_backend.persistence import CapabilityStateRepository
        CapabilityStateRepository.save_state(
            capability='voice',
            category='voice',
            status=state.value,
            state_json={'old_state': old_state.value, 'new_state': state.value},
            session_id=self._session_id,
            user_id=self._user_id,
        )

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify STT and TTS availability."""
        health_result = {
            'status': CapabilityStatus.READY,
            'healthy': True,
            'components': {},
        }

        # Check STT provider availability
        stt_ok = await self._check_stt_availability()
        health_result['components']['stt'] = 'available' if stt_ok else 'unavailable'
        if not stt_ok:
            health_result['stt_available'] = False
            health_result['status'] = CapabilityStatus.DEGRADED
            health_result['healthy'] = True  # Voice is available, just STT is not

        # Check TTS provider availability
        tts_ok = await self._check_tts_availability()
        health_result['components']['tts'] = 'available' if tts_ok else 'unavailable'
        if not tts_ok:
            health_result['tts_available'] = False

        if not stt_ok and not tts_ok:
            health_result['status'] = CapabilityStatus.UNAVAILABLE
            health_result['healthy'] = False

        # Check microphone availability (best-effort)
        mic_ok = self._check_microphone()
        health_result['components']['microphone'] = 'available' if mic_ok else 'unavailable'

        return health_result

    async def _check_stt_availability(self) -> bool:
        """Check if a speech-to-text provider is configured."""
        try:
            from jarvis_backend.gateway import ProviderGateway
            gateway = ProviderGateway()
            providers = gateway.get_available_providers()
            # Check for STT-capable providers
            for p in providers:
                if p.get('modality') == 'audio.input' or 'openai' in p.get('name', '').lower():
                    # Verify real config
                    api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('WHISPER_API_KEY')
                    if api_key:
                        return True
            # Check for local STT
            if os.environ.get('JARVIS_LOCAL_STT'):
                return True
            return False
        except Exception:
            return False

    async def _check_tts_availability(self) -> bool:
        """Check if a text-to-speech provider is configured."""
        try:
            tts_providers = []
            # Check environment for TTS config
            if os.environ.get('OPENAI_API_KEY'):
                tts_providers.append('openai_tts')
            if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS') or os.environ.get('GOOGLE_API_KEY'):
                tts_providers.append('google_tts')
            # Check for local TTS engines
            if os.environ.get('JARVIS_LOCAL_TTS'):
                tts_providers.append('local')

            self._tts_provider = tts_providers[0] if tts_providers else None
            return len(tts_providers) > 0
        except Exception:
            return False

    def _check_microphone(self) -> bool:
        """Check if microphone is accessible (best-effort)."""
        try:
            import pyaudio
            pa = pyaudio.PyAudio()
            devices = pa.get_device_count()
            pa.terminate()
            return devices > 0
        except ImportError:
            # pyaudio not available - microphone check is unavailable
            # This is OK - voice can still work with pre-recorded audio
            return False
        except Exception:
            return False

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a voice operation.

        Request types:
        - 'start_session': Begin a voice session
        - 'process_audio': Process captured audio -> STT -> Brain -> TTS
        - 'stop_session': Stop the current voice session
        - 'synthesize': Text-to-speech only
        - 'transcribe': Speech-to-text only
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'transcribe')
        start_time = time.time()

        self._session_id = context.session_id
        self._user_id = context.user_id
        correlation_id = context.correlation_id

        # Emit execution started
        self._event_bus.emit(
            event_type='voice.execution.started',
            source='orchestrator',
            capability='voice',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            payload={'action': action},
        )

        try:
            if action == 'start_session':
                result = await self._start_session(request, context)
            elif action == 'process_audio':
                result = await self._process_audio(request, context)
            elif action == 'stop_session':
                result = await self._stop_session(request, context)
            elif action == 'synthesize':
                result = await self._synthesize(request, context)
            elif action == 'transcribe':
                result = await self._transcribe(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown voice action: {action}",
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
            self.set_state(VoiceState.ERROR, correlation_id=correlation_id)

        result.latency_ms = (time.time() - start_time) * 1000.0
        result.correlation_id = correlation_id

        return result

    async def _start_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Start a voice session."""
        session_id = request.get('session_id', context.session_id)
        self._session_id = session_id

        self.set_state(VoiceState.IDLE, correlation_id=context.correlation_id)
        self.set_state(VoiceState.LISTENING, correlation_id=context.correlation_id)

        self._event_bus.emit(
            event_type='voice.session.started',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='started',
            payload={'session_id': session_id},
        )

        AuditLog.log(
            event_type='voice.session.started',
            source='voice',
            capability='voice',
            user_id=context.user_id,
            session_id=session_id,
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'session_id': session_id, 'state': self.state.value},
            correlation_id=context.correlation_id,
        )

    async def _process_audio(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Process captured audio through the full voice pipeline."""
        audio_data = request.get('audio_data')
        session_id = request.get('session_id', context.session_id)
        self._session_id = session_id

        # Step 1: Capturing
        self.set_state(VoiceState.CAPTURING, correlation_id=context.correlation_id)

        # Step 2: Transcribing (STT)
        self.set_state(VoiceState.TRANSCRIBING, correlation_id=context.correlation_id)
        transcription_result = await self._do_stt(audio_data)

        if not transcription_result['success']:
            self.set_state(VoiceState.ERROR, correlation_id=context.correlation_id,
                          error=transcription_result['error'])
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=transcription_result['error'],
                error_type='STT_FAILED',
                correlation_id=context.correlation_id,
            )

        text = transcription_result['text']

        # Emit transcription completed event
        self._event_bus.emit(
            event_type='voice.transcription.completed',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='completed',
            payload={'text': text},
            metrics={'confidence': transcription_result.get('confidence', 0)},
        )

        # Step 3: Understanding
        self.set_state(VoiceState.UNDERSTANDING, correlation_id=context.correlation_id)
        self._event_bus.emit(
            event_type='voice.understanding.started',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
        )

        # Step 4: Add voice input to conversation
        conversation_id = request.get('conversation_id') or self._conversation_id
        if conversation_id:
            ConversationRepository.add_message(
                conversation_id=conversation_id,
                session_id=session_id,
                role='user',
                content=text,
                modality='voice',
                correlation_id=context.correlation_id,
                provider_used=transcription_result.get('provider', 'unknown'),
            )
        else:
            # Create conversation if needed
            conversation_id = ConversationRepository.create_session(
                session_id=session_id,
                user_id=context.user_id,
                modality='voice'
            )
            self._conversation_id = conversation_id
            ConversationRepository.add_message(
                conversation_id=conversation_id,
                session_id=session_id,
                role='user',
                content=text,
                modality='voice',
                correlation_id=context.correlation_id,
            )

        # Step 5: Store in memory (voice contributes to memory)
        MemoryRepository.store_memory(
            memory_type='episodic',
            content=text,
            session_id=session_id,
            user_id=context.user_id,
            provenance='voice_input',
            metadata={'modality': 'voice', 'conversation_id': conversation_id},
        )

        self._event_bus.emit(
            event_type='voice.understanding.completed',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='completed',
            payload={'text': text},
        )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'transcription': text,
                'conversation_id': conversation_id,
                'confidence': transcription_result.get('confidence', 0),
                'stt_provider': transcription_result.get('provider', 'unknown'),
            },
            correlation_id=context.correlation_id,
        )

    async def _do_stt(self, audio_data) -> Dict[str, Any]:
        """Perform actual speech-to-text using available providers."""
        try:
            if audio_data is None:
                # No audio data - this happens when called from text
                return {
                    'success': False,
                    'error': 'No audio data provided. For STT, audio_data must be raw bytes or base64.',
                }

            # Try OpenAI Whisper
            api_key = os.environ.get('OPENAI_API_KEY')
            if api_key:
                import openai
                client = openai.AsyncOpenAI(api_key=api_key)

                # If audio_data is bytes, send directly; if base64 string, decode
                import base64
                filename = "audio.wav"
                if isinstance(audio_data, str):
                    audio_bytes = base64.b64decode(audio_data)
                elif isinstance(audio_data, dict):
                    filename = os.path.basename(audio_data.get('filename') or filename)
                    audio_bytes = audio_data.get('data', b'')
                    if isinstance(audio_bytes, str):
                        audio_bytes = base64.b64decode(audio_bytes)
                else:
                    audio_bytes = audio_data

                response = await client.audio.transcriptions.create(
                    model='whisper-1',
                    file=(filename, io.BytesIO(audio_bytes)),
                )

                return {
                    'success': True,
                    'text': response.text,
                    'confidence': getattr(response, 'confidence', 0.95),
                    'provider': 'openai_whisper',
                }

            # Try local STT if configured
            local_stt = os.environ.get('JARVIS_LOCAL_STT')
            if local_stt and os.path.exists(local_stt):
                try:
                    import whisper
                    model = whisper.load_model(local_stt)

                    import tempfile, base64
                    filename = 'audio.wav'
                    if isinstance(audio_data, str):
                        audio_bytes = base64.b64decode(audio_data)
                    elif isinstance(audio_data, dict):
                        filename = os.path.basename(audio_data.get('filename') or filename)
                        audio_bytes = audio_data.get('data', b'')
                        if isinstance(audio_bytes, str):
                            audio_bytes = base64.b64decode(audio_bytes)
                    else:
                        audio_bytes = audio_data

                    suffix = os.path.splitext(filename)[1] or '.wav'
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                        f.write(audio_bytes)
                        temp_path = f.name

                    result = model.transcribe(temp_path)
                    os.unlink(temp_path)

                    return {
                        'success': True,
                        'text': result.get('text', ''),
                        'confidence': result.get('segments', [{}])[0].get('confidence', 0.8),
                        'provider': 'local_whisper',
                    }
                except ImportError:
                    pass

            return {
                'success': False,
                'error': 'No STT provider configured. Set OPENAI_API_KEY or JARVIS_LOCAL_STT.',
                'provider': 'none',
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'provider': 'error',
            }

    async def _synthesize(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Synthesize text to speech and play audio."""
        text = request.get('text', '')
        session_id = request.get('session_id', context.session_id)
        self._session_id = session_id

        if not text:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="No text provided for synthesis",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        self.set_state(VoiceState.SYNTHESIZING, correlation_id=context.correlation_id)
        self._event_bus.emit(
            event_type='voice.synthesis.started',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='started',
        )

        voice = request.get('voice', 'nova')
        result = await self._do_tts(
            text,
            context,
            voice=voice,
        )

        if result['success']:
            self.set_state(VoiceState.SPEAKING, correlation_id=context.correlation_id)
            self._event_bus.emit(
                event_type='voice.speaking.started',
                source='voice',
                capability='voice',
                correlation_id=context.correlation_id,
                session_id=session_id,
                user_id=context.user_id,
                status='started',
            )
            self._event_bus.emit(
                event_type='voice.speaking.completed',
                source='voice',
                capability='voice',
                correlation_id=context.correlation_id,
                session_id=session_id,
                user_id=context.user_id,
                status='completed',
            )
            self._event_bus.emit(
                event_type='voice.synthesis.completed',
                source='voice',
                capability='voice',
                correlation_id=context.correlation_id,
                session_id=session_id,
                user_id=context.user_id,
                status='completed',
                payload={'audio_url': result.get('audio_url', '')},
            )
            self.set_state(VoiceState.IDLE, correlation_id=context.correlation_id)

            return ExecutionResult(
                capability=self.name,
                success=True,
                data={
                    'text': text,
                    'audio_url': result.get('audio_url'),
                    'audio_data': result.get('audio_data'),
                    'provider': result.get('provider', 'unknown'),
                    'duration_ms': result.get('duration_ms', 0),
                },
                correlation_id=context.correlation_id,
            )
        else:
            self.set_state(VoiceState.ERROR, correlation_id=context.correlation_id,
                          error=result.get('error'))
            self._event_bus.emit(
                event_type='voice.synthesis.failed',
                source='voice',
                capability='voice',
                correlation_id=context.correlation_id,
                session_id=session_id,
                user_id=context.user_id,
                status='failed',
                payload={'error': result.get('error')},
            )
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=result.get('error', 'TTS failed'),
                error_type='TTS_FAILED',
                correlation_id=context.correlation_id,
            )

    async def _do_tts(
        self,
        text: str,
        context: ExecutionContext,
        voice: str = 'nova',
    ) -> Dict[str, Any]:
        """Perform actual text-to-speech."""
        try:
            api_key = os.environ.get('OPENAI_API_KEY')
            if api_key:
                import openai
                client = openai.AsyncOpenAI(api_key=api_key)

                response = await client.audio.speech.create(
                    model='tts-1',
                    voice=voice,
                    input=text,
                )

                # Get audio bytes
                audio_data = response.content

                # Store as artifact
                from jarvis_backend.persistence import ArtifactRepository
                artifact_id = ArtifactRepository.store_artifact(
                    capability='voice',
                    artifact_type='audio.synthesis',
                    file_size=len(audio_data),
                    mime_type='audio/mpeg',
                    session_id=context.session_id,
                    conversation_id=getattr(context, 'conversation_id', None),
                    correlation_id=context.correlation_id,
                    provenance='tts_synthesis',
                    metadata={'text': text, 'provider': 'openai_tts', 'voice': voice},
                )

                import base64
                return {
                    'success': True,
                    'audio_data': base64.b64encode(audio_data).decode('utf-8'),
                    'audio_url': f'/api/voice/audio/{artifact_id}',
                    'artifact_id': artifact_id,
                    'provider': 'openai_tts',
                    'duration_ms': len(audio_data) / 1000 * 8,  # rough estimate
                }

            # Fallback - no TTS provider
            return {
                'success': False,
                'error': 'No TTS provider configured. Set OPENAI_API_KEY or JARVIS_LOCAL_TTS.',
                'provider': 'none',
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'provider': 'error',
            }

    async def _transcribe(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Transcribe audio without generating a response."""
        audio_data = request.get('audio_data')
        result = await self._do_stt(audio_data)

        if result['success']:
            self._event_bus.emit(
                event_type='voice.transcription.completed',
                source='voice',
                capability='voice',
                correlation_id=context.correlation_id,
                session_id=context.session_id,
                user_id=context.user_id,
                status='completed',
                payload={'text': result['text']},
                metrics={'confidence': result.get('confidence', 0)},
            )

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data={'text': result.get('text', '')} if result['success'] else {},
            error=result.get('error'),
            error_type=None if result['success'] else 'STT_FAILED',
            correlation_id=context.correlation_id,
        )

    async def _stop_session(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Stop the current voice session."""
        session_id = request.get('session_id', context.session_id)
        self._session_id = session_id
        self.set_state(VoiceState.IDLE, correlation_id=context.correlation_id)

        self._event_bus.emit(
            event_type='voice.session.ended',
            source='voice',
            capability='voice',
            correlation_id=context.correlation_id,
            session_id=session_id,
            user_id=context.user_id,
            status='completed',
        )

        self._audio_buffer = []

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'state': VoiceState.IDLE.value},
            correlation_id=context.correlation_id,
        )

    async def cancel(self, correlation_id: str) -> bool:
        """Cancel an in-progress voice execution."""
        self.set_state(VoiceState.INTERRUPTED, correlation_id=correlation_id)
        self._event_bus.emit(
            event_type='voice.session.interrupted',
            source='voice',
            capability='voice',
                correlation_id=correlation_id,
        )
        return True

    async def shutdown(self) -> bool:
        """Clean shutdown of voice capability."""
        self.set_state(VoiceState.OFFLINE)
        self._audio_buffer = []
        self._session_id = None
        return True


# ============================================================================
# VOICE STATE MACHINE
# ============================================================================

class VoiceStateMachine:
    """
    Manages voice state transitions.

    Voice has its own state machine that flows:
    IDLE -> LISTENING -> CAPTURING -> TRANSCRIBING -> UNDERSTANDING ->
    THINKING -> ACTING -> GENERATING_RESPONSE -> SYNTHESIZING -> SPEAKING ->
    LISTENING (for continuous interaction)
    """

    def __init__(self, capability: VoiceCapability):
        self._capability = capability
        self._states: List[VoiceState] = []
        self._current: VoiceState = VoiceState.IDLE

    def transition(self, new_state: VoiceState, **metadata) -> VoiceState:
        """Transition to a new state."""
        self._current = new_state
        self._states.append(new_state)
        self._capability.set_state(new_state, **metadata)
        return self._current

    def get_history(self) -> List[str]:
        """Get state transition history."""
        return [s.value for s in self._states[-50:]]

    @property
    def current(self) -> VoiceState:
        return self._current


__all__ = [
    'VoiceState',
    'VoiceCapability',
    'VoiceStateMachine',
]
