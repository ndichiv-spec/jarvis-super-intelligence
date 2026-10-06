"""
JARVIS Real-time Monitoring System for Codebase Dashboard
====================================================
Real-time monitoring and updates system for JARVIS codebase dashboard
with live updates, change detection, and performance monitoring.

Features:
- Real-time file system monitoring
- Change detection and notifications
- Live metrics updates
- WebSocket-based real-time updates
- Performance monitoring
- Alert system
- Activity logging
- Health monitoring
- Auto-refresh capabilities
- Event-driven updates
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import hashlib
from pathlib import Path
import aiofiles
import aiohttp
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from collections import defaultdict, deque
import threading
import queue

logger = logging.getLogger(__name__)


class MonitorEventType(Enum):
    """Monitor event type enumeration"""
    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_MOVED = "file_moved"
    DIRECTORY_CREATED = "directory_created"
    DIRECTORY_MODIFIED = "directory_modified"
    DIRECTORY_DELETED = "directory_deleted"
    CODE_CHANGE = "code_change"
    METRICS_UPDATE = "metrics_update"
    SYSTEM_EVENT = "system_event"


class AlertSeverity(Enum):
    """Alert severity enumeration"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MonitorEvent:
    """Monitor event data structure"""
    event_id: str
    event_type: MonitorEventType
    timestamp: datetime
    file_path: str
    file_size: int = 0
    file_hash: Optional[str] = None
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    severity: AlertSeverity = AlertSeverity.INFO
    processed: bool = False
    acknowledged: bool = False


@dataclass
class SystemMetrics:
    """System metrics for monitoring"""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_io: float = 0.0
    file_count: int = 0
    directory_count: int = 0
    total_size: int = 0
    last_scan_time: Optional[datetime] = None
    scan_duration: float = 0.0
    error_count: int = 0
    warning_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class HealthStatus:
    """System health status"""
    overall_status: str = "healthy"
    components: Dict[str, str] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.now)
    uptime: float = 0.0
    response_time: float = 0.0
    error_rate: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class FileSystemEventHandler(FileSystemEventHandler):
    """File system event handler"""
    
    def __init__(self, monitor_callback):
        self.monitor_callback = monitor_callback
        super().__init__()
    
    def on_created(self, event):
        if not event.is_directory:
            asyncio.create_task(self.monitor_callback({
                'type': 'file_created',
                'path': event.src_path,
                'is_directory': event.is_directory
            }))
    
    def on_modified(self, event):
        if not event.is_directory:
            asyncio.create_task(self.monitor_callback({
                'type': 'file_modified',
                'path': event.src_path,
                'is_directory': event.is_directory
            }))
    
    def on_deleted(self, event):
        if not event.is_directory:
            asyncio.create_task(self.monitor_callback({
                'type': 'file_deleted',
                'path': event.src_path,
                'is_directory': event.is_directory
            }))
    
    def on_moved(self, event):
        if not event.is_directory:
            asyncio.create_task(self.monitor_callback({
                'type': 'file_moved',
                'path': event.src_path,
                'dest_path': event.dest_path,
                'is_directory': event.is_directory
            }))


