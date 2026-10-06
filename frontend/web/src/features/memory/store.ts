import { create } from 'zustand';
import type { MemoryEntry, MemoryStats, CognitiveReport } from './types';
import memoryApi from './api';

interface MemoryState {
  entries: MemoryEntry[];
  stats: MemoryStats | null;
  cognitiveReport: CognitiveReport | null;
  isLoading: boolean;
  error: string | null;

  recall: (query?: string) => Promise<void>;
  store: (content: string, layer?: string) => Promise<void>;
  loadStats: () => Promise<void>;
  loadCognitiveReport: () => Promise<void>;
  consolidate: () => Promise<void>;
  clearError: () => void;
}

export const useMemoryStore = create<MemoryState>((set, get) => ({
  entries: [],
  stats: null,
  cognitiveReport: null,
  isLoading: false,
  error: null,

  recall: async (query?: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await memoryApi.recall(query);
      set({ entries: data.entries || [], isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to recall memories' });
    }
  },

  store: async (content: string, layer: string = 'short_term') => {
    try {
      await memoryApi.store(content, layer);
      get().loadStats();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Failed to store memory' });
    }
  },

  loadStats: async () => {
    try {
      const stats = await memoryApi.getStats();
      set({ stats });
    } catch {
      // silent
    }
  },

  loadCognitiveReport: async () => {
    set({ isLoading: true });
    try {
      const report = await memoryApi.getCognitiveReport();
      set({ cognitiveReport: report, isLoading: false });
    } catch (error) {
      set({ isLoading: false, error: error instanceof Error ? error.message : 'Failed to load cognitive report' });
    }
  },

  consolidate: async () => {
    try {
      await memoryApi.consolidate();
      get().loadStats();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : 'Consolidation failed' });
    }
  },

  clearError: () => set({ error: null }),
}));

export default useMemoryStore;
