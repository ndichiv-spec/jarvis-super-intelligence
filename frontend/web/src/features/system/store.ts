import { create } from 'zustand';
import type { SystemStatus, SystemProcess, ProviderSettingsResponse, SystemCapabilities, FileInfo } from './types';
import systemApi from './api';

interface SystemState {
  status: SystemStatus | null;
  capabilities: SystemCapabilities | null;
  processes: SystemProcess[];
  providerSettings: ProviderSettingsResponse | null;
  files: FileInfo[];
  isLoading: boolean;
  error: string | null;

  loadStatus: () => Promise<void>;
  loadCapabilities: () => Promise<void>;
  loadProcesses: () => Promise<void>;
  loadProviderSettings: () => Promise<void>;
  updateProviderSettings: (data: Record<string, string>) => Promise<void>;
  listFiles: (path?: string) => Promise<void>;
  killProcess: (pid: number) => Promise<void>;
  clearError: () => void;
}

export const useSystemStore = create<SystemState>((set, get) => ({
  status: null,
  capabilities: null,
  processes: [],
  providerSettings: null,
  files: [],
  isLoading: false,
  error: null,

  loadStatus: async () => {
    try {
      const status = await systemApi.getStatus();
      set({ status });
    } catch {
      // silent
    }
  },

  loadCapabilities: async () => {
    try {
      const capabilities = await systemApi.getCapabilities();
      set({ capabilities });
    } catch {
      // silent
    }
  },

  loadProcesses: async () => {
    try {
      const data = await systemApi.getProcesses();
      set({ processes: data.processes || [] });
    } catch {
      // silent
    }
  },

  loadProviderSettings: async () => {
    set({ isLoading: true });
    try {
      const settings = await systemApi.getProviderSettings();
      set({ providerSettings: settings, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to load settings' });
    }
  },

  updateProviderSettings: async (data: Record<string, string>) => {
    set({ isLoading: true });
    try {
      const result = await systemApi.updateProviderSettings(data);
      set({ providerSettings: result, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to update settings' });
    }
  },

  listFiles: async (path?: string) => {
    try {
      const data = await systemApi.listFiles(path);
      set({ files: data.files || [] });
    } catch {
      // silent
    }
  },

  killProcess: async (pid: number) => {
    try {
      await systemApi.killProcess(pid);
      get().loadProcesses();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to kill process' });
    }
  },

  clearError: () => set({ error: null }),
}));

export default useSystemStore;
