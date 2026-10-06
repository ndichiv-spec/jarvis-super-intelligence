"""
Execution policy engine for sandboxed operations.

Provides fine-grained control over what capabilities automation tools
and AI agents can exercise.
"""

import re
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum


class Capability(Enum):
    """Capabilities that can be granted or denied."""
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"
    NETWORK_HTTP = "network:http"
    NETWORK_SOCKET = "network:socket"
    PROCESS_SPAWN = "process:spawn"
    PROCESS_KILL = "process:kill"
    SYSTEM_INFO = "system:info"
    ENV_READ = "env:read"
    DATABASE_READ = "database:read"
    DATABASE_WRITE = "database:write"
    API_CALL = "api:call"
    AI_INFERENCE = "ai:inference"
    EXECUTE_CODE = "execute:code"
    EXECUTE_SHELL = "execute:shell"


class RuleAction(Enum):
    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class PolicyRule:
    """A single policy rule."""
    action: RuleAction
    capability: Capability
    pattern: str = "*"
    reason: str = ""
    priority: int = 0

    def matches(self, capability: Capability, resource: str = "") -> bool:
        if self.capability != capability:
            return False
        if self.pattern == "*":
            return True
        if re.match(self.pattern, resource):
            return True
        return False


class PolicyEngine:
    """
    Policy engine that evaluates whether an action is allowed.

    Rules evaluated in priority order. First matching rule wins.
    If no rule matches, action is denied (default-deny).
    """

    def __init__(self, default_action: RuleAction = RuleAction.DENY):
        self.default_action = default_action
        self._rules: List[PolicyRule] = []

    def add_rule(self, rule: PolicyRule):
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def allow(self, capability: Capability, pattern: str = "*",
              reason: str = ""):
        self.add_rule(PolicyRule(RuleAction.ALLOW, capability, pattern, reason))

    def deny(self, capability: Capability, pattern: str = "*",
             reason: str = ""):
        self.add_rule(PolicyRule(RuleAction.DENY, capability, pattern, reason))

    def audit(self, capability: Capability, pattern: str = "*",
              reason: str = ""):
        self.add_rule(PolicyRule(RuleAction.AUDIT, capability, pattern, reason))

    def evaluate(self, capability: Capability, resource: str = "") -> PolicyRule:
        for rule in self._rules:
            if rule.matches(capability, resource):
                return rule
        return PolicyRule(
            action=self.default_action,
            capability=capability,
            reason="Default action (no matching rule)",
        )

    def is_allowed(self, capability: Capability, resource: str = "") -> bool:
        rule = self.evaluate(capability, resource)
        return rule.action == RuleAction.ALLOW

    def batch_check(self, checks: List[tuple]) -> Dict[str, bool]:
        """Check multiple capabilities at once."""
        return {
            f"{cap.value}/{res}": self.is_allowed(cap, res)
            for cap, res in checks
        }

    def to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "action": r.action.value,
                "capability": r.capability.value,
                "pattern": r.pattern,
                "reason": r.reason,
                "priority": r.priority,
            }
            for r in self._rules
        ]

    @classmethod
    def default_policy(cls) -> "PolicyEngine":
        """Create a sensible default policy."""
        engine = cls(default_action=RuleAction.DENY)

        # File operations
        engine.allow(Capability.FILE_READ, "/tmp/*")
        engine.allow(Capability.FILE_READ, "/app/data/*")
        engine.allow(Capability.FILE_WRITE, "/tmp/*")
        engine.audit(Capability.FILE_DELETE)

        # Network
        engine.allow(Capability.NETWORK_HTTP, "https://api.openai.com/*")
        engine.allow(Capability.NETWORK_HTTP, "https://generativelanguage.googleapis.com/*")
        engine.allow(Capability.NETWORK_HTTP, "http://host.docker.internal:11434/*")
        engine.audit(Capability.NETWORK_HTTP)

        # AI
        engine.allow(Capability.AI_INFERENCE)
        engine.allow(Capability.API_CALL, "/api/v1/*")

        # Execution
        engine.allow(Capability.EXECUTE_CODE)
        engine.audit(Capability.EXECUTE_SHELL)

        # System
        engine.allow(Capability.SYSTEM_INFO)
        engine.allow(Capability.ENV_READ, "JARVIS_*")
        engine.deny(Capability.ENV_READ, "AWS_*")
        engine.deny(Capability.ENV_READ, "SECRET_*")
        engine.deny(Capability.ENV_READ, "TOKEN_*")
        engine.deny(Capability.ENV_READ, "*KEY*")
        engine.deny(Capability.ENV_READ, "*PASSWORD*")

        # Process
        engine.deny(Capability.PROCESS_SPAWN)
        engine.deny(Capability.PROCESS_KILL)

        # Database
        engine.allow(Capability.DATABASE_READ)
        engine.audit(Capability.DATABASE_WRITE)

        return engine
