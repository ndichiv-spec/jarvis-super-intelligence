"""Silverwing Intelligence Fabric — unified runtime layer above the Model Gateway.

The Fabric sits above the Model Gateway and is responsible for deciding:
  * what needs to happen (MissionPlanner)
  * which agent should do it (AgentScheduler)
  * which tools are required (ToolSelector)
  * what model capability is required (delegates to ModelRouter)
  * what needs verification (VerificationCoordinator)

The ModelRouter remains responsible for model selection.
"""

from fabric_models import (
    IntelligenceRequest,
    MissionContext,
    TaskSpec,
    AgentSpec,
    FabricResult,
    FrameworkInfo,
    TaskStatus,
    TaskPriority,
    RiskLevel,
    AgentCapability,
    VerificationStatus,
)

from mission_planner import MissionPlanner
from task_planner import TaskPlanner
from agent_scheduler import AgentScheduler
from tool_selector import ToolSelector
from verification_coordinator import VerificationCoordinator, VerificationStatus
from fabric import IntelligenceFabric
from adapters import (
    get_adapter,
    get_adapter_info_all,
    get_all_adapters,
    BaseOrchestrationAdapter,
    NativeExecutionAdapter,
)

__all__ = [
    # Fabric
    "IntelligenceFabric",
    # Core components
    "MissionPlanner",
    "TaskPlanner",
    "AgentScheduler",
    "ToolSelector",
    "VerificationCoordinator",
    # Models
    "IntelligenceRequest",
    "MissionContext",
    "TaskSpec",
    "AgentSpec",
    "FabricResult",
    "FrameworkInfo",
    # Enums
    "TaskStatus",
    "TaskPriority",
    "RiskLevel",
    "AgentCapability",
    "VerificationStatus",
    # Adapters
    "get_adapter",
    "get_adapter_info_all",
    "get_all_adapters",
    "BaseOrchestrationAdapter",
    "NativeExecutionAdapter",
]
