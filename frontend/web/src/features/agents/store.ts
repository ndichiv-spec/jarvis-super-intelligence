import { create } from 'zustand';
import type { AgentTask, AgentStats, TaskExecution, SchedulerStatus, CollaborationAgent, CollaborationTask } from './types';
import agentsApi from './api';

interface AgentsState {
  tasks: AgentTask[];
  executions: TaskExecution[];
  stats: AgentStats | null;
  schedulerStatus: SchedulerStatus | null;
  collaborationAgents: CollaborationAgent[];
  collaborationTasks: CollaborationTask[];
  isLoading: boolean;
  error: string | null;

  loadTasks: () => Promise<void>;
  loadExecutions: () => Promise<void>;
  loadStats: () => Promise<void>;
  loadSchedulerStatus: () => Promise<void>;
  toggleTask: (taskId: string, enabled: boolean) => Promise<void>;
  runTask: (taskId: string) => Promise<void>;
  deleteTask: (taskId: string) => Promise<void>;
  registerTask: (task: Omit<AgentTask, 'id' | 'enabled' | 'last_run_at' | 'last_run_status' | 'last_run_duration_ms' | 'created_at'>) => Promise<AgentTask | null>;
  toggleScheduler: (running: boolean) => Promise<void>;
  loadCollaborationAgents: () => Promise<void>;
  loadCollaborationTasks: () => Promise<void>;
  loadAll: () => Promise<void>;
  clearError: () => void;
}

export const useAgentsStore = create<AgentsState>((set, get) => ({
  tasks: [],
  executions: [],
  stats: null,
  schedulerStatus: null,
  collaborationAgents: [],
  collaborationTasks: [],
  isLoading: false,
  error: null,

  loadTasks: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await agentsApi.list();
      set({ tasks: data.tasks || [], isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to load tasks' });
    }
  },

  loadExecutions: async () => {
    try {
      const data = await agentsApi.getExecutions();
      set({ executions: data.executions || [] });
    } catch {
      // silent
    }
  },

  loadStats: async () => {
    try {
      const stats = await agentsApi.getStats();
      set({ stats });
    } catch {
      // silent
    }
  },

  loadSchedulerStatus: async () => {
    try {
      const status = await agentsApi.getSchedulerStatus();
      set({ schedulerStatus: status });
    } catch {
      // silent
    }
  },

  toggleTask: async (taskId: string, enabled: boolean) => {
    try {
      await agentsApi.toggleTask(taskId, enabled);
      set((state) => ({
        tasks: state.tasks.map((t) => (t.id === taskId ? { ...t, enabled } : t)),
      }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to toggle task' });
    }
  },

  runTask: async (taskId: string) => {
    try {
      await agentsApi.runTask(taskId);
      get().loadExecutions();
      get().loadTasks();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to run task' });
    }
  },

  deleteTask: async (taskId: string) => {
    try {
      await agentsApi.deleteTask(taskId);
      set((state) => ({ tasks: state.tasks.filter((t) => t.id !== taskId) }));
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to delete task' });
    }
  },

  registerTask: async (task: Omit<AgentTask, 'id' | 'enabled' | 'last_run_at' | 'last_run_status' | 'last_run_duration_ms' | 'created_at'>) => {
    try {
      const result = await agentsApi.registerTask(task);
      return result.task || null;
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to register task' });
      return null;
    }
  },

  toggleScheduler: async (running: boolean) => {
    try {
      await agentsApi.toggleScheduler(running);
      set({ schedulerStatus: { ...get().schedulerStatus!, running } });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to toggle scheduler' });
    }
  },

  loadCollaborationAgents: async () => {
    try {
      const data = await agentsApi.collaboration.listAgents();
      set({ collaborationAgents: data.agents || [] });
    } catch {
      // silent
    }
  },

  loadCollaborationTasks: async () => {
    try {
      const data = await agentsApi.collaboration.listTasks();
      set({ collaborationTasks: data.tasks || [] });
    } catch {
      // silent
    }
  },

  clearError: () => set({ error: null }),

  loadAll: async () => {
    await Promise.allSettled([
      get().loadTasks(),
      get().loadExecutions(),
      get().loadStats(),
      get().loadSchedulerStatus(),
      get().loadCollaborationAgents(),
      get().loadCollaborationTasks(),
    ]);
  },
}));

export default useAgentsStore;
