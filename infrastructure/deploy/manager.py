"""
Unified deployment orchestrator.

Supports three deployment modes:
  - local:    Docker Compose on the local machine
  - cloud:    Cloud deployment (AWS ECS, GCP Cloud Run, Azure)
  - hybrid:   Local services + cloud AI providers
"""

import os
import sys
import json
import subprocess
import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DeploymentMode(Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


@dataclass
class ServiceInfo:
    name: str
    status: str
    container_id: str = ""
    ports: List[str] = field(default_factory=list)
    health: str = "unknown"


@dataclass
class DeploymentResult:
    success: bool
    mode: DeploymentMode
    message: str
    timestamp: str
    services: List[ServiceInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class DeploymentManager:
    """Orchestrates deployment across local, cloud, and hybrid environments."""

    def __init__(
        self,
        mode: DeploymentMode = DeploymentMode.LOCAL,
        project_root: Optional[Path] = None,
        compose_file: Optional[Path] = None,
        env_file: Optional[Path] = None,
    ):
        self.mode = mode
        self.project_root = project_root or Path.cwd()
        self.compose_file = compose_file or self.project_root / "deployment" / "docker-compose.yml"
        self.env_file = env_file or self.project_root / ".env"

    async def deploy(self) -> DeploymentResult:
        if self.mode == DeploymentMode.LOCAL:
            return await self._deploy_local()
        elif self.mode == DeploymentMode.CLOUD:
            return await self._deploy_cloud()
        elif self.mode == DeploymentMode.HYBRID:
            return await self._deploy_hybrid()
        raise ValueError(f"Unknown deployment mode: {self.mode}")

    async def _run_compose_command(self, action: str, service: str = "") -> Tuple[int, str, str]:
        cmd = ["docker-compose"]
        if self.compose_file and self.compose_file.exists():
            cmd.extend(["-f", str(self.compose_file)])
        if self.env_file and self.env_file.exists():
            cmd.extend(["--env-file", str(self.env_file)])
        cmd.append(action)
        if service:
            cmd.append(service)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_root),
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            return proc.returncode or 0, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", "docker-compose not found. Is Docker installed?"

    def _load_env_template(self) -> Dict[str, str]:
        env: Dict[str, str] = {}
        env_file = self.project_root / ".env.example"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip().strip('"\'')
        return env

    async def _deploy_local(self) -> DeploymentResult:
        logger.info("Starting local deployment...")
        errors: List[str] = []
        services: List[ServiceInfo] = []

        rc, stdout, stderr = await self._run_compose_command("pull")
        if rc != 0:
            errors.append(f"docker-compose pull failed: {stderr}")

        rc, stdout, stderr = await self._run_compose_command("up", "-d")
        if rc != 0:
            errors.append(f"docker-compose up failed: {stderr}")
            return DeploymentResult(
                success=False,
                mode=DeploymentMode.LOCAL,
                message="Local deployment failed",
                timestamp=datetime.now(timezone.utc).isoformat(),
                errors=errors,
            )

        rc, stdout, stderr = await self._run_compose_command("ps")
        if rc == 0:
            for line in stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    services.append(ServiceInfo(
                        name=parts[0],
                        status=parts[-1] if parts[-1] in ("Up", "running", "exited") else "unknown",
                    ))

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.LOCAL,
            message="Local deployment completed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            services=services,
            errors=errors,
        )

    async def _deploy_cloud(self) -> DeploymentResult:
        logger.info("Starting cloud deployment...")
        errors: List[str] = []

        provider = os.environ.get("CLOUD_PROVIDER", "aws").lower()
        if provider == "aws":
            result = await self._deploy_aws()
        elif provider == "gcp":
            result = await self._deploy_gcp()
        elif provider == "azure":
            result = await self._deploy_azure()
        else:
            return DeploymentResult(
                success=False,
                mode=DeploymentMode.CLOUD,
                message=f"Unknown cloud provider: {provider}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                errors=[f"CLOUD_PROVIDER={provider} not supported"],
            )
        return result

    async def _deploy_aws(self) -> DeploymentResult:
        errors: List[str] = []
        ecs_cluster = os.environ.get("AWS_ECS_CLUSTER", "jarvis-cluster")
        ecs_service = os.environ.get("AWS_ECS_SERVICE", "jarvis-service")

        try:
            proc = await asyncio.create_subprocess_exec(
                "aws", "ecs", "update-service",
                "--cluster", ecs_cluster,
                "--service", ecs_service,
                "--force-new-deployment",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode:
                errors.append(f"AWS deploy failed: {stderr.decode()}")
        except FileNotFoundError:
            errors.append("AWS CLI not found. Install with: pip install awscli")
        except asyncio.TimeoutError:
            errors.append("AWS deploy timed out")

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.CLOUD,
            message="AWS deployment completed" if not errors else "AWS deployment failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=errors,
            details={"provider": "aws", "cluster": ecs_cluster, "service": ecs_service},
        )

    async def _deploy_gcp(self) -> DeploymentResult:
        errors: List[str] = []
        service_name = os.environ.get("GCP_CLOUD_RUN_SERVICE", "jarvis")
        region = os.environ.get("GCP_REGION", "us-central1")

        try:
            proc = await asyncio.create_subprocess_exec(
                "gcloud", "run", "deploy", service_name,
                "--region", region,
                "--source", ".",
                "--allow-unauthenticated",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode:
                errors.append(f"GCP deploy failed: {stderr.decode()}")
        except FileNotFoundError:
            errors.append("gcloud CLI not found. Install from: https://cloud.google.com/sdk")
        except asyncio.TimeoutError:
            errors.append("GCP deploy timed out")

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.CLOUD,
            message="GCP deployment completed" if not errors else "GCP deployment failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=errors,
            details={"provider": "gcp", "service": service_name, "region": region},
        )

    async def _deploy_azure(self) -> DeploymentResult:
        errors: List[str] = []
        app_name = os.environ.get("AZURE_WEBAPP_NAME", "jarvis-app")
        rg = os.environ.get("AZURE_RESOURCE_GROUP", "jarvis-rg")

        try:
            proc = await asyncio.create_subprocess_exec(
                "az", "webapp", "deploy",
                "--resource-group", rg,
                "--name", app_name,
                "--src-path", ".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode:
                errors.append(f"Azure deploy failed: {stderr.decode()}")
        except FileNotFoundError:
            errors.append("Azure CLI not found. Install from: https://docs.microsoft.com/cli/azure")
        except asyncio.TimeoutError:
            errors.append("Azure deploy timed out")

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.CLOUD,
            message="Azure deployment completed" if not errors else "Azure deployment failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=errors,
            details={"provider": "azure", "app": app_name, "resource_group": rg},
        )

    async def _deploy_hybrid(self) -> DeploymentResult:
        logger.info("Starting hybrid deployment (local services + cloud AI)...")
        errors: List[str] = []
        services: List[ServiceInfo] = []

        # Deploy core services locally (DB, Redis, API)
        local_services = ["db", "redis", "backend"]
        for svc in local_services:
            rc, stdout, stderr = await self._run_compose_command("up", "-d")
            if rc != 0:
                errors.append(f"Failed to start {svc}: {stderr}")

        rc, stdout, stderr = await self._run_compose_command("ps")
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                services.append(ServiceInfo(
                    name=parts[0],
                    status=parts[-1] if parts[-1] in ("Up", "running", "exited") else "unknown",
                ))

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.HYBRID,
            message="Hybrid deployment completed" if not errors else "Hybrid deployment had errors",
            timestamp=datetime.now(timezone.utc).isoformat(),
            services=services,
            errors=errors,
            details={"mode": "hybrid", "local_services": local_services},
        )

    async def rollback(self, service: str = "") -> DeploymentResult:
        if self.mode == DeploymentMode.LOCAL:
            return await self._rollback_local(service)
        elif self.mode == DeploymentMode.CLOUD:
            return await self._rollback_cloud(service)
        return DeploymentResult(
            success=False,
            mode=self.mode,
            message="Rollback not supported for this mode",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def _rollback_local(self, service: str = "") -> DeploymentResult:
        target = service if service else ""
        rc, stdout, stderr = await self._run_compose_command("down")
        if rc != 0:
            return DeploymentResult(
                success=False,
                mode=DeploymentMode.LOCAL,
                message=f"Rollback failed: {stderr}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                errors=[stderr],
            )
        return DeploymentResult(
            success=True,
            mode=DeploymentMode.LOCAL,
            message="All local services stopped (rollback complete)",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    async def _rollback_cloud(self, service: str = "") -> DeploymentResult:
        provider = os.environ.get("CLOUD_PROVIDER", "aws").lower()
        errors: List[str] = []
        try:
            if provider == "aws":
                ecs_cluster = os.environ.get("AWS_ECS_CLUSTER", "jarvis-cluster")
                ecs_service = os.environ.get("AWS_ECS_SERVICE", "jarvis-service")
                proc = await asyncio.create_subprocess_exec(
                    "aws", "ecs", "update-service",
                    "--cluster", ecs_cluster,
                    "--service", ecs_service,
                    "--force-new-deployment",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                if proc.returncode:
                    errors.append(f"AWS rollback failed: {stderr.decode()}")
            elif provider == "gcp":
                revision = os.environ.get("GCP_PREVIOUS_REVISION", "")
                if revision:
                    proc = await asyncio.create_subprocess_exec(
                        "gcloud", "run", "services", "update-traffic",
                        os.environ.get("GCP_CLOUD_RUN_SERVICE", "jarvis"),
                        f"--to-revisions={revision}=100",
                        f"--region={os.environ.get('GCP_REGION', 'us-central1')}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                    if proc.returncode:
                        errors.append(f"GCP rollback failed: {stderr.decode()}")
                else:
                    errors.append("GCP_PREVIOUS_REVISION not set for rollback")
        except FileNotFoundError:
            errors.append(f"{provider} CLI not found")
        except asyncio.TimeoutError:
            errors.append(f"{provider} rollback timed out")

        return DeploymentResult(
            success=len(errors) == 0,
            mode=DeploymentMode.CLOUD,
            message="Cloud rollback completed" if not errors else "Cloud rollback failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            errors=errors,
        )

    async def status(self) -> Dict[str, Any]:
        rc, stdout, stderr = await self._run_compose_command("ps")
        services: List[Dict[str, str]] = []
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                services.append({
                    "name": parts[0],
                    "status": parts[-1] if parts[-1] in ("Up", "running", "exited") else "unknown",
                })

        return {
            "mode": self.mode.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": services,
            "total": len(services),
        }

    async def logs(self, service: str = "", tail: int = 100) -> str:
        rc, stdout, stderr = await self._run_compose_command("logs", f"--tail={tail} {service}")
        return stdout + stderr
