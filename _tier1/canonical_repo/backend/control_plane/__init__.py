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
]