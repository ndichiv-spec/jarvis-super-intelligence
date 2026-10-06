"""
JARVIS Deployment and Scaling Management System
==============================================
Advanced deployment and scaling management system for the JARVIS drive engine
with comprehensive deployment strategies, auto-scaling, and infrastructure management.

Features:
- Multi-environment deployment
- Auto-scaling capabilities
- Load balancing
- Service orchestration
- Infrastructure management
- Deployment strategies (rolling, blue-green, canary)
- Health monitoring during deployment
- Rollback capabilities
- Resource optimization
- Performance monitoring
- Container orchestration
- Cloud deployment support
- Zero-downtime deployment
"""

import asyncio
import json
import logging
import time
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid
import threading
from pathlib import Path
import yaml
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class DeploymentEnvironment(Enum):
    """Deployment environment enumeration"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DR = "disaster_recovery"


class DeploymentStrategy(Enum):
    """Deployment strategy enumeration"""
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    RECREATE = "recreate"
    CUSTOM = "custom"


class ScalingPolicy(Enum):
    """Scaling policy enumeration"""
    MANUAL = "manual"
    AUTO = "auto"
    SCHEDULED = "scheduled"
    EVENT_DRIVEN = "event_driven"


class ServiceState(Enum):
    """Service state enumeration"""
    PENDING = "pending"
    DEPLOYING = "deploying"
    RUNNING = "running"
    SCALING = "scaling"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class Service:
    """Service definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    service_type: str = ""
    image: str = ""
    version: str = "1.0.0"
    replicas: int = 1
    min_replicas: int = 1
    max_replicas: int = 10
    cpu_request: float = 0.5
    cpu_limit: float = 1.0
    memory_request: str = "512Mi"
    memory_limit: str = "1Gi"
    ports: List[int] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    volumes: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    health_check_path: str = "/health"
    readiness_check_path: str = "/ready"
    state: ServiceState = ServiceState.UNKNOWN
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.state == ServiceState.RUNNING
    
    def needs_scaling(self) -> bool:
        """Check if service needs scaling"""
        return self.replicas != self.min_replicas and self.replicas != self.max_replicas


@dataclass
class Deployment:
    """Deployment definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service_id: str = ""
    environment: DeploymentEnvironment = DeploymentEnvironment.DEVELOPMENT
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    target_version: str = ""
    current_version: str = ""
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration: float = 0.0
    rollout_percent: float = 0.0
    rollback_enabled: bool = True
    rollback_version: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def start_deployment(self):
        """Start deployment"""
        self.status = "deploying"
        self.started_at = datetime.now()
        self.add_log("Deployment started")
    
    def complete_deployment(self):
        """Complete deployment"""
        self.status = "completed"
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration = (self.completed_at - self.started_at).total_seconds()
        self.add_log("Deployment completed successfully")
    
    def fail_deployment(self, error: str):
        """Fail deployment"""
        self.status = "failed"
        self.completed_at = datetime.now()
        if self.started_at:
            self.duration = (self.completed_at - self.started_at).total_seconds()
        self.error = error
        self.add_log(f"Deployment failed: {error}")
    
    def add_log(self, message: str):
        """Add log entry"""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        logger.info(f"Deployment {self.id}: {message}")


@dataclass
class ScalingEvent:
    """Scaling event definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service_id: str = ""
    scaling_type: str = "scale_out"  # scale_out or scale_in
    current_replicas: int = 0
    target_replicas: int = 0
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    triggered_by: str = "auto"  # auto, manual, scheduled
    metrics: Dict[str, float] = field(default_factory=dict)
    completed: bool = False
    error: Optional[str] = None


