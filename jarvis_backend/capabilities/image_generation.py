"""
JARVIS IMAGE GENERATION CAPABILITY
===================================

Image generation is a FIRST-CLASS capability - NOT owned by Chat.

Image generation has its own:
- request
- provider/model selection
- execution
- status
- artifact storage
- provenance
- error handling
- permissions
- audit
- metrics

A conversation can invoke image generation.
Voice can request image generation.
The Brain can decide image generation is required.

But image generation remains its own capability.

Generated images become REAL artifacts stored in the database.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import base64
import uuid
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.core import DATA_DIR
from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ArtifactRepository, AuditLog, ProviderStateRepository


class ImageGenerationCapability(Capability):
    """
    First-class Image Generation capability.

    Independent from Chat. Has its own provider/model selection.
    Results are persisted as real artifacts.
    """

    name = "image.generate"
    version = "1.0.0"
    category = "image_generation"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._generation_verified = False
        self._artifact_dir = os.environ.get(
            'JARVIS_ARTIFACT_DIR',
            str(DATA_DIR / 'artifacts' / 'images'),
        )
        os.makedirs(self._artifact_dir, exist_ok=True)

    async def _check_health(self) -> Dict[str, Any]:
        """Report image providers as configured until generation succeeds."""
        providers = []

        # Check OpenAI DALL-E
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)
                client.models.list()
                providers.append({
                    'name': 'openai_dalle',
                    'models': ['dall-e-2', 'dall-e-3'],
                    'status': 'configured',
                })
            except Exception as e:
                providers.append({
                    'name': 'openai_dalle',
                    'status': 'unavailable',
                    'error': type(e).__name__,
                })
        else:
            providers.append({
                'name': 'openai_dalle',
                'status': 'not_configured',
            })

        # Check stability/stability AI
        stability_key = os.environ.get('STABILITY_API_KEY')
        if stability_key:
            providers.append({
                'name': 'stability',
                'models': ['sd3', 'sdxl', 'stable-diffusion-21'],
                'status': 'configured',
            })
        else:
            providers.append({
                'name': 'stability',
                'status': 'not_configured',
            })

        # Check for local model
        local_model = os.environ.get('JARVIS_LOCAL_IMAGE_MODEL')
        if local_model:
            providers.append({
                'name': 'local',
                'models': [local_model],
                'status': 'configured',
            })

        configured = any(p['status'] == 'configured' for p in providers)

        ProviderStateRepository.update_state(
            provider_name='image_generation',
            capability='image.generate',
            status='configured' if configured else 'not_configured',
            latency_ms=0,
            metadata={'providers': providers},
        )

        return {
            'status': (
                CapabilityStatus.AVAILABLE if self._generation_verified
                else CapabilityStatus.CONFIGURED if configured
                else CapabilityStatus.NOT_CONFIGURED
            ),
            'providers': providers,
            'configured': configured,
            'healthy': self._generation_verified,
            'generation_verified': self._generation_verified,
            'artifact_directory': self._artifact_dir,
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute an image generation request.

        Request fields:
        - prompt: Text description of the image
        - model: Optional model selection
        - size: Image dimensions (e.g., "1024x1024")
        - quality: "standard" or "hd"
        - n: Number of images
        - provider: Optional provider override
        - conversation_id: Link to conversation
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        prompt = request.get('prompt', '')
        if not prompt:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="prompt is required for image generation",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        start_time = time.time()
        correlation_id = context.correlation_id

        # Emit start event
        self._event_bus.emit(
            event_type='image.generation.started',
            source='orchestrator',
            capability='image.generate',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={
                'prompt_length': len(prompt),
                'size': request.get('size', '1024x1024'),
                'execution_id': context.execution_id,
            },
        )

        try:
            result = await self._generate_image(prompt, request, context)
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

        # Store artifacts
        artifact_ids = []
        if result.success and result.artifacts:
            for artifact in result.artifacts:
                artifact_id = ArtifactRepository.store_artifact(
                    capability='image.generate',
                    artifact_type='image.generated',
                    file_path=artifact.get('file_path'),
                    file_size=artifact.get('size', 0),
                    mime_type='image/png',
                    session_id=context.session_id,
                    conversation_id=request.get('conversation_id'),
                    correlation_id=correlation_id,
                    provenance=f"image_generation_{artifact.get('provider', 'unknown')}",
                    metadata={
                        'owner_id': context.user_id,
                        'prompt': prompt,
                        'model': artifact.get('model'),
                        'provider': artifact.get('provider'),
                    },
                )
                if isinstance(artifact_id, str):
                    artifact_ids.append(artifact_id)

        self._event_bus.emit(
            event_type=(
                'image.generation.completed'
                if result.success
                else 'image.generation.failed'
            ),
            source='image.generate',
            capability='image.generate',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='completed' if result.success else 'failed',
            payload={
                'success': result.success,
                'artifact_count': len(result.artifacts),
                'artifact_ids': artifact_ids,
                'execution_id': context.execution_id,
            },
            metrics={'latency_ms': result.latency_ms, 'artifact_count': len(result.artifacts)},
        )

        AuditLog.log(
            event_type='image.generation',
            source='image.generate',
            capability='image.generate',
            user_id=context.user_id,
            session_id=context.session_id,
            action='generate',
            resource='image',
            result='success' if result.success else 'error',
            details=f"prompt_length={len(prompt)}",
        )

        return result

    async def _generate_image(
        self,
        prompt: str,
        request: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Generate image using available provider."""

        # Provider/model selection
        provider_name = request.get('provider', 'auto')
        model = request.get('model', 'auto')
        size = request.get('size', '1024x1024')
        n = request.get('n', 1)
        quality = request.get('quality', 'standard')

        artifacts: List[Dict[str, Any]] = []

        # Try OpenAI DALL-E
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key and (provider_name == 'auto' or provider_name == 'openai' or provider_name == 'openai_dalle'):
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)

                dalle_model = 'dall-e-3' if model == 'dall-e-3' or model == 'auto' else model
                if dalle_model == 'dall-e-2':
                    response = client.images.generate(
                        model=dalle_model,
                        prompt=prompt,
                        n=n,
                        size=size,
                    )
                else:
                    response = client.images.generate(
                        model=dalle_model,
                        prompt=prompt,
                        n=n,
                        size=size,
                        quality=quality,
                        response_format='b64_json',
                    )

                for i, img in enumerate(response.data):
                    b64_data = img.b64_json
                    img_bytes = base64.b64decode(b64_data)

                    # Save to artifact directory
                    file_name = f"img_{uuid.uuid4().hex[:8]}.png"
                    file_path = os.path.join(self._artifact_dir, file_name)

                    with open(file_path, 'wb') as f:
                        f.write(img_bytes)

                    artifacts.append({
                        'file_path': file_path,
                        'url': f'/api/artifacts/{file_name}',
                        'size': len(img_bytes),
                        'mime_type': 'image/png',
                        'model': dalle_model,
                        'provider': 'openai_dalle',
                        'index': i,
                    })

                if not artifacts:
                    raise ValueError("Image provider returned no image data")
                self._generation_verified = True
                self.set_status(CapabilityStatus.AVAILABLE)
                ProviderStateRepository.update_state(
                    provider_name='openai_dalle',
                    capability='image.generate',
                    status=CapabilityStatus.AVAILABLE.value,
                    latency_ms=0,
                )
                return ExecutionResult(
                    capability=self.name,
                    success=True,
                    data={
                        'prompt': prompt,
                        'model': dalle_model,
                        'provider': 'openai_dalle',
                        'artifact_count': len(artifacts),
                    },
                    artifacts=artifacts,
                    metrics={
                        'total_size_bytes': sum(a['size'] for a in artifacts),
                        'model': dalle_model,
                    },
                    correlation_id=context.correlation_id,
                )

            except Exception as e:
                error_msg = str(e)
                if 'quota' in error_msg.lower() or 'rate' in error_msg.lower():
                    ProviderStateRepository.update_state(
                        'openai_dalle', 'image.generate',
                        CapabilityStatus.RATE_LIMITED.value,
                        error=error_msg,
                    )
                else:
                    ProviderStateRepository.update_state(
                        'openai_dalle', 'image.generate',
                        CapabilityStatus.ERROR.value,
                        error=error_msg,
                    )

                # Don't return yet - try fallback providers
                last_error = error_msg

        # Try Stability AI
        stability_key = os.environ.get('STABILITY_API_KEY')
        if stability_key and (provider_name == 'auto' or provider_name == 'stability'):
            try:
                import requests
                api_host = os.environ.get('STABILITY_API_HOST', 'https://api.stability.ai')
                engine = 'sd3-large' if model == 'auto' else model

                response = requests.post(
                    f"{api_host}/v2beta/stable-image",
                    headers={
                        'Authorization': f'Bearer {stability_key}',
                        'Accept': 'image/*',
                    },
                    files={'prompt': (None, prompt)},
                    timeout=120,
                )

                if response.status_code == 200:
                    img_bytes = response.content
                    file_name = f"img_{uuid.uuid4().hex[:8]}.png"
                    file_path = os.path.join(self._artifact_dir, file_name)

                    with open(file_path, 'wb') as f:
                        f.write(img_bytes)

                    artifacts.append({
                        'file_path': file_path,
                        'url': f'/api/artifacts/{file_name}',
                        'size': len(img_bytes),
                        'mime_type': 'image/png',
                        'model': engine,
                        'provider': 'stability',
                    })

                    self._generation_verified = True
                    self.set_status(CapabilityStatus.AVAILABLE)
                    ProviderStateRepository.update_state(
                        provider_name='stability',
                        capability='image.generate',
                        status=CapabilityStatus.AVAILABLE.value,
                        latency_ms=0,
                    )
                    return ExecutionResult(
                        capability=self.name,
                        success=True,
                        data={
                            'prompt': prompt,
                            'model': engine,
                            'provider': 'stability',
                            'artifact_count': len(artifacts),
                        },
                        artifacts=artifacts,
                        correlation_id=context.correlation_id,
                    )
                else:
                    last_error = f"Stability API returned {response.status_code}: {response.text}"
            except ImportError:
                last_error = "requests library not available for Stability AI"
            except Exception as e:
                last_error = str(e)

        # If we got here, all providers failed
        error_msg = locals().get('last_error', 'No image generation provider available')
        if not api_key and not stability_key:
            error_msg = ("No image generation provider configured. "
                         "Set OPENAI_API_KEY for DALL-E or STABILITY_API_KEY for Stable Diffusion.")

        return ExecutionResult(
            capability=self.name,
            success=False,
            error=error_msg,
            error_type='NO_PROVIDER' if 'not configured' in error_msg.lower() else 'PROVIDER_ERROR',
            correlation_id=context.correlation_id,
        )

    async def cancel(self, correlation_id: str) -> bool:
        """Cancel image generation - note: DALL-E generation can't be cancelled mid-flight."""
        return False

    async def shutdown(self) -> bool:
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['ImageGenerationCapability']
