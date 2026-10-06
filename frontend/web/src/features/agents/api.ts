import apiClient from '@/lib/api-client';
import API_ENDPOINTS from '@/config/api';
import type { AgentTask, AgentStats, TaskExecution, SchedulerStatus, CollaborationAgent, CollaborationTask } from './types';

export const agentsApi = {
  list(): Promise<{ tasks: AgentTask[]; agents?: CollaborationAgent[] }> {
    return apiClient.get(API_ENDPOINTS.agents.list);
  },

  getStatus(agentId: string): Promise<AgentTask> {
    return apiClient.get(`${API_ENDPOINTS.agents.list}/${agentId}`);
  },

  createTask(name: string, description: string, priority: string = 'normal'): Promise<{ success: boolean; task: AgentTask }> {
    return apiClient.post(API_ENDPOINTS.agents.task, { name, description, priority });
  },

  registerTask(task: Omit<AgentTask, 'id' | 'enabled' | 'last_run_at' | 'last_run_status' | 'last_run_duration_ms' | 'created_at'>): Promise<{ success: boolean; task: AgentTask }> {
    return apiClient.post(API_ENDPOINTS.agents.tasks, task);
  },

  toggleTask(taskId: string, enabled: boolean): Promise<{ success: boolean }> {
    return apiClient.post(`${API_ENDPOINTS.agents.tasks}/${taskId}/toggle`, { enabled });
  },

  runTask(taskId: string): Promise<{ success: boolean; execution?: TaskExecution }> {
    return apiClient.post(`${API_ENDPOINTS.agents.tasks}/${taskId}/run`);
  },

  deleteTask(taskId: string): Promise<{ success: boolean }> {
    return apiClient.delete(`${API_ENDPOINTS.agents.tasks}/${taskId}`);
  },

  getStats(): Promise<AgentStats> {
    return apiClient.get(API_ENDPOINTS.agents.stats);
  },

  getSchedulerStatus(): Promise<SchedulerStatus> {
    return apiClient.get(API_ENDPOINTS.agents.scheduler);
  },

  toggleScheduler(running: boolean): Promise<{ success: boolean }> {
    return apiClient.post(API_ENDPOINTS.agents.schedulerToggle, { running });
  },

  getExecutions(limit: number = 20): Promise<{ executions: TaskExecution[] }> {
    return apiClient.get(API_ENDPOINTS.agents.executions, { params: { limit } });
  },

  getServiceTailoring(): Promise<any> {
    return apiClient.get(API_ENDPOINTS.agents.serviceTailoring);
  },

  collaboration: {
    listAgents(): Promise<{ agents: CollaborationAgent[] }> {
      return apiClient.get(API_ENDPOINTS.agents.collaboration.agents);
    },

    listTasks(status?: string, limit: number = 50): Promise<{ tasks: CollaborationTask[] }> {
      return apiClient.get(API_ENDPOINTS.agents.collaboration.tasks, {
        params: { status, limit },
      });
    },

    createTask(description: string, agents: string[], pattern: string): Promise<{ success: boolean; task: CollaborationTask }> {
      return apiClient.post(API_ENDPOINTS.agents.collaboration.create, {
        description,
        agents_needed: agents,
        collaboration_pattern: pattern,
      });
    },

    executeTask(taskId: string): Promise<{ success: boolean }> {
      return apiClient.post(API_ENDPOINTS.agents.collaboration.execute, { task_id: taskId });
    },

    getMetrics(): Promise<any> {
      return apiClient.get(API_ENDPOINTS.agents.collaboration.metrics);
    },

    selfOrganize(description: string): Promise<{ success: boolean; task?: CollaborationTask }> {
      return apiClient.post(API_ENDPOINTS.agents.collaboration.selfOrganize, null, {
        params: { description },
      });
    },
  },
};

export default agentsApi;
