"""
JARVIS Comprehensive Monitoring and Alerting System
==================================================
Real-time monitoring, alerting, and incident management for JARVIS platform.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import smtplib
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request
import uuid

from performance.performance_optimizer import get_performance_monitor

logger = logging.getLogger(__name__)

# Simplified RFC-5322 email-address validator (sufficient for allow-list
# verification of alert recipients / sender).
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


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
    delivery_status: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_seen_at: Optional[datetime] = None
    occurrences: int = 1


class AlertDeliveryNotConfigured(RuntimeError):
    """Raised when a requested notification channel has no real receiver."""


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
        self.state_file = Path(
            os.environ.get("JARVIS_ALERT_STATE_FILE", "./data/monitoring/alert_state.json")
        )
        self.monitoring_active = False
        self.monitor_task = None
        
        # Initialize notification handlers
        self._initialize_notification_handlers()
        
        # Load existing rules
        self._load_rules()
        self._load_alert_state()
    
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
                "notification_channels": ["webhook", "in_app"],
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
                "notification_channels": ["webhook", "email", "in_app"],
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
                "notification_channels": ["webhook", "in_app"],
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
                "notification_channels": ["webhook", "email", "in_app"],
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
                "notification_channels": ["webhook", "in_app"],
                "tags": ["performance", "response_time"]
            }
        ]
        
        for rule_data in default_rules:
            rule_data["notification_channels"] = [
                NotificationChannel(channel)
                for channel in rule_data["notification_channels"]
            ]
            rule = AlertRule(
                id=str(uuid.uuid4()),
                **rule_data,
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
        existing = next(
            (
                item
                for item in self.alerts.values()
                if item.rule_id == rule.id
                and item.status in {AlertStatus.ACTIVE, AlertStatus.ACKNOWLEDGED}
            ),
            None,
        )
        if existing:
            existing.current_value = current_value
            existing.last_seen_at = datetime.now()
            existing.occurrences += 1
            existing.details.update({
                "metric_unit": metric_data.get("unit", ""),
                "trend": metric_data.get("trend", "stable"),
                "level": metric_data.get("level", "unknown"),
            })
            self._persist_alert_state()
            return

        alert_id = str(uuid.uuid4())
        triggered_at = datetime.now()
        
        alert = Alert(
            id=alert_id,
            rule_id=rule.id,
            metric_name=rule.metric_name,
            current_value=current_value,
            threshold=rule.threshold,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            message=f"{rule.name}: {rule.metric_name} is {current_value} (threshold: {rule.threshold})",
            triggered_at=triggered_at,
            last_seen_at=triggered_at,
            details={
                "rule_name": rule.name,
                "metric_unit": metric_data.get("unit", ""),
                "trend": metric_data.get("trend", "stable"),
                "level": metric_data.get("level", "unknown")
            }
        )
        
        self.alerts[alert_id] = alert
        self.alert_history.append(alert)
        self._persist_alert_state()
        
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
            delivery = alert.delivery_status.setdefault(
                channel.value,
                {"status": "pending", "attempts": 0, "updated_at": datetime.now().isoformat()},
            )
            try:
                handler = self.notification_handlers.get(channel)
                if handler:
                    await handler(alert)
                    if delivery.get("status") == "pending":
                        delivery.update(status="delivered", updated_at=datetime.now().isoformat())
                    if delivery.get("status") in ("delivered", "accepted") and channel.value not in alert.notifications_sent:
                        alert.notifications_sent.append(channel.value)
                else:
                    delivery.update(
                        status="not_configured",
                        error="ALERT_DELIVERY_NOT_CONFIGURED",
                        updated_at=datetime.now().isoformat(),
                    )
            except AlertDeliveryNotConfigured:
                delivery.update(
                    status="not_configured",
                    error="ALERT_DELIVERY_NOT_CONFIGURED",
                    updated_at=datetime.now().isoformat(),
                )
            except (ValueError, RuntimeError, URLError, TimeoutError, OSError) as error:
                # Preserve a terminal status the handler already set (e.g.
                # "failed" or "rejected") instead of clobbering it with a
                # generic "failed".  Only flip still-pending / delivering
                # states here.
                if delivery.get("status") in ("pending", "delivering"):
                    delivery.update(
                        status="failed",
                        error=type(error).__name__,
                        updated_at=datetime.now().isoformat(),
                    )
                logger.error("Alert delivery failed for %s (%s)", channel.value, type(error).__name__)
            self._persist_alert_state()

    async def _send_email_notification(self, alert: Alert):
        """Deliver an alert as a real email via SMTP.

        Credentials are read from environment variables (or a credential
        file) and are never logged or committed.  Recipients are restricted
        to the ``JARVIS_ALERT_EMAIL_TO`` allow-list.  Uses STARTTLS (or
        SMTP-SSL) with a 15 s timeout and 3 bounded retries, mirroring the
        webhook channel's delivery-state machine.

        Only ``accepted`` (SMTP server accepted the message) is claimed on
        success — end-to-end recipient delivery cannot be verified over SMTP.
        """
        host = os.environ.get("JARVIS_ALERT_EMAIL_SMTP_HOST", "").strip()
        port_str = os.environ.get("JARVIS_ALERT_EMAIL_SMTP_PORT", "").strip()
        user = os.environ.get("JARVIS_ALERT_EMAIL_SMTP_USER", "").strip()
        password = self._read_email_password()
        sender = os.environ.get("JARVIS_ALERT_EMAIL_FROM", "").strip() or user
        recipients_env = os.environ.get("JARVIS_ALERT_EMAIL_TO", "").strip()
        use_ssl = os.environ.get("JARVIS_ALERT_EMAIL_USE_SSL", "").lower() in {"1", "true", "yes"}

        if not host or not password or not sender or not recipients_env:
            raise AlertDeliveryNotConfigured("ALERT_DELIVERY_NOT_CONFIGURED")

        # --- validate sender --------------------------------------------------
        if not _EMAIL_RE.match(sender):
            raise ValueError("ALERT_EMAIL_FROM is not a valid email address")

        # --- validate port ----------------------------------------------------
        try:
            port = int(port_str) if port_str else 587
        except ValueError:
            raise ValueError("JARVIS_ALERT_EMAIL_SMTP_PORT is not a valid integer")
        if not 1 <= port <= 65535:
            raise ValueError("JARVIS_ALERT_EMAIL_SMTP_PORT is out of range")

        # --- validate recipient allow-list ------------------------------------
        allowed = [r.strip() for r in recipients_env.split(",") if r.strip()]
        for addr in allowed:
            if not _EMAIL_RE.match(addr):
                raise ValueError(
                    "ALERT_EMAIL_TO contains an invalid address — refusing to send"
                )

        # --- build the message ------------------------------------------------
        subject = (
            f"[JARVIS Alert] {alert.severity.value.upper()}: "
            f"{alert.metric_name} = {alert.current_value} "
            f"(threshold {alert.threshold})"
        )
        body = self._format_alert_email_body(alert)
        message = self._build_email_message(sender, allowed, subject, body)

        delivery = alert.delivery_status.setdefault("email", {})

        # --- duplicate-delivery protection ------------------------------------
        current_status = delivery.get("status")
        if current_status in ("accepted", "delivered"):
            logger.info(
                "Alert %s email already accepted/delivered — skipping duplicate",
                alert.id,
            )
            return

        # --- bounded retry loop (mirrors webhook pattern) ---------------------
        for attempt in range(1, 4):
            delivery.update(
                status="delivering",
                attempts=attempt,
                updated_at=datetime.now().isoformat(),
            )
            self._persist_alert_state()

            try:
                await asyncio.to_thread(
                    self._smtp_send_attempt,
                    host, port, user, password, sender, allowed, message, use_ssl,
                )
            except self._NON_RETRYABLE_SMTP_ERRORS as exc:
                delivery.update(
                    status="rejected",
                    error=type(exc).__name__,
                    smtp_response=str(getattr(exc, "smtp_error", exc))[:200],
                    attempts=attempt,
                    updated_at=datetime.now().isoformat(),
                )
                self._persist_alert_state()
                raise RuntimeError(str(exc)) from exc
            except (smtplib.SMTPException, OSError, TimeoutError) as exc:
                if attempt < 3:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))
                    continue
                delivery.update(
                    status="failed",
                    error=type(exc).__name__,
                    attempts=attempt,
                    error_detail=str(exc)[:200],
                    updated_at=datetime.now().isoformat(),
                )
                self._persist_alert_state()
                raise RuntimeError(f"SMTP send failed: {exc}") from exc

            # Success — SMTP server accepted the message.
            delivery.update(
                status="accepted",
                smtp_host=host,
                smtp_port=port,
                recipient_count=len(allowed),
                attempts=attempt,
                updated_at=datetime.now().isoformat(),
            )
            self._persist_alert_state()
            logger.info(
                "Alert %s email notification accepted by SMTP %s:%s",
                alert.id, host, port,
            )
            return

    async def _send_slack_notification(self, alert: Alert):
        raise AlertDeliveryNotConfigured("Slack alert delivery is not configured.")

    async def _send_webhook_notification(self, alert: Alert):
        """Deliver a signed JSON alert to a configured HTTPS webhook."""
        url = os.environ.get("JARVIS_ALERT_WEBHOOK_URL", "").strip()
        secret = self._read_webhook_secret()
        if not url or not secret:
            raise AlertDeliveryNotConfigured("ALERT_DELIVERY_NOT_CONFIGURED")
        if len(secret) < 32:
            raise ValueError("Alert webhook signing secret must be at least 32 characters.")

        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Alert webhook must be an HTTPS URL without embedded credentials.")

        body = json.dumps({
            "id": alert.id,
            "rule_id": alert.rule_id,
            "metric": alert.metric_name,
            "value": alert.current_value,
            "threshold": alert.threshold,
            "severity": alert.severity.value,
            "status": alert.status.value,
            "message": alert.message,
            "details": alert.details,
            "triggered_at": alert.triggered_at.isoformat(),
        }, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        delivery = alert.delivery_status.setdefault("webhook", {})

        for attempt in range(1, 4):
            delivery.update(
                status="delivering",
                attempts=attempt,
                updated_at=datetime.now().isoformat(),
            )
            self._persist_alert_state()
            request = Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Jarvis-Alert-Id": alert.id,
                    "X-Jarvis-Signature": f"sha256={signature}",
                },
                method="POST",
            )
            try:
                status_code = await asyncio.to_thread(self._post_webhook, request)
            except HTTPError as error:
                status_code = error.code
            except (URLError, TimeoutError, OSError) as error:
                if attempt == 3:
                    delivery.update(
                        status="failed",
                        error=type(error).__name__,
                        updated_at=datetime.now().isoformat(),
                    )
                    raise
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
                continue

            if 200 <= status_code < 300:
                delivery.update(
                    status="delivered",
                    http_status=status_code,
                    updated_at=datetime.now().isoformat(),
                )
                return
            if status_code < 500 and status_code != 429:
                delivery.update(
                    status="failed",
                    error="HTTP_ERROR",
                    http_status=status_code,
                    updated_at=datetime.now().isoformat(),
                )
                raise RuntimeError(f"Alert webhook returned HTTP {status_code}.")
            if attempt == 3:
                delivery.update(
                    status="failed",
                    error="HTTP_ERROR",
                    http_status=status_code,
                    updated_at=datetime.now().isoformat(),
                )
                raise RuntimeError(f"Alert webhook returned HTTP {status_code}.")
            await asyncio.sleep(min(2 ** (attempt - 1), 4))

    async def _send_sms_notification(self, alert: Alert):
        raise AlertDeliveryNotConfigured("SMS alert delivery is not configured.")

    async def _send_in_app_notification(self, alert: Alert):
        """Persist an in-app alert for retrieval by a configured application surface."""
        alert.delivery_status.setdefault("in_app", {}).update({
            "status": "stored",
            "updated_at": datetime.now().isoformat(),
        })
        self._persist_alert_state()

    @staticmethod
    def _post_webhook(request: Request) -> int:
        from urllib.request import HTTPRedirectHandler, build_opener

        class RejectRedirects(HTTPRedirectHandler):
            def redirect_request(self, request, response, code, message, headers, new_url):
                return None

        with build_opener(RejectRedirects()).open(request, timeout=10) as response:
            return response.status

    @staticmethod
    def _read_webhook_secret() -> str | None:
        secret = os.environ.get("JARVIS_ALERT_WEBHOOK_SECRET")
        if secret:
            return secret
        secret_file = os.environ.get("JARVIS_ALERT_WEBHOOK_SECRET_FILE")
        if secret_file:
            return Path(secret_file).read_text(encoding="utf-8").strip()
        return None

    # -------------------------------------------------------------------------
    # Email (SMTP) notification helpers
    # -------------------------------------------------------------------------
    _NON_RETRYABLE_SMTP_ERRORS = (
        smtplib.SMTPAuthenticationError,
        smtplib.SMTPRecipientsRefused,
        smtplib.SMTPSenderRefused,
    )

    @staticmethod
    def _read_email_password() -> str:
        """Read the SMTP password from env or a credential file.

        The value is never logged or persisted to alert state.  When
        ``JARVIS_ALERT_EMAIL_SMTP_PASSWORD`` is set it is used directly;
        otherwise ``JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE`` is read (a path
        to a file containing the password, e.g. a Docker/K8s secret mount).
        Returns an empty string when neither is available.
        """
        password = os.environ.get("JARVIS_ALERT_EMAIL_SMTP_PASSWORD", "").strip()
        if password:
            return password
        password_file = os.environ.get("JARVIS_ALERT_EMAIL_SMTP_PASSWORD_FILE")
        if password_file:
            try:
                return Path(password_file).read_text(encoding="utf-8").strip()
            except OSError:
                pass
        return ""

    @staticmethod
    def _build_email_message(sender: str, recipients: List[str],
                             subject: str, body: str) -> str:
        """Build a standards-compliant RFC-822 email message string."""
        from email.message import EmailMessage
        from email.utils import formatdate, make_msgid

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg["Date"] = formatdate()
        msg["Message-ID"] = make_msgid()
        msg.set_content(body)
        return msg.as_string()

    @staticmethod
    def _format_alert_email_body(alert: Alert) -> str:
        """Format the alert details as a plain-text email body."""
        details = (
            json.dumps(alert.details, sort_keys=True, indent=2)
            if alert.details else "{}"
        )
        return (
            "JARVIS Alert Notification\n"
            "==========================\n\n"
            f"Severity:    {alert.severity.value.upper()}\n"
            f"Rule:        {alert.rule_id}\n"
            f"Metric:      {alert.metric_name} = {alert.current_value}"
            f" (threshold: {alert.threshold})\n"
            f"Status:      {alert.status.value}\n"
            f"Message:     {alert.message}\n"
            f"Triggered:   {alert.triggered_at.isoformat()}\n"
            f"Occurrences: {alert.occurrences}\n\n"
            f"Details:\n{details}\n\n"
            "---\n"
            "This message was accepted by the SMTP server (JARVIS alerting).\n"
            "End-to-end recipient delivery is not verified over SMTP.\n"
        )

    @staticmethod
    def _smtp_send_attempt(
        host: str, port: int, user: str, password: str,
        sender: str, recipients: List[str], message: str, use_ssl: bool,
    ) -> None:
        """Perform a single SMTP send attempt.

        Raises ``smtplib.SMTPException`` or ``OSError`` on failure.
        Returns ``None`` on success (SMTP server accepted the message).
        """
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
        try:
            server.ehlo()
            if not use_ssl:
                try:
                    server.starttls()
                    server.ehlo()
                except smtplib.SMTPException:
                    # STARTTLS not supported — re-issue EHLO so esmtp_features
                    # is consistent before AUTH, matching smtp_connector.py.
                    try:
                        server.ehlo()
                    except smtplib.SMTPException:
                        pass
            if user and password:
                server.login(user, password)
            server.sendmail(sender, recipients, message)
        finally:
            try:
                server.quit()
            except Exception:
                pass

    def _load_alert_state(self) -> None:
        if not self.state_file.exists():
            return
        payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        alerts = []
        for item in payload.get("alerts", []):
            alert = Alert(
                id=item["id"],
                rule_id=item["rule_id"],
                metric_name=item["metric_name"],
                current_value=item["current_value"],
                threshold=item["threshold"],
                severity=AlertSeverity(item["severity"]),
                status=AlertStatus(item["status"]),
                message=item["message"],
                details=item.get("details", {}),
                triggered_at=datetime.fromisoformat(item["triggered_at"]),
                acknowledged_at=datetime.fromisoformat(item["acknowledged_at"]) if item.get("acknowledged_at") else None,
                resolved_at=datetime.fromisoformat(item["resolved_at"]) if item.get("resolved_at") else None,
                notifications_sent=item.get("notifications_sent", []),
                delivery_status=item.get("delivery_status", {}),
                last_seen_at=datetime.fromisoformat(item["last_seen_at"]) if item.get("last_seen_at") else None,
                occurrences=item.get("occurrences", 1),
            )
            alerts.append(alert)
        self.alerts = {alert.id: alert for alert in alerts}
        self.alert_history = list(alerts)

    def _persist_alert_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "alerts": [
                {
                    "id": alert.id,
                    "rule_id": alert.rule_id,
                    "metric_name": alert.metric_name,
                    "current_value": alert.current_value,
                    "threshold": alert.threshold,
                    "severity": alert.severity.value,
                    "status": alert.status.value,
                    "message": alert.message,
                    "details": alert.details,
                    "triggered_at": alert.triggered_at.isoformat(),
                    "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                    "notifications_sent": alert.notifications_sent,
                    "delivery_status": alert.delivery_status,
                    "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
                    "occurrences": alert.occurrences,
                }
                for alert in self.alert_history
            ]
        }
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.state_file.parent,
                prefix=f".{self.state_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(payload, temporary_file, separators=(",", ":"), sort_keys=True)
            os.replace(temporary_path, self.state_file)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
    
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
        self._persist_alert_state()
        
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
        self._persist_alert_state()
        
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
            self.alert_history = [
                alert for alert in self.alert_history if alert.id not in alerts_to_remove
            ]
            self._persist_alert_state()
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
                "notifications_sent": alert.notifications_sent,
                "delivery_status": alert.delivery_status,
                "occurrences": alert.occurrences,
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
