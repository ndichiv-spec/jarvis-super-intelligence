import { create } from 'zustand';
import type { AutomationTask } from './types';
import automationApi from './api';

interface AutomationState {
  tasks: AutomationTask[];
  isLoading: boolean;
  error: string | null;

  loadTasks: () => Promise<void>;
  runTask: (taskId: string) => Promise<void>;
  clearError: () => void;
}

export const useAutomationStore = create<AutomationState>((set) => ({
  tasks: [],
  isLoading: false,
  error: null,

  loadTasks: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await automationApi.getTasks();
      set({ tasks: data.tasks || [], isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to load automation tasks' });
    }
  },

  runTask: async (taskId: string) => {
    try {
      await automationApi.runTask(taskId);
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to run automation task' });
    }
  },

  clearError: () => set({ error: null }),
}));

export default useAutomationStore;
