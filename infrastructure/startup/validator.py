"""
Startup validation system.

Runs pre-flight checks before the service starts serving traffic:
  - Database connectivity
  - Redis/cache availability
  - AI provider API reachability
  - Filesystem permissions
  - Required environment variables
  - Port availability
  - Disk space
"""

import os
import socket
import asyncio
import shutil
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CHECK_TIMEOUT = 30.0


class CheckSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DependencyStatus:
    name: str
    host: str
    port: Optional[int] = None
    reachable: bool = False
    error: str = ""


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    severity: CheckSeverity = CheckSeverity.CRITICAL
    duration_ms: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity.value,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


StartupCheckFunc = Callable[[], Awaitable[CheckResult]]


class StartupCheck:
    def __init__(
        self,
        name: str,
        check_fn: StartupCheckFunc,
        severity: CheckSeverity = CheckSeverity.CRITICAL,
        timeout: float = CHECK_TIMEOUT,
    ):
        self.name = name
        self.check_fn = check_fn
        self.severity = severity
        self.timeout = timeout


class StartupValidator:
    """
    Validates all dependencies before the application starts.

    Usage:
        validator = StartupValidator()

        @validator.check("database")
        async def check_db():
            ...

        results = await validator.run()
        validator.report(results)
    """

    def __init__(self, app_name: str = "jarvis"):
        self.app_name = app_name
        self.checks: Dict[str, StartupCheck] = {}
        self._results: Dict[str, CheckResult] = {}

    def check(
        self,
        name: str,
        severity: CheckSeverity = CheckSeverity.CRITICAL,
        timeout: float = CHECK_TIMEOUT,
    ):
        """Decorator to register a startup check."""
        def decorator(fn: StartupCheckFunc):
            self.checks[name] = StartupCheck(
                name=name,
                check_fn=fn,
                severity=severity,
                timeout=timeout,
            )
            return fn
        return decorator

    def register(self, check: StartupCheck):
        self.checks[check.name] = check

    async def run_check(self, name: str) -> CheckResult:
        check = self.checks.get(name)
        if not check:
            return CheckResult(
                name=name,
                passed=False,
                message="No check registered",
                severity=CheckSeverity.CRITICAL,
            )

        import time
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(check.check_fn(), timeout=check.timeout)
            result.duration_ms = (time.monotonic() - start) * 1000
            self._results[name] = result
            return result
        except asyncio.TimeoutError:
            result = CheckResult(
                name=name,
                passed=False,
                message=f"Timed out after {check.timeout}s",
                severity=check.severity,
                duration_ms=(time.monotonic() - start) * 1000,
            )
            self._results[name] = result
            return result
        except Exception as e:
            result = CheckResult(
                name=name,
                passed=False,
                message=str(e),
                severity=check.severity,
                duration_ms=(time.monotonic() - start) * 1000,
            )
            self._results[name] = result
            return result

    async def run(self, checks: Optional[List[str]] = None) -> List[CheckResult]:
        """Run specified checks (or all if none specified)."""
        names = checks or list(self.checks.keys())
        results = await asyncio.gather(*[self.run_check(n) for n in names])
        return list(results)

    def has_failures(self, results: Optional[List[CheckResult]] = None) -> bool:
        """Check if any critical checks failed."""
        results = results or list(self._results.values())
        return any(
            r is not None and not r.passed and r.severity == CheckSeverity.CRITICAL
            for r in results
        )

    def report(self, results: Optional[List[CheckResult]] = None) -> Dict[str, Any]:
        """Generate a startup validation report."""
        results = results or list(self._results.values())

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        critical_failures = sum(
            1 for r in results if not r.passed and r.severity == CheckSeverity.CRITICAL
        )

        return {
            "app": self.app_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "failed": failed,
            "total": total,
            "critical_failures": critical_failures,
            "all_passed": failed == 0,
            "can_start": critical_failures == 0,
            "checks": [r.to_dict() for r in results],
        }

    async def assert_can_start(self):
        """Run checks and raise if critical failures exist."""
        results = await self.run()
        report = self.report(results)
        if not report["can_start"]:
            failed = [r for r in results if not r.passed and r.severity == CheckSeverity.CRITICAL]
            msgs = "; ".join(f"{r.name}: {r.message}" for r in failed)
            raise RuntimeError(
                f"Startup validation failed: {report['critical_failures']} critical check(s) failed. {msgs}"
            )
        return report


