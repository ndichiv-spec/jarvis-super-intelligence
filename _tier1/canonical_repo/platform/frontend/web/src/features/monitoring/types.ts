export interface HealthStatus {
  status: string;
  timestamp: string;
  version: string;
  milestone?: string;
  app_name?: string;
}

export interface MetricsData {
  timestamp: string;
  available: boolean;
  reason?: string;
  cpu_percent?: number;
  memory?: { percent?: number; available?: number; total?: number; used?: number };
  disk?: number;
  processes?: number;
  system?: SystemMetrics;
  application?: Record<string, unknown>;
  uptime_seconds?: number;
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
export type { HealthReport } from '@/lib/types/platform';
