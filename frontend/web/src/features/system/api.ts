import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { SystemStatus, SystemProcess, ProviderSettingsResponse, SystemCapabilities, FileInfo, ModelCatalog, ServiceStatus } from './types';

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

  updateProviderSettings(
    data: Partial<Pick<ProviderSettingsResponse['settings'], 'ollama_base_url' | 'ollama_model' | 'aws_region'>>,
  ): Promise<ProviderSettingsResponse> {
    return apiClient.put<ProviderSettingsResponse>(API_ENDPOINTS.system.providerSettings, {
      ollama_base_url: data.ollama_base_url,
      ollama_model: data.ollama_model,
      aws_region: data.aws_region,
    });
  },

  listFiles(path: string = '.'): Promise<{ files: FileInfo[] }> {
    return apiClient.get(API_ENDPOINTS.system.files, { params: { path } });
  },

  readFile(path: string): Promise<{ path: string; content: string }> {
    return apiClient.post(API_ENDPOINTS.system.fileRead, { path });
  },

  getModels(): Promise<ModelCatalog> {
    return apiClient.get<ModelCatalog>(API_ENDPOINTS.system.models);
  },

  getServices(): Promise<ServiceStatus> {
    return apiClient.get<ServiceStatus>(API_ENDPOINTS.system.services);
  },

  getIdentity(): Promise<any> {
    return apiClient.get(API_ENDPOINTS.system.identity);
  },

  killProcess(pid: number, force: boolean = false): Promise<{ success: boolean }> {
    return apiClient.post(`${API_ENDPOINTS.system.processes}/kill`, { pid, force });
  },
};

export default systemApi;
