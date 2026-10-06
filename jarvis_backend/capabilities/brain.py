"""
JARVIS BRAIN CAPABILITY
========================

The Brain is the reasoning and orchestration subsystem. It receives context
from Conversation, Memory, Knowledge, and tools, and selects which
capabilities to execute.

The Brain should NOT receive:
- provider API keys
- database passwords
- GitHub tokens
- cloud credentials
- arbitrary secrets

Credentials remain behind the connector/security boundary.

Flow:
    Brain
    |- Tool request
    |- Authorization
    |- Connector
    |- Credential boundary
    |- External system
    |- Sanitized result
    |- Brain
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jarvis_backend.capability import Capability, CapabilityStatus, ExecutionContext, ExecutionResult
from jarvis_backend.event_fabric import get_event_bus
from jarvis_backend.persistence import ConversationRepository, MemoryRepository, AuditLog


class BrainCapability(Capability):
    """
    The JARVIS Brain - reasoning and capability orchestration core.

    The Brain does NOT directly call providers. Instead, it:
    1. Receives context (conversation, memory, knowledge)
    2. Decides what capabilities are needed
    3. Returns a decision/plan
    4. The Orchestrator executes the selected capabilities
    5. Results come back to the Brain for final response
    """

    name = "brain"
    version = "1.0.0"
    category = "brain"

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._orchestrator = None
        self._thinking_log: List[Dict[str, Any]] = []

    def set_orchestrator(self, orchestrator):
        """Set reference to the orchestrator for capability execution."""
        self._orchestrator = orchestrator

    async def _check_health(self) -> Dict[str, Any]:
        """Real health check - verify Brain can access providers."""
        providers_available = False
        try:
            from jarvis_backend.gateway import ProviderGateway
            gateway = ProviderGateway()
            providers = gateway.get_available_providers()
            providers_available = len(providers) > 0
        except Exception:
            providers_available = os.environ.get('OPENAI_API_KEY') is not None

        return {
            'status': CapabilityStatus.READY if providers_available else CapabilityStatus.NOT_CONFIGURED,
            'providers_available': providers_available,
            'healthy': providers_available,
            'thinking_log_entries': len(self._thinking_log),
        }

    async def execute(
        self,
        request: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """
        Execute Brain reasoning.

        Request fields:
        - action: 'reason', 'plan', 'decide', 'respond'
        - input: The input to reason about
        - conversation_id: Current conversation context
        - context: Additional context for the Brain
        - allowed_capabilities: List of capabilities the Brain can select
        """
        if context is None:
            context = ExecutionContext(user_id="anonymous", session_id="default")

        action = request.get('action', 'reason')
        correlation_id = context.correlation_id

        self._event_bus.emit(
            event_type='brain.reasoning.started',
            source='orchestrator',
            capability='brain',
            correlation_id=correlation_id,
            session_id=context.session_id,
            user_id=context.user_id,
            status='started',
            payload={'action': action, 'input_len': len(str(request.get('input', '')))},
        )

        start_time = time.time()

        try:
            if action == 'reason':
                result = await self._reason(request, context)
            elif action == 'plan':
                result = await self._plan(request, context)
            elif action == 'decide':
                result = await self._decide(request, context)
            elif action == 'respond':
                result = await self._respond(request, context)
            else:
                result = ExecutionResult(
                    capability=self.name,
                    success=False,
                    error=f"Unknown brain action: {action}",
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
        finally:
            # Log thinking step
            self._thinking_log.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'action': action,
                'correlation_id': correlation_id,
                'success': not result.error if result else False,
            })
            if len(self._thinking_log) > 1000:
                self._thinking_log = self._thinking_log[-500:]

        result.latency_ms = (time.time() - start_time) * 1000.0
        result.correlation_id = correlation_id

        self._event_bus.emit(
            event_type='brain.reasoning.completed',
            source='brain',
            capability='brain',
            correlation_id=correlation_id,
            status='completed' if result.success else 'failed',
            payload={'action': action, 'success': result.success},
            metrics={'latency_ms': result.latency_ms},
        )

        AuditLog.log(
            event_type='brain.reasoning',
            source='brain',
            capability='brain',
            user_id=context.user_id,
            session_id=context.session_id,
            action=action,
            result='success' if result.success else 'error',
        )

        return result

    async def _reason(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Reason about input with full context."""
        input_text = request.get('input', '')
        conversation_id = request.get('conversation_id') or context.conversation_id

        # Gather context
        context_parts = []

        # 1. Current conversation
        if conversation_id:
            messages = ConversationRepository.get_messages(conversation_id, limit=50)
            if messages:
                context_parts.append(f"Conversation history ({len(messages)} messages):")
                for m in messages[-10:]:  # Last 10 messages
                    role = m.get('role', 'unknown')
                    content = m.get('content', '')[:200]
                    context_parts.append(f"  {role}: {content}")

        # 2. Working memory
        working_mem = MemoryRepository.get_working_memory(context.session_id, limit=10)
        if working_mem:
            context_parts.append(f"\nWorking memory ({len(working_mem)} entries):")
            for mem in working_mem[:5]:
                context_parts.append(f"  - {mem.get('content', '')[:200]}")

        # 3. Relevant episodic memories
        episodic = MemoryRepository.retrieve_memories(
            memory_type='episodic',
            session_id=context.session_id,
            user_id=context.user_id,
            limit=5,
        )
        if episodic:
            context_parts.append(f"\nEpisodic memories ({len(episodic)} entries):")
            for mem in episodic:
                context_parts.append(f"  - {mem.get('content', '')[:200]}")

        # 4. Allowed capabilities
        allowed_caps = request.get('allowed_capabilities', [])
        if allowed_caps:
            context_parts.append(f"\nAllowed capabilities: {', '.join(allowed_caps)}")

        # Build the full prompt
        full_context = f"""Context:
{chr(10).join(context_parts)}

Input: {input_text}

Task: Reason about the input considering the context. Determine:
1. What capabilities are needed (from the allowed set)
2. What is the optimal response
3. Are there any security concerns

Output your reasoning as JSON with:
- "capabilities_needed": list of capabilities to invoke
- "reasoning": your analysis
- "confidence": 0.0-1.0
- "security_flags": any security concerns
"""

        # Call LLM through provider gateway (credentials stay behind boundary)
        brain_response = await self._call_provider(full_context, context)

        if not brain_response['success']:
            return ExecutionResult(
                capability=self.name,
                success=False,
                error=brain_response.get('error', 'Unknown error'),
                error_type='PROVIDER_ERROR',
                correlation_id=correlation_id,
            )

        response_text = brain_response['data']['response']

        # Parse JSON from response
        try:
            # Extract JSON from potentially fenced response
            cleaned = response_text.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]

            reasoning = json.loads(cleaned.strip())
        except json.JSONDecodeError:
            # Fallback: use LLM response as-is
            reasoning = {
                'capabilities_needed': [],
                'reasoning': response_text,
                'confidence': 0.5,
                'security_flags': [],
            }

        # Emit capability selection event
        for cap in reasoning.get('capabilities_needed', []):
            self._event_bus.emit(
                event_type='brain.tool.request',
                source='brain',
                capability='brain',
                correlation_id=correlation_id,
                session_id=context.session_id,
                user_id=context.user_id,
                status='started',
                payload={'capability': cap, 'reasoning': reasoning.get('reasoning', '')[:200]},
            )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data=reasoning,
            correlation_id=correlation_id,
            metrics={
                'context_length': len(full_context),
                'capabilities_needed': len(reasoning.get('capabilities_needed', [])),
                'provider': brain_response['data'].get('provider', 'unknown'),
            },
        )

    async def _plan(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Create a plan for executing a task."""
        task = request.get('task', '')
        goal = request.get('goal', '')

        plan_prompt = f"""
Create a step-by-step plan for this task:
Task: {task}

Goal: {goal}

Output JSON with:
- "steps": list of {step_number, capability, action, description, reason}
- "estimated_time": total estimated time in seconds
- "parallel_steps": which steps can run in parallel
- "fallbacks": what to do if each step fails
- "dependencies": capability dependencies
"""
        response = await self._call_provider(plan_prompt, context)
        if not response['success']:
            return ExecutionResult(
                capability=self.name, success=False, error=response.get('error'),
                error_type='PROVIDER_ERROR', correlation_id=context.correlation_id,
            )

        try:
            cleaned = response['data']['response'].strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            plan = json.loads(cleaned.strip())
        except:
            plan = {'steps': [], 'raw': response['data']['response']}

        self.set_state(CapabilityStatus.READY)
        return ExecutionResult(
            capability=self.name, success=True, data=plan,
            correlation_id=context.correlation_id,
        )

    async def _decide(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Make a decision based on context."""
        input_text = request.get('input', '')
        options = request.get('options', [])

        decide_prompt = f"""
Input: {input_text}

Options:
{json.dumps(options, indent=2)}

Choose the best option and explain your reasoning.
Output JSON with: "chosen", "reasoning", "confidence"
"""
        response = await self._call_provider(decide_prompt, context)
        if not response['success']:
            return ExecutionResult(
                capability=self.name, success=False, error=response.get('error'),
                error_type='PROVIDER_ERROR', correlation_id=context.correlation_id,
            )

        try:
            cleaned = response['data']['response'].strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            decision = json.loads(cleaned.strip())
        except:
            decision = {'chosen': options[0] if options else None,
                       'reasoning': response['data']['response']}

        return ExecutionResult(
            capability=self.name, success=True, data=decision,
            correlation_id=context.correlation_id,
        )

    async def _respond(self, request: Dict, context: ExecutionContext) -> ExecutionResult:
        """Generate a response using the Brain with full context."""
        input_text = request.get('input', '')
        conversation_id = request.get('conversation_id')

        # Gather full context
        context_parts = []

        if conversation_id:
            messages = ConversationRepository.get_messages(conversation_id, limit=30)
            if messages:
                context_parts.append("Conversation context:")
                for m in messages[-10:]:
                    role = m.get('role', 'user')
                    content = m.get('content', '')[:300]
                    context_parts.append(f"  {role}: {content}")

        working_mem = MemoryRepository.get_working_memory(context.session_id, limit=5)
        if working_mem:
            context_parts.append("\nWorking memory:")
            for mem in working_mem[:3]:
                context_parts.append(f"  - {mem.get('content', '')[:200]}")

        allowed_caps = request.get('allowed_capabilities', ['chat'])
        context_parts.append(f"\nAvailable capabilities: {', '.join(allowed_caps)}")

        # Check for tool executions in the request
        tool_results = request.get('tool_results', [])
        if tool_results:
            context_parts.append("\nTool results:")
            for tr in tool_results:
                context_parts.append(f"  - {tr.get('result', '')[:200]}")

        full_prompt = f"""You are JARVIS, an intelligent AI assistant. Respond naturally.

Context:
{chr(10).join(context_parts)}

User: {input_text}

Response:"""

        response = await self._call_provider(full_prompt, context)
        if not response['success']:
            return ExecutionResult(
                capability=self.name, success=False, error=response.get('error'),
                error_type='PROVIDER_ERROR', correlation_id=context.correlation_id,
            )

        return ExecutionResult(
            capability=self.name,
            success=True,
            data={
                'response': response['data']['response'],
                'provider': response['data'].get('provider', 'unknown'),
                'model': response['data'].get('model', 'unknown'),
                'usage': response['data'].get('usage', {}),
            },
            correlation_id=context.correlation_id,
        )

    async def _call_provider(self, prompt: str, context: ExecutionContext) -> Dict[str, Any]:
        """Call a provider through the gateway (credentials stay behind boundary)."""
        try:
            from jarvis_backend.gateway import ProviderGateway
            gateway = ProviderGateway()

            # Get best available provider
            result = gateway.route_request(
                modality='text',
                user_id=context.user_id,
                message=prompt,
            )

            if result.get('success'):
                return {
                    'success': True,
                    'data': {
                        'response': result.get('response', result.get('choices', [{}])[0].get('message', {}).get('content', '')),
                        'provider': result.get('provider', 'unknown'),
                        'model': result.get('model', 'unknown'),
                        'usage': result.get('usage', {}),
                    },
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown provider error'),
                }
        except Exception as e:
            # Fallback to direct provider call
            api_key = os.environ.get('OPENAI_API_KEY')
            if api_key:
                try:
                    import openai
                    client = openai.OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model='gpt-3.5-turbo',
                        messages=[{'role': 'user', 'content': prompt}],
                        max_tokens=2000,
                    )
                    return {
                        'success': True,
                        'data': {
                            'response': response.choices[0].message.content.strip(),
                            'provider': 'openai',
                            'model': 'gpt-3.5-turbo',
                            'usage': {
                                'input_tokens': response.usage.input_tokens,
                                'output_tokens': response.usage.output_tokens,
                            },
                        },
                    }
                except Exception as fallback_e:
                    return {'success': False, 'error': str(fallback_e)}
            return {'success': False, 'error': str(e)}

    async def cancel(self, correlation_id: str) -> bool:
        return False

    async def shutdown(self) -> bool:
        self._thinking_log.clear()
        self.set_status(CapabilityStatus.OFFLINE)
        return True


__all__ = ['BrainCapability']
