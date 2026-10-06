"""Remote execution host abstraction.

Attaches a capable remote machine to JARVIS as an execution plane without
changing any existing architecture.  This module creates NO registry, job
queue, provider abstraction or secret store: it plugs into the existing
Capability Fabric, JobRegistry, ArtifactRegistry and AuditEventService.

Lifecycle (existing state vocabulary only)::

    configured -> authenticated -> reachable -> healthy
               -> resource_verified -> job_verified

Nothing is provisioned.  With no host configured the system reports
``NOT_CONFIGURED`` and ``blocking=False``.  A configured-but-unreachable host is
never reported AVAILABLE.
"""
from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# The single environment variable that identifies a real remote execution
# endpoint.  No competing variables are introduced.
ENV_HOST = "JARVIS_DOCKER_REMOTE_HOST"
ENV_USER = "JARVIS_DOCKER_REMOTE_USER"
ENV_IDENTITY = "JARVIS_DOCKER_REMOTE_IDENTITY"
ENV_TIMEOUT = "JARVIS_DOCKER_REMOTE_TIMEOUT"

RESOURCE_TYPE = "remote_execution_host"
RESOURCE_ID = "remote_execution_host"

# Lifecycle states, exactly the existing vocabulary.
STATES = ("configured", "authenticated", "reachable", "healthy",
          "resource_verified", "job_verified", "inference_verified")

NOT_CONFIGURED = "NOT_CONFIGURED"
AVAILABLE = "AVAILABLE"
UNREACHABLE = "UNREACHABLE"

# Cost classes.  Nothing is ever started automatically.
COST_CLASSES = ("free", "free_tier", "pay_per_use", "always_on")


# --------------------------------------------------------------------------- #
# Resource contract
# --------------------------------------------------------------------------- #
@dataclass
class RemoteExecutionHost:
    """A general-purpose remote machine able to run workloads the laptop cannot.

    Unavailable fields stay ``None`` - they are never invented.
    """

    resource_id: str = RESOURCE_ID
    provider: str = "remote_host"
    region: Optional[str] = None
    endpoint: Optional[str] = None
    os: Optional[str] = None
    architecture: Optional[str] = None
    cpu: Optional[str] = None
    cpu_cores: Optional[int] = None
    memory_gb: Optional[float] = None
    gpu: Optional[str] = None
    gpu_count: int = 0
    gpu_memory_gb: Optional[float] = None
    storage_gb: Optional[float] = None
    docker: bool = False
    docker_version: Optional[str] = None
    status: str = NOT_CONFIGURED
    health: str = "unknown"
    transport: Optional[str] = None
    capabilities: list[str] = field(default_factory=list)
    cost_class: Optional[str] = None
    state_chain: dict[str, bool] = field(default_factory=dict)
    reason: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    created_at: Optional[float] = None
    last_seen: Optional[float] = None
    uptime_s: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_usable(self) -> bool:
        """Usable only when authenticated, reachable AND resource verified."""
        chain = self.state_chain or {}
        return bool(self.status == AVAILABLE
                    and chain.get("authenticated")
                    and chain.get("reachable")
                    and chain.get("resource_verified"))


