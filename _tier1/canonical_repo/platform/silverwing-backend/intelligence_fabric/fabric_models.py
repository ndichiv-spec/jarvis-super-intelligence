"""Pydantic models for the Silverwing Intelligence Fabric layer.

This module defines the data structures that flow through the Intelligence
Fabric runtime.  The Fabric sits *above* the Model Gateway and is responsible
for deciding *what needs to happen*, *which agent should do it*, *which tools
are required*, and *which model capability is required*.  The ModelRouter
(inside the Gateway) remains responsible for *which specific model*.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    """Lifecycle states for a unit of work within the Fabric."""
    PENDING = "pending"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class AgentCapability(str, Enum):
    """High-level capabilities an agent can declare."""
    RESEARCH = "research"
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    CODING = "coding"
    LIBRARIAN = "librarian"
    VERIFICATION = "verification"
    PLANNING = "planning"
    ORCHESTRATION = "orchestration"
    SYNTHESIS = "synthesis"
    MEMORY_MANAGEMENT = "memory_management"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    TOOL_USE = "tool_use"


class RiskLevel(str, Enum):
    """Risk classification for a task execution."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskPriority(str, Enum):
    """Priority bands for task scheduling."""
    LOWEST = "lowest"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Core request / context / result models
# ---------------------------------------------------------------------------

class IntelligenceRequest(BaseModel):
    """Top-level request entering the Intelligence Fabric.

    This is the Fabric-level analogue of ``ModelRequest`` in the Gateway.
    It carries the user objective plus all the metadata the Fabric needs to
    decompose, schedule, and execute the work.
    """

    query: str
    mission_id: Optional[str] = None
    context: Optional[str] = None
    privacy: str = "public"
    cost: str = "best_quality"
    latency: str = "normal"
    priority: TaskPriority = TaskPriority.NORMAL
    max_budget_usd: Optional[float] = None
    timeout_seconds: Optional[int] = None
    framework: Optional[str] = None  # e.g. "native", "langgraph", "crewai"
    constraints: Dict[str, Any] = Field(default_factory=dict)
    memory_access: List[str] = Field(default_factory=list)
    required_capabilities: List[str] = Field(default_factory=list)


class MissionContext(BaseModel):
    """Runtime context that travels with a mission through the Fabric.

    Created by the ``MissionPlanner`` and consumed by the ``Orchestrator``.
    """

    mission_id: str
    objective: str
    sub_mission_ids: List[str] = Field(default_factory=list)
    task_ids: List[str] = Field(default_factory=list)
    agents: List[str] = Field(default_factory=list)
    memory_access: List[str] = Field(default_factory=list)
    required_model_capability: str = ""
    privacy: str = "public"
    cost: str = "best_quality"
    budget_remaining_usd: float = 0.0
    started_at: float = Field(default_factory=time.time)
    deadline: Optional[float] = None
    constraints: Dict[str, Any] = Field(default_factory=dict)


class TaskSpec(BaseModel):
    """A single unit of work created by the ``TaskPlanner``."""

    task_id: str
    mission_id: str
    parent_task_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_role: Optional[str] = None
    description: str
    capability: str
    priority: TaskPriority = TaskPriority.NORMAL
    risk: RiskLevel = RiskLevel.LOW
    status: TaskStatus = TaskStatus.PENDING
    required_tools: List[str] = Field(default_factory=list)
    required_model_classes: List[str] = Field(default_factory=list)
    privacy: str = "public"
    cost: str = "best_quality"
    latency: str = "normal"
    timeout_seconds: Optional[int] = None
    budget_usd: Optional[float] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 1
    retry_count: int = 0
    created_at: float = Field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AgentSpec(BaseModel):
    """Declarative specification of an agent within the Fabric.

    Mirrors the ``AgentDefinition`` concept but is owned by the Fabric
    rather than hardcoded in a single module.  Agents declare their
    capabilities, allowed tools, preferred model classes, and
    verification policy.
    """

    agent_id: str
    role: str
    capabilities: List[str] = Field(default_factory=list)
    allowed_tools: List[str] = Field(default_factory=list)
    preferred_model_classes: List[str] = Field(default_factory=list)
    memory_access: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    verification_policy: str = "strict"
    system_prompt: str = ""
    model_preference: Optional[str] = None  # e.g. "deep-thinking"


class FabricResult(BaseModel):
    """The final result returned by the Intelligence Fabric."""

    mission_id: str
    success: bool
    query: str
    findings: List[Dict[str, Any]] = Field(default_factory=list)
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    routing_decisions: List[Dict[str, Any]] = Field(default_factory=list)
    tool_executions: List[Dict[str, Any]] = Field(default_factory=list)
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    total_cost_usd: float = 0.0
    error: Optional[str] = None


class FrameworkInfo(BaseModel):
    """Metadata about an orchestration framework adapter."""

    name: str
    available: bool
    version: Optional[str] = None
    license: Optional[str] = None
    description: str = ""
    use_cases: List[str] = Field(default_factory=list)
