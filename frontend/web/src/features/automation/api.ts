import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { AutomationTask, AutomationExecution, AutomationStats } from './types';

export const automationApi = {
  getTasks(): Promise<{ tasks: AutomationTask[] }> {
    return apiClient.get(API_ENDPOINTS.automation.tasks);
  },

  runTask(taskId: string): Promise<{ success: boolean; execution?: AutomationExecution }> {
    return apiClient.post(API_ENDPOINTS.automation.runTask(taskId));
  },
};

export default automationApi;
