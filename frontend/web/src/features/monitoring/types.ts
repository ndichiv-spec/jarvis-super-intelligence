export interface HealthStatus {
  status: string;
  timestamp: string;
  version: string;
  milestone?: string;
  app_name?: string;
}

export interface HealthReport {
  current_status: string;
  last_check: string;
  health_rate_percent: number;
  total_checks: number;
  healthy_checks: number;
  avg_api_response_time_ms: number;
  recent_recoveries: number;
  recent_failures: number;
  latest_checks: HealthCheck[];
}

export interface HealthCheck {
  name: string;
  status: string;
  message: string;
  response_time_ms: number;
}

export interface MetricsData {
  system: SystemMetrics;
  application: Record<string, unknown>;
  uptime_seconds: number;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_available_mb: number;
  disk_percent: number;
  disk_used_gb: number;
  process_count: number;
  network?: NetworkMetrics;
}

export interface NetworkMetrics {
  bytes_sent: number;
  bytes_recv: number;
  packets_sent: number;
  packets_recv: number;
}

export interface OptimizationReport {
  status: string;
  improvements: string[];
  metrics_before: Partial<SystemMetrics>;
  metrics_after: Partial<SystemMetrics>;
  timestamp: string;
}

export interface ConnectionStatus {
  connected: boolean;
  lastChecked: Date | null;
  error: string | null;
  retryCount: number;
}
