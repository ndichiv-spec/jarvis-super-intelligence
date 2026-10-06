"""
JARVIS Advanced Analytics Dashboard Engine
=========================================
Real-time analytics and business intelligence for JARVIS platform.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import statistics

from core.config import settings

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric type enumeration"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class TimeRange(Enum):
    """Time range enumeration"""
    LAST_HOUR = "1h"
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"
    LAST_90_DAYS = "90d"
    CUSTOM = "custom"


@dataclass
class MetricDefinition:
    """Metric definition structure"""
    name: str
    type: MetricType
    description: str
    unit: str
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DataPoint:
    """Data point structure"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class DashboardWidget:
    """Dashboard widget structure"""
    id: str
    type: str  # chart, metric, table, etc.
    title: str
    query: str
    config: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, int] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class AnalyticsEngine:
    """Advanced analytics engine for JARVIS"""
    
    def __init__(self):
        self.metrics: Dict[str, MetricDefinition] = {}
        self.data_points: Dict[str, List[DataPoint]] = {}
        self.dashboards: Dict[str, List[DashboardWidget]] = {}
        self.real_time_subscribers: List[asyncio.Queue] = []
        
        # Initialize core metrics
        self._initialize_core_metrics()
        
        # Start data collection
        self.collection_running = False
        self.collection_task = None
    
    def _initialize_core_metrics(self):
        """Initialize core JARVIS metrics"""
        core_metrics = [
            ("api_requests_total", MetricType.COUNTER, "Total API requests", "requests"),
            ("api_response_time", MetricType.HISTOGRAM, "API response time", "ms"),
            ("active_users", MetricType.GAUGE, "Active users", "users"),
            ("conversations_total", MetricType.COUNTER, "Total conversations", "conversations"),
            ("tokens_used", MetricType.COUNTER, "Tokens used", "tokens"),
            ("agent_executions", MetricType.COUNTER, "Agent executions", "executions"),
            ("error_rate", MetricType.GAUGE, "Error rate", "percentage"),
            ("cpu_usage", MetricType.GAUGE, "CPU usage", "percentage"),
            ("memory_usage", MetricType.GAUGE, "Memory usage", "percentage"),
            ("database_connections", MetricType.GAUGE, "Database connections", "connections"),
        ]
        
        for name, metric_type, description, unit in core_metrics:
            self.metrics[name] = MetricDefinition(
                name=name,
                type=metric_type,
                description=description,
                unit=unit
            )
    
    async def start_collection(self):
        """Start real-time data collection"""
        if self.collection_running:
            return
        
        self.collection_running = True
        self.collection_task = asyncio.create_task(self._collection_loop())
        logger.info("Analytics collection started")
    
    async def stop_collection(self):
        """Stop real-time data collection"""
        self.collection_running = False
        if self.collection_task:
            self.collection_task.cancel()
        logger.info("Analytics collection stopped")
    
    async def _collection_loop(self):
        """Main collection loop"""
        while self.collection_running:
            try:
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Collect application metrics
                await self._collect_application_metrics()
                
                # Notify subscribers
                await self._notify_subscribers()
                
                # Wait for next collection
                await asyncio.sleep(30)  # Collect every 30 seconds
                
            except Exception as e:
                logger.error(f"Collection loop error: {e}")
                await asyncio.sleep(5)
    
    async def _collect_system_metrics(self):
        """Collect system-level metrics"""
        try:
            import psutil
            
            # CPU usage
            cpu_percent = psutil.cpu_percent()
            await self.record_metric("cpu_usage", cpu_percent, {"host": "server"})
            
            # Memory usage
            memory = psutil.virtual_memory()
            await self.record_metric("memory_usage", memory.percent, {"host": "server"})
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            await self.record_metric("disk_usage", disk_percent, {"host": "server", "mount": "/"})
            
        except ImportError:
            logger.warning("psutil not available for system metrics")
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
    
    async def _collect_application_metrics(self):
        """Collect application-level metrics"""
        try:
            # This would integrate with actual application metrics
            # For now, simulate some data
            
            # Active users (simulated)
            active_users = len(self.real_time_subscribers) + 10
            await self.record_metric("active_users", active_users)
            
            # API response time (simulated)
            response_time = statistics.normalvariate(150, 50)  # Mean 150ms, std 50ms
            await self.record_metric("api_response_time", max(0, response_time), {"endpoint": "/api/v1/enhanced"})
            
        except Exception as e:
            logger.error(f"Failed to collect application metrics: {e}")
    
    async def record_metric(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a metric data point"""
        if metric_name not in self.metrics:
            logger.warning(f"Unknown metric: {metric_name}")
            return
        
        data_point = DataPoint(
            timestamp=datetime.now(),
            value=value,
            labels=labels or {}
        )
        
        if metric_name not in self.data_points:
            self.data_points[metric_name] = []
        
        self.data_points[metric_name].append(data_point)
        
        # Keep only last 1000 points per metric
        if len(self.data_points[metric_name]) > 1000:
            self.data_points[metric_name] = self.data_points[metric_name][-1000:]
    
    async def query_metrics(
        self,
        metric_name: str,
        time_range: TimeRange = TimeRange.LAST_24_HOURS,
        aggregation: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Query metrics with time range and aggregation"""
        if metric_name not in self.metrics:
            raise ValueError(f"Unknown metric: {metric_name}")
        
        # Get time range
        end_time = datetime.now()
        start_time = self._get_start_time(end_time, time_range)
        
        # Filter data points
        data_points = self.data_points.get(metric_name, [])
        filtered_points = [
            dp for dp in data_points
            if start_time <= dp.timestamp <= end_time
            and (not labels or all(dp.labels.get(k) == v for k, v in labels.items()))
        ]
        
        if not filtered_points:
            return {
                "metric": metric_name,
                "time_range": time_range.value,
                "data": [],
                "aggregated": None
            }
        
        # Aggregate if requested
        if aggregation:
            aggregated_value = self._aggregate_data(filtered_points, aggregation)
            return {
                "metric": metric_name,
                "time_range": time_range.value,
                "data": [dp.timestamp.isoformat() for dp in filtered_points],
                "aggregated": {
                    "value": aggregated_value,
                    "method": aggregation
                }
            }
        
        return {
            "metric": metric_name,
            "time_range": time_range.value,
            "data": [
                {
                    "timestamp": dp.timestamp.isoformat(),
                    "value": dp.value,
                    "labels": dp.labels
                }
                for dp in filtered_points
            ],
            "aggregated": None
        }
    
    def _get_start_time(self, end_time: datetime, time_range: TimeRange) -> datetime:
        """Get start time for time range"""
        if time_range == TimeRange.LAST_HOUR:
            return end_time - timedelta(hours=1)
        elif time_range == TimeRange.LAST_24_HOURS:
            return end_time - timedelta(days=1)
        elif time_range == TimeRange.LAST_7_DAYS:
            return end_time - timedelta(days=7)
        elif time_range == TimeRange.LAST_30_DAYS:
            return end_time - timedelta(days=30)
        elif time_range == TimeRange.LAST_90_DAYS:
            return end_time - timedelta(days=90)
        else:
            return end_time - timedelta(days=1)  # Default to 24 hours
    
    def _aggregate_data(self, data_points: List[DataPoint], method: str) -> float:
        """Aggregate data points using specified method"""
        values = [dp.value for dp in data_points]
        
        if method == "avg":
            return statistics.mean(values)
        elif method == "sum":
            return sum(values)
        elif method == "min":
            return min(values)
        elif method == "max":
            return max(values)
        elif method == "count":
            return len(values)
        elif method == "p50":
            return statistics.median(values)
        elif method == "p95":
            return statistics.quantiles(values, n=20)[18] if len(values) >= 20 else max(values)
        else:
            return statistics.mean(values)  # Default to average
    
    async def create_dashboard(self, name: str, widgets: List[DashboardWidget]) -> str:
        """Create a new dashboard"""
        dashboard_id = str(uuid.uuid4())
        self.dashboards[dashboard_id] = widgets
        
        logger.info(f"Created dashboard: {name} ({dashboard_id})")
        return dashboard_id
    
    async def get_dashboard_data(self, dashboard_id: str) -> Dict[str, Any]:
        """Get all data for a dashboard"""
        widgets = self.dashboards.get(dashboard_id, [])
        dashboard_data = {}
        
        for widget in widgets:
            try:
                # Parse widget query and get data
                widget_data = await self._execute_widget_query(widget)
                dashboard_data[widget.id] = widget_data
            except Exception as e:
                logger.error(f"Failed to get data for widget {widget.id}: {e}")
                dashboard_data[widget.id] = {"error": str(e)}
        
        return {
            "dashboard_id": dashboard_id,
            "widgets": dashboard_data,
            "timestamp": datetime.now().isoformat()
        }
    
    async def _execute_widget_query(self, widget: DashboardWidget) -> Dict[str, Any]:
        """Execute widget query and return data"""
        # Parse query (simplified - in real implementation would use proper query language)
        query_parts = widget.query.split()
        
        if len(query_parts) < 2:
            raise ValueError("Invalid query format")
        
        metric_name = query_parts[0]
        time_range = TimeRange(query_parts[1]) if len(query_parts) > 1 else TimeRange.LAST_24_HOURS
        
        # Get metric data
        metric_data = await self.query_metrics(metric_name, time_range)
        
        # Apply widget-specific transformations
        if widget.type == "line_chart":
            return {
                "type": "line_chart",
                "data": metric_data["data"],
                "config": widget.config
            }
        elif widget.type == "metric":
            return {
                "type": "metric",
                "value": metric_data.get("aggregated", {}).get("value", 0),
                "config": widget.config
            }
        elif widget.type == "table":
            return {
                "type": "table",
                "data": metric_data["data"],
                "config": widget.config
            }
        else:
            return metric_data
    
    async def subscribe_to_real_time(self) -> asyncio.Queue:
        """Subscribe to real-time metric updates"""
        queue = asyncio.Queue(maxsize=100)
        self.real_time_subscribers.append(queue)
        return queue
    
    async def unsubscribe_from_real_time(self, queue: asyncio.Queue):
        """Unsubscribe from real-time updates"""
        if queue in self.real_time_subscribers:
            self.real_time_subscribers.remove(queue)
    
    async def _notify_subscribers(self):
        """Notify all subscribers of new data"""
        if not self.real_time_subscribers:
            return
        
        # Get latest data points
        latest_data = {}
        for metric_name, points in self.data_points.items():
            if points:
                latest_data[metric_name] = points[-1]
        
        # Send to subscribers
        for queue in self.real_time_subscribers:
            try:
                if not queue.full():
                    await queue.put({
                        "type": "metric_update",
                        "data": latest_data,
                        "timestamp": datetime.now().isoformat()
                    })
            except asyncio.QueueFull:
                # Remove slow subscribers
                self.real_time_subscribers.remove(queue)
    
    def get_metric_definitions(self) -> List[Dict[str, Any]]:
        """Get all metric definitions"""
        return [
            {
                "name": metric.name,
                "type": metric.type.value,
                "description": metric.description,
                "unit": metric.unit,
                "tags": metric.tags
            }
            for metric in self.metrics.values()
        ]
    
    async def get_analytics_summary(self) -> Dict[str, Any]:
        """Get analytics summary for dashboard"""
        summary = {}
        
        # Get key metrics for different time ranges
        key_metrics = [
            ("api_requests_total", TimeRange.LAST_24_HOURS),
            ("active_users", TimeRange.LAST_HOUR),
            ("api_response_time", TimeRange.LAST_24_HOURS),
            ("error_rate", TimeRange.LAST_24_HOURS),
            ("tokens_used", TimeRange.LAST_24_HOURS)
        ]
        
        for metric_name, time_range in key_metrics:
            try:
                data = await self.query_metrics(metric_name, time_range, "avg")
                summary[metric_name] = data.get("aggregated", {}).get("value", 0)
            except Exception as e:
                logger.warning(f"Failed to get metric {metric_name}: {e}")
                summary[metric_name] = 0
        
        return {
            "summary": summary,
            "timestamp": datetime.now().isoformat(),
            "collection_status": "running" if self.collection_running else "stopped"
        }


# Global instance
_analytics_engine = None


def get_analytics_engine() -> AnalyticsEngine:
    """Get global analytics engine instance"""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = AnalyticsEngine()
    return _analytics_engine
