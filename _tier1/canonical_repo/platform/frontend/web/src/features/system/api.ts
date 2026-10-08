import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { SystemStatus, SystemProcess, ProviderSettingsResponse, SystemCapabilities, FileInfo } from './types';

export const systemApi = {
  getStatus(): Promise<SystemStatus> {
    return apiClient.get<SystemStatus>(API_ENDPOINTS.system.status);
  },

  getCapabilities(): Promise<SystemCapabilities> {
    return apiClient.get<SystemCapabilities>(API_ENDPOINTS.system.capabilities);
  },

  getProcesses(limit: number = 50, sortBy: string = 'cpu'): Promise<{ processes: SystemProcess[] }> {
    return apiClient.get(API_ENDPOINTS.system.processes, { params: { limit, sort: sortBy } });
  },

  getProviderSettings(): Promise<ProviderSettingsResponse> {
    return apiClient.get<ProviderSettingsResponse>(API_ENDPOINTS.system.providerSettings);
  },

  updateProviderSettings(data: Record<string, string>): Promise<ProviderSettingsResponse> {
    return apiClient.put<ProviderSettingsResponse>(API_ENDPOINTS.system.providerSettings, data);
  },

  listFiles(path: string = '.'): Promise<{ files: FileInfo[] }> {
    return apiClient.get(API_ENDPOINTS.system.files, { params: { path } });
  },

  killProcess(pid: number, force: boolean = false): Promise<{ success: boolean }> {
    return apiClient.post(`${API_ENDPOINTS.system.processes}/kill`, { pid, force });
  },
};

export default systemApi;
