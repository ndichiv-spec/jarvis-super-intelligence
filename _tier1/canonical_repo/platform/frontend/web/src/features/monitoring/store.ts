import { create } from 'zustand';
import type { HealthStatus, HealthReport, MetricsData, OptimizationReport } from './types';
import monitoringApi from './api';

interface MonitoringState {
  health: HealthStatus | null;
  healthReport: HealthReport | null;
  metrics: MetricsData | null;
  optimizationReport: OptimizationReport | null;
  recoveryHistory: unknown[];
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;

  loadHealth: () => Promise<void>;
  loadHealthReport: () => Promise<void>;
  loadMetrics: () => Promise<void>;
  loadOptimizationReport: () => Promise<void>;
  loadRecoveryHistory: () => Promise<void>;
  triggerOptimization: () => Promise<void>;
  clearError: () => void;
}

export const useMonitoringStore = create<MonitoringState>((set) => ({
  health: null,
  healthReport: null,
  metrics: null,
  optimizationReport: null,
  recoveryHistory: [],
  isLoading: false,
  error: null,
  lastUpdated: null,

  loadHealth: async () => {
    try {
      const health = await monitoringApi.getHealthStatus();
      set({ health, lastUpdated: new Date() });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load health status' });
    }
  },

  loadHealthReport: async () => {
    set({ isLoading: true, error: null });
    try {
      const healthReport = await monitoringApi.getHealthReport();
      set({ healthReport, isLoading: false, lastUpdated: new Date() });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to load health report' });
    }
  },

  loadMetrics: async () => {
    try {
      const metrics = await monitoringApi.getMetrics();
      set({ metrics, lastUpdated: new Date() });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load monitoring metrics' });
    }
  },

  loadOptimizationReport: async () => {
    try {
      const report = await monitoringApi.getOptimizationReport();
      set({ optimizationReport: report });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load optimization report' });
    }
  },

  loadRecoveryHistory: async () => {
    try {
      const history = await monitoringApi.getRecoveryHistory();
      set({ recoveryHistory: Array.isArray(history) ? history : [] });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to load recovery history' });
    }
  },

  triggerOptimization: async () => {
    set({ isLoading: true });
    try {
      const result = await monitoringApi.triggerOptimization();
      if (result.report) {
        set({ optimizationReport: result.report });
      }
      set({ isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Optimization failed' });
    }
  },

  clearError: () => set({ error: null }),
}));

export default useMonitoringStore;
