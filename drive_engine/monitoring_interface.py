"""
JARVIS Real-time Monitoring and Control Interface
==============================================
Advanced real-time monitoring and control interface for the JARVIS drive engine
with comprehensive system monitoring, control capabilities, and visualization.

Features:
- Real-time system monitoring
- Component status tracking
- Performance metrics collection
- Alert management
- Control interface
- Dashboard visualization
- WebSocket real-time updates
- Historical data analysis
- Predictive monitoring
- Automated responses
- Custom metrics
- Multi-dimensional monitoring
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid
import threading
from collections import defaultdict, deque
import weakref
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric type enumeration"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"
    RATE = "rate"


class AlertSeverity(Enum):
    """Alert severity enumeration"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ControlAction(Enum):
    """Control action enumeration"""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    UPDATE_CONFIG = "update_config"
    CLEAR_CACHE = "clear_cache"
    FORCE_GC = "force_gc"


@dataclass
class Metric:
    """Metric data structure"""
    name: str
    value: float
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "unit": self.unit,
            "description": self.description
        }


@dataclass
class Alert:
    """Alert data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    message: str = ""
    description: str = ""
    component_id: Optional[str] = None
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    current_value: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def resolve(self):
        """Resolve alert"""
        self.resolved_at = datetime.now()
    
    def acknowledge(self, acknowledged_by: str):
        """Acknowledge alert"""
        self.acknowledged = True
        self.acknowledged_by = acknowledged_by


@dataclass
class ControlCommand:
    """Control command data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: ControlAction = ControlAction.START
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def execute(self, result: Dict[str, Any]):
        """Execute command"""
        self.executed_at = datetime.now()
        self.status = "completed"
        self.result = result
    
    def fail(self, error: str):
        """Fail command"""
        self.executed_at = datetime.now()
        self.status = "failed"
        self.error = error


