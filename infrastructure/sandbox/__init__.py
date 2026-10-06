"""
Sandboxed execution environment for automation and tool execution.

Provides:
  - Restricted subprocess execution with resource limits
  - Execution policies controlling what can run
  - Timeout and memory bounds
  - Allow/deny lists for commands and capabilities
  - Output capture and redaction
"""

from .executor import SandboxExecutor, SandboxResult, ExecutionPolicy, SandboxViolation
from .policy import PolicyEngine, PolicyRule, RuleAction, Capability

__all__ = [
    "SandboxExecutor", "SandboxResult", "ExecutionPolicy", "SandboxViolation",
    "PolicyEngine", "PolicyRule", "RuleAction", "Capability",
]
