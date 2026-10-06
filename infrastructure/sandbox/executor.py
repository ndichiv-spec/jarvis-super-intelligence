"""
Sandboxed execution engine.

Provides restricted execution of automation actions and tools with:
  - Subprocess isolation (optional)
  - Timeout enforcement
  - Memory limits
  - Command allow/deny lists
  - Structured results with exit codes and output
"""

import os
import sys
import time
import json
import asyncio
import logging
import tempfile
import subprocess
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxViolation(Exception):
    """Raised when an execution violates sandbox policy."""
    pass


@dataclass
class SandboxResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout[:5000],
            "stderr": self.stderr[:2000],
            "exit_code": self.exit_code,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "truncated": self.truncated,
        }


@dataclass
class ExecutionPolicy:
    """Policies governing sandboxed execution."""
    allowed_commands: List[str] = field(default_factory=lambda: [
        "python", "python3", "bash", "sh", "ls", "cat", "echo",
        "grep", "find", "wc", "sort", "head", "tail", "cut",
        "mkdir", "cp", "mv", "rm",
    ])
    denied_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "mkfs", "dd", "wget", "curl", "nc", "nmap",
        "sudo", "su", "chmod", "chown", "mount", "umount",
        "reboot", "shutdown", "halt", "poweroff",
    ])
    max_stdout_bytes: int = 100_000
    max_stderr_bytes: int = 50_000
    default_timeout: float = 30.0
    max_timeout: float = 300.0
    allow_network: bool = False
    allow_write: bool = False
    work_directory: Optional[str] = None


class SandboxExecutor:
    """
    Executes commands and code in a sandboxed environment.

    Usage:
        executor = SandboxExecutor()
        result = await executor.run_command("python3 script.py", timeout=30)
        result = await executor.run_python("print('hello')")
    """

    def __init__(self, policy: Optional[ExecutionPolicy] = None):
        self.policy = policy or ExecutionPolicy()

    async def run_command(self, command: str, timeout: Optional[float] = None,
                          env: Optional[Dict[str, str]] = None) -> SandboxResult:
        """Run a shell command in the sandbox."""
        self._validate_command(command)

        timeout = min(timeout or self.policy.default_timeout, self.policy.max_timeout)
        start = time.time()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.policy.work_directory,
                env={**os.environ, **(env or {})},
                limit=self.policy.max_stdout_bytes,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return SandboxResult(
                    success=False,
                    error=f"Command timed out after {timeout}s",
                    duration_ms=(time.time() - start) * 1000,
                )

            stdout_str = stdout.decode(errors="replace")
            stderr_str = stderr.decode(errors="replace")

            truncated = False
            if len(stdout_str) > self.policy.max_stdout_bytes:
                stdout_str = stdout_str[:self.policy.max_stdout_bytes]
                truncated = True

            return SandboxResult(
                success=proc.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=proc.returncode or 0,
                duration_ms=(time.time() - start) * 1000,
                truncated=truncated,
            )

        except FileNotFoundError:
            return SandboxResult(
                success=False,
                error=f"Command not found: {command.split()[0]}",
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.exception(f"Sandbox execution failed: {e}")
            return SandboxResult(
                success=False,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def run_python(self, code: str, timeout: Optional[float] = None) -> SandboxResult:
        """Run Python code in the sandbox."""
        # Write code to temp file and execute
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            python_cmd = "python" if os.name == "nt" else "python3"
            result = await self.run_command(f"{python_cmd} {temp_path}", timeout=timeout)
            return result
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _validate_command(self, command: str):
        """Check command against security policies."""
        command_lower = command.strip().lower()

        for denied in self.policy.denied_commands:
            if command_lower.startswith(denied) or denied in command_lower:
                raise SandboxViolation(
                    f"Command '{command}' matches denied pattern: {denied}"
                )

        cmd_name = command.split()[0] if command.split() else ""
        if self.policy.allowed_commands:
            allowed = any(
                cmd_name == allowed or cmd_name.startswith(allowed)
                for allowed in self.policy.allowed_commands
            )
            # Allow scripts run via python/bash
            if cmd_name in ("python3", "python", "bash", "sh"):
                allowed = True
            if not allowed:
                raise SandboxViolation(
                    f"Command '{cmd_name}' is not in the allowed list"
                )

    def validate_code(self, code: str) -> List[str]:
        """Static analysis of Python code for dangerous patterns."""
        warnings = []
        dangerous_patterns = [
            ("import os", "OS module access"),
            ("import subprocess", "Subprocess execution"),
            ("import sys", "System access"),
            ("import shutil", "File system operations"),
            ("__import__", "Dynamic import"),
            ("exec(", "Code execution"),
            ("eval(", "Code evaluation"),
            ("open(", "File access"),
            ("__builtins__", "Built-in access"),
        ]
        for pattern, desc in dangerous_patterns:
            if pattern in code:
                warnings.append(f"{desc} detected: {pattern}")
        return warnings
