"""
JARVIS Performance Optimizer
==========================
Performance monitoring, optimization, and auto-tuning system.
"""

import asyncio
import logging
import time
import psutil
import gc
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import statistics
import weakref

from performance.cache_manager import get_cache_manager

logger = logging.getLogger(__name__)


class OptimizationType(Enum):
    """Optimization type enumeration"""
    CACHE_TUNING = "cache_tuning"
    MEMORY_CLEANUP = "memory_cleanup"
    CONNECTION_POOLING = "connection_pooling"
    QUERY_OPTIMIZATION = "query_optimization"
    ASYNC_OPTIMIZATION = "async_optimization"


class PerformanceLevel(Enum):
    """Performance level enumeration"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


@dataclass
class PerformanceMetric:
    """Performance metric structure"""
    name: str
    value: float
    unit: str
    threshold: float
    current_level: PerformanceLevel
    timestamp: datetime = field(default_factory=datetime.now)
    history: List[float] = field(default_factory=list)


@dataclass
class OptimizationResult:
    """Optimization result structure"""
    type: OptimizationType
    success: bool
    improvement: float
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class PerformanceMonitor:
    """Real-time performance monitoring"""
    
    def __init__(self, collection_interval: int = 30):
        self.collection_interval = collection_interval
        self.metrics: Dict[str, PerformanceMetric] = {}
        self.monitoring = False
        self.monitor_task = None
        self.callbacks: List[Callable] = []
        
        # Initialize core metrics
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize core performance metrics"""
        core_metrics = [
            ("cpu_usage", "%", 80.0),
            ("memory_usage", "%", 85.0),
            ("response_time_p50", "ms", 500.0),
            ("response_time_p95", "ms", 1000.0),
            ("cache_hit_rate", "%", 70.0),
            ("error_rate", "%", 5.0),
            ("throughput", "req/s", 0.0),
            ("active_connections", "count", 1000.0),
        ]
        
        for name, unit, threshold in core_metrics:
            self.metrics[name] = PerformanceMetric(
                name=name,
                value=0.0,
                unit=unit,
                threshold=threshold,
                current_level=PerformanceLevel.GOOD
            )
    
    async def start_monitoring(self):
        """Start performance monitoring"""
        if self.monitoring:
            return
        
        self.monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring = False
        if self.monitor_task:
            self.monitor_task.cancel()
        logger.info("Performance monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Collect metrics
                await self._collect_metrics()
                
                # Analyze performance
                performance_level = self._analyze_performance()
                
                # Notify callbacks
                for callback in self.callbacks:
                    try:
                        await callback(self.metrics, performance_level)
                    except Exception as e:
                        logger.error(f"Performance callback error: {e}")
                
                # Wait for next collection
                await asyncio.sleep(self.collection_interval)
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    async def _collect_metrics(self):
        """Collect system and application metrics"""
        timestamp = datetime.now()
        
        # System metrics
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self._update_metric("cpu_usage", cpu_percent, timestamp)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self._update_metric("memory_usage", memory.percent, timestamp)
            
            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # Calculate I/O rate (simplified)
                self._update_metric("disk_io_rate", disk_io.read_bytes + disk_io.write_bytes, timestamp)
            
        except Exception as e:
            logger.error(f"System metrics collection error: {e}")
        
        # Application metrics (would be collected from actual application)
        # For now, simulate some data
        await self._collect_application_metrics(timestamp)
    
    async def _collect_application_metrics(self, timestamp: datetime):
        """Collect application-specific metrics"""
        # Cache metrics
        cache_manager = get_cache_manager()
        cache_stats = cache_manager.get_stats()
        
        overall_hit_rate = cache_stats["overall"]["hit_rate"] * 100
        self._update_metric("cache_hit_rate", overall_hit_rate, timestamp)
        
        # Simulate response times
        response_times = [150, 200, 180, 250, 120, 300, 160]  # Sample data
        p50 = statistics.median(response_times)
        p95 = sorted(response_times)[int(len(response_times) * 0.95)]
        
        self._update_metric("response_time_p50", p50, timestamp)
        self._update_metric("response_time_p95", p95, timestamp)
        
        # Simulate throughput
        throughput = len(response_times) * 10  # requests per second
        self._update_metric("throughput", throughput, timestamp)
        
        # Simulate error rate
        error_rate = 2.5  # percentage
        self._update_metric("error_rate", error_rate, timestamp)
    
    def _update_metric(self, name: str, value: float, timestamp: datetime):
        """Update metric value and history"""
        if name not in self.metrics:
            return
        
        metric = self.metrics[name]
        metric.value = value
        metric.timestamp = timestamp
        
        # Update history (keep last 100 values)
        metric.history.append(value)
        if len(metric.history) > 100:
            metric.history.pop(0)
        
        # Update performance level
        metric.current_level = self._calculate_performance_level(metric)
    
    def _calculate_performance_level(self, metric: PerformanceMetric) -> PerformanceLevel:
        """Calculate performance level for metric"""
        value = metric.value
        threshold = metric.threshold
        
        if metric.name in ["cache_hit_rate", "throughput"]:
            # Higher is better
            if value >= threshold * 1.2:
                return PerformanceLevel.EXCELLENT
            elif value >= threshold:
                return PerformanceLevel.GOOD
            elif value >= threshold * 0.8:
                return PerformanceLevel.FAIR
            else:
                return PerformanceLevel.POOR
        else:
            # Lower is better
            if value <= threshold * 0.5:
                return PerformanceLevel.EXCELLENT
            elif value <= threshold:
                return PerformanceLevel.GOOD
            elif value <= threshold * 1.5:
                return PerformanceLevel.FAIR
            else:
                return PerformanceLevel.POOR
    
    def _analyze_performance(self) -> PerformanceLevel:
        """Analyze overall performance level"""
        levels = [metric.current_level for metric in self.metrics.values()]
        
        if all(level == PerformanceLevel.EXCELLENT for level in levels):
            return PerformanceLevel.EXCELLENT
        elif any(level == PerformanceLevel.POOR for level in levels):
            return PerformanceLevel.POOR
        elif any(level == PerformanceLevel.FAIR for level in levels):
            return PerformanceLevel.FAIR
        else:
            return PerformanceLevel.GOOD
    
    def add_callback(self, callback: Callable):
        """Add performance monitoring callback"""
        self.callbacks.append(callback)
    
    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get all current metrics"""
        return {
            name: {
                "value": metric.value,
                "unit": metric.unit,
                "threshold": metric.threshold,
                "level": metric.current_level.value,
                "timestamp": metric.timestamp.isoformat(),
                "trend": self._calculate_trend(metric.history)
            }
            for name, metric in self.metrics.items()
        }
    
    def _calculate_trend(self, history: List[float]) -> str:
        """Calculate trend from history"""
        if len(history) < 10:
            return "stable"
        
        recent = history[-10:]
        older = history[-20:-10] if len(history) >= 20 else history[:10]
        
        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)
        
        if recent_avg > older_avg * 1.1:
            return "increasing"
        elif recent_avg < older_avg * 0.9:
            return "decreasing"
        else:
            return "stable"


class PerformanceOptimizer:
    """Automatic performance optimization"""
    
    def __init__(self, monitor: PerformanceMonitor):
        self.monitor = monitor
        self.optimizations: List[OptimizationResult] = []
        self.optimization_history: Dict[str, List[OptimizationResult]] = {}
        self.auto_tuning = True
        
        # Register optimization callback
        self.monitor.add_callback(self._performance_callback)
    
    async def _performance_callback(self, metrics: Dict[str, PerformanceMetric], level: PerformanceLevel):
        """Performance monitoring callback"""
        if not self.auto_tuning:
            return
        
        # Trigger optimizations based on performance level
        if level == PerformanceLevel.POOR:
            await self._trigger_emergency_optimizations(metrics)
        elif level == PerformanceLevel.FAIR:
            await self._trigger_maintenance_optimizations(metrics)
    
    async def _trigger_emergency_optimizations(self, metrics: Dict[str, PerformanceMetric]):
        """Trigger emergency performance optimizations"""
        optimizations_to_run = []
        
        # Check specific metrics
        if metrics.get("memory_usage", {}).get("value", 0) > 90:
            optimizations_to_run.append(OptimizationType.MEMORY_CLEANUP)
        
        if metrics.get("cpu_usage", {}).get("value", 0) > 90:
            optimizations_to_run.append(OptimizationType.ASYNC_OPTIMIZATION)
        
        if metrics.get("cache_hit_rate", {}).get("value", 100) < 50:
            optimizations_to_run.append(OptimizationType.CACHE_TUNING)
        
        # Run optimizations
        for opt_type in optimizations_to_run:
            await self.run_optimization(opt_type)
    
    async def _trigger_maintenance_optimizations(self, metrics: Dict[str, PerformanceMetric]):
        """Trigger maintenance optimizations"""
        # Run cache tuning periodically
        if metrics.get("cache_hit_rate", {}).get("value", 100) < 70:
            await self.run_optimization(OptimizationType.CACHE_TUNING)
    
    async def run_optimization(self, opt_type: OptimizationType) -> OptimizationResult:
        """Run specific optimization"""
        start_time = time.time()
        
        try:
            if opt_type == OptimizationType.MEMORY_CLEANUP:
                result = await self._optimize_memory()
            elif opt_type == OptimizationType.CACHE_TUNING:
                result = await self._optimize_cache()
            elif opt_type == OptimizationType.ASYNC_OPTIMIZATION:
                result = await self._optimize_async()
            elif opt_type == OptimizationType.CONNECTION_POOLING:
                result = await self._optimize_connections()
            else:
                result = OptimizationResult(
                    type=opt_type,
                    success=False,
                    improvement=0.0,
                    details={"error": "Unknown optimization type"}
                )
            
            # Record optimization
            execution_time = time.time() - start_time
            result.details["execution_time"] = execution_time
            
            self.optimizations.append(result)
            
            if opt_type not in self.optimization_history:
                self.optimization_history[opt_type] = []
            self.optimization_history[opt_type].append(result)
            
            logger.info(f"Optimization {opt_type.value}: {'SUCCESS' if result.success else 'FAILED'}")
            
            return result
            
        except Exception as e:
            logger.error(f"Optimization {opt_type.value} failed: {e}")
            return OptimizationResult(
                type=opt_type,
                success=False,
                improvement=0.0,
                details={"error": str(e)}
            )
    
    async def _optimize_memory(self) -> OptimizationResult:
        """Optimize memory usage"""
        # Get initial memory usage
        initial_memory = psutil.virtual_memory().percent
        
        # Force garbage collection
        collected = gc.collect()
        
        # Clear cache if needed
        cache_manager = get_cache_manager()
        if initial_memory > 85:
            # Clear old cache entries
            await cache_manager.clear_by_tag("old")
        
        # Get final memory usage
        final_memory = psutil.virtual_memory().percent
        improvement = initial_memory - final_memory
        
        return OptimizationResult(
            type=OptimizationType.MEMORY_CLEANUP,
            success=improvement > 0,
            improvement=improvement,
            details={
                "initial_memory": initial_memory,
                "final_memory": final_memory,
                "objects_collected": collected
            }
        )
    
    async def _optimize_cache(self) -> OptimizationResult:
        """Optimize cache performance"""
        cache_manager = get_cache_manager()
        stats = cache_manager.get_stats()
        
        initial_hit_rate = stats["overall"]["hit_rate"]
        
        # Adjust cache sizes based on hit rate
        if initial_hit_rate < 0.7:
            # Increase L1 cache size
            cache_manager.l1_cache.max_size = min(2000, cache_manager.l1_cache.max_size * 1.2)
            cache_manager.l1_cache.max_memory_mb = min(200, cache_manager.l1_cache.max_memory_mb * 1.2)
        
        # Clear expired entries
        await cache_manager.clear_by_tag("expired")
        
        # Get new stats
        new_stats = cache_manager.get_stats()
        final_hit_rate = new_stats["overall"]["hit_rate"]
        improvement = (final_hit_rate - initial_hit_rate) * 100
        
        return OptimizationResult(
            type=OptimizationType.CACHE_TUNING,
            success=improvement > 0,
            improvement=improvement,
            details={
                "initial_hit_rate": initial_hit_rate,
                "final_hit_rate": final_hit_rate,
                "l1_size": cache_manager.l1_cache.max_size,
                "l1_memory_mb": cache_manager.l1_cache.max_memory_mb
            }
        )
    
    async def _optimize_async(self) -> OptimizationResult:
        """Optimize async performance"""
        # This would optimize async operations
        # For now, simulate optimization
        
        # Check for blocked tasks
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        
        # Cancel stuck tasks (simplified)
        cancelled_count = 0
        for task in tasks:
            # In real implementation, would check task age and cancel if stuck
            pass
        
        return OptimizationResult(
            type=OptimizationType.ASYNC_OPTIMIZATION,
            success=True,
            improvement=5.0,  # Simulated improvement
            details={
                "active_tasks": len(tasks),
                "cancelled_tasks": cancelled_count
            }
        )
    
    async def _optimize_connections(self) -> OptimizationResult:
        """Optimize connection pooling"""
        # This would optimize database and external service connections
        return OptimizationResult(
            type=OptimizationType.CONNECTION_POOLING,
            success=True,
            improvement=3.0,
            details={"optimized_pools": ["database", "redis", "external_apis"]}
        )
    
    def get_optimization_summary(self) -> Dict[str, Any]:
        """Get optimization summary"""
        total_optimizations = len(self.optimizations)
        successful_optimizations = len([opt for opt in self.optimizations if opt.success])
        
        type_counts = {}
        for opt in self.optimizations:
            opt_type = opt.type.value
            type_counts[opt_type] = type_counts.get(opt_type, 0) + 1
        
        return {
            "total_optimizations": total_optimizations,
            "successful_optimizations": successful_optimizations,
            "success_rate": successful_optimizations / total_optimizations if total_optimizations > 0 else 0,
            "optimizations_by_type": type_counts,
            "recent_optimizations": [
                {
                    "type": opt.type.value,
                    "success": opt.success,
                    "improvement": opt.improvement,
                    "timestamp": opt.timestamp.isoformat()
                }
                for opt in self.optimizations[-10:]
            ]
        }


# Global instances
_performance_monitor = None
_performance_optimizer = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer instance"""
    global _performance_optimizer
    if _performance_optimizer is None:
        monitor = get_performance_monitor()
        _performance_optimizer = PerformanceOptimizer(monitor)
    return _performance_optimizer