# --- Common built-in checks ---

def check_tcp_connectivity(
    host: str, port: int, name: Optional[str] = None, timeout: float = 5.0
) -> StartupCheck:
    """Create a check that verifies TCP connectivity to a host:port."""
    check_name = name or f"tcp_{host}_{port}"

    async def _check() -> CheckResult:
        try:
            _, await asyncio.wait_for(
                asyncio.get_event_loop().sock_connect(
                    socket.create_connection((host, port), timeout=timeout),
                    (host, port),
                ),
                timeout=timeout,
            )
            # Simpler approach for cross-platform
            async def _connect():
                loop = asyncio.get_event_loop()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                try:
                    await loop.sock_connect(sock, (host, port))
                    return CheckResult(
                        name=check_name,
                        passed=True,
                        message=f"Connected to {host}:{port}",
                        details={"host": host, "port": port},
                    )
                finally:
                    sock.close()

            return await _connect()
        except Exception as e:
            return CheckResult(
                name=check_name,
                passed=False,
                message=f"Cannot connect to {host}:{port} - {e}",
                details={"host": host, "port": port},
            )

    return StartupCheck(name=check_name, check_fn=_check)


def check_env_var(var_name: str, severity: CheckSeverity = CheckSeverity.CRITICAL) -> StartupCheck:
    """Create a check that verifies a required environment variable is set."""
    async def _check() -> CheckResult:
        value = os.environ.get(var_name)
        if value:
            masked = value[:4] + "..." if len(value) > 8 else "***"
            return CheckResult(
                name=f"env_{var_name}",
                passed=True,
                message=f"{var_name}={masked}",
                severity=severity,
                details={"var": var_name, "set": True},
            )
        return CheckResult(
            name=f"env_{var_name}",
            passed=False,
            message=f"{var_name} is not set",
            severity=severity,
            details={"var": var_name, "set": False},
        )
    return StartupCheck(name=f"env_{var_name}", check_fn=_check, severity=severity)


def check_disk_space(
    path: str = ".",
    min_gb: float = 1.0,
    severity: CheckSeverity = CheckSeverity.WARNING,
) -> StartupCheck:
    """Create a check that verifies available disk space."""
    async def _check() -> CheckResult:
        try:
            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < min_gb:
                return CheckResult(
                    name=f"disk_{path}",
                    passed=False,
                    message=f"Low disk space: {free_gb:.2f}GB free (min {min_gb}GB)",
                    severity=severity,
                    details={"path": path, "free_gb": round(free_gb, 2), "min_gb": min_gb},
                )
            return CheckResult(
                name=f"disk_{path}",
                passed=True,
                message=f"{free_gb:.2f}GB free",
                severity=severity,
                details={"path": path, "free_gb": round(free_gb, 2)},
            )
        except Exception as e:
            return CheckResult(
                name=f"disk_{path}",
                passed=False,
                message=str(e),
                severity=severity,
            )
    return StartupCheck(name=f"disk_{path}", check_fn=_check, severity=severity)


def check_directory_writable(
    path: str,
    severity: CheckSeverity = CheckSeverity.CRITICAL,
) -> StartupCheck:
    """Create a check that verifies a directory exists and is writable."""
    async def _check() -> CheckResult:
        try:
            os.makedirs(path, exist_ok=True)
            test_file = os.path.join(path, ".startup_write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return CheckResult(
                name=f"writable_{path}",
                passed=True,
                message=f"{path} is writable",
                severity=severity,
                details={"path": path},
            )
        except Exception as e:
            return CheckResult(
                name=f"writable_{path}",
                passed=False,
                message=f"{path} not writable: {e}",
                severity=severity,
                details={"path": path},
            )
    return StartupCheck(name=f"writable_{path}", check_fn=_check, severity=severity)


# --- Singleton ---

_validator: Optional[StartupValidator] = None


def get_startup_validator() -> StartupValidator:
    global _validator
    if _validator is None:
        _validator = StartupValidator()
    return _validator


def reset_startup_validator():
    global _validator
    _validator = None
