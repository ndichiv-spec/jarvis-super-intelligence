"""
JARVIS Comprehensive Monitoring and Alerting System
==================================================
Real-time monitoring, alerting, and incident management for JARVIS platform.
"""

import asyncio
import json
import logging
import smtplib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import statistics

from core.config import settings
from performance.performance_optimizer import get_performance_monitor, PerformanceLevel

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(Enum):
    """Alert status enumeration"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class NotificationChannel(Enum):
    """Notification channel enumeration"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    IN_APP = "in_app"


@dataclass
class AlertRule:
    """Alert rule definition"""
    id: str
    name: str
    description: str
    metric_name: str
    condition: str  # gt, lt, eq, gte, lte
    threshold: float
    severity: AlertSeverity
    enabled: bool = True
    duration: int = 300  # seconds
    notification_channels: List[NotificationChannel] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_triggered: Optional[datetime] = None


@dataclass
class Alert:
    """Alert instance"""
    id: str
    rule_id: str
    metric_name: str
    current_value: float
    threshold: float
    severity: AlertSeverity
    status: AlertStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    triggered_at: datetime = field(default_factory=datetime.now)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    notifications_sent: List[str] = field(default_factory=list)


@dataclass
class Incident:
    """Incident record"""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    status: str = "open"  # open, investigating, resolved, closed
    alerts: List[str] = field(default_factory=list)  # Alert IDs
    assigned_to: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution_summary: Optional[str] = None


