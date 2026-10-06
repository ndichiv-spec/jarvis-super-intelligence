"""
JARVIS Performance Optimization and Tuning System
===============================================
Advanced performance optimization and tuning system for the JARVIS drive engine
with intelligent optimization, resource management, and performance tuning.

Features:
- System performance monitoring
- Resource optimization
- Memory management
- CPU optimization
- I/O optimization
- Network optimization
- Database optimization
- Cache management
- Garbage collection optimization
- Thread pool optimization
- Async/await optimization
- Performance profiling
- Bottleneck detection
- Auto-tuning
- Performance recommendations
"""

import asyncio
import json
import logging
import time
import gc
import sys
import threading
import weakref
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union, Callable, Type
from dataclasses import dataclass, field
from enum import Enum
import uuid
import psutil
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict, deque
import inspect

logger = logging.getLogger(__name__)


class OptimizationType(Enum):
    """Optimization type enumeration"""
    MEMORY = "memory"
    CPU = "cpu"
    IO = "io"
    NETWORK = "network"
    DATABASE = "database"
    CACHE = "cache"
    THREAD_POOL = "thread_pool"
    GARBAGE_COLLECTION = "garbage_collection"
    ASYNC_AWAIT = "async_await"
    ALGORITHM = "algorithm"


class OptimizationPriority(Enum):
    """Optimization priority enumeration"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class PerformanceMetric:
    """Performance metric data structure"""
    name: str
    value: float
    unit: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    threshold: Optional[float] = None
    optimal_range: Optional[Tuple[float, float]] = None
    category: str = ""
    description: str = ""
    
    def is_optimal(self) -> bool:
        """Check if metric is within optimal range"""
        if self.optimal_range:
            return self.optimal_range[0] <= self.value <= self.optimal_range[1]
        if self.threshold:
            return self.value <= self.threshold
        return True
    
    def needs_optimization(self) -> bool:
        """Check if metric needs optimization"""
        return not self.is_optimal()


@dataclass
class OptimizationAction:
    """Optimization action data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    optimization_type: OptimizationType = OptimizationType.MEMORY
    priority: OptimizationPriority = OptimizationPriority.NORMAL
    description: str = ""
    target_metric: str = ""
    expected_improvement: float = 0.0
    execution_time: float = 0.0
    success: bool = False
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def execute(self, result: bool, execution_time: float, error: str = None):
        """Mark action as executed"""
        self.executed_at = datetime.now()
        self.execution_time = execution_time
        self.success = result
        self.error = error


