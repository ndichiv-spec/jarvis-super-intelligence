#!/usr/bin/env python3
"""
JARVIS Logging and Monitoring System
=====================================
Comprehensive logging, monitoring, and alerting system for JARVIS.
"""

import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import json
import traceback
from pathlib import Path
import asyncio
from collections import deque
import time

# Log levels
class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# Alert levels
class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: datetime
    level: LogLevel
    component: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "component": self.component,
            "message": self.message,
            "context": self.context,
            "exception": self.exception
        }

@dataclass
class Metric:
    """System metric"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels
        }

@dataclass
class Alert:
    """System alert"""
    id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "context": self.context
        }

class JARVISLogger:
    """Custom logger for JARVIS system"""
    
    def __init__(self, name: str, log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Configure logging
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        log_file = self.log_dir / f"{name}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # In-memory log storage
        self.log_entries: deque = deque(maxlen=1000)
    
    def log(self, level: LogLevel, component: str, message: str, 
            context: Optional[Dict[str, Any]] = None, exception: Optional[Exception] = None):
        """Log a message"""
        entry = LogEntry(
            timestamp=datetime.utcnow(),
            level=level,
            component=component,
            message=message,
            context=context or {},
            exception=traceback.format_exc() if exception else None
        )
        
        self.log_entries.append(entry)
        
        # Log to standard logger
        log_method = getattr(self.logger, level.value.lower())
        log_method(f"[{component}] {message}")
        
        if exception:
            self.logger.error(f"Exception: {traceback.format_exc()}")
    
    def debug(self, component: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogLevel.DEBUG, component, message, context)
    
    def info(self, component: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogLevel.INFO, component, message, context)
    
    def warning(self, component: str, message: str, context: Optional[Dict[str, Any]] = None):
        self.log(LogLevel.WARNING, component, message, context)
    
    def error(self, component: str, message: str, context: Optional[Dict[str, Any]] = None, 
              exception: Optional[Exception] = None):
        self.log(LogLevel.ERROR, component, message, context, exception)
    
    def critical(self, component: str, message: str, context: Optional[Dict[str, Any]] = None,
                exception: Optional[Exception] = None):
        self.log(LogLevel.CRITICAL, component, message, context, exception)
    
    def get_logs(self, level: Optional[LogLevel] = None, 
                 component: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get filtered logs"""
        filtered = self.log_entries
        
        if level:
            filtered = [e for e in filtered if e.level == level]
        
        if component:
            filtered = [e for e in filtered if e.component == component]
        
        return [e.to_dict() for e in list(filtered)[-limit:]]

