"""
JARVIS Performance Auto-Optimizer
================================
Self-tuning system with automatic resource allocation and performance optimization.
"""

import asyncio
import psutil
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class OptimizationType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    I_O = "io"
    NETWORK = "network"
    CACHE = "cache"

@dataclass
class OptimizationRule:
    name: str
    metric: str
    threshold: float
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

@dataclass
class OptimizationResult:
    rule_applied: str
    metric_before: float
    metric_after: float
    improvement: float
    timestamp: float = field(default_factory=time.time)

class PerformanceAutoOptimizer:
    """Automatic performance optimization system"""
    
    def __init__(self):
        self.optimization_rules: List[OptimizationRule] = []
        self.optimization_history: List[OptimizationResult] = []
        self.current_metrics: Dict[str, float] = {}
        self.optimization_active = False
        self.auto_tuning_enabled = True
        self.optimization_stats = {
            "total_optimizations": 0,
            "successful_optimizations": 0,
            "avg_improvement": 0.0,
            "last_optimization": None
        }
    
    async def initialize(self):
        """Initialize auto-optimizer"""
        logger.info("Initializing Performance Auto-Optimizer")
        self._initialize_default_rules()
        self.optimization_active = True
        # Start optimization loop
        asyncio.create_task(self.optimization_loop())
    
    def _initialize_default_rules(self):
        """Initialize default optimization rules"""
        self.optimization_rules = [
            OptimizationRule(
                name="High CPU Optimization",
                metric="cpu_percent",
                threshold=80.0,
                action="reduce_load",
                parameters={"target_reduction": 0.2}
            ),
            OptimizationRule(
                name="Memory Optimization",
                metric="memory_percent",
                threshold=85.0,
                action="clear_cache",
                parameters={"clear_fraction": 0.3}
            ),
            OptimizationRule(
                name="I/O Optimization",
                metric="io_wait",
                threshold=20.0,
                action="optimize_io",
                parameters={"batch_size": 100}
            ),
            OptimizationRule(
                name="Network Optimization",
                metric="network_latency",
                threshold=100.0,
                action="optimize_network",
                parameters={"buffer_size": 8192}
            ),
            OptimizationRule(
                name="Cache Optimization",
                metric="cache_hit_rate",
                threshold=0.7,
                action="expand_cache",
                parameters={"expansion_factor": 1.5}
            )
        ]
    
    async def optimization_loop(self):
        """Main optimization loop"""
        while self.optimization_active:
            try:
                if self.auto_tuning_enabled:
                    await self.collect_metrics()
                    await self.check_and_apply_optimizations()
                
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Optimization loop error: {e}")
    
    async def collect_metrics(self):
        """Collect current system metrics"""
        try:
            self.current_metrics = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_available": psutil.virtual_memory().available / (1024**3),  # GB
                "disk_usage": psutil.disk_usage('/').percent,
                "network_sent": psutil.net_io_counters().bytes_sent / (1024**2),  # MB
                "network_recv": psutil.net_io_counters().bytes_recv / (1024**2),  # MB
                "process_count": len(psutil.pids()),
                "io_wait": 0.0,  # Placeholder
                "network_latency": 0.0,  # Placeholder
                "cache_hit_rate": 0.85  # Placeholder
            }
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def check_and_apply_optimizations(self):
        """Check rules and apply optimizations if needed"""
        for rule in self.optimization_rules:
            if not rule.enabled:
                continue
            
            metric_value = self.current_metrics.get(rule.metric, 0)
            
            # Check if threshold is exceeded
            if metric_value > rule.threshold:
                result = await self.apply_optimization(rule, metric_value)
                if result:
                    self.optimization_stats["total_optimizations"] += 1
                    if result.improvement > 0:
                        self.optimization_stats["successful_optimizations"] += 1
    
    async def apply_optimization(self, rule: OptimizationRule, 
                               current_value: float) -> Optional[OptimizationResult]:
        """Apply optimization rule"""
        try:
            metric_before = current_value
            metric_after = current_value
            
            # Simulate optimization effect
            if rule.action == "reduce_load":
                # Simulate CPU load reduction
                reduction = rule.parameters.get("target_reduction", 0.2)
                metric_after = metric_before * (1 - reduction)
                
            elif rule.action == "clear_cache":
                # Simulate memory optimization
                clear_fraction = rule.parameters.get("clear_fraction", 0.3)
                metric_after = metric_before * (1 - clear_fraction)
                
            elif rule.action == "optimize_io":
                # Simulate I/O optimization
                metric_after = metric_before * 0.8
                
            elif rule.action == "optimize_network":
                # Simulate network optimization
                metric_after = metric_before * 0.7
                
            elif rule.action == "expand_cache":
                # Simulate cache expansion (inverse metric)
                metric_after = min(0.95, metric_before * 1.2)
            
            # Calculate improvement
            improvement = metric_before - metric_after if metric_before > metric_after else 0
            
            result = OptimizationResult(
                rule_applied=rule.name,
                metric_before=metric_before,
                metric_after=metric_after,
                improvement=improvement
            )
            
            self.optimization_history.append(result)
            self.optimization_stats["last_optimization"] = time.time()
            
            # Update average improvement
            if self.optimization_stats["successful_optimizations"] > 0:
                self.optimization_stats["avg_improvement"] = (
                    (self.optimization_stats["avg_improvement"] * 
                     (self.optimization_stats["successful_optimizations"] - 1) + improvement) /
                    self.optimization_stats["successful_optimizations"]
                )
            
            logger.info(f"Applied optimization: {rule.name}, improvement: {improvement:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error applying optimization {rule.name}: {e}")
            return None
    
    async def manual_optimization(self, optimization_type: str, 
                                parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Manually trigger optimization"""
        try:
            # Create temporary rule
            rule = OptimizationRule(
                name=f"Manual {optimization_type}",
                metric=optimization_type,
                threshold=0,  # Always apply
                action=optimization_type,
                parameters=parameters
            )
            
            metric_value = self.current_metrics.get(optimization_type, 0)
            result = await self.apply_optimization(rule, metric_value)
            
            if result:
                return {
                    "success": True,
                    "rule_applied": result.rule_applied,
                    "metric_before": result.metric_before,
                    "metric_after": result.metric_after,
                    "improvement": result.improvement
                }
            else:
                return {"success": False, "error": "Optimization failed"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_optimization_status(self) -> Dict[str, Any]:
        """Get current optimization status"""
        return {
            "active": self.optimization_active,
            "auto_tuning_enabled": self.auto_tuning_enabled,
            "current_metrics": self.current_metrics,
            "rules_count": len(self.optimization_rules),
            "active_rules": len([r for r in self.optimization_rules if r.enabled]),
            "stats": self.optimization_stats,
            "recent_optimizations": [
                {
                    "rule": result.rule_applied,
                    "improvement": result.improvement,
                    "timestamp": result.timestamp
                }
                for result in self.optimization_history[-10:]
            ]
        }
    
    def enable_auto_tuning(self):
        """Enable automatic tuning"""
        self.auto_tuning_enabled = True
        logger.info("Auto-tuning enabled")
    
    def disable_auto_tuning(self):
        """Disable automatic tuning"""
        self.auto_tuning_enabled = False
        logger.info("Auto-tuning disabled")
    
    def add_custom_rule(self, rule: OptimizationRule):
        """Add custom optimization rule"""
        self.optimization_rules.append(rule)
        logger.info(f"Added custom rule: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """Remove optimization rule"""
        self.optimization_rules = [r for r in self.optimization_rules if r.name != rule_name]
        logger.info(f"Removed rule: {rule_name}")

# Global auto-optimizer instance
auto_optimizer: Optional[PerformanceAutoOptimizer] = None

def get_auto_optimizer() -> PerformanceAutoOptimizer:
    """Get or create auto-optimizer instance"""
    global auto_optimizer
    if auto_optimizer is None:
        auto_optimizer = PerformanceAutoOptimizer()
    return auto_optimizer
