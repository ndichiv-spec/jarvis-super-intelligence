"""JARVIS Research / Verification Fabric.

A thin orchestration layer that ties the existing JARVIS subsystems (Browser,
Sandbox, Knowledge/RAG, Memory, Model Gateway, Learning Arena, Teacher Node)
into a single coherent research → experiment → verify → learn pipeline.

It does NOT rebuild any of those subsystems.  It consumes them through a
:py:class:`~research_engine.tool_registry.ToolRegistry` that enforces an
authorization + credential-resolution boundary (Sections 2, 20) so the Brain
model never sees provider secrets.

Modules:
    - :mod:`research_engine.models`            domain models (Evidence, Experiment, budgets)
    - :mod:`research_engine.verification`      verification engine (Section 12)
    - :mod:`research_engine.tool_registry`     tools + authorization (Sections 2, 6, 20)
    - :mod:`research_engine.research_engine`   Section 4 research pipeline
    - :mod:`research_engine.agent`             tool-aware Brain agent (Section 2)
"""
from __future__ import annotations

from .models import (
    Evidence,
    EvidenceStatus,
    Experiment,
    ResearchBudgets,
    ResearchMode,
    ResearchReport,
    ResearchSession,
    ResearchStatus,
    SearchResponse,
    SearchResult,
    SourceType,
    ToolCall,
    ToolResult,
)
from .tool_registry import (
    BrowserSearchTool,
    DefaultPermissionPolicy,
    KnowledgeRetrieveTool,
    MemoryRecallTool,
    MemoryTool,
    ModelConsultTool,
    Permission,
    PermissionPolicy,
    RiskLevel,
    SandboxRunTool,
    StaticSearchTool,
    Tool,
    ToolContext,
    ToolRegistry,
    scrub_secrets,
)
from .verification import VerificationEngine
from .research_engine import ResearchEngine
from .agent import BrainAgent
from .project_tools import (
    ProjectInspectTool,
    ProjectSearchTool,
    ProjectTestStatusTool,
)

__all__ = [
    "Evidence",
    "EvidenceStatus",
    "Experiment",
    "ResearchBudgets",
    "ResearchMode",
    "ResearchReport",
    "ResearchSession",
    "ResearchStatus",
    "SearchResponse",
    "SearchResult",
    "SourceType",
    "ToolCall",
    "ToolResult",
    "ToolRegistry",
    "Tool",
    "ToolContext",
    "RiskLevel",
    "Permission",
    "PermissionPolicy",
    "DefaultPermissionPolicy",
    "SandboxRunTool",
    "BrowserSearchTool",
    "KnowledgeRetrieveTool",
    "MemoryTool",
    "MemoryRecallTool",
    "ModelConsultTool",
    "StaticSearchTool",
    "scrub_secrets",
    "VerificationEngine",
    "ResearchEngine",
    "BrainAgent",
    "ProjectInspectTool",
    "ProjectSearchTool",
    "ProjectTestStatusTool",
]