class DeploymentManager:
    """Advanced deployment and scaling management system"""
    
    def __init__(self, project_root: str = str(Path(__file__).parent.parent)):
        self.project_root = Path(project_root)
        self.services: Dict[str, Service] = {}
        self.deployments: Dict[str, Deployment] = {}
        self.scaling_events: Dict[str, ScalingEvent] = {}
        
        # Deployment configuration
        self.deployment_configs = {
            "development": {
                "auto_deploy": True,
                "health_check_interval": 30,
                "rollback_on_failure": True,
                "max_parallel_deployments": 3
            },
            "testing": {
                "auto_deploy": True,
                "health_check_interval": 60,
                "rollback_on_failure": True,
                "max_parallel_deployments": 2
            },
            "staging": {
                "auto_deploy": False,
                "health_check_interval": 30,
                "rollback_on_failure": True,
                "max_parallel_deployments": 1
            },
            "production": {
                "auto_deploy": False,
                "health_check_interval": 15,
                "rollback_on_failure": True,
                "max_parallel_deployments": 1
            }
        }
        
        # Auto-scaling configuration
        self.scaling_policies = {
            "cpu_threshold": 70.0,
            "memory_threshold": 80.0,
            "scale_up_cooldown": 300,  # 5 minutes
            "scale_down_cooldown": 600,  # 10 minutes
            "min_replicas_for_scaling": 2
        }
        
        # Active deployments
        self.active_deployments: Dict[str, Deployment] = {}
        
        # Monitoring
        self.monitoring_active = False
        self.monitoring_task = None
        
        # Load balancer
        self.load_balancer = LoadBalancer()
        
        # Initialize
        self._initialize_default_services()
    
    def _initialize_default_services(self):
        """Initialize default services"""
        default_services = [
            Service(
                name="jarvis-api",
                service_type="api",
                image="jarvis/api",
                version="1.0.0",
                replicas=2,
                min_replicas=1,
                max_replicas=5,
                ports=[8080],
                health_check_path="/health",
                readiness_check_path="/ready"
            ),
            Service(
                name="jarvis-dashboard",
                service_type="web",
                image="jarvis/dashboard",
                version="1.0.0",
                replicas=1,
                min_replicas=1,
                max_replicas=3,
                ports=[3000],
                health_check_path="/api/health",
                readiness_check_path="/api/ready"
            ),
            Service(
                name="jarvis-ai-orchestrator",
                service_type="ai",
                image="jarvis/ai-orchestrator",
                version="1.0.0",
                replicas=3,
                min_replicas=2,
                max_replicas=8,
                ports=[8081],
                health_check_path="/ai/health",
                readiness_check_path="/ai/ready"
            )
        ]
        
        for service in default_services:
            self.services[service.id] = service
    
    async def start_monitoring(self):
        """Start deployment monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Deployment monitoring started")
    
    async def stop_monitoring(self):
        """Stop deployment monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Deployment monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Monitor service health
                await self._monitor_service_health()
                
                # Check for auto-scaling
                await self._check_auto_scaling()
                
                # Monitor active deployments
                await self._monitor_active_deployments()
                
                # Update load balancer
                await self._update_load_balancer()
                
                # Sleep for next iteration
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(60)
    
    async def _monitor_service_health(self):
        """Monitor service health"""
        for service_id, service in self.services.items():
            try:
                if service.state == ServiceState.RUNNING:
                    # Perform health check
                    healthy = await self._perform_health_check(service)
                    
                    if not healthy:
                        logger.warning(f"Service {service.name} is unhealthy")
                        service.state = ServiceState.ERROR
                        # Trigger auto-recovery
                        await self._trigger_service_recovery(service_id)
                    else:
                        service.state = ServiceState.RUNNING
                
            except Exception as e:
                logger.error(f"Error monitoring service {service_id}: {e}")
                service.state = ServiceState.ERROR
    
    async def _perform_health_check(self, service: Service) -> bool:
        """Perform health check on service"""
        try:
            # Check if service has ports
            if not service.ports:
                return True
            
            # Try to connect to health endpoint
            for port in service.ports:
                try:
                    url = f"http://localhost:{port}{service.health_check_path}"
                    response = requests.get(url, timeout=5)
                    if response.status_code == 200:
                        return True
                except requests.RequestException:
                    continue
            
            return False
            
        except Exception as e:
            logger.error(f"Health check error for service {service.name}: {e}")
            return False
    
    async def _trigger_service_recovery(self, service_id: str):
        """Trigger service recovery"""
        service = self.services[service_id]
        logger.info(f"Triggering recovery for service {service.name}")
        
        # Try to restart service
        await self.restart_service(service_id)
    
    async def _check_auto_scaling(self):
        """Check for auto-scaling opportunities"""
        for service_id, service in self.services.items():
            if service.state != ServiceState.RUNNING:
                continue
            
            # Get current metrics
            metrics = await self._get_service_metrics(service_id)
            
            # Check scale-up conditions
            if self._should_scale_up(service, metrics):
                await self._scale_service(service_id, service.replicas + 1, "Auto scale-up due to high load")
            
            # Check scale-down conditions
            elif self._should_scale_down(service, metrics):
                await self._scale_service(service_id, service.replicas - 1, "Auto scale-down due to low load")
    
    def _should_scale_up(self, service: Service, metrics: Dict[str, float]) -> bool:
        """Check if service should scale up"""
        if service.replicas >= service.max_replicas:
            return False
        
        cpu_usage = metrics.get("cpu_usage", 0)
        memory_usage = metrics.get("memory_usage", 0)
        
        return (cpu_usage > self.scaling_policies["cpu_threshold"] or 
                memory_usage > self.scaling_policies["memory_threshold"])
    
    def _should_scale_down(self, service: Service, metrics: Dict[str, float]) -> bool:
        """Check if service should scale down"""
        if service.replicas <= service.min_replicas:
            return False
        
        cpu_usage = metrics.get("cpu_usage", 0)
        memory_usage = metrics.get("memory_usage", 0)
        
        return (cpu_usage < self.scaling_policies["cpu_threshold"] * 0.5 and 
                memory_usage < self.scaling_policies["memory_threshold"] * 0.5)
    
    async def _get_service_metrics(self, service_id: str) -> Dict[str, float]:
        """Get service metrics"""
        # This would integrate with monitoring system
        # For now, return mock metrics
        return {
            "cpu_usage": 45.0,
            "memory_usage": 60.0,
            "request_rate": 100.0,
            "error_rate": 1.0
        }
    
    async def _monitor_active_deployments(self):
        """Monitor active deployments"""
        for deployment_id, deployment in list(self.active_deployments.items()):
            try:
                if deployment.status == "deploying":
                    # Check deployment progress
                    await self._check_deployment_progress(deployment)
                
                elif deployment.status == "completed":
                    # Remove from active deployments
                    del self.active_deployments[deployment_id]
                
                elif deployment.status == "failed":
                    # Trigger rollback if enabled
                    if deployment.rollback_enabled and deployment.rollback_version:
                        await self._trigger_rollback(deployment)
                    del self.active_deployments[deployment_id]
            
            except Exception as e:
                logger.error(f"Error monitoring deployment {deployment_id}: {e}")
    
    async def _check_deployment_progress(self, deployment: Deployment):
        """Check deployment progress"""
        # This would check actual deployment progress
        # For now, simulate progress
        if deployment.rollout_percent < 100:
            deployment.rollout_percent = min(100, deployment.rollout_percent + 10)
            deployment.add_log(f"Rollout progress: {deployment.rollout_percent}%")
    
    async def _trigger_rollback(self, deployment: Deployment):
        """Trigger deployment rollback"""
        deployment.add_log("Triggering rollback")
        
        # Create rollback deployment
        rollback_deployment = Deployment(
            service_id=deployment.service_id,
            environment=deployment.environment,
            strategy=DeploymentStrategy.ROLLING,
            target_version=deployment.rollback_version,
            current_version=deployment.target_version
        )
        
        # Execute rollback
        await self.execute_deployment(rollback_deployment)
    
    async def _update_load_balancer(self):
        """Update load balancer configuration"""
        # Get all running services
        running_services = [
            service for service in self.services.values()
            if service.state == ServiceState.RUNNING
        ]
        
        # Update load balancer
        await self.load_balancer.update_configuration(running_services)
    
    async def deploy_service(self, service_id: str, version: str, environment: DeploymentEnvironment, strategy: DeploymentStrategy) -> str:
        """Deploy service"""
        if service_id not in self.services:
            raise ValueError(f"Service {service_id} not found")
        
        service = self.services[service_id]
        
        # Create deployment
        deployment = Deployment(
            service_id=service_id,
            environment=environment,
            strategy=strategy,
            target_version=version,
            current_version=service.version,
            rollback_version=service.version
        )
        
        # Execute deployment
        await self.execute_deployment(deployment)
        
        return deployment.id
    
    async def execute_deployment(self, deployment: Deployment):
        """Execute deployment"""
        try:
            # Add to active deployments
            self.active_deployments[deployment.id] = deployment
            self.deployments[deployment.id] = deployment
            
            # Start deployment
            deployment.start_deployment()
            
            # Get deployment strategy handler
            if deployment.strategy == DeploymentStrategy.ROLLING:
                await self._execute_rolling_deployment(deployment)
            elif deployment.strategy == DeploymentStrategy.BLUE_GREEN:
                await self._execute_blue_green_deployment(deployment)
            elif deployment.strategy == DeploymentStrategy.CANARY:
                await self._execute_canary_deployment(deployment)
            elif deployment.strategy == DeploymentStrategy.RECREATE:
                await self._execute_recreate_deployment(deployment)
            else:
                raise ValueError(f"Unknown deployment strategy: {deployment.strategy}")
            
            # Update service version
            service = self.services[deployment.service_id]
            service.version = deployment.target_version
            service.updated_at = datetime.now()
            
            deployment.complete_deployment()
            
        except Exception as e:
            deployment.fail_deployment(str(e))
            logger.error(f"Deployment {deployment.id} failed: {e}")
    
    async def _execute_rolling_deployment(self, deployment: Deployment):
        """Execute rolling deployment"""
        service = self.services[deployment.service_id]
        
        # Simulate rolling update
        for i in range(service.replicas):
            # Update one replica at a time
            deployment.add_log(f"Updating replica {i+1}/{service.replicas}")
            await asyncio.sleep(1)  # Simulate update time
            deployment.rollout_percent = ((i + 1) / service.replicas) * 100
    
    async def _execute_blue_green_deployment(self, deployment: Deployment):
        """Execute blue-green deployment"""
        # Deploy to green environment
        deployment.add_log("Deploying to green environment")
        await asyncio.sleep(2)  # Simulate deployment time
        
        # Switch traffic
        deployment.add_log("Switching traffic to green environment")
        await asyncio.sleep(1)  # Simulate traffic switch
        
        deployment.rollout_percent = 100
    
    async def _execute_canary_deployment(self, deployment: Deployment):
        """Execute canary deployment"""
        service = self.services[deployment.service_id]
        canary_replicas = max(1, service.replicas // 10)
        
        # Deploy canary
        deployment.add_log(f"Deploying canary with {canary_replicas} replicas")
        await asyncio.sleep(2)  # Simulate deployment time
        
        # Monitor canary
        deployment.add_log("Monitoring canary deployment")
        await asyncio.sleep(2)  # Simulate monitoring time
        
        # Promote if successful
        deployment.add_log("Promoting canary to full deployment")
        await asyncio.sleep(1)  # Simulate promotion time
        
        deployment.rollout_percent = 100
    
    async def _execute_recreate_deployment(self, deployment: Deployment):
        """Execute recreate deployment"""
        service = self.services[deployment.service_id]
        
        # Stop all replicas
        deployment.add_log("Stopping all replicas")
        await asyncio.sleep(1)  # Simulate stop time
        
        # Deploy new version
        deployment.add_log("Deploying new version")
        await asyncio.sleep(2)  # Simulate deployment time
        
        # Start all replicas
        deployment.add_log(f"Starting {service.replicas} replicas")
        await asyncio.sleep(1)  # Simulate start time
        
        deployment.rollout_percent = 100
    
    async def scale_service(self, service_id: str, target_replicas: int, reason: str = "") -> str:
        """Scale service"""
        if service_id not in self.services:
            raise ValueError(f"Service {service_id} not found")
        
        service = self.services[service_id]
        
        # Validate target replicas
        if target_replicas < service.min_replicas or target_replicas > service.max_replicas:
            raise ValueError(f"Target replicas {target_replicas} out of range [{service.min_replicas}, {service.max_replicas}]")
        
        # Create scaling event
        scaling_event = ScalingEvent(
            service_id=service_id,
            scaling_type="scale_out" if target_replicas > service.replicas else "scale_in",
            current_replicas=service.replicas,
            target_replicas=target_replicas,
            reason=reason or f"Manual scaling to {target_replicas} replicas"
        )
        
        self.scaling_events[scaling_event.id] = scaling_event
        
        try:
            # Update service state
            service.state = ServiceState.SCALING
            
            # Perform scaling
            await self._perform_scaling(service, target_replicas)
            
            # Update service
            old_replicas = service.replicas
            service.replicas = target_replicas
            service.state = ServiceState.RUNNING
            
            # Mark scaling event as completed
            scaling_event.completed = True
            
            logger.info(f"Scaled service {service.name} from {old_replicas} to {target_replicas} replicas")
            
            return scaling_event.id
            
        except Exception as e:
            scaling_event.error = str(e)
            service.state = ServiceState.ERROR
            logger.error(f"Failed to scale service {service_id}: {e}")
            raise
    
    async def _perform_scaling(self, service: Service, target_replicas: int):
        """Perform service scaling"""
        # This would integrate with container orchestrator
        # For now, simulate scaling
        logger.info(f"Scaling service {service.name} to {target_replicas} replicas")
        await asyncio.sleep(1)  # Simulate scaling time
    
    async def restart_service(self, service_id: str) -> bool:
        """Restart service"""
        if service_id not in self.services:
            return False
        
        service = self.services[service_id]
        
        try:
            logger.info(f"Restarting service {service.name}")
            
            # Stop service
            service.state = ServiceState.STOPPING
            await asyncio.sleep(1)  # Simulate stop time
            
            # Start service
            service.state = ServiceState.RUNNING
            await asyncio.sleep(1)  # Simulate start time
            
            logger.info(f"Service {service.name} restarted successfully")
            return True
            
        except Exception as e:
            service.state = ServiceState.ERROR
            logger.error(f"Failed to restart service {service_id}: {e}")
            return False
    
    def get_service_status(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service status"""
        if service_id not in self.services:
            return None
        
        service = self.services[service_id]
        
        return {
            "id": service.id,
            "name": service.name,
            "service_type": service.service_type,
            "version": service.version,
            "state": service.state.value,
            "replicas": service.replicas,
            "min_replicas": service.min_replicas,
            "max_replicas": service.max_replicas,
            "cpu_request": service.cpu_request,
            "cpu_limit": service.cpu_limit,
            "memory_request": service.memory_request,
            "memory_limit": service.memory_limit,
            "ports": service.ports,
            "health_check_path": service.health_check_path,
            "readiness_check_path": service.readiness_check_path,
            "created_at": service.created_at.isoformat(),
            "updated_at": service.updated_at.isoformat(),
            "is_healthy": service.is_healthy(),
            "needs_scaling": service.needs_scaling()
        }
    
    def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get deployment status"""
        if deployment_id not in self.deployments:
            return None
        
        deployment = self.deployments[deployment_id]
        
        return {
            "id": deployment.id,
            "service_id": deployment.service_id,
            "environment": deployment.environment.value,
            "strategy": deployment.strategy.value,
            "target_version": deployment.target_version,
            "current_version": deployment.current_version,
            "status": deployment.status,
            "rollout_percent": deployment.rollout_percent,
            "rollback_enabled": deployment.rollback_enabled,
            "rollback_version": deployment.rollback_version,
            "created_at": deployment.created_at.isoformat(),
            "started_at": deployment.started_at.isoformat() if deployment.started_at else None,
            "completed_at": deployment.completed_at.isoformat() if deployment.completed_at else None,
            "duration": deployment.duration,
            "error": deployment.error,
            "logs": deployment.logs[-10:]  # Last 10 logs
        }
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        total_services = len(self.services)
        running_services = sum(1 for s in self.services.values() if s.state == ServiceState.RUNNING)
        error_services = sum(1 for s in self.services.values() if s.state == ServiceState.ERROR)
        
        total_replicas = sum(s.replicas for s in self.services.values())
        
        return {
            "services": {
                "total": total_services,
                "running": running_services,
                "error": error_services,
                "total_replicas": total_replicas
            },
            "deployments": {
                "total": len(self.deployments),
                "active": len(self.active_deployments),
                "completed": sum(1 for d in self.deployments.values() if d.status == "completed"),
                "failed": sum(1 for d in self.deployments.values() if d.status == "failed")
            },
            "scaling": {
                "total_events": len(self.scaling_events),
                "completed": sum(1 for e in self.scaling_events.values() if e.completed),
                "failed": sum(1 for e in self.scaling_events.values() if e.error)
            },
            "monitoring": {
                "active": self.monitoring_active
            },
            "load_balancer": self.load_balancer.get_status(),
            "timestamp": datetime.now().isoformat()
        }


class LoadBalancer:
    """Load balancer for service management"""
    
    def __init__(self):
        self.services = {}
        self.backends = defaultdict(list)
        self.algorithms = {
            "round_robin": self._round_robin,
            "least_connections": self._least_connections,
            "weighted": self._weighted
        }
        self.current_algorithm = "round_robin"
        self.round_robin_index = defaultdict(int)
    
    async def update_configuration(self, services: List[Service]):
        """Update load balancer configuration"""
        self.services = {service.id: service for service in services}
        
        # Update backends
        for service in services:
            if service.state == ServiceState.RUNNING:
                # Add backends for each replica
                self.backends[service.id] = [
                    f"{service.name}-{i}" for i in range(service.replicas)
                ]
            else:
                # Remove backends for unhealthy service
                if service.id in self.backends:
                    del self.backends[service.id]
    
    def get_backend(self, service_id: str) -> Optional[str]:
        """Get backend for service using current algorithm"""
        if service_id not in self.backends or not self.backends[service_id]:
            return None
        
        algorithm = self.algorithms.get(self.current_algorithm)
        if algorithm:
            return algorithm(service_id)
        
        return None
    
    def _round_robin(self, service_id: str) -> str:
        """Round-robin load balancing"""
        backends = self.backends[service_id]
        backend = backends[self.round_robin_index[service_id] % len(backends)]
        self.round_robin_index[service_id] += 1
        return backend
    
    def _least_connections(self, service_id: str) -> str:
        """Least connections load balancing"""
        # For simplicity, return first backend
        backends = self.backends[service_id]
        return backends[0] if backends else None
    
    def _weighted(self, service_id: str) -> str:
        """Weighted load balancing"""
        # For simplicity, return first backend
        backends = self.backends[service_id]
        return backends[0] if backends else None
    
    def get_status(self) -> Dict[str, Any]:
        """Get load balancer status"""
        return {
            "algorithm": self.current_algorithm,
            "total_services": len(self.services),
            "total_backends": sum(len(backends) for backends in self.backends.values()),
            "services": {
                service_id: {
                    "backends": len(backends),
                    "algorithm": self.current_algorithm
                }
                for service_id, backends in self.backends.items()
            }
        }


# Global instance
_deployment_manager = None


def get_deployment_manager(project_root: str = str(Path(__file__).parent.parent)) -> DeploymentManager:
    """Get global deployment manager instance"""
    global _deployment_manager
    if _deployment_manager is None:
        _deployment_manager = DeploymentManager(project_root)
    return _deployment_manager


# Example usage
async def demo_deployment_manager():
    """Demonstrate deployment manager"""
    print("=== JARVIS Deployment Manager Demo ===")
    
    # Get deployment manager
    manager = get_deployment_manager()
    
    # Start monitoring
    await manager.start_monitoring()
    
    # Deploy a service
    service_id = list(manager.services.keys())[0]
    deployment_id = await manager.deploy_service(
        service_id,
        "1.1.0",
        DeploymentEnvironment.DEVELOPMENT,
        DeploymentStrategy.ROLLING
    )
    
    print(f"Started deployment: {deployment_id}")
    
    # Wait for deployment to complete
    await asyncio.sleep(5)
    
    # Get deployment status
    status = manager.get_deployment_status(deployment_id)
    print(f"Deployment status: {status['status'] if status else 'Not found'}")
    
    # Scale service
    service = manager.services[service_id]
    scaling_event_id = await manager.scale_service(
        service_id,
        service.replicas + 1,
        "Demo scaling"
    )
    
    print(f"Scaling event: {scaling_event_id}")
    
    # Get system status
    system_status = manager.get_system_status()
    print(f"System status: {system_status['services']}")
    
    # Stop monitoring
    await manager.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(demo_deployment_manager())