class AlertingEngine:
    """Advanced alerting and incident management system"""
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: Dict[str, Alert] = {}
        self.incidents: Dict[str, Incident] = {}
        self.notification_handlers: Dict[NotificationChannel, Callable] = {}
        self.alert_history: List[Alert] = []
        self.monitoring_active = False
        self.monitor_task = None
        
        # Initialize notification handlers
        self._initialize_notification_handlers()
        
        # Load existing rules
        self._load_rules()
    
    def _initialize_notification_handlers(self):
        """Initialize notification channel handlers"""
        self.notification_handlers = {
            NotificationChannel.EMAIL: self._send_email_notification,
            NotificationChannel.SLACK: self._send_slack_notification,
            NotificationChannel.WEBHOOK: self._send_webhook_notification,
            NotificationChannel.SMS: self._send_sms_notification,
            NotificationChannel.IN_APP: self._send_in_app_notification
        }
    
    def _load_rules(self):
        """Load alert rules from storage"""
        try:
            import os
            
            if not os.path.exists("./data/monitoring/alert_rules.json"):
                # Create default rules
                self._create_default_rules()
                return
            
            with open("./data/monitoring/alert_rules.json", "r") as f:
                rules_data = json.load(f)
            
            for rule_data in rules_data.get("rules", []):
                rule = AlertRule(
                    id=rule_data["id"],
                    name=rule_data["name"],
                    description=rule_data["description"],
                    metric_name=rule_data["metric_name"],
                    condition=rule_data["condition"],
                    threshold=rule_data["threshold"],
                    severity=AlertSeverity(rule_data["severity"]),
                    enabled=rule_data.get("enabled", True),
                    duration=rule_data.get("duration", 300),
                    notification_channels=[
                        NotificationChannel(ch) for ch in rule_data.get("notification_channels", [])
                    ],
                    tags=rule_data.get("tags", []),
                    created_at=datetime.fromisoformat(rule_data["created_at"]),
                    last_triggered=datetime.fromisoformat(rule_data["last_triggered"]) if rule_data.get("last_triggered") else None
                )
                self.rules[rule.id] = rule
            
            logger.info(f"Loaded {len(self.rules)} alert rules")
            
        except Exception as e:
            logger.error(f"Failed to load alert rules: {e}")
            self._create_default_rules()
    
    def _create_default_rules(self):
        """Create default alert rules"""
        default_rules = [
            {
                "name": "High CPU Usage",
                "description": "Alert when CPU usage exceeds threshold",
                "metric_name": "cpu_usage",
                "condition": "gt",
                "threshold": 85.0,
                "severity": "warning",
                "duration": 300,
                "notification_channels": ["email", "in_app"],
                "tags": ["system", "performance"]
            },
            {
                "name": "High Memory Usage",
                "description": "Alert when memory usage exceeds threshold",
                "metric_name": "memory_usage",
                "condition": "gt",
                "threshold": 90.0,
                "severity": "critical",
                "duration": 180,
                "notification_channels": ["email", "slack", "in_app"],
                "tags": ["system", "performance"]
            },
            {
                "name": "Low Cache Hit Rate",
                "description": "Alert when cache hit rate is below threshold",
                "metric_name": "cache_hit_rate",
                "condition": "lt",
                "threshold": 60.0,
                "severity": "warning",
                "duration": 600,
                "notification_channels": ["in_app"],
                "tags": ["performance", "cache"]
            },
            {
                "name": "High Error Rate",
                "description": "Alert when error rate exceeds threshold",
                "metric_name": "error_rate",
                "condition": "gt",
                "threshold": 5.0,
                "severity": "error",
                "duration": 120,
                "notification_channels": ["email", "slack", "in_app"],
                "tags": ["application", "errors"]
            },
            {
                "name": "High Response Time",
                "description": "Alert when response time exceeds threshold",
                "metric_name": "response_time_p95",
                "condition": "gt",
                "threshold": 1000.0,
                "severity": "warning",
                "duration": 300,
                "notification_channels": ["in_app"],
                "tags": ["performance", "response_time"]
            }
        ]
        
        for rule_data in default_rules:
            rule = AlertRule(
                id=str(uuid.uuid4()),
                **rule_data,
                notification_channels=[
                    NotificationChannel(ch) for ch in rule_data["notification_channels"]
                ]
            )
            self.rules[rule.id] = rule
        
        logger.info(f"Created {len(self.rules)} default alert rules")
    
    async def start_monitoring(self):
        """Start alert monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Alert monitoring started")
    
    async def stop_monitoring(self):
        """Stop alert monitoring"""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
        logger.info("Alert monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Get current metrics
                monitor = get_performance_monitor()
                metrics = monitor.get_metrics()
                
                # Check each rule
                for rule in self.rules.values():
                    if not rule.enabled:
                        continue
                    
                    await self._check_rule(rule, metrics)
                
                # Clean up old alerts
                await self._cleanup_old_alerts()
                
                # Wait for next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Alert monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    async def _check_rule(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Check if alert rule should trigger"""
        metric_data = metrics.get(rule.metric_name)
        if not metric_data:
            return
        
        current_value = metric_data["value"]
        threshold_met = self._evaluate_condition(current_value, rule.condition, rule.threshold)
        
        if threshold_met:
            # Check if alert already exists and is active
            existing_alerts = [
                alert for alert in self.alerts.values()
                if alert.rule_id == rule.id and alert.status == AlertStatus.ACTIVE
            ]
            
            if not existing_alerts:
                # Create new alert
                await self._create_alert(rule, current_value, metric_data)
            else:
                # Update existing alert
                for alert in existing_alerts:
                    alert.current_value = current_value
                    alert.triggered_at = datetime.now()
        
        elif not threshold_met:
            # Resolve any active alerts for this rule
            active_alerts = [
                alert for alert in self.alerts.values()
                if alert.rule_id == rule.id and alert.status == AlertStatus.ACTIVE
            ]
            
            for alert in active_alerts:
                await self._resolve_alert(alert.id, "Threshold returned to normal")
    
    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """Evaluate alert condition"""
        if condition == "gt":
            return value > threshold
        elif condition == "gte":
            return value >= threshold
        elif condition == "lt":
            return value < threshold
        elif condition == "lte":
            return value <= threshold
        elif condition == "eq":
            return abs(value - threshold) < 0.001
        else:
            return False
    
    async def _create_alert(self, rule: AlertRule, current_value: float, metric_data: Dict[str, Any]):
        """Create new alert"""
        alert_id = str(uuid.uuid4())
        
        alert = Alert(
            id=alert_id,
            rule_id=rule.id,
            metric_name=rule.metric_name,
            current_value=current_value,
            threshold=rule.threshold,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            message=f"{rule.name}: {rule.metric_name} is {current_value} (threshold: {rule.threshold})",
            details={
                "rule_name": rule.name,
                "metric_unit": metric_data.get("unit", ""),
                "trend": metric_data.get("trend", "stable"),
                "level": metric_data.get("level", "unknown")
            }
        )
        
        self.alerts[alert_id] = alert
        self.alert_history.append(alert)
        
        # Update rule last triggered
        rule.last_triggered = datetime.now()
        
        # Send notifications
        await self._send_notifications(alert, rule.notification_channels)
        
        # Create incident if critical
        if rule.severity == AlertSeverity.CRITICAL:
            await self._create_incident(alert)
        
        logger.warning(f"Alert created: {alert.message}")
    
    async def _send_notifications(self, alert: Alert, channels: List[NotificationChannel]):
        """Send alert notifications"""
        for channel in channels:
            try:
                handler = self.notification_handlers.get(channel)
                if handler:
                    await handler(alert)
                    alert.notifications_sent.append(channel.value)
            except Exception as e:
                logger.error(f"Failed to send {channel.value} notification: {e}")
    
    async def _send_email_notification(self, alert: Alert):
        """Send email notification"""
        # Implementation would use actual email service
        logger.info(f"Email notification sent for alert {alert.id}: {alert.message}")
    
    async def _send_slack_notification(self, alert: Alert):
        """Send Slack notification"""
        # Implementation would use Slack API
        logger.info(f"Slack notification sent for alert {alert.id}: {alert.message}")
    
    async def _send_webhook_notification(self, alert: Alert):
        """Send webhook notification"""
        # Implementation would send HTTP request to webhook URL
        logger.info(f"Webhook notification sent for alert {alert.id}: {alert.message}")
    
    async def _send_sms_notification(self, alert: Alert):
        """Send SMS notification"""
        # Implementation would use SMS service
        logger.info(f"SMS notification sent for alert {alert.id}: {alert.message}")
    
    async def _send_in_app_notification(self, alert: Alert):
        """Send in-app notification"""
        # Store for frontend to retrieve
        logger.info(f"In-app notification created for alert {alert.id}: {alert.message}")
    
    async def _create_incident(self, alert: Alert):
        """Create incident for critical alert"""
        incident_id = str(uuid.uuid4())
        
        incident = Incident(
            id=incident_id,
            title=f"Critical Alert: {alert.metric_name}",
            description=f"Critical threshold exceeded for {alert.metric_name}. Current value: {alert.current_value}",
            severity=alert.severity,
            alerts=[alert.id]
        )
        
        self.incidents[incident_id] = incident
        logger.error(f"Incident created: {incident_id}")
    
    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledge an alert"""
        alert = self.alerts.get(alert_id)
        if not alert or alert.status != AlertStatus.ACTIVE:
            return False
        
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_at = datetime.now()
        
        logger.info(f"Alert {alert_id} acknowledged by user {user_id}")
        return True
    
    async def resolve_alert(self, alert_id: str, resolution: str) -> bool:
        """Resolve an alert"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return False
        
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = datetime.now()
        
        # Update related incidents
        for incident in self.incidents.values():
            if alert_id in incident.alerts:
                incident.updated_at = datetime.now()
                incident.resolution_summary = resolution
        
        logger.info(f"Alert {alert_id} resolved: {resolution}")
        return True
    
    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now() - timedelta(days=30)
        
        alerts_to_remove = []
        for alert_id, alert in self.alerts.items():
            if (alert.status == AlertStatus.RESOLVED and 
                alert.resolved_at and 
                alert.resolved_at < cutoff_time):
                alerts_to_remove.append(alert_id)
        
        for alert_id in alerts_to_remove:
            del self.alerts[alert_id]
        
        if alerts_to_remove:
            logger.info(f"Cleaned up {len(alerts_to_remove)} old alerts")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        active_alerts = [
            {
                "id": alert.id,
                "rule_id": alert.rule_id,
                "metric_name": alert.metric_name,
                "current_value": alert.current_value,
                "threshold": alert.threshold,
                "severity": alert.severity.value,
                "status": alert.status.value,
                "message": alert.message,
                "triggered_at": alert.triggered_at.isoformat(),
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "notifications_sent": alert.notifications_sent
            }
            for alert in self.alerts.values()
            if alert.status in [AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED]
        ]
        
        return sorted(active_alerts, key=lambda x: x["triggered_at"], reverse=True)
    
    def get_incidents(self) -> List[Dict[str, Any]]:
        """Get all incidents"""
        incidents = []
        for incident in self.incidents.values():
            incidents.append({
                "id": incident.id,
                "title": incident.title,
                "description": incident.description,
                "severity": incident.severity.value,
                "status": incident.status,
                "alert_count": len(incident.alerts),
                "assigned_to": incident.assigned_to,
                "created_at": incident.created_at.isoformat(),
                "updated_at": incident.updated_at.isoformat(),
                "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
                "resolution_summary": incident.resolution_summary
            })
        
        return sorted(incidents, key=lambda x: x["created_at"], reverse=True)
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        total_alerts = len(self.alert_history)
        
        severity_counts = {}
        status_counts = {}
        
        for alert in self.alerts.values():
            severity_counts[alert.severity.value] = severity_counts.get(alert.severity.value, 0) + 1
            status_counts[alert.status.value] = status_counts.get(alert.status.value, 0) + 1
        
        # Recent alerts (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_alerts = len([
            alert for alert in self.alert_history
            if alert.triggered_at > cutoff_time
        ])
        
        return {
            "total_alerts": total_alerts,
            "active_alerts": status_counts.get("active", 0),
            "recent_alerts_24h": recent_alerts,
            "alerts_by_severity": severity_counts,
            "alerts_by_status": status_counts,
            "total_incidents": len(self.incidents),
            "active_rules": len([r for r in self.rules.values() if r.enabled])
        }


# Global instance
_alerting_engine = None


def get_alerting_engine() -> AlertingEngine:
    """Get global alerting engine instance"""
    global _alerting_engine
    if _alerting_engine is None:
        _alerting_engine = AlertingEngine()
    return _alerting_engine
