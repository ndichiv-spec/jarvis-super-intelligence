import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { HealthStatus, HealthReport, MetricsData, OptimizationReport } from './types';

export const monitoringApi = {
  getHealthStatus(): Promise<HealthStatus> {
    return apiClient.get<HealthStatus>(API_ENDPOINTS.health);
  },

  getHealthReport(): Promise<HealthReport> {
    return apiClient.get<HealthReport>(API_ENDPOINTS.monitoring.healthReport);
  },

  getMetrics(): Promise<MetricsData> {
    return apiClient.get<MetricsData>(API_ENDPOINTS.monitoring.metrics);
  },

  getOptimizationReport(): Promise<OptimizationReport> {
    return apiClient.get<OptimizationReport>(API_ENDPOINTS.monitoring.optimizationReport);
  },

  triggerOptimization(): Promise<{ success: boolean; report?: OptimizationReport }> {
    return apiClient.post(API_ENDPOINTS.monitoring.optimize);
  },

  getDiagnostics(): Promise<any> {
    return apiClient.get(API_ENDPOINTS.monitoring.diagnostics);
  },

  getRecoveryHistory(): Promise<any> {
    return apiClient.get(API_ENDPOINTS.monitoring.recoveryHistory);
  },

  triggerRecovery(): Promise<{ success: boolean; message: string }> {
    return apiClient.post(API_ENDPOINTS.monitoring.triggerRecovery);
  },
};

export default monitoringApi;