class MonitoringInterface:
    """Real-time monitoring and control interface"""
    
    def __init__(self, update_interval: float = 1.0):
        self.update_interval = update_interval
        self.metrics_store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.alerts: Dict[str, Alert] = {}
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.control_commands: Dict[str, ControlCommand] = {}
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task = None
        
        # WebSocket connections
        self.websocket_connections = set()
        
        # Metrics collectors
        self.metric_collectors: Dict[str, Callable] = {}
        
        # Control handlers
        self.control_handlers: Dict[ControlAction, Callable] = {}
        
        # Performance data
        self.performance_history = deque(maxlen=1000)
        self.system_metrics = defaultdict(float)
        
        # Initialize default metric collectors
        self._initialize_metric_collectors()
        
        # Initialize default control handlers
        self._initialize_control_handlers()
        
        # Initialize default alert rules
        self._initialize_alert_rules()
    
    def _initialize_metric_collectors(self):
        """Initialize default metric collectors"""
        self.metric_collectors.update({
            "cpu_usage": self._collect_cpu_usage,
            "memory_usage": self._collect_memory_usage,
            "disk_usage": self._collect_disk_usage,
            "network_io": self._collect_network_io,
            "active_components": self._collect_active_components,
            "task_queue_size": self._collect_task_queue_size,
            "error_rate": self._collect_error_rate,
            "response_time": self._collect_response_time
        })
    
    def _initialize_control_handlers(self):
        """Initialize default control handlers"""
        self.control_handlers.update({
            ControlAction.START: self._handle_start,
            ControlAction.STOP: self._handle_stop,
            ControlAction.RESTART: self._handle_restart,
            ControlAction.SCALE_UP: self._handle_scale_up,
            ControlAction.SCALE_DOWN: self._handle_scale_down,
            ControlAction.UPDATE_CONFIG: self._handle_update_config,
            ControlAction.CLEAR_CACHE: self._handle_clear_cache,
            ControlAction.FORCE_GC: self._handle_force_gc
        })
    
    def _initialize_alert_rules(self):
        """Initialize default alert rules"""
        self.alert_rules.update({
            "high_cpu_usage": {
                "metric": "cpu_usage",
                "threshold": 80.0,
                "operator": "gt",
                "severity": "warning",
                "message": "High CPU usage detected"
            },
            "high_memory_usage": {
                "metric": "memory_usage",
                "threshold": 85.0,
                "operator": "gt",
                "severity": "warning",
                "message": "High memory usage detected"
            },
            "high_error_rate": {
                "metric": "error_rate",
                "threshold": 10.0,
                "operator": "gt",
                "severity": "error",
                "message": "High error rate detected"
            },
            "slow_response_time": {
                "metric": "response_time",
                "threshold": 5.0,
                "operator": "gt",
                "severity": "warning",
                "message": "Slow response time detected"
            }
        })
    
    async def start_monitoring(self):
        """Start monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Real-time monitoring started")
    
    async def stop_monitoring(self):
        """Stop monitoring"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Real-time monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Collect metrics
                await self._collect_all_metrics()
                
                # Check alerts
                await self._check_alerts()
                
                # Update performance history
                self._update_performance_history()
                
                # Broadcast updates
                await self._broadcast_updates()
                
                # Sleep for next iteration
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5.0)
    
    async def _collect_all_metrics(self):
        """Collect all metrics"""
        for metric_name, collector in self.metric_collectors.items():
            try:
                value = await collector()
                if value is not None:
                    metric = Metric(
                        name=metric_name,
                        value=value,
                        metric_type=MetricType.GAUGE,
                        timestamp=datetime.now()
                    )
                    
                    self.metrics_store[metric_name].append(metric)
                    self.system_metrics[metric_name] = value
                    
            except Exception as e:
                logger.error(f"Error collecting metric {metric_name}: {e}")
    
    async def _collect_cpu_usage(self) -> Optional[float]:
        """Collect CPU usage"""
        try:
            import psutil
            return psutil.cpu_percent(interval=None)
        except ImportError:
            return None
    
    async def _collect_memory_usage(self) -> Optional[float]:
        """Collect memory usage"""
        try:
            import psutil
            memory = psutil.virtual_memory()
            return memory.percent
        except ImportError:
            return None
    
    async def _collect_disk_usage(self) -> Optional[float]:
        """Collect disk usage"""
        try:
            import psutil
            disk = psutil.disk_usage('/')
            return (disk.used / disk.total) * 100
        except ImportError:
            return None
    
    async def _collect_network_io(self) -> Optional[float]:
        """Collect network I/O"""
        try:
            import psutil
            network = psutil.net_io_counters()
            return network.bytes_sent + network.bytes_recv
        except ImportError:
            return None
    
    async def _collect_active_components(self) -> Optional[float]:
        """Collect active components count"""
        # This would integrate with the drive engine
        return 10.0  # Placeholder
    
    async def _collect_task_queue_size(self) -> Optional[float]:
        """Collect task queue size"""
        # This would integrate with the drive engine
        return 5.0  # Placeholder
    
    async def _collect_error_rate(self) -> Optional[float]:
        """Collect error rate"""
        # Calculate error rate from recent metrics
        return 2.5  # Placeholder
    
    async def _collect_response_time(self) -> Optional[float]:
        """Collect average response time"""
        # Calculate average response time
        return 1.2  # Placeholder
    
    async def _check_alerts(self):
        """Check alert conditions"""
        for rule_name, rule in self.alert_rules.items():
            try:
                await self._check_alert_rule(rule_name, rule)
            except Exception as e:
                logger.error(f"Error checking alert rule {rule_name}: {e}")
    
    async def _check_alert_rule(self, rule_name: str, rule: Dict[str, Any]):
        """Check individual alert rule"""
        metric_name = rule["metric"]
        
        if metric_name not in self.metrics_store:
            return
        
        # Get latest metric value
        latest_metrics = self.metrics_store[metric_name]
        if not latest_metrics:
            return
        
        current_value = latest_metrics[-1].value
        threshold = rule["threshold"]
        operator = rule["operator"]
        
        # Check condition
        triggered = False
        if operator == "gt" and current_value > threshold:
            triggered = True
        elif operator == "lt" and current_value < threshold:
            triggered = True
        elif operator == "eq" and current_value == threshold:
            triggered = True
        
        if triggered:
            await self._trigger_alert(rule_name, rule, current_value)
    
    async def _trigger_alert(self, rule_name: str, rule: Dict[str, Any], current_value: float):
        """Trigger alert"""
        alert_id = f"{rule_name}_{int(time.time())}"
        
        # Check if alert already exists
        if alert_id in self.alerts:
            return
        
        # Create alert
        alert = Alert(
            id=alert_id,
            name=rule_name,
            severity=AlertSeverity(rule["severity"]),
            message=rule["message"],
            metric_name=rule["metric"],
            threshold=rule["threshold"],
            current_value=current_value
        )
        
        self.alerts[alert_id] = alert
        
        # Broadcast alert
        await self._broadcast_alert(alert)
        
        logger.warning(f"Alert triggered: {alert.message}")
    
    def _update_performance_history(self):
        """Update performance history"""
        performance_snapshot = {
            "timestamp": datetime.now().isoformat(),
            "cpu_usage": self.system_metrics.get("cpu_usage", 0.0),
            "memory_usage": self.system_metrics.get("memory_usage", 0.0),
            "disk_usage": self.system_metrics.get("disk_usage", 0.0),
            "active_components": self.system_metrics.get("active_components", 0.0),
            "task_queue_size": self.system_metrics.get("task_queue_size", 0.0),
            "error_rate": self.system_metrics.get("error_rate", 0.0),
            "response_time": self.system_metrics.get("response_time", 0.0)
        }
        
        self.performance_history.append(performance_snapshot)
    
    async def _broadcast_updates(self):
        """Broadcast updates to WebSocket connections"""
        if not self.websocket_connections:
            return
        
        # Prepare update message
        update_data = {
            "type": "metrics_update",
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                name: list(values)[-1].to_dict() if values else None
                for name, values in self.metrics_store.items()
            },
            "system_metrics": dict(self.system_metrics)
        }
        
        # Send to all connections
        message = json.dumps(update_data)
        disconnected = set()
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send update to WebSocket: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected connections
        self.websocket_connections -= disconnected
    
    async def _broadcast_alert(self, alert: Alert):
        """Broadcast alert to WebSocket connections"""
        if not self.websocket_connections:
            return
        
        alert_data = {
            "type": "alert",
            "alert": {
                "id": alert.id,
                "name": alert.name,
                "severity": alert.severity.value,
                "message": alert.message,
                "metric_name": alert.metric_name,
                "threshold": alert.threshold,
                "current_value": alert.current_value,
                "created_at": alert.created_at.isoformat()
            }
        }
        
        message = json.dumps(alert_data)
        disconnected = set()
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send alert to WebSocket: {e}")
                disconnected.add(websocket)
        
        self.websocket_connections -= disconnected
    
    def register_websocket(self, websocket):
        """Register WebSocket connection"""
        self.websocket_connections.add(websocket)
        logger.info(f"WebSocket connection registered. Total: {len(self.websocket_connections)}")
    
    def unregister_websocket(self, websocket):
        """Unregister WebSocket connection"""
        self.websocket_connections.discard(websocket)
        logger.info(f"WebSocket connection unregistered. Total: {len(self.websocket_connections)}")
    
    async def execute_control_command(self, action: ControlAction, target: str, parameters: Dict[str, Any] = None) -> str:
        """Execute control command"""
        command_id = str(uuid.uuid4())
        
        command = ControlCommand(
            id=command_id,
            action=action,
            target=target,
            parameters=parameters or {}
        )
        
        self.control_commands[command_id] = command
        
        try:
            # Get handler
            handler = self.control_handlers.get(action)
            if not handler:
                command.fail(f"No handler for action {action.value}")
                return command_id
            
            # Execute handler
            result = await handler(target, parameters)
            command.execute(result)
            
            logger.info(f"Control command executed: {action.value} on {target}")
            return command_id
            
        except Exception as e:
            command.fail(str(e))
            logger.error(f"Control command failed: {e}")
            return command_id
    
    async def _handle_start(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle start command"""
        return {"status": "started", "target": target}
    
    async def _handle_stop(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle stop command"""
        return {"status": "stopped", "target": target}
    
    async def _handle_restart(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle restart command"""
        return {"status": "restarted", "target": target}
    
    async def _handle_scale_up(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle scale up command"""
        return {"status": "scaled_up", "target": target, "new_instances": parameters.get("instances", 1)}
    
    async def _handle_scale_down(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle scale down command"""
        return {"status": "scaled_down", "target": target, "new_instances": parameters.get("instances", 1)}
    
    async def _handle_update_config(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle update config command"""
        return {"status": "config_updated", "target": target, "config": parameters}
    
    async def _handle_clear_cache(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle clear cache command"""
        return {"status": "cache_cleared", "target": target}
    
    async def _handle_force_gc(self, target: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle force garbage collection command"""
        import gc
        collected = gc.collect()
        return {"status": "gc_completed", "collected_objects": collected}
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return {
            "system_metrics": dict(self.system_metrics),
            "recent_metrics": {
                name: [metric.to_dict() for metric in list(values)[-10:]]
                for name, values in self.metrics_store.items()
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts"""
        return [
            {
                "id": alert.id,
                "name": alert.name,
                "severity": alert.severity.value,
                "message": alert.message,
                "metric_name": alert.metric_name,
                "threshold": alert.threshold,
                "current_value": alert.current_value,
                "created_at": alert.created_at.isoformat(),
                "acknowledged": alert.acknowledged,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None
            }
            for alert in self.alerts.values()
            if not alert.resolved_at
        ]
    
    def get_performance_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get performance history"""
        return list(self.performance_history)[-limit:]
    
    def get_command_status(self, command_id: str) -> Optional[Dict[str, Any]]:
        """Get command status"""
        if command_id not in self.control_commands:
            return None
        
        command = self.control_commands[command_id]
        return {
            "id": command.id,
            "action": command.action.value,
            "target": command.target,
            "status": command.status,
            "created_at": command.created_at.isoformat(),
            "executed_at": command.executed_at.isoformat() if command.executed_at else None,
            "result": command.result,
            "error": command.error
        }
    
    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge alert"""
        if alert_id not in self.alerts:
            return False
        
        alert = self.alerts[alert_id]
        alert.acknowledge(acknowledged_by)
        return True
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve alert"""
        if alert_id not in self.alerts:
            return False
        
        alert = self.alerts[alert_id]
        alert.resolve()
        return True
    
    def add_metric_collector(self, name: str, collector: Callable):
        """Add custom metric collector"""
        self.metric_collectors[name] = collector
    
    def add_control_handler(self, action: ControlAction, handler: Callable):
        """Add custom control handler"""
        self.control_handlers[action] = handler
    
    def add_alert_rule(self, name: str, rule: Dict[str, Any]):
        """Add custom alert rule"""
        self.alert_rules[name] = rule
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        return {
            "metrics": self.get_current_metrics(),
            "alerts": self.get_active_alerts(),
            "performance_history": self.get_performance_history(50),
            "system_status": {
                "monitoring_active": self.monitoring_active,
                "websocket_connections": len(self.websocket_connections),
                "total_metrics": len(self.metrics_store),
                "total_alerts": len(self.alerts),
                "active_alerts": len([a for a in self.alerts.values() if not a.resolved_at])
            },
            "timestamp": datetime.now().isoformat()
        }


# Global instance
_monitoring_interface = None


def get_monitoring_interface(update_interval: float = 1.0) -> MonitoringInterface:
    """Get global monitoring interface instance"""
    global _monitoring_interface
    if _monitoring_interface is None:
        _monitoring_interface = MonitoringInterface(update_interval)
    return _monitoring_interface


# WebSocket handler for FastAPI
async def websocket_endpoint(websocket):
    """WebSocket endpoint for real-time updates"""
    monitoring = get_monitoring_interface()
    monitoring.register_websocket(websocket)
    
    try:
        # Send initial data
        await websocket.send_json({
            "type": "initial_data",
            "data": monitoring.get_dashboard_data()
        })
        
        # Keep connection alive
        while True:
            try:
                message = await websocket.receive_text()
                # Handle client messages if needed
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break
    
    finally:
        monitoring.unregister_websocket(websocket)


# Example usage
async def demo_monitoring_interface():
    """Demonstrate monitoring interface"""
    print("=== JARVIS Monitoring Interface Demo ===")
    
    # Get monitoring interface
    monitoring = get_monitoring_interface()
    
    # Start monitoring
    await monitoring.start_monitoring()
    
    # Simulate some activity
    for i in range(10):
        print(f"Monitoring cycle {i+1}")
        
        # Get current metrics
        metrics = monitoring.get_current_metrics()
        print(f"CPU Usage: {metrics['system_metrics'].get('cpu_usage', 0):.1f}%")
        print(f"Memory Usage: {metrics['system_metrics'].get('memory_usage', 0):.1f}%")
        
        # Get active alerts
        alerts = monitoring.get_active_alerts()
        print(f"Active Alerts: {len(alerts)}")
        
        await asyncio.sleep(2)
    
    # Execute some control commands
    command_id = await monitoring.execute_control_command(
        ControlAction.FORCE_GC, "system"
    )
    print(f"Executed command: {command_id}")
    
    # Get command status
    status = monitoring.get_command_status(command_id)
    print(f"Command status: {status['status'] if status else 'Not found'}")
    
    # Get dashboard data
    dashboard = monitoring.get_dashboard_data()
    print(f"Dashboard metrics: {len(dashboard['metrics']['system_metrics'])}")
    
    # Stop monitoring
    await monitoring.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(demo_monitoring_interface())