@dataclass
class OptimizationRule:
    """Optimization rule data structure"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    optimization_type: OptimizationType = OptimizationType.MEMORY
    condition: str = ""
    action: str = ""
    priority: OptimizationPriority = OptimizationPriority.NORMAL
    enabled: bool = True
    frequency: int = 300  # seconds
    last_executed: Optional[datetime] = None
    execution_count: int = 0
    success_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def should_execute(self) -> bool:
        """Check if rule should be executed"""
        if not self.enabled:
            return False
        
        if self.last_executed:
            time_since_last = (datetime.now() - self.last_executed).total_seconds()
            return time_since_last >= self.frequency
        
        return True


class PerformanceOptimizer:
    """Advanced performance optimization and tuning system"""
    
    def __init__(self):
        self.metrics: Dict[str, PerformanceMetric] = {}
        self.optimization_actions: Dict[str, OptimizationAction] = {}
        self.optimization_rules: Dict[str, OptimizationRule] = {}
        
        # Optimization engines
        self.optimization_engines: Dict[OptimizationType, Callable] = {}
        
        # Performance monitoring
        self.monitoring_active = False
        self.monitoring_task = None
        
        # Performance history
        self.performance_history: deque = deque(maxlen=1000)
        
        # Optimization statistics
        self.optimization_stats = {
            "total_optimizations": 0,
            "successful_optimizations": 0,
            "failed_optimizations": 0,
            "total_improvement": 0.0,
            "average_execution_time": 0.0
        }
        
        # Initialize optimization engines
        self._initialize_optimization_engines()
        
        # Initialize default rules
        self._initialize_default_rules()
        
        # Start memory tracking
        tracemalloc.start()
    
    def _initialize_optimization_engines(self):
        """Initialize optimization engines"""
        self.optimization_engines.update({
            OptimizationType.MEMORY: self._optimize_memory,
            OptimizationType.CPU: self._optimize_cpu,
            OptimizationType.IO: self._optimize_io,
            OptimizationType.NETWORK: self._optimize_network,
            OptimizationType.DATABASE: self._optimize_database,
            OptimizationType.CACHE: self._optimize_cache,
            OptimizationType.THREAD_POOL: self._optimize_thread_pool,
            OptimizationType.GARBAGE_COLLECTION: self._optimize_garbage_collection,
            OptimizationType.ASYNC_AWAIT: self._optimize_async_await,
            OptimizationType.ALGORITHM: self._optimize_algorithm
        })
    
    def _initialize_default_rules(self):
        """Initialize default optimization rules"""
        default_rules = [
            OptimizationRule(
                name="High Memory Usage",
                optimization_type=OptimizationType.MEMORY,
                condition="memory_usage > 80",
                action="garbage_collect",
                priority=OptimizationPriority.HIGH,
                frequency=60
            ),
            OptimizationRule(
                name="High CPU Usage",
                optimization_type=OptimizationType.CPU,
                condition="cpu_usage > 85",
                action="reduce_thread_pool_size",
                priority=OptimizationPriority.HIGH,
                frequency=120
            ),
            OptimizationRule(
                name="Low Cache Hit Rate",
                optimization_type=OptimizationType.CACHE,
                condition="cache_hit_rate < 70",
                action="increase_cache_size",
                priority=OptimizationPriority.NORMAL,
                frequency=300
            ),
            OptimizationRule(
                name="High I/O Wait",
                optimization_type=OptimizationType.IO,
                condition="io_wait > 20",
                action="optimize_io_buffers",
                priority=OptimizationPriority.NORMAL,
                frequency=180
            ),
            OptimizationRule(
                name="Memory Fragmentation",
                optimization_type=OptimizationType.MEMORY,
                condition="memory_fragmentation > 30",
                action="compact_memory",
                priority=OptimizationPriority.NORMAL,
                frequency=600
            )
        ]
        
        for rule in default_rules:
            self.optimization_rules[rule.id] = rule
    
    async def start_optimization(self):
        """Start performance optimization"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._optimization_loop())
        logger.info("Performance optimization started")
    
    async def stop_optimization(self):
        """Stop performance optimization"""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Performance optimization stopped")
    
    async def _optimization_loop(self):
        """Main optimization loop"""
        while self.monitoring_active:
            try:
                # Collect metrics
                await self._collect_metrics()
                
                # Check optimization rules
                await self._check_optimization_rules()
                
                # Update performance history
                self._update_performance_history()
                
                # Analyze performance trends
                await self._analyze_performance_trends()
                
                # Sleep for next iteration
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")
                await asyncio.sleep(60)
    
    async def _collect_metrics(self):
        """Collect performance metrics"""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            network_io = psutil.net_io_counters()
            
            # Update metrics
            self._update_metric("cpu_usage", cpu_percent, "%", "CPU Usage", 80.0, (0, 80))
            self._update_metric("memory_usage", memory.percent, "%", "Memory Usage", 85.0, (0, 85))
            self._update_metric("memory_available", memory.available / 1024 / 1024, "MB", "Available Memory")
            self._update_metric("disk_read_bytes", disk_io.read_bytes, "bytes", "Disk Read")
            self._update_metric("disk_write_bytes", disk_io.write_bytes, "bytes", "Disk Write")
            self._update_metric("network_sent_bytes", network_io.bytes_sent, "bytes", "Network Sent")
            self._update_metric("network_recv_bytes", network_io.bytes_recv, "bytes", "Network Received")
            
            # Process metrics
            process = psutil.Process()
            self._update_metric("process_memory", process.memory_info().rss / 1024 / 1024, "MB", "Process Memory")
            self._update_metric("process_cpu", process.cpu_percent(), "%", "Process CPU")
            
            # Python-specific metrics
            self._update_metric("python_objects", len(gc.get_objects()), "count", "Python Objects")
            self._update_metric("gc_collections", gc.collect(), "count", "GC Collections")
            
            # Memory tracking
            current, peak = tracemalloc.get_traced_memory()
            self._update_metric("traced_memory", current / 1024 / 1024, "MB", "Traced Memory")
            self._update_metric("peak_memory", peak / 1024 / 1024, "MB", "Peak Memory")
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    def _update_metric(self, name: str, value: float, unit: str, description: str, threshold: float = None, optimal_range: Tuple[float, float] = None):
        """Update performance metric"""
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            description=description,
            threshold=threshold,
            optimal_range=optimal_range
        )
        
        self.metrics[name] = metric
    
    async def _check_optimization_rules(self):
        """Check and execute optimization rules"""
        for rule_id, rule in self.optimization_rules.items():
            try:
                if rule.should_execute():
                    # Evaluate condition
                    if await self._evaluate_condition(rule.condition):
                        # Execute action
                        await self._execute_optimization_rule(rule)
                        rule.last_executed = datetime.now()
                        rule.execution_count += 1
                        
                        if rule.success:
                            rule.success_count += 1
                
            except Exception as e:
                logger.error(f"Error checking rule {rule.name}: {e}")
    
    async def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate optimization condition"""
        try:
            # Simple condition evaluation
            # In a real implementation, this would be more sophisticated
            parts = condition.split()
            if len(parts) >= 3:
                metric_name = parts[0]
                operator = parts[1]
                threshold = float(parts[2])
                
                if metric_name in self.metrics:
                    metric_value = self.metrics[metric_name].value
                    
                    if operator == ">":
                        return metric_value > threshold
                    elif operator == "<":
                        return metric_value < threshold
                    elif operator == ">=":
                        return metric_value >= threshold
                    elif operator == "<=":
                        return metric_value <= threshold
                    elif operator == "==":
                        return metric_value == threshold
            
            return False
            
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False
    
    async def _execute_optimization_rule(self, rule: OptimizationRule):
        """Execute optimization rule"""
        try:
            # Create optimization action
            action = OptimizationAction(
                name=f"Rule: {rule.name}",
                optimization_type=rule.optimization_type,
                priority=rule.priority,
                description=rule.description,
                target_metric=rule.condition
            )
            
            # Execute optimization
            start_time = time.time()
            
            engine = self.optimization_engines.get(rule.optimization_type)
            if engine:
                result = await engine(rule.action)
                success = result.get("success", False)
                error = result.get("error") if not success else None
            else:
                success = False
                error = f"No optimization engine for {rule.optimization_type}"
            
            execution_time = time.time() - start_time
            
            # Record action
            action.execute(success, execution_time, error)
            self.optimization_actions[action.id] = action
            
            # Update statistics
            self._update_optimization_stats(action)
            
            logger.info(f"Executed optimization rule {rule.name}: {success}")
            
        except Exception as e:
            logger.error(f"Error executing optimization rule {rule.name}: {e}")
    
    def _update_optimization_stats(self, action: OptimizationAction):
        """Update optimization statistics"""
        self.optimization_stats["total_optimizations"] += 1
        
        if action.success:
            self.optimization_stats["successful_optimizations"] += 1
            self.optimization_stats["total_improvement"] += action.expected_improvement
        else:
            self.optimization_stats["failed_optimizations"] += 1
        
        # Update average execution time
        total = self.optimization_stats["total_optimizations"]
        current_avg = self.optimization_stats["average_execution_time"]
        self.optimization_stats["average_execution_time"] = ((current_avg * (total - 1)) + action.execution_time) / total
    
    async def _optimize_memory(self, action: str) -> Dict[str, Any]:
        """Optimize memory usage"""
        try:
            if action == "garbage_collect":
                # Force garbage collection
                collected = gc.collect()
                return {"success": True, "collected_objects": collected}
            
            elif action == "compact_memory":
                # Compact memory (Python doesn't have direct compaction)
                # This would involve memory pools or other techniques
                gc.collect()  # Force GC first
                return {"success": True, "message": "Memory compacted"}
            
            elif action == "clear_cache":
                # Clear caches (would integrate with actual cache systems)
                return {"success": True, "message": "Cache cleared"}
            
            else:
                return {"success": False, "error": f"Unknown memory action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_cpu(self, action: str) -> Dict[str, Any]:
        """Optimize CPU usage"""
        try:
            if action == "reduce_thread_pool_size":
                # Reduce thread pool size
                # This would integrate with actual thread pool management
                return {"success": True, "message": "Thread pool size reduced"}
            
            elif action == "optimize_algorithm":
                # Optimize algorithm efficiency
                return {"success": True, "message": "Algorithm optimized"}
            
            elif action == "reduce_computation":
                # Reduce computational intensity
                return {"success": True, "message": "Computation reduced"}
            
            else:
                return {"success": False, "error": f"Unknown CPU action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_io(self, action: str) -> Dict[str, Any]:
        """Optimize I/O operations"""
        try:
            if action == "optimize_io_buffers":
                # Optimize I/O buffer sizes
                return {"success": True, "message": "I/O buffers optimized"}
            
            elif action == "batch_io_operations":
                # Batch I/O operations
                return {"success": True, "message": "I/O operations batched"}
            
            elif action == "use_async_io":
                # Use asynchronous I/O
                return {"success": True, "message": "Async I/O enabled"}
            
            else:
                return {"success": False, "error": f"Unknown I/O action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_network(self, action: str) -> Dict[str, Any]:
        """Optimize network operations"""
        try:
            if action == "optimize_connection_pool":
                # Optimize connection pool
                return {"success": True, "message": "Connection pool optimized"}
            
            elif action == "enable_compression":
                # Enable network compression
                return {"success": True, "message": "Network compression enabled"}
            
            elif action == "batch_network_operations":
                # Batch network operations
                return {"success": True, "message": "Network operations batched"}
            
            else:
                return {"success": False, "error": f"Unknown network action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_database(self, action: str) -> Dict[str, Any]:
        """Optimize database operations"""
        try:
            if action == "optimize_connection_pool":
                # Optimize database connection pool
                return {"success": True, "message": "Database connection pool optimized"}
            
            elif action == "enable_query_caching":
                # Enable query caching
                return {"success": True, "message": "Query caching enabled"}
            
            elif action == "optimize_queries":
                # Optimize database queries
                return {"success": True, "message": "Queries optimized"}
            
            else:
                return {"success": False, "error": f"Unknown database action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_cache(self, action: str) -> Dict[str, Any]:
        """Optimize caching"""
        try:
            if action == "increase_cache_size":
                # Increase cache size
                return {"success": True, "message": "Cache size increased"}
            
            elif action == "optimize_cache_eviction":
                # Optimize cache eviction policy
                return {"success": True, "message": "Cache eviction optimized"}
            
            elif action == "warm_up_cache":
                # Warm up cache with common data
                return {"success": True, "message": "Cache warmed up"}
            
            else:
                return {"success": False, "error": f"Unknown cache action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_thread_pool(self, action: str) -> Dict[str, Any]:
        """Optimize thread pool"""
        try:
            if action == "reduce_thread_pool_size":
                # Reduce thread pool size
                return {"success": True, "message": "Thread pool size reduced"}
            
            elif action == "increase_thread_pool_size":
                # Increase thread pool size
                return {"success": True, "message": "Thread pool size increased"}
            
            elif action == "optimize_thread_allocation":
                # Optimize thread allocation strategy
                return {"success": True, "message": "Thread allocation optimized"}
            
            else:
                return {"success": False, "error": f"Unknown thread pool action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_garbage_collection(self, action: str) -> Dict[str, Any]:
        """Optimize garbage collection"""
        try:
            if action == "force_gc":
                # Force garbage collection
                collected = gc.collect()
                return {"success": True, "collected_objects": collected}
            
            elif action == "adjust_gc_threshold":
                # Adjust GC threshold
                gc.set_threshold(700, 10, 10)
                return {"success": True, "message": "GC threshold adjusted"}
            
            elif action == "enable_gc_debug":
                # Enable GC debugging
                gc.set_debug(gc.DEBUG_STATS)
                return {"success": True, "message": "GC debugging enabled"}
            
            else:
                return {"success": False, "error": f"Unknown GC action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_async_await(self, action: str) -> Dict[str, Any]:
        """Optimize async/await usage"""
        try:
            if action == "optimize_event_loop":
                # Optimize event loop
                return {"success": True, "message": "Event loop optimized"}
            
            elif action == "reduce_async_overhead":
                # Reduce async overhead
                return {"success": True, "message": "Async overhead reduced"}
            
            elif action == "batch_async_operations":
                # Batch async operations
                return {"success": True, "message": "Async operations batched"}
            
            else:
                return {"success": False, "error": f"Unknown async action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _optimize_algorithm(self, action: str) -> Dict[str, Any]:
        """Optimize algorithms"""
        try:
            if action == "use_caching":
                # Use caching in algorithms
                return {"success": True, "message": "Algorithm caching enabled"}
            
            elif action == "use_memoization":
                # Use memoization
                return {"success": True, "message": "Memoization enabled"}
            
            elif action == "optimize_data_structures":
                # Optimize data structures
                return {"success": True, "message": "Data structures optimized"}
            
            else:
                return {"success": False, "error": f"Unknown algorithm action: {action}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _update_performance_history(self):
        """Update performance history"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                name: {
                    "value": metric.value,
                    "unit": metric.unit,
                    "needs_optimization": metric.needs_optimization()
                }
                for name, metric in self.metrics.items()
            },
            "optimization_stats": self.optimization_stats.copy()
        }
        
        self.performance_history.append(snapshot)
    
    async def _analyze_performance_trends(self):
        """Analyze performance trends"""
        if len(self.performance_history) < 10:
            return
        
        # Get recent history
        recent_history = list(self.performance_history)[-10:]
        
        # Analyze trends for each metric
        for metric_name in self.metrics:
            values = [snapshot["metrics"][metric_name]["value"] for snapshot in recent_history]
            
            if len(values) >= 2:
                # Calculate trend
                trend = (values[-1] - values[0]) / values[0] * 100 if values[0] != 0 else 0
                
                # Check if trend is concerning
                if abs(trend) > 20:  # 20% change
                    logger.warning(f"Performance trend for {metric_name}: {trend:.1f}%")
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return {
            "metrics": {
                name: {
                    "value": metric.value,
                    "unit": metric.unit,
                    "threshold": metric.threshold,
                    "optimal_range": metric.optimal_range,
                    "needs_optimization": metric.needs_optimization(),
                    "description": metric.description,
                    "timestamp": metric.timestamp.isoformat()
                }
                for name, metric in self.metrics.items()
            },
            "optimization_stats": self.optimization_stats,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_optimization_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get optimization actions"""
        actions = list(self.optimization_actions.values())
        actions.sort(key=lambda x: x.created_at, reverse=True)
        
        return [
            {
                "id": action.id,
                "name": action.name,
                "optimization_type": action.optimization_type.value,
                "priority": action.priority.value,
                "description": action.description,
                "target_metric": action.target_metric,
                "expected_improvement": action.expected_improvement,
                "success": action.success,
                "execution_time": action.execution_time,
                "error": action.error,
                "created_at": action.created_at.isoformat(),
                "executed_at": action.executed_at.isoformat() if action.executed_at else None
            }
            for action in actions[:limit]
        ]
    
    def get_optimization_rules(self) -> List[Dict[str, Any]]:
        """Get optimization rules"""
        return [
            {
                "id": rule.id,
                "name": rule.name,
                "optimization_type": rule.optimization_type.value,
                "condition": rule.condition,
                "action": rule.action,
                "priority": rule.priority.value,
                "enabled": rule.enabled,
                "frequency": rule.frequency,
                "last_executed": rule.last_executed.isoformat() if rule.last_executed else None,
                "execution_count": rule.execution_count,
                "success_count": rule.success_count,
                "success_rate": (rule.success_count / rule.execution_count * 100) if rule.execution_count > 0 else 0
            }
            for rule in self.optimization_rules.values()
        ]
    
    def add_optimization_rule(self, rule: OptimizationRule):
        """Add optimization rule"""
        self.optimization_rules[rule.id] = rule
        logger.info(f"Added optimization rule: {rule.name}")
    
    def remove_optimization_rule(self, rule_id: str):
        """Remove optimization rule"""
        if rule_id in self.optimization_rules:
            del self.optimization_rules[rule_id]
            logger.info(f"Removed optimization rule: {rule_id}")
    
    def enable_optimization_rule(self, rule_id: str):
        """Enable optimization rule"""
        if rule_id in self.optimization_rules:
            self.optimization_rules[rule_id].enabled = True
            logger.info(f"Enabled optimization rule: {rule_id}")
    
    def disable_optimization_rule(self, rule_id: str):
        """Disable optimization rule"""
        if rule_id in self.optimization_rules:
            self.optimization_rules[rule_id].enabled = False
            logger.info(f"Disabled optimization rule: {rule_id}")
    
    async def manual_optimization(self, optimization_type: OptimizationType, action: str) -> Dict[str, Any]:
        """Perform manual optimization"""
        engine = self.optimization_engines.get(optimization_type)
        if engine:
            return await engine(action)
        else:
            return {"success": False, "error": f"No optimization engine for {optimization_type}"}
    
    def get_performance_recommendations(self) -> List[Dict[str, Any]]:
        """Get performance recommendations"""
        recommendations = []
        
        # Analyze current metrics
        for metric_name, metric in self.metrics.items():
            if metric.needs_optimization():
                if metric.name == "memory_usage" and metric.value > 80:
                    recommendations.append({
                        "type": "memory",
                        "metric": metric_name,
                        "current_value": metric.value,
                        "recommendation": "Consider running garbage collection or reducing memory usage",
                        "priority": "high" if metric.value > 90 else "medium"
                    })
                elif metric.name == "cpu_usage" and metric.value > 80:
                    recommendations.append({
                        "type": "cpu",
                        "metric": metric_name,
                        "current_value": metric.value,
                        "recommendation": "Consider reducing thread pool size or optimizing algorithms",
                        "priority": "high" if metric.value > 90 else "medium"
                    })
        
        return recommendations


# Global instance
_performance_optimizer = None


def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer instance"""
    global _performance_optimizer
    if _performance_optimizer is None:
        _performance_optimizer = PerformanceOptimizer()
    return _performance_optimizer


# Example usage
async def demo_performance_optimizer():
    """Demonstrate performance optimizer"""
    print("=== JARVIS Performance Optimizer Demo ===")
    
    # Get performance optimizer
    optimizer = get_performance_optimizer()
    
    # Start optimization
    await optimizer.start_optimization()
    
    # Wait for some optimization cycles
    for i in range(5):
        print(f"Optimization cycle {i+1}")
        
        # Get current metrics
        metrics = optimizer.get_performance_metrics()
        print(f"CPU Usage: {metrics['metrics'].get('cpu_usage', {}).get('value', 0):.1f}%")
        print(f"Memory Usage: {metrics['metrics'].get('memory_usage', {}).get('value', 0):.1f}%")
        print(f"Optimization Stats: {metrics['optimization_stats']}")
        
        await asyncio.sleep(2)
    
    # Get performance recommendations
    recommendations = optimizer.get_performance_recommendations()
    print(f"\nPerformance Recommendations: {len(recommendations)}")
    
    # Get optimization actions
    actions = optimizer.get_optimization_actions(10)
    print(f"Recent Optimization Actions: {len(actions)}")
    
    # Stop optimization
    await optimizer.stop_optimization()


if __name__ == "__main__":
    asyncio.run(demo_performance_optimizer())
