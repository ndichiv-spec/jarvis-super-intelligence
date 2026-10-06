import { create } from 'zustand';

interface SystemProcess {
  pid: number;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  status: string;
}

interface SystemState {
  processes: SystemProcess[];
  commonApps: Array<{ name: string; command: string; icon?: string }>;
  windows: any[];
  clipboard: string;
  isLoading: boolean;
  selectedProcess: SystemProcess | null;

  setProcesses: (processes: SystemProcess[]) => void;
  setCommonApps: (apps: any[]) => void;
  setWindows: (windows: any[]) => void;
  setClipboard: (clipboard: string) => void;
  setLoading: (loading: boolean) => void;
  setSelectedProcess: (proc: SystemProcess | null) => void;
}

export const useSystemStore = create<SystemState>((set) => ({
  processes: [],
  commonApps: [],
  windows: [],
  clipboard: '',
  isLoading: false,
  selectedProcess: null,

  setProcesses: (processes) => set({ processes }),
  setCommonApps: (apps) => set({ commonApps: apps }),
  setWindows: (windows) => set({ windows }),
  setClipboard: (clipboard) => set({ clipboard }),
  setLoading: (loading) => set({ isLoading: loading }),
  setSelectedProcess: (selectedProcess) => set({ selectedProcess }),
}));
