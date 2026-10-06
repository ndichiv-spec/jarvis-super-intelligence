import { create } from 'zustand';

interface MetricsData {
  cpu_percent: number;
  memory_percent: number;
  disk_percent: number;
  process_count: number;
  uptime_seconds: number;
}

interface MonitoringState {
  healthStatus: string;
  healthRate: number;
  metrics: MetricsData | null;
  recoveryHistory: any[];
  optimizationReport: any | null;
  lastUpdated: Date | null;
  isLoading: boolean;

  setHealthStatus: (status: string, rate: number) => void;
  setMetrics: (metrics: MetricsData) => void;
  setRecoveryHistory: (history: any[]) => void;
  setOptimizationReport: (report: any) => void;
  setLastUpdated: (time: Date) => void;
  setLoading: (loading: boolean) => void;
}

export const useMonitoringStore = create<MonitoringState>((set) => ({
  healthStatus: 'unknown',
  healthRate: 0,
  metrics: null,
  recoveryHistory: [],
  optimizationReport: null,
  lastUpdated: null,
  isLoading: false,

  setHealthStatus: (healthStatus, healthRate) => set({ healthStatus, healthRate }),
  setMetrics: (metrics) => set({ metrics }),
  setRecoveryHistory: (recoveryHistory) => set({ recoveryHistory }),
  setOptimizationReport: (optimizationReport) => set({ optimizationReport }),
  setLastUpdated: (lastUpdated) => set({ lastUpdated }),
  setLoading: (isLoading) => set({ isLoading }),
}));
