"""
Immediate Effect Engine - Connect sandbox results to system changes.

When JARVIS solves a problem in the Sandbox, the result must have a route
to the actual platform through the ChangeSet pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List, Callable
from enum import Enum
import time
import logging
import hashlib
import json

from .changes import (
    ChangeSet, ChangeType, ChangeStatus, RiskLevel, 
    ChangeOperation, change_manager
)
from .executor import ChangeExecutor, executor

logger = logging.getLogger("control_plane.immediate_effects")


class EffectType(str, Enum):
    """Types of immediate effects"""
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    SKILL = "skill"
    PROCEDURE = "procedure"
    CODE_PATCH = "code_patch"
    CONFIG_CHANGE = "config_change"
    TOOL_REGISTRATION = "tool_registration"
    WORKFLOW_UPDATE = "workflow_update"
    DATASET_UPDATE = "dataset_update"


@dataclass
class EffectProposal:
    """Proposal for an immediate effect"""
    effect_type: EffectType
    reason: str
    content: Dict[str, Any]
    confidence: float = 1.0
    risk: RiskLevel = RiskLevel.LOW
    requires_verification: bool = True
    source: str = "agent"
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_type": self.effect_type.value,
            "reason": self.reason,
            "content": self.content,
            "confidence": self.confidence,
            "risk": self.risk.value,
            "requires_verification": self.requires_verification,
            "source": self.source,
            "created_at": self.created_at,
        }


@dataclass
class EffectRequest:
    """Request to create an effect from sandbox result"""
    problem_description: str
    sandbox_result: str
    evidence: List[str] = field(default_factory=list)
    verification_status: Literal["unverified", "verified", "contradicted"] = "unverified"
    metadata: Dict[str, Any] = field(default_factory=dict)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    effect_proposal: Optional[EffectProposal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_description": self.problem_description,
            "sandbox_result": self.sandbox_result,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
            "metadata": self.metadata,
            "priority": self.priority,
            "effect_proposal": self.effect_proposal.to_dict() if self.effect_proposal else None,
        }


class ImmediateEffectEngine:
    """
    Engine that transforms sandbox results into verified system changes.
    
    Pipeline:
    Problem → Sandbox → Result → Effect Proposal → ChangeSet → Apply → Verify → Commit
    """
    
    _instance: Optional["ImmediateEffectEngine"] = None
    _lock = None
    
    def __init__(self):
        self._effect_handlers: Dict[EffectType, Callable[[EffectRequest], Optional[EffectProposal]]] = {}
        self._setup_default_handlers()
        self._pending_effects: List[EffectRequest] = []
    
    @classmethod
    def get_instance(cls) -> "ImmediateEffectEngine":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _setup_default_handlers(self) -> None:
        """Set up default effect handlers"""
        # Note: Actual handlers would be registered by the application
        # This is a placeholder for future extension
        pass
    
    def process_sandbox_result(
        self,
        problem: str,
        result: str,
        evidence: List[str] = None,
        verification_status: str = "unverified",
        **metadata
    ) -> Optional[ChangeSet]:
        """
        Process a sandbox result and create an effect if appropriate.
        
        Args:
            problem: The original problem statement
            result: The sandbox result/solution
            evidence: List of evidence sources
            verification_status: Current verification status
            **metadata: Additional context
        
        Returns:
            ChangeSet if an effect was created, None otherwise
        """
        evidence = evidence or []
        request = EffectRequest(
            problem_description=problem,
            sandbox_result=result,
            evidence=evidence,
            verification_status=verification_status,
            metadata=metadata,
        )
        
        # Analyze result to determine effect type
        effect_proposal = self._analyze_result(request)
        if not effect_proposal:
            return None
        
        request.effect_proposal = effect_proposal
        
        # Create ChangeSet from effect proposal
        change = self._create_changeset(request)
        if not change:
            return None
        
        logger.info(f"Created ChangeSet {change.change_id} from sandbox result")
        return change
    
    def _analyze_result(self, request: EffectRequest) -> Optional[EffectProposal]:
        """Analyze sandbox result to determine effect type and content"""
        
        # Check if result indicates knowledge
        if self._is_knowledge_result(request):
            return self._build_knowledge_proposal(request)
        
        # Check if result is a code patch
        if self._is_code_patch_result(request):
            return self._build_code_patch_proposal(request)
        
        # Check if result is a configuration change
        if self._is_config_change_result(request):
            return self._build_config_proposal(request)
        
        # Check if result is a procedure/skill
        if self._is_procedure_result(request):
            return self._build_procedure_proposal(request)
        
        return None
    
    def _is_knowledge_result(self, request: EffectRequest) -> bool:
        """Check if result is a verified finding"""
        result_lower = request.sandbox_result.lower()
        knowledge_indicators = [
            "research reveals",
            "verified that",
            "finding",
            "discovery",
            "study shows",
            "documented",
            "confirmed that",
            "evidence shows",
        ]
        return any(indicator in result_lower for indicator in knowledge_indicators)
    
    def _is_code_patch_result(self, request: EffectRequest) -> bool:
        """Check if result contains a code fix"""
        result_lower = request.sandbox_result.lower()
        patch_indicators = [
            "fixed",
            "patch",
            "solution:",
            "code:",
            "replace:",
            "add:",
            "remove:",
        ]
        return any(indicator in result_lower for indicator in patch_indicators)
    
    def _is_config_change_result(self, request: EffectRequest) -> bool:
        """Check if result is a configuration change"""
        result_lower = request.sandbox_result.lower()
        config_indicators = [
            "configuration update",
            "config change",
            "update setting",
            "set parameter",
            "environment variable",
        ]
        return any(indicator in result_lower for indicator in config_indicators)
    
    def _is_procedure_result(self, request: EffectRequest) -> bool:
        """Check if result is a reusable procedure"""
        result_lower = request.sandbox_result.lower()
        proc_indicators = [
            "procedure:",
            "steps:",
            "algorithm:",
            "skill:",
            "workflow:",
        ]
        return any(indicator in result_lower for indicator in proc_indicators)
    
    def _build_knowledge_proposal(self, request: EffectRequest) -> EffectProposal:
        """Build a knowledge update proposal from sandbox result"""
        # Extract knowledge content from result
        result = request.sandbox_result
        
        # Try to parse knowledge structure
        knowledge_content = {
            "problem": request.problem_description,
            "solution": result,
            "sources": request.evidence,
            "verified": request.verification_status == "verified",
        }
        
        return EffectProposal(
            effect_type=EffectType.KNOWLEDGE,
            reason=f"Knowledge discovery from sandbox: {request.problem_description[:100]}",
            content=knowledge_content,
            confidence=0.9 if request.verification_status == "verified" else 0.6,
            risk=RiskLevel.LOW,
        )
    
    def _build_code_patch_proposal(self, request: EffectRequest) -> EffectProposal:
        """Build a code patch proposal from sandbox result"""
        return EffectProposal(
            effect_type=EffectType.CODE_PATCH,
            reason=f"Bug fix from sandbox: {request.problem_description[:100]}",
            content={
                "problem": request.problem_description,
                "patch": request.sandbox_result,
                "evidence": request.evidence,
            },
            confidence=0.8 if request.verification_status == "verified" else 0.5,
            risk=RiskLevel.MEDIUM,
            requires_verification=True,
        )
    
    def _build_config_proposal(self, request: EffectRequest) -> EffectProposal:
        """Build a config change proposal from sandbox result"""
        return EffectProposal(
            effect_type=EffectType.CONFIG_CHANGE,
            reason=f"Config improvement from sandbox: {request.problem_description[:100]}",
            content={
                "problem": request.problem_description,
                "config_change": request.sandbox_result,
            },
            confidence=0.7 if request.verification_status == "verified" else 0.4,
            risk=RiskLevel.MEDIUM,
            requires_verification=True,
        )
    
    def _build_procedure_proposal(self, request: EffectRequest) -> EffectProposal:
        """Build a procedure/skill proposal from sandbox result"""
        return EffectProposal(
            effect_type=EffectType.PROCEDURE,
            reason=f"Procedure discovered: {request.problem_description[:100]}",
            content={
                "problem": request.problem_description,
                "procedure": request.sandbox_result,
                "steps": parse_procedure_steps(request.sandbox_result),
            },
            confidence=0.8,
            risk=RiskLevel.LOW,
        )
    
    def _create_changeset(self, request: EffectRequest) -> Optional[ChangeSet]:
        """Create a ChangeSet from an effect proposal"""
        if not request.effect_proposal:
            return None
        
        proposal = request.effect_proposal
        
        # Create appropriate ChangeSet based on effect type
        if proposal.effect_type == EffectType.KNOWLEDGE:
            return self._create_knowledge_changeset(request, proposal)
        elif proposal.effect_type == EffectType.CODE_PATCH:
            return self._create_code_patch_changeset(request, proposal)
        elif proposal.effect_type == EffectType.CONFIG_CHANGE:
            return self._create_config_changeset(request, proposal)
        elif proposal.effect_type == EffectType.PROCEDURE:
            return self._create_procedure_changeset(request, proposal)
        
        return None
    
    def _create_knowledge_changeset(
        self, request: EffectRequest, proposal: EffectProposal
    ) -> ChangeSet:
        """Create a knowledge update ChangeSet"""
        change = ChangeSet(
            type=ChangeType.KNOWLEDGE_UPDATE,
            title=f"Knowledge: {request.problem_description[:50]}",
            description=proposal.reason,
            reason=proposal.reason,
            target=f"/knowledge/{hashlib.md5(request.problem_description.encode()).hexdigest()[:8]}",
            risk=RiskLevel.LOW,
            policy="auto" if proposal.confidence > 0.8 else "approval",
            created_by=proposal.source,
        )
        
        change.operations.append(ChangeOperation(
            op="add",
            path=change.target,
            value=proposal.content,
            description="Add verified knowledge from sandbox"
        ))
        
        change.tests.append({
            "type": "health_check",
            "target": "knowledge",
        })
        
        change_manager._changes[change.change_id] = change
        return change
    
    def _create_code_patch_changeset(
        self, request: EffectRequest, proposal: EffectProposal
    ) -> ChangeSet:
        """Create a code patch ChangeSet"""
        change = ChangeSet(
            type=ChangeType.CODE_PATCH,
            title=f"Code Fix: {request.problem_description[:50]}",
            description=proposal.reason,
            reason=proposal.reason,
            target=request.metadata.get("target_file", "unknown"),
            risk=RiskLevel.MEDIUM,
            policy="approval" if proposal.risk == RiskLevel.MEDIUM else "auto",
            created_by=proposal.source,
        )
        
        change.operations.append(ChangeOperation(
            op="patch",
            path=change.target,
            value=proposal.content.get("patch", request.sandbox_result),
            description="Apply verified patch from sandbox"
        ))
        
        return change
    
    def _create_config_changeset(
        self, request: EffectRequest, proposal: EffectProposal
    ) -> ChangeSet:
        """Create a config change ChangeSet"""
        change = ChangeSet(
            type=ChangeType.CONFIG_CHANGE,
            title=f"Config: {request.problem_description[:50]}",
            description=proposal.reason,
            reason=proposal.reason,
            target="config",
            risk=RiskLevel.MEDIUM,
            policy="approval",
            created_by=proposal.source,
        )
        
        return change
    
    def _create_procedure_changeset(
        self, request: EffectRequest, proposal: EffectProposal
    ) -> ChangeSet:
        """Create a procedure/skill ChangeSet"""
        change = ChangeSet(
            type=ChangeType.PROCEDURE_UPDATE,
            title=f"Skill: {request.problem_description[:50]}",
            description=proposal.reason,
            reason=proposal.reason,
            target=f"/skills/{hashlib.md5(request.problem_description.encode()).hexdigest()[:8]}",
            risk=RiskLevel.LOW,
            policy="auto",
            created_by=proposal.source,
        )
        
        return change
    
    def execute_effect(
        self, change: ChangeSet, executor_instance=None
    ) -> Any:
        """Execute an effect (ChangeSet) through the executor"""
        exec = executor_instance or executor
        return exec.execute(change)


def parse_procedure_steps(text: str) -> List[str]:
    """Parse procedure steps from text"""
    steps = []
    for line in text.split("\n"):
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith(("- ", "1.", "2."))):
            steps.append(line)
        elif line and "step" in line.lower():
            steps.append(line)
    return steps if steps else [text[:200]]


# Global engine instance
effect_engine = ImmediateEffectEngine.get_instance()


def create_knowledge_effect(
    problem: str,
    solution: str,
    sources: List[str] = None,
    verified: bool = True,
) -> Optional[ChangeSet]:
    """
    Convenience function to create a knowledge effect from a verified solution.
    
    This is the primary entry point for making sandbox results immediately
    affect the platform through the verified change pipeline.
    """
    proposal = EffectProposal(
        effect_type=EffectType.KNOWLEDGE,
        reason=f"Verified finding: {problem}",
        content={
            "problem": problem,
            "solution": solution,
            "sources": sources or [],
            "verified": verified,
        },
        confidence=0.95 if verified else 0.7,
        risk=RiskLevel.LOW,
    )
    
    request = EffectRequest(
        problem_description=problem,
        sandbox_result=solution,
        evidence=sources or [],
        verification_status="verified" if verified else "unverified",
        effect_proposal=proposal,
    )
    
    return effect_engine._create_changeset(request)


def process_sandbox_result(
    problem: str,
    result: str,
    evidence: List[str] = None,
    verified: bool = True,
) -> Optional[ChangeSet]:
    """
    Process a sandbox result and create a ChangeSet if appropriate.
    
    This is the main entry point for the immediate effect pipeline.
    """
    return effect_engine.process_sandbox_result(
        problem=problem,
        result=result,
        evidence=evidence or [],
        verification_status="verified" if verified else "unverified",
    )