class RealtimeMonitoringSystem:
    """Real-time monitoring system for JARVIS codebase"""
    
    def __init__(self, project_root: str = "c:\\Users\\Administrator\\Jarvis"):
        self.project_root = Path(project_root)
        self.monitoring_active = False
        
        # Event handling
        self.event_queue = asyncio.Queue()
        self.event_history: deque = deque(maxlen=1000)
        self.alerts: deque = deque(maxlen=100)
        
        # File system monitoring
        self.file_observer = None
        self.monitored_paths = []
        
        # WebSocket connections
        self.websocket_connections = set()
        
        # System metrics
        self.system_metrics = SystemMetrics()
        self.health_status = HealthStatus()
        
        # Monitoring configuration
        self.config = {
            'scan_interval': 30,  # seconds
            'max_file_size': 10 * 1024 * 1024,  # 10MB
            'excluded_patterns': [
                '*.pyc',
                '*.log',
                '*.tmp',
                '__pycache__',
                '.git',
                'node_modules',
                '.pytest_cache',
                '.mypy_cache'
            ],
            'alert_thresholds': {
                'error_rate': 0.1,  # 10%
                'response_time': 5.0,  # 5 seconds
                'disk_usage': 0.9,  # 90%
                'memory_usage': 0.8  # 80%
            }
        }
        
        # Performance tracking
        self.performance_stats = {
            'events_processed': 0,
            'average_processing_time': 0.0,
            'last_update': None,
            'uptime': 0.0
        }
        
        # Initialize monitoring
        self._initialize_monitoring()
    
    def _initialize_monitoring(self):
        """Initialize monitoring system"""
        try:
            # Create monitoring directories
            self.monitor_dir = Path("c:\\Users\\Administrator\\Jarvis\\logs\\monitoring")
            self.monitor_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info("Real-time monitoring system initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize monitoring: {e}")
    
    async def start_monitoring(self):
        """Start real-time monitoring"""
        try:
            if self.monitoring_active:
                logger.warning("Monitoring already active")
                return
            
            self.monitoring_active = True
            self.start_time = datetime.now()
            
            # Start file system monitoring
            await self._start_file_system_monitoring()
            
            # Start metrics collection
            await self._start_metrics_collection()
            
            # Start event processing
            await self._start_event_processing()
            
            # Start health monitoring
            await self._start_health_monitoring()
            
            logger.info("Real-time monitoring started")
            
        except Exception as e:
            logger.error(f"Failed to start monitoring: {e}")
            self.monitoring_active = False
    
    async def stop_monitoring(self):
        """Stop real-time monitoring"""
        try:
            if not self.monitoring_active:
                logger.warning("Monitoring not active")
                return
            
            self.monitoring_active = False
            
            # Stop file system monitoring
            if self.file_observer:
                self.file_observer.stop()
                self.file_observer = None
            
            logger.info("Real-time monitoring stopped")
            
        except Exception as e:
            logger.error(f"Failed to stop monitoring: {e}")
    
    async def _start_file_system_monitoring(self):
        """Start file system monitoring"""
        try:
            # Create event handler
            event_handler = FileSystemEventHandler(self._handle_file_system_event)
            
            # Create observer
            self.file_observer = Observer()
            
            # Add paths to monitor
            paths_to_monitor = [
                self.project_root / "core",
                self.project_root / "api",
                self.project_root / "web",
                self.project_root / "mobile",
                self.project_root / "dashboard",
                self.project_root / "tests",
                self.project_root / "scripts"
            ]
            
            for path in paths_to_monitor:
                if path.exists():
                    self.file_observer.schedule(event_handler, str(path), recursive=True)
                    self.monitored_paths.append(str(path))
            
            # Start observer
            self.file_observer.start()
            
            logger.info(f"File system monitoring started for {len(self.monitored_paths)} paths")
            
        except Exception as e:
            logger.error(f"Failed to start file system monitoring: {e}")
    
    async def _start_metrics_collection(self):
        """Start metrics collection"""
        try:
            while self.monitoring_active:
                await self._collect_system_metrics()
                await self._update_performance_stats()
                await asyncio.sleep(self.config['scan_interval'])
                
        except Exception as e:
            logger.error(f"Metrics collection error: {e}")
    
    async def _start_event_processing(self):
        """Start event processing"""
        try:
            while self.monitoring_active:
                try:
                    # Get event with timeout
                    event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                    await self._process_event(event)
                    
                except asyncio.TimeoutError:
                    # No events, continue
                    continue
                except Exception as e:
                    logger.error(f"Event processing error: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Event processing failed: {e}")
    
    async def _start_health_monitoring(self):
        """Start health monitoring"""
        try:
            while self.monitoring_active:
                await self._check_system_health()
                await asyncio.sleep(60)  # Check health every minute
                
        except Exception as e:
            logger.error(f"Health monitoring error: {e}")
    
    async def _handle_file_system_event(self, event_data: Dict[str, Any]):
        """Handle file system event"""
        try:
            event_type = event_data['type']
            file_path = Path(event_data['path'])
            
            # Skip excluded patterns
            if self._is_excluded_path(file_path):
                return
            
            # Create monitor event
            monitor_event = MonitorEvent(
                event_id=str(uuid.uuid4()),
                event_type=MonitorEventType(event_type),
                timestamp=datetime.now(),
                file_path=str(file_path),
                file_size=file_path.stat().st_size if file_path.exists() else 0,
                file_hash=await self._calculate_file_hash(file_path) if file_path.exists() else None,
                description=f"File {event_type.replace('_', ' ')}: {file_path.name}",
                details={
                    'file_extension': file_path.suffix,
                    'file_size': file_path.stat().st_size if file_path.exists() else 0,
                    'relative_path': str(file_path.relative_to(self.project_root))
                }
            )
            
            # Add to queue
            await self.event_queue.put(monitor_event)
            
        except Exception as e:
            logger.error(f"Failed to handle file system event: {e}")
    
    def _is_excluded_path(self, file_path: Path) -> bool:
        """Check if path should be excluded"""
        path_str = str(file_path)
        
        for pattern in self.config['excluded_patterns']:
            if pattern in path_str:
                return True
        
        return False
    
    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate file hash"""
        try:
            if file_path.stat().st_size > self.config['max_file_size']:
                return "large_file"
            
            hasher = hashlib.md5()
            async with aiofiles.open(file_path, 'rb') as f:
                async for chunk in f:
                    hasher.update(chunk)
                    if hasher.block_size * 1024 * 1024 > self.config['max_file_size']:
                        break
            
            return hasher.hexdigest()
            
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return "error"
    
    async def _process_event(self, event: MonitorEvent):
        """Process monitor event"""
        try:
            start_time = time.time()
            
            # Add to history
            self.event_history.append(event)
            
            # Check for alerts
            await self._check_event_alerts(event)
            
            # Notify WebSocket clients
            await self._notify_websocket_clients({
                'type': 'event',
                'data': {
                    'event_id': event.event_id,
                    'event_type': event.event_type.value,
                    'timestamp': event.timestamp.isoformat(),
                    'file_path': event.file_path,
                    'description': event.description,
                    'severity': event.severity.value
                }
            })
            
            # Update performance stats
            processing_time = time.time() - start_time
            self.performance_stats['events_processed'] += 1
            self.performance_stats['last_update'] = datetime.now()
            
            # Update average processing time
            total_events = self.performance_stats['events_processed']
            current_avg = self.performance_stats['average_processing_time']
            self.performance_stats['average_processing_time'] = ((current_avg * (total_events - 1)) + processing_time) / total_events
            
            # Mark as processed
            event.processed = True
            
        except Exception as e:
            logger.error(f"Failed to process event: {e}")
    
    async def _check_event_alerts(self, event: MonitorEvent):
        """Check if event should generate alert"""
        try:
            alerts = []
            
            # Check for error events
            if event.event_type == MonitorEventType.FILE_DELETED:
                alert = MonitorEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=MonitorEventType.SYSTEM_EVENT,
                    timestamp=datetime.now(),
                    file_path=event.file_path,
                    description=f"File deleted: {event.file_path}",
                    severity=AlertSeverity.WARNING,
                    details={'original_event': event.event_id}
                )
                alerts.append(alert)
            
            # Check for large files
            if event.file_size > 5 * 1024 * 1024:  # 5MB
                alert = MonitorEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=MonitorEventType.SYSTEM_EVENT,
                    timestamp=datetime.now(),
                    file_path=event.file_path,
                    description=f"Large file detected: {event.file_path} ({event.file_size / 1024 / 1024:.1f}MB)",
                    severity=AlertSeverity.INFO,
                    details={'file_size': event.file_size}
                )
                alerts.append(alert)
            
            # Add alerts to queue
            for alert in alerts:
                await self.event_queue.put(alert)
                self.alerts.append(alert)
            
        except Exception as e:
            logger.error(f"Failed to check event alerts: {e}")
    
    async def _collect_system_metrics(self):
        """Collect system metrics"""
        try:
            import psutil
            
            # CPU usage
            self.system_metrics.cpu_usage = psutil.cpu_percent()
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.system_metrics.memory_usage = memory.percent
            
            # Disk usage
            disk = psutil.disk_usage(str(self.project_root))
            self.system_metrics.disk_usage = (disk.used / disk.total) * 100
            
            # Network I/O
            network = psutil.net_io_counters()
            self.system_metrics.network_io = network.bytes_sent + network.bytes_recv
            
            # File system metrics
            self.system_metrics.file_count = len(list(self.project_root.rglob("*")))
            self.system_metrics.directory_count = len(list(self.project_root.rglob("*/")))
            self.system_metrics.total_size = sum(f.stat().st_size for f in self.project_root.rglob("*") if f.is_file())
            
            # Update timestamp
            self.system_metrics.timestamp = datetime.now()
            
            # Notify WebSocket clients
            await self._notify_websocket_clients({
                'type': 'metrics',
                'data': {
                    'cpu_usage': self.system_metrics.cpu_usage,
                    'memory_usage': self.system_metrics.memory_usage,
                    'disk_usage': self.system_metrics.disk_usage,
                    'file_count': self.system_metrics.file_count,
                    'directory_count': self.system_metrics.directory_count,
                    'total_size': self.system_metrics.total_size,
                    'timestamp': self.system_metrics.timestamp.isoformat()
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
    
    async def _update_performance_stats(self):
        """Update performance statistics"""
        try:
            if hasattr(self, 'start_time'):
                uptime = (datetime.now() - self.start_time).total_seconds()
                self.performance_stats['uptime'] = uptime
            
        except Exception as e:
            logger.error(f"Failed to update performance stats: {e}")
    
    async def _check_system_health(self):
        """Check system health"""
        try:
            components = {}
            warnings = []
            errors = []
            
            # Check file system health
            if self.system_metrics.disk_usage > self.config['alert_thresholds']['disk_usage']:
                warnings.append(f"High disk usage: {self.system_metrics.disk_usage:.1f}%")
                components['disk'] = 'warning'
            else:
                components['disk'] = 'healthy'
            
            # Check memory health
            if self.system_metrics.memory_usage > self.config['alert_thresholds']['memory_usage']:
                warnings.append(f"High memory usage: {self.system_metrics.memory_usage:.1f}%")
                components['memory'] = 'warning'
            else:
                components['memory'] = 'healthy'
            
            # Check CPU health
            if self.system_metrics.cpu_usage > 80:
                warnings.append(f"High CPU usage: {self.system_metrics.cpu_usage:.1f}%")
                components['cpu'] = 'warning'
            else:
                components['cpu'] = 'healthy'
            
            # Check monitoring health
            if not self.monitoring_active:
                errors.append("Monitoring system is not active")
                components['monitoring'] = 'error'
            else:
                components['monitoring'] = 'healthy'
            
            # Check file observer health
            if self.file_observer and not self.file_observer.is_alive():
                errors.append("File system observer is not running")
                components['file_observer'] = 'error'
            else:
                components['file_observer'] = 'healthy'
            
            # Determine overall status
            if errors:
                overall_status = 'critical'
            elif warnings:
                overall_status = 'warning'
            else:
                overall_status = 'healthy'
            
            # Update health status
            self.health_status = HealthStatus(
                overall_status=overall_status,
                components=components,
                last_check=datetime.now(),
                uptime=self.performance_stats.get('uptime', 0.0),
                response_time=self.performance_stats.get('average_processing_time', 0.0),
                error_rate=len(errors) / max(1, len(components)),
                warnings=warnings,
                errors=errors
            )
            
            # Notify WebSocket clients
            await self._notify_websocket_clients({
                'type': 'health',
                'data': {
                    'overall_status': overall_status,
                    'components': components,
                    'warnings': warnings,
                    'errors': errors,
                    'timestamp': self.health_status.last_check.isoformat()
                }
            })
            
        except Exception as e:
            logger.error(f"Failed to check system health: {e}")
    
    async def _notify_websocket_clients(self, message: Dict[str, Any]):
        """Notify all WebSocket clients"""
        if not self.websocket_connections:
            return
        
        # Create JSON message
        json_message = json.dumps(message)
        
        # Send to all connected clients
        disconnected_clients = set()
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(json_message)
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {e}")
                disconnected_clients.add(websocket)
        
        # Remove disconnected clients
        self.websocket_connections -= disconnected_clients
    
    def register_websocket(self, websocket):
        """Register WebSocket connection"""
        self.websocket_connections.add(websocket)
        logger.info(f"WebSocket connection registered. Total connections: {len(self.websocket_connections)}")
    
    def unregister_websocket(self, websocket):
        """Unregister WebSocket connection"""
        self.websocket_connections.discard(websocket)
        logger.info(f"WebSocket connection unregistered. Total connections: {len(self.websocket_connections)}")
    
    async def trigger_full_scan(self):
        """Trigger full codebase scan"""
        try:
            start_time = datetime.now()
            
            # Create scan event
            scan_event = MonitorEvent(
                event_id=str(uuid.uuid4()),
                event_type=MonitorEventType.SYSTEM_EVENT,
                timestamp=start_time,
                file_path=str(self.project_root),
                description="Full codebase scan triggered",
                severity=AlertSeverity.INFO,
                details={'triggered_by': 'user_request'}
            )
            
            await self.event_queue.put(scan_event)
            
            # Import and run documentation scan
            from dashboard.codebase_documentation import get_codebase_documentation_system
            doc_system = get_codebase_documentation_system()
            
            # Perform scan
            scan_result = await doc_system.scan_codebase(force=True)
            
            # Calculate scan duration
            scan_duration = (datetime.now() - start_time).total_seconds()
            
            # Update metrics
            self.system_metrics.last_scan_time = start_time
            self.system_metrics.scan_duration = scan_duration
            
            # Create completion event
            completion_event = MonitorEvent(
                event_id=str(uuid.uuid4()),
                event_type=MonitorEventType.SYSTEM_EVENT,
                timestamp=datetime.now(),
                file_path=str(self.project_root),
                description=f"Full codebase scan completed",
                severity=AlertSeverity.INFO,
                details={
                    'scan_result': scan_result,
                    'duration': scan_duration
                }
            )
            
            await self.event_queue.put(completion_event)
            
            # Notify clients
            await self._notify_websocket_clients({
                'type': 'scan_completed',
                'data': {
                    'scan_result': scan_result,
                    'duration': scan_duration,
                    'timestamp': datetime.now().isoformat()
                }
            })
            
            return scan_result
            
        except Exception as e:
            logger.error(f"Failed to trigger full scan: {e}")
            return {"status": "failed", "error": str(e)}
    
    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events"""
        try:
            recent_events = list(self.event_history)[-limit:]
            
            return [
                {
                    'event_id': event.event_id,
                    'event_type': event.event_type.value,
                    'timestamp': event.timestamp.isoformat(),
                    'file_path': event.file_path,
                    'description': event.description,
                    'severity': event.severity.value,
                    'processed': event.processed,
                    'acknowledged': event.acknowledged
                }
                for event in recent_events
            ]
            
        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent alerts"""
        try:
            recent_alerts = list(self.alerts)[-limit:]
            
            return [
                {
                    'event_id': alert.event_id,
                    'event_type': alert.event_type.value,
                    'timestamp': alert.timestamp.isoformat(),
                    'file_path': alert.file_path,
                    'description': alert.description,
                    'severity': alert.severity.value,
                    'details': alert.details
                }
                for alert in recent_alerts
            ]
            
        except Exception as e:
            logger.error(f"Failed to get recent alerts: {e}")
            return []
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            return {
                'monitoring_active': self.monitoring_active,
                'monitored_paths': self.monitored_paths,
                'system_metrics': {
                    'cpu_usage': self.system_metrics.cpu_usage,
                    'memory_usage': self.system_metrics.memory_usage,
                    'disk_usage': self.system_metrics.disk_usage,
                    'file_count': self.system_metrics.file_count,
                    'directory_count': self.system_metrics.directory_count,
                    'total_size': self.system_metrics.total_size,
                    'last_scan_time': self.system_metrics.last_scan_time.isoformat() if self.system_metrics.last_scan_time else None,
                    'scan_duration': self.system_metrics.scan_duration
                },
                'health_status': {
                    'overall_status': self.health_status.overall_status,
                    'components': self.health_status.components,
                    'last_check': self.health_status.last_check.isoformat(),
                    'uptime': self.health_status.uptime,
                    'response_time': self.health_status.response_time,
                    'error_rate': self.health_status.error_rate,
                    'warnings': self.health_status.warnings,
                    'errors': self.health_status.errors
                },
                'performance_stats': self.performance_stats,
                'websocket_connections': len(self.websocket_connections),
                'event_queue_size': self.event_queue.qsize(),
                'recent_events_count': len(self.event_history),
                'recent_alerts_count': len(self.alerts)
            }
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {"error": str(e)}
    
    def acknowledge_event(self, event_id: str) -> bool:
        """Acknowledge an event"""
        try:
            for event in self.event_history:
                if event.event_id == event_id:
                    event.acknowledged = True
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to acknowledge event {event_id}: {e}")
            return False
    
    def clear_events(self, older_than_hours: int = 24) -> int:
        """Clear old events and alerts"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            
            # Clear old events
            initial_event_count = len(self.event_history)
            self.event_history = deque(
                (event for event in self.event_history if event.timestamp > cutoff_time),
                maxlen=1000
            )
            cleared_events = initial_event_count - len(self.event_history)
            
            # Clear old alerts
            initial_alert_count = len(self.alerts)
            self.alerts = deque(
                (alert for alert in self.alerts if alert.timestamp > cutoff_time),
                maxlen=100
            )
            cleared_alerts = initial_alert_count - len(self.alerts)
            
            logger.info(f"Cleared {cleared_events} events and {cleared_alerts} alerts older than {older_than_hours} hours")
            
            return cleared_events + cleared_alerts
            
        except Exception as e:
            logger.error(f"Failed to clear events: {e}")
            return 0


# Global instance
_realtime_monitoring = None


def get_realtime_monitoring_system() -> RealtimeMonitoringSystem:
    """Get global real-time monitoring system instance"""
    global _realtime_monitoring
    if _realtime_monitoring is None:
        _realtime_monitoring = RealtimeMonitoringSystem()
    return _realtime_monitoring
