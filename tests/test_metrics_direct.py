import sys

sys.path.insert(0, "C:/Users/Administrator/Jarvis")

# Test directly
from core.metrics import metrics, system_collector

print("Testing metrics module...")

# Collect system metrics
sys_metrics = system_collector.collect()
print("System metrics:", sys_metrics)

# Get metrics summary
summary = metrics.get_metrics_summary()
print("Metrics summary:", summary)

print("\nMetrics module is working correctly!")