# --------------------------------------------------------------------------- #
# Transports - extensible; only SSH is wired, and only when configured
# --------------------------------------------------------------------------- #
class Transport:
    """Base transport contract. Implementations never provision anything."""

    name = "none"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def run(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        raise NotImplementedError


class SshTransport(Transport):
    """Runs a fixed, read-only probe argv over SSH.

    The local command is always a fixed list; the remote command is always a
    fixed literal. No user string is ever interpolated into a shell command.
    """

    name = "ssh"

    def __init__(self, host: str = "", user: str = "", identity: Optional[str] = None,
                 timeout: int = 20) -> None:
        self.host = host
        self.user = user
        self.identity = identity
        self.timeout = timeout

    def _base(self) -> list[str]:
        exe = shutil.which("ssh")
        if not exe:
            raise RuntimeError("ssh client not available on this host")
        argv = [exe, "-o", "BatchMode=yes", "-o",
                f"ConnectTimeout={self.timeout}", "-o", "StrictHostKeyChecking=accept-new"]
        if self.identity:
            argv += ["-i", self.identity]
        argv.append(f"{self.user}@{self.host}" if self.user else self.host)
        return argv

    def available(self) -> tuple[bool, str]:
        exe = shutil.which("ssh")
        if not exe:
            return False, "ssh client not installed on the control node"
        return True, "ssh client present"

    def run(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        """``argv`` must be a fixed remote command; never caller-interpolated."""
        proc = subprocess.run(  # noqa: S603
            self._base() + [argv], capture_output=True, text=True,
            timeout=timeout, shell=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""


class HttpsAgentTransport(Transport):
    """Reserved for a future JARVIS worker agent exposing an HTTPS API.

    Not implemented: no agent exists, and inventing one would fabricate a host.
    """

    name = "agent_https"

    def available(self) -> tuple[bool, str]:
        return False, "no remote worker agent is deployed"

    def run(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        raise RuntimeError("agent transport not implemented")


TRANSPORTS: dict[str, type[Transport]] = {
    "ssh": SshTransport,
    "agent_https": HttpsAgentTransport,
}


# --------------------------------------------------------------------------- #
# Fixed probe commands (read-only, no mutation)
# --------------------------------------------------------------------------- #
_PROBES: dict[str, str] = {
    "os": "uname -s",
    "architecture": "uname -m",
    "cpu": "nproc",
    "memory": "awk '/MemTotal/ {printf \"%.1f\", $2/1048576}' /proc/meminfo",
    "storage": "df -BG --output=avail / | tail -1 | tr -dc '0-9'",
    "docker_version": "docker version --format '{{.Server.Version}}' 2>/dev/null",
    "gpu": "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null",
    "gpu_memory": ("nvidia-smi --query-gpu=memory.total "
                   "--format=csv,noheader,nounits 2>/dev/null | head -1"),
    "uptime": "awk '{print int($1)}' /proc/uptime",
}

_SAFE_TEST_JOB = "echo JARVIS_REMOTE_EXECUTION_OK"


# --------------------------------------------------------------------------- #
# Discovery + verification
# --------------------------------------------------------------------------- #
def _timeout() -> int:
    try:
        return int(os.environ.get(ENV_TIMEOUT, "20"))
    except ValueError:
        return 20


def discover(verify: bool = True) -> RemoteExecutionHost:
    """Discover and (optionally) verify the remote execution host.

    Returns a host whose unavailable fields are ``None``.  Never provisions.
    """
    host = RemoteExecutionHost()
    raw = (os.environ.get(ENV_HOST) or "").strip()
    if not raw:
        host.status = NOT_CONFIGURED
        host.reason = (
            f"{ENV_HOST} is not set. JARVIS operates as a single-node control "
            "plane; remote execution is optional and non-blocking.")
        host.notes.append("Set JARVIS_DOCKER_REMOTE_HOST to attach a host.")
        return host

    host.configured = True  # type: ignore[attr-defined]
    host.endpoint = raw
    user = (os.environ.get(ENV_USER) or "").strip() or None
    identity = (os.environ.get(ENV_IDENTITY) or "").strip() or None
    host.created_at = time.time()

    # Normalise host:port / scheme forms without shell involvement.
    target = raw.split("://", 1)[-1].split("/")[0]
    hostname, _, port = target.partition(":")
    if not hostname:
        host.status = UNREACHABLE
        host.reason = f"{ENV_HOST} is malformed: {raw!r}"
        return host

    # Transport selection: ssh when a client exists, else the (unimplemented)
    # agent transport. Never silently downgrade to something unsafe.
    transport: Optional[Transport] = None
    ssh_ok, ssh_reason = SshTransport().available()
    if ssh_ok:
        transport = SshTransport(hostname, user or "", identity, _timeout())
    else:
        host.status = UNREACHABLE
        host.transport = "none"
        host.reason = ssh_reason
        host.state_chain = {"configured": True}
        return host
    host.transport = transport.name
    host.state_chain = {"configured": True}

    if not verify:
        host.status = UNREACHABLE
        host.reason = "verification not requested"
        return host

    # TCP reachability first: cheap and does not require credentials.
    reachable, detail = _tcp_probe(hostname, int(port) if port else 22, 3.0)
    host.state_chain["reachable"] = reachable
    host.last_seen = time.time() if reachable else None
    if not reachable:
        host.status = UNREACHABLE
        host.reason = f"TCP connect failed: {detail}"
        return host

    # Authentication: BatchMode means no interactive prompt is possible; a
    # non-zero exit from a trivial remote command means auth failed.
    try:
        code, _out, err = transport.run(["true"], timeout=_timeout())
    except (subprocess.TimeoutExpired, OSError, RuntimeError) as exc:
        host.status = UNREACHABLE
        host.reason = f"transport error: {type(exc).__name__}: {exc}"
        return host
    host.state_chain["authenticated"] = (code == 0)
    if code != 0:
        host.status = UNREACHABLE
        host.reason = ("SSH authentication failed (BatchMode, non-interactive)"
                       if "Permission denied" in err else
                       f"remote probe failed (exit {code})")
        return host

    # Resource discovery: every field stays None if the probe fails.
    for key, command in _PROBES.items():
        try:
            code, out, _err = transport.run([command], timeout=_timeout())
        except (subprocess.TimeoutExpired, OSError, RuntimeError):
            continue
        if code != 0:
            continue
        value = out.strip()
        if not value:
            continue
        if key == "os":
            host.os = value
        elif key == "architecture":
            host.architecture = value
        elif key == "cpu":
            host.cpu_cores = int(value) if value.isdigit() else None
            host.cpu = f"{host.cpu_cores} cores" if host.cpu_cores else None
        elif key == "memory":
            try:
                host.memory_gb = float(value)
            except ValueError:
                pass
        elif key == "storage":
            try:
                host.storage_gb = float(value)
            except ValueError:
                pass
        elif key == "docker_version":
            host.docker = True
            host.docker_version = value
        elif key == "gpu":
            gpus = [g.strip() for g in value.splitlines() if g.strip()]
            host.gpu = gpus[0] if gpus else None
            host.gpu_count = len(gpus)
        elif key == "gpu_memory":
            try:
                host.gpu_memory_gb = round(float(value) / 1024.0, 1)
            except ValueError:
                pass
        elif key == "uptime":
            try:
                host.uptime_s = float(value)
            except ValueError:
                pass

    host.state_chain["healthy"] = True
    host.health = "reachable"

    # Resource verification requires facts, not optimism: at minimum we must
    # know the OS and that we can execute something.
    verified = bool(host.os)
    if verified:
        try:
            code, out, _err = transport.run([_SAFE_TEST_JOB], timeout=_timeout())
            verified = (code == 0 and "JARVIS_REMOTE_EXECUTION_OK" in out)
            if verified:
                host.state_chain["job_verified"] = True
        except (subprocess.TimeoutExpired, OSError, RuntimeError):
            verified = False
    host.state_chain["resource_verified"] = verified

    if not verified:
        host.status = UNREACHABLE
        host.reason = "connected but could not verify resources or run a safe job"
        return host

    caps = ["long_running_jobs", "process_execution", "filesystem_sandbox"]
    if host.docker:
        caps += ["containers", "service_isolation", "build_test",
                 "integration_testing", "browser_worker"]
    if host.gpu:
        caps.append("gpu_workloads")
    if host.memory_gb and host.memory_gb >= 8:
        caps.append("large_document_processing")
    host.capabilities = sorted(set(caps))
    host.cost_class = os.environ.get("JARVIS_DOCKER_REMOTE_COST_CLASS",
                                    "unknown")
    host.status = AVAILABLE
    host.reason = None
    return host


def _tcp_probe(host: str, port: int, timeout: float) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "connected"
    except OSError as exc:
        return False, f"{type(exc).__name__}"


def verify_job() -> dict[str, Any]:
    """Run the safe, read-only test job and report an ACTUAL result."""
    host = discover(verify=False)
    if not host.endpoint or not host.transport:
        return {"status": "NOT_CONFIGURED", "ran": False,
                "reason": host.reason, "blocking": False}
    transport = SshTransport(
        host.endpoint.split("://", 1)[-1].split("/")[0],
        (os.environ.get(ENV_USER) or "").strip(),
        (os.environ.get(ENV_IDENTITY) or "").strip() or None, _timeout())
    started = time.monotonic()
    try:
        code, out, err = transport.run([_SAFE_TEST_JOB], timeout=_timeout())
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAILED", "ran": False, "blocking": False,
                "reason": f"{type(exc).__name__}: {exc}"}
    ok = (code == 0 and "JARVIS_REMOTE_EXECUTION_OK" in out)
    return {
        "status": "JOB_VERIFIED" if ok else "FAILED",
        "ran": True, "command": _SAFE_TEST_JOB, "exit_code": code,
        "stdout": out.strip()[:200], "stderr": err.strip()[:200] if err else None,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "blocking": False,
        "note": ("Real execution only. Mocks are never reported as "
                 "remote_execution_verified."),
    }


# --------------------------------------------------------------------------- #
# Requirement matching
# --------------------------------------------------------------------------- #
def meets_requirements(host: RemoteExecutionHost,
                       req: dict[str, Any]) -> tuple[bool, list[str]]:
    """Does this host satisfy the request? Providers are never hardcoded."""
    reasons: list[str] = []
    if not host.is_usable():
        reasons.append(host.reason or f"host status={host.status}")
    if req.get("gpu_required") and not host.gpu:
        reasons.append("gpu_required but host exposes no GPU")
    if req.get("gpu_memory_required"):
        need = float(req.get("gpu_memory_required") or 0)
        have = host.gpu_memory_gb or 0
        if have < need:
            reasons.append(f"gpu_memory required {need}GB, host reports {have}GB")
    if req.get("docker_required") and not host.docker:
        reasons.append("docker_required but host has no Docker daemon")
    if req.get("cpu_required"):
        need = int(req.get("cpu_required") or 0)
        if (host.cpu_cores or 0) < need:
            reasons.append(f"cpu_required {need}, host reports {host.cpu_cores}")
    if req.get("memory_required"):
        need = float(req.get("memory_required") or 0)
        have = host.memory_gb or 0
        if have < need:
            reasons.append(f"memory_required {need}GB, host reports {have}GB")
    if req.get("network_required") and host.state_chain.get("reachable") is False:
        reasons.append("network_required but host unreachable")
    return (not reasons), reasons


def remote_status() -> dict[str, Any]:
    """Status of the remote execution plane, including cost controls."""
    host = discover()
    return {
        "resource": host.to_dict(),
        "available": host.is_usable(),
        "blocking": False,
        "transports_available": {
            name: (cls().available()[0] if name == "ssh" else False)
            for name, cls in TRANSPORTS.items()
        },
        "environment": {
            ENV_HOST: bool((os.environ.get(ENV_HOST) or "").strip()),
            ENV_USER: bool((os.environ.get(ENV_USER) or "").strip()),
            ENV_IDENTITY: bool((os.environ.get(ENV_IDENTITY) or "").strip()),
        },
        "cost_controls": {
            "cost_class": host.cost_class,
            "lifecycle_states": ["running", "idle", "stopped", "terminated"],
            "auto_start": False,
            "auto_provision": False,
            "note": ("Observation and lifecycle contracts only. JARVIS never "
                     "creates, starts or terminates paid infrastructure."),
        },
        "deployment_contracts": {
            "brain": {"supported": host.is_usable(), "deployed": False,
                      "note": "Brain is NOT deployed remotely. Requires a "
                              "verified host."},
            "browser_worker": {"supported": bool(host.docker),
                               "deployed": False,
                               "note": "No browser worker is launched."},
            "job_worker": {"supported": host.is_usable(), "deployed": False},
        },
    }


__all__ = [
    "RemoteExecutionHost", "Transport", "SshTransport", "HttpsAgentTransport",
    "TRANSPORTS", "discover", "verify_job", "remote_status",
    "meets_requirements", "ENV_HOST", "ENV_USER", "ENV_IDENTITY",
    "ENV_TIMEOUT", "RESOURCE_ID", "RESOURCE_TYPE", "STATES",
    "NOT_CONFIGURED", "AVAILABLE", "COST_CLASSES",
]
