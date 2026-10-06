import sys

sys.path.insert(0, "C:/Users/Administrator/Jarvis")

# Test the metrics endpoints
from core.metrics import metrics, system_collector

print("Metrics module loaded")

# Get system metrics
sys_metrics = system_collector.get_system_metrics()
print("System metrics:", sys_metrics)

app_metrics = metrics.get_metrics()
print("App metrics:", app_metrics)
