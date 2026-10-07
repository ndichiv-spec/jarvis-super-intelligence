"""
JARVIS Control Plane - Unified AI Operating System

The Control Plane is the authoritative runtime layer that knows:
- desired state
- observed state
- capabilities
- services
- providers
- models
- users
- permissions
- active tasks
- pending changes
- applied changes
- failed changes
- rollback state
- deliberative reasoning (think-before-act)
- workflow orchestration (DAG-based multi-step)
- event sourcing (append-only event log)
- vector storage (embeddings / similarity)
- circuit breakers (graceful degradation)
- rate limiting (per-user / per-provider quotas)
"""

from .desired_state import (
    DesiredState, DesiredService, DesiredAuth, DesiredProvider,
    get_desired_state, set_desired_state
)
from .observed_state import (
    ObservedState, ObservedService, ObservedProc,
    get_observed_state, set_observed_state, refresh_from_endpoints
)
from .service_registry import (
    ServiceRegistry, ServiceEntry, ServiceType, ServiceState,
    service_registry, registry
)
from .capabilities import Capability, CapabilityState, CapabilityRegistry, capability_registry
from .drift import DriftDetector, Drift, DriftType, detect_drift, DriftReport
from .reconciler import Reconciler, ReconciliationResult
from .changes import (
    ChangeSet, ChangeType, ChangeStatus, ChangeOperation,
    ChangeSetManager, change_manager
)
from .executor import ChangeExecutor, ExecutorResult, executor
from .auth_runtime import (
    AuthRuntime, Session, User, Role, Permission,
    auth_runtime, check_permission, require_permission
)
from .task_runtime import Task, TaskState, TaskManager, task_manager
from .observer import (
    Observer, HealthStatus, ServiceHealth, observer,
    check_system_health, check_service_health
)
from .immediate_effects import (
    ImmediateEffectEngine, EffectType, effect_engine,
    create_knowledge_effect, process_sandbox_result
)
from .supervisor import Supervisor, RecoveryPolicy, supervisor

# --- Phase 9: Advanced Backend Systems ---
from .thinking import (
    ThinkBeforeActEngine, DeliberationPlan, DeliberationResult,
    ReasoningBlock, PlanStep, Constraint, FallbackStrategy,
    StepStatus, ConfidenceState, RiskLevel,
    think_engine, deliberate
)
from .workflow_engine import (
    WorkflowEngine, Workflow, WorkflowNode, WorkflowEdge,
    WorkflowRun, NodeConfig, NodeType, NodeStatus,
    WorkflowStatus, FailurePolicy,
    workflow_engine, define_workflow
)
from .event_store import (
    Event, EventType, EventStore, Projection,
    InMemoryEventStore, PostgresEventStore,
    ConcurrentModificationError,
    event_store, record_event
)
from .vector_store import (
    VectorStore, EmbeddingRecord, SearchResult,
    InMemoryVectorStore, RedisVectorStore, PgVectorStore,
    VectorStoreFactory, DistanceMetric, VectorStoreError,
    get_vector_store, reset_vector_store
)
from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerStats,
    CircuitState, CircuitBreakerError, CircuitBreakerOpen,
    CircuitBreakerTimeout, CircuitBreakerRegistry,
    circuit_breaker_registry, DEFAULT_CONFIG
)
from .rate_limiter import (
    RateLimiter, RateLimitConfig, RateLimitResult,
    RateLimitExceeded,
    rate_limiter, DEFAULT_USER_CONFIG, DEFAULT_PROVIDER_CONFIG,
    check_rate_limit, consume_rate_limit
)

__all__ = [
    # State models
    'DesiredState', 'DesiredService', 'DesiredAuth', 'DesiredProvider',
    'ObservedState', 'ObservedService', 'ObservedProc',

    # Convenience functions
    'get_desired_state', 'set_desired_state',
    'get_observed_state', 'set_observed_state', 'refresh_from_endpoints',

    # Registry
    'ServiceRegistry', 'ServiceEntry', 'ServiceType', 'ServiceState', 'service_registry',
    'Capability', 'CapabilityState', 'CapabilityRegistry', 'capability_registry',

    # Reconciliation
    'DriftDetector', 'Drift', 'DriftType', 'detect_drift', 'DriftReport',
    'Reconciler', 'ReconciliationResult',

    # Changes
    'ChangeSet', 'ChangeType', 'ChangeStatus', 'ChangeOperation',
    'ChangeSetManager', 'change_manager',
    'ChangeExecutor', 'ExecutorResult', 'executor',

    # Authentication
    'AuthRuntime', 'Session', 'User', 'Role', 'Permission',
    'auth_runtime', 'check_permission', 'require_permission',

    # Task runtime
    'Task', 'TaskState', 'TaskManager', 'task_manager',

    # Observer
    'Observer', 'HealthStatus', 'ServiceHealth', 'observer',
    'check_system_health', 'check_service_health',

    # Immediate effects
    'ImmediateEffectEngine', 'EffectType', 'effect_engine',
    'create_knowledge_effect', 'process_sandbox_result',

    # Supervisor
    'Supervisor', 'RecoveryPolicy', 'supervisor',

    # Think-Before-Act (deliberative reasoning)
    'ThinkBeforeActEngine', 'DeliberationPlan', 'DeliberationResult',
    'ReasoningBlock', 'PlanStep', 'Constraint', 'FallbackStrategy',
    'StepStatus', 'ConfidenceState', 'RiskLevel',
    'think_engine', 'deliberate',

    # Agentic Workflow Engine (DAG orchestration)
    'WorkflowEngine', 'Workflow', 'WorkflowNode', 'WorkflowEdge',
    'WorkflowRun', 'NodeConfig', 'NodeType', 'NodeStatus',
    'WorkflowStatus', 'FailurePolicy',
    'workflow_engine', 'define_workflow',

    # Event Sourcing
    'Event', 'EventType', 'EventStore', 'Projection',
    'InMemoryEventStore', 'PostgresEventStore',
    'ConcurrentModificationError',
    'event_store', 'record_event',

    # Vector Store
    'VectorStore', 'EmbeddingRecord', 'SearchResult',
    'InMemoryVectorStore', 'RedisVectorStore', 'PgVectorStore',
    'VectorStoreFactory', 'DistanceMetric', 'VectorStoreError',
    'get_vector_store', 'reset_vector_store',

    # Circuit Breaker
    'CircuitBreaker', 'CircuitBreakerConfig', 'CircuitBreakerStats',
    'CircuitState', 'CircuitBreakerError', 'CircuitBreakerOpen',
    'CircuitBreakerTimeout', 'CircuitBreakerRegistry',
    'circuit_breaker_registry', 'DEFAULT_CONFIG',

    # Rate Limiter
    'RateLimiter', 'RateLimitConfig', 'RateLimitResult',
    'RateLimitExceeded',
    'rate_limiter', 'DEFAULT_USER_CONFIG', 'DEFAULT_PROVIDER_CONFIG',
    'check_rate_limit', 'consume_rate_limit',
]