"""
JARVIS VISION CAPABILITY
=========================

Vision is an independent capability - NOT a child of Chat. Vision connects
to the same underlying interaction/session/orchestration system.

Supports:
- Image understanding (multimodal LLM analysis)
- OCR (text extraction from images)
- Screenshot analysis
- Visual reasoning
- Document vision
- Camera input (where hardware permits)
- Visual context for the Brain

Vision results are available to the Brain through the orchestration layer.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import base64
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ArtifactRepository, AuditLog


class VisionCapability(Capability):
    """
    Independent Vision capability for JARVIS.

    Vision is NOT controlled by Chat. Vision can be invoked by:
    - Chat (user sends an image)
    - Voice (user describes "what's in this image")
    - Brain (autonomous reasoning requires visual context)

    Vision contributes results to:
    - Conversation (as context)
    - Memory (visual memories)
    - Brain (visual reasoning)
    """

    name = "vision"
    version = "1.0.0"
    category = "vision"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._max_image_size = 10 * 1024 * 1024  # 10MB limit
        self._inference_verified = False

    async def _check_health(self) -> Dict[str, Any]:
        """Report configured vision backends without implying inference worked."""
        configured_providers = []

        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            configured_providers.append({
                'name': 'openai',
                'models': ['gpt-4o', 'gpt-4-vision-preview'],
                'status': 'configured',
            })

        google_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        google_api_key = os.environ.get('GOOGLE_API_KEY')
        if google_creds or google_api_key:
            configured_providers.append({
                'name': 'google',
                'models': ['gemini-1.5-flash', 'gemini-pro-vision'],
                'status': 'configured',
            })

        local_vision = os.environ.get('JARVIS_LOCAL_VISION')
        if local_vision:
            configured_providers.append({
                'name': 'local',
                'models': [local_vision],
                'status': 'configured',
            })

        status = (
            CapabilityStatus.AVAILABLE if self._inference_verified
            else CapabilityStatus.CONFIGURED if configured_providers
            else CapabilityStatus.NOT_CONFIGURED
        )
        return {
            'status': status,
            'providers': configured_providers,
            'configured': bool(configured_providers),
            'healthy': self._inference_verified,
            'ocr_available': self._inference_verified,
            'image_understanding_available': self._inference_verified,
            'inference_verified': self._inference_verified,
            'error': None if configured_providers else (
                'No vision provider configured. Set OPENAI_API_KEY, '
                'GOOGLE_API_KEY, or JARVIS_LOCAL_VISION.'
            ),
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute a vision operation.

        Request actions:
        - 'analyze_image': Full image analysis with prompt
        - 'ocr': Extract text from image
        - 'describe': Generate description of image
        - 'extract_objects': Identify objects in image
        - 'compare_images': Compare two images
        - 'analyze_document': Analyze document image
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'analyze_image')
        start_time = time.time()
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type='vision.analysis.started',
            source='orchestrator',
            capability='vision',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action},
        )

        try:
            if action == 'analyze_image':
                result = await self._analyze_image(request, context)
            elif action == 'ocr':
                result = await self._ocr(request, context)
            elif action == 'describe':
                result = await self._describe_image(request, context)
            elif action == 'extract_objects':
                result = await self._extract_objects(request, context)
            elif action == 'compare_images':
                result = await self._compare_images(request, context)
            elif action == 'analyze_document':
                result = await self._analyze_document(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown vision action: {action}",
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
        if result.success:
            self._inference_verified = True
            self.set_status(CapabilityStatus.AVAILABLE)

        # Emit completion
        self._event_bus.emit(
            event_type='vision.analysis.completed',
            source='vision',
            capability='vision',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload=result.to_dict(),
        )

        # Store artifact if an image was processed
        if result.success and request.get('image_data'):
            ArtifactRepository.store_artifact(
                capability='vision',
                artifact_type='vision_input',
                file_size=len(request.get('image_data', b'')),
                mime_type='image/png',
                session_id=context.session_id,
                correlation_id=correlation_id,
                provenance='vision_analysis',
                metadata={'action': action, 'result': result.data},
            )

        AuditLog.log(
            event_type=f'vision.{action}',
            source='vision',
            capability='vision',
            user_id=context.user_id,
            session_id=context.session_id,
            action=action,
            result='success' if result.success else 'error',
        )

        return result

    async def _analyze_image(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Analyze an image with a prompt."""
        image_data = request.get('image_data')
        prompt = request.get('prompt', 'What is in this image?')

        if not image_data:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="image_data required for image analysis",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        result = await self._call_multimodal_llm(image_data, prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
            artifacts=[{
                'type': 'vision_analysis',
                'content': result.get('data', {}).get('analysis', ''),
            }] if result['success'] else [],
        )

    async def _ocr(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Extract text from an image using OCR."""
        image_data = request.get('image_data')

        if not image_data:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="image_data required for OCR",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        # Use OpenAI's OCR capabilities via vision model
        prompt = "Extract all text from this image. Return only the text content, nothing else."
        result = await self._call_multimodal_llm(image_data, prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
            artifacts=[{
                'type': 'ocr_text',
                'content': result.get('data', {}).get('analysis', ''),
            }] if result['success'] else [],
        )

    async def _describe_image(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Generate a detailed description of an image."""
        image_data = request.get('image_data')
        prompt = "Describe this image in detail."

        result = await self._call_multimodal_llm(image_data, prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
        )

    async def _extract_objects(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Identify and list objects in an image."""
        image_data = request.get('image_data')
        prompt = ("Identify all objects, people, and items in this image. "
                   "List each item on a separate line with its position.")

        result = await self._call_multimodal_llm(image_data, prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
        )

    async def _compare_images(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Compare two images."""
        image1 = request.get('image_data_1')
        image2 = request.get('image_data_2')

        if not image1 or not image2:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error="Both image_data_1 and image_data_2 required for comparison",
                error_type="INVALID_INPUT",
                correlation_id=context.correlation_id,
            )

        # Combine both images for comparison
        prompt = ("Compare these two images. What is similar and what is different? "
                   "Describe the differences in detail.")

        result = await self._call_multimodal_llm([image1, image2], prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
        )

    async def _analyze_document(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Analyze a document image."""
        image_data = request.get('image_data')
        prompt = ("Analyze this document. Extract the text, key fields, dates, "
                   "amounts, and summarize the content. If it's a table, extract it.")

        result = await self._call_multimodal_llm(image_data, prompt)

        return ExecutionResult(
            capability=self.name,
            success=result['success'],
            data=result.get('data', {}),
            error=result.get('error'),
            error_type=result.get('error_type'),
            correlation_id=context.correlation_id,
        )

    async def _call_multimodal_llm(
        self,
        image_data: Any,
        prompt: str,
    ) -> Dict[str, Any]:
        """Call a multimodal LLM to analyze an image."""

        # Handle base64 encoded images
        is_base64 = isinstance(image_data, str) and not image_data.startswith('http')
        images = image_data if isinstance(image_data, list) else [image_data]

        # Try OpenAI
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)

                content = [{"type": "text", "text": prompt}]

                for img in images:
                    if isinstance(img, str) and img.startswith('http'):
                        content.append({"type": "image_url", "image_url": {"url": img}})
                    else:
                        # Assume base64
                        img_str = img if img.startswith('data:image') else f"data:image/png;base64,{img}"
                        content.append({"type": "image_url", "image_url": {"url": img_str}})

                response = client.chat.completions.create(
                    model='gpt-4o',
                    messages=[{"role": "user", "content": content}],
                    max_tokens=4000,
                )

                analysis = response.choices[0].message.content.strip()
                return {
                    'success': True,
                    'data': {
                        'analysis': analysis,
                        'provider': 'openai_gpt4o',
                        'model': 'gpt-4o',
                        'usage': {
                            'input_tokens': response.usage.input_tokens,
                            'output_tokens': response.usage.output_tokens,
                        },
                    },
                }
            except Exception as e:
                # Try Google as fallback
                pass

        # Try Google Gemini
        google_key = os.environ.get('GOOGLE_API_KEY')
        google_creds = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
        if google_key or google_creds:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=google_key) if google_key else \
                       genai.Client(credentials_file=google_creds)

                content_parts = [types.Part.from_text(prompt)]
                for img in images:
                    img_bytes = base64.b64decode(img) if isinstance(img, str) else img
                    content_parts.append(types.Part.from_bytes(img_bytes, "image/png"))

                response = client.models.generate_content(
                    model='gemini-1.5-flash',
                    contents=[types.Content(role='user', parts=content_parts)],
                )

                analysis = response.text
                return {
                    'success': True,
                    'data': {
                        'analysis': analysis,
                        'provider': 'google_gemini',
                        'model': 'gemini-1.5-flash',
                    },
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': f"Vision provider error: {e}",
                    'error_type': 'PROVIDER_ERROR',
                }

        return {
            'success': False,
            'error': 'No vision provider configured. Set OPENAI_API_KEY or GOOGLE_API_KEY.',
            'error_type': 'NOT_CONFIGURED',
        }

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['VisionCapability']
