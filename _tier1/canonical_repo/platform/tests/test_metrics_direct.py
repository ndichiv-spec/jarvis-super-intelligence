
def run_metrics_probe():
    from core.metrics import metrics, system_collector

    print("Testing metrics module...")
    print("System metrics:", system_collector.collect())
    print("Metrics summary:", metrics.get_metrics_summary())
    print("\nMetrics module is working correctly!")


if __name__ == "__main__":
    run_metrics_probe()
