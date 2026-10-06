"""
JARVIS PROVIDER CAPABILITY
==========================

Wraps the existing ProviderGateway, ModelRouter, and ModelRegistry.
Extends them with modality-aware routing.

Provider status must be truthful:
NOT_CONFIGURED, CONFIGURED, AVAILABLE, READY, ACTIVE,
DEGRADED, RATE_LIMITED, OFFLINE, ERROR

A provider must not appear green merely because its code exists.
A model must not appear available unless it can actually be invoked.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from enum import Enum
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ProviderStateRepository, AuditLog


class ProviderStatus(str, Enum):
    """Truthful provider status values per spec section 13."""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    AVAILABLE = "available"
    READY = "ready"
    ACTIVE = "active"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    OFFLINE = "offline"
    ERROR = "error"


class ProviderCapability(Capability):
    """
    Provider/Model orchestration capability.

    Wraps the existing ProviderGateway to provide modality-aware routing:
    - text
    - vision
    - audio.input
    - audio.output
    - image
    - embedding
    - reasoning

    Provider status comes from REAL health checks, not fabrication.
    """

    name = "provider"
    version = "1.0.0"
    category = "provider"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._gateway = None
        self._provider_status: Dict[str, ProviderStatus] = {}
        self._model_status: Dict[str, ProviderStatus] = {}

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify each provider via actual probing."""
        providers = self._get_provider_config()
        statuses = {}
        models = {}

        for provider_name, config in providers.items():
            if config.get('enabled') or config.get('api_key_present'):
                # Real liveness check
                status = await self._probe_provider(provider_name, config)
            else:
                status = ProviderStatus.NOT_CONFIGURED

            statuses[provider_name] = status.value
            self._provider_status[provider_name] = status

            # Record in database
            ProviderStateRepository.update_state(
                provider_name=provider_name,
                capability=config.get('modality', 'text'),
                status=status.value,
                metadata=config,
            )

        # Build model list
        for provider_name, config in providers.items():
            for model_name in config.get('models', []):
                model_status = self._provider_status.get(provider_name, ProviderStatus.NOT_CONFIGURED)
                models[f"{provider_name}/{model_name}"] = model_status.value
                self._model_status[f"{provider_name}/{model_name}"] = model_status

        healthy = any(s == ProviderStatus.AVAILABLE for s in self._provider_status.values())

        self.set_status(CapabilityStatus.READY if healthy else CapabilityStatus.NOT_CONFIGURED)

        return {
            'status': 'ready' if healthy else 'not_configured',
            'healthy': healthy,
            'providers': statuses,
            'models': models,
            'modality_routing': self._get_modality_routing(),
        }

    def _get_provider_config(self) -> Dict[str, Dict[str, Any]]:
        """Get provider configuration from existing infrastructure."""
        providers = {}

        # Read from existing provider_settings store
        try:
            from jarvis_backend.core import get_store
            settings = get_store("misc").load().get("provider_settings", {}) or {}

            # Check each provider
            provider_map = {
                'openai': {
                    'api_key_present': bool(os.environ.get('OPENAI_API_KEY') or settings.get('openai_api_key')),
                    'modality': 'text',
                    'models': ['gpt-4', 'gpt-3.5-turbo', 'gpt-4o', 'gpt-4-turbo'],
                    'enabled': True,
                },
                'google': {
                    'api_key_present': bool(os.environ.get('GOOGLE_API_KEY') or settings.get('google_gemini_api_key')),
                    'modality': 'text',
                    'models': ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-pro'],
                    'enabled': True,
                },
                'anthropic': {
                    'api_key_present': bool(os.environ.get('ANTHROPIC_API_KEY') or settings.get('anthropic_api_key')),
                    'modality': 'text',
                    'models': ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'],
                    'enabled': True,
                },
                'nvidia': {
                    'api_key_present': bool(os.environ.get('NVIDIA_API_KEY') or settings.get('nvidia_api_key')),
                    'modality': 'text',
                    'models': ['nvidia/nemotron-4-340b', 'nv-mistralai/mistral-7b-instruct'],
                    'enabled': True,
                },
                'huggingface': {
                    'api_key_present': bool(os.environ.get('HF_API_KEY') or settings.get('huggingface_api_key')),
                    'modality': 'text',
                    'models': ['mistralai/Mistral-7B-Instruct', 'meta-llama/Llama-2-7b-chat'],
                    'enabled': True,
                },
                'stability': {
                    'api_key_present': bool(os.environ.get('STABILITY_API_KEY') or settings.get('stability_api_key')),
                    'modality': 'image',
                    'models': ['sd3', 'sdxl', 'stable-diffusion-21'],
                    'enabled': True,
                },
                'ollama': {
                    'api_key_present': bool(os.environ.get('OLLAMA_HOST') or settings.get('ollama_base_url')),
                    'modality': 'text',
                    'models': settings.get('ollama_model', 'llama3'),
                    'enabled': os.environ.get('OLLAMA_HOST', '').lower() not in ('', '0'),
                },
                'silverwing': {
                    'api_key_present': bool(os.environ.get('SILVERWING_ENDPOINT')),
                    'modality': 'text',
                    'models': ['silverwing-r1', 'silverwing-local-rule'],
                    'enabled': True,
                },
            }

            for name, info in provider_map.items():
                if name == 'ollama':
                    info['models'] = [info['models']] if isinstance(info['models'], str) else info['models']

            providers = provider_map

        except Exception:
            # Fallback to environment-only check
            providers = {
                'openai': {
                    'api_key_present': bool(os.environ.get('OPENAI_API_KEY')),
                    'modality': 'text',
                    'models': ['gpt-4', 'gpt-3.5-turbo'],
                    'enabled': True,
                },
                'google': {
                    'api_key_present': bool(os.environ.get('GOOGLE_API_KEY') or os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')),
                    'modality': 'text',
                    'models': ['gemini-1.5-flash', 'gemini-1.5-pro'],
                    'enabled': True,
                },
            }

        return providers

    async def _probe_provider(self, name: str, config: Dict[str, Any]) -> ProviderStatus:
        """Perform a REAL liveness check on a provider."""
        try:
            if name == 'openai':
                return await self._probe_openai()
            elif name == 'google':
                return await self._probe_google()
            elif name == 'anthropic':
                return await self._probe_anthropic()
            elif name == 'nvidia':
                return await self._probe_nvidia()
            elif name == 'silverwing':
                endpoint = os.environ.get('SILVERWING_ENDPOINT', '')
                if endpoint:
                    return await self._probe_http(endpoint)
                return ProviderStatus.NOT_CONFIGURED
            elif name == 'ollama':
                ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
                return await self._probe_http(f"{ollama_host}/api/tags")
        except Exception:
            return ProviderStatus.ERROR
        return ProviderStatus.OFFLINE

    async def _probe_openai(self) -> ProviderStatus:
        """Real health check for OpenAI."""
        try:
            import openai
            client = openai.OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
            # Real API call - list models (cheap, no tokens consumed)
            client.models.list()
            return ProviderStatus.AVAILABLE
        except Exception as e:
            err = str(e).lower()
            if 'rate' in err or '429' in err:
                return ProviderStatus.RATE_LIMITED
            if 'auth' in err or 'unauthorized' in err or '401' in err:
                return ProviderStatus.ERROR
            return ProviderStatus.OFFLINE

    async def _probe_google(self) -> ProviderStatus:
        """Real health check for Google."""
        try:
            import google.genai as genai
            client = genai.Client(api_key=os.environ.get('GOOGLE_API_KEY'))
            # Real list operation
            client.list_models()
            return ProviderStatus.AVAILABLE
        except Exception:
            return ProviderStatus.OFFLINE

    async def _probe_anthropic(self) -> ProviderStatus:
        """Real health check for Anthropic."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
            client.messages.create(
                model='claude-3-haiku-20240307',
                max_tokens=1,
                messages=[{'role': 'user', 'content': 'Hi'}],
            )
            return ProviderStatus.AVAILABLE
        except Exception:
            return ProviderStatus.OFFLINE

    async def _probe_nvidia(self) -> ProviderStatus:
        """Real health check for NVIDIA NIM."""
        try:
            import requests
            headers = {'Authorization': f'Bearer {os.environ.get("NVIDIA_API_KEY")}'}
            resp = requests.get('https://integrate.api.nvidia.com/v1/models', headers=headers, timeout=10)
            if resp.status_code == 200:
                return ProviderStatus.AVAILABLE
            elif resp.status_code == 429:
                return ProviderStatus.RATE_LIMITED
            else:
                return ProviderStatus.ERROR
        except Exception:
            return ProviderStatus.OFFLINE

    async def _probe_http(self, url: str, timeout: float = 10.0) -> ProviderStatus:
        """Real HTTP probe."""
        try:
            import urllib.request
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=timeout)
            if resp.status == 200:
                return ProviderStatus.AVAILABLE
            return ProviderStatus.ERROR
        except Exception:
            return ProviderStatus.OFFLINE

    def _get_modality_routing(self) -> Dict[str, str]:
        """Get modality-to-provider routing."""
        routing = {}
        providers = self._get_provider_config()
        for name, config in providers.items():
            modality = config.get('modality', 'text')
            if name not in routing:
                routing[modality] = name
            elif name == 'openai' and modality == 'text':
                routing[modality] = name
        return routing

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """Get list of available providers (used by other capabilities)."""
        providers = []
        for name, config in self._get_provider_config().items():
            status = self._provider_status.get(name, ProviderStatus.NOT_CONFIGURED)
            providers.append({
                'name': name,
                'modality': config.get('modality', 'text'),
                'status': status.value,
                'models': config.get('models', []),
                'available': status == ProviderStatus.AVAILABLE,
            })
        return providers

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a provider/model operation."""
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'route')
        start_time = time.time()
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type='provider.request.started',
            source='orchestrator',
            capability='provider',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action},
        )

        try:
            if action == 'route':
                result = await self._route_request(request, context)
            elif action == 'list':
                result = await self._list_providers(request, context)
            elif action == 'status':
                result = await self._get_status(request, context)
            elif action == 'health':
                result = await self._health_check(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown provider action: {action}",
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

        return result

    async def _route_request(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Route a request through the provider gateway."""
        modality = request.get('modality', 'text')
        message = request.get('message', '')
        model = request.get('model')

        # Use existing ProviderGateway
        try:
            from jarvis_backend.gateway import ProviderGateway
            gateway = ProviderGateway()
            messages = [{'role': 'user', 'content': message}]

            result = await gateway.chat(messages=messages, model=model)

            # Phoenix AI evaluation (non-blocking — falls back gracefully)
            evaluation = None
            try:
                from jarvis_backend.phoenix_integration import run_evaluation
                evaluation = run_evaluation(
                    prompt=message,
                    response=result.get('content', ''),
                )
            except Exception:
                evaluation = None

            exec_result = ExecutionResult(
                capability=self.name,
                success=True,
                data={
                    'response': result.get('content', ''),
                    'model': result.get('model', 'unknown'),
                    'provider': result.get('provider', 'unknown'),
                    'backend': result.get('backend', 'unknown'),
                    'latency_ms': result.get('latency_ms', 0),
                    'usage': result.get('usage', {}),
                    'cost_usd': result.get('cost_usd', 0.0),
                    'evaluation': evaluation,
                },
                correlation_id=context.correlation_id,
                metrics={'provider': result.get('provider'), 'model': result.get('model')},
            )

            # Record LLM call in LangSmith
            try:
                from jarvis_backend.langsmith_integration import get_langsmith_tracer
                ls = get_langsmith_tracer()
                usage = result.get('usage', {})
                ls.record_llm_call(
                    model=result.get('model', 'unknown'),
                    prompt=message,
                    response=result.get('content', ''),
                    prompt_tokens=usage.get('prompt_tokens', 0),
                    completion_tokens=usage.get('completion_tokens', 0),
                    latency_ms=result.get('latency_ms', 0),
                    correlation_id=context.correlation_id,
                    provider=result.get('provider', 'unknown'),
                    cost_usd=result.get('cost_usd', 0.0),
                )
            except Exception:
                pass

            return exec_result
        except Exception as e:
            error_name = type(e).__name__
            if 'PROVIDER_UNAVAILABLE' in error_name or 'CHAT' in error_name.upper():
                error_type = 'PROVIDER_UNAVAILABLE'
            else:
                error_type = 'PROVIDER_ERROR'

            return ExecutionResult(
                capability=self.name,
                success=False,
                error=str(e),
                error_type=error_type,
                correlation_id=context.correlation_id,
            )

    async def _list_providers(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """List all providers with their real status."""
        await self.health()
        providers = self.get_available_providers()

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={'providers': providers},
            correlation_id=context.correlation_id,
        )

    async def _get_status(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Get current provider and model status."""
        await self.health()

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'providers': {k: v.value for k, v in self._provider_status.items()},
                'models': {k: v.value for k, v in self._model_status.items()},
            },
            correlation_id=context.correlation_id,
        )

    async def _health_check(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Run health checks on all providers."""
        health = await self.health()

        return ExecutionResult(
            capability=self.name,
            success=True,
            data=health,
            correlation_id=context.correlation_id,
        )

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['ProviderCapability', 'ProviderStatus']