class MetricsCollector:
    """Collect and store system metrics"""
    
    def __init__(self):
        self.metrics: deque = deque(maxlen=10000)
        self.metric_history: Dict[str, deque] = {}
    
    def record_metric(self, name: str, value: float, unit: str = "", 
                     labels: Optional[Dict[str, str]] = None):
        """Record a metric"""
        metric = Metric(
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.utcnow(),
            labels=labels or {}
        )
        
        self.metrics.append(metric)
        
        # Store in history
        if name not in self.metric_history:
            self.metric_history[name] = deque(maxlen=1000)
        self.metric_history[name].append(metric)
    
    def get_metric(self, name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get metric history"""
        if name not in self.metric_history:
            return []
        
        return [m.to_dict() for m in list(self.metric_history[name])[-limit:]]
    
    def get_latest_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the latest value for a metric"""
        if name not in self.metric_history or not self.metric_history[name]:
            return None
        
        return self.metric_history[name][-1].to_dict()
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all latest metrics"""
        result = {}
        for name in self.metric_history:
            latest = self.get_latest_metric(name)
            if latest:
                result[name] = latest
        return result

class AlertManager:
    """Manage system alerts"""
    
    def __init__(self):
        self.alerts: deque = deque(maxlen=1000)
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_rules: List[Dict[str, Any]] = []
    
    def add_alert_rule(self, name: str, condition: callable, level: AlertLevel, 
                      title: str, message_template: str):
        """Add an alert rule"""
        self.alert_rules.append({
            "name": name,
            "condition": condition,
            "level": level,
            "title": title,
            "message_template": message_template
        })
    
    def check_alerts(self, metrics: Dict[str, Any]):
        """Check alert conditions against metrics"""
        for rule in self.alert_rules:
            try:
                if rule["condition"](metrics):
                    alert_id = f"{rule['name']}_{int(time.time())}"
                    alert = Alert(
                        id=alert_id,
                        level=rule["level"],
                        title=rule["title"],
                        message=rule["message_template"].format(**metrics),
                        timestamp=datetime.utcnow(),
                        context=metrics.copy()
                    )
                    
                    self.alerts.append(alert)
                    self.active_alerts[alert_id] = alert
            except Exception as e:
                print(f"Error checking alert rule {rule['name']}: {e}")
    
    def create_alert(self, level: AlertLevel, title: str, message: str, 
                    context: Optional[Dict[str, Any]] = None) -> Alert:
        """Create a manual alert"""
        alert_id = f"manual_{int(time.time())}"
        alert = Alert(
            id=alert_id,
            level=level,
            title=title,
            message=message,
            timestamp=datetime.utcnow(),
            context=context or {}
        )
        
        self.alerts.append(alert)
        self.active_alerts[alert_id] = alert
        return alert
    
    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].resolved = True
            self.active_alerts[alert_id].resolved_at = datetime.utcnow()
            del self.active_alerts[alert_id]
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [alert.to_dict() for alert in self.active_alerts.values()]
    
    def get_all_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all alerts"""
        return [alert.to_dict() for alert in list(self.alerts)[-limit:]]

class MonitoringSystem:
    """Main monitoring system"""
    
    def __init__(self):
        self.logger = JARVISLogger("jarvis")
        self.metrics = MetricsCollector()
        self.alerts = AlertManager()
        self.start_time = datetime.utcnow()
        
        # Setup default alert rules
        self._setup_default_alerts()
    
    def _setup_default_alerts(self):
        """Setup default alert rules"""
        self.alerts.add_alert_rule(
            name="high_cpu",
            condition=lambda m: m.get("cpu_usage", 0) > 90,
            level=AlertLevel.WARNING,
            title="High CPU Usage",
            message_template="CPU usage is {cpu_usage}%"
        )
        
        self.alerts.add_alert_rule(
            name="high_memory",
            condition=lambda m: m.get("memory_usage", 0) > 90,
            level=AlertLevel.WARNING,
            title="High Memory Usage",
            message_template="Memory usage is {memory_usage}%"
        )
        
        self.alerts.add_alert_rule(
            name="high_error_rate",
            condition=lambda m: m.get("error_rate", 0) > 0.1,
            level=AlertLevel.ERROR,
            title="High Error Rate",
            message_template="Error rate is {error_rate}%"
        )
    
    def log_system_metrics(self, cpu_usage: float, memory_usage: float, 
                          disk_usage: float, error_rate: float = 0.0):
        """Log system metrics"""
        self.metrics.record_metric("cpu_usage", cpu_usage, "%")
        self.metrics.record_metric("memory_usage", memory_usage, "%")
        self.metrics.record_metric("disk_usage", disk_usage, "%")
        self.metrics.record_metric("error_rate", error_rate, "%")
        
        # Check alerts
        current_metrics = self.metrics.get_all_metrics()
        self.alerts.check_alerts(current_metrics)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        
        return {
            "status": "healthy",
            "uptime_seconds": uptime,
            "uptime_formatted": str(timedelta(seconds=int(uptime))),
            "metrics": self.metrics.get_all_metrics(),
            "active_alerts": len(self.alerts.get_active_alerts()),
            "total_alerts": len(self.alerts.alerts),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_monitoring_dashboard(self) -> Dict[str, Any]:
        """Get monitoring dashboard data"""
        return {
            "system_status": self.get_system_status(),
            "recent_logs": self.logger.get_logs(limit=50),
            "active_alerts": self.alerts.get_active_alerts(),
            "recent_alerts": self.alerts.get_all_alerts(limit=20),
            "metrics": self.metrics.get_all_metrics()
        }

# Create global monitoring system instance
monitoring = MonitoringSystem()

if __name__ == "__main__":
    # Test monitoring system
    print("Testing JARVIS Monitoring System...")
    
    # Log some messages
    monitoring.logger.info("System", "JARVIS monitoring system started")
    monitoring.logger.warning("System", "High CPU usage detected", {"cpu": 85})
    monitoring.logger.error("System", "Database connection failed", 
                           exception=Exception("Connection timeout"))
    
    # Record metrics
    monitoring.log_system_metrics(cpu_usage=45, memory_usage=62, disk_usage=38)
    monitoring.log_system_metrics(cpu_usage=92, memory_usage=88, disk_usage=40)
    
    # Check status
    print("\nSystem Status:")
    print(json.dumps(monitoring.get_system_status(), indent=2))
    
    print("\nMonitoring Dashboard:")
    print(json.dumps(monitoring.get_monitoring_dashboard(), indent=2))
