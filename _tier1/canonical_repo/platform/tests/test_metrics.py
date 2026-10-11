def run_metrics_probe():
    from core.metrics import metrics, system_collector

    print("Metrics module loaded")
    print("System metrics:", system_collector.get_system_metrics())
    print("App metrics:", metrics.get_metrics())


if __name__ == "__main__":
    run_metrics_probe()
