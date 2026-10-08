"""
Gateway Integration Layer - Bridges Phase 2 control plane with runtime gateway.

This module provides the integration between the durable PostgreSQL registries
(Model Registry, Provider Registry) and the actual request processing in the
JARVIS gateway, including usage accounting and audit events.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger("gateway_integration")


class GatewayIntegration:
    """
    Integration layer between control plane and gateway.
    
    Provides:
    - Model lookup through durable Model Registry
    - Provider status from durable Provider Registry  
    - Usage accounting for real inference requests
    - Audit events for operational visibility
    """
    
    _instance: Optional["GatewayIntegration"] = None
    
    def __init__(self):
        self._model_registry = None
        self._provider_registry = None
        self._usage_accountant = None
        self._audit_service = None
        self._routing_policy = None
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """Lazy-load all Phase 2 components."""
        if self._initialized:
            return
        
        try:
            from infrastructure.model_registry import get_model_registry
            self._model_registry = get_model_registry()
            logger.debug("Model registry initialized")
        except Exception as e:
            logger.warning(f"Failed to init model registry: {e}")
        
        try:
            from infrastructure.provider_registry import get_provider_registry
            self._provider_registry = get_provider_registry()
            logger.debug("Provider registry initialized")
        except Exception as e:
            logger.warning(f"Failed to init provider registry: {e}")
        
        try:
            from infrastructure.routing_policy import RoutingPolicyEngine
            self._routing_policy = RoutingPolicyEngine()
            logger.debug("Routing policy engine initialized")
        except Exception as e:
            logger.warning(f"Failed to init routing policy: {e}")
        
        try:
            from infrastructure.usage_accounting import UsageAccountant
            self._usage_accountant = UsageAccountant.get_instance()
            logger.debug("Usage accountant initialized")
        except Exception as e:
            logger.warning(f"Failed to init usage accountant: {e}")
        
        try:
            from infrastructure.audit_events import AuditEventService, AuditEvent, EventCategory, EventSeverity
            self._audit_service = AuditEventService.get_instance()
            self._AuditEvent = AuditEvent
            self._EventCategory = EventCategory
            self._EventSeverity = EventSeverity
            logger.debug("Audit service initialized")
        except Exception as e:
            logger.warning(f"Failed to init audit service: {e}")
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> "GatewayIntegration":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
    
    def resolve_model(self, model_ref: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a model reference through the durable Model Registry.
        
        Args:
            model_ref: Model reference (e.g., 'openai:gpt-4', 'google:gemini-pro')
            
        Returns:
            Model info dict or None if not found/approved
        """
        self._ensure_initialized()
        
        if not self._model_registry:
            return None
        
        try:
            # Get model from registry
            model = self._model_registry.get(model_ref)
            if not model:
                # Try by model_id only
                parts = model_ref.split(":")
                if len(parts) == 2:
                    provider, model_id = parts
                    models = self._model_registry.list_models(provider_id=provider)
                    for m in models:
                        if m.model_id == model_id:
                            model = m
                            break
            
            if model and self._is_model_usable(model):
                return {
                    "model_id": model.model_id,
                    "provider_id": model.provider_id,
                    "display_name": model.display_name,
                    "context_window": model.context_window,
                    "capabilities": model.capabilities or [],
                    "lifecycle_status": model.lifecycle_status,
                    "deployment_type": model.deployment_type,
                    "endpoint_reference": model.endpoint_reference,
                    "artifact_reference": model.artifact_reference,
                }
        except Exception as e:
            logger.warning(f"Model resolution failed: {e}")
        
        return None
    
    def _is_model_usable(self, model) -> bool:
        """Check if a model is usable (lifecycle allows it)."""
        status = getattr(model, 'lifecycle_status', 'discovered')
        return status in ('approved', 'deployed', 'candidate', 'registered')
    
    def get_provider_info(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """
        Get provider info from durable Provider Registry.
        
        Args:
            provider_id: Provider identifier (e.g., 'openai', 'google')
            
        Returns:
            Provider info dict or None
        """
        self._ensure_initialized()
        
        if not self._provider_registry:
            return None
        
        try:
            provider = self._provider_registry.get(provider_id)
            if provider:
                return {
                    "provider_id": provider.provider_id,
                    "provider_name": provider.provider_name,
                    "capabilities": provider.capabilities or [],
                    "enabled": provider.enabled,
                    "health_state": provider.health_state,
                    "last_health_check": provider.last_health_check,
                    "verification_state": provider.verification_state,
                }
        except Exception as e:
            logger.warning(f"Provider lookup failed: {e}")
        
        return None
    
    def make_routing_decision(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a routing decision using Phase 2 routing policy.
        
        Args:
            query: Routing query parameters
            
        Returns:
            Routing decision dict
        """
        self._ensure_initialized()
        
        if not self._routing_policy:
            return {"selected_provider": "local", "selected_model": "local-rule", "reason": "no routing engine"}
        
        try:
            from infrastructure.routing_policy import RoutingQuery
            rq = RoutingQuery(
                capability=query.get("capability", ""),
                cost_policy=query.get("cost_policy", "best_quality"),
                privacy=query.get("privacy", "public"),
                context_length=query.get("context_length", 0),
                modalities=query.get("modalities", ["text"]),
                min_parameters=query.get("min_parameters"),
                enabled_only=query.get("enabled_only", True),
                verified_only=query.get("verified_only", False),
            )
            
            decision = self._routing_policy.route(rq)
            
            return {
                "selected_provider": decision.selected_provider,
                "selected_model": decision.selected_model,
                "reason": decision.reasoning,
                "cost_estimate": decision.cost_estimate_usd,
                "is_verified": decision.is_verified,
                "provider_health": decision.provider_health,
                "model_lifecycle": decision.model_lifecycle,
                "fallback_chain": decision.fallback_chain,
                "matched_rules": decision.matched_rules,
            }
        except Exception as e:
            logger.warning(f"Routing decision failed: {e}")
            return {"selected_provider": "local", "selected_model": "local-rule", "reason": str(e)}
    
    def record_usage(self, usage_data: Dict[str, Any]) -> Optional[str]:
        """
        Record usage for an inference request.
        
        Args:
            usage_data: Usage information including:
                - provider: Provider ID
                - model: Model ID
                - input_tokens: Input token count
                - output_tokens: Output token count
                - user_id: Optional user ID
                - request_id: Optional request ID
                
        Returns:
            Record ID if recorded, None otherwise
        """
        self._ensure_initialized()
        
        if not self._usage_accountant:
            logger.debug("Usage accountant not available")
            return None
        
        try:
            record = self._usage_accountant.record_inference(
                provider_id=usage_data.get("provider", ""),
                model_id=usage_data.get("model", ""),
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                user_id=usage_data.get("user_id"),
                request_id=usage_data.get("request_id"),
                metadata=usage_data.get("metadata", {})
            )
            logger.info(f"Recorded usage: {record.record_id}")
            return record.record_id
        except Exception as e:
            logger.warning(f"Usage recording failed: {e}")
        
        return None
    
    def record_audit_inference(self, audit_data: Dict[str, Any]) -> Optional[str]:
        """
        Record an audit event for an inference operation.
        
        Args:
            audit_data: Audit information including:
                - provider: Provider ID
                - model: Model ID
                - request_id: Request ID
                - latency_ms: Request latency
                - success: Whether the request succeeded
                - user_id: User ID
                
        Returns:
            Event ID if recorded, None otherwise
        """
        self._ensure_initialized()
        
        if not self._audit_service:
            logger.debug("Audit service not available")
            return None
        
        try:
            now = time.time()
            event_id = str(uuid.uuid4())
            
            # Build the AuditEvent
            if self._AuditEvent:
                event = self._AuditEvent(
                    id=event_id,
                    event_id=event_id,
                    timestamp=now,
                    timestamp_iso=datetime.utcfromtimestamp(now).isoformat() + "Z",
                    category=self._EventCategory.ROUTING.value if self._EventCategory else "routing",
                    severity=self._EventSeverity.INFO.value if self._EventSeverity else "info",
                    event_type="inference",
                    user_id=audit_data.get("user_id", ""),
                    provider=audit_data.get("provider"),
                    model=audit_data.get("model"),
                    action="inference_request",
                    result="success" if audit_data.get("success", True) else "error",
                    message=f"Inference via {audit_data.get('provider')}/{audit_data.get('model')}",
                    request_id=audit_data.get("request_id"),
                    duration_ms=audit_data.get("latency_ms"),
                    tokens_used=audit_data.get("input_tokens", 0) + audit_data.get("output_tokens", 0),
                )
                return self._audit_service.log_event(event)
            else:
                logger.warning("AuditEvent class not available")
                return None
        except Exception as e:
            logger.warning(f"Audit recording failed: {e}")
        
        return None
    
    def verify_model_for_routing(self, model_ref: str) -> Dict[str, Any]:
        """
        Verify a model is available for routing decisions.
        
        Returns the model info if usable, or error info.
        """
        result = self.resolve_model(model_ref)
        if result:
            return {"valid": True, "model": result}
        return {"valid": False, "error": f"Model {model_ref} not found or not approved"}


def get_gateway_integration() -> GatewayIntegration:
    """Get the gateway integration singleton."""
    return GatewayIntegration.get_instance()